"""
Verify mediump shader arithmetic runs at half precision
(patches/android/android-19-mediump-precision.patch).

A desktop GPU evaluates every float at 32 bits; a phone GPU evaluates mediump
at 16. getShaderPrecisionFormat() already reports fp16 for mediump on the
Android profile -- this checks the pixels agree with it.

With {"device:profile": "pixel10"}, in WebGL1 and WebGL2 fragment shaders:

  * mediump 1.0 + 2^-11 is 1.0 (below half's resolution at 1.0);
  * mediump 1.0 + 3 * 2^-11 truncates to 1.0 + 2^-10;
  * mediump x += 2^-11 (a compound assignment) is 1.0 too;
  * a highp value stored into a mediump variable is narrowed;
  * mediump sin() results, and literals used at mediump, are rounded to
    half precision;
  * the same computations in a highp shader keep full 32-bit results.

The control launch (no profile) gets full precision everywhere.

Run:
    python tests/patches/android-mediump-precision.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

# Each case writes one value in [0, 1] to the red channel; the probe returns
# the byte read back. `u` is the uniform 2^-11 (set from JS, so nothing can be
# constant-folded), `h` a highp uniform.
CASES = {
    # (x - 1) * 2048 * (1/2): 0 at half precision, 0.5 at float precision.
    "add below resolution": "x = 1.0 + u; r = (x - 1.0) * 1024.0;",
    # 1 + 3u = 1.00146: half keeps 1 + 2^-10 -> (x-1)*512 = 0.5; float 0.75.
    "add truncates": "x = 1.0 + 3.0 * u; r = (x - 1.0) * 512.0;",
    "compound assignment": "x = 1.0; x += u; r = (x - 1.0) * 1024.0;",
    # A highp value narrowed on store: 1 + 2^-11 again.
    "highp stored in mediump": "x = hv; r = (x - 1.0) * 1024.0;",
    # sin(0.5 + 2^-11) - sin(0.5). Half keeps multiples of 2^-12 near 0.48:
    # sin(0.50049) = 0.47985 -> 1965 * 2^-12, and the folded constant
    # sin(0.5) = 0.47943 -> 1963 * 2^-12, so x = 2^-11 and r = 0.25.
    # At float precision x = 0.000428 and r = 0.219.
    "sin rounded": "x = sin(0.5 + u) - sin(0.5); r = x * 2048.0 / 4.0;",
    # A literal is narrowed before it takes part: 1.0001 is 1.0 at half.
    "literal narrowed": "x = u * 1.0001 - u; r = x * 1.0e7;",
}

WEBGL1_FS = """precision {prec} float;
uniform {prec} float u;
uniform highp float h;
void main() {{
  {prec} float x; {prec} float r;
  highp float hv = 1.0 + h;
  {body}
  gl_FragColor = vec4(r, 0.0, 0.0, 1.0);
}}"""

WEBGL2_FS = """#version 300 es
precision {prec} float;
uniform {prec} float u;
uniform highp float h;
out vec4 o;
void main() {{
  {prec} float x; {prec} float r;
  highp float hv = 1.0 + h;
  {body}
  o = vec4(r, 0.0, 0.0, 1.0);
}}"""

PROBE = r"""({kind, sources}) => {
  const c = document.createElement('canvas');
  c.width = c.height = 1;
  const gl = c.getContext(kind, {antialias: false});
  if (!gl) return 'no ' + kind;
  const vs = kind === 'webgl2'
    ? '#version 300 es\nin vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }'
    : 'attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }';
  const compile = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  };
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const out = {};
  for (const [name, src] of Object.entries(sources)) {
    try {
      const prog = gl.createProgram();
      gl.attachShader(prog, compile(gl.VERTEX_SHADER, vs));
      gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, src));
      gl.bindAttribLocation(prog, 0, 'p');
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
      gl.useProgram(prog);
      gl.uniform1f(gl.getUniformLocation(prog, 'u'), 1 / 2048);
      gl.uniform1f(gl.getUniformLocation(prog, 'h'), 1 / 2048);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      const px = new Uint8Array(4);
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      out[name] = px[0];
    } catch (e) {
      out[name] = 'error: ' + e.message;
    }
  }
  return out;
}"""

# Red byte expected at half and at float precision (1 byte of slack for the
# driver's own float -> unorm rounding).
HALF = {
    "add below resolution": 0,
    "add truncates": 128,
    "compound assignment": 0,
    "highp stored in mediump": 0,
    "sin rounded": 64,
    "literal narrowed": 0,
}
FULL = {
    "add below resolution": 128,
    "add truncates": 191,
    "compound assignment": 128,
    "highp stored in mediump": 128,
    "sin rounded": 56,
    # 2^-11 * 1e-4 * 1e7 = 0.488 -> 124
    "literal narrowed": 124,
}


def near(expected):
    if callable(expected):
        return expected
    return lambda b: isinstance(b, int) and abs(b - expected) <= 1


def sources(template, prec):
    return {name: template.format(prec=prec, body=body) for name, body in CASES.items()}


async def probe(binary, config):
    results = {}
    with PageServer({"/": ("text/html", "<!doctype html><title>mediump</title>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            for kind, template in (("webgl", WEBGL1_FS), ("webgl2", WEBGL2_FS)):
                for prec in ("mediump", "highp"):
                    results[(kind, prec)] = await page.evaluate(
                        PROBE, {"kind": kind, "sources": sources(template, prec)})
    return results


def check(results, mediump_expected) -> bool:
    ok = True
    for (kind, prec), got in results.items():
        print(f"  {kind} {prec}:")
        if isinstance(got, str):
            print(f"  FAIL: {got}")
            ok = False
            continue
        table = mediump_expected if prec == "mediump" else FULL
        ok &= compare(got, {k: near(v) for k, v in table.items()})
    return ok


async def main(binary) -> bool:
    print("\n=== pixel10: mediump evaluates at half precision ===")
    pixel = check(await probe(binary, PIXEL10), HALF)
    print("\n=== control (no profile): full precision ===")
    control = check(await probe(binary, {}), FULL)
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
