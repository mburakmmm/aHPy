#ifndef AHPY_EXTERNAL_H
#define AHPY_EXTERNAL_H

long long ahpy_external_signed_answer(void);
unsigned long long ahpy_external_unsigned_answer(void);
double ahpy_external_ratio(void);
int ahpy_external_ready(void);
long long ahpy_external_add(long long left, long long right);
signed char ahpy_external_byte(signed char value);
int ahpy_external_byte_calls(void);
double ahpy_external_scale(double value, double factor);
long long ahpy_external_nogil_probe(void);
long long ahpy_external_nogil_advance(long long amount);
long long ahpy_external_nogil_probe_calls(void);

#endif
