/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// The profile tables live in this one translation unit, not in the header, so
// adjusting a profile rebuilds one file rather than every MaskConfig reader.

#include "DeviceProfiles.hpp"

#include "mozilla/glue/Debug.h"

namespace MaskConfig {
namespace DeviceProfiles {

// Google Pixel 10, Android 17, current stable Chrome, arm64.
//
// Each Android behaviour lands with the change that implements it, and adds
// the keys it reads here at the same time, so this table only ever describes
// what the browser actually does.
static nlohmann::json Pixel10() {
  nlohmann::json p = nlohmann::json::object();

  // Android-family behaviour that is not a single spoofed value: which APIs
  // exist, how input and sensors behave, which platform defaults apply.
  // Everything gated on "this is an Android device" reads this one key.
  p["device:android"] = true;

  // Tensor G5 is arm64: NaNs created by arithmetic carry ARM's default NaN
  // bit pattern (0x7FC00000), not x86's 0xFFC00000.
  p["cpu:armDefaultNaN"] = true;

  // Tensor G5: 8 cores (1 + 5 + 2), 12 GB of RAM. Chrome reports
  // deviceMemory rounded down to a power of two and capped at 8.
  p["navigator.platform"] = "Linux aarch64";
  p["navigator.hardwareConcurrency"] = 8;
  p["navigator.deviceMemory"] = 8;
  p["navigator.maxTouchPoints"] = 5;
  p["navigator.vendor"] = "Google Inc.";

  // Platform defaults that Gecko keys on prefs. Chrome on Android has no
  // Document Picture-in-Picture (the rest of the desktop-only APIs --
  // EyeDropper, WebHID, Window Management, Local Font Access, Window Controls
  // Overlay, File System Access pickers, Keyboard Map -- Firefox never had).
  p["device:prefs"] = {
      {"dom.documentpip.enabled", false},
  };

  return p;
}

nlohmann::json Lookup(const std::string& name) {
  nlohmann::json profile;
  if (name == "pixel10") {
    profile = Pixel10();
  } else {
    return nullptr;
  }
  // Round-trip through the parser so every value is typed exactly as the
  // same value written in CAMOU_CONFIG would be: a non-negative integer
  // literal in C++ is a signed JSON number, but parses as an unsigned one,
  // and MaskConfig::GetUint32 accepts only the latter.
  return nlohmann::json::parse(profile.dump());
}

bool Expand(nlohmann::json& config) {
  if (!config.is_object()) {
    return false;
  }
  auto selected = config.find("device:profile");
  if (selected == config.end()) {
    return false;
  }
  if (!selected->is_string()) {
    printf_stderr("ERROR: 'device:profile' must be a string\n");
    return false;
  }

  const std::string name = selected->get<std::string>();
  nlohmann::json profile = Lookup(name);
  if (profile.is_null()) {
    // Loud, because the alternative is a desktop fingerprint the caller
    // believes is a phone.
    printf_stderr("ERROR: unknown device:profile '%s'; no profile applied\n",
                  name.c_str());
    return false;
  }

  for (auto& [key, value] : profile.items()) {
    if (!config.contains(key)) {
      config[key] = value;
    }
  }
  return true;
}

}  // namespace DeviceProfiles
}  // namespace MaskConfig
