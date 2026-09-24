"""
Verify ARM default-NaN emulation (patches/android/android-01-arm-default-nan.patch).

x86 and ARM disagree on exactly one bit of float arithmetic: the sign of the NaN
an operation *creates* from ordered operands. SSE's is negative (0xFFC00000),
ARM's positive (0x7FC00000). FingerprintJS reads that bit as its "architecture"
signal:

    const f = new Float32Array(1), u8 = new Uint8Array(f.buffer);
    f[0] = Infinity; f[0] = f[0] - f[0];
    return u8[3];                       // 255 on x86, 127 on ARM

With {"device:profile": "pixel10"} every path must read 127, in every JIT tier:
the interpreter, Baseline and Ion (forced with low tier-up thresholds), plus
DataView and the typed-array bulk paths (fill / set / from / of / constructor).
wasm must produce ARM's NaN for f32/f64 add, sub, mul, div and sqrt in both of
its compilers, and must still *propagate* an incoming NaN untouched, because ARM
does too: canonicalizing every NaN would be its own tell.

The control launch, without the profile, must still read the host CPU's value.

Run:
    python tests/patches/android-arm-nan.py [--binary /path/to/camoufox-bin]
"""

import platform
from typing import Any, Dict

from helpers import PIXEL10, compare, launch_raw, run_guard

ARM_F32 = 0x7FC00000
X86_F32 = 0xFFC00000

# Tier-up after a handful of calls, so a loop of a few thousand iterations is
# guaranteed to have run in the interpreter, Baseline and Ion.
EAGER_JIT_PREFS = {
    "javascript.options.blinterp.threshold": 2,
    "javascript.options.baselinejit.threshold": 10,
    "javascript.options.ion.threshold": 50,
    "javascript.options.ion.frequent_bailout_threshold": 1000,
}

# Each wasm compiler on its own.
WASM_TIERS = {
    "wasm baseline": {"javascript.options.wasm_optimizingjit": False},
    "wasm ion": {"javascript.options.wasm_baselinejit": False},
}

JS_PROBE = r"""() => {
  const u32 = x => x >>> 0;
  const f32Bits = v => { const f = new Float32Array([0]); f[0] = v; return u32(new Uint32Array(f.buffer)[0]); };

  // FingerprintJS getArchitecture(), called enough times to tier up.
  function arch() {
    const f = new Float32Array(1), u8 = new Uint8Array(f.buffer);
    f[0] = Infinity; f[0] = f[0] - f[0];
    return u8[3];
  }
  const archSeen = new Set();
  for (let i = 0; i < 5000; i++) archSeen.add(arch());

  function f64Sign() {
    const d = new Float64Array(1), u8 = new Uint8Array(d.buffer);
    d[0] = Infinity; d[0] = d[0] - d[0];
    return u8[7];
  }
  const f64Seen = new Set();
  for (let i = 0; i < 5000; i++) f64Seen.add(f64Sign());

  function dataView() {
    const dv = new DataView(new ArrayBuffer(12));
    const inf = Infinity, nan = inf - inf;
    dv.setFloat32(0, nan); dv.setFloat64(4, nan);
    return [dv.getUint8(0), dv.getUint8(4)];
  }
  const dvSeen = new Set();
  for (let i = 0; i < 5000; i++) dvSeen.add(dataView().join(","));

  const inf = Infinity, nan = inf - inf;
  const bulk = {};
  bulk.fill = u32(new Uint32Array(new Float32Array(1).fill(nan).buffer)[0]);
  const s = new Float32Array(1); s.set([nan]);
  bulk.set = u32(new Uint32Array(s.buffer)[0]);
  bulk.from = u32(new Uint32Array(Float32Array.from([nan]).buffer)[0]);
  bulk.of = u32(new Uint32Array(Float32Array.of(nan).buffer)[0]);
  bulk.ctor = u32(new Uint32Array(new Float32Array([nan]).buffer)[0]);
  bulk.mathSqrt = f32Bits(Math.sqrt(-1));
  bulk.mulZeroInf = f32Bits(0 * inf);

  return {
    arch: [...archSeen],
    f64SignByte: [...f64Seen],
    dataView: [...dvSeen],
    bulk,
  };
}"""

# (func $op (param f32 f32) (result i32) local.get 0 local.get 1 f32.<op> i32.reinterpret_f32)
# built by hand so the guard needs no wasm toolchain.
WASM_PROBE = r"""() => {
  const u32 = x => x >>> 0;
  function binop(opcode, isF64) {
    const t = isF64 ? 0x7c : 0x7d, rt = isF64 ? 0x7e : 0x7f;
    const reinterpret = isF64 ? 0xbd : 0xbc;
    const bytes = [0,97,115,109,1,0,0,0,
      1,7,1,0x60,2,t,t,1,rt,
      3,2,1,0,
      7,5,1,1,102,0,0,
      10,10,1,8,0,0x20,0,0x20,1,opcode,reinterpret,0x0b];
    return new WebAssembly.Instance(new WebAssembly.Module(new Uint8Array(bytes))).exports.f;
  }
  function unop(opcode, isF64) {
    const t = isF64 ? 0x7c : 0x7d, rt = isF64 ? 0x7e : 0x7f;
    const reinterpret = isF64 ? 0xbd : 0xbc;
    const bytes = [0,97,115,109,1,0,0,0,
      1,6,1,0x60,1,t,1,rt,
      3,2,1,0,
      7,5,1,1,102,0,0,
      10,8,1,6,0,0x20,0,opcode,reinterpret,0x0b];
    return new WebAssembly.Instance(new WebAssembly.Module(new Uint8Array(bytes))).exports.f;
  }
  // (param i32 f32) (result i32): f32.sub(f32.reinterpret_i32(a), b) -- an
  // incoming NaN with a payload, which both CPUs propagate (quieted).
  function propagate() {
    const bytes = [0,97,115,109,1,0,0,0,
      1,7,1,0x60,2,0x7f,0x7d,1,0x7f,
      3,2,1,0,
      7,5,1,1,102,0,0,
      10,11,1,9,0,0x20,0,0xbe,0x20,1,0x93,0xbc,0x0b];
    return new WebAssembly.Instance(new WebAssembly.Module(new Uint8Array(bytes))).exports.f;
  }
  const inf = Infinity;
  // Call each export enough times for lazy tiering to kick in as well.
  const run = (fn, ...args) => { let r; for (let i = 0; i < 2000; i++) r = fn(...args); return r; };
  const f64hi = v => Number(BigInt.asUintN(64, v) >> 32n);
  return {
    "f32.sub": u32(run(binop(0x93), inf, inf)),
    "f32.add": u32(run(binop(0x92), inf, -inf)),
    "f32.mul": u32(run(binop(0x94), 0, inf)),
    "f32.div": u32(run(binop(0x95), 0, 0)),
    "f32.sqrt": u32(run(unop(0x91), -1)),
    "f64.sub (high word)": f64hi(run(binop(0xa1, true), inf, inf)),
    "f64.div (high word)": f64hi(run(binop(0xa3, true), 0, 0)),
    "f64.sqrt (high word)": f64hi(run(unop(0x9f, true), -1)),
    "f32.sub(NaN payload) propagates": u32(run(propagate(), 0xFFA00000 | 0, 1)),
    "f32.sub ordinary result": u32(run(binop(0x93), 5, 3)),
  };
}"""


def expected_js(nan_sign_byte: int) -> Dict[str, Any]:
    f32 = ARM_F32 if nan_sign_byte == 0x7F else X86_F32
    return {
        "arch": [nan_sign_byte],
        "f64SignByte": [nan_sign_byte],
        "dataView": [f"{nan_sign_byte},{nan_sign_byte}"],
        "bulk": {k: f32 for k in ("fill", "set", "from", "of", "ctor", "mathSqrt", "mulZeroInf")},
    }


def expected_wasm(arm: bool) -> Dict[str, Any]:
    f32 = ARM_F32 if arm else X86_F32
    f64hi = 0x7FF80000 if arm else 0xFFF80000
    return {
        "f32.sub": f32,
        "f32.add": f32,
        "f32.mul": f32,
        "f32.div": f32,
        "f32.sqrt": f32,
        "f64.sub (high word)": f64hi,
        "f64.div (high word)": f64hi,
        "f64.sqrt (high word)": f64hi,
        # sNaN 0xFFA00000 quieted, sign and payload kept -- on both CPUs.
        "f32.sub(NaN payload) propagates": 0xFFE00000,
        "f32.sub ordinary result": 0x40000000,  # 2.0f
    }


async def probe(binary, config, prefs, script):
    from playwright.async_api import async_playwright
    import json
    import os

    env = dict(os.environ)
    env["CAMOU_CONFIG_1"] = json.dumps(config)
    async with async_playwright() as p:
        browser = await p.firefox.launch(
            executable_path=str(binary), headless=True, env=env,
            firefox_user_prefs=prefs,
        )
        try:
            page = await browser.new_page()
            await page.goto("about:blank")
            return await page.evaluate(script)
        finally:
            await browser.close()


async def main(binary) -> bool:
    host_is_arm = platform.machine().lower() in ("aarch64", "arm64")
    ok = True

    print("\n=== pixel10: JS typed arrays / DataView, every JIT tier ===")
    ok &= compare(await probe(binary, PIXEL10, EAGER_JIT_PREFS, JS_PROBE), expected_js(0x7F))

    for tier, prefs in WASM_TIERS.items():
        print(f"\n=== pixel10: {tier} ===")
        ok &= compare(await probe(binary, PIXEL10, prefs, WASM_PROBE), expected_wasm(True))

    host = 0x7F if host_is_arm else 0xFF
    print(f"\n=== control (no profile): host CPU value {host:#x} ===")
    ok &= compare(await probe(binary, {}, EAGER_JIT_PREFS, JS_PROBE), expected_js(host))
    for tier, prefs in WASM_TIERS.items():
        print(f"\n=== control (no profile): {tier} ===")
        ok &= compare(await probe(binary, {}, prefs, WASM_PROBE), expected_wasm(host_is_arm))

    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
