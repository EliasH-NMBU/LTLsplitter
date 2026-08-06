from __future__ import annotations

from pathlib import Path

from ltlsplitter.core.models import Specification


def generate_ros2_monitor(spec: Specification, output_dir: Path) -> Path:
    """Shell out to `ogma ros` to generate a ROS2 monitor package from a spec."""
    raise NotImplementedError
