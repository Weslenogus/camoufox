"""
Verify the WebGPU adapter (patches/android/android-17-webgpu.patch).

With {"device:profile": "pixel10"}, navigator.gpu is present in the window
and in a dedicated worker, and the adapter is the Pixel 10's as Chrome
reports it (a real device's WebGPU report):

  * adapter.info: vendor "img-tec", architecture "d-series", empty device
    and description, subgroup sizes 4..128, not a fallback adapter;
  * adapter.features: the phone's list -- texture-compression-astc and -etc2,
    no texture-compression-bc (a desktop format);
  * adapter.limits: the phone's (maxBufferSize 2 GiB,
    maxStorageBufferBindingSize 128 MiB, maxComputeWorkgroupSizeZ 64, ...);
  * navigator.gpu.getPreferredCanvasFormat() "rgba8unorm", as on Android.

The adapter needs a host WebGPU backend (Vulkan; lavapipe will do). Without
one requestAdapter() resolves null and only the API's presence is checked.

The control launch (no profile) does not get the phone's adapter.

Run:
    python tests/patches/android-webgpu.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""async () => {
  const out = {gpu: 'gpu' in navigator};
  if (!out.gpu) return out;
  out.preferredFormat = navigator.gpu.getPreferredCanvasFormat();
  out.worker = await new Promise(r => {
    const w = new Worker(URL.createObjectURL(new Blob(
      ["postMessage('gpu' in navigator)"], {type: 'text/javascript'})));
    w.onmessage = e => r(e.data);
  });
  const adapter = await navigator.gpu.requestAdapter({powerPreference: 'low-power'});
  if (!adapter) { out.adapter = null; return out; }
  const i = adapter.info;
  out.info = {vendor: i.vendor, architecture: i.architecture, device: i.device,
              description: i.description, subgroupMinSize: i.subgroupMinSize,
              subgroupMaxSize: i.subgroupMaxSize, isFallbackAdapter: i.isFallbackAdapter};
  out.features = [...adapter.features].sort();
  const l = adapter.limits;
  out.limits = {maxBufferSize: l.maxBufferSize, maxStorageBufferBindingSize: l.maxStorageBufferBindingSize,
                maxComputeWorkgroupSizeZ: l.maxComputeWorkgroupSizeZ, maxBindGroups: l.maxBindGroups,
                maxInterStageShaderVariables: l.maxInterStageShaderVariables,
                maxTextureDimension2D: l.maxTextureDimension2D};
  return out;
}"""

FEATURES = sorted([
    "clip-distances", "core-features-and-limits", "depth-clip-control",
    "depth32float-stencil8", "dual-source-blending", "float32-blendable",
    "indirect-first-instance", "primitive-index", "rg11b10ufloat-renderable",
    "shader-f16", "subgroups", "texture-component-swizzle",
    "texture-compression-astc", "texture-compression-etc2",
    "texture-formats-tier1", "texture-formats-tier2", "timestamp-query",
])


# The probe iterates adapter.features, which the isolated world cannot do
# (Xrays do not wrap iterators), so the page defines it and a "mw:"
# evaluation runs it.
PAGE = "<!doctype html><title>webgpu</title><script>window.probe = " + PROBE + ";</script>"


async def probe(binary, config):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        async with launch_raw(binary, dict(config, allowMainWorld=True)) as page:
            await page.goto(server.url("/"))
            return await page.evaluate("mw:window.probe()")


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    data = await probe(binary, PIXEL10)
    ok = compare({"navigator.gpu": data.get("gpu"), "worker navigator.gpu": data.get("worker"),
                  "preferred canvas format": data.get("preferredFormat")},
                 {"navigator.gpu": True, "worker navigator.gpu": True,
                  "preferred canvas format": "rgba8unorm"})
    if data.get("adapter", 0) is None:
        print("    [info] no host WebGPU adapter; adapter checks skipped")
    elif data.get("gpu"):
        ok &= compare({"info": data["info"], "features": data["features"],
                       "no BC compression": "texture-compression-bc" not in data["features"],
                       "limits": data["limits"]}, {
            "info": {"vendor": "img-tec", "architecture": "d-series", "device": "",
                     "description": "", "subgroupMinSize": 4, "subgroupMaxSize": 128,
                     "isFallbackAdapter": False},
            "features": FEATURES,
            "no BC compression": True,
            "limits": {"maxBufferSize": 2147483648, "maxStorageBufferBindingSize": 134217728,
                       "maxComputeWorkgroupSizeZ": 64, "maxBindGroups": 4,
                       "maxInterStageShaderVariables": 28, "maxTextureDimension2D": 16384},
        })
    print("\n=== control (no profile): not the phone's adapter ===")
    data = await probe(binary, {})
    vendor = (data.get("info") or {}).get("vendor")
    control = compare({"phone adapter": vendor == "img-tec"}, {"phone adapter": False})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
