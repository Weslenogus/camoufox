# Changes: Google Pixel 10 / Android 17 device emulation

A runtime device profile. `{"device:profile": "pixel10"}` in `CAMOU_CONFIG`
turns the browser into a Google Pixel 10 running Android 17 and current stable
Chrome (arm64, 12 GB RAM, 412x915 CSS px at DPR 2.625), at the C++ engine
level. Explicit config keys still win over the profile's values, one key at a
time. Without the key, nothing below changes behaviour: every Android code
path is gated on `device:android`, which only the profile sets.

Each section below is one commit. Line numbers are generated from the diffs:
for a `patches/android/*.patch` they are lines in the patched
`camoufox-*/` source tree (the new side of each hunk); for every other file
they are lines in that file as of the commit.

Every behaviour has a guard in `tests/patches/android-*.py`, run with

    python3 -m ci.run_patch_guards --binary /path/to/camoufox-bin

and each guard also launches without the profile to check the desktop
behaviour is untouched.

## Task 0 - Device profiles

`device:profile` expands a built-in profile beneath the explicit config keys,
once, inside `MaskConfig::GetJson()`, so every existing config reader picks
it up unchanged. The profile tables are compiled once in
`camoucfg/DeviceProfiles.cpp` (camoucfg is now a build directory) rather than
in a header every reader includes. `MaskConfig::IsAndroidDevice()` is the
single gate for Android-only behaviour. Patches in `patches/android/` apply
after every other patch (`scripts/_mixin.py`), since they build on the whole
stack. An unknown profile name is reported on stderr and ignored.

- `additions/camoucfg/DeviceProfiles.hpp`: new file, L1-39
- `additions/camoucfg/DeviceProfiles.cpp`: new file, L1-70
- `additions/camoucfg/MaskConfig.hpp`: L8, L87-90, L198-208
- `additions/camoucfg/moz.build`: L11, L16-19
- `patches/android/android-00-device-profiles.patch` (patch; lines in the patched source tree):
  - `toolkit/toolkit.mozbuild`: L56-59
- `scripts/_mixin.py`: L78-84, L86-97
- `settings/camoucfg.jvv`: L312-315
- `settings/properties.json`: L112-115
- `tests/patches/helpers.py`: L60-198

## Task 1 - ARM default NaN (JS JIT and wasm)

x86 and ARM disagree on one bit of float arithmetic: the sign of a NaN an
operation creates from ordered operands (`Infinity - Infinity`, `0 * Infinity`,
`0 / 0`, `sqrt(-1)`). SSE creates `0xFFC00000`, ARM `0x7FC00000`, and
FingerprintJS reads that sign from a `Float32Array` as its architecture
signal. With `cpu:armDefaultNaN` (set by the profile), NaNs written to typed
arrays, DataViews and the asm.js heap are canonicalized in every JIT tier
(the canonical NaN is ARM's default NaN). wasm f32/f64 add, sub, mul, div and
sqrt produce ARM's NaN in both the baseline and Ion compilers, while an
incoming NaN still propagates untouched, as on ARM. Cached wasm code compiled
with the emulation is never reused without it. The switch is set in
`XPCJSContext::Initialize`, before any script runs; the public API is the new
`js/ArmNaN.h`, so no widely included header changes.

- `additions/camoucfg/DeviceProfiles.cpp`: L28-31
- `patches/android/android-01-arm-default-nan.patch` (patch; lines in the patched source tree):
  - `js/public/ArmNaN.h`: L1-29
  - `js/src/builtin/DataViewObject.cpp`: L578
  - `js/src/jit/CacheIRCompiler.cpp`: L7688-7690, L8217-8219
  - `js/src/jit/TypePolicy.cpp`: L948-950
  - `js/src/jsapi.cpp`: L41, L5127-5128, L5138-5141
  - `js/src/moz.build`: L102
  - `js/src/util/DifferentialTesting.h`: L23-48
  - `js/src/vm/TypedArrayObject-inl.h`: L668-670
  - `js/src/vm/TypedArrayObject.cpp`: L1273, L3114, L3950
  - `js/src/wasm/WasmBaselineCompile.cpp`: L144-145, L3010-3048, L3050, L3054, L3058, L3062, L3112, L3116, L3120, L3124, L3128, L3179
  - `js/src/wasm/WasmIonCompile.cpp`: L909-946, L1548-1550, L5987, L6912-6921, L7039, L7050, L7119, L7121-7122, L7134, L10394, L10423
  - `js/src/wasm/WasmModule.cpp`: L250, L269-274
  - `js/xpconnect/src/XPCJSContext.cpp`: L9-11, L1241-1247
  - `js/xpconnect/src/moz.build`: L79-81
- `settings/camoucfg.jvv`: L315-316
- `settings/properties.json`: L115-116
- `tests/patches/android-arm-nan.py`: new file, L1-222
