#include <windows.h>

int main(void) {
    HANDLE heap = GetProcessHeap();
    volatile unsigned char *buffer =
        (volatile unsigned char *) HeapAlloc(heap, 0, 16);

    if (buffer == NULL) {
        return 2;
    }

    buffer[16] = 0xA5;
    HeapFree(heap, 0, (void *) buffer);
    return 0;
}
