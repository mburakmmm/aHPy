"""Representative runtime paths for the aHPy performance regression gate."""


def identity(value):
    return value


def add(left, right):
    return left + right


def make_pair(left, right):
    return [left, right]


def get_value(value):
    return value.value


def call_zero(callable_object):
    return callable_object()


def raise_value():
    raise ValueError("aHPy benchmark")
