"""
Verify automation's mouse input fires a finger's trusted touch events
(patches/android/android-18-touch-trusted.patch).

On a phone a tap fires touch events as well as pointer events, and pages
listen for either. With {"device:profile": "pixel10"}, page.mouse.click()
reaches the page as a finger (android-touch.py) and now also fires
touchstart and touchend:

  * isTrusted true, like everything the browser itself dispatches;
  * each right after the finger's pointer event: pointerdown, touchstart ...
    pointerup, touchend, then the compatibility mouse events and the click;
  * one pointer only -- no duplicate pointerdown;
  * the touch's contact geometry is the pointer event's (radiusX == width/2),
    and touchend's touches list is empty, its changedTouches holding the
    finger;
  * a drag (mouse down, move, up) fires touchmove in between.

The control launch keeps Firefox's behaviour: a mouse click fires no touch
events at all.

Run:
    python tests/patches/android-touch-trusted.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PAGE = """<!doctype html><title>touch trusted</title>
<div id=b style="position:absolute;left:40px;top:40px;width:240px;height:200px;background:#ccc"></div>
<script>
  window.log = [];
  for (const type of ['pointerdown', 'pointermove', 'pointerup', 'touchstart', 'touchmove',
                      'touchend', 'mousedown', 'mouseup', 'click'])
    b.addEventListener(type, e => {
      const t = e.changedTouches && e.changedTouches[0];
      log.push({type: e.type, trusted: e.isTrusted, width: e.width,
                radiusX: t ? t.radiusX : null, touches: e.touches ? e.touches.length : null,
                changed: e.changedTouches ? e.changedTouches.length : null});
    });
</script>"""


async def probe(binary, config):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            await page.mouse.click(150, 120)
            click = await page.evaluate("mw:log.splice(0)")
            await page.mouse.move(100, 100)
            await page.mouse.down()
            await page.mouse.move(160, 140, steps=4)
            await page.mouse.up()
            drag = await page.evaluate("mw:log.splice(0)")
            return click, drag


def main_types(log):
    return [e["type"] for e in log if e["type"] != "pointermove"]


async def main(binary) -> bool:
    print("\n=== pixel10: a mouse click is a finger's tap ===")
    click, drag = await probe(binary, dict(PIXEL10, allowMainWorld=True))
    by = {}
    for e in click:
        by.setdefault(e["type"], e)
    ts, te, pd = by.get("touchstart", {}), by.get("touchend", {}), by.get("pointerdown", {})
    ok = compare({
        "event order": main_types(click),
        "touch events trusted": bool(ts.get("trusted")) and bool(te.get("trusted")),
        "one pointerdown": sum(e["type"] == "pointerdown" for e in click),
        "radiusX == pointer width / 2": ts.get("radiusX") is not None and
                                        pd.get("width") == 2 * ts["radiusX"],
        "touchend touches / changedTouches": (te.get("touches"), te.get("changed")),
        "drag fires touchmove": any(e["type"] == "touchmove" and e["trusted"] for e in drag),
    }, {
        "event order": ["pointerdown", "touchstart", "mousedown", "pointerup", "touchend",
                        "mouseup", "click"],
        "touch events trusted": True,
        "one pointerdown": 1,
        "radiusX == pointer width / 2": True,
        "touchend touches / changedTouches": (0, 1),
        "drag fires touchmove": True,
    })
    print("\n=== control (no profile): no touch events from the mouse ===")
    click, _ = await probe(binary, {"allowMainWorld": True})
    control = compare({"touch events": [e["type"] for e in click if e["type"].startswith("touch")]},
                      {"touch events": []})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
