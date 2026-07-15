# mode: run
# tag: ahpy_candidate


def add_ints(int left, int right):
    """
    >>> add_ints(20, 22)
    42
    >>> add_ints(-10, 3)
    -7
    """
    return left + right


def echo(value):
    """
    >>> marker = object()
    >>> echo(marker) is marker
    True
    """
    return value


def keyword_mix(first, second=2, *, third=3):
    """
    >>> keyword_mix(1)
    (1, 2, 3)
    >>> keyword_mix(1, third=5)
    (1, 2, 5)
    >>> keyword_mix(first=1, second=4, third=6)
    (1, 4, 6)
    """
    return first, second, third
