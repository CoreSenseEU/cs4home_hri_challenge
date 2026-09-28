#include <memory>
#include <string>

#include "behaviortree_cpp_v3/action_node.h"
#include "behaviortree_cpp_v3/bt_factory.h"
#include "cs4home_hri_challenge/RuntimeTrace.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_cascade_lifecycle/rclcpp_cascade_lifecycle.hpp"

namespace cs4home_hri_challenge
{

class RuntimeTraceNode : public BT::SyncActionNode
{
public:
  RuntimeTraceNode(const std::string & name, const BT::NodeConfiguration & config)
  : BT::SyncActionNode(name, config)
  {
  }

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("architecture", "monolithic"),
      BT::InputPort<std::string>("flow", ""),
      BT::InputPort<std::string>("capability"),
      BT::InputPort<std::string>("module", ""),
      BT::InputPort<std::string>("event"),
      BT::InputPort<std::string>("success", ""),
      BT::InputPort<std::string>("details", ""),
    };
  }

  BT::NodeStatus tick() override
  {
    std::string architecture;
    std::string flow;
    std::string capability;
    std::string module;
    std::string event;
    std::string success;
    std::string details;

    getInput("architecture", architecture);
    getInput("flow", flow);
    getInput("capability", capability);
    getInput("module", module);
    getInput("event", event);
    getInput("success", success);
    getInput("details", details);

    architecture = RuntimeTrace::architecture_from_env(architecture.empty() ? "monolithic" : architecture);

    rclcpp::Time stamp;
    try {
      auto node = config().blackboard->get<
        std::shared_ptr<rclcpp_cascade_lifecycle::CascadeLifecycleNode>>("node");
      stamp = node->now();
      if (module.empty()) {
        module = node->get_name();
      }
    } catch (const std::exception &) {
      stamp = rclcpp::Clock(RCL_SYSTEM_TIME).now();
    }

    if (capability.empty() && !module.empty()) {
      capability = RuntimeTrace::capability_from_module(module);
    }

    RuntimeTrace::record(architecture, flow, capability, module, event, stamp, success, details);
    return BT::NodeStatus::SUCCESS;
  }
};

}  // namespace cs4home_hri_challenge

extern "C" __attribute__((visibility("default"))) void BT_RegisterNodesFromPlugin(
  BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<cs4home_hri_challenge::RuntimeTraceNode>("RuntimeTrace");
}
