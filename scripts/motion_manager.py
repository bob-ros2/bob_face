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
Motion Orchestration Node for Bob.

Automates facial animations by switching between 'Speaking' and 'Idle' states
based on activity on the spoken_text topic or speaking_flag.
"""

import os
import random
import sys

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from bob_msgs.srv import SetSequence
from rcl_interfaces.msg import ParameterDescriptor, ParameterType, SetParametersResult
from rclpy.node import Node
from std_msgs.msg import Bool, String


class MotionNode(Node):
    """
    ROS 2 Node for managing facial motion states.

    Orchestrates animations by monitoring TTS output (spoken_text) or
    explicit speaking flags (speaking_flag).
    """

    def __init__(self):
        """Initialize parameters, load sequences, and setup communication."""
        super().__init__('motion_node')

        # Declare parameters
        default_config = os.path.join(
            get_package_share_directory('bob_face'),
            'config', 'sequences.yaml'
        )
        self.declare_parameter(
            'sequences_config',
            default_config,
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Path to the sequences YAML configuration.'
            )
        )

        self.declare_parameter(
            'seconds_per_char',
            float(os.environ.get('MOTION_SECONDS_PER_CHAR', '0.07')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Heuristic for speaking duration calculation.'
            )
        )

        speed = self.get_parameter('seconds_per_char').value
        self.get_logger().info(f"Using speed: {speed} s/char")

        self.declare_parameter(
            'min_idle_duration',
            5.0,
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Minimum time between random idle animations.'
            )
        )

        self.declare_parameter(
            'max_idle_duration',
            15.0,
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Maximum time between random idle animations.'
            )
        )

        self.declare_parameter(
            'speaking_sequences',
            '',
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Comma-separated list of sequence names for speaking.'
            )
        )

        self.declare_parameter(
            'idle_sequences',
            '',
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Comma-separated list of sequence names for idle.'
            )
        )

        # Load and parse sequences
        self.all_sequences = self.load_sequences()
        self.speaking_pool = []
        self.idle_pool = []
        self.parse_sequence_groups()

        # State tracking
        self.is_speaking = False
        self.current_timer = None
        self.idle_timer = None
        self.last_speaking_flag = False

        # Communication
        self.client = self.create_client(SetSequence, 'set_sequence')
        self.sub_spoken = self.create_subscription(
            String, 'spoken_text', self.spoken_callback, 10)
        self.sub_flag = self.create_subscription(
            Bool, 'speaking_flag', self.flag_callback, 10)

        # Parameter callback for dynamic reconfiguration
        self.add_on_set_parameters_callback(self.parameter_callback)

        # Start initial idle behavior
        self.start_idle_timer()
        self.get_logger().info("Motion Manager initialized.")

    def flag_callback(self, msg: Bool):
        """
        Handle explicit speaking flag updates.

        :param msg: Boolean message indicating speaking state.
        """
        if msg.data == self.last_speaking_flag:
            return

        self.last_speaking_flag = msg.data
        self.get_logger().info(f"Speaking flag changed to: {msg.data}")

        if msg.data:
            self.is_speaking = True
            self.stop_timers()
            if self.speaking_pool:
                self.trigger_sequence(random.choice(self.speaking_pool))
        else:
            self.stop_speaking_callback()

    def spoken_callback(self, msg: String):
        """
        Trigger speaking state based on incoming text (Heuristic mode).

        :param msg: String message containing spoken text.
        """
        if not msg.data:
            return

        # Check for flag publishers
        if self.count_publishers('speaking_flag') > 0:
            self.get_logger().debug(
                "Speaking flag publishers detected. Ignoring spoken_text heuristic.")
            return

        # Calculate duration
        duration = len(msg.data) * self.get_parameter('seconds_per_char').value
        text_preview = msg.data[:20]
        self.get_logger().info(
            f"Speaking detected: '{text_preview}...' "
            f"(Estimated duration: {duration:.2f}s)")

        self.is_speaking = True
        self.stop_timers()

        # Call service with random speaking sequence
        if self.speaking_pool:
            self.trigger_sequence(random.choice(self.speaking_pool))

        # Set timer to return to idle
        self.current_timer = self.create_timer(duration, self.stop_speaking_callback)

    def load_sequences(self):
        """
        Load sequences from YAML file.

        :return: List of sequence dictionaries.
        """
        config_path = self.get_parameter('sequences_config').value
        if not os.path.exists(config_path):
            self.get_logger().error(f"Sequences config not found: {config_path}")
            sys.exit(1)

        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
                seqs = data.get('sequences', [])
                if not seqs:
                    self.get_logger().error("No sequences found in YAML.")
                    sys.exit(1)
                return seqs
        except Exception as e:
            self.get_logger().error(f"Error loading YAML: {e}")
            sys.exit(1)

    def parse_sequence_groups(self):
        """Build speaking and idle pools based on parameters or fallbacks."""
        speak_str = self.get_parameter('speaking_sequences').value
        idle_str = self.get_parameter('idle_sequences').value

        if not speak_str and not idle_str:
            # Fallback logic
            self.get_logger().info("No sequence groupings defined. Using fallback logic.")
            self.speaking_pool = [self.all_sequences[0]]
            if len(self.all_sequences) > 1:
                self.idle_pool = self.all_sequences[1:]
            else:
                self.idle_pool = [self.all_sequences[0]]
        else:
            # Parse comma-separated strings
            speak_names = [s.strip() for s in speak_str.split(',') if s.strip()]
            idle_names = [s.strip() for s in idle_str.split(',') if s.strip()]

            for seq in self.all_sequences:
                if seq['name'] in speak_names:
                    self.speaking_pool.append(seq)
                if seq['name'] in idle_names:
                    self.idle_pool.append(seq)

        if not self.speaking_pool:
            self.get_logger().warn("Speaking pool is empty! Using fallback.")
            self.speaking_pool = [self.all_sequences[0]]
        if not self.idle_pool:
            self.get_logger().warn("Idle pool is empty! Using all as fallback.")
            self.idle_pool = self.all_sequences

        self.get_logger().info(
            f"Loaded {len(self.speaking_pool)} speaking and "
            f"{len(self.idle_pool)} idle sequences.")

    def parameter_callback(self, params):
        """
        Handle dynamic parameter updates.

        :param params: List of updated parameters.
        :return: SetParametersResult indicating success.
        """
        rebuild_pools = False
        for param in params:
            if param.name in ['speaking_sequences', 'idle_sequences']:
                rebuild_pools = True
            self.get_logger().info(f"Parameter '{param.name}' updated to: {param.value}")

        if rebuild_pools:
            self.parse_sequence_groups()

        return SetParametersResult(successful=True)

    def stop_speaking_callback(self):
        """Return to idle state after speaking duration elapses."""
        self.get_logger().info("Speaking finished. Returning to idle.")
        self.is_speaking = False
        self.stop_timers()
        self.start_idle_timer()

    def start_idle_timer(self):
        """Schedule next random idle animation."""
        if self.is_speaking:
            return

        # Trigger one now
        if self.idle_pool:
            self.trigger_sequence(random.choice(self.idle_pool))

        # Schedule next
        wait = random.uniform(
            self.get_parameter('min_idle_duration').value,
            self.get_parameter('max_idle_duration').value
        )
        self.idle_timer = self.create_timer(wait, self.idle_anim_callback)

    def idle_anim_callback(self):
        """Trigger a random idle animation and reschedule."""
        if self.is_speaking:
            return

        if self.idle_pool:
            self.trigger_sequence(random.choice(self.idle_pool))

        # Reschedule with new random duration
        self.stop_timers()
        self.start_idle_timer()

    def trigger_sequence(self, seq):
        """
        Send service call to trigger a sequence.

        :param seq: Sequence dictionary.
        """
        if not self.client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn("Service set_sequence not available.")
            return

        req = SetSequence.Request()
        req.start = int(seq['start'])
        req.end = int(seq['end'])
        req.rate = int(seq.get('rate', 30))
        req.type = int(seq.get('type', 1))

        self.client.call_async(req)

    def stop_timers(self):
        """Cancel both speaking and idle timers."""
        if self.current_timer:
            self.current_timer.cancel()
            self.destroy_timer(self.current_timer)
            self.current_timer = None
        if self.idle_timer:
            self.idle_timer.cancel()
            self.destroy_timer(self.idle_timer)
            self.idle_timer = None


def main(args=None):
    rclpy.init(args=args)
    node = MotionNode()
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
