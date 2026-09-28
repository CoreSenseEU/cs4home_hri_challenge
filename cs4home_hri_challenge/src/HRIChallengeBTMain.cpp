#include <memory>
#include <string>
#include <vector>
#include <algorithm>

#include "ament_index_cpp/get_package_share_directory.hpp"
#include "behaviortree_cpp_v3/behavior_tree.h"
#include "behaviortree_cpp_v3/bt_factory.h"
#include "behaviortree_cpp_v3/utils/shared_library.h"
#include "lifecycle_msgs/msg/transition.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_cascade_lifecycle/rclcpp_cascade_lifecycle.hpp"

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  rclcpp::NodeOptions options;
  options.allow_undeclared_parameters(true);
  options.automatically_declare_parameters_from_overrides(true);

  auto node = std::make_shared<rclcpp_cascade_lifecycle::CascadeLifecycleNode>(
    "hri_challenge_bt", options);

  const std::vector<std::string> default_plugins = {
    "activation_control_bt_node",
    "init_receptionist_bt_node",
    "look_at_bt_node",
    "speak_bt_node",
    "is_detected_bt_node",
    "pan_bt_node",
    "filter_entity_bt_node",
    "extract_entity_color_bt_node",
    "listen_bt_node",
    "query_bt_node",
    "dialogConfirmation_bt_node",
    "store_detection_bt_node",
    "move_to_bt_node",
    "check_policy_bt_node",
    "store_guest_info_bt_node",
    "sleep_bt_node",
    "store_identity_vector_bt_node",
    "enable_detect_by_identity_bt_node",
    "get_attended_guest_bt_node",
    "remove_string_prefix_bt_node",
    "remove_guest_attended_bt_node",
    "remove_guest_facts_bt_node",
    "explain_bt_node",
    "set_head_joint_position_bt_node",
    "is_sittable_bt_node",
    "point_at_bt_node",
    "play_motion_predefined_bt_node",
    "set_torso_height_bt_node",
    "move_to_predefined_bt_node",
    "extract_handover_alignment_bt_node",
    "move_along_axis_bt_node",
    "move_joint_bt_node",
    "switch_yolo_model_bt_node",
    "get_model_path_bt_node",
    "get_guest_info_bt_node",
    "is_entity_moving_bt_node",
    "follow_entity_bt_node",
    "goal_publisher_bt_node",
    "add_string_suffix_bt_node",
    "set_persistent_id_bt_node",
    "runtime_trace_bt_node"};

  if (!node->has_parameter("bt_xml_file")) {
    node->declare_parameter("bt_xml_file", "hri_challenge.xml");
  }
  if (!node->has_parameter("plugins")) {
    node->declare_parameter("plugins", default_plugins);
  }
  if (!node->has_parameter("waypoints_names")) {
    node->declare_parameter(
      "waypoints_names",
      std::vector<std::string>{"entrance", "party", "guest_confirmation", "follow_ready"});
  }
  if (!node->has_parameter("waypoints.entrance")) {
    node->declare_parameter("waypoints.entrance", std::vector<double>{0.98, 6.29, 0.7});
  }
  if (!node->has_parameter("waypoints.party")) {
    node->declare_parameter("waypoints.party", std::vector<double>{1.13, 5.17, 0.92});
  }
  if (!node->has_parameter("waypoints.guest_confirmation")) {
    node->declare_parameter(
      "waypoints.guest_confirmation", std::vector<double>{1.13, 5.17, 0.92});
  }
  if (!node->has_parameter("waypoints.follow_ready")) {
    node->declare_parameter("waypoints.follow_ready", std::vector<double>{1.13, 5.17, 0.92});
  }

  std::string bt_xml_file;
  std::vector<std::string> plugins;
  node->get_parameter("bt_xml_file", bt_xml_file);
  node->get_parameter("plugins", plugins);
  if (std::find(plugins.begin(), plugins.end(), "runtime_trace_bt_node") == plugins.end()) {
    plugins.push_back("runtime_trace_bt_node");
  }

  BT::BehaviorTreeFactory factory;
  BT::SharedLibrary loader;

  for (const auto & plugin : plugins) {
    RCLCPP_INFO(node->get_logger(), "Loading BT node plugin: %s", plugin.c_str());
    factory.registerFromPlugin(loader.getOSName(plugin));
  }

  const auto pkg_path = ament_index_cpp::get_package_share_directory("cs4home_hri_challenge");
  const auto xml_file = pkg_path + "/bt_xml/" + bt_xml_file;

  auto blackboard = BT::Blackboard::create();
  blackboard->set("node", node);

  RCLCPP_INFO(node->get_logger(), "Loading behavior tree: %s", xml_file.c_str());
  auto tree = factory.createTreeFromFile(xml_file, blackboard);

  node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);
  node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE);

  rclcpp::Rate rate(30);
  auto status = BT::NodeStatus::RUNNING;

  while (rclcpp::ok() && status == BT::NodeStatus::RUNNING) {
    try {
      status = tree.rootNode()->executeTick();
    } catch (const std::exception & e) {
      RCLCPP_ERROR(node->get_logger(), "Behavior Tree tick failed: %s", e.what());
      status = BT::NodeStatus::FAILURE;
    } catch (...) {
      RCLCPP_ERROR(node->get_logger(), "Behavior Tree tick failed with an unknown exception");
      status = BT::NodeStatus::FAILURE;
    }
    rclcpp::spin_some(node->get_node_base_interface());
    rate.sleep();
  }

  tree.haltTree();

  if (rclcpp::ok()) {
    RCLCPP_INFO(
      node->get_logger(), "Behavior tree finished with status: %s",
      BT::toStr(status, true).c_str());
  }

  rclcpp::shutdown();
  return status == BT::NodeStatus::SUCCESS ? 0 : 1;
}
