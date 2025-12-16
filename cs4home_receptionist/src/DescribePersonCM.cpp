#include "cs4home_core/CognitiveModule.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"

class DescribePersonCM : public cs4home_core::CognitiveModule {
public:
  explicit DescribePersonCM(
      const rclcpp::NodeOptions &options = rclcpp::NodeOptions())
      : cs4home_core::CognitiveModule("describe_person_cognitive_mmodule", options) {

    this->declare_parameter<std::vector<std::string>>("plugin_list");
    this->declare_parameter<std::string>("bt_name");
    this->declare_parameter<std::vector<std::string>>("on_success_transition", {""});
    this->declare_parameter<std::vector<std::string>>("waypoints_names", std::vector<std::string>{});
    RCLCPP_INFO(this->get_logger(), "DescribePersonCM initialized");
  }
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<DescribePersonCM>();
  rclcpp::spin(node->get_node_base_interface());
  rclcpp::shutdown();
  return 0;
}