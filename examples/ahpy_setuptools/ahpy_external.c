#include "ahpy_external.h"

static int ahpy_external_byte_call_count;
static long long ahpy_external_nogil_probe_call_count;

long long ahpy_external_signed_answer(void)
{
    return -42;
}

unsigned long long ahpy_external_unsigned_answer(void)
{
    return 18446744073709551615ULL;
}

double ahpy_external_ratio(void)
{
    return 0.125;
}

int ahpy_external_ready(void)
{
    return 1;
}

long long ahpy_external_add(long long left, long long right)
{
    return left + right;
}

signed char ahpy_external_byte(signed char value)
{
    ahpy_external_byte_call_count += 1;
    return value;
}

int ahpy_external_byte_calls(void)
{
    return ahpy_external_byte_call_count;
}

double ahpy_external_scale(double value, double factor)
{
    return value * factor;
}

long long ahpy_external_nogil_probe(void)
{
    ahpy_external_nogil_probe_call_count += 1;
    return ahpy_external_nogil_probe_call_count;
}

long long ahpy_external_nogil_probe_calls(void)
{
    return ahpy_external_nogil_probe_call_count;
}
