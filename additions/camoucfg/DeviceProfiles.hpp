/*
Built-in device profiles.

A profile is a named bundle of CAMOU_CONFIG keys. Selecting one with

    {"device:profile": "pixel10"}

fills in every key the profile defines that the config does not already set.
Explicit keys always win, so a profile can be adjusted one value at a time
("device:profile" plus "userAgentData:model" gives the same phone reporting a
different model).

Expansion happens once, inside MaskConfig::GetJson(), before any reader sees
the config. Every existing consumer -- navigator, screen, WebGL, headers,
battery -- therefore picks a profile up without knowing profiles exist, and the
expanded config is identical in every process that inherits CAMOU_CONFIG.

With no "device:profile" key nothing here runs and the config is untouched, so
desktop fingerprints are unaffected by the existence of this file.
*/

#pragma once

#include "json.hpp"

#include <string>

namespace MaskConfig {
namespace DeviceProfiles {

// Returns the profile for `name`, or null for an unknown name.
nlohmann::json Lookup(const std::string& name);

// Merges the selected profile beneath the explicit keys in `config`.
// Returns true when a profile was applied.
bool Expand(nlohmann::json& config);

}  // namespace DeviceProfiles
}  // namespace MaskConfig
