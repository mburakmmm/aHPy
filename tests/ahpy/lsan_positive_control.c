#include <stdlib.h>

int ahpy_lsan_positive_control_leak(void)
{
    void *leak = malloc(64);
    (void)leak;
    return 0;
}

int main(void)
{
    return ahpy_lsan_positive_control_leak();
}
