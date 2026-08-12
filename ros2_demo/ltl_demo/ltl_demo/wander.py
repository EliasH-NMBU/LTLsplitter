"""Random-goal navigation with reactive obstacle avoidance and a human-detection
safety override.

This ROS2 distro doesn't ship a full navigation stack for this system (classic
Nav2 isn't packaged here -- replaced by a different framework this demo doesn't
depend on), so goal-seeking is a simple proportional heading controller driven by
odometry, blended with a LIDAR-based reactive avoidance layer that takes over
whenever something is close in front: drive toward the current random goal, turn
away from close obstacles, and once the goal is reached (within tolerance) pick a
new random goal inside the arena and repeat. Independently of all that, whenever
/human_detected is true this node forces zero velocity -- that override, plus the
/stopped topic reporting actual commanded linear velocity, is what stage 4/5's
generated LTL monitor checks: "whenever a human is detected, the robot must be
stopped."
"""
from __future__ import annotations

import math
import random

import rclpy
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool

_FRONT_HALF_ANGLE_RAD = math.radians(30)
_STOP_DISTANCE_M = 0.45
_SLOW_DISTANCE_M = 0.9
_FORWARD_SPEED = 0.18
_TURN_SPEED = 0.6
_CONTROL_PERIOD_S = 0.1

# Random goals are sampled well inside the turtlebot3_world arena's walls (which sit at
# roughly x=+-1.8/y=+-2.7) so goals stay reachable without needing wall-aware planning.
_GOAL_X_RANGE_M = (-1.5, 1.5)
_GOAL_Y_RANGE_M = (-2.2, 2.2)
_GOAL_TOLERANCE_M = 0.2
_HEADING_GAIN = 1.2
# Above this heading error, rotate in place toward the goal rather than also driving
# forward -- avoids arcing wide loops when the goal starts out behind the robot.
_HEADING_ALIGN_THRESHOLD_RAD = math.radians(45)


def _wrap_to_pi(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _yaw_from_quaternion(q) -> float:
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Wander(Node):
    def __init__(self) -> None:
        super().__init__("wander")
        self._human_detected = False
        self._min_front_range = math.inf
        self._turn_bias = 1.0  # sign of the last avoidance turn, for a consistent escape direction
        self._pose_x = 0.0
        self._pose_y = 0.0
        self._pose_yaw = 0.0
        self._have_odom = False
        self._goal_x, self._goal_y = self._sample_goal()

        self.create_subscription(LaserScan, "scan", self._on_scan, 10)
        self.create_subscription(Bool, "human_detected", self._on_human_detected, 10)
        self.create_subscription(Odometry, "odom", self._on_odom, 10)
        self._cmd_pub = self.create_publisher(TwistStamped, "cmd_vel", 10)
        self._stopped_pub = self.create_publisher(Bool, "stopped", 10)
        self.create_timer(_CONTROL_PERIOD_S, self._on_control_tick)

    @staticmethod
    def _sample_goal() -> tuple[float, float]:
        return random.uniform(*_GOAL_X_RANGE_M), random.uniform(*_GOAL_Y_RANGE_M)

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

    def _on_odom(self, msg: Odometry) -> None:
        self._pose_x = msg.pose.pose.position.x
        self._pose_y = msg.pose.pose.position.y
        self._pose_yaw = _yaw_from_quaternion(msg.pose.pose.orientation)
        self._have_odom = True

    def _on_control_tick(self) -> None:
        linear_x = 0.0
        angular_z = 0.0

        if not self._human_detected:
            if self._have_odom:
                dx = self._goal_x - self._pose_x
                dy = self._goal_y - self._pose_y
                if math.hypot(dx, dy) < _GOAL_TOLERANCE_M:
                    self._goal_x, self._goal_y = self._sample_goal()
                    self.get_logger().info(f"Goal reached, new goal: ({self._goal_x:.2f}, {self._goal_y:.2f})")

            if self._min_front_range < _STOP_DISTANCE_M:
                angular_z = _TURN_SPEED * self._turn_bias
            else:
                heading_error = 0.0
                if self._have_odom:
                    heading_error = _wrap_to_pi(
                        math.atan2(self._goal_y - self._pose_y, self._goal_x - self._pose_x) - self._pose_yaw
                    )

                if abs(heading_error) > _HEADING_ALIGN_THRESHOLD_RAD:
                    angular_z = math.copysign(_TURN_SPEED, heading_error)
                else:
                    linear_x = _FORWARD_SPEED
                    angular_z = max(-_TURN_SPEED, min(_TURN_SPEED, _HEADING_GAIN * heading_error))

                if self._min_front_range < _SLOW_DISTANCE_M:
                    self._turn_bias = -1.0 if self._turn_bias > 0 else 1.0
                    linear_x = min(linear_x, _FORWARD_SPEED * 0.5)
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
