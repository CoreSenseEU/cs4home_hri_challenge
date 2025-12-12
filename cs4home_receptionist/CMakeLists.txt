cmake_minimum_required(VERSION 3.8)
project(cs4home_receptionist)

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
)


add_library(execute_bt SHARED
  src/ExecuteBT.cpp
)
ament_target_dependencies(execute_bt ${dependencies})

add_library(transition_output SHARED
src/TransitionOutput.cpp
)
ament_target_dependencies(transition_output ${dependencies})

add_executable(receptionist_master
  src/ReceptionistMaster.cpp
)
ament_target_dependencies(receptionist_master ${dependencies})

add_executable(describe_person_cognitive_module
  src/DescribePersonCM.cpp
)
ament_target_dependencies(describe_person_cognitive_module ${dependencies})

add_executable(find_seat_cognitive_module
  src/FindSeatCM.cpp
)
ament_target_dependencies(find_seat_cognitive_module ${dependencies})

add_executable(greeting_guest_cognitive_module
  src/GreetingGuestCM.cpp
)
ament_target_dependencies(greeting_guest_cognitive_module ${dependencies})


install(TARGETS
  execute_bt
  transition_output
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS
  receptionist_master
  find_seat_cognitive_module
  greeting_guest_cognitive_module
  describe_person_cognitive_module
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  bt_xml
  config
  DESTINATION share/${PROJECT_NAME}
)


if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_export_include_directories(include)
ament_export_libraries(execute_bt)
ament_export_dependencies(${dependencies})

ament_package()
