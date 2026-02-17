cmake_minimum_required(VERSION 3.8)
project(bob_face)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosbag2_cpp REQUIRED)
find_package(bob_msgs REQUIRED)

include_directories(include)

# bag node
add_executable(bag src/bag_node.cpp)

ament_target_dependencies(bag
  rclcpp
  visualization_msgs
  rosbag2_cpp
  bob_msgs
)

# face marker node
add_executable(face_marker src/face_marker_node.cpp)
ament_target_dependencies(face_marker
  rclcpp
  visualization_msgs
  std_msgs
)

install(TARGETS
  bag
  face_marker
  DESTINATION lib/${PROJECT_NAME}
)

# Install scripts
install(PROGRAMS
  scripts/face_gui.py
  scripts/sentiment_node.py
  scripts/motion_node.py
  scripts/motion_manager.py
  DESTINATION lib/${PROJECT_NAME}
)

# Install directories
install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}/
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
