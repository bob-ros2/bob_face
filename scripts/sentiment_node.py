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
import time

import huggingface_hub
import numpy as np
from matplotlib import colormaps
import onnxruntime as ort
from rcl_interfaces.msg import ParameterDescriptor, ParameterType
import rclpy
from rclpy.node import Node
from std_msgs.msg import ColorRGBA, Float32, String
from tokenizers import Tokenizer


class SentimentNode(Node):
    """ROS 2 Node for real-time sentiment analysis using ONNX TinyBERT."""

    def __init__(self):
        """Initialize the node, parameters, and download/load the model."""
        super().__init__('sentiment')

        # Declare Parameters
        default_repo = 'Xenova/twitter-xlm-roberta-base-sentiment-multilingual'
        self.declare_parameter(
            'model_repo',
            os.environ.get('SENTIMENT_MODEL_REPO', default_repo),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='HuggingFace repo for multilingual ONNX model.'
            )
        )

        self.declare_parameter(
            'model_dir',
            os.environ.get('SENTIMENT_MODEL_DIR', ''),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Local dir for model storage. (Env: SENTIMENT_MODEL_DIR)'
            )
        )

        self.declare_parameter(
            'cmap_name',
            os.environ.get('SENTIMENT_CMAP_NAME', 'plasma'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Matplotlib colormap name. (Env: SENTIMENT_CMAP_NAME)'
            )
        )

        self.declare_parameter(
            'smooth_alpha',
            float(os.environ.get('SENTIMENT_SMOOTH_ALPHA', '0.3')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Smoothing factor [0.0 to 1.0]. Lower = slower reaction. (Env: SENTIMENT_SMOOTH_ALPHA)'
            )
        )

        self.declare_parameter(
            'sensitivity',
            float(os.environ.get('SENTIMENT_SENSITIVITY', '1.5')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Linear multiplier [0.0 to inf]. Typical: 1.0-3.0. (Env: SENTIMENT_SENSITIVITY)'
            )
        )

        self.declare_parameter(
            'buffer_size',
            int(os.environ.get('SENTIMENT_BUFFER_SIZE', '0')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_INTEGER,
                description='Text buffer size chars [0 to inf]. 0 = disable smoothing. (Env: SENTIMENT_BUFFER_SIZE)'
            )
        )

        self.declare_parameter(
            'temperature',
            float(os.environ.get('SENTIMENT_TEMPERATURE', '1.0')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Logit temperature [> 0.0]. < 1.0 = sharp, > 1.0 = flat. (Env: SENTIMENT_TEMPERATURE)'
            )
        )

        # Internal state
        self.context_buffer = ''
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
            self.get_logger().error(f'Colormap "{name}" not found. Using "plasma".')
            self.cmap = colormaps['plasma']

        # Setup Pub/Sub
        self.pub_score = self.create_publisher(Float32, 'sentiment_score', 10)
        self.pub_color = self.create_publisher(ColorRGBA, 'face_color_override', 10)

        self.sub_text = self.create_subscription(
            String,
            'analize',
            self.text_callback,
            10
        )

        self.get_logger().info('Sentiment Node initialized (Multilingual ONNX).')

    def load_transformer_model(self):
        """Download and load the ONNX model and tokenizer."""
        repo = self.get_parameter('model_repo').value
        local_dir = self.get_parameter('model_dir').value

        # Filename candidates
        onnx_files = [
            'onnx/model_quantized.onnx', 'onnx/model.onnx',
            'model_quantized.onnx', 'model.onnx'
        ]
        tokenizer_file = 'tokenizer.json'

        model_path = None
        tokenizer_path = None

        if local_dir:
            self.get_logger().info(f'Loading model from local directory: {local_dir}')
            os.makedirs(local_dir, exist_ok=True)

            # Try to download/check files
            for f in onnx_files:
                try:
                    self.get_logger().info(f'Trying to find/download: {f}')
                    model_path = huggingface_hub.hf_hub_download(
                        repo_id=repo,
                        filename=f,
                        local_dir=local_dir,
                        local_dir_use_symlinks=False
                    )
                    break
                except Exception:
                    continue

            try:
                tokenizer_path = huggingface_hub.hf_hub_download(
                    repo_id=repo,
                    filename=tokenizer_file,
                    local_dir=local_dir,
                    local_dir_use_symlinks=False
                )
            except Exception as e:
                self.get_logger().error(f'Tokenizer download failed: {e}')

        else:
            self.get_logger().info(f'Loading model from HF cache: {repo}')
            for f in onnx_files:
                try:
                    model_path = huggingface_hub.hf_hub_download(repo_id=repo, filename=f)
                    break
                except Exception:
                    continue
            tokenizer_path = huggingface_hub.hf_hub_download(repo_id=repo, filename=tokenizer_file)

        if not model_path or not os.path.exists(model_path):
            self.get_logger().fatal('Could not find suitable ONNX model file in the repository.')
            raise FileNotFoundError('ONNX model file not found.')

        try:
            # Load ONNX Session
            self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

            # Load Tokenizer
            self.tokenizer = Tokenizer.from_file(tokenizer_path)
            model_base = os.path.basename(model_path)
            self.get_logger().info(f'Model loaded successfully: {model_base}')
        except Exception as e:
            self.get_logger().fatal(f'Failed to initialize ONNX session: {e}')
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

        # Process Logits
        logits = outputs[0][0]
        temp = self.get_parameter('temperature').value
        if temp <= 0:
            temp = 1.0
        logits = logits / temp

        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum()

        # Mapping for Xenova/twitter-xlm-roberta-base-sentiment-multilingual
        # Verified Label Order: {0: "positive", 1: "neutral", 2: "negative"}
        # Target score: positive=1.0, neutral=0.5, negative=0.0
        new_score = (probs[0] * 1.0) + (probs[1] * 0.5) + (probs[2] * 0.0)

        # Apply Sensitivity and Clipping
        compound = (new_score * 2.0) - 1.0
        compound *= self.get_parameter('sensitivity').value
        compound = max(-1.0, min(1.0, compound))

        # Back to 0..1
        new_score = (compound + 1.0) / 2.0

        # Exponential smoothing (Leaky Integrator)
        if max_buf > 0:
            alpha = self.get_parameter('smooth_alpha').value
            self.last_score = (alpha * new_score) + ((1.0 - alpha) * self.last_score)
        else:
            self.last_score = new_score

        # Publish Score
        score_msg = Float32()
        score_msg.data = float(self.last_score)
        self.pub_score.publish(score_msg)

        # Get color from cmap and publish
        rgba = self.cmap(self.last_score)
        self.publish_color(rgba)

        # Performance measurement and debug logging
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        log_msg = f"In: '{msg.data[:30]}...' -> Score: {self.last_score:.3f} ({elapsed_ms:.2f}ms)"
        self.get_logger().debug(log_msg)

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
