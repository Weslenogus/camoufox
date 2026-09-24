"""
Verify the Android navigator bindings (patches/android/android-02-navigator.patch).

With {"device:profile": "pixel10"} these must hold, and hold identically in
every realm a page can reach -- a worker that disagrees with its window is a
one-line check:

    navigator.platform             "Linux aarch64"   window, iframes, all workers
    navigator.hardwareConcurrency  8                 window, iframes, all workers
    navigator.deviceMemory         8                 window, iframes, all workers
    navigator.maxTouchPoints       5                 window, iframes
    navigator.vendor               "Google Inc."     window, iframes

(maxTouchPoints and vendor are Window-only members in every browser, so workers
are checked for their *absence* instead.)

The control launch, without the profile, must keep Firefox's own shape: no
deviceMemory member at all, an empty vendor, no digitizer.

Run:
    python tests/patches/android-navigator.py [--binary /path/to/camoufox-bin]
"""

import asyncio
import os
from typing import Any, Dict

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

COLLECT = r"""
function collect(scope) {
  const n = scope.navigator;
  return {
    platform: n.platform,
    hardwareConcurrency: n.hardwareConcurrency,
    deviceMemory: 'deviceMemory' in n ? n.deviceMemory : 'absent',
    maxTouchPoints: 'maxTouchPoints' in n ? n.maxTouchPoints : 'absent',
    vendor: 'vendor' in n ? n.vendor : 'absent',
  };
}
"""

WORKER_JS = COLLECT + "postMessage(collect(self));"
SHARED_JS = COLLECT + "onconnect = e => e.ports[0].postMessage(collect(self));"
SW_JS = COLLECT + (
    "self.addEventListener('install', () => self.skipWaiting());"
    "self.addEventListener('message', e => e.ports[0].postMessage(collect(self)));"
)
FRAME_HTML = "<script>" + COLLECT + "parent.postMessage({frame: collect(window)}, '*');</script>"

INDEX_HTML = "<!doctype html><title>realms</title><script>" + COLLECT + r"""
window.realms = (async () => {
  if (!document.body) await new Promise(r => addEventListener('DOMContentLoaded', r));
  const out = {window: collect(window)};
  const fromFrame = src => new Promise(resolve => {
    const f = document.createElement('iframe');
    addEventListener('message', function h(e) {
      if (e.source === f.contentWindow) { removeEventListener('message', h); resolve(e.data.frame); }
    });
    Object.assign(f, src);
    document.body.appendChild(f);
  });
  out.iframe = await fromFrame({src: '/frame.html'});
  const sandboxed = document.createElement('iframe');
  sandboxed.setAttribute('sandbox', 'allow-scripts');
  out['sandboxed iframe'] = await new Promise(resolve => {
    addEventListener('message', function h(e) {
      if (e.source === sandboxed.contentWindow) { removeEventListener('message', h); resolve(e.data.frame); }
    });
    sandboxed.srcdoc = %FRAME%;
    document.body.appendChild(sandboxed);
  });
  out.worker = await new Promise(r => { new Worker('/worker.js').onmessage = e => r(e.data); });
  // Chrome ships SharedWorker on Android since M148.
  if ('SharedWorker' in window) {
    out['shared worker'] = await new Promise(r => {
      const s = new SharedWorker('/shared.js'); s.port.onmessage = e => r(e.data); s.port.start();
    });
  }
  try {
    const reg = await navigator.serviceWorker.register('/sw.js');
    const sw = reg.installing || reg.waiting || reg.active;
    out['service worker'] = await new Promise(r => {
      const ch = new MessageChannel(); ch.port1.onmessage = e => r(e.data);
      const send = () => sw.postMessage(null, [ch.port2]);
      sw.state === 'activated' ? send() : sw.addEventListener('statechange', () => sw.state === 'activated' && send());
    });
  } catch (e) {
    out['service worker'] = 'unavailable: ' + e;
  }
  return out;
})();
</script>"""

REALMS = ("window", "iframe", "sandboxed iframe", "worker", "shared worker", "service worker")
WINDOW_REALMS = ("window", "iframe", "sandboxed iframe")


def expectations(per_realm: Dict[str, Any], window_only: Dict[str, Any],
                 realms=REALMS) -> Dict[str, Any]:
    expected = {}
    for realm in realms:
        for key, want in per_realm.items():
            expected[f"{realm}: {key}"] = want
        for key, want in window_only.items():
            expected[f"{realm}: {key}"] = want if realm in WINDOW_REALMS else "absent"
    return expected


async def probe(binary, config) -> Dict[str, Any]:
    import json

    routes = {
        # "<\/" so the srcdoc string's own </script> does not end the page's.
        "/": ("text/html", INDEX_HTML.replace(
            "%FRAME%", json.dumps(FRAME_HTML).replace("</", "<\\/"))),
        "/frame.html": ("text/html", FRAME_HTML),
        "/worker.js": ("text/javascript", WORKER_JS),
        "/shared.js": ("text/javascript", SHARED_JS),
        "/sw.js": ("text/javascript", SW_JS),
    }
    with PageServer(routes) as server:
        # allowMainWorld only unlocks the guard's own "mw:" read of the page's
        # result; the values themselves are collected by page scripts.
        async with launch_raw(binary, dict(config, allowMainWorld=True)) as page:
            await page.goto(server.url("/"))
            realms = await asyncio.wait_for(page.evaluate("mw:window.realms"), 30)
    flat = {}
    for realm in REALMS:
        values = realms.get(realm)
        if values is None:
            continue  # not a realm this browser has
        if not isinstance(values, dict):
            print(f"  {realm}: {values}")
            continue
        for key, value in values.items():
            flat[f"{realm}: {key}"] = value
    return flat


def present_realms(flat: Dict[str, Any]):
    return tuple(r for r in REALMS if any(k.startswith(r + ":") for k in flat))


async def main(binary) -> bool:
    print("\n=== pixel10: every realm ===")
    flat = await probe(binary, PIXEL10)
    realms = present_realms(flat)
    print(f"  realms: {', '.join(realms)}")
    pixel = compare(
        flat,
        expectations(
            {"platform": "Linux aarch64", "hardwareConcurrency": 8, "deviceMemory": 8},
            {"maxTouchPoints": 5, "vendor": "Google Inc."},
            realms,
        ),
    )
    # Window, both iframes and both kinds of dedicated worker must be there.
    required = {"window", "iframe", "sandboxed iframe", "worker", "service worker"}
    if not required <= set(realms):
        print(f"  FAIL: missing realms {sorted(required - set(realms))}")
        pixel = False

    print("\n=== control (no profile): Firefox's own shape ===")
    control = compare(
        await probe(binary, {}),
        expectations(
            {"platform": "Linux x86_64" if os.uname().machine == "x86_64" else "Linux aarch64",
             "hardwareConcurrency": lambda v: isinstance(v, int) and v > 0,
             "deviceMemory": "absent"},
            {"maxTouchPoints": 0, "vendor": ""},
        ),
    )
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
