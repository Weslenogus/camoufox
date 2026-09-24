/*
User-Agent Client Hints, read from CAMOU_CONFIG.

One source for both surfaces a page can compare: navigator.userAgentData
(dom/base/NavigatorUAData.cpp) and the Sec-CH-UA request headers
(nsHttpHandler::AddStandardRequestHeaders). Everything is keyed off
"userAgentData:*"; with no "userAgentData:brands" there are no client hints at
all, which is Firefox's own behaviour.
*/

#pragma once

#include "MaskConfig.hpp"

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

namespace MaskConfig {
namespace ClientHints {

// (brand, version) pairs, in the order they were configured.
using BrandList = std::vector<std::pair<std::string, std::string>>;

inline BrandList GetBrandList(const std::string& key) {
  BrandList out;
  const auto& data = GetJson();
  if (!data.is_object()) {
    return out;
  }
  auto list = data.find(key);
  if (list == data.end() || !list->is_array()) {
    return out;
  }
  for (const auto& item : *list) {
    if (!item.is_object()) {
      continue;
    }
    auto brand = item.find("brand");
    auto version = item.find("version");
    if (brand == item.end() || version == item.end() || !brand->is_string() ||
        !version->is_string()) {
      continue;
    }
    out.emplace_back(brand->get<std::string>(), version->get<std::string>());
  }
  return out;
}

// Whether client hints exist at all. CAMOU_CONFIG never changes after
// startup, so the answer is cached; safe on any thread.
inline bool Enabled() {
  static const bool enabled = !GetBrandList("userAgentData:brands").empty();
  return enabled;
}

// RFC 8941 list of strings with a "v" parameter:
//   "Google Chrome";v="155", "Chromium";v="155", "Not(A:Brand";v="24"
inline std::string SerializeBrandList(const BrandList& brands) {
  std::string out;
  for (const auto& [brand, version] : brands) {
    if (!out.empty()) {
      out += ", ";
    }
    out += "\"" + brand + "\";v=\"" + version + "\"";
  }
  return out;
}

inline std::string Quoted(const std::string& value) {
  return "\"" + value + "\"";
}

// The Sec-CH-UA request headers, sorted by name as Chrome sends them. The
// three low-entropy hints always go out; the high-entropy ones only when
// "clientHints:sendHighEntropy" is set -- Chrome itself sends those only
// after a server opts in with Accept-CH.
inline const std::vector<std::pair<std::string, std::string>>&
RequestHeaders() {
  static const auto headers = [] {
    std::vector<std::pair<std::string, std::string>> h;
    if (!Enabled()) {
      return h;
    }
    h.emplace_back("Sec-CH-UA",
                   SerializeBrandList(GetBrandList("userAgentData:brands")));
    h.emplace_back("Sec-CH-UA-Mobile",
                   CheckBool("userAgentData:mobile") ? "?1" : "?0");
    h.emplace_back("Sec-CH-UA-Platform",
                   Quoted(GetString("userAgentData:platform").value_or("")));
    if (CheckBool("clientHints:sendHighEntropy")) {
      const std::pair<const char*, const char*> highEntropy[] = {
          {"Sec-CH-UA-Arch", "userAgentData:architecture"},
          {"Sec-CH-UA-Bitness", "userAgentData:bitness"},
          {"Sec-CH-UA-Model", "userAgentData:model"},
          {"Sec-CH-UA-Platform-Version", "userAgentData:platformVersion"},
      };
      for (const auto& [header, key] : highEntropy) {
        if (auto value = GetString(key)) {
          h.emplace_back(header, Quoted(*value));
        }
      }
      BrandList full = GetBrandList("userAgentData:fullVersionList");
      if (!full.empty()) {
        h.emplace_back("Sec-CH-UA-Full-Version-List", SerializeBrandList(full));
      }
      // RFC 8941 list of strings: "Mobile"
      std::string formFactors;
      for (const auto& factor : GetStringList("userAgentData:formFactors")) {
        formFactors += (formFactors.empty() ? "" : ", ") + Quoted(factor);
      }
      if (!formFactors.empty()) {
        h.emplace_back("Sec-CH-UA-Form-Factors", formFactors);
      }
    }
    std::stable_sort(h.begin(), h.end(), [](const auto& a, const auto& b) {
      return a.first < b.first;
    });
    return h;
  }();
  return headers;
}

}  // namespace ClientHints
}  // namespace MaskConfig
