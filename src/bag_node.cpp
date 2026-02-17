/**
  Copyright 2023 BobRos

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
*/

#include "bob_msgs/srv/set_sequence.hpp"
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <cmath>
#include <cstddef>
#include <map>
#include <random>
#include <rcl_interfaces/msg/set_parameters_result.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/serialization.hpp>
#include <rosbag2_cpp/readers/sequential_reader.hpp>
#include <rosbag2_storage/storage_options.hpp>
#include <vector>
#include <visualization_msgs/msg/marker_array.hpp>

const char * package_name = "bob_face";

using namespace rclcpp;
using namespace bob_msgs::srv;
using namespace std::placeholders;
using namespace rcl_interfaces::msg;

class BagNode : public Node
{
  rosbag2_cpp::readers::SequentialReader reader_;

  Publisher<visualization_msgs::msg::MarkerArray>::SharedPtr publisher_{
    nullptr};

  TimerBase::SharedPtr timer_{nullptr};

  Service<SetSequence>::SharedPtr srv_set_sequence_{nullptr};

  std::vector<visualization_msgs::msg::MarkerArray> frame_buffer_;
  bool frame_buffer_loaded_;

  rcutils_time_point_value_t start_timestamp_;

  OnSetParametersCallbackHandle::SharedPtr callback_handle_;

  size_t count_frames_;
  size_t current_frame_;
  size_t rate_;
  bool loop_;
  int loop_direction_;
  uint32_t seq_type_, seq_start_, seq_end_;
  int jitter_mode_;
  double jitter_intensity_;

  // Blending state
  bool is_blending_;
  size_t blend_frame_counter_;
  size_t blend_duration_;
  visualization_msgs::msg::MarkerArray last_published_msg_;
  visualization_msgs::msg::MarkerArray blend_start_msg_;

  // Jitter components
  std::default_random_engine generator_;
  std::normal_distribution<double> distribution_;

public:
  BagNode()
  : Node("bag"), frame_buffer_loaded_(false), start_timestamp_(0),
    count_frames_(0), current_frame_(0), rate_(30), loop_(false),
    loop_direction_(1), seq_type_(1), seq_start_(0), seq_end_(0),
    is_blending_(false), blend_frame_counter_(0), blend_duration_(24),
    distribution_(0.0, 0.001)     // subtle jitter
  {
    this->declare_parameter("bag", "rosbag2_face/rosbag2_face.db3");
    std::string file_path = this->get_parameter("bag").as_string();

    if (access(file_path.c_str(), F_OK) ==
      -1)   // try to find default rosbag2 file
    {
      file_path = ament_index_cpp::get_package_share_directory(package_name) +
        "/config/" + file_path;
      if (access(file_path.c_str(), F_OK) == -1) {
        RCLCPP_ERROR(
          this->get_logger(),
          "can't access bag file! Check the bag parameter.");
        exit(1);
      }
    }

    this->declare_parameter("start_seconds", 0.0);
    double start = this->get_parameter("start_seconds").as_double();

    this->declare_parameter("num_frames", 0);
    count_frames_ = this->get_parameter("num_frames").as_int();

    this->declare_parameter("rate", 30);
    rate_ = this->get_parameter("rate").as_int();

    this->declare_parameter("sequence_type", 1);
    seq_type_ = (uint32_t)this->get_parameter("sequence_type").as_int();

    // A rate of 0 (preload) makes no sense with loop==false,
    // in that case set the loop default to true.
    this->declare_parameter("loop", (rate_ ? false : true));
    loop_ = this->get_parameter("loop").as_bool();

    this->declare_parameter("jitter_mode", 0); // 0:Off, 1:Blending, 2:Always
    jitter_mode_ = this->get_parameter("jitter_mode").as_int();

    this->declare_parameter("jitter_intensity", 0.001);
    jitter_intensity_ = this->get_parameter("jitter_intensity").as_double();
    distribution_ = std::normal_distribution<double>(0.0, jitter_intensity_);

    this->declare_parameter("blend_duration", 24);
    blend_duration_ = this->get_parameter("blend_duration").as_int();

    rosbag2_storage::StorageOptions storage_options{};
    storage_options.uri = file_path;
    storage_options.storage_id = "sqlite3";

    rosbag2_cpp::ConverterOptions converter_options{};
    converter_options.input_serialization_format = "cdr";
    converter_options.output_serialization_format = "cdr";

    reader_.open(storage_options, converter_options);
    const auto topics = reader_.get_all_topics_and_types();

    for (const auto & topic : topics) {
      RCLCPP_INFO(this->get_logger(), topic.name.c_str());
    }

    auto metadata = reader_.get_metadata();
    std::chrono::milliseconds begin((int)(start * 1000));
    std::chrono::milliseconds frame_length(1000 / (rate_ ? rate_ : 0xFFFF));
    start_timestamp_ =
      (metadata.starting_time + begin).time_since_epoch().count();

    reader_.seek(start_timestamp_);

    srv_set_sequence_ = this->create_service<SetSequence>(
      "set_sequence", std::bind(&BagNode::set_sequence, this, _1, _2));

    publisher_ = this->create_publisher<visualization_msgs::msg::MarkerArray>(
      "face_marker_array", 10);

    callback_handle_ = this->add_on_set_parameters_callback(
      std::bind(&BagNode::parametersCallback, this, std::placeholders::_1));

    timer_ = this->create_wall_timer(
      frame_length,
      std::bind(&BagNode::timer_callback, this));
  }

private:
  visualization_msgs::msg::MarkerArray
  lerp(
    const visualization_msgs::msg::MarkerArray & a,
    const visualization_msgs::msg::MarkerArray & b, double t)
  {
    if (t <= 0.0) {
      return a;
    }
    if (t >= 1.0) {
      return b;
    }

    visualization_msgs::msg::MarkerArray result =
      b;   // Use b as template for metadata/IDs

    // Create map for quick lookup from 'a' using (ns, id) pair
    std::map<std::pair<std::string, int>, size_t> lookup_a;
    for (size_t i = 0; i < a.markers.size(); ++i) {
      lookup_a[{a.markers[i].ns, a.markers[i].id}] = i;
    }

    size_t match_count = 0;
    for (size_t i = 0; i < b.markers.size(); ++i) {
      auto it = lookup_a.find({b.markers[i].ns, b.markers[i].id});
      if (it != lookup_a.end()) {
        const auto & marker_a = a.markers[it->second];
        const auto & marker_b = b.markers[i];

        // 1. Interpolate pose (rarely used but good to have)
        result.markers[i].pose.position.x =
          marker_a.pose.position.x * (1.0 - t) + marker_b.pose.position.x * t;
        result.markers[i].pose.position.y =
          marker_a.pose.position.y * (1.0 - t) + marker_b.pose.position.y * t;
        result.markers[i].pose.position.z =
          marker_a.pose.position.z * (1.0 - t) + marker_b.pose.position.z * t;

        // 2. Interpolate points array (CRITICAL: this is where the face
        // geometry is)
        if (marker_a.points.size() == marker_b.points.size()) {
          for (size_t j = 0; j < marker_a.points.size(); ++j) {
            result.markers[i].points[j].x =
              marker_a.points[j].x * (1.0 - t) + marker_b.points[j].x * t;
            result.markers[i].points[j].y =
              marker_a.points[j].y * (1.0 - t) + marker_b.points[j].y * t;
            result.markers[i].points[j].z =
              marker_a.points[j].z * (1.0 - t) + marker_b.points[j].z * t;
          }
        }

        match_count++;
      }
    }

    static size_t last_match_count = 0;
    if (match_count != last_match_count || match_count == 0) {
      RCLCPP_INFO(
        this->get_logger(),
        "lerp: matched %zu/%zu markers (Unique keys in A: %zu)",
        match_count, b.markers.size(), lookup_a.size());
      last_match_count = match_count;
    }

    if (match_count == 0 && !a.markers.empty() && !b.markers.empty()) {
      RCLCPP_WARN_ONCE(
        this->get_logger(),
        "lerp: No matching marker IDs found between sequences! "
        "(A:%zu, B:%zu)",
        a.markers.size(), b.markers.size());
    }

    return result;
  }

  void add_jitter(visualization_msgs::msg::MarkerArray & msg)
  {
    if (jitter_mode_ == 0) {
      return;
    }
    if (jitter_mode_ == 1 && !is_blending_) {
      return;
    }

    // Apply jitter to Brows & Eyes
    for (size_t i = 0; i < msg.markers.size(); ++i) {
      bool should_jitter = (i == 3 || i == 4 || i == 6 || i == 7);
      if (should_jitter) {
        for (auto & p : msg.markers[i].points) {
          p.x += distribution_(generator_);
          p.y += distribution_(generator_);
          p.z += distribution_(generator_);
        }
      }
    }
  }

  void timer_callback()
  {
    if (frame_buffer_loaded_ && !frame_buffer_.empty()) {
      visualization_msgs::msg::MarkerArray raw_msg =
        frame_buffer_[current_frame_];
      visualization_msgs::msg::MarkerArray msg_to_publish = raw_msg;

      if (is_blending_) {
        double t = (double)blend_frame_counter_ / (double)blend_duration_;
        msg_to_publish = lerp(blend_start_msg_, raw_msg, t);

        if (blend_frame_counter_ % 5 == 0 || blend_frame_counter_ < 3) {
          double start_val = (blend_start_msg_.markers.empty() ||
            blend_start_msg_.markers[0].points.empty()) ?
            0.0 :
            blend_start_msg_.markers[0].points[0].y;
          double target_val =
            (raw_msg.markers.empty() || raw_msg.markers[0].points.empty()) ?
            0.0 :
            raw_msg.markers[0].points[0].y;
          double current_val = (msg_to_publish.markers.empty() ||
            msg_to_publish.markers[0].points.empty()) ?
            0.0 :
            msg_to_publish.markers[0].points[0].y;

          RCLCPP_DEBUG(
            this->get_logger(),
            "Blending: %zu/%zu, t=%.2f, p0_y: %.4f -> %.4f (curr: %.4f)",
            blend_frame_counter_, blend_duration_, t, start_val, target_val,
            current_val);
        }

        blend_frame_counter_++;

        if (blend_frame_counter_ >= blend_duration_) {
          RCLCPP_DEBUG(this->get_logger(), "Blending status: Finished");
          is_blending_ = false;
          blend_frame_counter_ = 0;
        }
      }

      // Logic for frame progression (always happens)
      size_t next_frame = current_frame_ + loop_direction_;
      bool sequence_end_reached = false;

      if (loop_direction_ > 0) {
        if (next_frame >= frame_buffer_.size() ||
          (seq_end_ > 0 && next_frame >= seq_end_))
        {
          sequence_end_reached = true;
        }
      } else {
        if (next_frame < seq_start_ || next_frame >= frame_buffer_.size()) {
          sequence_end_reached = true;
        }
      }

      if (sequence_end_reached) {
        size_t target_frame;
        if (seq_type_ == 1) { // TYPE_FLIPFLOP
          loop_direction_ *= -1;
          target_frame = current_frame_; // Stay here and reverse
        } else {                         // TYPE_CIRCULAR
          target_frame = seq_end_ ? seq_start_ : 0;
        }

        if (target_frame != current_frame_) {
          // Trigger loop blending
          blend_start_msg_ = msg_to_publish;
          is_blending_ = true;
          blend_frame_counter_ = 0;
          current_frame_ = target_frame;
        } else {
          current_frame_ = target_frame;
        }
      } else {
        current_frame_ = next_frame;
      }

      add_jitter(msg_to_publish);
      publisher_->publish(msg_to_publish);
      last_published_msg_ = msg_to_publish;
    } else if (reader_.has_next()) {
      auto serialized_message = reader_.read_next();

      rclcpp::SerializedMessage extracted_serialized_msg(
        *serialized_message->serialized_data);
      auto deserializer =
        rclcpp::Serialization<visualization_msgs::msg::MarkerArray>();
      auto topic = serialized_message->topic_name;
      visualization_msgs::msg::MarkerArray msg;

      if (topic.find("face_marker_array") != std::string::npos) {
        current_frame_++;
        RCLCPP_DEBUG(this->get_logger(), "got frame %d", (int)current_frame_);
        deserializer.deserialize_message(&extracted_serialized_msg, &msg);

        if (rate_) {
          publisher_->publish(msg);
          last_published_msg_ = msg;
        }

        if (loop_ && (count_frames_ > 0 && current_frame_ > count_frames_)) {
          current_frame_ = 0;
          frame_buffer_loaded_ = true;
          RCLCPP_INFO(
            this->get_logger(), "buffer filled with %d messages",
            (int)frame_buffer_.size());
        } else if (loop_) {
          frame_buffer_.push_back(msg);
        }
      }
    } else if (!reader_.has_next()) { // handle end of bag
      if (loop_) {
        frame_buffer_loaded_ = true;
        RCLCPP_INFO(this->get_logger(), "filling frame buffer done");

        // Just preload the data? If yes stop the timer and wait for a
        // service call to begin publishing data
        if (rate_ == 0) {
          timer_->cancel();
          RCLCPP_INFO(
            this->get_logger(), "buffer filled with %d messages",
            (int)frame_buffer_.size());
          RCLCPP_INFO(
            this->get_logger(),
            "wait for service call to start publising data");
        }
      } else {
        timer_->cancel();
        RCLCPP_INFO(this->get_logger(), "all messages processed");
        rclcpp::shutdown();
      }
    }
  }

#define RETURN_ERROR_IF(condition, msg) \
  if (condition) { \
    response->error = msg; \
    RCLCPP_ERROR(this->get_logger(), msg); \
    return; \
  }

#define DUMP_PARAMS_STREAM(stream) \
  RCLCPP_DEBUG_STREAM(this->get_logger(), "" << stream)

  void set_sequence(
    const std::shared_ptr<SetSequence::Request> request,
    std::shared_ptr<SetSequence::Response> response)
  {
    RCLCPP_INFO(this->get_logger(), "service call set_sequence");

    RETURN_ERROR_IF(
      request->start > request->end,
      "set_sequence: Sequence start is greater than sequence end");
    RETURN_ERROR_IF(request->type > 1, "set_sequence: Unkown type parameter");
    RETURN_ERROR_IF(
      !frame_buffer_loaded_,
      "set_sequence: Framebuffer is not fully loaded yet");

    seq_start_ = request->start;
    seq_end_ = request->end;
    seq_type_ = request->type;
    loop_direction_ = 1;

    // Initiate blending to new sequence
    if (last_published_msg_.markers.empty()) {
      RCLCPP_WARN(
        this->get_logger(),
        "set_sequence: last_published_msg_ is empty! Using target as start.");
      blend_start_msg_ = frame_buffer_[seq_start_];
    } else {
      blend_start_msg_ = last_published_msg_;
    }

    is_blending_ = true;
    blend_frame_counter_ = 0;
    current_frame_ = seq_start_;

    RCLCPP_DEBUG(
      this->get_logger(),
      "set_sequence: Blending from current (%zu markers) to frame %u "
      "(%zu markers) with duration %zu",
      blend_start_msg_.markers.size(), seq_start_,
      frame_buffer_[seq_start_].markers.size(), blend_duration_);

    DUMP_PARAMS_STREAM("seq_start: " << seq_start_);
    DUMP_PARAMS_STREAM("seq_end: " << seq_end_);
    DUMP_PARAMS_STREAM("seq_type: " << seq_type_);
    DUMP_PARAMS_STREAM("current_frame: " << current_frame_);
    DUMP_PARAMS_STREAM("loop_direction: " << loop_direction_);
    DUMP_PARAMS_STREAM("buffer_size: " << frame_buffer_.size());

    if (request->rate) {
      rate_ = request->rate;
      timer_->cancel();
      std::chrono::milliseconds frame_length(1000 / rate_);
      timer_ = this->create_wall_timer(
        frame_length, std::bind(&BagNode::timer_callback, this));
      RCLCPP_INFO(
        this->get_logger(), "set_sequence: Updated rate to %zu FPS",
        rate_);
    }
  }

  SetParametersResult
  parametersCallback(const std::vector<rclcpp::Parameter> & parameters)
  {
    SetParametersResult result;
    auto request = std::make_shared<SetSequence::Request>();
    auto response = std::make_shared<SetSequence::Response>();

    request->start = seq_start_;
    request->end = seq_end_;
    request->type = seq_type_;
    result.successful = true;
    result.reason = "success";

    for (auto & param : parameters) {
      if (param.get_name() == "rate") {
        request->rate = param.as_int();
        this->set_sequence(request, response);
      } else if (param.get_name() == "num_frames") {
        request->end = seq_start_ + param.as_int();
        this->set_sequence(request, response);
      } else if (param.get_name() == "start_seconds") {
        request->start = (int)(param.as_double() * rate_);
        this->set_sequence(request, response);
      } else if (param.get_name() == "loop") {
        loop_ = param.as_bool();
      } else if (param.get_name() == "sequence_type") {
        request->type = (uint32_t)param.as_int();
        this->set_sequence(request, response);
      } else if (param.get_name() == "jitter_mode") {
        jitter_mode_ = param.as_int();
      } else if (param.get_name() == "jitter_intensity") {
        jitter_intensity_ = param.as_double();
        distribution_ =
          std::normal_distribution<double>(0.0, jitter_intensity_);
      } else if (param.get_name() == "blend_duration") {
        blend_duration_ = param.as_int();
      } else {
        response->error =
          ("parameter " + param.get_name() + " is read only").c_str();
        RCLCPP_WARN(this->get_logger(), response->error.c_str());
      }
    }

    if (response->error.length()) {
      result.successful = false;
      result.reason = response->error.c_str();
    }

    return result;
  }
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<BagNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
