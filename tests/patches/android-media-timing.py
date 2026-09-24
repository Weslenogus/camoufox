"""
Verify requestVideoFrameCallback and AudioContext timing
(patches/android/android-28-media-timing.patch).

With {"device:profile": "pixel10"}:

  * HTMLVideoElement.prototype.requestVideoFrameCallback and
    cancelVideoFrameCallback exist and are native functions
    ("[native code]");
  * new AudioContext() runs at 48000 Hz with baseLatency 0.005333 and
    outputLatency 0.021333, as Chrome on the phone reports them;
  * an OfflineAudioContext keeps the sample rate it was given.

The control launch keeps Gecko's baseLatency of 0.

Run:
    python tests/patches/android-media-timing.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""async () => {
  const proto = HTMLVideoElement.prototype;
  const ctx = new AudioContext();
  const out = {
    rvfc: typeof proto.requestVideoFrameCallback === 'function' &&
          /\[native code\]/.test(Function.prototype.toString.call(proto.requestVideoFrameCallback)),
    cancel: typeof proto.cancelVideoFrameCallback === 'function',
    sampleRate: ctx.sampleRate,
    baseLatency: ctx.baseLatency,
    outputLatency: ctx.outputLatency,
    offlineRate: new OfflineAudioContext(1, 128, 22050).sampleRate,
  };
  await ctx.close();
  return out;
}"""


async def probe(binary, config):
    with PageServer({"/": ("text/html", "<!doctype html><title>media timing</title>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE)


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    ok = compare(await probe(binary, PIXEL10), {
        "rvfc": True, "cancel": True, "sampleRate": 48000,
        "baseLatency": 0.005333, "outputLatency": 0.021333, "offlineRate": 22050,
    })
    print("\n=== control (no profile): Gecko's baseLatency ===")
    control = compare({"baseLatency": (await probe(binary, {}))["baseLatency"]}, {"baseLatency": 0})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
