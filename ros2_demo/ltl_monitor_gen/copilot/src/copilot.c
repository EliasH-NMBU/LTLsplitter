#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

#include "copilot_types.h"
#include "copilot.h"

static bool human_detected_cpy;
static bool stopped_cpy;
static bool s0[(1)] = {(true)};
static size_t s0_idx = (0);

static bool s0_get(size_t x) {
  return (s0)[((s0_idx) + (x)) % ((size_t)(1))];
}

static bool s0_gen(void) {
  return ((!(human_detected_cpy)) || (stopped_cpy)) && ((s0_get)((0)));
}

static bool handlerR1_0_guard(void) {
  return !(((!(human_detected_cpy)) || (stopped_cpy)) && ((s0_get)((0))));
}

void step(void) {
  bool s0_tmp;
  (human_detected_cpy) = (human_detected);
  (stopped_cpy) = (stopped);
  if ((handlerR1_0_guard)()) {
    {(handlerR1)();}
  };
  (s0_tmp) = ((s0_gen)());
  ((s0)[s0_idx]) = (s0_tmp);
  (s0_idx) = (((s0_idx) + ((size_t)(1))) % ((size_t)(1)));
}
