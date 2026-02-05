////////////////////////////////////////////////////////////////////
// Copyright 2025 IMR Robotics & Automation Group
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//See the License for the specific language governing permissions and
// limitations under the License.
////////////////////////////////////////////////////////////////////

#include "cs4home_core/Master.hpp"
#include "cs4home_core/Flow.hpp"
#include "lifecycle_msgs/srv/change_state.hpp"
#include "lifecycle_msgs/srv/get_state.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "std_msgs/msg/string.hpp"
#include "std_msgs/msg/bool.hpp"
#include <map>
#include <memory>
#include <string>
#include <vector>

using namespace std::chrono_literals;
using namespace std::placeholders;

// Simple flow configuration - just lists modules and initial states
struct FlowConfig {
  std::vector<std::string> initial_states;  // Modules to activate at startup
  std::vector<std::string> all_modules;     // All modules in this flow
};

class HRIChallengeMaster : public cs4home_core::Master {
public:
  explicit HRIChallengeMaster(
      const rclcpp::NodeOptions &options = rclcpp::NodeOptions())
      : cs4home_core::Master("hri_challenge_master", options) {
    
    RCLCPP_INFO(this->get_logger(), "HRIChallengeMaster initialized");
    declare_parameter<std::vector<std::string>>("on_startup", {});
  }

  using CallbackReturnT = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;

  CallbackReturnT on_configure(const rclcpp_lifecycle::State &state) override {
    RCLCPP_INFO(this->get_logger(), "=== HRI CHALLENGE MASTER CONFIGURE ===");

  
    // Create single callback group for all lifecycle service calls
    lifecycle_callback_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);
    
    // Create single executor for the lifecycle callback group
    lifecycle_executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    lifecycle_executor_->add_callback_group(lifecycle_callback_group_, 
                                            this->get_node_base_interface());
    
    parse_flow_configuration();
    
    configure_nodes();
    
    setup_sequential_state_machine();
    
    
    RCLCPP_INFO(this->get_logger(), "Master configured with %zu modules, %zu initial states",
                flow_config_.all_modules.size(), flow_config_.initial_states.size());

    
    return CallbackReturnT::SUCCESS;
  }

  CallbackReturnT on_activate(const rclcpp_lifecycle::State &state) override {

    // Activate all initial states defined in the flow
    if (!flow_config_.initial_states.empty()) {
      RCLCPP_INFO(this->get_logger(), "Activating %zu initial state(s)...", 
                  flow_config_.initial_states.size());
      
      for (const auto &module_name : flow_config_.initial_states) {
        RCLCPP_INFO(this->get_logger(), "  → Starting initial module: %s", module_name.c_str());
        activate_module(module_name);
      }
    } else {
      RCLCPP_WARN(this->get_logger(), "No initial states defined in flow!");
    }

    RCLCPP_INFO(this->get_logger(), "=== HRI CHALLENGE MASTER ACTIVE ===");
    return CallbackReturnT::SUCCESS;
  }

  CallbackReturnT on_deactivate(const rclcpp_lifecycle::State &state) override {
    RCLCPP_INFO(this->get_logger(), "=== MASTER DEACTIVATE ===");
    
    // Deactivate all modules
    for (const auto& module_name : flow_config_.all_modules) {
      deactivate_module(module_name);
    }
    
    return cs4home_core::Master::on_deactivate(state);
  }

  CallbackReturnT on_cleanup(const rclcpp_lifecycle::State &state) override {
    RCLCPP_INFO(this->get_logger(), "=== MASTER CLEANUP ===");
    
    // Stop the lifecycle executor
    if (lifecycle_executor_) {
      lifecycle_executor_->cancel();
    }
    
    if (lifecycle_executor_thread_.joinable()) {
      lifecycle_executor_thread_.join();
    }
    
    lifecycle_clients_.clear();
    get_state_clients_.clear();
    
    return cs4home_core::Master::on_cleanup(state);
  }

private:
  // Flow configuration
  FlowConfig flow_config_;
  
  // Single callback group for all lifecycle service calls (change_state and get_state)
  rclcpp::CallbackGroup::SharedPtr lifecycle_callback_group_;
  
  // Single executor for the lifecycle callback group
  rclcpp::executors::SingleThreadedExecutor::SharedPtr lifecycle_executor_;
  std::thread lifecycle_executor_thread_;
  
  // Lifecycle clients for each cognitive module
  std::map<std::string, rclcpp::Client<lifecycle_msgs::srv::ChangeState>::SharedPtr> lifecycle_clients_;
  std::map<std::string, rclcpp::Client<lifecycle_msgs::srv::GetState>::SharedPtr> get_state_clients_;
  
  // Completion subscribers for sequential state machine
  std::map<std::string, rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr> completion_subscribers_;
  
  // Current module index in the sequence
  size_t current_module_index_ = 0;

  void parse_flow_configuration() {
    RCLCPP_INFO(this->get_logger(), "Parsing flow configuration...");
    
    // Get flow names
    std::vector<std::string> flow_names;
    if (!this->get_parameter("flows", flow_names) || flow_names.empty()) {
      RCLCPP_ERROR(this->get_logger(), "No flows parameter defined!");
      return;
    }
    
    std::string flow_name = flow_names[0];  // Use first flow
    RCLCPP_INFO(this->get_logger(), "Loading flow: %s", flow_name.c_str());
    
    // Declare the flow parameter before getting it
    this->declare_parameter<std::vector<std::string>>(flow_name, {});
    
    // Get initial states from on_startup parameter
    if (!this->get_parameter("on_startup", flow_config_.initial_states)) {
      RCLCPP_WARN(this->get_logger(), "No on_startup parameter defined!");
    } else {
      RCLCPP_INFO(this->get_logger(), "Found %zu initial state(s) from on_startup", 
                  flow_config_.initial_states.size());
    }
    
    // Get all modules in the flow (just the list)
    if (this->get_parameter(flow_name, flow_config_.all_modules)) {
      RCLCPP_INFO(this->get_logger(), "Found %zu modules in flow", flow_config_.all_modules.size());
      for (const auto& module : flow_config_.all_modules) {
        RCLCPP_INFO(this->get_logger(), "  - %s", module.c_str());
      }
    }
  }

  void configure_nodes() {
    if (flow_config_.all_modules.empty()) {
      RCLCPP_WARN(this->get_logger(), "No modules configured in flow!");
      return;
    }

    RCLCPP_INFO(this->get_logger(), "Configuring lifecycle clients for %zu modules...", 
                flow_config_.all_modules.size());

    // Create lifecycle clients for all modules
    for (const auto& module_name : flow_config_.all_modules) {
      create_lifecycle_client(module_name);
      create_get_state_client(module_name);
    }

    rclcpp::sleep_for(500ms);

    for (const auto& [module_name, client] : lifecycle_clients_) {
      if (!client->wait_for_service(1s)) {
        RCLCPP_WARN(this->get_logger(), "Lifecycle service for %s not available", 
                    module_name.c_str());
        continue;
      }
      configure_module(module_name);
    }
  }

  void create_lifecycle_client(const std::string& module_name) {
    std::string service_name = "/" + module_name + "/change_state";
    lifecycle_clients_[module_name] = 
      this->create_client<lifecycle_msgs::srv::ChangeState>(
        service_name, rmw_qos_profile_services_default, lifecycle_callback_group_);
    
    RCLCPP_DEBUG(this->get_logger(), "Created change_state client for %s", module_name.c_str());
  }

  void create_get_state_client(const std::string& module_name) {
    std::string service_name = "/" + module_name + "/get_state";
    get_state_clients_[module_name] = 
      this->create_client<lifecycle_msgs::srv::GetState>(
        service_name, rmw_qos_profile_services_default, lifecycle_callback_group_);
    
    RCLCPP_DEBUG(this->get_logger(), "Created get_state client for %s", module_name.c_str());
  }

  // Helper method to get the current state of a module
  std::string get_module_state(const std::string& module_name) {
    auto it = get_state_clients_.find(module_name);
    if (it == get_state_clients_.end()) {
      RCLCPP_ERROR(this->get_logger(), "No get_state client for module: %s", module_name.c_str());
      return "unknown";
    }

    auto client = it->second;
    
    if (!client->wait_for_service(100ms)) {
      RCLCPP_WARN(this->get_logger(), "get_state service not available for: %s", 
                   module_name.c_str());
      return "unavailable";
    }

    auto req = std::make_shared<lifecycle_msgs::srv::GetState::Request>();
    auto future = client->async_send_request(req);
    
    if (lifecycle_executor_->spin_until_future_complete(future, 500ms) ==
        rclcpp::FutureReturnCode::SUCCESS) {
      auto response = future.get();
      RCLCPP_DEBUG(this->get_logger(), "Module %s is in state: %s (id: %d)", 
                   module_name.c_str(), response->current_state.label.c_str(), 
                   response->current_state.id);
      return response->current_state.label;
    } else {
      RCLCPP_WARN(this->get_logger(), "Failed to get state for: %s", module_name.c_str());
      return "timeout";
    }
  }

  void configure_module(const std::string& module_name) {
    auto it = lifecycle_clients_.find(module_name);
    if (it == lifecycle_clients_.end()) {
      RCLCPP_ERROR(this->get_logger(), "No lifecycle client for module: %s", module_name.c_str());
      return;
    }

    auto client = it->second;
    
    if (!client->wait_for_service(100ms)) {
      RCLCPP_ERROR(this->get_logger(), "Lifecycle service not available for: %s", 
                   module_name.c_str());
      return;
    }

    auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
    req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE;

    RCLCPP_INFO(this->get_logger(), "Configuring module: %s", module_name.c_str());
    auto future = client->async_send_request(req);
  }

  // Helper method to activate any module (you'll call this from your custom logic)
  void activate_module(const std::string& module_name) {
    auto it = lifecycle_clients_.find(module_name);
    if (it == lifecycle_clients_.end()) {
      RCLCPP_ERROR(this->get_logger(), "No lifecycle client for module: %s", module_name.c_str());
      return;
    }

    auto client = it->second;
    
    if (!client->wait_for_service(100ms)) {
      RCLCPP_ERROR(this->get_logger(), "Lifecycle service not available for: %s", 
                   module_name.c_str());
      return;
    }

    // Check current state before activating
    std::string current_state = get_module_state(module_name);
    RCLCPP_INFO(this->get_logger(), "Module Current state is  %s", 
            current_state.c_str());
    
    if (current_state == "active") {
      RCLCPP_INFO(this->get_logger(), "Module %s is already active, skipping activation", 
                  module_name.c_str());
      return;
    }
    
    if (current_state != "inactive") {
      RCLCPP_WARN(this->get_logger(), "Module %s is in state '%s', cannot activate. Expected 'inactive'", 
                  module_name.c_str(), current_state.c_str());
      return;
    }

    auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
    req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE;

    RCLCPP_INFO(this->get_logger(), "Activating module: %s", module_name.c_str());
    
    auto future = client->async_send_request(req);
  }

  // Helper method to deactivate any module
  void deactivate_module(const std::string& module_name) {
    auto it = lifecycle_clients_.find(module_name);
    if (it == lifecycle_clients_.end()) {
      return;
    }

    auto client = it->second;
    
    if (!client->wait_for_service(100ms)) {
      return;
    }

    auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
    req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_DEACTIVATE;

    RCLCPP_DEBUG(this->get_logger(), "Deactivating: %s", module_name.c_str());
    auto future = client->async_send_request(req);
  }

  // Helper method to cleanup any module
  void cleanup_module(const std::string& module_name) {
    auto it = lifecycle_clients_.find(module_name);
    if (it == lifecycle_clients_.end()) {
      RCLCPP_ERROR(this->get_logger(), "No lifecycle client for module: %s", module_name.c_str());
      return;
    }

    auto client = it->second;
    
    if (!client->wait_for_service(100ms)) {
      RCLCPP_ERROR(this->get_logger(), "Lifecycle service not available for: %s", 
                   module_name.c_str());
      return;
    }

    auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
    req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_CLEANUP;

    RCLCPP_INFO(this->get_logger(), "Cleaning up module: %s", module_name.c_str());
    auto future = client->async_send_request(req);
  }

  void setup_sequential_state_machine() {
    RCLCPP_INFO(this->get_logger(), "Setting up sequential state machine for %zu modules", 
                flow_config_.all_modules.size());
    
    for (const auto& module_name : flow_config_.all_modules) {
      std::string topic_name = "/" + module_name + "/completion";
      
      auto callback = [this, module_name](const std_msgs::msg::Bool::SharedPtr msg) {
        this->handle_module_completion(module_name, msg->data);
      };
      
      completion_subscribers_[module_name] = 
        this->create_subscription<std_msgs::msg::Bool>(topic_name, 10, callback);
      
      RCLCPP_INFO(this->get_logger(), "  Subscribed to: %s", topic_name.c_str());
    }
  }

  void handle_module_completion(const std::string& module_name, bool success) {
    RCLCPP_INFO(this->get_logger(), "Module '%s' completed with status: %s", 
                module_name.c_str(), success ? "SUCCESS" : "FAILURE");
    
    // Just deactivate the module - keep it configured and ready for next activation
    deactivate_module(module_name);
    
    // Find current module index
    auto it = std::find(flow_config_.all_modules.begin(), 
                       flow_config_.all_modules.end(), 
                       module_name);
    
    if (it == flow_config_.all_modules.end()) {
      RCLCPP_ERROR(this->get_logger(), "Module %s not found in flow!", module_name.c_str());
      return;
    }
    
    size_t current_idx = std::distance(flow_config_.all_modules.begin(), it);
    
    if (success) {
      size_t next_idx = (current_idx + 1) % flow_config_.all_modules.size();
      std::string next_module = flow_config_.all_modules[next_idx];
      
      RCLCPP_INFO(this->get_logger(), "SUCCESS → Transitioning to next module: %s", 
                  next_module.c_str());
      activate_module(next_module);
    } else {
      // FAILURE: Retry the same module
      RCLCPP_WARN(this->get_logger(), "FAILURE → Retrying module: %s", module_name.c_str());
      activate_module(module_name);
    }
  }

};

int main(int argc, char **argv) {
  RCLCPP_INFO(rclcpp::get_logger("main"), "=== STARTING HRI CHALLENGE MASTER ===");
  rclcpp::init(argc, argv);
  
  rclcpp::NodeOptions options;
  auto node = std::make_shared<HRIChallengeMaster>(options);
  
  rclcpp::spin(node->get_node_base_interface());
  rclcpp::shutdown();
  return 0;
}