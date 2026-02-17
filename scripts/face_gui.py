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
GUI for controlling facial animation sequences.

This module provides a PyQt5-based interface to trigger, add, edit, and delete
facial animation sequences stored in a YAML configuration file.
"""

import sys
import os
import yaml
import signal
import rclpy
from rclpy.node import Node
from ament_index_python.packages import get_package_share_directory
from bob_msgs.srv import SetSequence
from visualization_msgs.msg import MarkerArray
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QSlider, QLabel, QGridLayout,
                             QLineEdit, QSpinBox, QGroupBox, QMessageBox,
                             QScrollArea)
from PyQt5.QtCore import Qt, QTimer


# Handle Ctrl+C properly
def sigint_handler(*args):
    """Handle SIGINT (Ctrl+C) to exit the application gracefully."""
    QApplication.quit()


class FaceGui(QWidget):
    """
    Main GUI window for facial animation control.

    Supports live testing, adding/overwriting sequences, and persistent
    saving to a YAML configuration file.
    """

    def __init__(self):
        """Initialize the ROS 2 node, load configuration, and setup the UI."""
        super().__init__()

        # ROS 2 Node initialization
        if not rclpy.ok():
            rclpy.init()
        self.node = Node('face_gui')

        # Declare parameter for config file
        default_config = os.path.join(
            get_package_share_directory('bob_face'),
            'config', 'sequences.yaml'
        )
        self.node.declare_parameter('sequences_config', default_config)
        param = self.node.get_parameter('sequences_config')
        self.config_path = param.get_parameter_value().string_value

        self.client = self.node.create_client(SetSequence, 'set_sequence')

        # MarkerArray Subscriber for graph connectivity and status
        self.marker_sub = self.node.create_subscription(
            MarkerArray,
            'marker_array',
            self.marker_callback,
            10
        )
        self.marker_count = 0

        # Load config
        self.sequences = []
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = yaml.safe_load(f)
                    self.sequences = data.get('sequences', [])
            except Exception as e:
                print(f"Error loading config: {e}")

        self.init_ui()

        # Timer for ROS 2 spinning (non-blocking)
        self.ros_timer = QTimer()
        self.ros_timer.timeout.connect(self.ros_spin)
        self.ros_timer.start(10)  # 100Hz spin

    def init_ui(self):
        """Set up the window layout, widgets, and styles."""
        self.setWindowTitle(f'Bob Face Control - [{os.path.basename(self.config_path)}]')
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #efefef;
                      font-family: 'Segoe UI', sans-serif; }
            QPushButton { background-color: #333; border: 1px solid #555;
                          padding: 8px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #444; border-color: #007acc; }
            QPushButton:pressed { background-color: #007acc; }
            QLabel { font-size: 14px; }
            QLineEdit, QSpinBox { background-color: #2b2b2b; border: 1px solid #555;
                                  padding: 5px; color: #fff; }
            QGroupBox { border: 1px solid #555; margin-top: 10px; font-weight: bold;
                        padding-top: 15px; }
            QSlider::groove:horizontal { border: 1px solid #999; height: 10px;
                                         background: #333; border-radius: 4px; }
            QSlider::handle:horizontal { background: #007acc; border: 1px solid #555;
                                         width: 22px; margin: -6px 0; border-radius: 11px; }
        """)

        main_layout = QVBoxLayout()

        # --- Presets Section ---
        self.presets_group = QGroupBox("Animation Presets")
        presets_group_layout = QVBoxLayout(self.presets_group)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(250)
        self.scroll_area.setStyleSheet("border: none;")

        self.presets_container = QWidget()
        self.presets_layout = QGridLayout(self.presets_container)
        self.presets_layout.setSpacing(10)
        # Ensure rows are tight
        self.presets_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.presets_container)
        presets_group_layout.addWidget(self.scroll_area)

        self.refresh_presets()
        main_layout.addWidget(self.presets_group)

        # --- Global Controls ---
        ctrl_layout = QHBoxLayout()

        self.rate_label = QLabel("Rate: 30 FPS")
        self.rate_label.setStyleSheet("font-size: 16px; font-weight: bold; min-width: 120px;")
        ctrl_layout.addWidget(self.rate_label)

        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setMinimum(1)
        self.rate_slider.setMaximum(120)
        self.rate_slider.setValue(30)
        self.rate_slider.valueChanged.connect(self.update_rate_label)
        ctrl_layout.addWidget(self.rate_slider)

        main_layout.addLayout(ctrl_layout)

        # --- Editor Section ---
        editor_group = QGroupBox("Sequence Editor")
        editor_layout = QGridLayout(editor_group)

        editor_layout.addWidget(QLabel("Name:"), 0, 0)
        self.edit_name = QLineEdit("New Sequence")
        editor_layout.addWidget(self.edit_name, 0, 1, 1, 3)

        editor_layout.addWidget(QLabel("Start:"), 1, 0)
        self.edit_start = QSpinBox()
        self.edit_start.setRange(0, 100000)
        self.edit_start.setValue(500)
        editor_layout.addWidget(self.edit_start, 1, 1)

        editor_layout.addWidget(QLabel("End:"), 1, 2)
        self.edit_end = QSpinBox()
        self.edit_end.setRange(0, 100000)
        self.edit_end.setValue(1000)
        editor_layout.addWidget(self.edit_end, 1, 3)

        editor_layout.addWidget(QLabel("Type:"), 2, 0)
        self.edit_type = QSpinBox()
        self.edit_type.setValue(1)
        editor_layout.addWidget(self.edit_type, 2, 1)

        btn_test = QPushButton("Test Live")
        btn_test.setStyleSheet("background-color: #444; color: #ffeb3b;")
        btn_test.clicked.connect(self.test_sequence)
        editor_layout.addWidget(btn_test, 2, 2)

        btn_add = QPushButton("Add to List")
        btn_add.setStyleSheet("background-color: #2e7d32; color: #fff;")
        btn_add.clicked.connect(self.add_sequence)
        editor_layout.addWidget(btn_add, 2, 3)

        main_layout.addWidget(editor_group)

        # --- Global Actions ---
        actions_layout = QHBoxLayout()
        btn_save = QPushButton("SAVE CONFIG TO YAML")
        btn_save.setStyleSheet("background-color: #c62828; color: #fff; "
                               "font-size: 16px; padding: 15px;")
        btn_save.clicked.connect(self.save_config)
        actions_layout.addWidget(btn_save)
        main_layout.addLayout(actions_layout)

        # --- Status Line ---
        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet("color: #00ff00; font-size: 18px; font-weight: bold;")
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)
        self.setMinimumWidth(500)

    def refresh_presets(self):
        """Clear and rebuild the animation presets grid based on current sequences."""
        # Clear existing widgets from the layout
        while self.presets_layout.count():
            item = self.presets_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Recursive cleanup for sub-layouts
                self.clear_layout(item.layout())

        cols = 3  # Use 3 columns to fit more items
        for i, seq in enumerate(self.sequences):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)

            # Play & Load Button
            btn_play = QPushButton(seq['name'])
            btn_play.setToolTip(f"Start: {seq['start']}, End: {seq['end']}")
            btn_play.clicked.connect(lambda checked, s=seq: self.preset_clicked(s))
            row_layout.addWidget(btn_play, 4)

            # Delete Button
            btn_del = QPushButton("X")
            btn_del.setFixedWidth(25)
            btn_del.setStyleSheet("background-color: #b71c1c; color: white; padding: 2px;")
            btn_del.clicked.connect(lambda checked, idx=i: self.delete_sequence(idx))
            row_layout.addWidget(btn_del, 1)

            self.presets_layout.addWidget(row_widget, i // cols, i % cols)

    def clear_layout(self, layout):
        """Recursively clear a layout and its sub-widgets."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    self.clear_layout(item.layout())

    def update_rate_label(self, value):
        """Update the rate label text when the slider value changes."""
        self.rate_label.setText(f"Rate: {value} FPS")

    def preset_clicked(self, seq_dict):
        """Populate editor and play sequence."""
        self.edit_name.setText(seq_dict['name'])
        self.edit_start.setValue(seq_dict['start'])
        self.edit_end.setValue(seq_dict['end'])
        self.edit_type.setValue(seq_dict['type'])
        if 'rate' in seq_dict:
            self.rate_slider.setValue(seq_dict['rate'])
        self.call_service(seq_dict)

    def call_service(self, seq_dict):
        """Send a SetSequence service request to the face node."""
        if not self.client.wait_for_service(timeout_sec=1.0):
            self.status_label.setText("Status: Service /set_sequence not available!")
            self.status_label.setStyleSheet("color: #ff4444; font-size: 18px; font-weight: bold;")
            return

        req = SetSequence.Request()
        req.start = seq_dict['start']
        req.end = seq_dict['end']
        req.type = seq_dict['type']
        req.rate = self.rate_slider.value()  # Use the slider override

        self.status_label.setText(f"Status: Sending {seq_dict['name']}...")
        self.status_label.setStyleSheet("color: #007acc; font-size: 18px; font-weight: bold;")

        future = self.client.call_async(req)
        future.add_done_callback(self.service_callback)

    def service_callback(self, future):
        """Handle the result of a service call."""
        try:
            response = future.result()
            if not response.error:
                self.status_label.setText("Status: Sequence accepted")
                self.status_label.setStyleSheet("color: #00ff00; font-size: 18px; "
                                                "font-weight: bold;")
            else:
                self.status_label.setText(f"Status Error: {response.error}")
                self.status_label.setStyleSheet(
                    "color: #ff4444; font-size: 18px; font-weight: bold;"
                )
        except Exception as e:
            self.status_label.setText(f"Status Exception: {str(e)}")
            self.status_label.setStyleSheet("color: #ff4444; font-size: 18px; font-weight: bold;")

    def marker_callback(self, msg):
        """Handle incoming MarkerArray messages (status monitoring)."""
        self.marker_count += 1
        # No heavy processing here, just heartbeat awareness
        if self.marker_count % 30 == 0:
            self.node.get_logger().debug(f"Received MarkerArray frame {self.marker_count}")

    def test_sequence(self):
        """Trigger a temporary 'TEST' sequence using current editor values."""
        temp_seq = {
            'name': 'TEST',
            'start': self.edit_start.value(),
            'end': self.edit_end.value(),
            'type': self.edit_type.value()
        }
        self.call_service(temp_seq)

    def add_sequence(self):
        """Add the current editor configuration to the sequence list or update existing one."""
        name = self.edit_name.text()
        new_seq = {
            'name': name,
            'start': self.edit_start.value(),
            'end': self.edit_end.value(),
            'type': self.edit_type.value(),
            'rate': self.rate_slider.value()
        }

        # Overwrite if exists, otherwise append
        existing_idx = -1
        for idx, s in enumerate(self.sequences):
            if s['name'] == name:
                existing_idx = idx
                break

        if existing_idx >= 0:
            self.sequences[existing_idx] = new_seq
            self.status_label.setText(f"Status: Updated {name}")
        else:
            self.sequences.append(new_seq)
            self.status_label.setText(f"Status: Added {name}")

        self.refresh_presets()

    def delete_sequence(self, index):
        """Remove a sequence from the list by its index."""
        if 0 <= index < len(self.sequences):
            name = self.sequences[index]['name']
            del self.sequences[index]
            self.refresh_presets()
            self.status_label.setText(f"Status: Deleted {name}")

    def save_config(self):
        """Persist the current sequence list to the YAML configuration file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump({'sequences': self.sequences}, f, default_flow_style=False)
            self.status_label.setText("Status: Config SAVED to YAML!")
            self.status_label.setStyleSheet("color: #00ff00; font-size: 18px; font-weight: bold;")
            QMessageBox.information(self, "Success", f"Config saved to:\n{self.config_path}")
        except Exception as e:
            self.status_label.setText(f"Save Error: {str(e)}")
            self.status_label.setStyleSheet("color: #ff4444; font-size: 18px; font-weight: bold;")

    def ros_spin(self):
        """Process ROS 2 callbacks periodically."""
        if rclpy.ok():
            rclpy.spin_once(self.node, timeout_sec=0)

    def closeEvent(self, event):
        """Ensure clean shutdown of ROS 2 when the window is closed."""
        self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        event.accept()


if __name__ == '__main__':
    # Add signal handler
    signal.signal(signal.SIGINT, sigint_handler)

    app = QApplication(sys.argv)

    # Use a QTimer to periodically process signals (allows Ctrl+C to be caught)
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    gui = FaceGui()
    gui.show()

    # Catching KeyboardInterrupt to exit gracefully
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        pass
