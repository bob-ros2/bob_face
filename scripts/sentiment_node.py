#!/usr/bin/env python3

# Copyright 2026 BobRos
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Sentiment Analysis Node for Bob.

This node performs fast sentiment analysis on input text using VADER
and publishes both the score and a corresponding color from a colormap.
"""

import os
import json
import time
import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import ParameterDescriptor, ParameterType
from std_msgs.msg import String, Float32, ColorRGBA
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from matplotlib import colormaps


class SentimentNode(Node):
    """
    ROS 2 Node for real-time sentiment analysis.

    Uses VADER for high-speed computation on CPU and maps the result
    to a visual color override for the face markers.
    """

    def __init__(self):
        """Initialize the node, parameters, and communication."""
        super().__init__('sentiment')

        # Declare Parameters with standard naming and descriptors
        self.declare_parameter(
            'cmap_name',
            os.environ.get('SENTIMENT_CMAP_NAME', 'plasma'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='The matplotlib colormap name to use.'
            )
        )

        self.declare_parameter(
            'analize_topic',
            os.environ.get('SENTIMENT_ANALIZE_TOPIC', 'analize'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Topic name for input text strings.'
            )
        )

        self.declare_parameter(
            'color_topic',
            os.environ.get('SENTIMENT_COLOR_TOPIC', 'face_color_override'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Topic name for the output color override.'
            )
        )

        # Handle initial color array parameter
        default_color = [0.5, 0.5, 0.5, 1.0]
        env_color = os.environ.get('SENTIMENT_INITIAL_COLOR')
        if env_color:
            try:
                default_color = json.loads(env_color)
            except (ValueError, SyntaxError):
                self.get_logger().warn(f"Failed to parse SENTIMENT_INITIAL_COLOR: {env_color}")

        self.declare_parameter(
            'initial_color',
            default_color,
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE_ARRAY,
                description='Initial RGBA color to publish on startup.'
            )
        )

        self.declare_parameter(
            'smooth_alpha',
            float(os.environ.get('SENTIMENT_SMOOTH_ALPHA', '0.2')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Smoothing factor (0..1). Lower is smoother.'
            )
        )

        self.declare_parameter(
            'buffer_size',
            int(os.environ.get('SENTIMENT_BUFFER_SIZE', '500')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_INTEGER,
                description='Max characters to buffer for context.'
            )
        )

        # Internal state
        self.context_buffer = ""
        self.last_compound = 0.0  # Range -1..1

        # Initialize VADER and Colormap
        self.analyzer = SentimentIntensityAnalyzer()
        try:
            name = self.get_parameter('cmap_name').value
            self.cmap = colormaps[name]
        except KeyError:
            self.get_logger().error(f"Colormap '{name}' not found. Using 'plasma'.")
            self.cmap = colormaps['plasma']

        # Setup Pub/Sub
        self.pub_score = self.create_publisher(Float32, 'sentiment_score', 10)
        self.pub_color = self.create_publisher(
            ColorRGBA,
            self.get_parameter('color_topic').value,
            10
        )

        self.sub_text = self.create_subscription(
            String,
            self.get_parameter('analize_topic').value,
            self.text_callback,
            10
        )

        # Publish initial color
        self.publish_color(self.get_parameter('initial_color').value)
        self.get_logger().info("Sentiment Node initialized with VADER.")

    def text_callback(self, msg: String):
        """
        Analyze incoming text and publish score and color.

        :param msg: String message containing text.
        """
        if not msg.data:
            return

        t_start = time.perf_counter()

        # Accumulate context for better nuance in streams
        self.context_buffer += msg.data
        max_buf = self.get_parameter('buffer_size').value
        if len(self.context_buffer) > max_buf:
            self.context_buffer = self.context_buffer[-max_buf:]

        # VADER returns compound score between -1 and 1
        scores = self.analyzer.polarity_scores(self.context_buffer)
        new_compound = scores['compound']

        # Exponential smoothing (Leaky Integrator)
        alpha = self.get_parameter('smooth_alpha').value
        self.last_compound = (alpha * new_compound) + ((1.0 - alpha) * self.last_compound)

        # Map -1..1 to 0..1 for colormap
        # 0.0 (negative) -> 1.0 (positive)
        norm_score = (self.last_compound + 1.0) / 2.0

        # Publish Score
        score_msg = Float32()
        score_msg.data = float(norm_score)
        self.pub_score.publish(score_msg)

        # Get color from cmap and publish
        rgba = self.cmap(norm_score)
        self.publish_color(rgba)

        # Performance measurement and debug logging
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        self.log_debug_details(msg.data, scores, norm_score, elapsed_ms)

    def log_debug_details(self, text, scores, norm_score, elapsed_ms):
        """
        Log detailed sentiment analysis info for debugging.

        Only processed if ROS 2 log level is set to DEBUG.
        """
        self.get_logger().debug("--- Sentiment Analysis Debug ---")
        self.get_logger().debug(f"Input Token: '{text}'")
        self.get_logger().debug(f"Buffer Content (last 50): '...{self.context_buffer[-50:]}'")
        self.get_logger().debug(f"VADER Raw (Buffer): {scores['compound']:.4f}")
        self.get_logger().debug(f"Smoothed Compound: {self.last_compound:.4f}")
        self.get_logger().debug(f"Float Value (Mapped): {norm_score:.4f}")
        self.get_logger().debug(f"Computing Time: {elapsed_ms:.2f} ms")
        self.get_logger().debug("--------------------------------")

    def publish_color(self, rgba_list):
        """
        Convert a list/tuple to ColorRGBA and publish.

        :param rgba_list: List/tuple of [r, g, b, a].
        """
        color_msg = ColorRGBA()
        color_msg.r = float(rgba_list[0])
        color_msg.g = float(rgba_list[1])
        color_msg.b = float(rgba_list[2])
        color_msg.a = float(rgba_list[3])
        self.pub_color.publish(color_msg)


def main(args=None):
    rclpy.init(args=args)
    node = SentimentNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
