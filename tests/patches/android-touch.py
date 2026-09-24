"""
Verify fingertip touch input (patches/android/android-08-touch.patch).

With {"device:profile": "pixel10"}:

  * a synthesized tap carries a fingertip's contact geometry: radiusX in
    [18, 31], radiusY within 3 of radiusX, rotationAngle in [0, 27], force in
    [0.38, 0.80] -- stable for the whole gesture, fresh for each new tap;
  * its pointer events report the contact's extent: width == 2 * radiusX,
    height == 2 * radiusY, pointerType "touch";
  * synthesized *mouse* input (page.mouse / page.click) reaches the page as a
    finger too: pointerType "touch", width/height of a fingertip, pressure of
    a finger while pressed -- and the click still lands;
  * the input shape of a phone: (pointer: coarse), (hover: none), the same for
    any-pointer / any-hover, and the legacy touch APIs Android has
    ('ontouchstart' in window, document.createTouch).

The control launch keeps Firefox's shape: 1px automation touches, mouse
pointers, a fine hovering primary pointer.

Run:
    python tests/patches/android-touch.py [--binary /path/to/camoufox-bin]
"""

from typing import Any, Dict

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PAGE = """<!doctype html><title>touch</title>
<button id=b style="position:absolute;left:50px;top:50px;width:200px;height:120px">tap</button>
<script>
  window.log = [];
  const rec = e => {
    const t = e.changedTouches && e.changedTouches[0];
    log.push({type: e.type, trusted: e.isTrusted,
      pointerType: e.pointerType, width: e.width, height: e.height, pressure: e.pressure,
      radiusX: t && t.radiusX, radiusY: t && t.radiusY,
      rotationAngle: t && t.rotationAngle, force: t && t.force});
  };
  for (const type of ['touchstart', 'touchend', 'pointerdown', 'pointerup', 'click'])
    b.addEventListener(type, rec);
</script>"""

SHAPE = r"""() => {
  const mq = q => matchMedia(q).matches;
  let createTouch = false;
  try { createTouch = typeof document.createTouch === 'function'; } catch (e) {}
  return {
    "(pointer: coarse)": mq('(pointer: coarse)'), "(pointer: fine)": mq('(pointer: fine)'),
    "(hover: none)": mq('(hover: none)'), "(any-pointer: fine)": mq('(any-pointer: fine)'),
    "(any-hover: hover)": mq('(any-hover: hover)'),
    "'ontouchstart' in window": 'ontouchstart' in window,
    "document.createTouch": createTouch,
    "window.TouchEvent": 'TouchEvent' in window,
  };
}"""


def by_type(log, type_):
    return [e for e in log if e["type"] == type_]


def check_tap(log) -> Dict[str, Any]:
    ts, te = by_type(log, "touchstart"), by_type(log, "touchend")
    pd = by_type(log, "pointerdown")
    if not ts or not te or not pd:
        return {"events": [e["type"] for e in log]}
    s, e, p = ts[0], te[0], pd[0]
    return {
        "radiusX in [18,31]": 18 <= s["radiusX"] <= 31,
        "|radiusY - radiusX| <= 3": abs(s["radiusY"] - s["radiusX"]) <= 3,
        "rotationAngle in [0,27]": 0 <= s["rotationAngle"] <= 27,
        "force in [0.38,0.80]": 0.38 <= s["force"] <= 0.80 + 1e-6,
        "same finger at touchend": (e["radiusX"], e["rotationAngle"]) ==
                                   (s["radiusX"], s["rotationAngle"]) or
                                   abs(e["radiusX"] - s["radiusX"]) <= 1,
        "pointerdown.pointerType": p["pointerType"],
        "pointerdown.width == 2*radiusX": p["width"] == 2 * s["radiusX"],
        "pointerdown.height == 2*radiusY": p["height"] == 2 * s["radiusY"],
        "touch events trusted": s["trusted"] and e["trusted"],
    }


async def probe(binary, config):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        async with launch_raw(binary, config, has_touch=True) as page:
            await page.goto(server.url("/"))
            shape = await page.evaluate(SHAPE)
            await page.touchscreen.tap(150, 110)
            tap1 = await page.evaluate("log.splice(0)")
            await page.touchscreen.tap(150, 110)
            tap2 = await page.evaluate("log.splice(0)")
            await page.mouse.click(150, 110)
            mouse = await page.evaluate("log.splice(0)")
            return shape, tap1, tap2, mouse


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    shape, tap1, tap2, mouse = await probe(binary, PIXEL10)
    ok = compare(shape, {
        "(pointer: coarse)": True, "(pointer: fine)": False, "(hover: none)": True,
        "(any-pointer: fine)": False, "(any-hover: hover)": False,
        "'ontouchstart' in window": True, "document.createTouch": True,
        "window.TouchEvent": True,
    })
    print("  tap:")
    ok &= compare(check_tap(tap1), {
        "radiusX in [18,31]": True, "|radiusY - radiusX| <= 3": True,
        "rotationAngle in [0,27]": True, "force in [0.38,0.80]": True,
        "same finger at touchend": True, "pointerdown.pointerType": "touch",
        "pointerdown.width == 2*radiusX": True, "pointerdown.height == 2*radiusY": True,
        "touch events trusted": True,
    })
    a = (by_type(tap1, "touchstart") or [{}])[0]
    b = (by_type(tap2, "touchstart") or [{}])[0]
    ok &= compare({"second tap is a new finger": (a.get("radiusX"), a.get("force")) !=
                   (b.get("radiusX"), b.get("force"))},
                  {"second tap is a new finger": True})
    print("  mouse click:")
    down = (by_type(mouse, "pointerdown") or [{}])[0]
    ok &= compare({
        "pointerdown.pointerType": down.get("pointerType"),
        "pointerdown.width": down.get("width"),
        "pointerdown.pressure": down.get("pressure"),
        "click landed": bool(by_type(mouse, "click")),
        "click.pointerType": (by_type(mouse, "click") or [{}])[0].get("pointerType"),
    }, {
        "pointerdown.pointerType": "touch",
        "pointerdown.width": lambda w: w is not None and 36 <= w <= 62,
        "pointerdown.pressure": lambda p: p is not None and 0.38 <= p <= 0.81,
        "click landed": True,
        "click.pointerType": "touch",
    })

    print("\n=== control (no profile): Firefox's automation shape ===")
    shape, tap1, _, mouse = await probe(binary, {})
    s = (by_type(tap1, "touchstart") or [{}])[0]
    down = (by_type(mouse, "pointerdown") or [{}])[0]
    control = compare({
        "(pointer: fine)": shape["(pointer: fine)"],
        "tap radiusX": s.get("radiusX"),
        "mouse pointerType": down.get("pointerType"),
    }, {"(pointer: fine)": True, "tap radiusX": 1, "mouse pointerType": "mouse"})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
