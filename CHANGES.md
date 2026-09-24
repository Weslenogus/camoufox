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

## Task 5 - User-Agent Client Hints

User-Agent Client Hints, which Firefox lacks entirely. `navigator.userAgentData`
(`NavigatorUAData`, window and workers, secure contexts) with `brands`,
`mobile`, `platform`, `getHighEntropyValues()` and `toJSON()`, and the
`Sec-CH-UA` request headers, built from one source (`camoucfg/UAClientHints.hpp`)
so the page's view and the wire agree. Chrome 155's brand list follows
Chromium's GREASE algorithm; architecture and bitness are empty and
formFactors is ["Mobile"], as Chrome reports on a phone. Headers go only to
potentially trustworthy URLs (https, localhost), sorted by name as Chrome
sends them; the high-entropy ones (arch, bitness, model, platform-version,
full-version-list) are gated by `clientHints:sendHighEntropy`, which the
profile sets. Without `userAgentData:brands` there are no client hints at all.

- `patches/android/android-05-client-hints.patch` (patch; lines in the patched source tree):
  - `dom/base/Navigator.cpp`: L11, L183, L287-288, L782-789
  - `dom/base/Navigator.h`: L45, L183, L332
  - `dom/base/NavigatorUAData.cpp`: L1-119
  - `dom/base/NavigatorUAData.h`: L1-54
  - `dom/base/moz.build`: L579-585
  - `dom/webidl/NavigatorUAData.webidl`: L1-56
  - `dom/webidl/moz.build`: L845
  - `dom/workers/WorkerNavigator.cpp`: L8, L60, L92-93, L264-274
  - `dom/workers/WorkerNavigator.h`: L33, L55, L114
  - `netwerk/protocol/http/nsHttpHandler.cpp`: L17-18, L750-764
- `additions/camoucfg/DeviceProfiles.cpp`: L40-65
- `additions/camoucfg/UAClientHints.hpp`: new file, L1-118
- `settings/camoucfg.jvv`: L322-338
- `settings/properties.json`: L119-131
- `tests/patches/android-client-hints.py`: new file, L1-160

## Task 6 - Synthetic device motion and orientation

A desktop has no motion sensors, so the profile gets a synthetic 60 Hz
source (interval 16 ms, as Chrome on Android) behind `devicemotion`,
`deviceorientation` and `deviceorientationabsolute`: a phone held still-ish,
at a per-session tilt with beta in [0, 5] and gamma in [0, 2] degrees
(`sensors:betaRange`/`gammaRange`) and a random heading, plus gaussian hand
tremor (sigma 0.15 degrees, `sensors:tremorSigma`). Gravity is derived from
that tilt, so `accelerationIncludingGravity` and the orientation agree the way
a real device's do; acceleration noise sigma 0.08 m/s^2
(`sensors:accelSigma`), rotation-rate noise 0.3 deg/s (`sensors:gyroSigma`).
Values are rounded as Chromium rounds them before they reach a page
(acceleration and Euler angles to 0.1; rotation rate to 0.1 degree in
radians). The timer runs only while a page listens.

- `patches/android/android-06-sensors.patch` (patch; lines in the patched source tree):
  - `dom/system/moz.build`: L85-87
  - `dom/system/nsDeviceSensors.cpp`: L9-13, L110-112, L114-116, L165-170, L191-195, L582-845
  - `dom/system/nsDeviceSensors.h`: L10, L18-19, L66-75
- `settings/camoucfg.jvv`: L338-343
- `settings/properties.json`: L131-136
- `tests/patches/android-sensors.py`: new file, L1-144

## Task 7 - WebGL: PowerVR identity, extensions, ASTC, fp16 mediump

WebGL as Chrome reports it on the Pixel 10's GPU (the PowerVR D-Series
DXT-48-1536 in Tensor G5): unmasked vendor/renderer, Chrome's
VENDOR/RENDERER/VERSION/SHADING_LANGUAGE_VERSION strings, Chrome on Android's
extension lists (less the few Gecko does not implement), and fp16 mediump
precision (15/15/10). `WEBGL_compressed_texture_astc` is offered even when
the host GPU cannot decode ASTC (`webGl:emulateAstc`): the extension, its
formats in COMPRESSED_TEXTURE_FORMATS, and correctly sized uploads succeed
(wrong sizes still fail as on hardware), with `getSupportedProfiles()` from
`webGl:astcProfiles`. S3TC, a desktop format, is not offered.

- `patches/android/android-07-webgl.patch` (patch; lines in the patched source tree):
  - `dom/canvas/ClientWebGLContext.cpp`: L6202-6209
  - `dom/canvas/WebGLAstcEmulation.h`: L1-49
  - `dom/canvas/WebGLExtensions.cpp`: L7-8, L207, L209-210
  - `dom/canvas/WebGLTextureUpload.cpp`: L7-8, L584-588, L676-694, L712-717
- `additions/camoucfg/DeviceProfiles.cpp`: L12-13, L68-130
- `settings/camoucfg.jvv`: L343-345
- `settings/properties.json`: L136-138
- `tests/patches/android-webgl.py`: new file, L1-125

## Task 8 - Fingertip touch input

Touch input with a fingertip's geometry. Each new contact gets radiusX in
[18, 31], radiusY within 3 of it, rotationAngle in [0, 27] and force in
[0.38, 0.80] (`touch:*` ranges), stable for the whole gesture; its
PointerEvents report width/height equal to the contact's diameter and
pointerType "touch". Synthesized mouse input reaches the page as a finger too
(pointerType "touch", a fingertip's size, a finger's pressure while pressed),
and the click still lands. The input media features are a phone's:
`(pointer: coarse)`, `(hover: none)` and the same for any-pointer/any-hover;
the legacy touch APIs Android has are enabled through `device:prefs`.

- `patches/android/android-08-touch.patch` (patch; lines in the patched source tree):
  - `dom/base/nsContentUtils.cpp`: L10022-10039, L10042
  - `dom/events/PointerEvent.cpp`: L15, L237-242
  - `dom/events/PointerEventHandler.cpp`: L26-27, L982-985, L1001-1016, L1059-1065
  - `dom/events/Touch.cpp`: L7-13, L237-338
  - `dom/events/Touch.h`: L75-88
  - `layout/style/nsMediaFeatures.cpp`: L444-450
- `additions/camoucfg/DeviceProfiles.cpp`: L137-139
- `settings/camoucfg.jvv`: L345-349
- `settings/properties.json`: L138-142
- `tests/patches/android-touch.py`: new file, L1-150

## Task 9 - Cameras, microphone and speaker

The phone's capture devices in place of the host's, for `enumerateDevices()`
and `getUserMedia()` alike, so an id from one works in the other: the default
microphone and speaker (deviceId "default", label "Default") and the Camera2
devices in Chrome's order -- "camera2 1, facing front" (user) before
"camera2 0, facing back" (environment) -- from `mediaDevices:cameras`. Ids are
Chrome's 64 lowercase hex digits. Inputs are `InputDeviceInfo` (new interface)
with `getCapabilities()`: empty before permission, then capture formats and
facing mode; a running track adds the Image Capture controls (back: zoom
1-8 step 0.1, torch, focus and exposure modes; front: no zoom or torch).
Before permission one anonymous device per kind is listed, as in Chrome.
Captures stream synthetic frames and tone -- never the host's devices -- and
`facingMode` constraints select the matching camera.

- `patches/android/android-09-media-devices.patch` (patch; lines in the patched source tree):
  - `dom/bindings/Bindings.conf`: L400-404
  - `dom/media/AndroidMediaDevices.cpp`: L1-296
  - `dom/media/AndroidMediaDevices.h`: L1-66
  - `dom/media/MediaDeviceInfo.cpp`: L7, L9, L43-71
  - `dom/media/MediaDeviceInfo.h`: L10, L22-23, L42-44, L50, L52-71
  - `dom/media/MediaDevices.cpp`: L7, L347-379, L538, L540-559
  - `dom/media/MediaManager.cpp`: L7, L1174-1177, L1183-1195, L2437-2466, L3477-3483
  - `dom/media/moz.build`: L264
  - `dom/media/webrtc/MediaEngineFake.cpp`: L7-8, L89-92, L141-143, L146-149, L153-156, L164, L186, L217-220, L635-636
  - `dom/webidl/InputDeviceInfo.webidl`: L1-15
  - `dom/webidl/MediaTrackCapabilities.webidl`: L9, L22-33, L37, L41-42, L51-57
  - `dom/webidl/moz.build`: L770
- `additions/camoucfg/DeviceProfiles.cpp`: L131-153
- `settings/camoucfg.jvv`: L349-365
- `settings/properties.json`: L142-143
- `tests/patches/android-media-devices.py`: new file, L1-136

## Task 10 - Battery Status API

Firefox keeps the Battery Status API for its own UI (ChromeOnly); Chrome on
Android exposes `navigator.getBattery()` and `BatteryManager` to secure pages.
The profile exposes them (gate `AndroidDevice::HasBatteryAPI`, secure contexts
only) and reports level 0.78, charging false, chargingTime Infinity,
dischargingTime 14400, through the existing `battery:*` keys.

- `patches/android/android-10-battery.patch` (patch; lines in the patched source tree):
  - `dom/base/AndroidDevice.cpp`: L6-7, L31-40
  - `dom/base/AndroidDevice.h`: L30-32
  - `dom/webidl/BatteryManager.webidl`: L12-15
  - `dom/webidl/Navigator.webidl`: L137-140
- `additions/camoucfg/DeviceProfiles.cpp`: L154-159
- `tests/patches/android-battery.py`: new file, L1-51
