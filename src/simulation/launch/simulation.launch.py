import os
import platform

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    SetEnvironmentVariable,
    TimerAction,
    UnsetEnvironmentVariable,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


AUV_JOINTS = [
    "surge_left_joint",
    "surge_right_joint",
    "sway_joint",
    "heave_front_joint",
    "heave_rear_joint",
]


def spawn_and_bridge(context, *args, **kwargs):
    """Built at launch time (not import time) since num_auvs is a runtime
    LaunchConfiguration -- can't Python-loop over it until it's resolved."""
    num_auvs = int(LaunchConfiguration("num_auvs").perform(context))
    world_file = LaunchConfiguration("world").perform(context)
    world_name = os.path.splitext(world_file)[0]

    share_dir = get_package_share_directory("simulation")
    auv_model_path = os.path.join(share_dir, "models", "auv", "model.sdf")
    with open(auv_model_path, "r") as f:
        auv_model_template = f.read()

    # Global (not per-agent) bridges.
    actions = [
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name="clock_bridge",
            output="screen",
            arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
        ),
    ]

    spacing = 15.0  # meters between AUV start positions along the dam face
    for i in range(num_auvs):
        name = f"auv{i}"
        x = (i - (num_auvs - 1) / 2.0) * spacing
        y = -15.0   # ~13m off the dam face (wall's near face is at y=-28)
        z = -20.0   # mid-water-column start depth

        # Sensor <topic> tags in model.sdf use a literal __AUV_NAME__ token:
        # confirmed by manually spawning one instance and running
        # `gz topic -l` that gz-sim does NOT auto-scope relative sensor
        # topics per spawned instance (a bare "camera" topic came out as a
        # flat, global /camera regardless of the model's actual name) -- so
        # per-instance uniqueness has to be baked into the topic string
        # before spawn, which means spawning from a substituted SDF string
        # rather than the raw file.
        instance_sdf = auv_model_template.replace("__AUV_NAME__", name)

        spawn = Node(
            package="ros_gz_sim",
            executable="create",
            name=f"spawn_{name}",
            output="screen",
            parameters=[{
                "world": world_name,
                "string": instance_sdf,
                "name": name,
                "allow_renaming": False,
                "x": x, "y": y, "z": z,
                "R": 0.0, "P": 0.0, "Y": 0.0,
            }],
        )

        bridge_args = [
            f"/model/{name}/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry",
            f"/{name}/camera@sensor_msgs/msg/Image[gz.msgs.Image",
            f"/{name}/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo",
            f"/{name}/sonar@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan",
            f"/{name}/sonar/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked",
        ]
        for joint in AUV_JOINTS:
            bridge_args.append(
                f"/model/{name}/joint/{joint}/cmd_thrust@std_msgs/msg/Float64]gz.msgs.Double"
            )

        bridge = Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name=f"{name}_bridge",
            output="screen",
            arguments=bridge_args,
            remappings=[
                (f"/model/{name}/odometry", f"/{name}/odom"),
                (f"/{name}/camera", f"/{name}/camera/image_raw"),
                (f"/{name}/camera_info", f"/{name}/camera/camera_info"),
                (f"/{name}/sonar", f"/{name}/sonar/scan"),
            ],
        )

        # Stagger spawns after gz sim has had time to come up, and bridges
        # slightly after their spawn so the topics/services already exist.
        actions.append(TimerAction(period=5.0 + i * 1.5, actions=[spawn]))
        actions.append(TimerAction(period=6.5 + i * 1.5, actions=[bridge]))

    return actions


def generate_launch_description():

    declare_num_auvs = DeclareLaunchArgument(
        "num_auvs", default_value="3",
        description="Number of AUVs to spawn into the swarm."
    )
    declare_world = DeclareLaunchArgument(
        "world", default_value="ocean.sdf",
        description="World SDF filename under simulation/worlds/."
    )
    declare_headless = DeclareLaunchArgument(
        "headless", default_value="false",
        description="Run gz sim server-only (-s), no GUI window. The GUI process "
                     "alone measured 200%+ CPU just rendering -- use this for "
                     "automated verification/CI, not for the actual judged demo."
    )
    declare_render_engine = DeclareLaunchArgument(
        "render_engine", default_value="ogre2",
        description="Gazebo rendering backend. Ogre2 uses the system GPU for "
                    "the GUI, cameras, and gpu_lidar sensors."
    )
    declare_nvidia = DeclareLaunchArgument(
        "nvidia", default_value="true",
        description="Prefer NVIDIA rendering through WSLg/D3D12 or native PRIME."
    )

    models_dir = os.path.join(get_package_share_directory("simulation"), "models")
    existing_resource_path = os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    resource_path_value = (
        f"{models_dir}:{existing_resource_path}" if existing_resource_path else models_dir
    )
    set_resource_path = SetEnvironmentVariable(
        name="GZ_SIM_RESOURCE_PATH", value=resource_path_value
    )

    def configure_gpu(context, *args, **kwargs):
        """Select NVIDIA OpenGL rendering for native Linux and WSLg."""
        use_nvidia = LaunchConfiguration("nvidia").perform(context).lower()
        if use_nvidia != "true":
            return []
        actions = [
            # Prevent an inherited software-rendering setting from silently
            # moving Ogre2 onto the CPU.
            SetEnvironmentVariable(
                name="LIBGL_ALWAYS_SOFTWARE", value="0"
            ),
            SetEnvironmentVariable(name="QT_QPA_PLATFORM", value="xcb"),
        ]
        if "microsoft" in platform.release().lower():
            # WSL has no native NVIDIA GLX driver. Mesa translates OpenGL to
            # D3D12 through the Windows NVIDIA driver and /usr/lib/wsl/lib.
            library_path = context.environment.get("LD_LIBRARY_PATH", "")
            actions.extend([
                UnsetEnvironmentVariable(name="__NV_PRIME_RENDER_OFFLOAD"),
                UnsetEnvironmentVariable(name="__GLX_VENDOR_LIBRARY_NAME"),
                SetEnvironmentVariable(name="GALLIUM_DRIVER", value="d3d12"),
                SetEnvironmentVariable(
                    name="MESA_D3D12_DEFAULT_ADAPTER_NAME", value="NVIDIA"
                ),
                SetEnvironmentVariable(
                    name="LD_LIBRARY_PATH",
                    value="/usr/lib/wsl/lib" + (
                        ":" + library_path if library_path else ""
                    ),
                ),
            ])
        else:
            actions.extend([
                SetEnvironmentVariable(
                    name="__NV_PRIME_RENDER_OFFLOAD", value="1"
                ),
                SetEnvironmentVariable(
                    name="__GLX_VENDOR_LIBRARY_NAME", value="nvidia"
                ),
            ])
        return actions

    def make_gazebo(context, *args, **kwargs):
        world_file = LaunchConfiguration("world").perform(context)
        world_full_path = os.path.join(
            get_package_share_directory("simulation"), "worlds", world_file
        )
        headless = LaunchConfiguration("headless").perform(context).lower() == "true"
        render_engine = LaunchConfiguration("render_engine").perform(context)
        use_nvidia = LaunchConfiguration("nvidia").perform(context).lower() == "true"
        cmd = ["gz", "sim", "-r"]
        if headless:
            cmd.append("-s")
        # Keep the world positional argument before the renderer option, as
        # documented by Gazebo's `gz sim ... --render-engine ...` CLI.
        cmd.extend([world_full_path, "--render-engine", render_engine])
        return [
            LogInfo(msg=[
                "Gazebo rendering with ", render_engine,
                "; NVIDIA selection ", "enabled" if use_nvidia else "disabled",
                ". Check the renderer with glxinfo -B."
            ]),
            ExecuteProcess(cmd=cmd, output="screen"),
        ]

    return LaunchDescription([
        declare_num_auvs,
        declare_world,
        declare_headless,
        declare_render_engine,
        declare_nvidia,
        set_resource_path,
        OpaqueFunction(function=configure_gpu),
        OpaqueFunction(function=make_gazebo),
        OpaqueFunction(function=spawn_and_bridge),
    ])
