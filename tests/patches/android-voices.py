"""
Verify the speech synthesis voices (patches/android/android-24-voices.patch).

With {"device:profile": "pixel10"}, speechSynthesis.getVoices() -- in the
window and in an iframe -- lists exactly Google's network voices, in order:

    name                       lang   localService  default
    Google français            fr-FR  false         false
    Google US English          en-US  false         true
    Google UK English Female   en-GB  false         false
    Google español             es-ES  false         false

with voiceURI equal to the name, and never a host voice: no Microsoft, Apple,
SAPI5, eSpeak or speech-dispatcher entry. speak() still completes (onend
fires) so pages that wait for it do not hang.

The control launch keeps the host's voices (whatever they are), so it only
checks that the Google list is not forced on it.

Run:
    python tests/patches/android-voices.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""async () => {
  const voices = await new Promise(resolve => {
    let v = speechSynthesis.getVoices();
    if (v.length) return resolve(v);
    speechSynthesis.onvoiceschanged = () => resolve(speechSynthesis.getVoices());
    setTimeout(() => resolve(speechSynthesis.getVoices()), 3000);
  });
  const frame = await new Promise(resolve => {
    const f = document.createElement('iframe');
    f.onload = () => resolve(f.contentWindow.speechSynthesis.getVoices().map(v => v.name));
    document.body.appendChild(f);
  });
  const spoken = await new Promise(resolve => {
    const u = new SpeechSynthesisUtterance('bonjour');
    u.onend = () => resolve('end');
    u.onerror = e => resolve('error: ' + e.error);
    speechSynthesis.speak(u);
    setTimeout(() => resolve('timeout'), 5000);
  });
  return {
    voices: voices.map(v => [v.name, v.lang, v.localService, v.default, v.voiceURI === v.name]),
    frame, spoken,
  };
}"""

GOOGLE = [
    ["Google français", "fr-FR", False, False, True],
    ["Google US English", "en-US", False, True, True],
    ["Google UK English Female", "en-GB", False, False, True],
    ["Google español", "es-ES", False, False, True],
]
HOST_MARKERS = ("microsoft", "apple", "sapi", "espeak", "speech-dispatcher", "speechd")


async def probe(binary, config):
    with PageServer({"/": ("text/html", "<!doctype html><title>voices</title><body>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE)


async def main(binary) -> bool:
    print("\n=== pixel10: Google's voices only ===")
    data = await probe(binary, PIXEL10)
    names = [v[0] for v in data["voices"]]
    pixel = compare({
        "voices": data["voices"],
        "iframe voices": data["frame"],
        "no host voice": not any(m in n.lower() for n in names for m in HOST_MARKERS),
        "speak() completes": data["spoken"],
    }, {
        "voices": GOOGLE,
        "iframe voices": [v[0] for v in GOOGLE],
        "no host voice": True,
        "speak() completes": "end",
    })
    print("\n=== control (no profile): not forced ===")
    data = await probe(binary, {})
    control = compare({"Google list forced": data["voices"] == GOOGLE},
                      {"Google list forced": False})
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
