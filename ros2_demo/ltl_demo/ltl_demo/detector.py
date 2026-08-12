"""Camera-based human detector.

Looks for the demo world's humanoid stand-in (a distinctly-colored cylinder+sphere
model, see worlds/tb3_sandbox_human.sdf) via HSV color thresholding on the robot's
RGB camera feed -- not a photorealistic figure or a pedestrian classifier. Publishes
/human_detected (std_msgs/Bool), true when enough matching-colored pixels are in frame.
"""
from __future__ import annotations

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool

# HSV range matching the human models' orange-red material (ambient/diffuse
# 0.95, 0.25, 0.05 plus a matching emissive glow -- see the world file).
_HSV_LOWER = np.array([0, 120, 80])
_HSV_UPPER = np.array([15, 255, 255])
_DETECTION_PIXEL_THRESHOLD = 400  # ~0.1% of a 640x480 frame


class HumanDetector(Node):
    def __init__(self) -> None:
        super().__init__("human_detector")
        self._bridge = CvBridge()
        self._pub = self.create_publisher(Bool, "human_detected", 10)
        self.create_subscription(Image, "rgb_camera", self._on_image, 10)

    def _on_image(self, msg: Image) -> None:
        frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, _HSV_LOWER, _HSV_UPPER)
        detected = cv2.countNonZero(mask) >= _DETECTION_PIXEL_THRESHOLD
        self._pub.publish(Bool(data=bool(detected)))


def main() -> None:
    rclpy.init()
    node = HumanDetector()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
