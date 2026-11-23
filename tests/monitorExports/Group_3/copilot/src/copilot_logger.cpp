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

      handlerOperationalstate_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_1", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_1_callback, this, _1));

      handlerClassifier_assumption_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerClassifier_assumption", 10,
        std::bind(&CopilotLogger::handlerClassifier_assumption_callback, this, _1));

      handlerState_req103_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req103", 10,
        std::bind(&CopilotLogger::handlerState_req103_callback, this, _1));

      handlerOperationalstate_3_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_1", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_3_1_callback, this, _1));

      handlerOperationalstate_3_2_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_2", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_3_2_callback, this, _1));

      handlerOperationalstate_3_3_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_3", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_3_3_callback, this, _1));

      handlerOperationalstate_3_4_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_4", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_3_4_callback, this, _1));

      handlerOperationalstate_2_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_1", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_2_1_callback, this, _1));

      handlerOperationalstate_2_2_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_2", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_2_2_callback, this, _1));

      handlerOperationalstate_2_3_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_3", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_2_3_callback, this, _1));

      handlerOperationalstate_2_4_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_4", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_2_4_callback, this, _1));

      handlerOperationalstate_0_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_1", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_0_1_callback, this, _1));

      handlerOperationalstate_0_2_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_2", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_0_2_callback, this, _1));

      handlerOperationalstate_0_3_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_3", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_0_3_callback, this, _1));

      handlerOperationalstate_0_4_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_4", 10,
        std::bind(&CopilotLogger::handlerOperationalstate_0_4_callback, this, _1));

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

    void handlerOperationalstate_1_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_1");
    }

    void handlerClassifier_assumption_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerClassifier_assumption");
    }

    void handlerState_req103_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerState_req103");
    }

    void handlerOperationalstate_3_1_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_3_1");
    }

    void handlerOperationalstate_3_2_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_3_2");
    }

    void handlerOperationalstate_3_3_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_3_3");
    }

    void handlerOperationalstate_3_4_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_3_4");
    }

    void handlerOperationalstate_2_1_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_2_1");
    }

    void handlerOperationalstate_2_2_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_2_2");
    }

    void handlerOperationalstate_2_3_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_2_3");
    }

    void handlerOperationalstate_2_4_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_2_4");
    }

    void handlerOperationalstate_0_1_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_0_1");
    }

    void handlerOperationalstate_0_2_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_0_2");
    }

    void handlerOperationalstate_0_3_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_0_3");
    }

    void handlerOperationalstate_0_4_callback(const std_msgs::msg::Empty::SharedPtr msg) const {
      RCLCPP_INFO(this->get_logger(), "Copilot monitor violation: handlerOperationalstate_0_4");
    }

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req101_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerDtt_assumption_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req201_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req202_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req203_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req102_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerClassifier_empty_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_1_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerClassifier_assumption_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerState_req103_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_1_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_2_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_3_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_3_4_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_1_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_2_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_3_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_2_4_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_1_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_2_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_3_subscription_;

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerOperationalstate_0_4_subscription_;

};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CopilotLogger>());
  rclcpp::shutdown();
  return 0;
}


