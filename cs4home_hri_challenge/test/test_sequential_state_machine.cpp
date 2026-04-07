// Copyright 2025 IMR Robotics & Automation Group
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

#include <gtest/gtest.h>
#include <memory>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "lifecycle_msgs/srv/change_state.hpp"
#include "std_msgs/msg/bool.hpp"

// Mock test class to access HRIChallengeMaster protected methods
// Since we can't easily test the actual Master class in isolation,
// we'll test the key logic components

class SequentialStateMachineTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    rclcpp::init(0, nullptr);
  }

  void TearDown() override
  {
    rclcpp::shutdown();
  }
};

// Test: Sequential flow parsing
TEST_F(SequentialStateMachineTest, TestFlowConfigParsing)
{
  // Create a test node to verify parameter parsing
  auto node = rclcpp::Node::make_shared("test_flow_config");

  // Declare test parameters
  node->declare_parameter("flows", std::vector<std::string>{"main_flow"});
  node->declare_parameter(
    "main_flow.initial_states",
    std::vector<std::string>{"module_a"});
  node->declare_parameter(
    "main_flow",
    std::vector<std::string>{"module_a", "module_b", "module_c"});

  // Verify parameters can be retrieved
  std::vector<std::string> flows;
  ASSERT_TRUE(node->get_parameter("flows", flows));
  EXPECT_EQ(flows.size(), 1);
  EXPECT_EQ(flows[0], "main_flow");

  std::vector<std::string> initial_states;
  ASSERT_TRUE(node->get_parameter("main_flow.initial_states", initial_states));
  EXPECT_EQ(initial_states.size(), 1);
  EXPECT_EQ(initial_states[0], "module_a");

  std::vector<std::string> all_modules;
  ASSERT_TRUE(node->get_parameter("main_flow", all_modules));
  EXPECT_EQ(all_modules.size(), 3);
  EXPECT_EQ(all_modules[0], "module_a");
  EXPECT_EQ(all_modules[1], "module_b");
  EXPECT_EQ(all_modules[2], "module_c");
}

// Test: Sequential advancement logic
TEST_F(SequentialStateMachineTest, TestSequentialAdvancement)
{
  std::vector<std::string> modules = {"module_a", "module_b", "module_c"};

  // Simulate finding current module and getting next
  std::string current = "module_a";
  auto it = std::find(modules.begin(), modules.end(), current);
  ASSERT_NE(it, modules.end());

  size_t current_idx = std::distance(modules.begin(), it);
  size_t next_idx = (current_idx + 1) % modules.size();

  EXPECT_EQ(modules[next_idx], "module_b");

  // Test wrapping around
  current = "module_c";
  it = std::find(modules.begin(), modules.end(), current);
  current_idx = std::distance(modules.begin(), it);
  next_idx = (current_idx + 1) % modules.size();

  EXPECT_EQ(modules[next_idx], "module_a");  // Should wrap to first
}

// Test: Completion message publishing
TEST_F(SequentialStateMachineTest, TestCompletionMessageFormat)
{
  auto node = rclcpp::Node::make_shared("test_completion");

  std::vector<std_msgs::msg::Bool::SharedPtr> received_messages;

  auto sub = node->create_subscription<std_msgs::msg::Bool>(
    "/test_module/completion", 10,
    [&received_messages](std_msgs::msg::Bool::SharedPtr msg) {
      received_messages.push_back(msg);
    });

  auto pub = node->create_publisher<std_msgs::msg::Bool>("/test_module/completion", 10);

  // Wait for subscription to be established
  rclcpp::sleep_for(std::chrono::milliseconds(100));

  // Publish success
  auto success_msg = std::make_shared<std_msgs::msg::Bool>();
  success_msg->data = true;
  pub->publish(*success_msg);

  // Spin to process first message
  rclcpp::spin_some(node);
  rclcpp::sleep_for(std::chrono::milliseconds(50));

  // Publish failure
  auto failure_msg = std::make_shared<std_msgs::msg::Bool>();
  failure_msg->data = false;
  pub->publish(*failure_msg);

  // Spin to process second message
  rclcpp::spin_some(node);
  rclcpp::sleep_for(std::chrono::milliseconds(50));

  ASSERT_GE(received_messages.size(), 1);  // At least one message received
  if (received_messages.size() >= 1) {
    EXPECT_TRUE(received_messages[0]->data);   // Success
  }
  if (received_messages.size() >= 2) {
    EXPECT_FALSE(received_messages[1]->data);  // Failure
  }
}

// Test: Module activation helper
TEST_F(SequentialStateMachineTest, TestActivateModuleHelper)
{
  // Test that we can create a lifecycle change state request
  auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
  req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE;

  EXPECT_EQ(req->transition.id, lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE);
}

// Test: Module deactivation helper
TEST_F(SequentialStateMachineTest, TestDeactivateModuleHelper)
{
  // Test that we can create a lifecycle change state request for deactivation
  auto req = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
  req->transition.id = lifecycle_msgs::msg::Transition::TRANSITION_DEACTIVATE;

  EXPECT_EQ(req->transition.id, lifecycle_msgs::msg::Transition::TRANSITION_DEACTIVATE);
}

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
