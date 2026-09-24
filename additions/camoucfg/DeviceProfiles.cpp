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

  return p;
}

nlohmann::json Lookup(const std::string& name) {
  if (name == "pixel10") {
    return Pixel10();
  }
  return nullptr;
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
