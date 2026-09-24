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

## Task 2 - Navigator: platform, cores, memory, touch points, vendor

The profile sets `navigator.platform` "Linux aarch64", `hardwareConcurrency`
8, `maxTouchPoints` 5 and the two members Firefox lacks: `navigator.vendor`
"Google Inc." (Firefox returns "") and `navigator.deviceMemory` 8 (Chrome's
value for 12 GB: rounded down to a power of two and capped at 8).
`deviceMemory` is a new `[SecureContext]` member on `Navigator` and
`WorkerNavigator`, gated by `AndroidDevice::HasDeviceMemory` so it exists only
when configured, and read from one place so every realm agrees (window,
iframes, dedicated, shared and service workers). `vendor` and
`maxTouchPoints` stay Window-only, as in every browser. `dom/base/AndroidDevice`
holds the WebIDL gates the Android changes share. Profile values are now
round-tripped through the JSON parser so they are typed exactly like the same
values written in `CAMOU_CONFIG`.

- `additions/camoucfg/DeviceProfiles.cpp`: L32-39, L44, L46-48, L50-54
- `patches/android/android-02-navigator.patch` (patch; lines in the patched source tree):
  - `dom/base/AndroidDevice.cpp`: L1-26
  - `dom/base/AndroidDevice.h`: L1-31
  - `dom/base/Navigator.cpp`: L9, L564-571, L774-778
  - `dom/base/Navigator.h`: L180
  - `dom/base/moz.build`: L562-569
  - `dom/webidl/Navigator.webidl`: L310-318
  - `dom/webidl/WorkerNavigator.webidl`: L14
  - `dom/workers/WorkerNavigator.cpp`: L7, L260-265
  - `dom/workers/WorkerNavigator.h`: L111
- `settings/camoucfg.jvv`: L37-38
- `settings/properties.json`: L15-16
- `tests/patches/android-navigator.py`: new file, L1-179

## Task 3 - Desktop-only APIs removed

Chrome on Android has none of EyeDropper, WebHID, `getScreenDetails`,
Document Picture-in-Picture, `queryLocalFonts`, Window Controls Overlay, the
File System Access pickers or `navigator.keyboard`. Firefox implements only
Document Picture-in-Picture among them, behind `dom.documentpip.enabled`. A
new `device:prefs` key (an object of pref name to bool/int/string, set by the
profile) is applied to the default pref branch right after `camoufox.cfg`, so
the device's platform defaults win over the desktop ones while user prefs
(prefs.js, Playwright's `firefox_user_prefs`) still override them; content
processes inherit them from the parent. The guard pins that the other APIs
stay absent. SharedWorker is deliberately kept: Chrome ships it on Android
since M148.

- `additions/camoucfg/DeviceProfiles.cpp`: L40-47
- `patches/android/android-03-desktop-apis.patch` (patch; lines in the patched source tree):
  - `modules/libpref/Preferences.cpp`: L12-13, L4177-4212, L4217
  - `modules/libpref/moz.build`: L186-188
- `settings/camoucfg.jvv`: L318-321
- `settings/properties.json`: L118
- `tests/patches/android-desktop-apis.py`: new file, L1-82

## Task 4 - Android-only APIs: Web NFC, Contact Picker, window.orientation

APIs only Chrome on Android has, exposed on the Android profile only (gate
`AndroidDevice::Exposed`, secure contexts where Chrome requires them). Web
NFC -- `NDEFReader`, `NDEFMessage`, `NDEFRecord`, `NDEFReadingEvent` -- with
working records and messages, `onreading`/`onreadingerror`, and `scan()`,
`write()` and `makeReadOnly()` refusing with NotAllowedError, as Chrome does
without the NFC permission. The Contact Picker -- `navigator.contacts`
(`ContactsManager`), `getProperties()` resolving Chrome's five properties,
`select()` requiring user activation, and `ContactAddress`. `window.orientation`
(0 for the profile's portrait screen) and `window.onorientationchange`, which
Gecko only builds for Android. `ondeviceorientationabsolute` already exists.

- `patches/android/android-04-android-apis.patch` (patch; lines in the patched source tree):
  - `dom/base/AndroidDevice.cpp`: L26-28
  - `dom/base/AndroidDevice.h`: L27-29
  - `dom/base/ContactsManager.cpp`: L1-90
  - `dom/base/ContactsManager.h`: L1-82
  - `dom/base/NDEFReader.cpp`: L1-345
  - `dom/base/NDEFReader.h`: L1-165
  - `dom/base/Navigator.cpp`: L10, L173, L258-259, L2390-2396
  - `dom/base/Navigator.h`: L89, L237-238, L320
  - `dom/base/moz.build`: L566-572, L575-576
  - `dom/base/nsGlobalWindowInner.h`: L600-615
  - `dom/bindings/Bindings.conf`: L123-127, L579-591
  - `dom/webidl/ContactsManager.webidl`: L1-54
  - `dom/webidl/NDEFReader.webidl`: L1-102
  - `dom/webidl/Navigator.webidl`: L319-326
  - `dom/webidl/Window.webidl`: L716, L718, L722-726, L728
  - `dom/webidl/moz.build`: L499, L845
- `tests/patches/android-api-stubs.py`: new file, L1-115
