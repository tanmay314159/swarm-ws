# Running the swarm simulation

This workspace uses ROS 2 and Gazebo for physics and GPU rendering, with
CUDA-enabled PyTorch for crack detection.

## Installed platform

- Ubuntu 26.04 / WSL2: **ROS 2 Lyrical + Gazebo Jetty (Sim 10)**.
- Original Ubuntu 24.04 platform: **ROS 2 Jazzy + Gazebo Harmonic (Sim 8)**.

Use the ROS/Gazebo packages built for your Ubuntu version. The shared setup
script detects either ROS installation.

## Activate and run

From the workspace root (`/home/tanmay/swarm-ws/swarm-ws` on this machine):

```bash
source setup_env.sh
ros2 launch simulation simulation.launch.py num_auvs:=3
```

Full swarm, perception, allocation, and dashboard:

```bash
source setup_env.sh
ros2 launch simulation full_demo.launch.py num_auvs:=3 run_dir:="$PWD/live_run"
```

The dashboard is at <http://localhost:8080>. Stop the launch with Ctrl+C.

Check the installed runtime and execute a CUDA inference with the shipped
checkpoint:

```bash
source setup_env.sh
python check_dependencies.py
```

## System dependencies

The official `ros2-apt-source` package configures the ROS repository and signing
key. After configuring it, the packages used on Ubuntu 26.04 are:

```bash
sudo apt-get update
sudo apt-get install -y \
  ros-lyrical-ros-base ros-lyrical-ros-gz ros-dev-tools \
  build-essential cmake pkg-config python3-venv python3-pip \
  python3-numpy python3-scipy python3-matplotlib python3-opencv \
  python3-flask python3-pytest python3-cffi ffmpeg mesa-utils \
  libgl1-mesa-dri libegl-mesa0 libglx-mesa0
```

For Ubuntu 24.04 use the `ros-jazzy-*` packages instead. `ros-dev-tools` provides
colcon and rosdep. The project package manifests can be checked with:

```bash
source setup_env.sh
rosdep check --from-paths src --ignore-src --rosdistro "$ROS_DISTRO"
```

## Python dependencies and build

The virtual environment inherits apt's ROS/scientific packages while keeping
the PyTorch/ML wheels separate from system Python:

```bash
python3 -m venv --system-site-packages venv
mkdir -p venv/tmp
TMPDIR="$PWD/venv/tmp" venv/bin/python -m pip install -r requirements.txt
source setup_env.sh
python -m colcon build --base-paths src --symlink-install --executor sequential
source setup_env.sh
```

Build through the virtual environment's Python so the ROS node entry points use
the same CUDA-enabled PyTorch installation. Explicit `--base-paths src` keeps
colcon from scanning the virtual environment as part of the workspace.
The disk-backed `venv/tmp` directory keeps large CUDA wheel downloads off
WSL's RAM-backed `/tmp` filesystem.

## GPU configuration

On WSL2, the Windows NVIDIA driver provides CUDA and graphics access. Ogre2's
OpenGL rendering uses Mesa/D3D12 through WSLg. `setup_env.sh` and the simulation
launch select the NVIDIA adapter and expose `/usr/lib/wsl/lib` to the loader.
On native Linux, the launch uses NVIDIA PRIME offload instead.

```bash
source setup_env.sh
glxinfo -B
nvidia-smi
```

On this WSL machine, the renderer should report:

```text
OpenGL renderer string: D3D12 (NVIDIA GeForce RTX 4060 Laptop GPU)
Accelerated: yes
```

Gazebo records its actual renderer in `~/.gz/rendering/ogre2.log`. CUDA is used
by the crack detector; Ogre2 cameras, GUI, and `gpu_lidar` use graphics APIs.
The PyTorch wheels include CUDA runtime libraries; no separate CUDA toolkit or
Linux NVIDIA kernel driver is required for this project's WSL runtime.

## Verified on this machine

All seven workspace packages build, `rosdep check` reports satisfied system
dependencies, and `pip check` reports no broken requirements. Gazebo's Ogre2
log confirms RTX 4060 rendering. The shipped `small_unet` checkpoint runs on
CUDA 12.8 with PyTorch 2.10.0.

A three-AUV full-demo smoke check received camera, sonar, odometry, and AI
damage-probability images, and verified the dashboard HTTP page, prognosis
JSON, and JPEG stream. During SIGINT shutdown, some Gazebo/bridge processes
reported segmentation faults on this Lyrical/Jetty stack; these occurred
after the runtime checks passed.
