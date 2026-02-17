/*
 * Copyright 2026 BobRos
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <memory>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/color_rgba.hpp>
#include <string>
#include <vector>
#include <visualization_msgs/msg/marker.hpp>
#include <visualization_msgs/msg/marker_array.hpp>

using std_msgs::msg::ColorRGBA;
using visualization_msgs::msg::Marker;
using visualization_msgs::msg::MarkerArray;

/**
 * @brief Node to efficiently colorize markers based on a sentiment-driven color
 * topic.
 */
class FaceMarkerNode : public rclcpp::Node
{
public:
  FaceMarkerNode()
  : Node("face_marker")
  {
    // --- Parameters ---
    auto descriptor = rcl_interfaces::msg::ParameterDescriptor();

    descriptor.description = "Fixed frame ID to override incoming markers.";
    this->declare_parameter(
      "fixed_frame", get_env_or("MARKER_FIXED_FRAME", ""),
      descriptor);

    descriptor.description = "Uniform scale override (if > 0.0).";
    this->declare_parameter(
      "marker_scale",
      get_env_double_or("MARKER_SCALE", 0.0), descriptor);

    descriptor.description = "Topic name for receiving color overrides.";
    this->declare_parameter(
      "color_topic", get_env_or("MARKER_COLOR_TOPIC", "face_color_override"),
      descriptor);

    // Initial color handling
    std::vector<double> default_color = {0.5, 0.5, 0.5, 1.0};
    descriptor.description = "Initial RGBA color (double array).";
    this->declare_parameter(
      "initial_color",
      get_env_double_array_or("MARKER_INITIAL_COLOR", default_color),
      descriptor);

    // Update local state from parameters
    fixed_frame_ = this->get_parameter("fixed_frame").as_string();
    scale_ = this->get_parameter("marker_scale").as_double();
    auto init_color_vec =
      this->get_parameter("initial_color").as_double_array();
    if (init_color_vec.size() == 4) {
      current_color_.r = init_color_vec[0];
      current_color_.g = init_color_vec[1];
      current_color_.b = init_color_vec[2];
      current_color_.a = init_color_vec[3];
    }

    // --- Subscriptions & Publishers ---
    std::string color_topic = this->get_parameter("color_topic").as_string();

    pub_marker_ = this->create_publisher<Marker>("marker_out", 10);
    pub_marker_array_ =
      this->create_publisher<MarkerArray>("marker_array_out", 10);

    sub_color_ = this->create_subscription<ColorRGBA>(
      color_topic, 10,
      std::bind(
        &FaceMarkerNode::color_callback, this,
        std::placeholders::_1));

    sub_marker_ = this->create_subscription<Marker>(
      "marker_in", 10,
      std::bind(
        &FaceMarkerNode::marker_callback, this,
        std::placeholders::_1));

    sub_marker_array_ = this->create_subscription<MarkerArray>(
      "marker_array_in", 10,
      std::bind(
        &FaceMarkerNode::marker_array_callback, this,
        std::placeholders::_1));

    RCLCPP_INFO(
      this->get_logger(),
      "Face Marker Node initialized. Subscribed to %s",
      color_topic.c_str());
  }

private:
  // --- Helper Methods ---

  std::string get_env_or(
    const std::string & key,
    const std::string & default_value)
  {
    const char * val = std::getenv(key.c_str());
    return val ? std::string(val) : default_value;
  }

  double get_env_double_or(const std::string & key, double default_value)
  {
    const char * val = std::getenv(key.c_str());
    return val ? std::stod(val) : default_value;
  }

  std::vector<double>
  get_env_double_array_or(
    const std::string & key,
    const std::vector<double> & default_value)
  {
    const char * val = std::getenv(key.c_str());
    if (!val) {
      return default_value;
    }
    // Simple comma-separated list parser "0.5,0.5,0.5,1.0"
    std::vector<double> result;
    std::string s(val);
    size_t pos = 0;
    while ((pos = s.find(",")) != std::string::npos) {
      result.push_back(std::stod(s.substr(0, pos)));
      s.erase(0, pos + 1);
    }
    result.push_back(std::stod(s));
    return result.size() == 4 ? result : default_value;
  }

  void update_marker(Marker & marker) const
  {
    if (!fixed_frame_.empty()) {
      marker.header.frame_id = fixed_frame_;
    }

    // Apply sentiment color
    marker.color = current_color_;

    // Uniform scale override
    if (scale_ > 0.0) {
      marker.scale.x = scale_;
      marker.scale.y = scale_;
      marker.scale.z = scale_;
    }
  }

  // --- Callbacks ---

  void color_callback(const ColorRGBA::SharedPtr msg) {current_color_ = *msg;}

  void marker_callback(const Marker::SharedPtr msg) const
  {
    Marker marker = *msg;
    update_marker(marker);
    pub_marker_->publish(marker);
  }

  void marker_array_callback(const MarkerArray::SharedPtr msg) const
  {
    MarkerArray array = *msg;
    for (auto & marker : array.markers) {
      update_marker(marker);
    }
    pub_marker_array_->publish(array);
  }

  // --- Members ---
  rclcpp::Publisher<Marker>::SharedPtr pub_marker_;
  rclcpp::Publisher<MarkerArray>::SharedPtr pub_marker_array_;

  rclcpp::Subscription<ColorRGBA>::SharedPtr sub_color_;
  rclcpp::Subscription<Marker>::SharedPtr sub_marker_;
  rclcpp::Subscription<MarkerArray>::SharedPtr sub_marker_array_;

  ColorRGBA current_color_;
  std::string fixed_frame_;
  double scale_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FaceMarkerNode>());
  rclcpp::shutdown();
  return 0;
}
