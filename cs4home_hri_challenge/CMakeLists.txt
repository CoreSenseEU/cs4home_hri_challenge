cmake_minimum_required(VERSION 3.8)
project(cs4home_hri_challenge)

if(POLICY CMP0071)
  cmake_policy(SET CMP0071 NEW)
endif()

set(CMAKE_AUTOMOC ON)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(pluginlib REQUIRED)
find_package(Qt5 REQUIRED COMPONENTS Widgets)
find_package(cs4home_core REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(rclcpp_cascade_lifecycle REQUIRED)
find_package(behaviortree_cpp_v3 REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(lifecycle_msgs REQUIRED)
find_package(hri REQUIRED)
find_package(motion REQUIRED)
find_package(perception REQUIRED)
find_package(attention_system REQUIRED)
find_package(perception_system REQUIRED)
find_package(nav2_behavior_tree REQUIRED)
find_package(kb_msgs REQUIRED)
find_package(configuration REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rviz_common REQUIRED)

set(dependencies
  cs4home_core
  builtin_interfaces
  rclcpp
  rclcpp_lifecycle
  rclcpp_components
  rclcpp_cascade_lifecycle
  behaviortree_cpp_v3
  ament_index_cpp
  lifecycle_msgs
  hri
  motion
  perception
  attention_system
  perception_system
  nav2_behavior_tree
  rclcpp_action
  kb_msgs
  configuration
  diagnostic_msgs
  std_msgs
)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ModuleTransitionEvent.msg"
  DEPENDENCIES builtin_interfaces
)
rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} "rosidl_typesupport_cpp")


add_library(hri_execute_bt SHARED
  src/ExecuteBT.cpp
)
ament_target_dependencies(hri_execute_bt ${dependencies})

add_library(hri_transition_output SHARED
src/TransitionOutput.cpp
)
ament_target_dependencies(hri_transition_output ${dependencies})

add_library(hri_challenge_monitor_panel SHARED
  include/cs4home_hri_challenge/HRIChallengeMonitorPanel.hpp
  src/HRIChallengeMonitorPanel.cpp
)
target_include_directories(hri_challenge_monitor_panel PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(hri_challenge_monitor_panel
  pluginlib
  rclcpp
  rviz_common
)
target_link_libraries(hri_challenge_monitor_panel
  Qt5::Widgets
  "${cpp_typesupport_target}"
)
pluginlib_export_plugin_description_file(rviz_common rviz_plugin_description.xml)

add_executable(hri_challenge_master
  src/HRIChallengeMaster.cpp
)
ament_target_dependencies(hri_challenge_master ${dependencies})
target_link_libraries(hri_challenge_master "${cpp_typesupport_target}")

add_executable(hri_challenge_bt
  src/HRIChallengeBTMain.cpp
)
ament_target_dependencies(hri_challenge_bt ${dependencies})

add_executable(describe_person_cognitive_module
  src/DescribePersonCM.cpp
)
ament_target_dependencies(describe_person_cognitive_module ${dependencies})

add_executable(introduce_guest_cognitive_module
  src/IntroduceGuestCM.cpp
)
ament_target_dependencies(introduce_guest_cognitive_module ${dependencies})

add_executable(find_seat_cognitive_module
  src/FindSeatCM.cpp
)
ament_target_dependencies(find_seat_cognitive_module ${dependencies})

add_executable(greeting_guest_cognitive_module
  src/GreetingGuestCM.cpp
)
ament_target_dependencies(greeting_guest_cognitive_module ${dependencies})

add_executable(grab_bag_cognitive_module
  src/GrabBagCM.cpp
)
ament_target_dependencies(grab_bag_cognitive_module ${dependencies})

add_executable(transport_bag_cognitive_module
  src/TransportBagCM.cpp
)
ament_target_dependencies(transport_bag_cognitive_module ${dependencies})

add_executable(recovery_cognitive_module
  src/RecoveryCM.cpp
)
ament_target_dependencies(recovery_cognitive_module ${dependencies})


install(TARGETS
  hri_execute_bt
  hri_transition_output
  hri_challenge_monitor_panel
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(DIRECTORY include/
  DESTINATION include
)

install(TARGETS
  hri_challenge_bt
  hri_challenge_master
  find_seat_cognitive_module
  greeting_guest_cognitive_module
  describe_person_cognitive_module
  grab_bag_cognitive_module
  transport_bag_cognitive_module
  introduce_guest_cognitive_module
  recovery_cognitive_module
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  bt_xml
  config
  DESTINATION share/${PROJECT_NAME}
)

install(FILES rviz_plugin_description.xml
  DESTINATION share/${PROJECT_NAME}
)


if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  
  # Add test for sequential state machine
  ament_add_gtest(test_sequential_state_machine test/test_sequential_state_machine.cpp)
  target_link_libraries(test_sequential_state_machine ${rclcpp_LIBRARIES})
  target_include_directories(test_sequential_state_machine PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  ament_target_dependencies(test_sequential_state_machine
    rclcpp
    lifecycle_msgs
    std_msgs
  )
endif()

ament_export_include_directories(include)
ament_export_libraries(hri_execute_bt hri_challenge_monitor_panel)
ament_export_dependencies(${dependencies})

ament_package()
