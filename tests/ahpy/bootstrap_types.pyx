ctypedef unsigned short LocalCode

TYPE_MODULE_VALUE = 47
TYPE_SLOT_TEXT = "module-slot"
TYPE_SLOT_EVENTS = []


cdef class Marker:
    pass


cdef class Box:
    cdef public object value
    cdef readonly object label
    cdef object hidden

    def owner(self):
        return self

    def identity(self, value, /):
        return value

    def combine(self, left, right):
        return [self, left, right]

    def read_hidden(self):
        return self.hidden

    def write_hidden(self, value, /):
        self.hidden = value
        return self

    def extend_hidden(self, value, /):
        self.hidden += value
        return self.hidden

    def read_value(self):
        return self.value


cdef class Initialized:
    cdef public object value

    def __init__(self, value):
        self.value = value


cdef class CInitConstructed:
    cdef public object stages

    def __cinit__(self, first, second):
        self.stages = [TYPE_MODULE_VALUE, first]

    def __init__(self, first, second):
        self.stages = self.stages + [second]


cdef class CInitBase:
    cdef object base_value

    def __cinit__(self, value):
        self.base_value = value


cdef class CInitDerived(CInitBase):
    cdef object derived_value

    def __cinit__(self, value):
        self.derived_value = [self.base_value, value]

    def values(self):
        return [self.base_value, self.derived_value]


cdef class FailingCInit:
    cdef object value

    def __cinit__(self, value):
        self.value = value
        raise RuntimeError("cinit failure")


cdef class FailingDerivedCInit(CInitBase):
    def __cinit__(self, value):
        raise RuntimeError("derived cinit failure")


cdef class NullaryCInitBase:
    cdef public object stage

    def __cinit__(self):
        self.stage = "base-cinit"


cdef class NullaryCInitDerived(NullaryCInitBase):
    def __init__(self, value):
        self.stage = [self.stage, value]


cdef class CInitCallable:
    cdef object value

    def __cinit__(self, value):
        self.value = value

    def __call__(self):
        return self.value


cdef class CInitDefault:
    cdef object value

    def __cinit__(self, value=[83]):
        self.value = value

    def read(self):
        return self.value


cdef class DerivedCInitDefault(CInitDefault):
    pass


cdef class NumericBox:
    cdef public int count
    cdef public double ratio
    cdef readonly int frozen
    cdef int hidden_count
    cdef double hidden_ratio

    def read_count(self):
        return self.count

    def write_count(self, value, /):
        self.count = value
        return self.count

    def read_hidden_count(self):
        return self.hidden_count

    def write_hidden_count(self, value, /):
        self.hidden_count = value
        return self.hidden_count

    def read_hidden_ratio(self):
        return self.hidden_ratio

    def write_hidden_ratio(self, value, /):
        self.hidden_ratio = value
        return self.hidden_ratio

    def adjust_count(self, add, subtract, multiply):
        self.hidden_count += add
        self.hidden_count -= subtract
        self.hidden_count *= multiply
        return self.hidden_count

    def adjust_ratio(self, add, subtract, multiply):
        self.hidden_ratio += add
        self.hidden_ratio -= subtract
        self.hidden_ratio *= multiply
        return self.hidden_ratio

    def mask_count(self, and_value, or_value, xor_value):
        self.hidden_count &= and_value
        self.hidden_count |= or_value
        self.hidden_count ^= xor_value
        return self.hidden_count

    def shift_count(self, initial, left, right):
        self.hidden_count = initial
        self.hidden_count <<= left
        self.hidden_count >>= right
        return self.hidden_count

    def floor_count(self, initial, value):
        self.hidden_count = initial
        self.hidden_count //= value
        return self.hidden_count

    def modulo_count(self, initial, value):
        self.hidden_count = initial
        self.hidden_count %= value
        return self.hidden_count

    def power_count(self, initial, value):
        self.hidden_count = initial
        self.hidden_count **= value
        return self.hidden_count

    def divide_count(self, initial, value):
        self.hidden_count = initial
        self.hidden_count /= value
        return self.hidden_count

    def divide_ratio(self, initial, value):
        self.hidden_ratio = initial
        self.hidden_ratio /= value
        return self.hidden_ratio


cdef class BintBox:
    cdef public bint enabled
    cdef readonly bint frozen
    cdef bint hidden

    def __init__(self, enabled):
        self.enabled = enabled

    def read_hidden(self):
        return self.hidden

    def write_hidden(self, value, /):
        self.hidden = value
        return self.hidden


cdef class SsizeBox:
    cdef public Py_ssize_t size
    cdef readonly Py_ssize_t frozen
    cdef Py_ssize_t hidden

    def __init__(self, size):
        self.size = size

    def read_hidden(self):
        return self.hidden

    def write_hidden(self, value, /):
        self.hidden = value
        return self.hidden


cdef class CharBox:
    cdef public char letter
    cdef readonly char frozen
    cdef char hidden

    def __init__(self, letter):
        self.letter = letter

    def read_letter(self):
        return self.letter

    def write_hidden(self, value, /):
        self.hidden = value
        return self.hidden


cdef class TypedefBox:
    cdef public LocalCode code
    cdef readonly LocalCode frozen
    cdef LocalCode hidden

    def __init__(self, code):
        self.code = code

    def read_code(self):
        return self.code

    def write_hidden(self, value, /):
        self.hidden = value
        return self.hidden


cdef class LongDoubleBox:
    cdef public long double value
    cdef readonly long double frozen
    cdef long double hidden

    def __init__(self, value):
        self.value = value

    def read_value(self):
        return self.value

    def write_hidden(self, value, /):
        self.hidden = value
        return self.hidden


cdef class CallableBox:
    cdef object prefix

    def __init__(self, prefix):
        self.prefix = prefix

    def __call__(self, left, /, right):
        return [self.prefix, left, right]


cdef class NoInitCallable:
    def __call__(self):
        return self


cdef class InheritedCallable(Initialized):
    def __call__(self):
        return self.value


cdef class DefaultCallable:
    cdef object value

    def __init__(self, value=17):
        self.value = value

    def __call__(self, other=23):
        return [self.value, other]

    def choose(self, item=[29]):
        return item

    def keyword_default(self, first=31, *, named=37):
        return [first, named]

    def module_value(self):
        return TYPE_MODULE_VALUE

    def builtin_length(self, value, /):
        return len(value)

    def cached_constant(self):
        return ("type-method", 61)


cdef class DerivedDefaultCallable(DefaultCallable):
    def read(self):
        return self.value


cdef class MutableDefaultCallable:
    cdef object value

    def __init__(self, value=[]):
        self.value = value

    def __call__(self, other={}):
        return [self.value, other]

    def method_defaults(self, items=[], mapping={}):
        return [items, mapping]


cdef class ModuleAwareSlots:
    cdef object value

    def __init__(self):
        self.value = TYPE_MODULE_VALUE

    def read(self):
        return self.value

    def __call__(self):
        return TYPE_MODULE_VALUE

    def __repr__(self):
        return TYPE_SLOT_TEXT

    def __len__(self):
        return len([1, 2, 3])

    def __getitem__(self, key):
        return [TYPE_MODULE_VALUE, key]

    def __setitem__(self, key, value):
        self.value = TYPE_MODULE_VALUE

    def __delitem__(self, key):
        self.value = TYPE_MODULE_VALUE

    def __hash__(self):
        return TYPE_MODULE_VALUE

    def __bool__(self):
        return TYPE_MODULE_VALUE

    def __contains__(self, value):
        return TYPE_MODULE_VALUE

    def __eq__(self, other):
        return TYPE_SLOT_TEXT

    def __del__(self):
        TYPE_SLOT_EVENTS.append(TYPE_MODULE_VALUE)


cdef class EarlyReturnSlots:
    cdef object flag

    def __init__(self, flag, /):
        self.flag = flag

    def __len__(self):
        if self.flag:
            return 3
        return 0

    def __bool__(self):
        if self.flag:
            return True
        return False

    def __hash__(self):
        if self.flag:
            return 11
        return 0


cdef class CompareBox:
    cdef object result

    def __init__(self, result):
        self.result = result

    def __lt__(self, other):
        return other

    def __le__(self, other):
        return self.result

    def __eq__(self, other):
        return self

    def __ne__(self, other):
        return other

    def __gt__(self, other):
        return self.result

    def __ge__(self, other):
        return self


cdef class PartialCompare:
    cdef object result

    def __init__(self, result):
        self.result = result

    def __eq__(self, other):
        return self.result


cdef class AddBox:
    cdef object label

    def __init__(self, label):
        self.label = label

    def __add__(self, other):
        return ["add", self.label, other]

    def __radd__(self, other):
        return ["radd", self.label, other]

    def __iadd__(self, other):
        return ["iadd", self.label, other]


cdef class ReflectedAddOnly:
    cdef object label

    def __init__(self, label):
        self.label = label

    def __radd__(self, other):
        return ["radd-only", self.label, other]


cdef class DecliningAdd:
    def __add__(self, other):
        return NotImplemented


cdef class RaisingAdd:
    def __add__(self, other):
        raise RuntimeError("add failure")


cdef class FallbackAdd:
    cdef object label

    def __init__(self, label):
        self.label = label

    def __add__(self, other):
        return NotImplemented

    def __radd__(self, other):
        return ["fallback-radd", self.label, other]


cdef class NumericFamilies:
    def __add__(self, other):
        return ["add", self, other]

    def __radd__(self, other):
        return ["radd", self, other]

    def __iadd__(self, other):
        return ["iadd", self, other]

    def __sub__(self, other):
        return ["sub", self, other]

    def __rsub__(self, other):
        return ["rsub", self, other]

    def __isub__(self, other):
        return ["isub", self, other]

    def __mul__(self, other):
        return ["mul", self, other]

    def __rmul__(self, other):
        return ["rmul", self, other]

    def __imul__(self, other):
        return ["imul", self, other]

    def __mod__(self, other):
        return ["mod", self, other]

    def __rmod__(self, other):
        return ["rmod", self, other]

    def __imod__(self, other):
        return ["imod", self, other]

    def __divmod__(self, other):
        return ["divmod", self, other]

    def __rdivmod__(self, other):
        return ["rdivmod", self, other]

    def __floordiv__(self, other):
        return ["floordiv", self, other]

    def __rfloordiv__(self, other):
        return ["rfloordiv", self, other]

    def __ifloordiv__(self, other):
        return ["ifloordiv", self, other]

    def __truediv__(self, other):
        return ["truediv", self, other]

    def __rtruediv__(self, other):
        return ["rtruediv", self, other]

    def __itruediv__(self, other):
        return ["itruediv", self, other]

    def __lshift__(self, other):
        return ["lshift", self, other]

    def __rlshift__(self, other):
        return ["rlshift", self, other]

    def __ilshift__(self, other):
        return ["ilshift", self, other]

    def __rshift__(self, other):
        return ["rshift", self, other]

    def __rrshift__(self, other):
        return ["rrshift", self, other]

    def __irshift__(self, other):
        return ["irshift", self, other]

    def __and__(self, other):
        return ["and", self, other]

    def __rand__(self, other):
        return ["rand", self, other]

    def __iand__(self, other):
        return ["iand", self, other]

    def __xor__(self, other):
        return ["xor", self, other]

    def __rxor__(self, other):
        return ["rxor", self, other]

    def __ixor__(self, other):
        return ["ixor", self, other]

    def __or__(self, other):
        return ["or", self, other]

    def __ror__(self, other):
        return ["ror", self, other]

    def __ior__(self, other):
        return ["ior", self, other]

    def __matmul__(self, other):
        return ["matmul", self, other]

    def __rmatmul__(self, other):
        return ["rmatmul", self, other]

    def __imatmul__(self, other):
        return ["imatmul", self, other]


cdef class NumericBase:
    cdef object label

    def __init__(self, label):
        self.label = label

    def __add__(self, other):
        return ["base-add", self.label, other]

    def __radd__(self, other):
        return ["base-radd", self.label, other]

    def __iadd__(self, other):
        return ["base-iadd", self.label, other]


cdef class NumericDerived(NumericBase):
    def __radd__(self, other):
        return ["derived-radd", self.label, other]

    def __iadd__(self, other):
        return ["derived-iadd", self.label, other]


cdef class PowerFamilies:
    def __pow__(self, other, modulus=None):
        return ["pow", self, other, modulus]

    def __rpow__(self, other, modulus=None):
        return ["rpow", self, other, modulus]

    def __ipow__(self, other, modulus=None):
        return ["ipow", self, other, modulus]


cdef class TwoArgPower:
    def __pow__(self, other):
        return ["two-arg-pow", self, other]


cdef class PowerBase:
    cdef object label

    def __init__(self, label):
        self.label = label

    def __pow__(self, other, modulus=None):
        return ["base-pow", self.label, other, modulus]

    def __rpow__(self, other, modulus=None):
        return ["base-rpow", self.label, other, modulus]


cdef class PowerDerived(PowerBase):
    def __rpow__(self, other, modulus=None):
        return ["derived-rpow", self.label, other, modulus]


cdef class DecliningPower:
    def __pow__(self, other, modulus=None):
        return NotImplemented


cdef class RaisingPower:
    def __pow__(self, other, modulus=None):
        raise RuntimeError("power failure")


cdef class FinalizerBox:
    cdef object sink

    def __init__(self, sink):
        self.sink = sink

    def __del__(self):
        self.sink.append(self)


cdef class ErrorFinalizer:
    def __del__(self):
        raise RuntimeError("finalize failure")


cdef class NativeInitialized:
    cdef public int count
    cdef public double ratio

    def __init__(self, count, ratio):
        self.count = count
        self.ratio = ratio


cdef class AllNative:
    cdef public signed char sbyte
    cdef public unsigned char ubyte
    cdef public short short_value
    cdef public unsigned short ushort_value
    cdef public unsigned int uint_value
    cdef public long long_value
    cdef public unsigned long ulong_value
    cdef public long long longlong_value
    cdef public unsigned long long ulonglong_value
    cdef public float float_value

    def __init__(self, sbyte, ubyte, short_value, ushort_value, uint_value,
                 long_value, ulong_value, longlong_value, ulonglong_value,
                 float_value):
        self.sbyte = sbyte
        self.ubyte = ubyte
        self.short_value = short_value
        self.ushort_value = ushort_value
        self.uint_value = uint_value
        self.long_value = long_value
        self.ulong_value = ulong_value
        self.longlong_value = longlong_value
        self.ulonglong_value = ulonglong_value
        self.float_value = float_value

    def values(self):
        return [self.sbyte, self.ubyte, self.short_value, self.ushort_value,
                self.uint_value, self.long_value, self.ulong_value,
                self.longlong_value, self.ulonglong_value, self.float_value]


cdef class Display:
    cdef object value

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return self.value

    def __str__(self):
        return self.value


cdef class FormatBox:
    cdef object values

    def __init__(self, values):
        self.values = values

    def __format__(self, spec, /):
        return self.values[spec]


cdef class DerivedFormatBox(FormatBox):
    pass


cdef class ProtocolMethods:
    cdef object bytes_value
    cdef object complex_value
    cdef object round_values

    def __init__(self, bytes_value, complex_value, round_values):
        self.bytes_value = bytes_value
        self.complex_value = complex_value
        self.round_values = round_values

    def __bytes__(self):
        return self.bytes_value

    def __complex__(self):
        return self.complex_value

    def __round__(self, ndigits=None):
        return self.round_values[ndigits]


cdef class DerivedProtocolMethods(ProtocolMethods):
    pass


cdef class ContextMethods:
    cdef object events
    cdef object suppress

    def __init__(self, events, suppress):
        self.events = events
        self.suppress = suppress

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events.append(exc_type)
        return self.suppress


cdef class DerivedContextMethods(ContextMethods):
    pass


cdef class Sized:
    cdef object value

    def __init__(self, value):
        self.value = value

    def __len__(self):
        return self.value


cdef class HashBox:
    cdef object value

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return self.value


cdef class BoolBox:
    cdef object value

    def __init__(self, value):
        self.value = value

    def __bool__(self):
        return self.value


cdef class UnaryBox:
    cdef object value

    def __init__(self, value):
        self.value = value

    def __neg__(self):
        return self.value

    def __pos__(self):
        return self.value

    def __abs__(self):
        return self.value

    def __invert__(self):
        return self.value


cdef class ConversionBox:
    cdef object integer_value
    cdef object float_value

    def __init__(self, integer_value, float_value):
        self.integer_value = integer_value
        self.float_value = float_value

    def __int__(self):
        return self.integer_value

    def __index__(self):
        return self.integer_value

    def __float__(self):
        return self.float_value


cdef class ContainsBox:
    cdef object result

    def __init__(self, result):
        self.result = result

    def __contains__(self, value):
        return self.result


cdef class IndexBox:
    cdef object value

    def __init__(self, value):
        self.value = value

    def __getitem__(self, key):
        return self.value[key]

    def __setitem__(self, key, value):
        self.value[key] = value

    def __delitem__(self, key):
        del self.value[key]


cdef class SequenceBox:
    cdef object value
    cdef Py_ssize_t length

    def __init__(self, value, length):
        self.value = value
        self.length = length

    def __len__(self):
        return self.length

    def __getitem__(self, key):
        return self.value[key]

    def __setitem__(self, key, value):
        self.value[key] = value

    def __delitem__(self, key):
        del self.value[key]
        self.length -= 1


cdef class DerivedSequenceBox(SequenceBox):
    def __getitem__(self, key):
        return self.value[key]


cdef class PropertyBox:
    cdef object value

    def __init__(self, value):
        self.value = value

    property managed:
        """managed property documentation"""

        def __get__(self):
            return self.value

        def __set__(self, value):
            self.value = value

        def __del__(self):
            self.value = None

    property readonly:
        def __get__(self):
            return self.value

    property writeonly:
        def __set__(self, value):
            self.value = value

    property item:
        def __get__(self):
            return self.value["key"]

        def __set__(self, value):
            self.value["key"] = value

        def __del__(self):
            del self.value["key"]


cdef class DerivedPropertyBox(PropertyBox):
    pass


cdef class InheritanceBase:
    cdef public object base_value

    def __init__(self, value):
        self.base_value = value

    def base_identity(self):
        return self.base_value


cdef class InheritanceDerived(InheritanceBase):
    cdef public object derived_value

    def set_derived(self, value, /):
        self.derived_value = value
        return self

    def values(self):
        return [self.base_value, self.derived_value]


cdef class GcCycleNode:
    cdef object peer
    cdef public object label

    def __init__(self, label):
        self.label = label
        self.peer = None

    def link(self, other):
        self.peer = other
        return self


cdef class GcFieldClearBox:
    cdef public object left
    cdef public object right

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def clear_fields(self):
        self.left = None
        self.right = None
        return ["cleared"]


cdef class ResurrectDel:
    cdef public object registry

    def __init__(self, registry):
        self.registry = registry

    def __del__(self):
        if self.registry is not None:
            self.registry.append(self)


cdef class NestedFinalizeSink:
    cdef public object events

    def __init__(self, events):
        self.events = events

    def __del__(self):
        self.events.append("nested")


cdef class NestedFinalizeBox:
    cdef public object sink

    def __init__(self, sink):
        self.sink = sink

    def __del__(self):
        if self.sink is not None:
            self.sink.events.append("outer")


def make_early_return_slots(flag, /):
    return EarlyReturnSlots(flag)


def make_marker():
    return Marker()


def marker_type():
    return Marker


def make_box():
    return Box()


def box_type():
    return Box


def initialized_type():
    return Initialized


def make_initialized(value, /):
    return Initialized(value)


def make_numeric_box():
    return NumericBox()


def make_native_initialized(count, ratio):
    return NativeInitialized(count, ratio)
