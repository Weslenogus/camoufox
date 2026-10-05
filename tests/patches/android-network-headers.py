"""
Verify network identity (patches/android/android-13-network-headers.patch).

With {"device:profile": "pixel10"}, on every request -- documents,
subresources, fetch(), workers, WebSockets alike:

    User-Agent       Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36
                     (KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36
    Accept-Language  fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7

and navigator.userAgent / appVersion agree with the header in the window and in
a worker (Chrome's reduced Android UA never names the model or the real
Android version: "Android 10; K" is fixed). Firefox's own navigator members
(oscpu, buildID, taintEnabled) are absent and productSub is Chrome's.

WebRTC: host ICE candidates must never carry the machine's LAN address or its
hostname. They are random mDNS names (<uuid>.local), which is also what
Chrome on Android sends.

Run:
    python tests/patches/android-network-headers.py [--binary /path/to/camoufox-bin]
"""

import re
import socket

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36")
APP_VERSION = UA[len("Mozilla/"):]
ACCEPT_LANGUAGE = "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"

PAGE = """<!doctype html><title>net</title>
<img src="/img.png"><link rel=stylesheet href="/s.css">"""

PROBE = r"""async () => {
  await fetch('/fetch.txt').then(r => r.text());
  const worker = await new Promise(resolve => {
    const w = new Worker('/w.js');
    w.onmessage = e => resolve(e.data);
  });
  const pc = new RTCPeerConnection({iceServers: []});
  pc.createDataChannel('x');
  const candidates = [];
  pc.onicecandidate = e => { if (e.candidate) candidates.push(e.candidate.candidate); };
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise(r => setTimeout(r, 1500));
  pc.close();
  return {ua: navigator.userAgent, appVersion: navigator.appVersion, worker, candidates,
          firefoxOnly: ['oscpu', 'buildID', 'taintEnabled'].filter(k => k in navigator),
          productSub: navigator.productSub};
}"""

WORKER = """fetch('/worker-fetch.txt').then(() =>
  postMessage({ua: navigator.userAgent, appVersion: navigator.appVersion}));"""


async def probe(binary, config):
    routes = {
        "/": ("text/html", PAGE), "/img.png": ("image/png", ""), "/s.css": ("text/css", ""),
        "/fetch.txt": ("text/plain", "ok"), "/w.js": ("text/javascript", WORKER),
        "/worker-fetch.txt": ("text/plain", "ok"),
    }
    with PageServer(routes) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            data = await page.evaluate(PROBE)
        return data, server.requests


def lan_addresses():
    addrs = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            addrs.add(info[4][0])
    except OSError:
        pass
    return {a for a in addrs if not a.startswith("127.") and a != "::1"}


async def main(binary) -> bool:
    print("\n=== pixel10: headers on every request ===")
    data, requests = await probe(binary, PIXEL10)
    ok = True
    for path, headers in requests:
        ok &= compare({f"{path} user-agent": headers.get("user-agent"),
                       f"{path} accept-language": headers.get("accept-language")},
                      {f"{path} user-agent": UA, f"{path} accept-language": ACCEPT_LANGUAGE})
    seen = {p for p, _ in requests}
    for path in ("/", "/img.png", "/s.css", "/fetch.txt", "/w.js", "/worker-fetch.txt"):
        if path not in seen:
            print(f"  FAIL: {path} was never requested")
            ok = False

    print("\n=== pixel10: navigator agrees with the header ===")
    ok &= compare({"window ua": data["ua"], "window appVersion": data["appVersion"],
                   "worker ua": data["worker"]["ua"],
                   "worker appVersion": data["worker"]["appVersion"]},
                  {"window ua": UA, "window appVersion": APP_VERSION,
                   "worker ua": UA, "worker appVersion": APP_VERSION})

    print("\n=== pixel10: no Firefox-only navigator members ===")
    ok &= compare({"Firefox-only members": data["firefoxOnly"], "productSub": data["productSub"]},
                  {"Firefox-only members": [], "productSub": "20030107"})

    print("\n=== pixel10: ICE candidates leak no host address or name ===")
    hosts = [c for c in data["candidates"] if " typ host" in c]
    leaks = lan_addresses() | {socket.gethostname()}
    ok &= compare({
        "host candidates gathered": len(hosts),
        "host candidates are <uuid>.local": all(
            re.search(r" [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.local ", c)
            for c in hosts),
        "no LAN address or hostname in any candidate": not any(
            leak and leak in c for c in data["candidates"] for leak in leaks),
    }, {
        "host candidates gathered": lambda n: n >= 1,
        "host candidates are <uuid>.local": True,
        "no LAN address or hostname in any candidate": True,
    })
    for c in data["candidates"]:
        print(f"    [info] {c}")

    print("\n=== control (no profile): the browser's own Gecko UA ===")
    _, requests = await probe(binary, {})
    ua = requests[0][1].get("user-agent", "")
    # An unconfigured build names itself (".../Camoufox/<version>"); what
    # matters is that it is a Gecko UA, not the phone's Chrome one.
    ok &= compare({"user-agent is Gecko's": "Gecko/20100101" in ua and "Chrome/" not in ua},
                  {"user-agent is Gecko's": True})
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
