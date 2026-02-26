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
#include "std_msgs/msg/bool.hpp"
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
    RCLCPP_INFO(parent_->get_logger(), "Core created: [ExecuteBT]");
  }

  /**
   * @brief Configures the ExecuteBT component.
   * @return True if configuration is successful.
   */
  bool configure() override {
    RCLCPP_INFO(parent_->get_logger(), "Configuring CORE!");

    std::vector<std::string> plugin_list;
    parent_->get_parameter("plugin_list", plugin_list);
    parent_->get_parameter("bt_name", bt_name_);

    for (const auto &plugin : plugin_list) {
      try {
        RCLCPP_INFO(parent_->get_logger(), "Loading plugin: %s", plugin.c_str());
        factory_.registerFromPlugin(loader_.getOSName(plugin));
      } catch (const std::exception &e) {
        RCLCPP_ERROR(parent_->get_logger(), "Failed to load plugin '%s': %s", plugin.c_str(), e.what());
      }
    }

    std::string pkgpath = ament_index_cpp::get_package_share_directory("cs4home_hri_challenge");
    xml_file_ = pkgpath + "/bt_xml/" + bt_name_;
    RCLCPP_INFO(parent_->get_logger(), "Behavior Tree XML file path: %s", xml_file_.c_str());

    // Create a new context for the cascade node to make it truly independent
    auto context = rclcpp::Context::make_shared();
    context->init(0, nullptr);

    rclcpp::NodeOptions options;
    options.context(context);
    
    // 2) Copy ALL params from parent_ to cascade_node_ (BT node)
    auto param_names = parent_->list_parameters({}, 0 /* depth recursive */).names;
    auto parent_params = parent_->get_parameters(param_names);
    options.parameter_overrides(parent_params);
    
    std::string bt_node_name = std::string(parent_->get_name()) + "_bt_node";
    cascade_node_ = std::make_shared<rclcpp_cascade_lifecycle::CascadeLifecycleNode>(
      bt_node_name, options);

    // 1) Configure first (so internal setup happens first)
    cascade_node_->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);

    // 3) Activate after params are available
    cascade_node_->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE);

    // blackboard_ = BT::Blackboard::create();
    // blackboard_->set("node", cascade_node_);

    // tree_ = factory_.createTreeFromFile(xml_file, blackboard_);

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
    stop_requested_.store(false);
    blackboard_ = BT::Blackboard::create();
    blackboard_->set("node", cascade_node_);
    tree_ = factory_.createTreeFromFile(xml_file_, blackboard_);
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
    stop_requested_.store(true);
    tree_.haltTree();
    if (bt_thread_.joinable()) {
      bt_thread_.join();
    }
    tree_ = BT::Tree();
    blackboard_.reset();
    return true;
  }

private:
  BT::BehaviorTreeFactory factory_;
  BT::SharedLibrary loader_;
  BT::Tree tree_;
  std::string bt_name_;
  std::string xml_file_;

  BT::Blackboard::Ptr blackboard_;
  std::shared_ptr<BT::PublisherZMQ> publisher_zmq_;
  std::thread bt_thread_;
  std::shared_ptr<rclcpp_cascade_lifecycle::CascadeLifecycleNode> cascade_node_;
  std::atomic_bool stop_requested_{false};

 void runBehaviorTree() {
    tree_.haltTree();
    rclcpp::Rate rate(30);
    bool finish = false;

    while (!stop_requested_.load() && !finish && rclcpp::ok()) {
      finish = tree_.rootNode()->executeTick() != BT::NodeStatus::RUNNING;
      rclcpp::spin_some(cascade_node_->get_node_base_interface());
      rate.sleep();
    }

    if (stop_requested_.load()) {
      return;
    }

    auto msg = std::make_shared<std_msgs::msg::Bool>();
    msg->data = 1;
    efferent_->publish(0, msg);
    
  
  }
};

/// Registers the ExecuteBT component with the ROS 2 class loader
CS_REGISTER_COMPONENT(ExecuteBT)