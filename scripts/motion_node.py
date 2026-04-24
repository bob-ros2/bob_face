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
Facial Motion Node for Bob.

Orchestrates animations by reacting to spoken text or manual flags.
"""

import os
import random

from ament_index_python.packages import get_package_share_directory
from bob_msgs.srv import SetSequence
from rcl_interfaces.msg import (
    ParameterDescriptor,
    ParameterType,
    SetParametersResult
)
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String
import yaml


class MotionNode(Node):
    """
    ROS 2 Node for controlling facial animations.

    Supports heuristic-based speaking animations and random idle behaviors.
    """

    def __init__(self):
        """Initialize parameters and setup orchestration logic."""
        super().__init__('motion_node')

        # Declare parameters with Environment Variable support
        default_config = os.path.join(
            get_package_share_directory('bob_face'),
            'config', 'sequences.yaml'
        )
        self.declare_parameter(
            'sequences_config',
            os.environ.get('MOTION_SEQUENCES_CONFIG', default_config),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Path to sequences YAML.'
            )
        )

        self.declare_parameter(
            'seconds_per_char',
            float(os.environ.get('MOTION_SECONDS_PER_CHAR', '0.07')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='[Dynamic] Duration multiplier for text heuristic.'
            )
        )

        self.declare_parameter(
            'min_idle_duration',
            float(os.environ.get('MOTION_MIN_IDLE_DURATION', '5.0')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='[Dynamic] Min idle pause.'
            )
        )

        self.declare_parameter(
            'max_idle_duration',
            float(os.environ.get('MOTION_MAX_IDLE_DURATION', '15.0')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='[Dynamic] Max idle pause.'
            )
        )

        self.declare_parameter(
            'speaking_sequences',
            os.environ.get('MOTION_SPEAKING_SEQUENCES', ''),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='[Dynamic] Comma-separated speaking sequences.'
            )
        )

        self.declare_parameter(
            'idle_sequences',
            os.environ.get('MOTION_IDLE_SEQUENCES', ''),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='[Dynamic] Comma-separated idle sequences.'
            )
        )

        # Load and parse sequences
        self.all_sequences = self.load_sequences()
        self.speaking_pool = []
        self.idle_pool = []
        self.parse_sequence_groups()

        # State
        self.is_speaking = False
        self.last_speaking_flag = False
        self.current_timer = None
        self.idle_timer = None

        # Callbacks for dynamic tuning
        self.add_on_set_parameters_callback(self.parameter_callback)

        # Communication
        self.client = self.create_client(SetSequence, 'set_sequence')
        self.sub_spoken = self.create_subscription(
            String, 'spoken_text', self.spoken_callback, 10)
        self.sub_flag = self.create_subscription(
            Bool, 'speaking_flag', self.flag_callback, 10)

        # Boot up behavior
        self.start_idle_timer()
        self.get_logger().info('Motion Node initialized.')

    def flag_callback(self, msg: Bool):
        """
        React to explicit speaking status updates.

        :param msg: Boolean flag.
        """
        if msg.data == self.last_speaking_flag:
            return

        self.last_speaking_flag = msg.data
        if msg.data:
            self.is_speaking = True
            self.stop_timers()
            if self.speaking_pool:
                self.trigger_sequence(random.choice(self.speaking_pool))
        else:
            self.stop_speaking_callback()

    def spoken_callback(self, msg: String):
        """
        Trigger animation based on text length (Heuristic).

        :param msg: Input text string.
        """
        if not msg.data:
            return

        # Heuristic only runs if no flag publishers are present
        if self.count_publishers('speaking_flag') > 0:
            return

        duration = len(msg.data) * self.get_parameter('seconds_per_char').value
        self.is_speaking = True
        self.stop_timers()

        if self.speaking_pool:
            self.trigger_sequence(random.choice(self.speaking_pool))

        self.current_timer = self.create_timer(
            duration, self.stop_speaking_callback)

    def load_sequences(self):
        """Load YAML configuration."""
        path = self.get_parameter('sequences_config').value
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f).get('sequences', [])
        except Exception:
            return []

    def parse_sequence_groups(self, speak_str=None, idle_str=None):
        """
        Build animation pools from parameters.

        :param speak_str: Optional new speaking string.
        :param idle_str: Optional new idle string.
        """
        if speak_str is None:
            speak_str = self.get_parameter('speaking_sequences').value
        if idle_str is None:
            idle_str = self.get_parameter('idle_sequences').value

        self.speaking_pool = []
        self.idle_pool = []

        speak_names = [s.strip() for s in speak_str.split(',') if s.strip()]
        idle_names = [s.strip() for s in idle_str.split(',') if s.strip()]

        for seq in self.all_sequences:
            if not speak_names or seq['name'] in speak_names:
                self.speaking_pool.append(seq)
            if not idle_names or seq['name'] in idle_names:
                self.idle_pool.append(seq)

        if not self.speaking_pool and self.all_sequences:
            self.speaking_pool = [self.all_sequences[0]]
        if not self.idle_pool:
            self.idle_pool = self.all_sequences

    def parameter_callback(self, params):
        """Dynamic parameter handler."""
        new_speak = None
        new_idle = None
        for p in params:
            if p.name == 'speaking_sequences':
                new_speak = p.value
            elif p.name == 'idle_sequences':
                new_idle = p.value

        if new_speak is not None or new_idle is not None:
            self.parse_sequence_groups(new_speak, new_idle)
        return SetParametersResult(successful=True)

    def stop_speaking_callback(self):
        """Transition back to idle state."""
        self.is_speaking = False
        self.stop_timers()
        self.start_idle_timer()

    def start_idle_timer(self):
        """Schedule the next idle movement."""
        if self.is_speaking:
            return

        wait = random.uniform(
            self.get_parameter('min_idle_duration').value,
            self.get_parameter('max_idle_duration').value
        )
        self.idle_timer = self.create_timer(wait, self.idle_anim_callback)

    def idle_anim_callback(self):
        """Trigger idle and reschedule."""
        if self.is_speaking:
            return
        if self.idle_pool:
            self.trigger_sequence(random.choice(self.idle_pool))
        self.stop_timers()
        self.start_idle_timer()

    def trigger_sequence(self, seq):
        """Call animation service."""
        if not self.client.wait_for_service(timeout_sec=0.1):
            return

        req = SetSequence.Request()
        req.start = int(seq['start'])
        req.end = int(seq['end'])
        req.rate = int(seq.get('rate', 30))
        req.type = int(seq.get('type', 1))
        self.client.call_async(req)

    def stop_timers(self):
        """Cleanup timers."""
        if self.current_timer:
            self.current_timer.cancel()
            self.destroy_timer(self.current_timer)
            self.current_timer = None
        if self.idle_timer:
            self.idle_timer.cancel()
            self.destroy_timer(self.idle_timer)
            self.idle_timer = None


def main(args=None):
    """Run the main loop."""
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
