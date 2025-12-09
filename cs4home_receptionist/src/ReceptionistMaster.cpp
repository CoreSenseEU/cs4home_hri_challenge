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
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "std_msgs/msg/string.hpp"
#include <map>
#include <memory>

using namespace std::chrono_literals;
using namespace std::placeholders;

class ReceptionistMaster : public cs4home_core::Master {
public:
  explicit ReceptionistMaster(
      const rclcpp::NodeOptions &options = rclcpp::NodeOptions())
      : cs4home_core::Master("receptionist_master", options) {

    this->declare_parameter<std::vector<std::string>>(
      "on_startup"
    );
    RCLCPP_INFO(this->get_logger(), " ReceptionistMaster initialized");
  }

  using CallbackReturnT = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;

  CallbackReturnT on_configure(const rclcpp_lifecycle::State &state) override {
    
    RCLCPP_INFO(this->get_logger(), "=== NAVIGATION COGNITIVE MASTER CONFIGURE ===");

    get_parameter("on_startup", on_startup_nodes_);
    auto result = cs4home_core::Master::on_configure(state);
    
    if (result == CallbackReturnT::SUCCESS) {
      transition_sub_ = this->create_subscription<std_msgs::msg::String>(
          "module_to_activate", 10,
          std::bind(&ReceptionistMaster::activate_module, this, std::placeholders::_1));
      configure_nodes();
      
      RCLCPP_INFO(this->get_logger(), " Master configured - ready to manage flows");
    }
    
    return CallbackReturnT::SUCCESS;
  }

  CallbackReturnT on_activate(const rclcpp_lifecycle::State &state) override {
    
    auto result = cs4home_core::Master::on_activate(state);

    if (!on_startup_nodes_.empty()) {
      RCLCPP_INFO(this->get_logger(), "Activating %zu startup nodes...", on_startup_nodes_.size());
      for (const auto &node_name : on_startup_nodes_) {
        RCLCPP_INFO(this->get_logger(), "  → Activating startup node: %s", node_name.c_str());
        activate_node(node_name);
      }
    }

    is_activated_ = true;
    RCLCPP_INFO(this->get_logger(), "=== NAVIGATION COGNITIVE MASTER ACTIVATE ===");
    return result;
  }

  CallbackReturnT on_deactivate(const rclcpp_lifecycle::State &state) override {
    RCLCPP_INFO(this->get_logger(), "=== MASTER DEACTIVATE ===");
    
    if (management_timer_) {
      management_timer_->cancel();
      management_timer_.reset();
    }
    
    return cs4home_core::Master::on_deactivate(state);
  }

  CallbackReturnT on_cleanup(const rclcpp_lifecycle::State &state) override {
    RCLCPP_INFO(this->get_logger(), "===  MASTER CLEANUP ===");
    
    lifecycle_clients_.clear();
    
    return cs4home_core::Master::on_cleanup(state);
  }

private:
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr transition_sub_;
  bool is_activated_;
  std::vector<std::string> on_startup_nodes_;
  
  std::map<std::string, rclcpp::Client<lifecycle_msgs::srv::ChangeState>::SharedPtr> lifecycle_clients_;
  rclcpp::TimerBase::SharedPtr management_timer_;
  
  void activate_module(const std_msgs::msg::String::SharedPtr msg) {
    auto next_node_ = msg->data;
    
    RCLCPP_INFO(this->get_logger(), "Master received next transition: %s",
               next_node_);
    activate_node(next_node_);
    
  }

  void create_lifecycle_client(const std::string& node_name) {
    std::string service_name = "/" + node_name + "/change_state";
    lifecycle_clients_[node_name] = 
      this->create_client<lifecycle_msgs::srv::ChangeState>(service_name);
    
    RCLCPP_DEBUG(this->get_logger(), "🔗 Created lifecycle client for %s", node_name.c_str());
  }

  void manage_flow_lifecycles() {
    // Ensure all nodes in flows are properly configured and activated
    for (const auto& [node_name, client] : lifecycle_clients_) {
      ensure_node_active(node_name, client);
    }
  }

  void ensure_node_active(const std::string& node_name, 
                         rclcpp::Client<lifecycle_msgs::srv::ChangeState>::SharedPtr client) {
    if (!client->wait_for_service(1s)) {
      RCLCPP_DEBUG(this->get_logger(), "⏳ Waiting for %s to become available...", node_name.c_str());
      return;
    }

    // In a full implementation, you'd check current state first
    // For now, we assume nodes are managed externally or by launch files
    RCLCPP_DEBUG(this->get_logger(), "✅ %s lifecycle service available", node_name.c_str());
  }

  void print_operational_summary() {
    RCLCPP_INFO(this->get_logger(), "🎯 === COGNITIVE NAVIGATION SYSTEM OPERATIONAL ===");
    RCLCPP_INFO(this->get_logger(), "🧠 Master monitoring %zu cognitive flows", flows_.size());
    RCLCPP_INFO(this->get_logger(), "🚀 Ready to coordinate navigation cognition!");
  }

  void configure_nodes() {
    if (flows_.empty()) {
      RCLCPP_WARN(this->get_logger(), "No cognitive flows configured!");
      return;
    }

    RCLCPP_INFO(this->get_logger(), "Configuring %zu cognitive flows...", flows_.size());

    for (const auto &flow_pair : flows_) {
      const std::string flow_name = flow_pair.first;
      auto flow_nodes = flow_pair.second;

      RCLCPP_INFO(this->get_logger(), "Configuring flow: %s", flow_name.c_str());

      for (const auto &node_name : flow_nodes->get_flow()) {
        RCLCPP_INFO(this->get_logger(), "    🧠 Adding lifecycle client for %s", node_name.c_str());
        create_lifecycle_client(node_name);
      }
      for (const auto &client_pair : lifecycle_clients_) {
        const auto &node = client_pair.first;
        auto client = client_pair.second;

        if (!client->wait_for_service(1s)) {
        RCLCPP_WARN(this->get_logger(), "Lifecycle service for %s not available, skipping", node.c_str());
        continue;
        }

        auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
        req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE;

        RCLCPP_INFO(this->get_logger(), "Requesting CONFIGURE for %s", node.c_str());
        auto future = client->async_send_request(req);
      }
    }



  }

  void activate_node(const std::string& node_name) {
    if (flows_.empty()) {
      RCLCPP_WARN(this->get_logger(), "No cognitive flows!");
      return;
    }

    RCLCPP_INFO(this->get_logger(), "Activating node: %s", node_name.c_str());

    auto it = lifecycle_clients_.find(node_name);
    if (it == lifecycle_clients_.end()) {
      RCLCPP_WARN(this->get_logger(), "No lifecycle client for %s", node_name.c_str());
      return;
    }

    auto client = it->second;
  
    auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
    req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE;

    auto future = client->async_send_request(req);
    }

};

int main(int argc, char **argv) {
  RCLCPP_INFO(rclcpp::get_logger("main"), "=== STARTING NAVIGATION COGNITIVE MASTER ===");
  rclcpp::init(argc, argv);
  
  rclcpp::NodeOptions options;
  auto node = std::make_shared<ReceptionistMaster>(options);
  
  rclcpp::spin(node->get_node_base_interface());
  rclcpp::shutdown();
  return 0;
}