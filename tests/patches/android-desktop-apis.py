"""
Verify desktop-only APIs are absent on the Android profile
(patches/android/android-03-desktop-apis.patch).

Chrome on Android ships none of these, so their presence alone says "desktop":

    window.EyeDropper                  navigator.hid
    window.getScreenDetails            window.documentPictureInPicture
    window.queryLocalFonts             navigator.windowControlsOverlay
    window.showOpenFilePicker          window.showSaveFilePicker
    window.showDirectoryPicker         navigator.keyboard

Firefox itself only implements one of them -- Document Picture-in-Picture --
which the profile switches off through a pref. The rest must simply stay
absent, and this guard pins that a Firefox update does not quietly add one.

SharedWorker, long desktop-only, must stay: Chrome ships it on Android since
M148 (blink-dev "Intent to Ship: SharedWorker on Android").

The control launch shows what the profile is switching off: on desktop
Document Picture-in-Picture is there.

Run:
    python tests/patches/android-desktop-apis.py [--binary /path/to/camoufox-bin]
"""

from typing import Any, Dict

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE_JS = r"""() => ({
  "EyeDropper": "EyeDropper" in window,
  "navigator.hid": "hid" in navigator,
  "getScreenDetails": "getScreenDetails" in window,
  "documentPictureInPicture": "documentPictureInPicture" in window,
  "DocumentPictureInPicture": "DocumentPictureInPicture" in window,
  "queryLocalFonts": "queryLocalFonts" in window,
  "windowControlsOverlay": "windowControlsOverlay" in navigator,
  "showOpenFilePicker": "showOpenFilePicker" in window,
  "showSaveFilePicker": "showSaveFilePicker" in window,
  "showDirectoryPicker": "showDirectoryPicker" in window,
  "navigator.keyboard": "keyboard" in navigator,
  "SharedWorker": "SharedWorker" in window,
})"""

ABSENT: Dict[str, Any] = {
    "EyeDropper": False,
    "navigator.hid": False,
    "getScreenDetails": False,
    "documentPictureInPicture": False,
    "DocumentPictureInPicture": False,
    "queryLocalFonts": False,
    "windowControlsOverlay": False,
    "showOpenFilePicker": False,
    "showSaveFilePicker": False,
    "showDirectoryPicker": False,
    "navigator.keyboard": False,
    "SharedWorker": True,
}

DESKTOP = dict(ABSENT, documentPictureInPicture=True, DocumentPictureInPicture=True)


async def probe(binary, config):
    # A secure context: documentPictureInPicture is [SecureContext].
    with PageServer({"/": ("text/html", "<!doctype html><title>apis</title>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE_JS)


async def main(binary) -> bool:
    print("\n=== pixel10: desktop-only APIs are absent ===")
    pixel = compare(await probe(binary, PIXEL10), ABSENT)
    print("\n=== control (no profile): Firefox desktop's own set ===")
    control = compare(await probe(binary, {}), DESKTOP)
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
