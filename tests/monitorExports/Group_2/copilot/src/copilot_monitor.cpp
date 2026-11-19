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

      handlerState_req101_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerState_req101", 10);

      handlerDtt_assumption_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerDtt_assumption", 10);

      handlerState_req201_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerState_req201", 10);

      handlerState_req202_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerState_req202", 10);

      handlerState_req203_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerState_req203", 10);

      handlerState_req102_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerState_req102", 10);

      handlerClassifier_empty_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerClassifier_empty", 10);

      handlerClassifier_assumption_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerClassifier_assumption", 10);

      handlerState_req103_publisher_ = this->create_publisher<std_msgs::msg::Empty>(
        "copilot/handlerState_req103", 10);

    }

    // Report (publish) monitor violations.
    void handlerState_req101() {
      auto output = std_msgs::msg::Empty();
      handlerState_req101_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerDtt_assumption() {
      auto output = std_msgs::msg::Empty();
      handlerDtt_assumption_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerState_req201() {
      auto output = std_msgs::msg::Empty();
      handlerState_req201_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerState_req202() {
      auto output = std_msgs::msg::Empty();
      handlerState_req202_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerState_req203() {
      auto output = std_msgs::msg::Empty();
      handlerState_req203_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerState_req102() {
      auto output = std_msgs::msg::Empty();
      handlerState_req102_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerClassifier_empty() {
      auto output = std_msgs::msg::Empty();
      handlerClassifier_empty_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerClassifier_assumption() {
      auto output = std_msgs::msg::Empty();
      handlerClassifier_assumption_publisher_->publish(output);
    }

    // Report (publish) monitor violations.
    void handlerState_req103() {
      auto output = std_msgs::msg::Empty();
      handlerState_req103_publisher_->publish(output);
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

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerState_req101_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerDtt_assumption_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerState_req201_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerState_req202_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerState_req203_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerState_req102_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerClassifier_empty_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerClassifier_assumption_publisher_;

    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr handlerState_req103_publisher_;

};

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerState_req101() {
  CopilotRV::getInstance()->handlerState_req101();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerDtt_assumption() {
  CopilotRV::getInstance()->handlerDtt_assumption();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerState_req201() {
  CopilotRV::getInstance()->handlerState_req201();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerState_req202() {
  CopilotRV::getInstance()->handlerState_req202();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerState_req203() {
  CopilotRV::getInstance()->handlerState_req203();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerState_req102() {
  CopilotRV::getInstance()->handlerState_req102();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerClassifier_empty() {
  CopilotRV::getInstance()->handlerClassifier_empty();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerClassifier_assumption() {
  CopilotRV::getInstance()->handlerClassifier_assumption();
}

// Pass monitor violations to the actual class, which has ways to
// communicate with other applications.
void handlerState_req103() {
  CopilotRV::getInstance()->handlerState_req103();
}

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(CopilotRV::getInstance());
  rclcpp::shutdown();
  return 0;
}

