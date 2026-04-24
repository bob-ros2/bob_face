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
- **Dynamic Tuning**: Adjust behavior at runtime via ROS parameters or Environment Variables.

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
Text-to-color mapping. Performs context-aware analysis using ONNX models.
- **Subscribes**: `analize` (`std_msgs/String`)
- **Publishes**: `face_color_override` (`std_msgs/ColorRGBA`), `sentiment_score` (`std_msgs/Float32`)

### `motion_manager` (Node) / `motion_node`
Automation of facial states (Speaking/Idle).
- **Subscribes**: `spoken_text` (`std_msgs/String`), `speaking_flag` (`std_msgs/Bool`)
- **Services**: `set_sequence` (Client: calls the `bag` node)

### `face_gui` (Node)
Interactive sequence editor and manual control.
- **Services**: `set_sequence` (Client)
- **Files**: Reads/Writes `config/sequences.yaml`

## Parameters & Environment Variables

All nodes support standard ROS parameters which can also be initialized via Environment Variables (useful for Docker deployments).

### Sentiment Parameters
| Parameter | Env Variable | Default | Description |
|-----------|--------------|---------|-------------|
| `model_repo` | `SENTIMENT_MODEL_REPO` | `Xenova/twitter-xlm-roberta-base-sentiment-multilingual` | HF model repository. |
| `model_dir` | `SENTIMENT_MODEL_DIR` | `""` | Local directory for model storage. |
| `sensitivity` | `SENTIMENT_SENSITIVITY` | `2.5` | [Dynamic] Multiplier (spread). |
| `smooth_alpha` | `SENTIMENT_SMOOTH_ALPHA` | `0.5` | [Dynamic] Smoothing [0..1]. |
| `temperature` | `SENTIMENT_TEMPERATURE` | `1.0` | [Dynamic] Logit scaling [>0]. |
| `buffer_size` | `SENTIMENT_BUFFER_SIZE` | `80` | [Dynamic] Character buffer. |
| `cmap_name` | `SENTIMENT_CMAP_NAME` | `RdYlGn` | Matplotlib colormap. |

### Motion Parameters
| Parameter | Env Variable | Default | Description |
|-----------|--------------|---------|-------------|
| `sequences_config` | `MOTION_SEQUENCES_CONFIG` | `.../sequences.yaml` | Path to sequences file. |
| `seconds_per_char` | `MOTION_SECONDS_PER_CHAR` | `0.07` | [Dynamic] s/char heuristic. |
| `min_idle_duration` | `MOTION_MIN_IDLE_DURATION` | `5.0` | [Dynamic] Min idle pause. |
| `max_idle_duration` | `MOTION_MAX_IDLE_DURATION` | `15.0` | [Dynamic] Max idle pause. |
| `speaking_sequences`| `MOTION_SPEAKING_SEQUENCES`| `""` | [Dynamic] Comma-separated names. |
| `idle_sequences`    | `MOTION_IDLE_SEQUENCES`    | `""` | [Dynamic] Comma-separated names. |

## Sentiment Tuning (Lessons Learned)

Through extensive testing, we found the following "sweet spot" settings:

### 1. The "Mood" Persistence (Buffer & Smoothing)
*   **Recommendation**: Use **`buffer_size := 80`** (approx. one sentence).
*   **Inertia**: Use **`smooth_alpha := 0.5`**. This mimics human emotion inertia.

### 2. Clarity vs. Neutrality (Temperature)
*   **Recommendation**: Use **`temperature := 1.0`**. Lower values makes Bob more "extreme", higher values more neutral.

### 3. Stretching the Spectrum (Sensitivity)
*   If Bob stays too "pale" (yellow), increase **`sensitivity`** to **`2.5` - `3.0`**.

## Model Choice & Alternatives

1.  **[XLM-RoBERTa (Default)](https://huggingface.co/Xenova/twitter-xlm-roberta-base-sentiment-multilingual)**: 
    *   **Label Order**: `0: Negative`, `1: Neutral`, `2: Positive`.
    *   **Pros**: Excellent nuanced understanding of German and English. Recommended.

## Requirements
- Python: `onnxruntime`, `tokenizers`, `matplotlib`, `PyQt5`, `PyYAML`, `numpy<2`
- ROS 2: `rclcpp`, `rclpy`, `visualization_msgs`, `bob_msgs`

## Installation & Build

### Docker (Recommended)
Official images for **amd64** and **arm64**:
```bash
docker pull ghcr.io/bob-ros2/bob-face:latest

# Example run with env overrides
docker run -it --rm --network host \
  -e MOTION_SECONDS_PER_CHAR=0.05 \
  -e SENTIMENT_SENSITIVITY=3.0 \
  ghcr.io/bob-ros2/bob-face:latest
```

### Manual Build
```bash
cd ~/ros2_ws/src
git clone https://github.com/bob-ros2/bob_face.git
cd ..
rosdep install --from-paths src --ignore-src -r -y
pip install -r src/bob_face/requirements.txt
colcon build --packages-select bob_face
```
