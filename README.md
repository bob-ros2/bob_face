# ROS Package [bob_face](https://github.com/bob-ros2/bob_face)

ROS 2 package for facial animation playback and sentiment-driven color orchestration.

## Features
- **Animation Engine (C++)**: Blended playback of `MarkerArray` face geometry from rosbag2.
- **Sentiment Logic (Python)**: VADER-based sentiment analysis mapped to Matplotlib colormaps.
- **Marker Colorizer (C++)**: Real-time RGBA override for visualization markers.
- **Sequence GUI (Python)**: PyQt5 interface for triggering and managing animation sequences.

## Components

### `bag` (Node)
Playback engine for facial geometry.
- **Subscribes**: N/A
- **Publishes**: `face_marker_array` (`visualization_msgs/MarkerArray`)
- **Services**: `set_sequence` (`bob_msgs/SetSequence`)

### `face_marker` (Node)
Applies sentiment color to incoming markers.
- **Subscribes**: `marker_array_in` (`visualization_msgs/MarkerArray`), `face_color_override` (`std_msgs/ColorRGBA`)
- **Publishes**: `marker_array_out` (`visualization_msgs/MarkerArray`)

### `sentiment` (Node)
Text-to-color mapping.
- **Subscribes**: `analize` (`std_msgs/String`)
- **Publishes**: `face_color_override` (`std_msgs/ColorRGBA`), `sentiment_score` (`std_msgs/Float32`)

### `motion_manager` (Node)
Automation of facial states (Speaking/Idle).
- **Subscribes**: `spoken_text` (`std_msgs/String`), `speaking_flag` (`std_msgs/Bool`)
- **Services**: `set_sequence` (Client: calls the `bag` node)

### `face_gui` (Node)
Interactive sequence editor and manual control.
- **Services**: `set_sequence` (Client)
- **Files**: Reads/Writes `config/sequences.yaml`

## Configuration (face.yaml)
Standard integration flow:
`bag` (out: `marker_array_raw`) -> `face_marker` (in: `marker_array_raw`, out: `marker_array`) -> `face_gui` & RViz.

## Parameters

| Node | Parameter | Default | Env Var | Description |
|------|-----------|---------|---------|-------------|
| `sentiment` | `cmap_name` | `plasma` | `SENTIMENT_CMAP_NAME` | Matplotlib colormap |
| `face_marker` | `marker_scale` | `0.0` | `MARKER_SCALE` | Global scale override |
| `face_marker` | `fixed_frame` | `""` | `MARKER_FIXED_FRAME` | Frame ID override |
| `motion_manager`| `seconds_per_char` | `0.07` | `MOTION_SECONDS_PER_CHAR` | Heuristic for speaking duration |
| `motion_manager`| `idle_sequences`| `""` | - | Comma-separated idle sequence names |
| `motion_manager`| `speaking_sequences`| `""` | - | Comma-separated speaking sequence names |

## Requirements
- Python: `vaderSentiment`, `matplotlib`, `PyQt5`, `PyYAML`
- ROS 2: `rclcpp`, `rclpy`, `visualization_msgs`, `bob_msgs`

## Quick Start
```bash
# Install Python deps
pip install -r requirements.txt

# Launch system
ros2 launch bob_launch generic.launch.py config:=face.yaml

# Test Sentiment
ros2 topic pub /bob/analize std_msgs/msg/String "{data: 'Excellent work'}" -1
```
