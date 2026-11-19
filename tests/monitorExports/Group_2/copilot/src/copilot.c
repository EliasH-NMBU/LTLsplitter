#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

#include "copilot_types.h"
#include "copilot.h"

static int32_t classifier_cpy;
static int32_t distance_to_target_cpy;
static int32_t state_cpy;
static bool s0[(1)] = {(true)};
static bool s1[(1)] = {(true)};
static bool s2[(1)] = {(true)};
static bool s3[(1)] = {(true)};
static bool s4[(1)] = {(true)};
static bool s5[(1)] = {(true)};
static bool s6[(1)] = {(true)};
static bool s7[(1)] = {(true)};
static bool s8[(1)] = {(true)};
static size_t s0_idx = (0);
static size_t s1_idx = (0);
static size_t s2_idx = (0);
static size_t s3_idx = (0);
static size_t s4_idx = (0);
static size_t s5_idx = (0);
static size_t s6_idx = (0);
static size_t s7_idx = (0);
static size_t s8_idx = (0);

static bool s0_get(size_t x) {
  return (s0)[((s0_idx) + (x)) % ((size_t)(1))];
}

static bool s1_get(size_t x) {
  return (s1)[((s1_idx) + (x)) % ((size_t)(1))];
}

static bool s2_get(size_t x) {
  return (s2)[((s2_idx) + (x)) % ((size_t)(1))];
}

static bool s3_get(size_t x) {
  return (s3)[((s3_idx) + (x)) % ((size_t)(1))];
}

static bool s4_get(size_t x) {
  return (s4)[((s4_idx) + (x)) % ((size_t)(1))];
}

static bool s5_get(size_t x) {
  return (s5)[((s5_idx) + (x)) % ((size_t)(1))];
}

static bool s6_get(size_t x) {
  return (s6)[((s6_idx) + (x)) % ((size_t)(1))];
}

static bool s7_get(size_t x) {
  return (s7)[((s7_idx) + (x)) % ((size_t)(1))];
}

static bool s8_get(size_t x) {
  return (s8)[((s8_idx) + (x)) % ((size_t)(1))];
}

static bool s0_gen(void) {
  return ((!((classifier_cpy) == ((int32_t)(1)))) || ((!((distance_to_target_cpy) > ((int32_t)(7)))) || ((state_cpy) == ((int32_t)(1))))) && ((s0_get)((0)));
}

static bool s1_gen(void) {
  return ((!(!((classifier_cpy) == ((int32_t)(0))))) || ((distance_to_target_cpy) >= ((int32_t)(0)))) && ((s1_get)((0)));
}

static bool s2_gen(void) {
  return ((!((classifier_cpy) == ((int32_t)(2)))) || ((!((distance_to_target_cpy) > ((int32_t)(7)))) || ((state_cpy) == ((int32_t)(2))))) && ((s2_get)((0)));
}

static bool s3_gen(void) {
  return ((!((classifier_cpy) == ((int32_t)(2)))) || ((!((!((distance_to_target_cpy) > ((int32_t)(7)))) && ((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(3))))) && ((s3_get)((0)));
}

static bool s4_gen(void) {
  return ((!((classifier_cpy) == ((int32_t)(2)))) || ((!(!((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(3))))) && ((s4_get)((0)));
}

static bool s5_gen(void) {
  return ((!((classifier_cpy) == ((int32_t)(1)))) || ((!((!((distance_to_target_cpy) > ((int32_t)(7)))) && ((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(2))))) && ((s5_get)((0)));
}

static bool s6_gen(void) {
  return ((!((classifier_cpy) == ((int32_t)(0)))) || ((state_cpy) == ((int32_t)(0)))) && ((s6_get)((0)));
}

static bool s7_gen(void) {
  return (((!(((!((classifier_cpy) == ((int32_t)(0)))) && ((classifier_cpy) == ((int32_t)(1)))) || (((classifier_cpy) == ((int32_t)(0))) && (!((classifier_cpy) == ((int32_t)(1))))))) && ((classifier_cpy) == ((int32_t)(2)))) || ((((!((classifier_cpy) == ((int32_t)(0)))) && ((classifier_cpy) == ((int32_t)(1)))) || (((classifier_cpy) == ((int32_t)(0))) && (!((classifier_cpy) == ((int32_t)(1)))))) && (!((classifier_cpy) == ((int32_t)(2)))))) && ((s7_get)((0)));
}

static bool s8_gen(void) {
  return ((!((classifier_cpy) == ((int32_t)(1)))) || ((!(!((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(3))))) && ((s8_get)((0)));
}

static bool handlerState_req101_0_guard(void) {
  return !(((!((classifier_cpy) == ((int32_t)(1)))) || ((!((distance_to_target_cpy) > ((int32_t)(7)))) || ((state_cpy) == ((int32_t)(1))))) && ((s0_get)((0))));
}

static bool handlerDtt_assumption_1_guard(void) {
  return !(((!(!((classifier_cpy) == ((int32_t)(0))))) || ((distance_to_target_cpy) >= ((int32_t)(0)))) && ((s1_get)((0))));
}

static bool handlerState_req201_2_guard(void) {
  return !(((!((classifier_cpy) == ((int32_t)(2)))) || ((!((distance_to_target_cpy) > ((int32_t)(7)))) || ((state_cpy) == ((int32_t)(2))))) && ((s2_get)((0))));
}

static bool handlerState_req202_3_guard(void) {
  return !(((!((classifier_cpy) == ((int32_t)(2)))) || ((!((!((distance_to_target_cpy) > ((int32_t)(7)))) && ((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(3))))) && ((s3_get)((0))));
}

static bool handlerState_req203_4_guard(void) {
  return !(((!((classifier_cpy) == ((int32_t)(2)))) || ((!(!((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(3))))) && ((s4_get)((0))));
}

static bool handlerState_req102_5_guard(void) {
  return !(((!((classifier_cpy) == ((int32_t)(1)))) || ((!((!((distance_to_target_cpy) > ((int32_t)(7)))) && ((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(2))))) && ((s5_get)((0))));
}

static bool handlerClassifier_empty_6_guard(void) {
  return !(((!((classifier_cpy) == ((int32_t)(0)))) || ((state_cpy) == ((int32_t)(0)))) && ((s6_get)((0))));
}

static bool handlerClassifier_assumption_7_guard(void) {
  return !((((!(((!((classifier_cpy) == ((int32_t)(0)))) && ((classifier_cpy) == ((int32_t)(1)))) || (((classifier_cpy) == ((int32_t)(0))) && (!((classifier_cpy) == ((int32_t)(1))))))) && ((classifier_cpy) == ((int32_t)(2)))) || ((((!((classifier_cpy) == ((int32_t)(0)))) && ((classifier_cpy) == ((int32_t)(1)))) || (((classifier_cpy) == ((int32_t)(0))) && (!((classifier_cpy) == ((int32_t)(1)))))) && (!((classifier_cpy) == ((int32_t)(2)))))) && ((s7_get)((0))));
}

static bool handlerState_req103_8_guard(void) {
  return !(((!((classifier_cpy) == ((int32_t)(1)))) || ((!(!((distance_to_target_cpy) > ((int32_t)(3))))) || ((state_cpy) == ((int32_t)(3))))) && ((s8_get)((0))));
}

void step(void) {
  bool s0_tmp;
  bool s1_tmp;
  bool s2_tmp;
  bool s3_tmp;
  bool s4_tmp;
  bool s5_tmp;
  bool s6_tmp;
  bool s7_tmp;
  bool s8_tmp;
  (classifier_cpy) = (classifier);
  (distance_to_target_cpy) = (distance_to_target);
  (state_cpy) = (state);
  if ((handlerState_req101_0_guard)()) {
    {(handlerState_req101)();}
  };
  if ((handlerDtt_assumption_1_guard)()) {
    {(handlerDtt_assumption)();}
  };
  if ((handlerState_req201_2_guard)()) {
    {(handlerState_req201)();}
  };
  if ((handlerState_req202_3_guard)()) {
    {(handlerState_req202)();}
  };
  if ((handlerState_req203_4_guard)()) {
    {(handlerState_req203)();}
  };
  if ((handlerState_req102_5_guard)()) {
    {(handlerState_req102)();}
  };
  if ((handlerClassifier_empty_6_guard)()) {
    {(handlerClassifier_empty)();}
  };
  if ((handlerClassifier_assumption_7_guard)()) {
    {(handlerClassifier_assumption)();}
  };
  if ((handlerState_req103_8_guard)()) {
    {(handlerState_req103)();}
  };
  (s0_tmp) = ((s0_gen)());
  (s1_tmp) = ((s1_gen)());
  (s2_tmp) = ((s2_gen)());
  (s3_tmp) = ((s3_gen)());
  (s4_tmp) = ((s4_gen)());
  (s5_tmp) = ((s5_gen)());
  (s6_tmp) = ((s6_gen)());
  (s7_tmp) = ((s7_gen)());
  (s8_tmp) = ((s8_gen)());
  ((s0)[s0_idx]) = (s0_tmp);
  ((s1)[s1_idx]) = (s1_tmp);
  ((s2)[s2_idx]) = (s2_tmp);
  ((s3)[s3_idx]) = (s3_tmp);
  ((s4)[s4_idx]) = (s4_tmp);
  ((s5)[s5_idx]) = (s5_tmp);
  ((s6)[s6_idx]) = (s6_tmp);
  ((s7)[s7_idx]) = (s7_tmp);
  ((s8)[s8_idx]) = (s8_tmp);
  (s0_idx) = (((s0_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s1_idx) = (((s1_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s2_idx) = (((s2_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s3_idx) = (((s3_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s4_idx) = (((s4_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s5_idx) = (((s5_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s6_idx) = (((s6_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s7_idx) = (((s7_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s8_idx) = (((s8_idx) + ((size_t)(1))) % ((size_t)(1)));
}
