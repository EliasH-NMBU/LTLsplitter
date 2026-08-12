#include <functional>
#include <memory>

#include "rclcpp/rclcpp.hpp"

#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/empty.hpp"
#include "std_msgs/msg/u_int8.hpp"
#include "std_msgs/msg/u_int16.hpp"
#include "std_msgs/msg/u_int32.hpp"
#include "std_msgs/msg/u_int64.hpp"
#include "std_msgs/msg/int8.hpp"
#include "std_msgs/msg/int16.hpp"
#include "std_msgs/msg/int32.hpp"
#include "std_msgs/msg/int64.hpp"
#include "std_msgs/msg/float32.hpp"
#include "std_msgs/msg/float64.hpp"
#include <cstdint>
#include "copilot_types.h"
#include "copilot.h"
#include "copilot.c"

using std::placeholders::_1;

bool human_detected;
bool stopped;

class CopilotRV : public rclcpp::Node {
  public:
    CopilotRV() : Node("copilotrv") {
      human_detected_subscription_ = this->create_subscription<std_msgs::msg::Bool>(
        "/human_detected", 10,
        std::bind(&CopilotRV::human_detected_callback, this, _1));

      stopped_subscription_ = this->create_subscription<std_msgs::msg::Bool>(
        "/stopped", 10,
        std::bind(&CopilotRV::stopped_callback, this, _1));

      handlerR1_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerR1", 10);

    }

    // Report (publish) monitor violations.
    void handlerR1() {
      auto output = std_msgs::msg::Empty();
      handlerR1_publisher_->publish(output);
    }

    // Needed so we can report messages to the log.
    static CopilotRV& getInstance() {
      static CopilotRV instance;
      return instance;
    }

  private:
    void human_detected_callback(const std_msgs::msg::Bool::SharedPtr msg) const {
      human_detected = msg->data;
      step();
    }

    void stopped_callback(const std_msgs::msg::Bool::SharedPtr msg) const {
      stopped = msg->data;
      step();
    }

    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr human_detected_subscription_;

    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr stopped_subscription_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerR1_publisher_;

};

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerR1() {
  CopilotRV::getInstance().handlerR1();
}

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CopilotRV>());
  rclcpp::shutdown();
  return 0;
}

