"""
Verify User-Agent Client Hints (patches/android/android-05-client-hints.patch).

Firefox has no client hints at all. With {"device:profile": "pixel10"} a page
must see Chrome-on-Android's -- in navigator.userAgentData (window and worker)
and in the Sec-CH-UA request headers -- and the two must agree, because the
cheapest check there is compares them.

    brands          Chromium's GREASE algorithm for the configured major version
    mobile          true                 platform         "Android"
    model           "Pixel 10"           platformVersion  "17.0.0"
    architecture    ""                   bitness          ""
    formFactors     ["Mobile"]           wow64            false

(architecture and bitness are empty on purpose: that is what Chrome on an
Android phone reports -- components/embedder_support/user_agent_utils.cc returns
"" for both unless the device is a desktop or XR form factor.)

The control launch, without the profile, must have no userAgentData and send no
Sec-CH-UA header, exactly like stock Firefox.

Run:
    python tests/patches/android-client-hints.py [--binary /path/to/camoufox-bin]
"""

import asyncio
from typing import Any, Dict, List

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

CHROME_MAJOR = 155
CHROME_FULL = "155.0.8059.16"


def chrome_brands(seed: int, version: str, full: bool) -> List[Dict[str, str]]:
    """Chromium's GenerateBrandVersionList(), reimplemented independently."""
    chars = [" ", "(", ":", "-", ".", "/", ")", ";", "=", "?", "_"]
    grease = f"Not{chars[seed % 11]}A{chars[(seed + 1) % 11]}Brand"
    grease_version = ["8", "99", "24"][seed % 3] + (".0.0.0" if full else "")
    orders = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]]
    listed = [
        {"brand": grease, "version": grease_version},
        {"brand": "Chromium", "version": version},
        {"brand": "Google Chrome", "version": version},
    ]
    out = [None, None, None]
    for i, pos in enumerate(orders[seed % 6]):
        out[pos] = listed[i]
    return out


def sec_ch_ua(brands: List[Dict[str, str]]) -> str:
    return ", ".join(f'"{b["brand"]}";v="{b["version"]}"' for b in brands)


BRANDS = chrome_brands(CHROME_MAJOR, str(CHROME_MAJOR), False)
FULL_LIST = chrome_brands(CHROME_MAJOR, CHROME_FULL, True)

HINTS = ["architecture", "bitness", "formFactors", "fullVersionList", "model",
         "platformVersion", "uaFullVersion", "wow64"]

PROBE = r"""async (hints) => {
  const collect = async (nav, hints) => {
    if (!('userAgentData' in nav)) return 'absent';
    const d = nav.userAgentData;
    return {
      brands: d.brands, mobile: d.mobile, platform: d.platform,
      sameObject: d === nav.userAgentData,
      frozen: Object.isFrozen(d.brands),
      json: JSON.stringify(d),
      high: await d.getHighEntropyValues(hints),
    };
  };
  const worker = await new Promise(resolve => {
    const w = new Worker(URL.createObjectURL(new Blob([
      // collect's source only: the hints travel in the message.
      `onmessage = async e => postMessage(await (${collect.toString()})(navigator, JSON.parse(e.data)));`
    ], {type: 'text/javascript'})));
    w.onmessage = e => resolve(e.data);
    w.onerror = e => resolve('worker error: ' + e.message);
    w.postMessage(JSON.stringify(hints));
  });
  return {window: await collect(navigator, hints), worker,
          interfaceExposed: 'NavigatorUAData' in window};
}"""

INDEX = "<!doctype html><title>ch</title>"


async def probe(binary, config):
    with PageServer({"/": ("text/html", INDEX), "/sub.css": ("text/css", "")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            data = await page.evaluate(PROBE, HINTS)
            await page.evaluate("fetch('/sub.css').then(r => r.text())")
        return data, server.headers_for("/"), server.headers_for("/sub.css")


def expected_values() -> Dict[str, Any]:
    high = {
        "architecture": "", "bitness": "", "brands": BRANDS,
        "formFactors": ["Mobile"], "fullVersionList": FULL_LIST, "mobile": True,
        "model": "Pixel 10", "platform": "Android", "platformVersion": "17.0.0",
        "uaFullVersion": CHROME_FULL, "wow64": False,
    }
    return {
        "brands": BRANDS, "mobile": True, "platform": "Android",
        "sameObject": True, "frozen": True,
        "json": '{"brands":%s,"mobile":true,"platform":"Android"}' % (
            __import__("json").dumps(BRANDS, separators=(",", ":"))),
        "high": high,
    }


async def main(binary) -> bool:
    ok = True
    print(f"\n=== pixel10: Chrome {CHROME_MAJOR} brands {sec_ch_ua(BRANDS)} ===")
    data, doc_headers, sub_headers = await probe(binary, PIXEL10)
    want = expected_values()
    print("  window:")
    ok &= compare(data["window"], want)
    print("  worker:")
    ok &= compare(data["worker"], want)
    ok &= compare({"interfaceExposed": data["interfaceExposed"]}, {"interfaceExposed": True})

    # The task asks for the high-entropy hints on every request, not only
    # after an Accept-CH opt-in ("clientHints:sendHighEntropy").
    want_headers = {
        "sec-ch-ua": sec_ch_ua(BRANDS),
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-ch-ua-arch": '""',
        "sec-ch-ua-bitness": '""',
        "sec-ch-ua-model": '"Pixel 10"',
        "sec-ch-ua-platform-version": '"17.0.0"',
    }
    for label, requests in (("document", doc_headers), ("subresource", sub_headers)):
        print(f"  {label} request headers:")
        if not requests:
            print("    FAIL: request never reached the server")
            ok = False
            continue
        ok &= compare({k: requests[-1].get(k) for k in want_headers}, want_headers)
        order = [k for k in requests[-1] if k.startswith("sec-ch-ua") or k == "user-agent"]
        ok &= compare({"client hints precede User-Agent": order[-1] == "user-agent"},
                      {"client hints precede User-Agent": True})

    print("\n=== control (no profile): no client hints anywhere ===")
    data, doc_headers, _ = await probe(binary, {})
    ok &= compare(
        {"window": data["window"], "worker": data["worker"],
         "interfaceExposed": data["interfaceExposed"],
         "sec-ch-ua header": any(k.startswith("sec-ch-ua") for k in doc_headers[-1])},
        {"window": "absent", "worker": "absent", "interfaceExposed": False,
         "sec-ch-ua header": False},
    )
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
