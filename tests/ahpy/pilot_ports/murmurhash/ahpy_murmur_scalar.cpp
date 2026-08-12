#include <stdint.h>

#include "ahpy_murmur_scalar.h"
#include "murmurhash/MurmurHash3.h"

static unsigned long long ahpy_calls = 0;

extern "C" unsigned long long ahpy_murmur3_u64(
        unsigned long long value,
        unsigned long long seed) {
    uint8_t bytes[8];
    uint32_t output = 0;
    ++ahpy_calls;
    for (unsigned int index = 0; index < 8; ++index) {
        bytes[index] = (uint8_t) (value >> (index * 8));
    }
    MurmurHash3_x86_32(bytes, 8, (uint32_t) seed, &output);
    return (unsigned long long) output;
}

extern "C" unsigned long long ahpy_murmur_calls(void) {
    return ahpy_calls;
}
