"""
Verify the storage estimate (patches/android/android-27-storage.patch).

With {"device:profile": "pixel10"}, navigator.storage.estimate() -- in the
window and in a worker -- reports what Chrome reports on the phone:

  * quota 34359738368 (32 GiB);
  * usage around 24576000 bytes for a fresh origin: the configured baseline
    plus whatever the origin really stores, so writing data still moves it;
  * usageDetails, Chrome's per-storage-type breakdown, summing to usage.

The control launch keeps Firefox's own estimate (no usageDetails, the host's
quota).

Run:
    python tests/patches/android-storage.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

QUOTA = 34359738368
BASELINE = 24576000

WORKER_JS = """navigator.storage.estimate().then(e => postMessage(
  {quota: e.quota, usage: e.usage, usageDetails: e.usageDetails || null}));"""

PROBE = r"""async () => {
  const shape = e => ({quota: e.quota, usage: e.usage, usageDetails: e.usageDetails || null});
  const before = shape(await navigator.storage.estimate());
  const worker = await new Promise(r => { new Worker('/w.js').onmessage = e => r(e.data); });
  // Store ~1 MB in IndexedDB; usage must move with it.
  await new Promise((resolve, reject) => {
    const open = indexedDB.open('guard', 1);
    open.onupgradeneeded = () => open.result.createObjectStore('s');
    open.onsuccess = () => {
      const tx = open.result.transaction('s', 'readwrite');
      tx.objectStore('s').put(new Uint8Array(1 << 20).fill(7), 'blob');
      tx.oncomplete = () => { open.result.close(); resolve(); };
      tx.onerror = () => reject(tx.error);
    };
    open.onerror = () => reject(open.error);
  });
  const after = shape(await navigator.storage.estimate());
  return {before, worker, after};
}"""


def details_sum(estimate):
    details = estimate.get("usageDetails")
    return sum(details.values()) if isinstance(details, dict) else None


async def probe(binary, config):
    routes = {"/": ("text/html", "<!doctype html><title>storage</title>"),
              "/w.js": ("text/javascript", WORKER_JS)}
    with PageServer(routes) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE)


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    data = await probe(binary, PIXEL10)
    b, w, a = data["before"], data["worker"], data["after"]
    pixel = compare({
        "quota": b["quota"],
        "worker quota": w["quota"],
        "fresh usage near baseline": b["usage"],
        "worker usage matches window": w["usage"] == b["usage"],
        "usageDetails sums to usage": details_sum(b) == b["usage"],
        "usage grows with stored data": a["usage"] - b["usage"],
        "quota unchanged after write": a["quota"],
    }, {
        "quota": QUOTA,
        "worker quota": QUOTA,
        "fresh usage near baseline": lambda u: BASELINE <= u <= BASELINE + 256 * 1024,
        "worker usage matches window": True,
        "usageDetails sums to usage": True,
        "usage grows with stored data": lambda d: d >= 512 * 1024,
        "quota unchanged after write": QUOTA,
    })
    print("\n=== control (no profile): Firefox's own estimate ===")
    data = await probe(binary, {})
    control = compare({"quota is the profile's": data["before"]["quota"] == QUOTA,
                       "usageDetails": data["before"]["usageDetails"]},
                      {"quota is the profile's": False, "usageDetails": None})
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
