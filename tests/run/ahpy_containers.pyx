# mode: run
# tag: ahpy_candidate


def build_containers(first, second):
    """
    >>> result = build_containers("a", "b")
    >>> result[:3] == (['a', 'b'], ('a', 'b'), {'first': 'a', 'second': 'b'})
    True
    >>> result[3] == {'a', 'b'}
    True
    """
    items = [first, second]
    pair = (first, second)
    mapping = {"first": first, "second": second}
    unique = {first, second}
    return items, pair, mapping, unique


def mutate_containers(value):
    """
    >>> mutate_containers(5)
    ([5, 6], {'value': 6}, 5)
    """
    items = [value]
    items.append(value + 1)
    mapping = {"value": value}
    mapping["value"] = items[1]
    return items, mapping, items[0]
