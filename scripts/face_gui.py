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
GUI for editing facial animation sequences.

Provides a ROS 2 interface to save and test animation ranges.
"""

import os
import signal
import sys

from ament_index_python.packages import get_package_share_directory
from bob_msgs.srv import SetSequence
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton,
                             QScrollArea, QSlider, QSpinBox, QVBoxLayout,
                             QWidget)
import rclpy
from rclpy.node import Node
import yaml


class SequenceGUI(QWidget):
    """
    Main GUI window for facial sequence editing.

    Manages a list of sequence widgets and allows saving to YAML.
    """

    def __init__(self, node):
        """
        Initialize the GUI.

        :param node: The ROS2 node used for service calls.
        """
        super().__init__()
        self.node = node
        self.sequences = []
        self.init_ui()
        self.load_sequences()

    def init_ui(self):
        """Set up the layout and widgets."""
        self.setWindowTitle('Bob Face Sequence Editor')
        self.resize(800, 600)

        main_layout = QVBoxLayout()

        # Config Path
        self.path_edit = QLineEdit()
        default_path = os.path.join(
            get_package_share_directory('bob_face'),
            'config', 'sequences.yaml'
        )
        self.path_edit.setText(default_path)
        main_layout.addWidget(QLabel('Config Path:'))
        main_layout.addWidget(self.path_edit)

        # Scroll Area for Sequences
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        # Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton('Add Sequence')
        add_btn.clicked.connect(self.add_sequence)
        save_btn = QPushButton('Save to YAML')
        save_btn.clicked.connect(self.save_sequences)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(save_btn)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

    def load_sequences(self):
        """Load sequences from the specified YAML file."""
        path = self.path_edit.text()
        if not os.path.exists(path):
            return

        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
                if data and 'sequences' in data:
                    for seq_data in data['sequences']:
                        self.add_sequence(seq_data)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to load YAML: {e}')

    def add_sequence(self, data=None):
        """
        Add a new sequence widget to the list.

        :param data: Optional dictionary containing initial sequence values.
        """
        seq_widget = SequenceItemWidget(self.node, data)
        self.scroll_layout.insertWidget(self.scroll_layout.count(), seq_widget)
        self.sequences.append(seq_widget)

    def save_sequences(self):
        """Save all sequences to the YAML file."""
        path = self.path_edit.text()
        data = {'sequences': []}
        for seq in self.sequences:
            if seq.name_edit.text():
                data['sequences'].append({
                    'name': seq.name_edit.text(),
                    'start': seq.start_spin.value(),
                    'end': seq.end_spin.value(),
                    'rate': seq.rate_spin.value(),
                    'type': seq.type_spin.value()
                })

        try:
            with open(path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
            QMessageBox.information(self, 'Success', f'Saved to {path}')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to save: {e}')


class SequenceItemWidget(QGroupBox):
    """A widget representing a single animation sequence."""

    def __init__(self, node, data=None):
        """
        Initialize the sequence widget.

        :param node: The ROS2 node for triggering sequences.
        :param data: Initial data for the sequence.
        """
        super().__init__()
        self.node = node
        self.init_ui(data)

    def init_ui(self, data):
        """
        Set up the sequence widget UI.

        :param data: Initial data dictionary.
        """
        layout = QGridLayout()

        # Name
        self.name_edit = QLineEdit()
        if data:
            self.name_edit.setText(data.get('name', ''))
        layout.addWidget(QLabel('Name:'), 0, 0)
        layout.addWidget(self.name_edit, 0, 1)

        # Start/End
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 50000)
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, 50000)
        if data:
            self.start_spin.setValue(data.get('start', 0))
            self.end_spin.setValue(data.get('end', 100))

        layout.addWidget(QLabel('Start:'), 1, 0)
        layout.addWidget(self.start_spin, 1, 1)
        layout.addWidget(QLabel('End:'), 1, 2)
        layout.addWidget(self.end_spin, 1, 3)

        # Sliders for visual range
        self.start_slider = QSlider(Qt.Horizontal)
        self.start_slider.setRange(0, 2000)
        self.start_slider.setValue(self.start_spin.value())
        self.start_slider.valueChanged.connect(self.start_spin.setValue)
        self.start_spin.valueChanged.connect(self.start_slider.setValue)

        self.end_slider = QSlider(Qt.Horizontal)
        self.end_slider.setRange(0, 2000)
        self.end_slider.setValue(self.end_spin.value())
        self.end_slider.valueChanged.connect(self.end_spin.setValue)
        self.end_spin.valueChanged.connect(self.end_slider.setValue)

        layout.addWidget(self.start_slider, 2, 0, 1, 4)
        layout.addWidget(self.end_slider, 3, 0, 1, 4)

        # Rate and Type
        self.rate_spin = QSpinBox()
        self.rate_spin.setValue(30)
        self.type_spin = QSpinBox()
        self.type_spin.setValue(1)
        if data:
            self.rate_spin.setValue(data.get('rate', 30))
            self.type_spin.setValue(data.get('type', 1))

        layout.addWidget(QLabel('Rate:'), 4, 0)
        layout.addWidget(self.rate_spin, 4, 1)
        layout.addWidget(QLabel('Type:'), 4, 2)
        layout.addWidget(self.type_spin, 4, 3)

        # Actions
        test_btn = QPushButton('Test')
        test_btn.clicked.connect(self.test_sequence)
        del_btn = QPushButton('Delete')
        del_btn.clicked.connect(self.deleteLater)

        layout.addWidget(test_btn, 5, 0, 1, 2)
        layout.addWidget(del_btn, 5, 2, 1, 2)

        self.setLayout(layout)

    def test_sequence(self):
        """Call set_sequence service with current widget values."""
        if not rclpy.ok():
            return

        client = self.node.create_client(SetSequence, 'set_sequence')
        if not client.wait_for_service(timeout_sec=1.0):
            QMessageBox.warning(self, 'Error', 'Service not available')
            return

        req = SetSequence.Request()
        req.start = self.start_spin.value()
        req.end = self.end_spin.value()
        req.rate = self.rate_spin.value()
        req.type = self.type_spin.value()

        client.call_async(req)


class GuiNode(Node):
    """Minimal ROS 2 node to host GUI service calls."""

    def __init__(self):
        """Initialize the node."""
        super().__init__('face_gui')


def main():
    """Start the GUI and ROS 2 spin loop."""
    # Required for Ctrl+C to work
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    rclpy.init()
    node = GuiNode()

    app = QApplication(sys.argv)
    gui = SequenceGUI(node)
    gui.show()

    # Periodically process ROS events
    timer = QTimer()
    timer.timeout.connect(lambda: rclpy.spin_once(node, timeout_sec=0))
    timer.start(10)

    try:
        sys.exit(app.exec_())
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
