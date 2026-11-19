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
#include "std_msgs/msg/empty.hpp"
using std::placeholders::_1;

class CopilotLogger : public rclcpp::Node {
  public:
    CopilotLogger() : Node("copilotlogger") {
      handlerState_req101_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req101", 10,
        std::bind(&CopilotLogger::handlerState_req101_callback, this, _1));

      handlerDtt_assumption_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerDtt_assumption", 10,
        std::bind(&CopilotLogger::handlerDtt_assumption_callback, this, _1));

      handlerState_req201_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req201", 10,
        std::bind(&CopilotLogger::handlerState_req201_callback, this, _1));

      handlerState_req202_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req202", 10,
        std::bind(&CopilotLogger::handlerState_req202_callback, this, _1));

      handlerState_req203_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req203", 10,
        std::bind(&CopilotLogger::handlerState_req203_callback, this, _1));

      handlerState_req102_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req102", 10,
        std::bind(&CopilotLogger::handlerState_req102_callback, this, _1));

      handlerClassifier_empty_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerClassifier_empty", 10,
        std::bind(&CopilotLogger::handlerClassifier_empty_callback, this, _1));

      handlerClassifier_assumption_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerClassifier_assumption", 10,
        std::bind(&CopilotLogger::handlerClassifier_assumption_callback, this, _1));

      handlerState_req103_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req103", 10,
        std::bind(&CopilotLogger::handlerState_req103_callback, this, _1));

    }

  private:
    void handlerState_req101_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerState_req101");
    }

    void handlerDtt_assumption_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerDtt_assumption");
    }

    void handlerState_req201_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerState_req201");
    }

    void handlerState_req202_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerState_req202");
    }

    void handlerState_req203_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerState_req203");
    }

    void handlerState_req102_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerState_req102");
    }

    void handlerClassifier_empty_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerClassifier_empty");
    }

    void handlerClassifier_assumption_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerClassifier_assumption");
    }

    void handlerState_req103_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerState_req103");
    }

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req101_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerDtt_assumption_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req201_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req202_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req203_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req102_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerClassifier_empty_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerClassifier_assumption_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req103_subscription_;

};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CopilotLogger>());
  rclcpp::shutdown();
  return 0;
}


