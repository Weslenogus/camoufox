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
