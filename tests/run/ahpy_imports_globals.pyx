# mode: run
# tag: ahpy_candidate

import math


GLOBAL_VALUE = ("aHPy", 40)


def use_import(double value):
    """
    >>> use_import(9.0)
    3.0
    """
    return math.sqrt(value)


def read_global(int increment):
    """
    >>> read_global(2)
    ('aHPy', 42)
    """
    return GLOBAL_VALUE[0], GLOBAL_VALUE[1] + increment


def builtin_lookup(values):
    """
    >>> builtin_lookup([1, 2, 3])
    (3, 6)
    """
    return len(values), sum(values)
