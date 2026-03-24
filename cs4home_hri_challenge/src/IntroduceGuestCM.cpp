#include "cs4home_core/CognitiveModule.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"

class IntroduceGuestCM : public cs4home_core::CognitiveModule {
public:
  explicit IntroduceGuestCM(
      const rclcpp::NodeOptions &options = rclcpp::NodeOptions())
      : cs4home_core::CognitiveModule("introduce_guest_cognitive_mmodule", options) {

    this->declare_parameter<std::vector<std::string>>("plugin_list");
    this->declare_parameter<std::string>("bt_name");
    this->declare_parameter<std::vector<std::string>>("on_success_transition", {""});
    this->declare_parameter<std::vector<std::string>>("waypoints_names", std::vector<std::string>{});
    this->declare_parameter<std::vector<double>>("waypoints.entrance", {});
    this->declare_parameter<std::vector<double>>("waypoints.party", {});
    this->declare_parameter<std::vector<double>>("waypoints.guest_confirmation", {});
    this->declare_parameter<std::vector<double>>("waypoints.follow_ready", {});
    RCLCPP_INFO(this->get_logger(), "IntroduceGuestCM initialized");
  }
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<IntroduceGuestCM>();
  rclcpp::spin(node->get_node_base_interface());
  rclcpp::shutdown();
  return 0;
}