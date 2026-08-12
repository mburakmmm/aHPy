cdef extern from "ahpy_murmur_scalar.h":
    unsigned long long ahpy_murmur3_u64(
        unsigned long long value,
        unsigned long long seed,
    ) noexcept nogil
    unsigned long long ahpy_murmur_calls()


def hash_u64(value, seed=0):
    return ahpy_murmur3_u64(value, seed)


def hash_u64_nogil(value, seed=0):
    with nogil:
        result = ahpy_murmur3_u64(value, seed)
    return result


def native_calls():
    return ahpy_murmur_calls()
