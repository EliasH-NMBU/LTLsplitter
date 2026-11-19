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

bool alert;
int32_t classifier;
int32_t distance_to_target;
bool halt;
bool slowdown;
int32_t state;
bool turnoffUVC;

class CopilotRV : public rclcpp::Node {
  public:
    CopilotRV() : Node("copilotrv") {
      alert_subscription_ = this->create_subscription<std_msgs::msg::Bool>(
        "/sRobotAlert", 10,
        std::bind(&CopilotRV::alert_callback, this, _1));

      classifier_subscription_ = this->create_subscription<std_msgs::msg::Int32>(
        "/sRobotClassifier", 10,
        std::bind(&CopilotRV::classifier_callback, this, _1));

      distance_to_target_subscription_ = this->create_subscription<std_msgs::msg::Int32>(
        "/scan", 10,
        std::bind(&CopilotRV::distance_to_target_callback, this, _1));

      halt_subscription_ = this->create_subscription<std_msgs::msg::Bool>(
        "/sRobotHalt", 10,
        std::bind(&CopilotRV::halt_callback, this, _1));

      slowdown_subscription_ = this->create_subscription<std_msgs::msg::Bool>(
        "/sRobotSlowdown", 10,
        std::bind(&CopilotRV::slowdown_callback, this, _1));

      state_subscription_ = this->create_subscription<std_msgs::msg::Int32>(
        "/sRobotState", 10,
        std::bind(&CopilotRV::state_callback, this, _1));

      turnoffUVC_subscription_ = this->create_subscription<std_msgs::msg::Bool>(
        "/sRobotTurnoffUVC", 10,
        std::bind(&CopilotRV::turnoffUVC_callback, this, _1));

      handlerOperationalstate_0_4_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_4", 10);

      handlerOperationalstate_0_3_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_3", 10);

      handlerOperationalstate_0_2_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_2", 10);

      handlerOperationalstate_0_1_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_1", 10);

      handlerOperationalstate_2_4_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_4", 10);

      handlerOperationalstate_2_3_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_3", 10);

      handlerOperationalstate_2_2_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_2", 10);

      handlerOperationalstate_2_1_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_1", 10);

      handlerOperationalstate_3_4_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_4", 10);

      handlerOperationalstate_3_3_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_3", 10);

      handlerOperationalstate_3_2_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_2", 10);

      handlerOperationalstate_3_1_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_1", 10);

      handlerOperationalstate_1_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_1", 10);

    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_0_4() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_0_4_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_0_3() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_0_3_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_0_2() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_0_2_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_0_1() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_0_1_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_2_4() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_2_4_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_2_3() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_2_3_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_2_2() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_2_2_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_2_1() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_2_1_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_3_4() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_3_4_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_3_3() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_3_3_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_3_2() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_3_2_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_3_1() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_3_1_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerOperationalstate_1() {
      auto output = std_msgs::msg::Empty();
      handlerOperationalstate_1_publisher_->publish(output);
    }

    // Needed so we can report messages to the log.
    static std::shared_ptr<CopilotRV> getInstance() {
      static std::shared_ptr<CopilotRV> instance = std::shared_ptr<CopilotRV>(new CopilotRV());
      return instance;
    }

  private:
    void alert_callback(const std_msgs::msg::Bool::SharedPtr msg) const {
      alert = msg->data;
      step();
    }

    void classifier_callback(const std_msgs::msg::Int32::SharedPtr msg) const {
      classifier = msg->data;
      step();
    }

    void distance_to_target_callback(const std_msgs::msg::Int32::SharedPtr msg) const {
      distance_to_target = msg->data;
      step();
    }

    void halt_callback(const std_msgs::msg::Bool::SharedPtr msg) const {
      halt = msg->data;
      step();
    }

    void slowdown_callback(const std_msgs::msg::Bool::SharedPtr msg) const {
      slowdown = msg->data;
      step();
    }

    void state_callback(const std_msgs::msg::Int32::SharedPtr msg) const {
      state = msg->data;
      step();
    }

    void turnoffUVC_callback(const std_msgs::msg::Bool::SharedPtr msg) const {
      turnoffUVC = msg->data;
      step();
    }

    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr alert_subscription_;

    rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr classifier_subscription_;

    rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr distance_to_target_subscription_;

    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr halt_subscription_;

    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr slowdown_subscription_;

    rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr state_subscription_;

    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr turnoffUVC_subscription_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_4_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_3_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_2_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_1_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_4_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_3_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_2_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_1_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_4_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_3_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_2_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_1_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_1_publisher_;

};

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_0_4() {
  CopilotRV::getInstance()->handlerOperationalstate_0_4();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_0_3() {
  CopilotRV::getInstance()->handlerOperationalstate_0_3();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_0_2() {
  CopilotRV::getInstance()->handlerOperationalstate_0_2();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_0_1() {
  CopilotRV::getInstance()->handlerOperationalstate_0_1();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_2_4() {
  CopilotRV::getInstance()->handlerOperationalstate_2_4();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_2_3() {
  CopilotRV::getInstance()->handlerOperationalstate_2_3();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_2_2() {
  CopilotRV::getInstance()->handlerOperationalstate_2_2();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_2_1() {
  CopilotRV::getInstance()->handlerOperationalstate_2_1();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_3_4() {
  CopilotRV::getInstance()->handlerOperationalstate_3_4();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_3_3() {
  CopilotRV::getInstance()->handlerOperationalstate_3_3();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_3_2() {
  CopilotRV::getInstance()->handlerOperationalstate_3_2();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_3_1() {
  CopilotRV::getInstance()->handlerOperationalstate_3_1();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerOperationalstate_1() {
  CopilotRV::getInstance()->handlerOperationalstate_1();
}

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(CopilotRV::getInstance());
  rclcpp::shutdown();
  return 0;
}

