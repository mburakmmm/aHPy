# mode: compile
# distutils: sources = ../../../../tests/ahpy/benchmark_external.c

"""Representative runtime paths for the aHPy performance regression gate."""


cdef extern from "benchmark_external.h":
    long long ahpy_benchmark_external_add(long long left, long long right)


cdef class BenchmarkBox:
    cdef object value

    def __cinit__(self, value, /):
        self.value = value

    def identity(self):
        return self.value


def identity(value, /):
    return value


def add(left, right, /):
    return left + right


def make_pair(left, right, /):
    return [left, right]


def get_value(value, /):
    return value.value


def call_zero(callable_object, /):
    return callable_object()


def raise_value():
    raise ValueError("aHPy benchmark")


def external_add():
    return ahpy_benchmark_external_add(20, 22)
