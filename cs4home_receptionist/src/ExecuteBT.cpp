// Copyright 2024 Intelligent Robotics Lab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "cs4home_core/Core.hpp"
#include "cs4home_core/macros.hpp"
#include <memory>
#include <string>

#include "ament_index_cpp/get_package_share_directory.hpp"
#include "behaviortree_cpp_v3/behavior_tree.h"
#include "behaviortree_cpp_v3/bt_factory.h"
#include "behaviortree_cpp_v3/loggers/bt_zmq_publisher.h"
#include "behaviortree_cpp_v3/utils/shared_library.h"
#include "std_msgs/msg/string.hpp"
#include "rclcpp/macros.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_cascade_lifecycle/rclcpp_cascade_lifecycle.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"

using std::placeholders::_1;
using namespace std::chrono_literals;

/**
 * @class ExecuteBT
 * @brief Core component execute the emergency action behaviour.
 */
class ExecuteBT : public cs4home_core::Core {
public:
  RCLCPP_SMART_PTR_DEFINITIONS(ExecuteBT)

  /**
   * @brief Constructs an ExecuteBT object and initializes the parent
   * lifecycle node.
   * @param parent Shared pointer to the lifecycle node managing this
   * ExecuteBT instance.
   */

  explicit ExecuteBT(rclcpp_lifecycle::LifecycleNode::SharedPtr parent)
      : Core("execute_bt", parent) {
    RCLCPP_DEBUG(parent_->get_logger(), "Core created: [ExecuteBT]");
  }

  /**
   * @brief Configures the ExecuteBT component.
   * @return True if configuration is successful.
   */
  bool configure() override {

    std::vector<std::string> plugin_list;
    parent_->get_parameter("plugin_list", plugin_list);
    parent_->get_parameter("bt_name", bt_name_);
    try {
      parent_->get_parameter("on_success_transition", on_success_transition_);
    } catch (const rclcpp::exceptions::ParameterNotDeclaredException &e) {
      RCLCPP_WARN(parent_->get_logger(),
            "Parameter 'on_success_transition' not set. If this is not the last BT be careful and set one.");
      on_success_transition_.clear();
    } catch (const std::exception &e) {
      RCLCPP_WARN(parent_->get_logger(),
            "Error getting parameter 'on_success_transition': %s", e.what());
      on_success_transition_.clear();
    }

    for (const auto &plugin : plugin_list) {
      try {
        factory_.registerFromPlugin(loader_.getOSName(plugin));
        RCLCPP_DEBUG(parent_->get_logger(), "Loaded plugin: %s", plugin.c_str());
      } catch (const std::exception &e) {
        RCLCPP_ERROR(parent_->get_logger(), "Failed to load plugin '%s': %s", plugin.c_str(), e.what());
      }
    }
    std::string pkgpath =
    ament_index_cpp::get_package_share_directory("cs4home_help_me_carry");
    std::string xml_file = pkgpath + "/bt_xml/" + bt_name_;
    
    cascade_node_ =
    std::make_shared<rclcpp_cascade_lifecycle::CascadeLifecycleNode>(
      "execute_bt_node");
    
    cascade_node_->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);
    cascade_node_->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE);
      
    blackboard_ = BT::Blackboard::create();
    blackboard_->set("node", cascade_node_);
      
    tree_ = factory_.createTreeFromFile(xml_file, blackboard_);
    
    // publisher_zmq_ = std::make_shared<BT::PublisherZMQ>(tree_, 10, 1670, 1671);
      
    RCLCPP_DEBUG(parent_->get_logger(), "[ExecuteBT] configured");
    return true;
  }

  /**
   * @brief Activates the ExecuteBT component by initializing the behavior
   * tree thread.
   *
   * @return True if activation is successful.
   */
  bool activate() override {
    bt_thread_ = std::thread(&ExecuteBT::runBehaviorTree, this);
    return true;
  }

  /**
   * @brief Deactivates the node and ensures proper shutdown of the behavior
   * tree thread.
   *
   * It ensures that any running behavior tree thread is
   * properly joined to avoid leaving background tasks running or causing race
   * conditions.
   *
   * @return True to indicate successful deactivation.
   */
  bool deactivate() override {
    if (bt_thread_.joinable()) {
      bt_thread_.join();
    }
    return true;
  }

private:
  BT::BehaviorTreeFactory factory_;
  BT::SharedLibrary loader_;
  BT::Tree tree_;
  std::string bt_name_;
  std::vector<std::string> on_success_transition_;

  BT::Blackboard::Ptr blackboard_;
  std::shared_ptr<BT::PublisherZMQ> publisher_zmq_;
  std::thread bt_thread_;
  std::shared_ptr<rclcpp_cascade_lifecycle::CascadeLifecycleNode> cascade_node_;

 void runBehaviorTree() {
    rclcpp::Rate rate(10);
    bool finish = false;

    while (!finish && rclcpp::ok()) {
      finish = tree_.rootNode()->executeTick() != BT::NodeStatus::RUNNING;
      rclcpp::spin_some(cascade_node_->get_node_base_interface());
      rate.sleep();
    }

    if (!on_success_transition_.empty()) {

      for (const auto &transition : on_success_transition_) {
        auto msg = std::make_shared<std_msgs::msg::String>();
        msg->data = transition;
        efferent_->publish(0, msg);
      }
    }
  
    RCLCPP_INFO(parent_->get_logger(),
                "Behavior Tree finished, deactivating ExecuteBt.");
    parent_->trigger_transition(
        lifecycle_msgs::msg::Transition::TRANSITION_DEACTIVATE);
  }
};

/// Registers the ExecuteBT component with the ROS 2 class loader
CS_REGISTER_COMPONENT(ExecuteBT)