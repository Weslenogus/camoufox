"""
Verify the Pixel's camera controls and Image Capture
(patches/android/android-29-camera2-image-capture.patch).

With {"device:profile": "pixel10"}, as Chrome on Android:

  * navigator.mediaDevices.getSupportedConstraints() lists Chrome's 36
    constrainable properties -- the Image Capture ones included, Firefox's
    mediaSource / browserWindow / scrollWithPage / viewport* gone;
  * ImageCapture exists, with Chrome's shape (track, getPhotoCapabilities,
    getPhotoSettings, takePhoto, grabFrame; not an EventTarget), and refuses
    an audio track;
  * a camera track's capabilities and settings carry every control Chrome's
    Camera2 capturer reports (white balance, exposure, focus, ISO, colour
    temperature, zoom, torch), with Chrome's float values, and its settings
    an aspectRatio;
  * applyConstraints() takes those controls as Blink does: zoom snaps to a
    whole-pixel sensor crop, exposure compensation to a 1/6 EV step, an
    unsatisfiable first advanced set is an OverconstrainedError naming the
    property, and mixing them with other constraints is refused;
  * takePhoto() returns a JPEG at the camera's JPEG size (the largest, or the
    closest to the size asked for), grabFrame() an ImageBitmap of the track;
  * the frames are a noisy, unevenly lit scene, not Firefox's flat test
    pattern.

The control launch keeps Firefox's shape: its own supported constraints and
no ImageCapture.

Run:
    python tests/patches/android-camera2.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

CHROME_SUPPORTED = sorted([
    "aspectRatio", "autoGainControl", "brightness", "channelCount",
    "colorTemperature", "contrast", "deviceId", "displaySurface",
    "echoCancellation", "exposureCompensation", "exposureMode", "exposureTime",
    "facingMode", "focusDistance", "focusMode", "frameRate", "groupId",
    "height", "iso", "latency", "noiseSuppression", "pan", "pointsOfInterest",
    "resizeMode", "restrictOwnAudio", "sampleRate", "sampleSize", "saturation",
    "sharpness", "suppressLocalAudioPlayback", "tilt", "torch",
    "voiceIsolation", "whiteBalanceMode", "width", "zoom",
])

PAGE_JS = r"""
window.basics = () => {
  const out = {
    supported: Object.keys(navigator.mediaDevices.getSupportedConstraints()).sort(),
    ImageCapture: typeof ImageCapture,
  };
  if (typeof ImageCapture === 'function') {
    out.proto = Object.getOwnPropertyNames(ImageCapture.prototype).sort();
    out.isEventTarget = ImageCapture.prototype instanceof EventTarget;
    try {
      const ctx = new AudioContext();
      new ImageCapture(ctx.createMediaStreamDestination().stream.getAudioTracks()[0]);
      out.audioTrack = 'accepted';
    } catch (e) { out.audioTrack = e.name; }
  }
  return out;
};

const err = e => ({name: e.name, constraint: e.constraint ?? null, message: e.message});

window.camera = async (facingMode) => {
  const s = await navigator.mediaDevices.getUserMedia({video: {facingMode}});
  const t = s.getVideoTracks()[0];
  const out = {caps: t.getCapabilities(), settings: t.getSettings()};
  const apply = async (c) => {
    try { await t.applyConstraints(c); return 'ok'; } catch (e) { return err(e); }
  };
  if (facingMode === 'environment') {
    out.mixed = await apply({zoom: 2, width: 640});
    out.badZoom = await apply({advanced: [{zoom: 20}]});
    out.zoom = await apply({advanced: [{zoom: 3.3}]});
    out.zoomSetting = t.getSettings().zoom;
    out.constraints = t.getConstraints();
    out.torch = await apply({torch: true, exposureCompensation: 0.3});
    const after = t.getSettings();
    out.torchSetting = after.torch;
    out.compensationSetting = after.exposureCompensation;
    out.badPan = await apply({advanced: [{pan: true}]});

    const ic = new ImageCapture(t);
    out.trackSame = ic.track === t;
    out.photoSettings = await ic.getPhotoSettings();
    out.photoCaps = await ic.getPhotoCapabilities();
    try { await ic.takePhoto({imageWidth: 99999}); out.badPhoto = 'ok'; }
    catch (e) { out.badPhoto = err(e); }
    const photo = await ic.takePhoto();
    const full = await createImageBitmap(photo);
    out.photo = {type: photo.type, width: full.width, height: full.height};
    const small = await createImageBitmap(await ic.takePhoto({imageWidth: 1000}));
    out.smallPhoto = [small.width, small.height];
    const frame = await ic.grabFrame();
    out.frame = [frame.width, frame.height];

    // Luma statistics of the grabbed frame.
    const c = document.createElement('canvas');
    c.width = frame.width; c.height = frame.height;
    const g = c.getContext('2d');
    g.drawImage(frame, 0, 0);
    const lum = (x, y, w, h) => {
      const d = g.getImageData(x, y, w, h).data, v = [];
      for (let i = 0; i < d.length; i += 4) v.push(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]);
      const mean = v.reduce((a, b) => a + b, 0) / v.length;
      const sd = Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / v.length);
      return {mean, sd};
    };
    const w = frame.width, h = frame.height;
    out.noise = lum(w / 2 - 16, h / 2 - 16, 32, 32).sd;
    const corners = [lum(0, 0, 32, 32), lum(w - 32, 0, 32, 32),
                     lum(0, h - 32, 32, 32), lum(w - 32, h - 32, 32, 32)].map(r => r.mean);
    out.lightingSpread = Math.max(...corners) - Math.min(...corners);
  }
  t.stop();
  return out;
};
"""

PAGE = "<!doctype html><title>camera2</title><script>" + PAGE_JS + "</script>"


async def probe(binary, config, grant):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        # Playwright's Firefox cannot grant "camera"; the pref allows
        # getUserMedia() without a prompt, as a granted permission does.
        prefs = {"media.navigator.permission.disabled": True} if grant else None
        async with launch_raw(binary, dict(config, allowMainWorld=True),
                              prefs=prefs) as page:
            await page.goto(server.url("/"))
            data = {"basics": await page.evaluate("mw:window.basics()")}
            if grant:
                for facing in ("environment", "user"):
                    try:
                        data[facing] = await page.evaluate(f"mw:window.camera('{facing}')")
                    except Exception as e:
                        data[facing] = f"unavailable: {str(e).splitlines()[0]}"
            return data


def keys(d, names):
    return {n: d.get(n) for n in names}


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    data = await probe(binary, PIXEL10, grant=True)
    basics = data["basics"]
    ok = compare({
        "supported constraints": basics["supported"],
        "ImageCapture": basics["ImageCapture"],
        "prototype": basics.get("proto"),
        "is EventTarget": basics.get("isEventTarget"),
        "audio track": basics.get("audioTrack"),
    }, {
        "supported constraints": CHROME_SUPPORTED,
        "ImageCapture": "function",
        "prototype": sorted(["constructor", "track", "getPhotoCapabilities",
                             "getPhotoSettings", "takePhoto", "grabFrame"]),
        "is EventTarget": False,
        "audio track": "NotSupportedError",
    })

    back = data.get("environment")
    if isinstance(back, dict):
        caps, settings = back["caps"], back["settings"]
        ok &= compare({
            **keys(caps, ["whiteBalanceMode", "exposureMode", "focusMode", "torch",
                          "zoom", "exposureCompensation", "colorTemperature",
                          "focusDistance"]),
            "has iso": "iso" in caps,
            "has exposureTime": "exposureTime" in caps,
        }, {
            "whiteBalanceMode": ["continuous", "manual"],
            "exposureMode": ["continuous", "manual"],
            "focusMode": ["manual", "single-shot", "continuous"],
            "torch": True,
            "zoom": {"max": 8, "min": 1, "step": 0.1},
            "exposureCompensation": {"max": 2, "min": -2, "step": 0.1666666716337204},
            "colorTemperature": {"max": 7000, "min": 2850, "step": 50},
            "focusDistance": {"max": 3.3333332538604736, "min": 0.10000000149011612,
                              "step": 0.009999999776482582},
            "has iso": True,
            "has exposureTime": True,
        })
        ok &= compare({
            "aspectRatio": settings.get("aspectRatio"),
            **keys(settings, ["whiteBalanceMode", "exposureMode", "focusMode", "zoom",
                              "torch", "exposureCompensation", "colorTemperature",
                              "focusDistance", "iso"]),
            "pointsOfInterest reported": "pointsOfInterest" in settings,
        }, {
            "aspectRatio": settings.get("width", 0) / max(settings.get("height", 1), 1),
            "whiteBalanceMode": "continuous",
            "exposureMode": "continuous",
            "focusMode": "continuous",
            "zoom": 1,
            "torch": False,
            "exposureCompensation": 0,
            "colorTemperature": 0,
            "focusDistance": 0,
            "iso": 100,
            "pointsOfInterest reported": False,
        })
        ok &= compare({
            "mixed": back["mixed"],
            "zoom 20 (first advanced)": back["badZoom"],
            "zoom 3.3": back["zoom"],
            "zoom setting": back["zoomSetting"],
            "getConstraints": back["constraints"],
            "torch + compensation": back["torch"],
            "torch setting": back["torchSetting"],
            "compensation setting": back["compensationSetting"],
            "pan (first advanced)": back["badPan"],
        }, {
            "mixed": {"name": "OverconstrainedError", "constraint": "",
                      "message": "Mixing ImageCapture and non-ImageCapture constraints "
                                 "is not currently supported"},
            "zoom 20 (first advanced)": {"name": "OverconstrainedError", "constraint": "zoom",
                                         "message": "zoom setting out of range"},
            "zoom 3.3": "ok",
            "zoom setting": 3.3009707927703857,
            "getConstraints": {"advanced": [{"zoom": 3.3}]},
            "torch + compensation": "ok",
            "torch setting": True,
            "compensation setting": 0.3333333432674408,
            "pan (first advanced)": {"name": "OverconstrainedError", "constraint": "pan",
                                     "message": "Unsupported constraint"},
        })
        ok &= compare({
            "track": back["trackSame"],
            "photo settings": back["photoSettings"],
            "photo capabilities": back["photoCaps"],
            "takePhoto out of range": back["badPhoto"],
            "photo": back["photo"],
            "photo at imageWidth 1000": back["smallPhoto"],
            "grabFrame": back["frame"],
            "frame has sensor noise": back["noise"] > 0.8,
            "frame is unevenly lit": back["lightingSpread"] > 5,
        }, {
            "track": True,
            "photo settings": {"imageHeight": settings.get("height"),
                               "imageWidth": settings.get("width")},
            "photo capabilities": {
                "fillLightMode": ["off", "auto", "flash"],
                "imageHeight": {"max": 3072, "min": 144, "step": 1},
                "imageWidth": {"max": 4080, "min": 176, "step": 1},
                "redEyeReduction": "controllable",
            },
            "takePhoto out of range": {"name": "NotSupportedError", "constraint": None,
                                       "message": "imageWidth setting out of range"},
            "photo": {"type": "image/jpeg", "width": 4080, "height": 3072},
            "photo at imageWidth 1000": [1024, 768],
            "grabFrame": [settings.get("width"), settings.get("height")],
            "frame has sensor noise": True,
            "frame is unevenly lit": True,
        })
    else:
        print(f"    [info] back camera checks skipped: {back}")
        ok = False

    front = data.get("user")
    if isinstance(front, dict):
        ok &= compare({
            "front torch": front["caps"].get("torch"),
            "front zoom": front["caps"].get("zoom"),
            "front settings torch": front["settings"].get("torch"),
        }, {
            "front torch": None,
            "front zoom": {"max": 4, "min": 1, "step": 0.1},
            "front settings torch": None,
        })
    else:
        print(f"    [info] front camera checks skipped: {front}")
        ok = False

    print("\n=== control (no profile): Firefox's shape ===")
    data = await probe(binary, {}, grant=False)
    ok &= compare({
        "has mediaSource": "mediaSource" in data["basics"]["supported"],
        "has zoom": "zoom" in data["basics"]["supported"],
        "ImageCapture": data["basics"]["ImageCapture"],
    }, {
        "has mediaSource": True,
        "has zoom": False,
        "ImageCapture": "undefined",
    })
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
