"""Toggles the demo's two humanoid stand-ins between visible and hidden every
_INTERVAL_S seconds, so the robot doesn't get stuck stopped in front of one
forever. "Hidden" means teleported straight down, out of both the camera's
view and the 2D LIDAR's scan plane -- simpler than actually deleting/
respawning the model, and just as effective for this demo.
"""
from __future__ import annotations

import rclpy
from rclpy.node import Node
from ros_gz_interfaces.srv import SetEntityPose

_HUMAN_POSES_M = {
    "human_1": (1.0, 0.6, 0.0),
    "human_2": (-1.2, 1.2, 0.0),
}
_HIDDEN_Z_OFFSET_M = -10.0
_INTERVAL_S = 10.0
_SET_POSE_SERVICE = "/world/default/set_pose"
_ENTITY_TYPE_MODEL = 2


class HumanBlinker(Node):
    def __init__(self) -> None:
        super().__init__("human_blinker")
        self._client = self.create_client(SetEntityPose, _SET_POSE_SERVICE)
        # Humans start visible at their poses from the world file, so the first
        # toggle (at t=_INTERVAL_S) is the one that hides them: 10s there, 10s away.
        self._visible = True
        self.create_timer(_INTERVAL_S, self._on_toggle)

    def _on_toggle(self) -> None:
        self._visible = not self._visible
        self.get_logger().info(f"Toggling humans to {'visible' if self._visible else 'hidden'}")
        for name, (x, y, z) in _HUMAN_POSES_M.items():
            self._set_pose(name, x, y, z if self._visible else z + _HIDDEN_Z_OFFSET_M)

    def _set_pose(self, name: str, x: float, y: float, z: float) -> None:
        request = SetEntityPose.Request()
        request.entity.name = name
        request.entity.type = _ENTITY_TYPE_MODEL
        request.pose.position.x = x
        request.pose.position.y = y
        request.pose.position.z = z
        self._client.call_async(request)


def main() -> None:
    rclpy.init()
    node = HumanBlinker()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
