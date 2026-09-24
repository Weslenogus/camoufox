"""
Verify the Pixel 10 screen (patches/android/android-11-screen.patch).

With {"device:profile": "pixel10"}:

    screen.width / height            412 x 915
    screen.availWidth / availHeight  412 x 873
    screen.colorDepth / pixelDepth   24 / 24
    devicePixelRatio                 2.625, and (resolution: 2.625dppx) agrees
    innerWidth / innerHeight         412 x 873 -- the real layout viewport, so
                                     documentElement.clientWidth agrees too
    outerWidth / outerHeight         412 x 915
    screen.orientation               portrait-primary, angle 0
    window.orientation               0
    env(safe-area-inset-*)           top 24px, bottom 24px, left/right 0
    (orientation: portrait), (device-width: 412px)

The control launch keeps the desktop's landscape orientation and zero insets.

Run:
    python tests/patches/android-screen.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PAGE = """<!doctype html><title>screen</title>
<style>
  #probe { position: fixed; padding-top: env(safe-area-inset-top, 99px);
           padding-bottom: env(safe-area-inset-bottom, 99px);
           padding-left: env(safe-area-inset-left, 99px);
           padding-right: env(safe-area-inset-right, 99px); }
</style><div id=probe></div>"""

PROBE = r"""() => {
  const cs = getComputedStyle(document.getElementById('probe'));
  const mq = q => matchMedia(q).matches;
  return {
    "screen.width": screen.width, "screen.height": screen.height,
    "screen.availWidth": screen.availWidth, "screen.availHeight": screen.availHeight,
    "screen.colorDepth": screen.colorDepth, "screen.pixelDepth": screen.pixelDepth,
    "devicePixelRatio": devicePixelRatio,
    "(resolution: 2.625dppx)": mq('(resolution: 2.625dppx)'),
    "(-webkit-device-pixel-ratio: 2.625)": mq('(-webkit-device-pixel-ratio: 2.625)'),
    "innerWidth": innerWidth, "innerHeight": innerHeight,
    "documentElement.clientWidth": document.documentElement.clientWidth,
    "outerWidth": outerWidth, "outerHeight": outerHeight,
    "screen.orientation.type": screen.orientation.type,
    "screen.orientation.angle": screen.orientation.angle,
    "window.orientation": 'orientation' in window ? window.orientation : 'absent',
    "safe-area-inset-top": cs.paddingTop, "safe-area-inset-bottom": cs.paddingBottom,
    "safe-area-inset-left": cs.paddingLeft, "safe-area-inset-right": cs.paddingRight,
    "(orientation: portrait)": mq('(orientation: portrait)'),
    "(device-width: 412px)": mq('(device-width: 412px)'),
  };
}"""

PIXEL_EXPECTED = {
    "screen.width": 412, "screen.height": 915,
    "screen.availWidth": 412, "screen.availHeight": 873,
    "screen.colorDepth": 24, "screen.pixelDepth": 24,
    "devicePixelRatio": 2.625,
    "(resolution: 2.625dppx)": True,
    "(-webkit-device-pixel-ratio: 2.625)": True,
    "innerWidth": 412, "innerHeight": 873,
    "documentElement.clientWidth": 412,
    "outerWidth": 412, "outerHeight": 915,
    "screen.orientation.type": "portrait-primary",
    "screen.orientation.angle": 0,
    "window.orientation": 0,
    "safe-area-inset-top": "24px", "safe-area-inset-bottom": "24px",
    "safe-area-inset-left": "0px", "safe-area-inset-right": "0px",
    "(orientation: portrait)": True,
    "(device-width: 412px)": True,
}


async def probe(binary, config):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        # Spoofed window dimensions imply no_viewport (tribal rule
        # no-viewport-when-window-is-spoofed): the chrome sizes the viewport.
        async with launch_raw(binary, config, no_viewport=True) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE)


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    pixel = compare(await probe(binary, PIXEL10), PIXEL_EXPECTED)
    print("\n=== control (no profile): desktop orientation, no insets ===")
    control = compare(await probe(binary, {}), {
        "safe-area-inset-top": "0px", "safe-area-inset-bottom": "0px",
        "window.orientation": "absent",
        "screen.orientation.type": "landscape-primary",
    })
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
