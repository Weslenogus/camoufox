"""
Verify the phone's capture devices (patches/android/android-09-media-devices.patch).

With {"device:profile": "pixel10"}, navigator.mediaDevices.enumerateDevices()
reports what Chrome on a Pixel does:

  * before any permission: one anonymous device per kind -- audioinput,
    videoinput, audiooutput -- with empty deviceId, label and groupId, the
    inputs as InputDeviceInfo whose getCapabilities() is {};
  * once camera and microphone are allowed: the default microphone and
    speaker (deviceId "default", label "Default"), then the two Camera2
    devices in Chrome's order -- "camera2 1, facing front" before
    "camera2 0, facing back" -- with 64-hex-digit ids;
  * the back camera's capabilities: facingMode ["environment"], and, on a
    running track, zoom, torch, focusMode and exposureMode; the front camera
    has facingMode ["user"] and neither zoom nor torch.

The control launch keeps Firefox's own shape: no InputDeviceInfo interface.

Run:
    python tests/patches/android-media-devices.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""async () => {
  const list = await navigator.mediaDevices.enumerateDevices();
  return {
    InputDeviceInfo: 'InputDeviceInfo' in window,
    devices: list.map(d => ({
      kind: d.kind, label: d.label, deviceId: d.deviceId, groupId: d.groupId,
      type: d.constructor.name,
      caps: typeof d.getCapabilities === 'function' ? d.getCapabilities() : null,
    })),
  };
}"""

TRACK = r"""async () => {
  const s = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}});
  const t = s.getVideoTracks()[0];
  const out = {caps: t.getCapabilities(), settings: t.getSettings()};
  t.stop();
  return out;
}"""

HEX64 = lambda v: isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)


async def probe(binary, config, grant):
    with PageServer({"/": ("text/html", "<!doctype html><title>media</title>")}) as server:
        options = {"permissions": ["camera", "microphone"]} if grant else {}
        async with launch_raw(binary, config, **options) as page:
            await page.goto(server.url("/"))
            data = await page.evaluate(PROBE)
            if grant and data["InputDeviceInfo"]:
                try:
                    data["track"] = await page.evaluate(TRACK)
                except Exception as e:  # no fake capture source on the host
                    data["track"] = f"unavailable: {str(e).splitlines()[0]}"
            return data


def summarize(data):
    out = {"InputDeviceInfo": data["InputDeviceInfo"],
           "kinds": [d["kind"] for d in data["devices"]],
           "labels": [d["label"] for d in data["devices"]]}
    for d in data["devices"]:
        if d["kind"] == "videoinput" and d["label"]:
            side = "back" if "back" in d["label"] else "front"
            out[f"{side} facingMode"] = (d["caps"] or {}).get("facingMode")
            out[f"{side} deviceId is 64 hex"] = HEX64(d["deviceId"])
            out[f"{side} has zoom before capture"] = "zoom" in (d["caps"] or {})
    return out


async def main(binary) -> bool:
    print("\n=== pixel10: before permission ===")
    data = await probe(binary, PIXEL10, grant=False)
    ok = compare({
        "InputDeviceInfo": data["InputDeviceInfo"],
        "kinds": [d["kind"] for d in data["devices"]],
        "all anonymous": all(not d["deviceId"] and not d["label"] and not d["groupId"]
                             for d in data["devices"]),
        "input types": [d["type"] for d in data["devices"] if d["kind"] != "audiooutput"],
        "capabilities": [d["caps"] for d in data["devices"] if d["kind"] != "audiooutput"],
    }, {
        "InputDeviceInfo": True,
        "kinds": ["audioinput", "videoinput", "audiooutput"],
        "all anonymous": True,
        "input types": ["InputDeviceInfo", "InputDeviceInfo"],
        "capabilities": [{}, {}],
    })

    print("\n=== pixel10: camera and microphone allowed ===")
    data = await probe(binary, PIXEL10, grant=True)
    mic = next((d for d in data["devices"] if d["kind"] == "audioinput"), {})
    ok &= compare(dict(summarize(data), **{"microphone deviceId": mic.get("deviceId")}), {
        "InputDeviceInfo": True,
        "kinds": ["audioinput", "videoinput", "videoinput", "audiooutput"],
        "labels": ["Default", "camera2 1, facing front", "camera2 0, facing back", "Default"],
        "front facingMode": ["user"],
        "back facingMode": ["environment"],
        "front deviceId is 64 hex": True,
        "back deviceId is 64 hex": True,
        "front has zoom before capture": False,
        "back has zoom before capture": False,
        "microphone deviceId": "default",
    })
    track = data.get("track")
    if isinstance(track, dict):
        caps = track["caps"]
        ok &= compare({
            "track facingMode": caps.get("facingMode"),
            "track has zoom": "zoom" in caps,
            "track torch": caps.get("torch"),
            "track focusMode": bool(caps.get("focusMode")),
            "track exposureMode": bool(caps.get("exposureMode")),
        }, {
            "track facingMode": ["environment"],
            "track has zoom": True,
            "track torch": True,
            "track focusMode": True,
            "track exposureMode": True,
        })
    else:
        print(f"    [info] running-track checks skipped: {track}")

    print("\n=== control (no profile): Firefox's shape ===")
    data = await probe(binary, {}, grant=False)
    ok &= compare({"InputDeviceInfo": data["InputDeviceInfo"]}, {"InputDeviceInfo": False})
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
