#include <functional>
#include <memory>

#include "gtest/gtest.h"

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

using std::placeholders::_1;

class RequirementsTest : public rclcpp::Node {
  public:
    RequirementsTest() : Node("requirementstest") {

      declare_parameter("testing_seed", 0); // defaults to 0
      declare_parameter("testing_deadline", 2); // defaults to 2 secs


      human_detected_publisher_ = this->create_publisher<std_msgs::msg::Bool>(
        "/human_detected", 10);

      stopped_publisher_ = this->create_publisher<std_msgs::msg::Bool>(
        "/stopped", 10);


      handlerR1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerR1", 10,
        std::bind(&RequirementsTest::handlerR1_callback, this, _1));


      get_parameter("testing_seed", initial_seed);
      get_parameter("testing_deadline", deadline);

      std::srand((unsigned int)this->initial_seed);

      this->seed = this->initial_seed;
      this->max_tests = calculate_num_tests();

      rclcpp::Duration update_period = rclcpp::Duration::from_seconds(1);
      timerInit = rclcpp::create_timer(this->get_node_base_interface(),
                                       this->get_node_timers_interface(),
                                       this->get_node_clock_interface()->get_clock(),
                                       update_period,
                                       std::bind(&RequirementsTest::tests_init, this)
                                       );
    }

  private:


    bool violation_handlerR1 = false;

    bool violations = false;


    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr human_detected_publisher_;

    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr stopped_publisher_;

    void handlerR1_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerR1 = true;
        this->violations = true;
    }

    rclcpp::Subscription<std_msgs::msg::Empty>::SharedPtr handlerR1_subscription_;



    int initial_seed; // To be configured using a parameter.
    int seed;         // To be configured using a parameter.
    int deadline;     // To be configured using a parameter.

    int max_tests;
    int num_test = 0;

    // Calculate the number of tests to be executed
    int calculate_num_tests() {
       return abs(std::rand());
    }

    rclcpp::TimerBase::SharedPtr timerResult;
    rclcpp::TimerBase::SharedPtr timerInit;

    void tests_init () {
        timerInit->cancel();
        tests_step_send();
    }

    void tests_step_send () {

       bool human_detected_data = randomBool();
       auto human_detected_data_msg = std_msgs::msg::Bool();
       human_detected_data_msg.data = human_detected_data;
       human_detected_publisher_->publish(human_detected_data_msg);

       bool stopped_data = randomBool();
       auto stopped_data_msg = std_msgs::msg::Bool();
       stopped_data_msg.data = stopped_data;
       stopped_publisher_->publish(stopped_data_msg);



        rclcpp::Duration update_period = rclcpp::Duration::from_seconds(deadline);
        timerResult = rclcpp::create_timer(this->get_node_base_interface(),
                                           this->get_node_timers_interface(),
                                           this->get_node_clock_interface()->get_clock(),
                                           update_period,
                                           std::bind(&RequirementsTest::tests_step_result, this)
                                           );
    }

    void tests_step_result () {
        timerResult->cancel();

        if (this->violation_handlerR1) {
            this->publish_violation("handlerR1");
        }


       this->num_test++;

       // Stop if out of steps or there have been violations
       if ((this->num_test >= this->max_tests) || violations) {
         // Terminate using the gtest mechanism to indicate the result
         if (violations) {
           RCLCPP_INFO(this->get_logger(), "Tests failed");
           // FAIL();
         } else {
           RCLCPP_INFO(this->get_logger(), "Tests succeeded");
           // SUCCEED();
         }
         rclcpp::shutdown();
       } else {
         tests_step_send();
       }
    }

    float randomFloat() {
       int numerator = rand();
       int denominator = rand();

       // Ensure that we do not divide by zero.
       if (denominator == 0) {
           denominator = 1;
       }

       return (float)numerator / (float)denominator;
    }

    int randomInt() {
       return rand();
    }

    bool randomBool() {
       return rand() & 1;
    }

    void delay(int time) {
       rclcpp::sleep_for(std::chrono::seconds(time));
    }

    void publish_violation (const char* requirement) {
        RCLCPP_INFO(this->get_logger(), "Requirement violation. Req: %s; Seed: %d; Step: %d\\n",
            requirement, this->initial_seed, this->num_test);
    }
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<RequirementsTest>());
  rclcpp::shutdown();
  return 0;
}
