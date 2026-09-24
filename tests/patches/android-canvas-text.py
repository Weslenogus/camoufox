"""
Verify canvas text metrics (patches/android/android-23-canvas-text.patch).

With {"device:profile": "pixel10"} canvas text measures as it does on the
phone: in Roboto (the default "10px sans-serif" included), unhinted and at
fractional advances. So:

  * measureText() in sans-serif equals measureText() in Roboto, at the
    default font and at 20px;
  * widths are linear in the font size -- width at 200px is ten times the
    width at 20px, to within Gecko's 1/60 px storage of each glyph advance
    (half a unit per glyph) -- which hinted advances, snapped to whole
    pixels at each size, are not by several pixels;
  * widths are fractional, not rounded to whole pixels;
  * the same measurement repeated, or taken in a worker's OffscreenCanvas,
    is identical (no noise).

The control launch keeps the host's own sans-serif.

Run:
    python tests/patches/android-canvas-text.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

TEXT = "Cwm fjord bank glyphs vext quiz 0123456789"

WORKER_JS = """const c = new OffscreenCanvas(10, 10).getContext('2d');
c.font = '20px sans-serif';
postMessage(c.measureText(%r).width);""" % TEXT

PROBE = r"""async (text) => {
  const ctx = document.createElement('canvas').getContext('2d');
  const w = f => { ctx.font = f; return ctx.measureText(text).width; };
  const defaultFont = ctx.font;
  ctx.font = defaultFont;
  const def = ctx.measureText(text).width;
  const worker = await new Promise(r => { new Worker('/w.js').onmessage = e => r(e.data); });
  return {
    defaultFont,
    defaultWidth: def,
    defaultRoboto: w('10px Roboto'),
    sans20: w('20px sans-serif'),
    roboto20: w('20px Roboto'),
    sans200: w('200px sans-serif'),
    again20: w('20px sans-serif'),
    worker20: worker,
  };
}"""


async def probe(binary, config):
    routes = {"/": ("text/html", "<!doctype html><title>canvas text</title>"),
              "/w.js": ("text/javascript", WORKER_JS)}
    with PageServer(routes) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE, TEXT)


async def main(binary) -> bool:
    print("\n=== pixel10: Roboto, unhinted, fractional ===")
    d = await probe(binary, PIXEL10)
    ok = compare({
        "default font": d["defaultFont"],
        "default text is Roboto": abs(d["defaultWidth"] - d["defaultRoboto"]) < 1e-6,
        "20px sans-serif is Roboto": abs(d["sans20"] - d["roboto20"]) < 1e-6,
        "width linear in size": abs(d["sans200"] - 10 * d["sans20"]) <= len(TEXT) / 120,
        "fractional width": abs(d["sans20"] - round(d["sans20"])) > 1e-3,
        "repeatable": d["again20"] == d["sans20"],
        "worker agrees": abs(d["worker20"] - d["sans20"]) < 1e-6,
    }, {
        "default font": "10px sans-serif",
        "default text is Roboto": True,
        "20px sans-serif is Roboto": True,
        "width linear in size": True,
        "fractional width": True,
        "repeatable": True,
        "worker agrees": True,
    })
    print(f"    [info] 20px width {d['sans20']:.4f}, 200px width {d['sans200']:.4f}")
    print("\n=== control (no profile): the host's sans-serif ===")
    d = await probe(binary, {})
    control = compare({"20px sans-serif is Roboto": abs(d["sans20"] - d["roboto20"]) < 1e-6},
                      {"20px sans-serif is Roboto": False})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
