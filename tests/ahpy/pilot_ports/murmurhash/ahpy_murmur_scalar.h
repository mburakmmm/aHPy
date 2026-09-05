#ifndef AHPY_MURMUR_SCALAR_H
#define AHPY_MURMUR_SCALAR_H

#ifdef __cplusplus
extern "C" {
#endif

unsigned long long ahpy_murmur3_u64(
    unsigned long long value,
    unsigned long long seed);
unsigned long long ahpy_murmur_calls(void);

#ifdef __cplusplus
}
#endif

#endif
