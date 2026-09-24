# Android system fonts

Bundled for the Android device profiles (`{"device:profile": "pixel10"}`):
the fonts Android itself uses for the CSS generic families, so text measures
and renders the way it does on the phone. `browser/fonts/moz.build` installs
them into the browser's `fonts/` directory, next to the bundled Twemoji, and
the profile's font allowlist keeps them out of every other fingerprint.

| File | Family | Android role | Source | License |
|---|---|---|---|---|
| `Roboto-Regular.ttf` | Roboto (variable: `wght`, `wdth`, `ital`) | `sans-serif`, `system-ui` | AOSP `platform/external/roboto-fonts` | Apache 2.0 (`LICENSE-Apache-2.0.txt`) |
| `NotoSerif-{Regular,Bold,Italic,BoldItalic}.ttf` | Noto Serif | `serif` | AOSP `platform/external/noto-fonts/notoserif` | SIL OFL 1.1 (`LICENSE-OFL.txt`) |
| `DroidSansMono.ttf` | Droid Sans Mono | `monospace` | AOSP `platform/frameworks/base/data/fonts` | Apache 2.0 (`LICENSE-Apache-2.0.txt`) |
| `NotoColorEmoji.ttf` | Noto Color Emoji 2.057 (COLRv1) | emoji | Google Fonts (`googlefonts/noto-emoji`), SVG table removed | SIL OFL 1.1 (`LICENSE-OFL.txt`) |

The emoji font's SVG glyph table was dropped (fontTools), leaving the COLRv1
glyphs Chrome renders; with both present Gecko would draw the SVG ones.
