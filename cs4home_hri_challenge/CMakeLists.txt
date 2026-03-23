cmake_minimum_required(VERSION 3.8)
project(cs4home_hri_challenge)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(cs4home_core REQUIRED)
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

set(dependencies
  cs4home_core
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
)


add_library(execute_bt SHARED
  src/ExecuteBT.cpp
)
ament_target_dependencies(execute_bt ${dependencies})

add_library(transition_output SHARED
src/TransitionOutput.cpp
)
ament_target_dependencies(transition_output ${dependencies})

add_executable(hri_challenge_master
  src/HRIChallengeMaster.cpp
)
ament_target_dependencies(hri_challenge_master ${dependencies})

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


install(TARGETS
  execute_bt
  transition_output
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS
  hri_challenge_master
  find_seat_cognitive_module
  greeting_guest_cognitive_module
  describe_person_cognitive_module
  grab_bag_cognitive_module
  transport_bag_cognitive_module
  introduce_guest_cognitive_module
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  bt_xml
  config
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
ament_export_libraries(execute_bt)
ament_export_dependencies(${dependencies})

ament_package()
