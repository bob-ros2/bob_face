#
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
#

"""Generate launch description for the bag playback node."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for the bag playback node."""
    # use config file if provided
    launch_config_yaml = DeclareLaunchArgument(
        'config_yaml',
        default_value=os.path.join(
            get_package_share_directory('bob_face'),
            'config', 'bag.yaml'))

    # used namespace
    launch_ns = DeclareLaunchArgument(
        'ns',
        default_value='/')

    # bag file path
    launch_bag = DeclareLaunchArgument(
        'bag',
        default_value='rosbag2_face/rosbag2_face.db3')

    return LaunchDescription([
        launch_config_yaml,
        launch_ns,
        launch_bag,
        Node(
            package='bob_face',
            executable='bag',
            name='bag',
            namespace=LaunchConfiguration('ns'),
            parameters=[
                LaunchConfiguration('config_yaml'),
                {'bag': LaunchConfiguration('bag')}
            ],
            output='screen'
        ),
        Node(
            package='tf2_ros',
            name='tf_map_2_face',
            executable='static_transform_publisher',
            arguments=['0.0', '0.0', '1.5', '0', '0', '0', 'map', 'face']
        )
    ])
