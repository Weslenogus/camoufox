"""
Verify performance.memory and timer resolution
(patches/android/android-22-performance.patch).

With {"device:profile": "pixel10"}:

  * performance.memory exists, as in Chrome: jsHeapSizeLimit 2147483648,
    usedJSHeapSize <= totalJSHeapSize < jsHeapSizeLimit, both one of
    Chrome's quantization buckets (at least 10000000, three significant
    digits), and no MemoryInfo interface object on window;
  * performance.now() has 1 ms resolution in the window and in a worker;
  * performance.timeOrigin exists in the worker, at or after the window's.

The control launch keeps Firefox's shape: no performance.memory.

Run:
    python tests/patches/android-performance.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

SAMPLE = """(() => { const out = []; const end = performance.now() + 60;
  while (performance.now() < end) out.push(performance.now()); return out; })()"""

WORKER_JS = f"postMessage({{now: {SAMPLE}, timeOrigin: performance.timeOrigin}});"

PROBE = r"""async (sample) => {
  const m = performance.memory;
  const worker = await new Promise(r => { new Worker('/w.js').onmessage = e => r(e.data); });
  return {
    memory: m ? {limit: m.jsHeapSizeLimit, total: m.totalJSHeapSize, used: m.usedJSHeapSize,
                 tag: Object.prototype.toString.call(m)} : null,
    MemoryInfo: 'MemoryInfo' in window,
    now: eval(sample),
    workerNow: worker.now,
    timeOrigin: performance.timeOrigin,
    workerTimeOrigin: worker.timeOrigin,
  };
}"""


def bucket(v):
    if not isinstance(v, int) or v < 10000000:
        return False
    digits = str(v).rstrip("0")
    return len(digits) <= 3


def whole_ms(values):
    return len(values) > 10 and all(abs(v - round(v)) < 1e-9 for v in values)


async def probe(binary, config):
    routes = {"/": ("text/html", "<!doctype html><title>perf</title>"),
              "/w.js": ("text/javascript", WORKER_JS)}
    with PageServer(routes) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE, SAMPLE)


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    d = await probe(binary, PIXEL10)
    m = d["memory"] or {}
    ok = compare({
        "jsHeapSizeLimit": m.get("limit"),
        "used <= total < limit": bool(m) and m["used"] <= m["total"] < m["limit"],
        "used is a Chrome bucket": bucket(m.get("used")),
        "total is a Chrome bucket": bucket(m.get("total")),
        "toString tag": m.get("tag"),
        "MemoryInfo interface object": d["MemoryInfo"],
        "window now() at 1 ms": whole_ms(d["now"]),
        "worker now() at 1 ms": whole_ms(d["workerNow"]),
        "worker timeOrigin": isinstance(d["workerTimeOrigin"], (int, float)) and
                             d["workerTimeOrigin"] >= d["timeOrigin"],
    }, {
        "jsHeapSizeLimit": 2147483648,
        "used <= total < limit": True,
        "used is a Chrome bucket": True,
        "total is a Chrome bucket": True,
        "toString tag": "[object MemoryInfo]",
        "MemoryInfo interface object": False,
        "window now() at 1 ms": True,
        "worker now() at 1 ms": True,
        "worker timeOrigin": True,
    })
    print("\n=== control (no profile): no performance.memory ===")
    d = await probe(binary, {})
    control = compare({"performance.memory": d["memory"]}, {"performance.memory": None})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
