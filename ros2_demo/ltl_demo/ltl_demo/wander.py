"""Reactive wander/patrol controller with a human-detection safety override.

This ROS2 distro doesn't ship a full navigation stack for this system (classic
Nav2 isn't packaged here -- replaced by a different framework this demo doesn't
depend on), so movement is a simple LIDAR-based reactive controller: drive forward,
turn away from close obstacles, rotate to escape dead ends. Independently of that,
whenever /human_detected is true this node forces zero velocity -- that override,
plus the /stopped topic reporting actual commanded linear velocity, is what stage
4/5's generated LTL monitor checks: "whenever a human is detected, the robot must
be stopped."
"""
from __future__ import annotations

import math

import rclpy
from geometry_msgs.msg import TwistStamped
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool

_FRONT_HALF_ANGLE_RAD = math.radians(30)
_STOP_DISTANCE_M = 0.45
_SLOW_DISTANCE_M = 0.9
_FORWARD_SPEED = 0.18
_TURN_SPEED = 0.6
_CONTROL_PERIOD_S = 0.1


def _wrap_to_pi(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class Wander(Node):
    def __init__(self) -> None:
        super().__init__("wander")
        self._human_detected = False
        self._min_front_range = math.inf
        self._turn_bias = 1.0  # sign of the last avoidance turn, for a consistent escape direction

        self.create_subscription(LaserScan, "scan", self._on_scan, 10)
        self.create_subscription(Bool, "human_detected", self._on_human_detected, 10)
        self._cmd_pub = self.create_publisher(TwistStamped, "cmd_vel", 10)
        self._stopped_pub = self.create_publisher(Bool, "stopped", 10)
        self.create_timer(_CONTROL_PERIOD_S, self._on_control_tick)

    def _on_human_detected(self, msg: Bool) -> None:
        self._human_detected = msg.data
        # React immediately rather than waiting for the next control tick -- otherwise
        # there's a window (up to _CONTROL_PERIOD_S) where /human_detected has gone true
        # but /stopped hasn't caught up yet, which the generated monitor's "historically"
        # semantics would flag as a permanent violation the instant it happens once.
        self._on_control_tick()

    def _on_scan(self, msg: LaserScan) -> None:
        min_range = math.inf
        for i, r in enumerate(msg.ranges):
            if not (msg.range_min <= r <= msg.range_max):
                continue
            angle = _wrap_to_pi(msg.angle_min + i * msg.angle_increment)
            if abs(angle) <= _FRONT_HALF_ANGLE_RAD:
                min_range = min(min_range, r)
        self._min_front_range = min_range

    def _on_control_tick(self) -> None:
        linear_x = 0.0
        angular_z = 0.0

        if not self._human_detected:
            if self._min_front_range < _STOP_DISTANCE_M:
                angular_z = _TURN_SPEED * self._turn_bias
            else:
                linear_x = _FORWARD_SPEED
                if self._min_front_range < _SLOW_DISTANCE_M:
                    self._turn_bias = -1.0 if self._turn_bias > 0 else 1.0
                    angular_z = _TURN_SPEED * 0.5 * self._turn_bias

        cmd = TwistStamped()
        cmd.header.stamp = self.get_clock().now().to_msg()
        cmd.header.frame_id = "base_link"
        cmd.twist.linear.x = linear_x
        cmd.twist.angular.z = angular_z
        self._cmd_pub.publish(cmd)

        self._stopped_pub.publish(Bool(data=abs(linear_x) < 1e-6))


def main() -> None:
    rclpy.init()
    node = Wander()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
