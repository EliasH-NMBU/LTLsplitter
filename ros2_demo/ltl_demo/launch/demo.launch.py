"""Brings up the whole LTLsplitter ROS2 demo: Gazebo + the world (with two
humanoid stand-ins that blink in and out of place every 10s), the
camera-equipped TurtleBot3, the RGB camera bridge, the human detector, and the
reactive wander/safety-stop controller.

Launched either directly (`ros2 launch ltl_demo demo.launch.py`) or from
LTLsplitter's own "Launch Simulation" button on stage 6, which runs this same
command as a subprocess.
"""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    AppendEnvironmentVariable,
    ExecuteProcess,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
    UnsetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

# When this whole app (or this launch file) is started from inside a snap-confined
# shell -- e.g. a VSCode integrated terminal, since VSCode itself ships as a snap --
# these GTK/snap desktop-integration variables leak into every child process. Gazebo's
# GUI links against them and pulls in a mismatched libpthread from snap's core20 base,
# crashing immediately with "symbol lookup error: ... undefined symbol: __libc_pthread_init,
# version GLIBC_PRIVATE". None of these variables matter to Gazebo or any ROS node here,
# so they're unset for the whole launch rather than chased down to one exact culprit.
_SNAP_ENV_VARS_TO_UNSET = [
    "SNAP", "SNAP_NAME", "SNAP_REVISION", "SNAP_ARCH", "SNAP_LIBRARY_PATH",
    "GTK_PATH", "GTK_EXE_PREFIX", "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR",
    "GIO_MODULE_DIR", "LOCPATH",
]

# On hybrid NVIDIA/integrated-GPU laptops, glvnd's default vendor selection lets Mesa try
# (and fail) to create a DRI2 rendering context on the NVIDIA render node -- Gazebo's Ogre2
# GUI then can't get a hardware context at all ("libEGL warning: egl: failed to create dri2
# screen") and the window shows nothing. Forcing the NVIDIA glvnd vendor explicitly fixes it;
# confirmed empirically (EGL warnings gone) on a GeForce RTX + AMD iGPU hybrid laptop. Only
# applied if the NVIDIA EGL vendor file is actually present -- pointing glvnd at a
# nonexistent vendor file would break EGL entirely on machines without an NVIDIA driver.
_NVIDIA_EGL_VENDOR_FILE = Path("/usr/share/glvnd/egl_vendor.d/10_nvidia.json")
_NVIDIA_RENDER_ENV_VARS = {
    "__NV_PRIME_RENDER_OFFLOAD": "1",
    "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
    "__EGL_VENDOR_LIBRARY_FILENAMES": str(_NVIDIA_EGL_VENDOR_FILE),
}


def generate_launch_description() -> LaunchDescription:
    ltl_demo_dir = get_package_share_directory("ltl_demo")
    tb3_sim_dir = get_package_share_directory("nav2_minimal_tb3_sim")

    world_path = str(Path(ltl_demo_dir) / "worlds" / "tb3_sandbox_human.sdf")
    robot_sdf_path = str(Path(ltl_demo_dir) / "urdf" / "gz_waffle_rgb.sdf.xacro")

    unset_snap_vars = [UnsetEnvironmentVariable(name) for name in _SNAP_ENV_VARS_TO_UNSET]
    nvidia_render_vars = (
        [SetEnvironmentVariable(name, value) for name, value in _NVIDIA_RENDER_ENV_VARS.items()]
        if _NVIDIA_EGL_VENDOR_FILE.is_file()
        else []
    )

    set_resource_path = AppendEnvironmentVariable(
        "GZ_SIM_RESOURCE_PATH", str(Path(tb3_sim_dir) / "models")
    )
    # Needed for gz-sim to resolve the robot's visual mesh "package://nav2_minimal_tb3_sim/..."
    # URIs -- gz-sim's package:// resolver walks GZ_SIM_RESOURCE_PATH entries looking for a
    # subdirectory matching the package name, so the share/ parent (not just models/) must be
    # on it too. Without this the robot spawns and works fully (physics/sensors/topics all
    # fine) but renders with missing/fallback geometry in the GUI -- cosmetic only.
    set_resource_path_parent = AppendEnvironmentVariable(
        "GZ_SIM_RESOURCE_PATH", str(Path(tb3_sim_dir).parent)
    )

    gz_sim = ExecuteProcess(
        cmd=["gz", "sim", "-r", world_path],
        output="screen",
    )

    # spawn_tb3.launch.py starts the robot + its ros_gz_bridge (odom/scan/imu/cmd_vel/tf).
    # Delayed so the Gazebo server is up before anything tries to spawn into it.
    spawn_robot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(Path(tb3_sim_dir) / "launch" / "spawn_tb3.launch.py")
        ),
        launch_arguments={"robot_sdf": robot_sdf_path}.items(),
    )

    camera_bridge = Node(
        package="ros_gz_image",
        executable="image_bridge",
        arguments=["/rgb_camera"],
        output="screen",
    )

    # Exposes Gazebo's world "set_pose" service over ROS -- human_blinker uses it to
    # teleport the human models in and out of place every 10s.
    set_pose_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/world/default/set_pose@ros_gz_interfaces/srv/SetEntityPose"],
        output="screen",
    )

    detector = Node(package="ltl_demo", executable="detector", output="screen")
    wander = Node(package="ltl_demo", executable="wander", output="screen")
    human_blinker = Node(package="ltl_demo", executable="human_blinker", output="screen")

    delayed = TimerAction(
        period=5.0,
        actions=[spawn_robot, camera_bridge, set_pose_bridge, detector, wander, human_blinker],
    )

    return LaunchDescription(
        [
            *unset_snap_vars,
            *nvidia_render_vars,
            set_resource_path,
            set_resource_path_parent,
            gz_sim,
            delayed,
        ]
    )
