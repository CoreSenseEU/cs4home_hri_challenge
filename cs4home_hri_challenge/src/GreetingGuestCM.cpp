#include "cs4home_core/CognitiveModule.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"

class GreetingGuestCM : public cs4home_core::CognitiveModule {
public:
  explicit GreetingGuestCM(
      const rclcpp::NodeOptions &options = rclcpp::NodeOptions())
      : cs4home_core::CognitiveModule("greeting_guest_cognitive_module", options) {

    this->declare_parameter<std::vector<std::string>>("plugin_list");
    this->declare_parameter<std::string>("bt_name");
    this->declare_parameter<std::vector<std::string>>("on_success_transition", {""});
    this->declare_parameter<std::vector<std::string>>("waypoints_names", std::vector<std::string>{});
    this->declare_parameter<std::vector<double>>("waypoints.entrance", {});
    this->declare_parameter<std::vector<double>>("waypoints.party", {});
    this->declare_parameter<std::vector<double>>("waypoints.guest_confirmation", {});
    RCLCPP_INFO(this->get_logger(), "GreetingGuestCM initialized");
  }
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<GreetingGuestCM>();
  rclcpp::spin(node->get_node_base_interface());
  rclcpp::shutdown();
  return 0;
}