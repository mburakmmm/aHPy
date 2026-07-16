cdef extern from "fault_injection_helpers.h":
    long long __pyx_ahpy_fault_long(long long value)


cdef class FaultType:
    pass


cdef class FaultTypeSecond:
    pass


cdef class FaultTypeThird:
    pass


def build_values():
    # External C longs force runtime HPyLong_FromLongLong (module int caches
    # skip that API at call sites that only Dup cached attributes).
    return [
        __pyx_ahpy_fault_long(101),
        __pyx_ahpy_fault_long(102),
        __pyx_ahpy_fault_long(103),
    ]


def build_nested_lists():
    return [
        [__pyx_ahpy_fault_long(101)],
        [__pyx_ahpy_fault_long(102), __pyx_ahpy_fault_long(103)],
    ]


def build_nested_tuples(value, /):
    return ((value,), (value, value))


def build_dictionary(value, /):
    return {"first": value, "second": value, "third": value}


def call_variants(callable, value, /):
    first = callable()
    second = callable(value)
    third = callable(value, second)
    fourth = callable(value, second=third)
    return [first, second, third, fourth]


def call_expanded(callable, positional, keywords, /):
    return callable(*positional, **keywords)


def call_method_variants(value, /):
    # One HPy_CallMethod site for fault injection (receiver as args[0]).
    return value.upper()


def read_attributes(value, /):
    return [value.first, value.second, value.third]


def read_items(value, /):
    return [value["first"], value["second"], value["third"]]


def write_attribute(target, value, /):
    target.answer = value
    return target.answer


def delete_attribute(target, /):
    del target.answer
    return None


def write_item(target, value, /):
    target["answer"] = value
    return target["answer"]


def delete_item(target, /):
    del target["answer"]
    return None


def fault_types():
    return (FaultType, FaultTypeSecond, FaultTypeThird)
