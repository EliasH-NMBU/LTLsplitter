// ROS 2 baseline for the violation-latency test: the same path shape as a Copilot monitor
// (receive a std_msgs message on a depth-10 subscription, publish std_msgs/Empty on a depth-10
// publisher) but with no monitor evaluation and no background topics to process.
#include <memory>
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/empty.hpp"

class ProbeRelay : public rclcpp::Node {
public:
  ProbeRelay() : Node("probe_relay") {
    pub_ = create_publisher<std_msgs::msg::Empty>("/probe_pong", 10);
    sub_ = create_subscription<std_msgs::msg::Bool>(
      "/probe_ping", 10,
      [this](const std_msgs::msg::Bool::SharedPtr) { pub_->publish(std_msgs::msg::Empty()); });
  }
private:
  rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr pub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<ProbeRelay>());
  rclcpp::shutdown();
  return 0;
}
