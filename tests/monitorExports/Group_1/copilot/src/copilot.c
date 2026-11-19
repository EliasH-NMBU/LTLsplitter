#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

#include "copilot_types.h"
#include "copilot.h"

static int32_t state_cpy;
static bool turnoffUVC_cpy;
static bool alert_cpy;
static bool halt_cpy;
static bool slowdown_cpy;
static bool s0[(1)] = {(true)};
static bool s1[(1)] = {(true)};
static bool s2[(1)] = {(true)};
static bool s3[(1)] = {(true)};
static bool s4[(1)] = {(true)};
static bool s5[(1)] = {(true)};
static bool s6[(1)] = {(true)};
static bool s7[(1)] = {(true)};
static bool s8[(1)] = {(true)};
static bool s9[(1)] = {(true)};
static bool s10[(1)] = {(true)};
static bool s11[(1)] = {(true)};
static bool s12[(1)] = {(true)};
static size_t s0_idx = (0);
static size_t s1_idx = (0);
static size_t s2_idx = (0);
static size_t s3_idx = (0);
static size_t s4_idx = (0);
static size_t s5_idx = (0);
static size_t s6_idx = (0);
static size_t s7_idx = (0);
static size_t s8_idx = (0);
static size_t s9_idx = (0);
static size_t s10_idx = (0);
static size_t s11_idx = (0);
static size_t s12_idx = (0);

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

static bool s9_get(size_t x) {
  return (s9)[((s9_idx) + (x)) % ((size_t)(1))];
}

static bool s10_get(size_t x) {
  return (s10)[((s10_idx) + (x)) % ((size_t)(1))];
}

static bool s11_get(size_t x) {
  return (s11)[((s11_idx) + (x)) % ((size_t)(1))];
}

static bool s12_get(size_t x) {
  return (s12)[((s12_idx) + (x)) % ((size_t)(1))];
}

static bool s0_gen(void) {
  return ((!((state_cpy) == ((int32_t)(0)))) || (!(turnoffUVC_cpy))) && ((s0_get)((0)));
}

static bool s1_gen(void) {
  return ((!((state_cpy) == ((int32_t)(0)))) || (!(alert_cpy))) && ((s1_get)((0)));
}

static bool s2_gen(void) {
  return ((!((state_cpy) == ((int32_t)(0)))) || (!(halt_cpy))) && ((s2_get)((0)));
}

static bool s3_gen(void) {
  return ((!((state_cpy) == ((int32_t)(0)))) || (!(slowdown_cpy))) && ((s3_get)((0)));
}

static bool s4_gen(void) {
  return ((!((state_cpy) == ((int32_t)(2)))) || (!(turnoffUVC_cpy))) && ((s4_get)((0)));
}

static bool s5_gen(void) {
  return ((!((state_cpy) == ((int32_t)(2)))) || (alert_cpy)) && ((s5_get)((0)));
}

static bool s6_gen(void) {
  return ((!((state_cpy) == ((int32_t)(2)))) || (halt_cpy)) && ((s6_get)((0)));
}

static bool s7_gen(void) {
  return ((!((state_cpy) == ((int32_t)(2)))) || (!(slowdown_cpy))) && ((s7_get)((0)));
}

static bool s8_gen(void) {
  return ((!((state_cpy) == ((int32_t)(3)))) || (turnoffUVC_cpy)) && ((s8_get)((0)));
}

static bool s9_gen(void) {
  return ((!((state_cpy) == ((int32_t)(3)))) || (alert_cpy)) && ((s9_get)((0)));
}

static bool s10_gen(void) {
  return ((!((state_cpy) == ((int32_t)(3)))) || (halt_cpy)) && ((s10_get)((0)));
}

static bool s11_gen(void) {
  return ((!((state_cpy) == ((int32_t)(3)))) || (!(slowdown_cpy))) && ((s11_get)((0)));
}

static bool s12_gen(void) {
  return ((!((state_cpy) == ((int32_t)(1)))) || ((((slowdown_cpy) && (!(halt_cpy))) && (alert_cpy)) && (!(turnoffUVC_cpy)))) && ((s12_get)((0)));
}

static bool handlerOperationalstate_0_4_0_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(0)))) || (!(turnoffUVC_cpy))) && ((s0_get)((0))));
}

static bool handlerOperationalstate_0_3_1_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(0)))) || (!(alert_cpy))) && ((s1_get)((0))));
}

static bool handlerOperationalstate_0_2_2_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(0)))) || (!(halt_cpy))) && ((s2_get)((0))));
}

static bool handlerOperationalstate_0_1_3_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(0)))) || (!(slowdown_cpy))) && ((s3_get)((0))));
}

static bool handlerOperationalstate_2_4_4_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(2)))) || (!(turnoffUVC_cpy))) && ((s4_get)((0))));
}

static bool handlerOperationalstate_2_3_5_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(2)))) || (alert_cpy)) && ((s5_get)((0))));
}

static bool handlerOperationalstate_2_2_6_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(2)))) || (halt_cpy)) && ((s6_get)((0))));
}

static bool handlerOperationalstate_2_1_7_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(2)))) || (!(slowdown_cpy))) && ((s7_get)((0))));
}

static bool handlerOperationalstate_3_4_8_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(3)))) || (turnoffUVC_cpy)) && ((s8_get)((0))));
}

static bool handlerOperationalstate_3_3_9_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(3)))) || (alert_cpy)) && ((s9_get)((0))));
}

static bool handlerOperationalstate_3_2_10_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(3)))) || (halt_cpy)) && ((s10_get)((0))));
}

static bool handlerOperationalstate_3_1_11_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(3)))) || (!(slowdown_cpy))) && ((s11_get)((0))));
}

static bool handlerOperationalstate_1_12_guard(void) {
  return !(((!((state_cpy) == ((int32_t)(1)))) || ((((slowdown_cpy) && (!(halt_cpy))) && (alert_cpy)) && (!(turnoffUVC_cpy)))) && ((s12_get)((0))));
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
  bool s9_tmp;
  bool s10_tmp;
  bool s11_tmp;
  bool s12_tmp;
  (state_cpy) = (state);
  (turnoffUVC_cpy) = (turnoffUVC);
  (alert_cpy) = (alert);
  (halt_cpy) = (halt);
  (slowdown_cpy) = (slowdown);
  if ((handlerOperationalstate_0_4_0_guard)()) {
    {(handlerOperationalstate_0_4)();}
  };
  if ((handlerOperationalstate_0_3_1_guard)()) {
    {(handlerOperationalstate_0_3)();}
  };
  if ((handlerOperationalstate_0_2_2_guard)()) {
    {(handlerOperationalstate_0_2)();}
  };
  if ((handlerOperationalstate_0_1_3_guard)()) {
    {(handlerOperationalstate_0_1)();}
  };
  if ((handlerOperationalstate_2_4_4_guard)()) {
    {(handlerOperationalstate_2_4)();}
  };
  if ((handlerOperationalstate_2_3_5_guard)()) {
    {(handlerOperationalstate_2_3)();}
  };
  if ((handlerOperationalstate_2_2_6_guard)()) {
    {(handlerOperationalstate_2_2)();}
  };
  if ((handlerOperationalstate_2_1_7_guard)()) {
    {(handlerOperationalstate_2_1)();}
  };
  if ((handlerOperationalstate_3_4_8_guard)()) {
    {(handlerOperationalstate_3_4)();}
  };
  if ((handlerOperationalstate_3_3_9_guard)()) {
    {(handlerOperationalstate_3_3)();}
  };
  if ((handlerOperationalstate_3_2_10_guard)()) {
    {(handlerOperationalstate_3_2)();}
  };
  if ((handlerOperationalstate_3_1_11_guard)()) {
    {(handlerOperationalstate_3_1)();}
  };
  if ((handlerOperationalstate_1_12_guard)()) {
    {(handlerOperationalstate_1)();}
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
  (s9_tmp) = ((s9_gen)());
  (s10_tmp) = ((s10_gen)());
  (s11_tmp) = ((s11_gen)());
  (s12_tmp) = ((s12_gen)());
  ((s0)[s0_idx]) = (s0_tmp);
  ((s1)[s1_idx]) = (s1_tmp);
  ((s2)[s2_idx]) = (s2_tmp);
  ((s3)[s3_idx]) = (s3_tmp);
  ((s4)[s4_idx]) = (s4_tmp);
  ((s5)[s5_idx]) = (s5_tmp);
  ((s6)[s6_idx]) = (s6_tmp);
  ((s7)[s7_idx]) = (s7_tmp);
  ((s8)[s8_idx]) = (s8_tmp);
  ((s9)[s9_idx]) = (s9_tmp);
  ((s10)[s10_idx]) = (s10_tmp);
  ((s11)[s11_idx]) = (s11_tmp);
  ((s12)[s12_idx]) = (s12_tmp);
  (s0_idx) = (((s0_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s1_idx) = (((s1_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s2_idx) = (((s2_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s3_idx) = (((s3_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s4_idx) = (((s4_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s5_idx) = (((s5_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s6_idx) = (((s6_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s7_idx) = (((s7_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s8_idx) = (((s8_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s9_idx) = (((s9_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s10_idx) = (((s10_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s11_idx) = (((s11_idx) + ((size_t)(1))) % ((size_t)(1)));
  (s12_idx) = (((s12_idx) + ((size_t)(1))) % ((size_t)(1)));
}
