from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


class MonitorDeployment:
    """Wraps a generated ROS2 monitor package: launches it and relays violation/state
    updates to a callback. Requires a sourced ROS2 environment (rclpy) at runtime."""

    def __init__(self, package_dir: Path, on_update: Callable[[str], None]):
        self.package_dir = package_dir
        self.on_update = on_update

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
