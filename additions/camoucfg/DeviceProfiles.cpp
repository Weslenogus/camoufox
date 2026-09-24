/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// The profile tables live in this one translation unit, not in the header, so
// adjusting a profile rebuilds one file rather than every MaskConfig reader.

#include "DeviceProfiles.hpp"

#include "mozilla/glue/Debug.h"

#include <string>

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

  // User-Agent Client Hints of Chrome 155 on Android (155.0.8059.16, the
  // current Android release). Brands follow Chromium's GREASE algorithm for
  // major version 155: order {2, 1, 0}, "Not(A:Brand" version 24.
  // architecture and bitness are empty on a phone: Chrome only fills them in
  // for desktop and XR form factors.
  p["userAgentData:brands"] = nlohmann::json::array({
      {{"brand", "Google Chrome"}, {"version", "155"}},
      {{"brand", "Chromium"}, {"version", "155"}},
      {{"brand", "Not(A:Brand"}, {"version", "24"}},
  });
  p["userAgentData:fullVersionList"] = nlohmann::json::array({
      {{"brand", "Google Chrome"}, {"version", "155.0.8059.16"}},
      {{"brand", "Chromium"}, {"version", "155.0.8059.16"}},
      {{"brand", "Not(A:Brand"}, {"version", "24.0.0.0"}},
  });
  p["userAgentData:uaFullVersion"] = "155.0.8059.16";
  p["userAgentData:mobile"] = true;
  p["userAgentData:platform"] = "Android";
  p["userAgentData:platformVersion"] = "17.0.0";
  p["userAgentData:model"] = "Pixel 10";
  p["userAgentData:architecture"] = "";
  p["userAgentData:bitness"] = "";
  p["userAgentData:wow64"] = false;
  p["userAgentData:formFactors"] = nlohmann::json::array({"Mobile"});
  p["clientHints:sendHighEntropy"] = true;

  // WebGL as Chrome reports it on the Pixel 10's GPU, the PowerVR D-Series
  // DXT-48-1536 in Tensor G5. The extension lists are Chrome on Android's,
  // less the ones Gecko does not implement (a listed extension must be
  // obtainable). ASTC is emulated where the host GPU lacks it; S3TC, a
  // desktop format, is not offered. mediump is fp16: 15/15/10.
  p["webGl:vendor"] = "Imagination Technologies";
  p["webGl:renderer"] = "PowerVR D-Series DXT-48-1536";
  p["webGl:emulateAstc"] = true;
  p["webGl:astcProfiles"] = nlohmann::json::array({"ldr"});
  p["webGl:supportedExtensions"] = nlohmann::json::array({
      "ANGLE_instanced_arrays", "EXT_blend_minmax",
      "EXT_color_buffer_half_float", "EXT_depth_clamp", "EXT_float_blend",
      "EXT_frag_depth", "EXT_shader_texture_lod", "EXT_sRGB",
      "EXT_texture_filter_anisotropic", "OES_element_index_uint",
      "OES_fbo_render_mipmap", "OES_standard_derivatives", "OES_texture_float",
      "OES_texture_float_linear", "OES_texture_half_float",
      "OES_texture_half_float_linear", "OES_vertex_array_object",
      "WEBGL_color_buffer_float", "WEBGL_compressed_texture_astc",
      "WEBGL_compressed_texture_etc", "WEBGL_compressed_texture_etc1",
      "WEBGL_debug_renderer_info", "WEBGL_debug_shaders",
      "WEBGL_depth_texture", "WEBGL_draw_buffers", "WEBGL_lose_context",
  });
  p["webGl2:supportedExtensions"] = nlohmann::json::array({
      "EXT_color_buffer_float", "EXT_color_buffer_half_float",
      "EXT_depth_clamp", "EXT_float_blend", "EXT_texture_filter_anisotropic",
      "EXT_texture_norm16", "OES_draw_buffers_indexed",
      "OES_texture_float_linear", "WEBGL_compressed_texture_astc",
      "WEBGL_compressed_texture_etc", "WEBGL_compressed_texture_etc1",
      "WEBGL_debug_renderer_info", "WEBGL_debug_shaders", "WEBGL_lose_context",
      "WEBGL_provoking_vertex",
  });
  {
    // "shaderType,precisionType": FRAGMENT 35632 / VERTEX 35633 x
    // LOW/MEDIUM/HIGH_FLOAT 36336-36338, LOW/MEDIUM/HIGH_INT 36339-36341.
    nlohmann::json formats = nlohmann::json::object();
    for (const char* shader : {"35632", "35633"}) {
      auto set = [&](const char* type, int lo, int hi, int precision) {
        formats[std::string(shader) + "," + type] = {
            {"rangeMin", lo}, {"rangeMax", hi}, {"precision", precision}};
      };
      set("36336", 15, 15, 10);
      set("36337", 15, 15, 10);
      set("36338", 127, 127, 23);
      set("36339", 15, 15, 0);
      set("36340", 15, 15, 0);
      set("36341", 31, 30, 0);
    }
    p["webGl:shaderPrecisionFormats"] = formats;
    p["webGl2:shaderPrecisionFormats"] = formats;
  }
  p["webGl:parameters"] = {
      {"7936", "WebKit"},
      {"7937", "WebKit WebGL"},
      {"7938", "WebGL 1.0 (OpenGL ES 2.0 Chromium)"},
      {"35724", "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)"},
  };
  p["webGl2:parameters"] = {
      {"7936", "WebKit"},
      {"7937", "WebKit WebGL"},
      {"7938", "WebGL 2.0 (OpenGL ES 3.0 Chromium)"},
      {"35724", "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)"},
  };

  // Capture devices, as Chrome enumerates them on a Pixel: the Camera2
  // devices in descending id order (front first), each with its capture
  // formats and Image Capture controls. Sizes are the sensors' largest
  // YUV outputs.
  p["mediaDevices:cameras"] = nlohmann::json::array({
      {{"label", "camera2 1, facing front"},
       {"facingMode", "user"},
       {"width", 3648},
       {"height", 2736},
       {"frameRate", 30},
       {"focusMode", {"continuous", "single-shot", "manual"}},
       {"exposureMode", {"continuous", "manual"}}},
      {{"label", "camera2 0, facing back"},
       {"facingMode", "environment"},
       {"width", 4080},
       {"height", 3072},
       {"frameRate", 30},
       {"zoom", {{"min", 1}, {"max", 8}, {"step", 0.1}}},
       {"torch", true},
       {"focusMode", {"continuous", "single-shot", "manual"}},
       {"exposureMode", {"continuous", "manual"}}},
  });

  // Screen: 1080x2424 physical at DPR 2.625 is 412x915 CSS px; the status
  // bar and gesture navigation take 42 px, leaving 412x873 for the page.
  // Portrait-primary, 24 px safe-area insets top and bottom.
  p["screen.width"] = 412;
  p["screen.height"] = 915;
  p["screen.availWidth"] = 412;
  p["screen.availHeight"] = 873;
  p["screen.availTop"] = 0;
  p["screen.availLeft"] = 0;
  p["screen.colorDepth"] = 24;
  p["screen.pixelDepth"] = 24;
  p["window.devicePixelRatio"] = 2.625;
  p["window.innerWidth"] = 412;
  p["window.innerHeight"] = 873;
  p["window.outerWidth"] = 412;
  p["window.outerHeight"] = 915;
  p["window.screenX"] = 0;
  p["window.screenY"] = 0;
  p["screen.orientation.type"] = "portrait-primary";
  p["screen.orientation.angle"] = 0;
  p["screen.safeAreaInsetTop"] = 24;
  p["screen.safeAreaInsetBottom"] = 24;
  p["screen.safeAreaInsetLeft"] = 0;
  p["screen.safeAreaInsetRight"] = 0;

  // Battery: 78%, on battery, four hours left (chargingTime is then
  // Infinity, as the Battery Status API specifies).
  p["battery:level"] = 0.78;
  p["battery:charging"] = false;
  p["battery:dischargingTime"] = 14400.0;

  // Platform defaults that Gecko keys on prefs. Chrome on Android has no
  // Document Picture-in-Picture (the rest of the desktop-only APIs --
  // EyeDropper, WebHID, Window Management, Local Font Access, Window Controls
  // Overlay, File System Access pickers, Keyboard Map -- Firefox never had).
  p["device:prefs"] = {
      {"dom.documentpip.enabled", false},
      // Android builds keep the legacy touch APIs ('ontouchstart' in window,
      // document.createTouch), as Chrome on Android does.
      {"dom.w3c_touch_events.legacy_apis.enabled", true},
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
