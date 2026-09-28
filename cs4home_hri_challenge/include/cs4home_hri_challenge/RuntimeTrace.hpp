#ifndef CS4HOME_HRI_CHALLENGE__RUNTIME_TRACE_HPP_
#define CS4HOME_HRI_CHALLENGE__RUNTIME_TRACE_HPP_

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>

#include "rclcpp/rclcpp.hpp"

namespace cs4home_hri_challenge
{

class RuntimeTrace
{
public:
  static std::string capability_from_module(const std::string & module_name)
  {
    static const std::unordered_map<std::string, std::string> names = {
      {"greeting_guest_cognitive_module", "Greeting"},
      {"find_seat_cognitive_module", "Find Seat"},
      {"describe_person_cognitive_module", "Describe / Invite"},
      {"introduce_guest_cognitive_module", "Introduce Guest"},
      {"grab_bag_cognitive_module", "Grab Bag"},
      {"transport_bag_cognitive_module", "Transport Bag"},
      {"recovery_cognitive_module", "Recovery"},
    };

    auto it = names.find(module_name);
    if (it != names.end()) {
      return it->second;
    }
    return module_name;
  }

  static void record(
    const std::string & architecture,
    const std::string & flow_name,
    const std::string & capability,
    const std::string & module_name,
    const std::string & event,
    const rclcpp::Time & stamp,
    const std::string & success = "",
    const std::string & details = "")
  {
    std::lock_guard<std::mutex> lock(mutex());
    const auto path = event_csv_path();
    const bool write_header = !std::filesystem::exists(path) || std::filesystem::file_size(path) == 0;

    std::ofstream out(path, std::ios::app);
    if (!out.is_open()) {
      return;
    }

    if (write_header) {
      out << "run_id,architecture,flow_name,capability,module_name,event,stamp_ns,success,details\n";
    }

    out << csv(run_id()) << ','
        << csv(architecture) << ','
        << csv(flow_name) << ','
        << csv(capability) << ','
        << csv(module_name) << ','
        << csv(event) << ','
        << stamp.nanoseconds() << ','
        << csv(success) << ','
        << csv(details) << '\n';
  }

  static std::string run_id()
  {
    const char * value = std::getenv("HRI_RUNTIME_EVAL_RUN_ID");
    if (value && *value) {
      return value;
    }
    return "run_0";
  }

  static std::string architecture_from_env(const std::string & fallback)
  {
    const char * value = std::getenv("HRI_RUNTIME_EVAL_ARCHITECTURE");
    if (value && *value) {
      return value;
    }
    return fallback;
  }

  static std::filesystem::path event_csv_path()
  {
    const char * dir_value = std::getenv("HRI_RUNTIME_EVAL_DIR");
    std::filesystem::path dir = (dir_value && *dir_value) ? dir_value : "data/hri_runtime_eval";
    std::filesystem::create_directories(dir);
    return dir / "runtime_events.csv";
  }

private:
  static std::mutex & mutex()
  {
    static std::mutex m;
    return m;
  }

  static std::string csv(const std::string & value)
  {
    bool quote = false;
    for (char c : value) {
      if (c == ',' || c == '"' || c == '\n' || c == '\r') {
        quote = true;
        break;
      }
    }
    if (!quote) {
      return value;
    }
    std::ostringstream out;
    out << '"';
    for (char c : value) {
      if (c == '"') {
        out << "\"\"";
      } else {
        out << c;
      }
    }
    out << '"';
    return out.str();
  }
};

}  // namespace cs4home_hri_challenge

#endif  // CS4HOME_HRI_CHALLENGE__RUNTIME_TRACE_HPP_
