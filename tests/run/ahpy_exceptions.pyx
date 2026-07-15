# mode: run
# tag: ahpy_candidate


def divide_or_none(int numerator, int denominator):
    """
    >>> divide_or_none(8, 2)
    4
    >>> divide_or_none(8, 0) is None
    True
    """
    try:
        return numerator // denominator
    except ZeroDivisionError:
        return None


def raise_with_payload(value):
    """
    >>> raise_with_payload("payload")
    Traceback (most recent call last):
    ...
    ValueError: ['payload']
    """
    payload = [value]
    raise ValueError(payload)


def chained_error(value):
    """
    >>> chained_error("bad")
    Traceback (most recent call last):
    ...
    RuntimeError: converted
    """
    try:
        raise ValueError(value)
    except ValueError as error:
        raise RuntimeError("converted") from error
