"""
Verify the Pixel 10 WebGL identity (patches/android/android-07-webgl.patch).

With {"device:profile": "pixel10"}, in WebGL1 and WebGL2:

  * UNMASKED_VENDOR_WEBGL "Imagination Technologies", UNMASKED_RENDERER_WEBGL
    "PowerVR D-Series DXT-48-1536" -- the Tensor G5's GPU;
  * VENDOR / RENDERER / VERSION / SHADING_LANGUAGE_VERSION in Chrome's form
    ("WebKit", "WebKit WebGL", "WebGL 1.0 (OpenGL ES 2.0 Chromium)", ...);
  * WEBGL_compressed_texture_astc offered, getExtension() non-null, its formats
    in COMPRESSED_TEXTURE_FORMATS once enabled (RGBA 4x4, 6x6, 8x8 and
    SRGB8_ALPHA8 4x4 among them), and a correctly sized ASTC upload succeeds
    with no GL error -- even on a desktop GPU that cannot decode ASTC;
  * WEBGL_compressed_texture_s3tc (and its sRGB twin) absent: getExtension()
    returns null and it is not listed;
  * every listed extension can actually be obtained;
  * mediump float precision {rangeMin 15, rangeMax 15, precision 10} in both
    shader stages, as fp16 hardware reports it.

The control launch keeps the host's own answers (S3TC is a desktop format, so
a desktop GPU normally offers it).

Run:
    python tests/patches/android-webgl.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""(kind) => {
  const c = document.createElement('canvas');
  const gl = c.getContext(kind);
  if (!gl) return 'no ' + kind;
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  const exts = gl.getSupportedExtensions();
  const astc = gl.getExtension('WEBGL_compressed_texture_astc');
  const formats = astc ? Array.from(gl.getParameter(gl.COMPRESSED_TEXTURE_FORMATS)) : [];
  let upload = 'no extension';
  if (astc) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    // 8x8 texels of 4x4 blocks = 4 blocks of 16 bytes.
    gl.compressedTexImage2D(gl.TEXTURE_2D, 0, astc.COMPRESSED_RGBA_ASTC_4x4_KHR, 8, 8, 0, new Uint8Array(64));
    const e1 = gl.getError();
    // A wrong size must still be rejected, as on real hardware.
    gl.compressedTexImage2D(gl.TEXTURE_2D, 0, astc.COMPRESSED_RGBA_ASTC_4x4_KHR, 8, 8, 0, new Uint8Array(63));
    const e2 = gl.getError();
    upload = [e1, e2 === gl.INVALID_VALUE];
  }
  const prec = (shader, type) => {
    const f = gl.getShaderPrecisionFormat(shader, type);
    return [f.rangeMin, f.rangeMax, f.precision];
  };
  return {
    vendor: dbg && gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL),
    renderer: dbg && gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL),
    VENDOR: gl.getParameter(gl.VENDOR),
    RENDERER: gl.getParameter(gl.RENDERER),
    VERSION: gl.getParameter(gl.VERSION),
    SHADING_LANGUAGE_VERSION: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
    astcListed: exts.includes('WEBGL_compressed_texture_astc'),
    astcObject: !!astc,
    astcProfiles: astc ? astc.getSupportedProfiles() : null,
    astcFormats: [0x93B0, 0x93B4, 0x93B7, 0x93D0].every(f => formats.includes(f)),
    astcUpload: upload,
    s3tcListed: exts.some(e => e.startsWith('WEBGL_compressed_texture_s3tc')),
    s3tcObject: gl.getExtension('WEBGL_compressed_texture_s3tc'),
    everyListedObtainable: exts.every(e => gl.getExtension(e) !== null),
    mediumVertex: prec(gl.VERTEX_SHADER, gl.MEDIUM_FLOAT),
    mediumFragment: prec(gl.FRAGMENT_SHADER, gl.MEDIUM_FLOAT),
  };
}"""


def expected(kind: str):
    gl2 = kind == "webgl2"
    return {
        "vendor": "Imagination Technologies",
        "renderer": "PowerVR D-Series DXT-48-1536",
        "VENDOR": "WebKit",
        "RENDERER": "WebKit WebGL",
        "VERSION": "WebGL 2.0 (OpenGL ES 3.0 Chromium)" if gl2 else "WebGL 1.0 (OpenGL ES 2.0 Chromium)",
        "SHADING_LANGUAGE_VERSION": (
            "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)" if gl2
            else "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)"),
        "astcListed": True,
        "astcObject": True,
        "astcProfiles": ["ldr"],
        "astcFormats": True,
        "astcUpload": [0, True],
        "s3tcListed": False,
        "s3tcObject": None,
        "everyListedObtainable": True,
        "mediumVertex": [15, 15, 10],
        "mediumFragment": [15, 15, 10],
    }


async def probe(binary, config, kind):
    with PageServer({"/": ("text/html", "<!doctype html><title>webgl</title>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE, kind)


async def main(binary) -> bool:
    ok = True
    for kind in ("webgl", "webgl2"):
        print(f"\n=== pixel10: {kind} ===")
        data = await probe(binary, PIXEL10, kind)
        if not isinstance(data, dict):
            print(f"  FAIL: {data}")
            ok = False
            continue
        ok &= compare(data, expected(kind))
    print("\n=== control (no profile): host answers (informational) ===")
    data = await probe(binary, {}, "webgl")
    if isinstance(data, dict):
        for key in ("vendor", "renderer", "astcListed", "s3tcListed", "mediumFragment"):
            print(f"    [info] {key}: {data[key]}")
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
