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
| `sentiment` | `model_repo` | `Xenova/distilbert-base-uncased-finetuned-sst-2-english` | HF-Repository für das ONNX-Modell. |
| `sentiment` | `model_dir` | `""` | Lokales Verzeichnis zum Speichern/Laden des Modells. |
| `sentiment` | `sensitivity` | `1.5` | Multiplikator für den Sentiment-Score. |
| `sentiment` | `smooth_alpha` | `0.3` | Glättungsfaktor (0..1). Niedriger = träger. |
| `sentiment` | `temperature` | `1.0` | Skalierung der Modell-Ausgabe. < 1.0 = extremer. |
| `sentiment` | `buffer_size` | `0` | Fenstergröße für Kontext. 0 = deaktiviert Smoothing. |
| `motion_manager`| `seconds_per_char` | `0.07` | Heuristic for speaking duration. (Env: MOTION_SECONDS_PER_CHAR) |
| `motion_manager`| `idle_sequences`| `""` | Comma-separated idle sequence names. |
| `motion_manager`| `speaking_sequences`| `""` | Comma-separated speaking sequence names. |

## Sentiment Tuning

Um das Verhalten von Bob's Stimmung optimal anzupassen, stehen folgende Parameter zur Verfügung:

### `temperature` (Logit Scaling)
Das Modell gibt Wahrscheinlichkeiten aus. Mit der `temperature` kannst du steuern, wie "sicher" sich das Modell sein soll:
*   **< 1.0 (z.B. 0.5):** Macht die Ergebnisse **extremer**. Bob wechselt schneller zwischen sehr glücklich und sehr traurig. Kleiner Nuancen führen bereits zu starken Farbausschlägen.
*   **> 1.0 (z.B. 2.0):** Macht die Ergebnisse **neutraler**. Bob bleibt länger im mittleren Farbbereich (gelb/orange) und reagiert nur auf sehr eindeutige Aussagen extrem.

### `sensitivity`
Dies ist ein linearer Multiplikator, der nach der Berechnung des Scores angewendet wird. Er hilft dabei, den Wertebereich (0..1) voll auszunutzen, falls das Modell zu konservative Schätzungen abgibt.

### `smooth_alpha` & `buffer_size`
*   **`buffer_size := 0`**: Deaktiviert die Glättung komplett. Bob reagiert **sofort** auf den aktuellen Satz. Ideal für direkte Interaktion.
*   **`buffer_size > 0`**: Aktiviert einen gleitenden Durchschnitt (Leaky Integrator). Bob "merkt" sich die Stimmung der letzten Sätze. `smooth_alpha` bestimmt dabei, wie schnell neue Sätze die aktuelle Stimmung beeinflussen.

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
