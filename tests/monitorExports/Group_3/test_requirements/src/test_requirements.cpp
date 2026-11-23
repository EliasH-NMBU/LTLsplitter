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


      alert_publisher_ = this->create_publisher<std_msgs::msg::Bool>(
        "/alert", 10);

      classifier_publisher_ = this->create_publisher<std_msgs::msg::Int32>(
        "/classifier", 10);

      distance_to_target_publisher_ = this->create_publisher<std_msgs::msg::Int32>(
        "/distance_to_target", 10);

      halt_publisher_ = this->create_publisher<std_msgs::msg::Bool>(
        "/halt", 10);

      slowdown_publisher_ = this->create_publisher<std_msgs::msg::Bool>(
        "/slowdown", 10);

      state_publisher_ = this->create_publisher<std_msgs::msg::Int32>(
        "/state", 10);

      turnoffUVC_publisher_ = this->create_publisher<std_msgs::msg::Bool>(
        "/turnoffUVC", 10);


      handlerState_req101_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req101", 10,
        std::bind(&RequirementsTest::handlerState_req101_callback, this, _1));

      handlerDtt_assumption_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerDtt_assumption", 10,
        std::bind(&RequirementsTest::handlerDtt_assumption_callback, this, _1));

      handlerState_req201_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req201", 10,
        std::bind(&RequirementsTest::handlerState_req201_callback, this, _1));

      handlerState_req202_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req202", 10,
        std::bind(&RequirementsTest::handlerState_req202_callback, this, _1));

      handlerState_req203_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req203", 10,
        std::bind(&RequirementsTest::handlerState_req203_callback, this, _1));

      handlerState_req102_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req102", 10,
        std::bind(&RequirementsTest::handlerState_req102_callback, this, _1));

      handlerClassifier_empty_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerClassifier_empty", 10,
        std::bind(&RequirementsTest::handlerClassifier_empty_callback, this, _1));

      handlerOperationalstate_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_1", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_1_callback, this, _1));

      handlerClassifier_assumption_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerClassifier_assumption", 10,
        std::bind(&RequirementsTest::handlerClassifier_assumption_callback, this, _1));

      handlerState_req103_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerState_req103", 10,
        std::bind(&RequirementsTest::handlerState_req103_callback, this, _1));

      handlerOperationalstate_3_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_1", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_3_1_callback, this, _1));

      handlerOperationalstate_3_2_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_2", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_3_2_callback, this, _1));

      handlerOperationalstate_3_3_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_3", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_3_3_callback, this, _1));

      handlerOperationalstate_3_4_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_3_4", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_3_4_callback, this, _1));

      handlerOperationalstate_2_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_1", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_2_1_callback, this, _1));

      handlerOperationalstate_2_2_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_2", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_2_2_callback, this, _1));

      handlerOperationalstate_2_3_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_3", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_2_3_callback, this, _1));

      handlerOperationalstate_2_4_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_2_4", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_2_4_callback, this, _1));

      handlerOperationalstate_0_1_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_1", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_0_1_callback, this, _1));

      handlerOperationalstate_0_2_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_2", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_0_2_callback, this, _1));

      handlerOperationalstate_0_3_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_3", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_0_3_callback, this, _1));

      handlerOperationalstate_0_4_subscription_ = this->create_subscription<std_msgs::msg::Empty>(
        "copilot/handlerOperationalstate_0_4", 10,
        std::bind(&RequirementsTest::handlerOperationalstate_0_4_callback, this, _1));


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


    bool violation_handlerState_req101 = false;

    bool violation_handlerDtt_assumption = false;

    bool violation_handlerState_req201 = false;

    bool violation_handlerState_req202 = false;

    bool violation_handlerState_req203 = false;

    bool violation_handlerState_req102 = false;

    bool violation_handlerClassifier_empty = false;

    bool violation_handlerOperationalstate_1 = false;

    bool violation_handlerClassifier_assumption = false;

    bool violation_handlerState_req103 = false;

    bool violation_handlerOperationalstate_3_1 = false;

    bool violation_handlerOperationalstate_3_2 = false;

    bool violation_handlerOperationalstate_3_3 = false;

    bool violation_handlerOperationalstate_3_4 = false;

    bool violation_handlerOperationalstate_2_1 = false;

    bool violation_handlerOperationalstate_2_2 = false;

    bool violation_handlerOperationalstate_2_3 = false;

    bool violation_handlerOperationalstate_2_4 = false;

    bool violation_handlerOperationalstate_0_1 = false;

    bool violation_handlerOperationalstate_0_2 = false;

    bool violation_handlerOperationalstate_0_3 = false;

    bool violation_handlerOperationalstate_0_4 = false;

    bool violations = false;


    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr alert_publisher_;

    rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr classifier_publisher_;

    rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr distance_to_target_publisher_;

    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr halt_publisher_;

    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr slowdown_publisher_;

    rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr state_publisher_;

    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr turnoffUVC_publisher_;

    void handlerState_req101_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerState_req101 = true;
        this->violations = true;
    }
    void handlerDtt_assumption_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerDtt_assumption = true;
        this->violations = true;
    }
    void handlerState_req201_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerState_req201 = true;
        this->violations = true;
    }
    void handlerState_req202_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerState_req202 = true;
        this->violations = true;
    }
    void handlerState_req203_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerState_req203 = true;
        this->violations = true;
    }
    void handlerState_req102_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerState_req102 = true;
        this->violations = true;
    }
    void handlerClassifier_empty_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerClassifier_empty = true;
        this->violations = true;
    }
    void handlerOperationalstate_1_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_1 = true;
        this->violations = true;
    }
    void handlerClassifier_assumption_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerClassifier_assumption = true;
        this->violations = true;
    }
    void handlerState_req103_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerState_req103 = true;
        this->violations = true;
    }
    void handlerOperationalstate_3_1_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_3_1 = true;
        this->violations = true;
    }
    void handlerOperationalstate_3_2_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_3_2 = true;
        this->violations = true;
    }
    void handlerOperationalstate_3_3_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_3_3 = true;
        this->violations = true;
    }
    void handlerOperationalstate_3_4_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_3_4 = true;
        this->violations = true;
    }
    void handlerOperationalstate_2_1_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_2_1 = true;
        this->violations = true;
    }
    void handlerOperationalstate_2_2_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_2_2 = true;
        this->violations = true;
    }
    void handlerOperationalstate_2_3_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_2_3 = true;
        this->violations = true;
    }
    void handlerOperationalstate_2_4_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_2_4 = true;
        this->violations = true;
    }
    void handlerOperationalstate_0_1_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_0_1 = true;
        this->violations = true;
    }
    void handlerOperationalstate_0_2_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_0_2 = true;
        this->violations = true;
    }
    void handlerOperationalstate_0_3_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_0_3 = true;
        this->violations = true;
    }
    void handlerOperationalstate_0_4_callback(const std_msgs::msg::Empty::SharedPtr msg) {
        this->violation_handlerOperationalstate_0_4 = true;
        this->violations = true;
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

       bool alert_data = randomBool();
       auto alert_data_msg = std_msgs::msg::Bool();
       alert_data_msg.data = alert_data;
       alert_publisher_->publish(alert_data_msg);

       int32_t classifier_data = randomInt();
       auto classifier_data_msg = std_msgs::msg::Int32();
       classifier_data_msg.data = classifier_data;
       classifier_publisher_->publish(classifier_data_msg);

       int32_t distance_to_target_data = randomInt();
       auto distance_to_target_data_msg = std_msgs::msg::Int32();
       distance_to_target_data_msg.data = distance_to_target_data;
       distance_to_target_publisher_->publish(distance_to_target_data_msg);

       bool halt_data = randomBool();
       auto halt_data_msg = std_msgs::msg::Bool();
       halt_data_msg.data = halt_data;
       halt_publisher_->publish(halt_data_msg);

       bool slowdown_data = randomBool();
       auto slowdown_data_msg = std_msgs::msg::Bool();
       slowdown_data_msg.data = slowdown_data;
       slowdown_publisher_->publish(slowdown_data_msg);

       int32_t state_data = randomInt();
       auto state_data_msg = std_msgs::msg::Int32();
       state_data_msg.data = state_data;
       state_publisher_->publish(state_data_msg);

       bool turnoffUVC_data = randomBool();
       auto turnoffUVC_data_msg = std_msgs::msg::Bool();
       turnoffUVC_data_msg.data = turnoffUVC_data;
       turnoffUVC_publisher_->publish(turnoffUVC_data_msg);



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

        if (this->violation_handlerState_req101) {
            this->publish_violation("handlerState_req101");
        }

        if (this->violation_handlerDtt_assumption) {
            this->publish_violation("handlerDtt_assumption");
        }

        if (this->violation_handlerState_req201) {
            this->publish_violation("handlerState_req201");
        }

        if (this->violation_handlerState_req202) {
            this->publish_violation("handlerState_req202");
        }

        if (this->violation_handlerState_req203) {
            this->publish_violation("handlerState_req203");
        }

        if (this->violation_handlerState_req102) {
            this->publish_violation("handlerState_req102");
        }

        if (this->violation_handlerClassifier_empty) {
            this->publish_violation("handlerClassifier_empty");
        }

        if (this->violation_handlerOperationalstate_1) {
            this->publish_violation("handlerOperationalstate_1");
        }

        if (this->violation_handlerClassifier_assumption) {
            this->publish_violation("handlerClassifier_assumption");
        }

        if (this->violation_handlerState_req103) {
            this->publish_violation("handlerState_req103");
        }

        if (this->violation_handlerOperationalstate_3_1) {
            this->publish_violation("handlerOperationalstate_3_1");
        }

        if (this->violation_handlerOperationalstate_3_2) {
            this->publish_violation("handlerOperationalstate_3_2");
        }

        if (this->violation_handlerOperationalstate_3_3) {
            this->publish_violation("handlerOperationalstate_3_3");
        }

        if (this->violation_handlerOperationalstate_3_4) {
            this->publish_violation("handlerOperationalstate_3_4");
        }

        if (this->violation_handlerOperationalstate_2_1) {
            this->publish_violation("handlerOperationalstate_2_1");
        }

        if (this->violation_handlerOperationalstate_2_2) {
            this->publish_violation("handlerOperationalstate_2_2");
        }

        if (this->violation_handlerOperationalstate_2_3) {
            this->publish_violation("handlerOperationalstate_2_3");
        }

        if (this->violation_handlerOperationalstate_2_4) {
            this->publish_violation("handlerOperationalstate_2_4");
        }

        if (this->violation_handlerOperationalstate_0_1) {
            this->publish_violation("handlerOperationalstate_0_1");
        }

        if (this->violation_handlerOperationalstate_0_2) {
            this->publish_violation("handlerOperationalstate_0_2");
        }

        if (this->violation_handlerOperationalstate_0_3) {
            this->publish_violation("handlerOperationalstate_0_3");
        }

        if (this->violation_handlerOperationalstate_0_4) {
            this->publish_violation("handlerOperationalstate_0_4");
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
