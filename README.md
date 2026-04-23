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

### `motion_manager` (Node)
Automation of facial states (Speaking/Idle).
- **Subscribes**: `spoken_text` (`std_msgs/String`), `speaking_flag` (`std_msgs/Bool`)
- **Services**: `set_sequence` (Client: calls the `bag` node)

### `face_gui` (Node)
Interactive sequence editor and manual control.
- **Services**: `set_sequence` (Client)
- **Files**: Reads/Writes `config/sequences.yaml`

## Configuration
Standard integration flow:
`bag` (out: `marker_array_raw`) -> `face_marker` (in: `marker_array_raw`, out: `marker_array`) -> `face_gui` & RViz.

## Parameters

| Node | Parameter | Default | Description |
|------|-----------|---------|-------------|
| `sentiment` | `model_repo` | `Xenova/twitter-xlm-roberta-base-sentiment-multilingual` | Powerful multilingual model (default). |
| `sentiment` | `model_dir` | `""` | Local directory for storing/loading the model. |
| `sentiment` | `sensitivity` | `2.5` | Linear multiplier (spread). Typical 1.0-3.0. |
| `sentiment` | `smooth_alpha` | `0.5` | Smoothing factor [0.0 to 1.0]. |
| `sentiment` | `temperature` | `1.0` | Logit scaling [> 0.0]. |
| `sentiment` | `buffer_size` | `80` | Character buffer [0 = instant, > 0 = context]. |
| `sentiment` | `cmap_name` | `RdYlGn` | Matplotlib colormap (Red-Yellow-Green). |

## Sentiment Tuning (Lessons Learned)

Through extensive testing with the **Bob Face** interface, we found the following "sweet spot" settings for a natural conversational experience:

### 1. The "Mood" Persistence (Buffer & Smoothing)
*   **The Buffer Problem**: A large buffer (`> 150` chars) acts as emotional memory. If Bob hears something deeply negative, he stays "sad" for several sentences until the negative text is pushed out.
*   **Recommendation**: Use **`buffer_size := 80`** (approx. one sentence). This allows Bob to maintain a "current mood" while still being responsive to the next input.
*   **Inertia**: Use **`smooth_alpha := 0.5`**. This mimics human emotion—we don't change from happy to sad in a millisecond, but it shouldn't take minutes either.

### 2. Clarity vs. Neutrality (Temperature)
*   **Keyword Bias**: Models can be "scared" by words like *Asthma* or *Symptom*, even in a positive context. 
*   **Recommendation**: Use **`temperature := 1.0`**. Going lower (e.g., `0.4`) makes Bob more "extreme" and sensitive to keywords, while higher values (e.g., `1.5`) make him more unshakeable/neutral.

### 3. Stretching the Spectrum (Sensitivity)
*   If Bob stays too "pale" (yellow) despite positive/negative input, increase **`sensitivity`** to **`2.5` - `3.0`**. This stretches the internal score away from the center towards the vibrant Red/Green edges of the colormap.

## Model Choice & Alternatives

Different models have different "personalities" and label orders. We verified the following:

1.  **[XLM-RoBERTa (Default)](https://huggingface.co/Xenova/twitter-xlm-roberta-base-sentiment-multilingual)**: 
    *   **Label Order**: `0: Positive`, `1: Neutral`, `2: Negative`.
    *   **Pros**: Excellent nuanced understanding of German and English. Less prone to trivial keyword triggers. Recommended for complex dialogue.
2.  **[DistilBERT Multilingual](https://huggingface.co/Xenova/distilbert-base-multilingual-cased-sentiments-student)**:
    *   **Label Order**: `0: Positive`, `1: Neutral`, `2: Negative`.
    *   **Pros**: Very fast, light-weight.
    *   **Cons**: Higher "Keyword Bias" (e.g., gets scared easily by medical/technical terms regardless of context).

## Requirements
- Python: `onnxruntime`, `tokenizers`, `matplotlib`, `PyQt5`, `PyYAML`, `numpy<2`
- ROS 2: `rclcpp`, `rclpy`, `visualization_msgs`, `bob_msgs`

## Installation & Build

### Docker (Recommended)
Official Docker images are available via GitHub Container Registry. Use these for stable, dependency-free deployment:
```bash
docker pull ghcr.io/bob-ros2/bob-face:latest
```

### Manual Workspace Build
If you want to build from source in your ROS 2 workspace:

1. **Clone the repository**:
   ```bash
   cd ~/ros2_ws/src
   git clone https://github.com/bob-ros2/bob_face.git
   ```

2. **Install dependencies**:
   ```bash
   cd ~/ros2_ws
   rosdep install --from-paths src --ignore-src -r -y
   # Install additional python dependencies
   pip install -r src/bob_face/requirements.txt
1. 
3. **Build**:
   ```bash
   colcon build --packages-select bob_face
   source install/setup.bash
   ```

## Usage
Launch the face system using a configuration file (e.g., from `bob_launch`):
```bash
ros2 launch bob_launch generic.launch.py config:=face.yaml
```

To manually trigger a sentiment update for testing:
```bash
ros2 topic pub /bob/analize std_msgs/msg/String "{data: 'Bob, the sun is rising in pastel colors!'}" -1
```
