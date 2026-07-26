import math
from operator import add as imported_add_function


MODULE_VALUE = {"answer": 42}
OVERWRITTEN_VALUE = ["old"]
OVERWRITTEN_VALUE = {"value": "new"}
MUTABLE_GLOBAL = 10
MISSING_GLOBAL = 1
abs = 99


def read_module_value():
    return MODULE_VALUE


def read_overwritten_value():
    return OVERWRITTEN_VALUE


def read_mutable_global():
    return MUTABLE_GLOBAL


def set_mutable_global(value, /):
    global MUTABLE_GLOBAL
    MUTABLE_GLOBAL = value
    return MUTABLE_GLOBAL


def increment_mutable_global(value, /):
    global MUTABLE_GLOBAL
    MUTABLE_GLOBAL += value
    return MUTABLE_GLOBAL


def delete_mutable_global():
    global MUTABLE_GLOBAL
    del MUTABLE_GLOBAL
    return None


def delete_local_value():
    value = 11
    del value
    return 0


def delete_local_and_rebind():
    value = 11
    del value
    value = 22
    return value


def delete_argument(value, /):
    del value
    return 0


def delete_locals_multi():
    left = 1
    right = 2
    del left, right
    return 0


def conditional_delete_local(flag, /):
    value = 5
    if flag:
        del value
    return value


def loop_delete_local(do_delete, /):
    value = 7
    for item in [0]:
        if do_delete:
            del value
    return value


def function_locals(left, /):
    right = 2
    skipped = 3
    del skipped
    return locals()


def function_vars_alias(left, /):
    right = 2
    return vars()


def function_dir_names(left, /):
    right = 1
    return sorted(dir())


def module_globals_probe(name, /):
    return name in globals()


def publish_through_globals(value, /):
    module_globals = globals()
    module_globals["GLOBALS_PUBLISHED"] = value
    return module_globals["GLOBALS_PUBLISHED"]


def list_from_genexp():
    return list(item for item in [1, 2, 3])


def any_from_genexp(values, /):
    return any(item for item in values)


def all_from_genexp(values, /):
    return all(item for item in values)


def imag_literal_a():
    return 2j


def imag_literal_b():
    return 2j


def try_with_conditional(flag, /):
    try:
        if flag:
            raise ValueError("boom")
        return 1
    except ValueError:
        return 9


def except_returns_local_expr():
    fallback = 4
    try:
        raise ValueError("boom")
        return 0
    except ValueError:
        return fallback + 1


def read_missing_global():
    return MISSING_GLOBAL


def read_shadowed_builtin():
    return abs


def delete_shadowed_builtin():
    global abs
    del abs
    return None


def default_values(required, value=2, *, option=(3, None)):
    return [required, value, option]


def default_positional_only(value=5, /):
    return value


def mutable_default(bucket=[]):
    return bucket


EFFECTFUL_MARKER = 11


def effectful_defaults(item=len([1, 2, 3]), tagged=EFFECTFUL_MARKER):
    return [item, tagged]


def imported_sqrt(value, /):
    return math.sqrt(value)


def imported_add(left, right, /):
    return imported_add_function(left, right)


def builtin_length(value, /):
    return len(value)


def answer():
    return 42


def call_answer():
    return answer()


def return_none():
    return None


def return_true():
    return True


def return_false():
    return False


def return_float():
    return 1.25


def return_big_integer():
    return 1234567890123456789012345678901234567890


def return_infinity():
    return 1e10000


def return_imaginary():
    return 2.5j


def return_complex():
    return 1 + 2.5j


def return_text():
    return "Türkçe 🐍"


def return_nul_text():
    return "before\x00after"


def return_surrogate_text():
    return "\ud800"


def return_bytes():
    return b"a\x00\xff"


def make_list():
    return [1, None, 2]


def make_tuple():
    return (3, None)


def empty_list():
    return []


def empty_tuple():
    return ()


def nested_sequences():
    return [[1, None, True], (2.5, [b"x", "metin"])]


def repeated_list(factor, /):
    return [1, None] * factor


def repeated_tuple():
    return (2, "x") * 3


def expanded_list(values, /):
    return [0, *values, 3]


def expanded_tuple(values, /):
    return (*values, "x")


def expanded_and_repeated(values, /):
    return [*values] * 2


def make_dict():
    return {"one": 1, 2: [None, {"nested": True}]}


def empty_dict():
    return {}


def identity(value, /):
    return value


def wrap_argument(value, /):
    return [value, {"copy": value}]


def get_item(value, /):
    return value["key"]


def get_attribute(value, /):
    return value.real


def invoke(callable, /):
    return callable()


def invoke_one(callable, /):
    return callable(5)


def invoke_two(callable, /):
    return callable(4, 5)


def invoke_keywords(callable, /):
    return callable(left=4, right=5)


def invoke_mixed(callable, /):
    return callable(1, right=5)


def invoke_expanded(callable, values, /):
    return callable(0, *values, 3)


def invoke_keyword_mapping(callable, values, /):
    return callable(**values)


def invoke_mixed_expanded(callable, positional, keywords, /):
    return callable(1, *positional, named=4, **keywords)


def invoke_method(value, /):
    return value.upper()


METHOD_EVAL_LOG = []


cdef class MethodEvalProbe:
    def join(self, left, right):
        return [left, right]


def _method_eval_tag(name, value):
    METHOD_EVAL_LOG.append(name)
    return value


def method_call_evaluation_order():
    """Receiver then positional args before HPy_CallMethod (no bound GetAttr)."""
    METHOD_EVAL_LOG[:] = []
    probe = MethodEvalProbe()
    result = _method_eval_tag("receiver", probe).join(
        _method_eval_tag("left", 1),
        _method_eval_tag("right", 2),
    )
    return [list(METHOD_EVAL_LOG), result]


def ellipsis_value():
    return ...


def format_greeting(name, /):
    return f"hello {name}!"


def format_repr(value, /):
    return f"{value!r}"


def format_padded(value, width, /):
    return f"{value:{width}}"


def walrus_threshold(values, limit, /):
    if (count := len(values)) > limit:
        return count
    return 0


def walrus_product(left, right, /):
    return (total := left + right) * total


def walrus_accumulate():
    total = 0
    for item in (1, 2, 3, 4):
        total = (total := total + item)
    return total


def unpack_pair(values, /):
    left, right = values
    return left, right


def unpack_starred(values, /):
    head, *rest = values
    return head, rest


def parallel_assign():
    left, right = 7, 9
    return left, right


def cascaded_assign(values, /):
    left = right = values
    return left, right


def unpack_nested(values, /):
    head, (left, right) = values
    return head, left, right


def for_unpack_sum():
    total = 0
    for left, right in [(1, 2), (3, 4)]:
        total = total + left + right
    return total


def list_comp_values():
    return [item * 2 for item in (1, 2, 3) if item]


def dict_comp_values():
    return {key: key + 1 for key in (1, 2)}


def nested_comp_values():
    return [left + right for left in (1, 2) for right in (10, 20)]


def dict_comp_unpack():
    return {key: value for key, value in ((1, 2), (3, 4))}


def ordinary(value):
    return value


def pair(first, second):
    return [first, second]


def mixed(first, /, second):
    return {"first": first, "second": second}


def required_keyword_only(value, *, option):
    return [value, option]


def linear_cleanup(value, /):
    result = [value]
    result
    result = {"value": result}
    pass
    return result


def choose_cleanup(condition, value, /):
    local = [value]
    if condition:
        selected = {"early": local}
        return selected
    return local


def choose_branch(first, second, value, /):
    local = [value]
    if first:
        return {"branch": "first", "value": local}
    elif second:
        return {"branch": "second", "value": local}
    else:
        return {"branch": "else", "value": local}


def set_item(mapping, /):
    mapping["new"] = 7
    return mapping


def delete_item(mapping, /):
    del mapping["old"]
    return mapping


def set_attribute(obj, /):
    obj.value = 8
    return obj


def delete_attribute(obj, /):
    del obj.old
    return obj


def raise_value_error(value):
    local = [value]
    raise ValueError("aHPy failure")


def raise_value_payload(value, /):
    local = [value]
    raise ValueError(local)


def raise_tuple_payload(value, /):
    raise KeyError((value, "tuple"))


def raise_nul_payload():
    raise RuntimeError("nul\0payload")


def raise_memory_error(value, /):
    local = [value]
    raise MemoryError


def raise_empty_value_error(value, /):
    local = [value]
    raise ValueError()


def raise_bare_value_error(value, /):
    local = [value]
    raise ValueError


def raise_multi_value_error(first, second, /):
    raise ValueError(first, second)


def raise_surrogate_payload():
    raise RuntimeError("\ud800")


def raise_failing_payload(value, fail, /):
    local = [value]
    raise ValueError(fail())


def raise_dynamic(exception, value, /):
    local = [value]
    raise exception


def raise_dynamic_call(factory, value, /):
    local = [value]
    raise factory(value)


def raise_dynamic_keyword(factory, value, /):
    local = [value]
    raise factory(payload=value)


def handle_value_or_type(callable, /):
    try:
        return callable()
    except ValueError:
        return 42
    except TypeError:
        return "type"


def handle_any(callable, /):
    try:
        return callable()
    except:
        return None


def handle_explicit_raise():
    try:
        raise ValueError("handled")
    except ValueError:
        return [1, 2]


def handle_missing_item(mapping, /):
    try:
        return mapping["missing"]
    except KeyError:
        return "missing"


handler_missing_global = 99


def handle_missing_global():
    try:
        return handler_missing_global
    except NameError:
        return "missing-global"


def handle_with_local(callable, value, /):
    local = [value]
    try:
        return callable()
    except ValueError:
        return 42


def handle_linear_try(callable, value, /):
    try:
        local = [value]
        callable()
        return local
    except ValueError:
        return ("handled",)


def handle_general_body(callable, value, /):
    try:
        return callable()
    except ValueError:
        local = [value]
        if value:
            local += [value]
        return local


def translate_value_error(callable, /):
    try:
        return callable()
    except ValueError:
        marker = ["translated"]
        raise TypeError(marker)


def add_values(left, right, /):
    return left + right


def subtract_values(left, right, /):
    return left - right


def multiply_values(left, right, /):
    return left * right


def matrix_multiply_values(left, right, /):
    return left @ right


def true_divide_values(left, right, /):
    return left / right


def floor_divide_values(left, right, /):
    return left // right


def remainder_values(left, right, /):
    return left % right


def left_shift_values(left, right, /):
    return left << right


def right_shift_values(left, right, /):
    return left >> right


def bitwise_and_values(left, right, /):
    return left & right


def bitwise_xor_values(left, right, /):
    return left ^ right


def bitwise_or_values(left, right, /):
    return left | right


def power_values(left, right, /):
    return left ** right


def positive_value(value, /):
    return +value


def negative_value(value, /):
    return -value


def invert_value(value, /):
    return ~value


def and_values(left, right, /):
    return left and right


def or_values(left, right, /):
    return left or right


def and_call(left, function, /):
    return left and function()


def or_call(left, function, /):
    return left or function()


def not_value(value, /):
    return not value


def chained_less(first, middle, last, /):
    return first < middle < last


def chained_identity(first, middle, last, /):
    return first is middle is last


def chained_identity_membership(first, middle, container, /):
    return first is middle in container


def chained_calls(first, middle, last, /):
    return first() < middle() < last()


def inplace_add(left, right, /):
    left += right
    return left


def inplace_floor_divide(left, right, /):
    left //= right
    return left


def inplace_power(left, right, /):
    left **= right
    return left


def inplace_bitwise_or(left, right, /):
    left |= right
    return left


def inplace_matrix(left, right, /):
    left @= right
    return left


def inplace_attribute(obj, right, /):
    obj.value += right
    return obj


def inplace_item(obj, key, right, /):
    obj[key] += right
    return obj


def inplace_dynamic_attribute(receiver, value, /):
    receiver().value += value()
    return None


def inplace_dynamic_item(obj, key, value, /):
    obj[key()] += value()
    return None


def merge_existing(flag, value, /):
    result = value
    if flag:
        result = [value]
    return result


def merge_new(which, value, /):
    if which == 1:
        result = [value]
    elif which == 2:
        result = (value,)
    else:
        result = {"value": value}
    return result


def merge_nested(first, second, value, /):
    result = value
    if first:
        if second:
            result = [value]
        else:
            result = (value,)
    else:
        result = {"value": value}
    return result


def conditional_value(condition, true_value, false_value, /):
    return true_value if condition else false_value


def conditional_call(condition, true_value, false_value, /):
    return true_value() if condition else false_value()


def while_consume(condition, value, /):
    result = []
    current = None
    while condition():
        current = value()
        if current == 0:
            continue
        if current < 0:
            break
        result += [current]
    else:
        result += ["done"]
    return result


def for_literal_consume(first, second, third, /):
    result = []
    for item in [first, second, third]:
        if item == 0:
            continue
        if item < 0:
            break
        result += [item]
    else:
        result += ["done"]
    return result


def for_dynamic_consume(values, /):
    result = []
    for item in values:
        if item == 0:
            continue
        if item < 0:
            break
        result += [item]
    else:
        result += ["done"]
    return result


def list_comp_dynamic(values, /):
    return [item * 2 for item in values if item]


def dict_comp_dynamic(values, /):
    return {key: key + 1 for key in values}


def empty_sequence_for(values, /):
    total = 0
    for item in values:
        total = total + item
    else:
        total = total + 100
    return total


def assert_truthy(value, /):
    assert value
    return value


def assert_with_message(value, /):
    assert value, "blocked"
    return value


def range_sum(n, /):
    total = 0
    for i in range(n):
        total = total + i
    return total


def range_literal_sum():
    total = 0
    for i in range(1, 5, 2):
        total = total + i
    return total


def range_break_else():
    total = 0
    for i in range(5):
        if i == 3:
            break
        total = total + i
    else:
        total = total + 100
    return total


def range_comp_squares():
    return [i * i for i in range(5)]


def for_from_sum(n, /):
    total = 0
    for i from 0 <= i < n:
        total = total + i
    return total


def return_from_while(condition, value, /):
    while condition():
        return value
    return None


def raise_from_while(condition, /):
    while condition():
        raise ValueError("loop")
    return None


def return_from_for(first, second, /):
    for item in [first, second]:
        if item:
            return item
    return None


def mixed_branch_return(flag, value, /):
    if flag:
        value = [value]
    else:
        return value
    return value


def mixed_branch_raise(flag, value, /):
    if flag:
        raise TypeError("blocked")
    value = (value,)
    return value


def get_slice(value, /):
    return value[1:4:2]


def set_slice(value, /):
    value[1:3] = [8, 9]
    return value


def delete_slice(value, /):
    del value[1:3]
    return value


def inplace_slice(value, /):
    value[1:2] += [7]
    return value


def inplace_dynamic_slice(obj, start, stop, value, /):
    obj[start():stop()] += value()
    return None


def equal_values(left, right, /):
    return left == right


def less_values(left, right, /):
    return left < right


def greater_equal_values(left, right, /):
    return left >= right


def same_values(left, right, /):
    return left is right


def different_values(left, right, /):
    return left is not right


def contains_value(key, container, /):
    return key in container


def excludes_value(key, container, /):
    return key not in container


def make_adder(x, /):
    def add(y, /):
        return x + y
    return add


def make_mutated_reader(x, /):
    def read():
        return x
    x = x + 10
    return read


def make_readers(first, second, /):
    def read_first():
        return first
    def read_second():
        return second
    return [read_first, read_second]


def make_constant_reader():
    def read():
        return 7
    return read


# Module-scope ``dir()`` → SortedDictKeysNode(globals().__dict__).
MODULE_DIR = dir()
