"""
Verify text is antialiased in grayscale only
(patches/android/android-25-grayscale-text.patch).

Android has no subpixel (LCD) text antialiasing, and its colour fringes are
readable from a canvas. With {"device:profile": "pixel10"}, black text on
white is drawn with every pixel grey (r == g == b):

  * on an opaque 2D canvas ({alpha: false}), where subpixel antialiasing is
    otherwise allowed;
  * in page text, read back from a screenshot.

The control launch is not asserted on (a headless host may have no subpixel
setting either); it only has to render the text.

Run:
    python tests/patches/android-text-aa.py [--binary /path/to/camoufox-bin]
"""

import io

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PAGE = """<!doctype html><title>aa</title>
<div id=t style="font:24px sans-serif;color:#000;background:#fff;padding:8px;
width:600px">The quick brown fox jumps over the lazy dog 0123456789</div>"""

PROBE = r"""() => {
  const c = document.createElement('canvas');
  c.width = 600; c.height = 60;
  const ctx = c.getContext('2d', {alpha: false});
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 600, 60);
  ctx.fillStyle = '#000'; ctx.font = '24px sans-serif';
  ctx.fillText('The quick brown fox jumps over the lazy dog', 4, 36);
  const d = ctx.getImageData(0, 0, 600, 60).data;
  let inked = 0, coloured = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i] < 250 || d[i + 1] < 250 || d[i + 2] < 250) inked++;
    if (d[i] !== d[i + 1] || d[i + 1] !== d[i + 2]) coloured++;
  }
  return {inked, coloured};
}"""


def screenshot_colour(png: bytes):
    try:
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(io.BytesIO(png)).convert("RGB")
    inked = coloured = 0
    for r, g, b in img.getdata():
        if min(r, g, b) < 250:
            inked += 1
        if not (r == g == b):
            coloured += 1
    return {"inked": inked, "coloured": coloured}


async def probe(binary, config):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            canvas = await page.evaluate(PROBE)
            shot = await page.locator("#t").screenshot()
            return canvas, screenshot_colour(shot)


async def main(binary) -> bool:
    print("\n=== pixel10: grayscale text ===")
    canvas, dom = await probe(binary, PIXEL10)
    ok = compare({"canvas text drawn": canvas["inked"] > 200,
                  "canvas coloured pixels": canvas["coloured"]},
                 {"canvas text drawn": True, "canvas coloured pixels": 0})
    if dom is None:
        print("    [info] Pillow not installed; page-text check skipped")
    else:
        ok &= compare({"page text drawn": dom["inked"] > 200,
                       "page coloured pixels": dom["coloured"]},
                      {"page text drawn": True, "page coloured pixels": 0})
    print("\n=== control (no profile): renders ===")
    canvas, _ = await probe(binary, {})
    control = compare({"canvas text drawn": canvas["inked"] > 200}, {"canvas text drawn": True})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
