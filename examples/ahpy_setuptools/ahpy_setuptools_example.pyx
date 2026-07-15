def answer():
    return 42


cdef extern from "ahpy_external.h":
    long long ahpy_external_signed_answer()
    unsigned long long ahpy_external_unsigned_answer()
    double ahpy_external_ratio()
    bint ahpy_external_ready()
    long long ahpy_external_add(long long left, long long right)
    signed char ahpy_external_byte(signed char value)
    int ahpy_external_byte_calls()
    double ahpy_external_scale(double value, double factor)


def external_signed_answer():
    return ahpy_external_signed_answer()


def external_unsigned_answer():
    return ahpy_external_unsigned_answer()


def external_ratio():
    return ahpy_external_ratio()


def external_ready():
    return ahpy_external_ready()


def external_add(left, right):
    return ahpy_external_add(left, right)


def external_byte(value):
    return ahpy_external_byte(value)


def external_byte_calls():
    return ahpy_external_byte_calls()


def external_scale(value, factor):
    return ahpy_external_scale(value, factor)


cdef class Box:
    cdef public object value

    def __init__(self, value, /):
        self.value = value

    def identity(self):
        return self.value
