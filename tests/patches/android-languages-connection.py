"""
Verify languages and network information in every realm
(patches/android/android-20-languages-connection.patch).

With {"device:profile": "pixel10"}, identically in the window, an iframe and
dedicated, shared and service workers:

  * navigator.language "fr-FR" and navigator.languages
    ["fr-FR", "fr", "en-US", "en"];
  * navigator.connection, Chrome's NetworkInformation on a phone on wifi:
    type "wifi", effectiveType "4g", downlink 10, rtt 50, saveData false,
    downlinkMax Infinity, with onchange and ontypechange handlers.

The control launch (no profile) keeps Firefox desktop's shape: no
navigator.connection at all.

Run:
    python tests/patches/android-languages-connection.py [--binary /path/to/camoufox-bin]
"""

import asyncio
import json
from typing import Any, Dict

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

COLLECT = r"""
function collect(scope) {
  const n = scope.navigator, c = n.connection;
  return {
    language: n.language,
    languages: Array.from(n.languages),
    connection: c ? {
      type: c.type, effectiveType: c.effectiveType, downlink: c.downlink,
      rtt: c.rtt, saveData: c.saveData, downlinkMaxInfinite: c.downlinkMax === Infinity,
      onchange: 'onchange' in c, ontypechange: 'ontypechange' in c,
      isEventTarget: c instanceof scope.EventTarget,
    } : 'absent',
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
  out.iframe = await new Promise(resolve => {
    const f = document.createElement('iframe');
    addEventListener('message', function h(e) {
      if (e.source === f.contentWindow) { removeEventListener('message', h); resolve(e.data.frame); }
    });
    f.src = '/frame.html';
    document.body.appendChild(f);
  });
  out.worker = await new Promise(r => { new Worker('/worker.js').onmessage = e => r(e.data); });
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

REALMS = ("window", "iframe", "worker", "shared worker", "service worker")

PHONE_CONNECTION = {
    "type": "wifi", "effectiveType": "4g", "downlink": 10, "rtt": 50, "saveData": False,
    "downlinkMaxInfinite": True, "onchange": True, "ontypechange": True, "isEventTarget": True,
}


async def probe(binary, config) -> Dict[str, Any]:
    routes = {
        "/": ("text/html", INDEX_HTML),
        "/frame.html": ("text/html", FRAME_HTML),
        "/worker.js": ("text/javascript", WORKER_JS),
        "/shared.js": ("text/javascript", SHARED_JS),
        "/sw.js": ("text/javascript", SW_JS),
    }
    with PageServer(routes) as server:
        # allowMainWorld only unlocks the guard's own "mw:" read of the result.
        async with launch_raw(binary, dict(config, allowMainWorld=True)) as page:
            await page.goto(server.url("/"))
            realms = await asyncio.wait_for(page.evaluate("mw:window.realms"), 30)
    flat = {}
    for realm in REALMS:
        values = realms.get(realm)
        if not isinstance(values, dict):
            flat[f"{realm}"] = values
            continue
        for key, value in values.items():
            flat[f"{realm}: {key}"] = value
    return flat


async def main(binary) -> bool:
    print("\n=== pixel10: every realm ===")
    expected = {}
    for realm in REALMS:
        expected[f"{realm}: language"] = "fr-FR"
        expected[f"{realm}: languages"] = ["fr-FR", "fr", "en-US", "en"]
        expected[f"{realm}: connection"] = PHONE_CONNECTION
    pixel = compare(await probe(binary, PIXEL10), expected)
    print("\n=== control (no profile): no navigator.connection ===")
    flat = await probe(binary, {})
    control = compare({k: v for k, v in flat.items() if k.endswith(": connection")},
                      {f"{r}: connection": "absent" for r in REALMS})
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
