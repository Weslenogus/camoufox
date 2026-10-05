"""
Verify Android-style permission states (patches/android/android-14-permissions.patch).

Chrome on a fresh phone answers "prompt" for anything the user has not granted.
With {"device:profile": "pixel10"} every permission Firefox knows must query as
"prompt", in the window and in a worker -- except screen-wake-lock, which
Chrome grants without asking (WakeLockPermissionContext allows screen wake
locks), so it reads "granted" -- while:

  * a real grant -- Playwright's context.grantPermissions() -- still reads
    "granted";
  * Permissions.prototype.query stays the engine's own native function (no JS
    wrapper, same function identity across calls).

Run:
    python tests/patches/android-permissions.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

NAMES = ["geolocation", "notifications", "push", "persistent-storage", "midi",
         "camera", "microphone", "screen-wake-lock", "storage-access"]

PROBE = r"""async (names) => {
  const query = async (perms, name) => {
    try { return (await perms.query({name})).state; } catch (e) { return 'error: ' + e.name; }
  };
  const window_ = {};
  for (const n of names) window_[n] = await query(navigator.permissions, n);
  const worker = await new Promise(resolve => {
    const src = `onmessage = async e => { const out = {};
      for (const n of e.data) { try { out[n] = (await navigator.permissions.query({name: n})).state; }
                                catch (err) { out[n] = 'error: ' + err.name; } }
      postMessage(out); };`;
    const w = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    w.onmessage = e => resolve(e.data);
    w.postMessage(['geolocation', 'notifications']);
  });
  const q = Permissions.prototype.query;
  return {
    window: window_, worker,
    native: Function.prototype.toString.call(q).includes('[native code]'),
    identity: q === navigator.permissions.query && q === Permissions.prototype.query,
    ownProperty: Object.prototype.hasOwnProperty.call(navigator.permissions, 'query'),
  };
}"""


async def probe(binary, config, grant=None):
    with PageServer({"/": ("text/html", "<!doctype html><title>perms</title>")}) as server:
        async with launch_raw(binary, config) as page:
            if grant:
                await page.context.grant_permissions(grant, origin=server.url("/").rstrip("/"))
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE, NAMES)


async def main(binary) -> bool:
    print("\n=== pixel10: everything but screen-wake-lock defaults to prompt ===")
    data = await probe(binary, PIXEL10)
    ok = compare(data["window"], dict({n: "prompt" for n in NAMES},
                                      **{"screen-wake-lock": "granted"}))
    ok &= compare(data["worker"], {"geolocation": "prompt", "notifications": "prompt"})
    ok &= compare({k: data[k] for k in ("native", "identity", "ownProperty")},
                  {"native": True, "identity": True, "ownProperty": False})

    print("\n=== pixel10: a real grant still reads granted ===")
    data = await probe(binary, PIXEL10, grant=["geolocation"])
    ok &= compare({"geolocation": data["window"]["geolocation"],
                   "notifications": data["window"]["notifications"]},
                  {"geolocation": "granted", "notifications": "prompt"})

    print("\n=== control (no profile): Firefox's answers (informational) ===")
    control = await probe(binary, {})
    for name, state in control["window"].items():
        print(f"    [info] {name}: {state}")
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
