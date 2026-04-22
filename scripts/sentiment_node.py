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
Sentiment Analysis Node for Bob using ONNX TinyBERT.

This node performs high-quality sentiment analysis using a Transformer model
exported to ONNX, providing context-aware awareness without heavy dependencies.
"""

import os
import json
import time
import rclpy
import numpy as np
from rclpy.node import Node
from rcl_interfaces.msg import ParameterDescriptor, ParameterType
from std_msgs.msg import String, Float32, ColorRGBA
from matplotlib import colormaps

# ONNX and Tokenizer imports
import onnxruntime as ort
from tokenizers import Tokenizer
from huggingface_hub import hf_hub_download


class SentimentNode(Node):
    """
    ROS 2 Node for real-time sentiment analysis using ONNX TinyBERT.
    """

    def __init__(self):
        """Initialize the node, parameters, and download/load the model."""
        super().__init__('sentiment')

        # Declare Parameters
        self.declare_parameter(
            'model_repo',
            os.environ.get('SENTIMENT_MODEL_REPO', 'Xenova/tiny-bert-sst2-distilled'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='HuggingFace repository for the ONNX model. (Env: SENTIMENT_MODEL_REPO)'
            )
        )

        self.declare_parameter(
            'model_dir',
            os.environ.get('SENTIMENT_MODEL_DIR', ''),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Local directory to store/load the model. (Env: SENTIMENT_MODEL_DIR)'
            )
        )

        self.declare_parameter(
            'cmap_name',
            os.environ.get('SENTIMENT_CMAP_NAME', 'plasma'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='The matplotlib colormap name to use. (Env: SENTIMENT_CMAP_NAME)'
            )
        )

        self.declare_parameter(
            'analize_topic',
            os.environ.get('SENTIMENT_ANALIZE_TOPIC', 'analize'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Topic name for input text strings. (Env: SENTIMENT_ANALIZE_TOPIC)'
            )
        )

        self.declare_parameter(
            'color_topic',
            os.environ.get('SENTIMENT_COLOR_TOPIC', 'face_color_override'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Topic name for the output color override. (Env: SENTIMENT_COLOR_TOPIC)'
            )
        )

        self.declare_parameter(
            'smooth_alpha',
            float(os.environ.get('SENTIMENT_SMOOTH_ALPHA', '0.3')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Smoothing factor (0..1). Lower is smoother. (Env: SENTIMENT_SMOOTH_ALPHA)'
            )
        )

        self.declare_parameter(
            'sensitivity',
            float(os.environ.get('SENTIMENT_SENSITIVITY', '1.5')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Sensitivity multiplier for sentiment score. (Env: SENTIMENT_SENSITIVITY)'
            )
        )

        self.declare_parameter(
            'buffer_size',
            int(os.environ.get('SENTIMENT_BUFFER_SIZE', '0')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_INTEGER,
                description='Window for text accumulation. Set to 0 for per-message analysis. (Env: SENTIMENT_BUFFER_SIZE)'
            )
        )

        # Internal state
        self.context_buffer = ""
        self.last_score = 0.5  # Neutral start
        self.session = None
        self.tokenizer = None

        # Load Model and Tokenizer
        self.load_transformer_model()

        # Initialize Colormap
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

        self.get_logger().info("Sentiment Node initialized with TinyBERT ONNX.")

    def load_transformer_model(self):
        """Download and load the ONNX model and tokenizer."""
        repo = self.get_parameter('model_repo').value
        local_dir = self.get_parameter('model_dir').value
        
        if local_dir:
            self.get_logger().info(f"Loading model from local directory: {local_dir}")
            os.makedirs(local_dir, exist_ok=True)
            
            # Use specific local paths
            model_file = "model_quantized.onnx"
            # Some Xenova models have the onnx file in an 'onnx/' subfolder in the repo
            repo_filename = "onnx/model_quantized.onnx"
            tokenizer_filename = "tokenizer.json"
            
            try:
                # Download into local_dir without symlinks
                model_path = hf_hub_download(
                    repo_id=repo, 
                    filename=repo_filename,
                    local_dir=local_dir,
                    local_dir_use_symlinks=False
                )
                tokenizer_path = hf_hub_download(
                    repo_id=repo, 
                    filename=tokenizer_filename,
                    local_dir=local_dir,
                    local_dir_use_symlinks=False
                )
            except Exception as e:
                self.get_logger().error(f"Error downloading to local_dir: {e}")
                # Fallback check: maybe it's already there?
                model_path = os.path.join(local_dir, "onnx", "model_quantized.onnx")
                if not os.path.exists(model_path):
                    model_path = os.path.join(local_dir, "model_quantized.onnx")
                tokenizer_path = os.path.join(local_dir, "tokenizer.json")
        else:
            self.get_logger().info(f"Loading model from HF cache: {repo}")
            model_path = hf_hub_download(repo_id=repo, filename="onnx/model_quantized.onnx")
            tokenizer_path = hf_hub_download(repo_id=repo, filename="tokenizer.json")

        try:
            # Load ONNX Session
            self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

            # Load Tokenizer
            self.tokenizer = Tokenizer.from_file(tokenizer_path)
            self.get_logger().info(f"Transformer model loaded (Model: {os.path.basename(model_path)})")
        except Exception as e:
            self.get_logger().fatal(f"Failed to load transformer model: {e}")
            raise e

    def text_callback(self, msg: String):
        """
        Analyze incoming text using TinyBERT and publish score and color.

        :param msg: String message containing text.
        """
        if not msg.data:
            return

        t_start = time.perf_counter()

        # Decide whether to use buffer or analyze message individually
        max_buf = self.get_parameter('buffer_size').value
        if max_buf > 0:
            self.context_buffer += msg.data
            if len(self.context_buffer) > max_buf:
                self.context_buffer = self.context_buffer[-max_buf:]
            input_text = self.context_buffer
        else:
            input_text = msg.data

        # Tokenization
        encoded = self.tokenizer.encode(input_text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

        # Run Inference
        outputs = self.session.run(None, {
            'input_ids': input_ids,
            'attention_mask': attention_mask
        })

        # Process Logits (Usually [Batch, 2] for SST-2: Negative, Positive)
        logits = outputs[0][0]
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum()
        
        # Calculate raw sentiment score: 0 (Negative) to 1 (Positive)
        # For SST-2: Probs[0] is negative, Probs[1] is positive
        new_score = probs[1]

        # Apply Sensitivity and Clipping
        # Shift to -1..1 first
        compound = (new_score * 2.0) - 1.0
        compound *= self.get_parameter('sensitivity').value
        compound = max(-1.0, min(1.0, compound))
        
        # Back to 0..1
        new_score = (compound + 1.0) / 2.0

        # Exponential smoothing (Leaky Integrator)
        alpha = self.get_parameter('smooth_alpha').value
        self.last_score = (alpha * new_score) + ((1.0 - alpha) * self.last_score)

        # Publish Score
        score_msg = Float32()
        score_msg.data = float(self.last_score)
        self.pub_score.publish(score_msg)

        # Get color from cmap and publish
        rgba = self.cmap(self.last_score)
        self.publish_color(rgba)

        # Performance measurement and debug logging
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        self.get_logger().debug(f"Input: '{msg.data[:30]}...' -> Score: {self.last_score:.3f} ({elapsed_ms:.2f}ms)")

    def publish_color(self, rgba_list):
        """Convert a list/tuple to ColorRGBA and publish."""
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
