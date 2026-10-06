# Underwater Inspection Swarm

A ROS 2 and Gazebo project for inspecting underwater infrastructure with a swarm
of autonomous underwater vehicles (AUVs). The demo places multiple AUVs near a
dam, builds maps from their sensors, detects cracks with a neural network, and
assigns follow-up inspections based on damage risk and uncertainty.

A browser dashboard shows camera images, damage overlays, a risk map, vehicle
status, and degradation prognosis. The default demo uses three AUVs.

## Architecture

The workspace contains seven Python ROS 2 packages:

| Package | Responsibility |
| --- | --- |
| `simulation` | Gazebo ocean world, dam and AUV models, vehicle spawning, and Gazebo-to-ROS sensor/thruster bridges. |
| `occupancy_mapping` | Builds per-AUV 3D occupancy grids from sonar scans and odometry, and shares map updates within simulated acoustic range. |
| `damage_detection` | Runs PyTorch crack segmentation on camera images and publishes damage-probability images. Also includes training and evaluation tools. |
| `belief_fusion` | Combines damage probabilities with sonar geometry and pose into shared damage, uncertainty, and risk maps; generates prognosis records. |
| `cbba_allocator` | Extracts inspection targets from risk maps and assigns them through a range-limited, consensus-based sequential auction. |
| `swarm_control` | Plans risk-aware paths using NOA-SQP and follows assigned waypoints through thruster commands. |
| `dashboard` | Serves the live inspection dashboard using Flask and an MJPEG stream. |

```text
Gazebo AUVs -> ROS 2 bridges -> sonar + odometry -> occupancy_mapping
                           -> camera images   -> damage_detection
                                                     |
                           sonar + odometry + damage probabilities
                                                     |
                                                belief_fusion
                                                     |
                                                  risk maps
                                                     |
                                                cbba_allocator
                                                     |
                                              assigned waypoints
                                                     |
                                                swarm_control
                                                     |
                                      thruster commands -> Gazebo AUVs

Sensor topics + saved maps/prognosis/task data -> dashboard -> browser
```

Live sensors and control use ROS 2 topics. Map snapshots and reports are shared
through a common `run_dir`. Each mapping/fusion node hosts all agents' individual
maps and simulates range-gated acoustic exchange internally.

## Dependencies

- **Ubuntu and ROS/Gazebo:** Ubuntu 26.04 with ROS 2 Lyrical and Gazebo Jetty
  (Sim 10), or Ubuntu 24.04 with ROS 2 Jazzy and Gazebo Harmonic (Sim 8).
- **ROS tooling:** `ros_gz` integration, `colcon`, and `rosdep`.
- **System packages:** build tools, Python 3 with `venv`/`pip`, OpenCV
  (`python3-opencv`), and Mesa/OpenGL libraries.
- **Python libraries:** CUDA-enabled PyTorch 2.10.0, torchvision 0.25.0,
  segmentation-models-pytorch, transformers, NumPy, SciPy, Matplotlib, and Flask.
  Versions are specified in [requirements.txt](requirements.txt).
- **Graphics:** the supplied environment setup targets NVIDIA GPU rendering and
  CUDA inference, including WSL2/WSLg support with the Windows NVIDIA driver.

See [DEPENDENCIES.md](DEPENDENCIES.md) for system installation commands, ROS
repository setup details, and GPU configuration.

## Setup and build

Run these commands from the workspace root, the directory containing `src/`,
`requirements.txt`, and `setup_env.sh`, after installing the system dependencies:

```bash
python3 -m venv --system-site-packages venv
mkdir -p venv/tmp
TMPDIR="$PWD/venv/tmp" venv/bin/python -m pip install -r requirements.txt

source setup_env.sh
python -m colcon build --base-paths src --symlink-install --executor sequential
source setup_env.sh
```

The virtual environment inherits the system's ROS packages. Building through
`python -m colcon` makes the nodes use the same Python environment as PyTorch.
`setup_env.sh` selects Lyrical or Jazzy, activates the virtual environment,
sources the built workspace, and configures graphics.

## Run the full demo

From the workspace root:

```bash
source setup_env.sh
ros2 launch simulation full_demo.launch.py num_auvs:=3 run_dir:="$PWD/live_run"
```

Open **<http://localhost:8080>** in your browser. Gazebo opens alongside the
dashboard. Nodes start in stages over roughly 20 seconds; maps, tasks, and
planned routes populate as sensor data arrives. Stop the launch with **Ctrl+C**.

The demo loads the shipped `sim_finetuned.pt` crack-detection checkpoint, which
was pretrained on DeepCrack and fine-tuned on crack-augmented Gazebo images.

### Simulation only

```bash
source setup_env.sh
ros2 launch simulation simulation.launch.py num_auvs:=3
```

### Run without the Gazebo GUI

```bash
source setup_env.sh
ros2 launch simulation full_demo.launch.py num_auvs:=3 headless:=true run_dir:="$PWD/live_run"
```

The dashboard and rendered camera/sonar sensors still run in this mode.

### Useful full-demo launch options

Append options as `name:=value` to the launch command.

| Option | Default | Purpose |
| --- | --- | --- |
| `num_auvs` | `3` | Number of vehicles, named `auv0`, `auv1`, etc. |
| `run_dir` | `~/swarm_ws/live_run` | Shared output directory; the examples override it to the current workspace's `live_run/`. |
| `headless` | `false` | Run Gazebo without its GUI. |
| `port` | `8080` | Dashboard HTTP port. |
| `checkpoint_path` | Installed `damage_detection/checkpoints/sim_finetuned.pt` | Select another trained checkpoint. |
| `render_engine` | `ogre2` | Gazebo rendering backend. |
| `nvidia` | `true` | Enable the launch file's NVIDIA rendering selection. |

## Runtime data and checks

With the example commands, outputs are saved under `live_run/`:

- `occupancy/`: per-AUV fused occupancy grids (`.npy`).
- `damage_probability/`: damage-probability, uncertainty, and risk grids.
- `prognosis/prognosis.json`: damage severity and re-inspection recommendations.
- `tasks/current_tasks.json`: the current auction's assigned inspection targets.

The live prognosis uses severity-based recommendations. The offline estimator
also supports trend comparisons with a previous inspection.

In another terminal, source the environment and inspect the running stack:

```bash
source setup_env.sh
ros2 node list
ros2 topic list
ros2 topic hz /auv0/camera/image_raw
```

Key per-AUV topics include `/auv0/odom`, `/auv0/sonar/scan`,
`/auv0/camera/image_raw`, `/auv0/damage_prob`, and `/auv0/assigned_waypoints`.
The dashboard also serves `/stream.mjpg` and `/prognosis.json`.

To check Python/ROS dependencies, NVIDIA rendering, CUDA, and inference with the
shipped checkpoint:

```bash
source setup_env.sh
python check_dependencies.py
```

## Project layout

```text
src/                  ROS 2 packages, launch files, models, and algorithms
requirements.txt      Python/ML dependencies
setup_env.sh          Environment activation and graphics setup
check_dependencies.py Runtime dependency and GPU checks
DEPENDENCIES.md       Detailed installation and platform notes
eval_results/         Crack-detection evaluation panels
cec_results/          Optimizer benchmark results
build/, install/, log/ Generated colcon build artifacts
live_run/             Runtime outputs when using the example commands
```
