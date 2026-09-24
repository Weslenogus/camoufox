"""
Verify the hardware-decoder answer of MediaCapabilities.decodingInfo
(patches/android/android-16-media-capabilities.patch).

With {"device:profile": "pixel10"}, H.264, VP9 and AV1 up to 1920x1080 at 30 fps
are {supported, smooth, powerEfficient} -- in the window and in a worker --
whatever decoders the host happens to have. Above the envelope they are still
supported, but not smooth or power-efficient, and a codec the phone does not
decode (or an impossible container/codec pair) is left to Gecko.

Run:
    python tests/patches/android-media-capabilities.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

CONFIGS = {
    "h264 1080p30 mp4": ("video/mp4; codecs=\"avc1.640028\"", 1920, 1080, 30),
    "vp9 1080p30 webm": ("video/webm; codecs=\"vp09.00.40.08\"", 1920, 1080, 30),
    "vp9 720p30 webm (vp9)": ("video/webm; codecs=\"vp9\"", 1280, 720, 30),
    "av1 1080p30 mp4": ("video/mp4; codecs=\"av01.0.08M.08\"", 1920, 1080, 30),
    "av1 1080p30 webm": ("video/webm; codecs=\"av01.0.08M.08\"", 1920, 1080, 30),
    "h264 2160p60 mp4": ("video/mp4; codecs=\"avc1.640033\"", 3840, 2160, 60),
    "h264 in webm": ("video/webm; codecs=\"avc1.640028\"", 1920, 1080, 30),
}

PROBE = r"""async (configs) => {
  const run = async (mc, configs) => {
    const out = {};
    for (const [name, [contentType, width, height, framerate]] of Object.entries(configs)) {
      try {
        const r = await mc.decodingInfo({type: 'file', video: {contentType, width, height, framerate, bitrate: 4000000}});
        out[name] = [r.supported, r.smooth, r.powerEfficient];
      } catch (e) { out[name] = 'error: ' + e.name; }
    }
    return out;
  };
  const worker = await new Promise(resolve => {
    // run's source only: the configurations travel in the message.
    const src = `const run = ${run.toString()};
      onmessage = async e => postMessage(await run(navigator.mediaCapabilities, JSON.parse(e.data)));`;
    const w = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    w.onmessage = e => resolve(e.data);
    w.onerror = e => resolve('worker error: ' + e.message);
    w.postMessage(JSON.stringify(configs));
  });
  return {window: await run(navigator.mediaCapabilities, configs), worker};
}"""

EXPECTED = {
    "h264 1080p30 mp4": [True, True, True],
    "vp9 1080p30 webm": [True, True, True],
    "vp9 720p30 webm (vp9)": [True, True, True],
    "av1 1080p30 mp4": [True, True, True],
    "av1 1080p30 webm": [True, True, True],
    "h264 2160p60 mp4": [True, False, False],
    "h264 in webm": [False, False, False],
}


async def probe(binary, config):
    with PageServer({"/": ("text/html", "<!doctype html><title>mc</title>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE, CONFIGS)


async def main(binary) -> bool:
    print("\n=== pixel10: window ===")
    data = await probe(binary, PIXEL10)
    ok = compare(data["window"], EXPECTED)
    print("\n=== pixel10: worker ===")
    ok &= compare(data["worker"], EXPECTED)
    print("\n=== control (no profile): the host's own answers (informational) ===")
    for name, result in (await probe(binary, {}))["window"].items():
        print(f"    [info] {name}: {result}")
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
