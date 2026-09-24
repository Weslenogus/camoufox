"""
Verify Android's fonts (patches/android/android-12-fonts.patch).

With {"device:profile": "pixel10"} text must render in Android's own fonts,
the files Android ships (bundled with the browser):

  * system-ui, sans-serif and unstyled text are Roboto;
  * serif is Noto Serif and monospace is Droid Sans Mono;
  * the CSS2 system-font keywords (font: menu, caption...) use Roboto;
  * -apple-system and BlinkMacSystemFont do not resolve (they are Apple's),
    nor do desktop families such as Arial -- they fall through to the next
    family in the list;
  * emoji come from Noto Color Emoji, in colour, and a flag sequence (FR)
    renders as one flag glyph rather than two letters.

Widths are compared with the same text in an explicitly named family, so the
check does not depend on the host's font rendering.

The control launch (no profile) keeps the host's generic families: system-ui
is not forced to Roboto there.

Run:
    python tests/patches/android-fonts.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""() => {
  const text = 'Sphinx of black quartz, judge my vow 0123456789';
  const ctx = document.createElement('canvas').getContext('2d');
  const width = family => { ctx.font = `20px ${family}`; return ctx.measureText(text).width; };
  const cssWidth = style => {
    const span = document.createElement('span');
    span.textContent = text;
    span.setAttribute('style', style + ';position:absolute;white-space:nowrap');
    document.body.appendChild(span);
    const w = span.getBoundingClientRect().width;
    span.remove();
    return w;
  };
  const same = (a, b) => Math.abs(a - b) < 0.01;
  const roboto = width('Roboto'), notoSerif = width('"Noto Serif"'),
        droidMono = width('"Droid Sans Mono"'), mono = width('monospace');

  // Emoji: colour and a single flag glyph.
  const e = document.createElement('canvas');
  e.width = 200; e.height = 60;
  const ec = e.getContext('2d');
  ec.font = '40px sans-serif';
  ec.textBaseline = 'top';
  ec.fillText('\u{1F1EB}\u{1F1F7}', 0, 0);
  const px = ec.getImageData(0, 0, 200, 60).data;
  let coloured = 0;
  for (let i = 0; i < px.length; i += 4)
    if (px[i + 3] > 0 && (Math.abs(px[i] - px[i + 1]) > 30 || Math.abs(px[i + 1] - px[i + 2]) > 30)) coloured++;
  const flagWidth = ec.measureText('\u{1F1EB}\u{1F1F7}').width;
  const faceWidth = ec.measureText('\u{1F600}').width;

  return {
    'system-ui is Roboto': same(width('system-ui'), roboto),
    'sans-serif is Roboto': same(width('sans-serif'), roboto),
    'unstyled text is Roboto': same(cssWidth(''), cssWidth('font-family:Roboto')),
    'serif is Noto Serif': same(width('serif'), notoSerif),
    'monospace is Droid Sans Mono': same(mono, droidMono),
    'font: menu is Roboto': same(cssWidth('font:menu;font-size:20px'), cssWidth('font:20px Roboto')),
    '-apple-system does not resolve': same(width('-apple-system, monospace'), mono),
    'BlinkMacSystemFont does not resolve': same(width('BlinkMacSystemFont, monospace'), mono),
    'Arial does not resolve': same(width('Arial, monospace'), mono),
    'emoji font is Noto Color Emoji': same(ec.measureText('\u{1F600}').width,
        (ec.font = '40px "Noto Color Emoji"', ec.measureText('\u{1F600}').width)),
    'flag emoji is in colour': coloured > 100,
    'flag is one glyph': Math.abs(flagWidth - faceWidth) < faceWidth * 0.35,
  };
}"""


async def probe(binary, config):
    with PageServer({"/": ("text/html", "<!doctype html><title>fonts</title><body>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE)


async def main(binary) -> bool:
    print("\n=== pixel10: Android's fonts ===")
    pixel = compare(await probe(binary, PIXEL10), {
        "system-ui is Roboto": True,
        "sans-serif is Roboto": True,
        "unstyled text is Roboto": True,
        "serif is Noto Serif": True,
        "monospace is Droid Sans Mono": True,
        "font: menu is Roboto": True,
        "-apple-system does not resolve": True,
        "BlinkMacSystemFont does not resolve": True,
        "Arial does not resolve": True,
        "emoji font is Noto Color Emoji": True,
        "flag emoji is in colour": True,
        "flag is one glyph": True,
    })
    print("\n=== control (no profile): the host's own generics ===")
    control = compare(await probe(binary, {}), {"system-ui is Roboto": False})
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
