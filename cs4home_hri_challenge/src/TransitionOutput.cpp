////////////////////////////////////////////////////////////////////
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
////////////////////////////////////////////////////////////////////

#include "cs4home_core/Efferent.hpp"
#include "cs4home_core/macros.hpp"
#include "std_msgs/msg/bool.hpp"
#include "rcl_interfaces/srv/set_parameters.hpp"
#include "rcl_interfaces/msg/parameter.hpp"
#include "rcl_interfaces/msg/parameter_value.hpp"
#include "rclcpp/macros.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"


/**
 * @class TransitionOutput
 * @brief Manages sound output by creating publishers for specified topics and
 *        providing a method to publish sound messages.
 */
class TransitionOutput : public cs4home_core::Efferent
{
public:
  RCLCPP_SMART_PTR_DEFINITIONS(TransitionOutput)

  /**
   * @brief Constructs a AudioOutput object and declares necessary
   * parameters.
   * @param parent Shared pointer to the lifecycle node managing this
   * AudioOutput instance.
   */
  explicit TransitionOutput(rclcpp_lifecycle::LifecycleNode::SharedPtr parent)
  : Efferent("transition_output", parent)
  {
    RCLCPP_INFO(parent_->get_logger(), "Efferent created: [TransitionOutput]");
  }

  /**
   * @brief Configures the AudioOutput by creating publishers for each
   * specified topic.
   *
   * This method retrieves the topic names from the parameter server and
   * attempts to create a publisher for each topic to publish
   * `sound_msgs::msg::SoundDetection` messages.
   *
   * @return True if all publishers are created successfully.
   */
  bool configure() {return Efferent::configure();}
};

/// Registers the TransitionOutput component with the ROS 2 class loader
CS_REGISTER_COMPONENT(TransitionOutput)
