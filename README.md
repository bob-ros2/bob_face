# ROS Package [bob_face](https://github.com/bob-ros2/bob_face)
[![ROS2 CI](https://github.com/bob-ros2/bob_face/actions/workflows/ros2_ci.yaml/badge.svg)](https://github.com/bob-ros2/bob_face/actions/workflows/ros2_ci.yaml)
[![amd64](https://img.shields.io/github/actions/workflow/status/bob-ros2/bob_face/docker.yml?label=amd64&logo=docker)](https://github.com/bob-ros2/bob_face/actions/workflows/docker.yml)
[![arm64](https://img.shields.io/github/actions/workflow/status/bob-ros2/bob_face/docker.yml?label=arm64&logo=docker)](https://github.com/bob-ros2/bob_face/actions/workflows/docker.yml)

ROS 2 package for facial animation playback and sentiment-driven color orchestration.

## Features
- **Animation Engine (C++)**: Blended playback of `MarkerArray` face geometry from rosbag2.
- **Sentiment Logic (Python)**: ONNX-based TinyBERT sentiment analysis for deep context awareness.
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
- **Engine**: ONNX Runtime (TinyBERT)
- **Parameters**: `model_repo`, `sensitivity`, `smooth_alpha`

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

| Node | Parameter | Default | Description |
|------|-----------|---------|-------------|
| `sentiment` | `model_repo` | `Xenova/distilbert-multi...` | HF repository for the multilingual ONNX model. |
| `sentiment` | `model_dir` | `""` | Local directory for storing/loading the model. |
| `sentiment` | `sensitivity` | `1.5` | Linear multiplier [0.0 to inf]. Typical: 1.0-3.0. |
| `sentiment` | `smooth_alpha` | `0.3` | Smoothing factor [0.0 to 1.0]. Lower is slower. |
| `sentiment` | `temperature` | `1.0` | Logit temperature [> 0.0]. < 1.0 = sharp, > 1.0 = flat. |
| `sentiment` | `buffer_size` | `0` | Buffer size in chars [0 to inf]. 0 = disables smoothing. |
| `motion_manager`| `seconds_per_char` | `0.07` | Heuristic for speaking duration. |
| `motion_manager`| `idle_sequences`| `""` | Comma-separated idle sequence names. |
| `motion_manager`| `speaking_sequences`| `""` | Comma-separated speaking sequence names. |

## Sentiment Tuning

To fine-tune Bob's emotional response, use the following parameters:

### `temperature` (Logit Scaling)
The model outputs raw "logits" before converting them to probabilities. `temperature` scales these values:
*   **Range: `> 0.0`** (Avoid exactly 0).
*   **`0.1` to `0.7`**: High contrast. Bob becomes very "opinionated," quickly reaching deep red or bright green.
*   **`1.0`**: Default behavior of the model.
*   **`1.5` to `5.0`**: "Calm" mode. Responses flatten out, keeping Bob mostly in the yellow/orange (neutral) zone.

### `sensitivity`
A linear secondary boost. While temperature changes the model's certainty, sensitivity simply stretches the final result.
*   **Range: `>= 0.0`**.
*   If Bob is still too "pale" even with low temperature, increase this to `2.0` or `3.0`.

### `smooth_alpha` & `buffer_size`
*   **Instant Burst (`buffer_size := 0`)**: Disables the Leaky Integrator. Bob reacts to every single sentence immediately.
*   **Atmospheric Mood (`buffer_size > 0`)**: Enables a moving average. Bob maintains a "mood" based on the last `X` characters. `smooth_alpha` determines the inertia (e.g., `0.1` is very slow/stable, `0.9` is fast).

## Requirements
- Python: `onnxruntime`, `tokenizers`, `matplotlib`, `PyQt5`, `PyYAML`, `numpy<2`
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
