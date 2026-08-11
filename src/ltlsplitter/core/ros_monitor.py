from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from ltlsplitter.core.ogma import patch_cmake_for_modern_ament

_MONITOR_WORKSPACE = Path.home() / ".local" / "share" / "ltlsplitter-tools" / "monitor_ws"
_ROS_SETUP_BASH = Path(os.environ.get("ROS_SETUP_BASH", "/opt/ros/lyrical/setup.bash"))
_TOPIC_DISCOVERY_TIMEOUT_SECONDS = 10

# Runs under the *system* Python (via `source ROS_SETUP_BASH && python3`), never LTLsplitter's
# own venv -- rclpy lives in ROS2's site-packages, which a plain `python -m venv` doesn't see.
# This mirrors how nuXmv/Strix/Ogma are shelled out to rather than imported: the dependency
# lives outside this app's own Python environment.
_WATCHER_SCRIPT = '''
import sys
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty

DISCOVERY_TIMEOUT_S = {timeout}

rclpy.init(args=None)
node = Node("ltlsplitter_monitor_watcher")
subscribed = set()

def make_callback(topic_name):
    def _cb(_msg):
        print(f"VIOLATION on {{topic_name}}", flush=True)
    return _cb

print("Waiting for the monitor node to advertise its violation topic(s)...", flush=True)
deadline = time.monotonic() + DISCOVERY_TIMEOUT_S
while True:
    for topic_name, _types in node.get_topic_names_and_types():
        if topic_name.startswith("/copilot/") and topic_name not in subscribed:
            node.create_subscription(Empty, topic_name, make_callback(topic_name), 10)
            subscribed.add(topic_name)
            print(f"Watching {{topic_name}} for violations.", flush=True)
    if subscribed or time.monotonic() > deadline:
        if not subscribed:
            print(
                f"No copilot/* violation topic found after {{DISCOVERY_TIMEOUT_S}}s -- "
                "is the monitor node running?", flush=True,
            )
        break
    rclpy.spin_once(node, timeout_sec=0.5)

try:
    while True:
        rclpy.spin_once(node, timeout_sec=0.2)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    rclpy.shutdown()
'''


class ToolNotFoundError(RuntimeError):
    """A sourced ROS2 environment (colcon, ros2 CLI, rclpy) isn't available."""


def _require_ros_setup() -> None:
    if not _ROS_SETUP_BASH.is_file():
        raise ToolNotFoundError(
            f"No sourced ROS2 environment found at '{_ROS_SETUP_BASH}'. Install ROS2 (see "
            "README.md) and/or set ROS_SETUP_BASH to your distro's setup.bash."
        )


def _run_sourced(command: str, cwd: Path, timeout: float) -> subprocess.CompletedProcess:
    """Runs a shell command with the ROS2 environment sourced first."""
    full_command = f"source {_ROS_SETUP_BASH} && {command}"
    return subprocess.run(
        ["bash", "-c", full_command], cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, stdin=subprocess.DEVNULL,
    )


class MonitorDeployment:
    """Wraps a generated ROS2 monitor package: builds it into a dedicated workspace,
    launches it, and relays violation notifications to a callback. Requires a sourced
    ROS2 environment (rclpy) at runtime.

    Ogma's monitor package is always named "copilot" with a "copilotrv" node that
    publishes an empty message to "copilot/handler<RequirementId>" on every property
    violation -- but the exact handler name depends on the requirement id used when
    the monitor was generated, which this class doesn't otherwise know. Rather than
    require that as a second constructor argument, it discovers violation topics
    dynamically by querying the running node for any topic under "copilot/"."""

    def __init__(self, package_dir: Path, on_update: Callable[[str], None]):
        self.package_dir = package_dir
        self.on_update = on_update
        self._process: subprocess.Popen | None = None
        self._watcher_process: subprocess.Popen | None = None
        self._watcher_thread: threading.Thread | None = None

    def start(self) -> None:
        _require_ros_setup()
        copilot_src = self.package_dir / "copilot"
        if not copilot_src.is_dir():
            raise RuntimeError(f"No 'copilot' package found under {self.package_dir}.")

        workspace_pkg_dir = _MONITOR_WORKSPACE / "src" / "copilot"
        _MONITOR_WORKSPACE.mkdir(parents=True, exist_ok=True)
        (_MONITOR_WORKSPACE / "src").mkdir(exist_ok=True)
        if workspace_pkg_dir.exists():
            shutil.rmtree(workspace_pkg_dir)
        shutil.copytree(copilot_src, workspace_pkg_dir)

        self._compile_copilot_spec(workspace_pkg_dir)
        patch_cmake_for_modern_ament(_MONITOR_WORKSPACE / "src")
        self._colcon_build()

        install_setup = _MONITOR_WORKSPACE / "install" / "setup.bash"
        self._process = subprocess.Popen(
            ["bash", "-c", f"source {_ROS_SETUP_BASH} && source {install_setup} && ros2 run copilot copilot"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )

        watcher_path = _MONITOR_WORKSPACE / "watcher.py"
        watcher_path.write_text(_WATCHER_SCRIPT.format(timeout=_TOPIC_DISCOVERY_TIMEOUT_SECONDS))
        self._watcher_process = subprocess.Popen(
            ["bash", "-c", f"source {_ROS_SETUP_BASH} && exec python3 -u {watcher_path}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self._watcher_thread = threading.Thread(target=self._read_watcher_output, daemon=True)
        self._watcher_thread.start()

    def stop(self) -> None:
        for proc in (self._watcher_process, self._process):
            if proc is None:
                continue
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._process = None
        self._watcher_process = None
        if self._watcher_thread is not None:
            self._watcher_thread.join(timeout=5)
            self._watcher_thread = None

    # ---- setup steps ----------------------------------------------------

    @staticmethod
    def _compile_copilot_spec(workspace_pkg_dir: Path) -> None:
        """Ogma generates a Haskell Copilot spec, not C -- `runhaskell Copilot.hs`
        compiles it to the copilot.c/.h the C++ node #includes."""
        src_dir = workspace_pkg_dir / "src"
        if (src_dir / "copilot.c").exists():
            return
        result = subprocess.run(
            ["runhaskell", "Copilot.hs"], cwd=str(src_dir), capture_output=True, text=True,
            timeout=60, stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Compiling the Copilot spec failed:\n{result.stdout}\n{result.stderr}")

    @staticmethod
    def _colcon_build() -> None:
        result = _run_sourced(
            "colcon build --packages-select copilot", _MONITOR_WORKSPACE, timeout=180
        )
        if result.returncode != 0:
            raise RuntimeError(f"colcon build failed:\n{result.stdout}\n{result.stderr}")

    # ---- runtime ----------------------------------------------------------

    def _read_watcher_output(self) -> None:
        if self._watcher_process is None or self._watcher_process.stdout is None:
            return
        for line in self._watcher_process.stdout:
            line = line.rstrip()
            if line:
                self.on_update(line)
