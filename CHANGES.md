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
  - `dom/base/ContactsManager.h`: L1-83
  - `dom/base/NDEFReader.cpp`: L1-346
  - `dom/base/NDEFReader.h`: L1-167
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
  - `dom/webidl/Navigator.webidl`: L318-319
  - `dom/webidl/NavigatorUAData.webidl`: L1-56
  - `dom/webidl/WorkerNavigator.webidl`: L15
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
  - `dom/bindings/Bindings.conf`: L400-404, L505-510
  - `dom/media/AndroidMediaDevices.cpp`: L1-296
  - `dom/media/AndroidMediaDevices.h`: L1-66
  - `dom/media/MediaDeviceInfo.cpp`: L7, L9, L43-71
  - `dom/media/MediaDeviceInfo.h`: L9, L11, L23-24, L43-45, L51, L53-72
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

## Task 11 - Screen, viewport, orientation and safe areas

The phone's screen: 412x915 CSS px (1080x2424 at DPR 2.625), available area
412x873, color depth 24, `devicePixelRatio` 2.625, inner 412x873 and outer
412x915, through the existing screen/window keys. New: `screen.orientation`
reports `screen.orientation.type`/`angle` (portrait-primary, 0) and the
orientation media query follows it; `env(safe-area-inset-*)` resolves to the
configured insets (24 px top and bottom) instead of the host's zeros.

- `patches/android/android-11-screen.patch` (patch; lines in the patched source tree):
  - `dom/base/ScreenOrientation.cpp`: L7-8, L696-731, L733-735, L750-752, L775-778, L797-800
  - `dom/base/nsScreen.cpp`: L218-222
  - `layout/style/GeckoBindings.cpp`: L9-10, L1785-1795
  - `layout/style/nsMediaFeatures.cpp`: L233-242
- `additions/camoucfg/DeviceProfiles.cpp`: L154-178
- `settings/camoucfg.jvv`: L365-371
- `settings/properties.json`: L143-149
- `tests/patches/android-screen.py`: new file, L1-100

## Task 12 - Android's fonts

Text renders in Android's own fonts, bundled with the browser
(`browser/fonts/android`, installed beside Twemoji by `browser/fonts/moz.build`):
AOSP's variable Roboto for `sans-serif`, `system-ui` and unstyled text, AOSP
Noto Serif for `serif`, Droid Sans Mono for `monospace`, and Noto Color Emoji
(COLRv1) for emoji, so flags render as coloured flag glyphs. The CSS2
system-font keywords use Roboto 12px, as Gecko's Android build does. The
profile's font allowlist (`fonts`) makes those four the only visible
families, so `-apple-system`, `BlinkMacSystemFont` and desktop families such
as Arial do not resolve; the generic-family prefs come through `device:prefs`.

- `patches/android/android-12-fonts.patch` (patch; lines in the patched source tree):
  - `browser/fonts/moz.build`: L8-24
  - `gfx/thebes/gfxPlatformFontList.cpp`: L2311-2315
  - `layout/base/nsLayoutUtils.cpp`: L9771, L9773, L9800-9805
- `additions/camoucfg/DeviceProfiles.cpp`: L194-212, L214-217
- `additions/browser/fonts/android/README.md`: new file, L1-17
- `additions/browser/fonts/android/LICENSE-OFL.txt`: new file, L1-94
- `additions/browser/fonts/android/LICENSE-Apache-2.0.txt`: new file, L1-202
- `additions/browser/fonts/android/Roboto-Regular.ttf`: new file (binary font, 2371712 bytes)
- `additions/browser/fonts/android/NotoSerif-Regular.ttf`: new file (binary font, 246740 bytes)
- `additions/browser/fonts/android/NotoSerif-Bold.ttf`: new file (binary font, 247892 bytes)
- `additions/browser/fonts/android/NotoSerif-Italic.ttf`: new file (binary font, 249748 bytes)
- `additions/browser/fonts/android/NotoSerif-BoldItalic.ttf`: new file (binary font, 263080 bytes)
- `additions/browser/fonts/android/DroidSansMono.ttf`: new file (binary font, 108128 bytes)
- `additions/browser/fonts/android/NotoColorEmoji.ttf`: new file (binary font, 5054984 bytes)
- `tests/patches/android-fonts.py`: new file, L1-107

## Task 13 - User agent, Accept-Language, WebRTC host candidates

Chrome's reduced Android user agent (`Mozilla/5.0 (Linux; Android 10; K)
AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36`)
on every request -- documents, subresources, fetch, workers, WebSockets -- and
in every realm's `navigator.userAgent`/`appVersion`; `Accept-Language`
`fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7`; Chrome's `productSub`. Firefox's own
`navigator.oscpu`, `navigator.buildID` and `taintEnabled()` are absent on the
profile (gate `AndroidDevice::IsNotEmulated`). WebRTC host candidates stay
random `<uuid>.local` mDNS names -- what Chrome on Android sends -- and the
guard pins that no LAN address or hostname appears in any candidate.

- `patches/android/android-13-network-headers.patch` (patch; lines in the patched source tree):
  - `dom/base/AndroidDevice.cpp`: L31-35, L39-44
  - `dom/base/AndroidDevice.h`: L30-32
  - `dom/webidl/Navigator.webidl`: L61-62, L182-185, L195-196
- `additions/camoucfg/DeviceProfiles.cpp`: L42-56
- `tests/patches/android-network-headers.py`: new file, L1-134

## Task 14 - Permission states

`navigator.permissions.query()` answers as Chrome on a fresh phone does:
anything the user has not granted is "prompt". Firefox's answers leaked its
configuration -- a pref-level block (`permissions.default.*`) read "denied",
and a persisted "Always Ask" camera or microphone read "granted"; a real grant
(e.g. Playwright's `grantPermissions`) still reads "granted".
`Permissions.prototype.query` is left untouched, so it stays a native
function.

- `patches/android/android-14-permissions.patch` (patch; lines in the patched source tree):
  - `dom/permission/PermissionUtils.cpp`: L7-8, L69-80
  - `dom/permission/moz.build`: L38-40
- `tests/patches/android-permissions.py`: new file, L1-79

## Task 15 - Automation markers

No automation marker reaches the page. `navigator.webdriver` stays false and
on `Navigator.prototype` (deleting it would itself be a marker); no
Selenium/ChromeDriver/PhantomJS/Puppeteer/Playwright/CDP globals or root
attributes exist (pinned by the guard). New: stacks captured by page code
that automation called into -- `page.evaluate` calling a page function, a
listener fired by an evaluated `click()` -- showed Juggler's frames
(`chrome://juggler/...`) and `debugger eval code`. Juggler runs its page-side
scripts with the page's principal, so principal filtering kept them; with
`automation:hideStackFrames` (set by the profile) SpiderMonkey hides them
from every non-system observer (`Error.stack`, SavedFrame, DOM exceptions),
through the new `js/AutomationFrames.h`.

- `patches/android/android-15-automation.patch` (patch; lines in the patched source tree):
  - `js/public/AutomationFrames.h`: L1-30
  - `js/src/moz.build`: L106
  - `js/src/vm/SavedStacks.cpp`: L18, L618-647, L651-654, L734-735, L2182-2185
  - `js/xpconnect/src/XPCJSContext.cpp`: L11, L1248-1252
- `additions/camoucfg/DeviceProfiles.cpp`: L34-36
- `settings/camoucfg.jvv`: L371-372
- `settings/properties.json`: L149-150
- `tests/patches/android-automation.py`: new file, L1-89

## Task 16 - MediaCapabilities

`navigator.mediaCapabilities.decodingInfo()`/`encodingInfo()` report what a
phone's hardware codecs do: H.264, VP9 and AV1 up to 1920x1080 at 30 fps are
supported, smooth and powerEfficient (`mediaCapabilities:maxWidth`,
`maxHeight`, `maxFramerate`), where a software-decoding desktop reports
powerEfficient false. Larger or faster configurations and other codecs keep
Gecko's own answer.

- `patches/android/android-16-media-capabilities.patch` (patch; lines in the patched source tree):
  - `dom/media/mediacapabilities/MediaCapabilities.cpp`: L7-8, L711-762, L803-809
  - `dom/media/mediacapabilities/moz.build`: L17-19
- `additions/camoucfg/DeviceProfiles.cpp`: L197-202
- `settings/camoucfg.jvv`: L372-375
- `settings/properties.json`: L150-153
- `tests/patches/android-media-capabilities.py`: new file, L1-80

## Task 17 - WebGPU adapter

`navigator.gpu` in windows and workers (via `device:prefs`), with the Pixel
10's adapter as Chrome reports it, from a real device's WebGPU report
(`tests/patches/assets/pixel10-webgpu-report.txt`): `adapter.info` vendor
"img-tec", architecture "d-series" (`webGpu:vendor`, `architecture`, `device`,
`description`, subgroup sizes, `isFallbackAdapter`), the phone's feature list
(`webGpu:features`: ASTC and ETC2, no BC) and limits (`webGpu:limits`), and
`getPreferredCanvasFormat()` "rgba8unorm" as on Android. Gecko otherwise
reports empty adapter info and the host GPU's features and limits. Adapter
selection ignores `powerPreference`: there is one GPU.

- `patches/android/android-17-webgpu.patch` (patch; lines in the patched source tree):
  - `dom/webgpu/Adapter.cpp`: L15, L26-49, L63-65, L89-91, L103-105, L296-365, L441-455
  - `dom/webgpu/Adapter.h`: L60-65
  - `dom/webgpu/Instance.cpp`: L7-8, L32-36
  - `dom/webgpu/Instance.h`: L65-67, L75-76
  - `dom/webgpu/moz.build`: L121-123
- `additions/camoucfg/DeviceProfiles.cpp`: L149-204, L293-297
- `settings/camoucfg.jvv`: L375-387
- `settings/properties.json`: L153-162
- `tests/patches/android-webgpu.py`: new file, L1-99
- `tests/patches/assets/pixel10-webgpu-report.txt`: new file, L1-177

## Task 18 - Trusted touch events for automation's mouse input

A finger on a touchscreen fires touch events as well as pointer events. Mouse
input that automation synthesizes already reaches the page as a finger's
pointer events (Task 8); each is now followed by the matching touch event --
touchstart, touchmove while pressed, touchend -- dispatched by the browser
itself, so `isTrusted` is true, to the element the gesture started on, with
the same contact geometry. There is still only one pointer, and Gecko's
compatibility mouse events and the click follow as before.

- `patches/android/android-18-touch-trusted.patch` (patch; lines in the patched source tree):
  - `dom/events/PointerEventHandler.cpp`: L7-8, L28-31, L992-1084, L1485-1491
- `tests/patches/android-touch-trusted.py`: new file, L1-94

## Task 19 - mediump at half precision

`getShaderPrecisionFormat()` already reported fp16 for mediump; now the
pixels agree. A new ANGLE translator pass (`EmulateMediumpPrecision`, enabled
by `webGl:emulateMediumpPrecision` through a new `ShCompileOptions` bit) rounds
every mediump/lowp float result in a fragment shader to IEEE half precision,
keeping the top 10 mantissa bits (11 significant, exponent range 2^-24 to
65504): arithmetic, math built-ins, compound assignments, higher-precision
values stored into mediump variables, and reads of mediump uniforms and
inputs. Float literals feeding mediump operations are truncated at compile
time. The rounding helper is exact in fp32. highp is untouched, and so is
everything without the option.

- `patches/android/android-19-mediump-precision.patch` (patch; lines in the patched source tree):
  - `dom/canvas/WebGLShaderValidator.cpp`: L7-8, L75-79
  - `gfx/angle/checkout/include/GLSLANG/ShaderLang.h`: L421-424
  - `gfx/angle/checkout/src/compiler/translator/Compiler.cpp`: L28, L865-873
  - `gfx/angle/checkout/src/compiler/translator/tree_ops/EmulateMediumpPrecision.cpp`: L1-476
  - `gfx/angle/checkout/src/compiler/translator/tree_ops/EmulateMediumpPrecision.h`: L1-28
  - `gfx/angle/targets/translator/moz.build`: L230
- `additions/camoucfg/DeviceProfiles.cpp`: L94-95
- `settings/camoucfg.jvv`: L387-388
- `settings/properties.json`: L162-163
- `tests/patches/android-mediump-precision.py`: new file, L1-178

## Task 20 - Languages and navigator.connection

`navigator.language` "fr-FR" and `navigator.languages` ["fr-FR", "fr", "en-US",
"en"] in every realm (window, iframes, dedicated/shared/service workers), from
the profile's accept-languages list (`locale:all`), with a fr-FR Intl locale.
`navigator.connection` in windows and workers (`dom.netinfo.enabled` via
`device:prefs`) with Chrome's members, new here and exposed only on the
profile: `effectiveType` "4g", `downlink` 10, `downlinkMax` Infinity, `rtt` 50,
`saveData` false, `onchange`; `type` "wifi" (`navigator.connection.*`).

- `patches/android/android-20-languages-connection.patch` (patch; lines in the patched source tree):
  - `dom/network/Connection.cpp`: L12-16, L89-130
  - `dom/network/Connection.h`: L41-51
  - `dom/network/moz.build`: L54-56
  - `dom/webidl/NetworkInformation.webidl`: L21-28, L33-48
- `additions/camoucfg/DeviceProfiles.cpp`: L59-74, L313-314
- `settings/camoucfg.jvv`: L388-394
- `settings/properties.json`: L163-169
- `tests/patches/android-languages-connection.py`: new file, L1-133

## Task 21 - Request metadata: Accept, Sec-Fetch, Origin, form factors

Request metadata as Chrome on Android sends it. Chrome's `Accept` header for
documents and for images (`network.http.accept`, `image.http.accept` through
`device:prefs`); `Sec-CH-UA-Form-Factors: "Mobile"` joins the high-entropy
client hints (`camoucfg/UAClientHints.hpp`). Gecko's `Sec-Fetch-*` headers and
its `Origin` rules already match Chrome's -- Origin on cross-origin and
non-GET requests, none on a same-origin GET -- and the guard pins them per
request type (document, image, same-origin and cross-site fetch).
`Accept-Encoding` keeps Gecko's per-scheme values, which are Chrome's too
(br and zstd only over HTTPS).

- `additions/camoucfg/DeviceProfiles.cpp`: L313-320
- `additions/camoucfg/UAClientHints.hpp`: L108-115
- `tests/patches/android-fetch-metadata.py`: new file, L1-100

## Task 22 - performance.memory and timer resolution

`performance.memory`, Chrome's non-standard heap report, on the profile only:
a new `MemoryInfo` interface (no interface object, as in Chrome) with
`jsHeapSizeLimit` 2147483648 (`performance.memory.jsHeapSizeLimit`) and used
and total sizes taken from the SpiderMonkey GC heap, rounded up to Chromium's
100 exponential buckets (10 MB to 4 GB, three significant digits) and
refreshed at most every 20 minutes, as Chrome does without precise memory
info. `performance.now()` is pinned to 1 ms resolution in every realm
(`device:prefs`), and workers keep their `timeOrigin`.

- `patches/android/android-22-performance.patch` (patch; lines in the patched source tree):
  - `dom/performance/MemoryInfo.cpp`: L1-96
  - `dom/performance/MemoryInfo.h`: L1-58
  - `dom/performance/Performance.cpp`: L7-8, L160-163
  - `dom/performance/Performance.h`: L26, L86-88
  - `dom/performance/moz.build`: L12, L38, L70-72
  - `dom/webidl/Performance.webidl`: L60-74
- `additions/camoucfg/DeviceProfiles.cpp`: L277-279, L324-326
- `settings/camoucfg.jvv`: L394-395
- `settings/properties.json`: L169-170
- `tests/patches/android-performance.py`: new file, L1-96

## Task 23 - Canvas text metrics

Canvas text measures as it does on the phone: in Roboto (Task 12 makes it the
sans-serif and default family, so `10px sans-serif` is Roboto), unhinted --
the font instance's fontconfig pattern drops hinting on the profile, so
outlines and advances are the font's own -- and at fractional advances
(`gfx.text.subpixel-position.force-enabled` via `device:prefs`). Widths are
therefore linear in the font size and identical across repeats and between
a window and a worker's OffscreenCanvas.

- `patches/android/android-23-canvas-text.patch` (patch; lines in the patched source tree):
  - `gfx/thebes/gfxFcPlatformFontList.cpp`: L8, L981-988
- `additions/camoucfg/DeviceProfiles.cpp`: L314-315
- `tests/patches/android-canvas-text.py`: new file, L1-89

## Task 24 - Speech synthesis voices

`speechSynthesis.getVoices()` lists exactly Google's network voices, in
windows and iframes alike: "Google français" (fr-FR), "Google US English"
(en-US, the default), "Google UK English Female" (en-GB) and "Google español"
(es-ES), all `localService` false, `voiceURI` equal to the name. Host voices
(Microsoft, Apple, SAPI5, eSpeak, speech-dispatcher) are never exposed
(`voices:blockIfNotDefined`), and `speak()` completes
(`voices:fakeCompletion`). Profile values only; the voice spoofing already
existed.

- `additions/camoucfg/DeviceProfiles.cpp`: L280-299
- `tests/patches/android-voices.py`: new file, L1-91

## Task 25 - Grayscale-only text antialiasing

Android has no subpixel (LCD) text antialiasing. On the profile, a font
instance's fontconfig render pattern carries no subpixel order
(`FC_RGBA_NONE`), so neither FreeType's glyph loading nor the scaled font
used for canvas and page text picks LCD rendering: text is antialiased in
grayscale only, even on an opaque canvas. Windows builds get ClearType level
0 (grayscale) through `device:prefs`.

- `patches/android/android-25-grayscale-text.patch` (patch; lines in the patched source tree):
  - `gfx/thebes/gfxFcPlatformFontList.cpp`: L989-996
- `additions/camoucfg/DeviceProfiles.cpp`: L336-339
- `tests/patches/android-text-aa.py`: new file, L1-89

## Task 26 - Exact, reproducible canvas pixels

Chrome adds no noise to canvas readbacks. The profile switches off Gecko's
fingerprinting-protection canvas randomization in normal and private windows,
including remotely delivered overrides (`device:prefs`), so readbacks are exact
(`rgb(10,20,30)` reads back as [10, 20, 30, 255], in a worker's OffscreenCanvas
too) and reproducible: twice from one canvas, across canvases, as
`toDataURL()`, and after a reload. Profile values and a guard only.

- `additions/camoucfg/DeviceProfiles.cpp`: L353-359
- `tests/patches/android-canvas-exact.py`: new file, L1-91

## Task 27 - Storage estimate

`navigator.storage.estimate()`, in windows and workers, reports the phone's:
`quota` 34359738368 (`storage:quota`), `usage` a baseline of 24576000
(`storage:usageBase`) plus what the origin really stores -- so writing data
still moves it -- and Chrome's `usageDetails` breakdown (a new
`StorageEstimate` member, set only on the profile), which sums to `usage`.

- `patches/android/android-27-storage.patch` (patch; lines in the patched source tree):
  - `dom/quota/StorageManager.cpp`: L7-10, L484-500
  - `dom/quota/moz.build`: L195-197
  - `dom/webidl/StorageManager.webidl`: L25-27
- `additions/camoucfg/DeviceProfiles.cpp`: L277-281
- `settings/camoucfg.jvv`: L395-397
- `settings/properties.json`: L170-172
- `tests/patches/android-storage.py`: new file, L1-93

## Task 28 - requestVideoFrameCallback and AudioContext timing

`HTMLVideoElement.requestVideoFrameCallback` / `cancelVideoFrameCallback` are
Gecko's own native implementation, pinned on through `device:prefs`
(`media.rvfc.enabled`). `AudioContext` runs at 48000 Hz with Chrome on the
phone's latencies: `baseLatency` 0.005333 (new `AudioContext:baseLatency`; Gecko
otherwise always reports 0) and `outputLatency` 0.021333 through the existing
keys. OfflineAudioContext keeps the rate it is given.

- `patches/android/android-28-media-timing.patch` (patch; lines in the patched source tree):
  - `dom/media/webaudio/AudioContext.cpp`: L552-558
  - `dom/media/webaudio/AudioContext.h`: L192-196
- `additions/camoucfg/DeviceProfiles.cpp`: L277-283, L372-373
- `settings/camoucfg.jvv`: L397-398
- `settings/properties.json`: L172-173
- `tests/patches/android-media-timing.py`: new file, L1-59
