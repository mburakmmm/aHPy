# mode: run
# tag: ahpy_candidate


def consume_or_raise(value, fail):
    """
    >>> consume_or_raise("ok", False)
    'ok'
    >>> consume_or_raise("bad", True)
    Traceback (most recent call last):
    ...
    RuntimeError: ['bad']
    """
    temporary = [value]
    if fail:
        raise RuntimeError(temporary)
    return temporary.pop()


def nested_early_return(flag, value):
    """
    >>> nested_early_return(True, 10)
    10
    >>> nested_early_return(False, 10) is None
    True
    """
    first = [value]
    second = {"first": first}
    if flag:
        return second["first"][0]
    return None


def loop_cleanup(values, stop):
    """
    >>> loop_cleanup([1, 2, 3], 2)
    2
    >>> loop_cleanup([1, 2, 3], 5) is None
    True
    """
    for value in values:
        temporary = (value, [value])
        if value == stop:
            return temporary[0]
    return None
