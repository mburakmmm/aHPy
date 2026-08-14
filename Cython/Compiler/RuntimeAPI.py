"""Typed boundary between Cython code generation and Python runtime APIs.

This module intentionally contains no mutable backend selection state.  A
runtime API instance belongs to a compilation ``Context`` and is selected from
its ``CompilationOptions``.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, FrozenSet, Optional, Protocol

from .Errors import CompileError


CPYTHON_BACKEND = "cpython"
HPY_UNIVERSAL_BACKEND = "hpy-universal"
HPY_CPYTHON_BACKEND = "hpy-cpython"
HPY_HYBRID_BACKEND = "hpy-hybrid"

_HPY_BUILTIN_EXCEPTIONS = frozenset({
    "AssertionError", "AttributeError", "BufferError", "EOFError",
    "Exception", "ImportError", "IndexError", "KeyError", "LookupError",
    "MemoryError", "ModuleNotFoundError", "NameError", "NotImplementedError",
    "OSError", "OverflowError", "RecursionError", "ReferenceError",
    "RuntimeError", "StopIteration", "SyntaxError", "SystemError",
    "TypeError", "UnboundLocalError", "UnicodeDecodeError",
    "UnicodeEncodeError", "UnicodeError", "UnicodeTranslateError",
    "ValueError", "ZeroDivisionError",
})

ACCEPTED_RUNTIME_BACKENDS = (
    CPYTHON_BACKEND,
    HPY_UNIVERSAL_BACKEND,
    HPY_CPYTHON_BACKEND,
)
RESERVED_RUNTIME_BACKENDS = (HPY_HYBRID_BACKEND,)


class RuntimeOperationGroup(Enum):
    OBJECTS = "objects"
    CALLS = "calls"
    CONTAINERS = "containers"
    CONVERSIONS = "conversions"
    EXCEPTIONS = "exceptions"
    GLOBALS = "globals"
    MODULES = "modules"
    TYPES = "types"


class RuntimeCapability(Enum):
    OBJECT_LIFETIME = ("object-lifetime", RuntimeOperationGroup.OBJECTS)
    PYTHON_CALLS = ("python-calls", RuntimeOperationGroup.CALLS)
    CONTAINER_BUILDERS = ("container-builders", RuntimeOperationGroup.CONTAINERS)
    VALUE_CONVERSIONS = ("value-conversions", RuntimeOperationGroup.CONVERSIONS)
    EXCEPTION_STATE = ("exception-state", RuntimeOperationGroup.EXCEPTIONS)
    MODULE_GLOBALS = ("module-globals", RuntimeOperationGroup.GLOBALS)
    MODULE_DEFINITIONS = ("module-definitions", RuntimeOperationGroup.MODULES)
    TYPE_DEFINITIONS = ("type-definitions", RuntimeOperationGroup.TYPES)

    def __init__(self, capability_name, group):
        self.capability_name = capability_name
        self.group = group


class RuntimeCallKeywordLayout(Enum):
    NONE = "none"
    KEYWORD_NAMES = "keyword-names"
    KEYWORD_DICT = "keyword-dict"


class RuntimeSequenceKind(Enum):
    LIST = "list"
    TUPLE = "tuple"


class RuntimeConversionDirection(Enum):
    TO_PYTHON = "to-python"
    FROM_PYTHON = "from-python"


class RuntimeConversionKind(Enum):
    BOOLEAN = "boolean"
    SIGNED_INTEGER = "signed-integer"
    UNSIGNED_INTEGER = "unsigned-integer"
    FLOAT = "float"
    COMPLEX = "complex"
    UNICODE_CODEPOINT = "unicode-codepoint"
    C_STRING = "c-string"
    CUSTOM = "custom"


class RuntimeNameLookupKind(Enum):
    MODULE_GLOBAL = "module-global"
    BUILTIN = "builtin"
    CLASS_NAMESPACE = "class-namespace"


class RuntimeGlobalStorageKind(Enum):
    CPYTHON_OBJECT = "cpython-object"
    REGISTERED_HPY_GLOBAL = "registered-hpy-global"


class RuntimeModuleInitializationKind(Enum):
    CPYTHON_CONFIGURABLE = "cpython-configurable"
    HPY_MULTIPHASE = "hpy-multiphase"


class RuntimeMethodSignature(Enum):
    NOARGS = "noargs"
    ONEARG = "onearg"
    POSITIONAL_VARARGS = "positional-varargs"
    VARARGS_KEYWORDS = "varargs-keywords"
    FASTCALL_KEYWORDS = "fastcall-keywords"


class RuntimeTypeSpecificationKind(Enum):
    CPYTHON_SLOT_SPEC = "cpython-slot-spec"
    HPY_PURE_SPEC = "hpy-pure-spec"


class RuntimeContextKind(Enum):
    NONE = "none"
    CALL_SCOPED_HPY = "call-scoped-hpy"


class RuntimeContextConstant(Enum):
    NONE = "none"
    NOT_IMPLEMENTED = "not-implemented"
    TRUE = "true"
    FALSE = "false"
    ELLIPSIS = "ellipsis"
    TYPE_ERROR = "type-error"
    BASE_EXCEPTION = "base-exception"
    TYPE_TYPE = "type-type"
    UNICODE_TYPE = "unicode-type"
    SLICE_TYPE = "slice-type"
    LONG_TYPE = "long-type"
    COMPLEX_TYPE = "complex-type"
    LIST_TYPE = "list-type"
    TUPLE_TYPE = "tuple-type"


class RuntimeBinaryOperation(Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    MATRIX_MULTIPLY = "matrix-multiply"
    TRUE_DIVIDE = "true-divide"
    FLOOR_DIVIDE = "floor-divide"
    REMAINDER = "remainder"
    LEFT_SHIFT = "left-shift"
    RIGHT_SHIFT = "right-shift"
    BITWISE_AND = "bitwise-and"
    BITWISE_XOR = "bitwise-xor"
    BITWISE_OR = "bitwise-or"
    POWER = "power"


class RuntimeUnaryOperation(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    INVERT = "invert"


class RuntimeInPlaceOperation(Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    MATRIX_MULTIPLY = "matrix-multiply"
    TRUE_DIVIDE = "true-divide"
    FLOOR_DIVIDE = "floor-divide"
    REMAINDER = "remainder"
    POWER = "power"
    LEFT_SHIFT = "left-shift"
    RIGHT_SHIFT = "right-shift"
    BITWISE_AND = "bitwise-and"
    BITWISE_XOR = "bitwise-xor"
    BITWISE_OR = "bitwise-or"


class RuntimeComparisonOperation(Enum):
    LESS_THAN = "less-than"
    LESS_EQUAL = "less-equal"
    EQUAL = "equal"
    NOT_EQUAL = "not-equal"
    GREATER_THAN = "greater-than"
    GREATER_EQUAL = "greater-equal"


class RuntimeCodeGenerationKind(Enum):
    CPYTHON = "cpython"
    HPY_UNIVERSAL_BOOTSTRAP = "hpy-universal-bootstrap"


@dataclass(frozen=True)
class RuntimePrimitiveConversion:
    direction: RuntimeConversionDirection
    kind: RuntimeConversionKind
    c_type_cname: str
    function_cname: str
    type_: object


@dataclass(frozen=True)
class RuntimeContextContract:
    kind: RuntimeContextKind
    parameter_type_cname: str
    default_parameter_cname: str
    required_for_python_operations: bool
    may_be_persisted: bool

    def require_cname(self, context_cname):
        if self.required_for_python_operations and not context_cname:
            raise ValueError(
                "%s runtime operation requires a context cname" %
                self.kind.value)
        return context_cname


@dataclass(frozen=True)
class RuntimeNameLookup:
    kind: RuntimeNameLookupKind
    namespace_is_type: bool = False


@dataclass(frozen=True)
class RuntimeGlobalStorage:
    kind: RuntimeGlobalStorageKind
    storage_type_cname: str
    requires_module_registration: bool
    load_returns_owned_reference: bool
    store_consumes_reference: bool
    runtime_manages_stored_lifetime: bool


@dataclass(frozen=True)
class RuntimeGlobalLoadResult:
    cname: str
    owns_local_reference: bool
    context_cname: str = ""


@dataclass(frozen=True)
class RuntimeModuleDefinition:
    kind: RuntimeModuleInitializationKind
    definition_type_cname: str
    requires_multiphase_init: bool
    init_returns_definition: bool
    init_has_context: bool
    execution_uses_slot: bool
    execution_receives_context: bool
    supports_manual_creation: bool
    supports_legacy_methods: bool
    supports_registered_globals: bool


@dataclass(frozen=True)
class RuntimeMethodDefinition:
    signature: RuntimeMethodSignature
    definition_cname: str
    python_name_cname: str
    implementation_cname: str
    doc_cname: str
    coexists_with_slot: bool = False


@dataclass(frozen=True)
class RuntimeTypeDefinition:
    kind: RuntimeTypeSpecificationKind
    specification_type_cname: str
    uses_slot_array: bool
    uses_definition_array: bool
    requires_builtin_shape: bool
    supports_legacy_slots: bool
    pure_layout_omits_object_header: bool


@dataclass(frozen=True)
class RuntimeArrayCall:
    utility_code_name: str
    function_cname: str
    keyword_layout: RuntimeCallKeywordLayout
    includes_receiver: bool


@dataclass(frozen=True)
class RuntimeSequenceBuilder:
    """Runtime contract for constructing a fixed-size sequence.

    CPython builds directly into the result object whereas HPy uses an opaque,
    separately owned builder.  Keeping these facts in the contract prevents
    code generators from assuming that the builder is a Python object handle.
    """

    kind: RuntimeSequenceKind
    builder_type_cname: str
    result_type_cname: str
    uses_separate_builder: bool
    set_item_steals_reference: bool
    creation_reports_error: bool
    supports_from_array: bool


@dataclass(frozen=True)
class RuntimeSequenceFromArray:
    kind: RuntimeSequenceKind
    function_cname: str
    utility_code_name: str = ""
    utility_code_file: str = ""


@dataclass(frozen=True)
class RuntimeModuleEmitter:
    """Complete module-emission callback selected by one runtime service."""
    backend: str
    emit: Callable[[object, object, object], None]

    def __post_init__(self):
        if not isinstance(self.backend, str) or not self.backend:
            raise ValueError("runtime module emitter backend must be non-empty")
        if not callable(self.emit):
            raise TypeError("runtime module emitter must be callable")


class RuntimeAPI(Protocol):
    """Structural type implemented by runtime-specific code generators."""

    name: str
    capabilities: FrozenSet[RuntimeCapability]

    def uses_handle_ownership(self) -> bool:
        ...

    def code_generation_kind(self) -> RuntimeCodeGenerationKind:
        ...

    def module_emitter(self) -> Optional[RuntimeModuleEmitter]:
        ...

    def context_contract(self) -> RuntimeContextContract:
        ...

    def context_constant(
        self, constant: RuntimeContextConstant, context_cname: str = "",
    ) -> str:
        ...

    def builtin_exception(self, name: str, context_cname: str = "") -> str:
        ...

    def reference_type_cname(self) -> str:
        ...

    def execution_state_type_cname(self) -> str:
        ...

    def leave_python_execution(self, context_cname: str = "") -> str:
        ...

    def reenter_python_execution(
        self, state_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def signed_integer_from_cvalue(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def ssize_integer_from_cvalue(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def unsigned_integer_from_cvalue(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def floating_from_cvalue(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def signed_long_from_python(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def ssize_t_from_python(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def type_check(
        self, value_cname: str, type_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def object_type(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def type_is_subtype(
        self, subtype_cname: str, type_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def object_hash(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def signed_long_long_from_python(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def unsigned_long_from_python(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def unsigned_long_long_from_python(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def double_from_python(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def python_error_occurred(self, context_cname: str = "") -> str:
        ...

    def unicode_from_utf8(
        self, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def unicode_from_encoded_object(
        self, value_cname: str, encoding_cname: str, errors_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def bytes_from_data(
        self, value_cname: str, size_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def argument_tracker_type_cname(self) -> str:
        ...

    def parse_keyword_arguments(
        self,
        tracker_cname: str,
        args_cname: str,
        nargs_cname: str,
        kwnames_cname: str,
        format_cname: str,
        keywords_cname: str,
        output_cnames,
        context_cname: str = "",
    ) -> str:
        ...

    def parse_keyword_dictionary(
        self,
        tracker_cname: str,
        args_cname: str,
        nargs_cname: str,
        keyword_dictionary_cname: str,
        format_cname: str,
        keywords_cname: str,
        output_cnames,
        context_cname: str = "",
    ) -> str:
        ...

    def close_argument_tracker(
        self, tracker_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def length(self, value_cname: str, context_cname: str = "") -> str:
        ...

    def item_get_index(
        self, receiver_cname: str, index_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def unicode_as_utf8_and_size(
        self, value_cname: str, size_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def truth_test(self, value_cname: str, context_cname: str = "") -> str:
        ...

    def binary_operation(
        self, operation: RuntimeBinaryOperation, left_cname: str,
        right_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def unary_operation(
        self, operation: RuntimeUnaryOperation, operand_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def object_str(self, value_cname: str, context_cname: str = "") -> str:
        ...

    def object_repr(self, value_cname: str, context_cname: str = "") -> str:
        ...

    def object_ascii(self, value_cname: str, context_cname: str = "") -> str:
        ...

    def inplace_operation(
        self, operation: RuntimeInPlaceOperation, left_cname: str,
        right_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def rich_compare(
        self, operation: RuntimeComparisonOperation, left_cname: str,
        right_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def identity_test(
        self, left_cname: str, right_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def contains(
        self, container_cname: str, key_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def attribute_get_string(
        self, receiver_cname: str, name_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def attribute_has_string(
        self, receiver_cname: str, name_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def item_get(
        self, receiver_cname: str, key_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def item_set(
        self, receiver_cname: str, key_cname: str, value_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def item_delete(
        self, receiver_cname: str, key_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def attribute_set_string(
        self, receiver_cname: str, name_cname: str, value_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def attribute_delete_string(
        self, receiver_cname: str, name_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def supports(self, capability: RuntimeCapability) -> bool:
        ...

    def require_capability(
        self,
        capability: RuntimeCapability,
        position=None,
        reason=None,
        guidance=None,
    ) -> None:
        ...

    def ensure_compilation_ready(self, position=None) -> None:
        ...

    def null_check(self, cname: str) -> str:
        ...

    def error_occurred(self, use_utility_code: bool = False) -> str:
        ...

    def check_for_null_code(self, type_, cname: str) -> str:
        ...

    def incref_code(self, type_, cname: str, nanny: bool = True) -> str:
        ...

    def xincref_code(self, type_, cname: str, nanny: bool = True) -> str:
        ...

    def decref_code(self, type_, cname: str, nanny: bool = True, have_gil: bool = True) -> str:
        ...

    def xdecref_code(self, type_, cname: str, nanny: bool = True, have_gil: bool = True) -> str:
        ...

    def decref_clear_code(
        self, type_, cname: str, clear_before_decref: bool = False,
        nanny: bool = True, have_gil: bool = True,
    ) -> str:
        ...

    def xdecref_clear_code(
        self, type_, cname: str, clear_before_decref: bool = False,
        nanny: bool = True, have_gil: bool = True,
    ) -> str:
        ...

    def decref_set_code(self, type_, cname: str, rhs_cname: str) -> str:
        ...

    def xdecref_set_code(self, type_, cname: str, rhs_cname: str) -> str:
        ...

    def duplicate_reference(
        self, cname: str, null_safe: bool = False, context_cname: str = "",
    ) -> str:
        ...

    def close_reference(
        self, cname: str, null_safe: bool = False, context_cname: str = "",
    ) -> str:
        ...

    def clear_reference(self, cname: str) -> str:
        ...

    def empty_reference(self, cname: str) -> str:
        ...

    def null_reference_value(self) -> str:
        ...

    def call_tuple_dict(
        self,
        callable_cname: str,
        args_cname: str,
        kwargs_cname: str = "NULL",
        use_utility_code: bool = True,
        context_cname: str = "",
    ) -> str:
        ...

    def call_no_args(
        self, callable_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def call_one_arg(
        self, callable_cname: str, arg_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def call_positional_array(
        self, callable_cname: str, args_cname: str, nargs_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def call_array_with_keyword_names(
        self, callable_cname: str, args_cname: str, nargs_cname: str,
        kwnames_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def call_method_no_args(self, receiver_cname: str, name_cname: str) -> str:
        ...

    def call_method_array(
        self,
        name_cname: str,
        args_cname: str,
        nargs_cname: str,
        kwnames_cname: str = "",
        context_cname: str = "",
    ) -> str:
        """Call a method with args[0] as receiver (HPy_CallMethod layout)."""
        ...

    def select_array_call(
        self,
        includes_receiver: bool,
        keyword_layout: RuntimeCallKeywordLayout,
    ) -> RuntimeArrayCall:
        ...

    def call_array(
        self,
        call: RuntimeArrayCall,
        callable_cname: str,
        args_cname: str,
        nargs_cname: str,
        keyword_cname: str = "",
    ) -> str:
        ...

    def sequence_builder(self, kind: RuntimeSequenceKind) -> RuntimeSequenceBuilder:
        ...

    def sequence_builder_new(
        self,
        builder: RuntimeSequenceBuilder,
        size_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def sequence_builder_set(
        self,
        builder: RuntimeSequenceBuilder,
        builder_cname: str,
        index_cname: str,
        item_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def sequence_builder_build(
        self,
        builder: RuntimeSequenceBuilder,
        builder_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def sequence_builder_cancel(
        self,
        builder: RuntimeSequenceBuilder,
        builder_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def select_sequence_from_array(
        self,
        kind: RuntimeSequenceKind,
    ) -> RuntimeSequenceFromArray:
        ...

    def sequence_from_array(
        self,
        operation: RuntimeSequenceFromArray,
        items_cname: str,
        size_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def sequence_pack(
        self,
        kind: RuntimeSequenceKind,
        item_cnames,
        context_cname: str = "",
    ) -> str:
        ...

    def dict_new(self, presized_size_cname: str = "", context_cname: str = "") -> str:
        ...

    def dict_set_item(
        self,
        dict_cname: str,
        key_cname: str,
        value_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def dict_set_item_string(
        self,
        dict_cname: str,
        key_cname: str,
        value_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def dict_copy(self, dict_cname: str, context_cname: str = "") -> str:
        ...

    def to_python_conversion(
        self,
        conversion: RuntimePrimitiveConversion,
        source_code: str,
        result_code: str,
        result_type,
        to_py_function=None,
    ) -> str:
        ...

    def from_python_conversion(
        self,
        conversion: RuntimePrimitiveConversion,
        source_code: str,
        result_code: str,
        error_pos,
        code,
        from_py_function=None,
        error_condition=None,
        special_none_cvalue=None,
    ) -> str:
        ...

    def error_set_string(
        self, exception_cname: str, message_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def error_set_from_errno(
        self, exception_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def error_set_object(
        self, exception_cname: str, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def error_set_none(
        self, exception_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def error_format(
        self, exception_cname: str, format_cname: str, arg_cnames,
        context_cname: str = "",
    ) -> str:
        ...

    def error_clear(self, context_cname: str = "") -> str:
        ...

    def error_no_memory(self, context_cname: str = "") -> str:
        ...

    def current_exception_type(
        self, use_utility_code: bool = True, context_cname: str = "",
    ) -> str:
        ...

    def exception_matches(
        self,
        pattern_cname: str,
        exception_cname: str = "",
        second_pattern_cname: str = "",
        use_utility_code: bool = False,
        context_cname: str = "",
    ) -> str:
        ...

    def fetch_exception(
        self, type_ptr_cname: str, value_ptr_cname: str, traceback_ptr_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def restore_exception(
        self, type_cname: str, value_cname: str, traceback_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def raise_exception(
        self, type_cname: str, value_cname: str, traceback_cname: str, cause_cname: str,
    ) -> str:
        ...

    def reraise_exception(self) -> str:
        ...

    def get_exception(self, arg_cnames) -> str:
        ...

    def save_exception(self, arg_cnames) -> str:
        ...

    def reset_exception(self, arg_cnames) -> str:
        ...

    def swap_exception(self, arg_ptr_cnames) -> str:
        ...

    def name_lookup(
        self,
        lookup: RuntimeNameLookup,
        result_cname: str,
        name_cname: str,
        namespace_cname: str = "",
        context_cname: str = "",
    ) -> str:
        ...

    def global_storage(self) -> RuntimeGlobalStorage:
        ...

    def global_load(
        self, storage_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def global_store(
        self, storage_cname: str, value_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def field_load(
        self, owner_cname: str, field_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def field_store(
        self, owner_cname: str, field_cname: str, value_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def module_definition(self) -> RuntimeModuleDefinition:
        ...

    def import_module(
        self, name_cname: str, context_cname: str = "",
    ) -> str:
        ...

    def module_set_attr(
        self,
        module_cname: str,
        name_cname: str,
        value_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def module_set_attr_string(
        self,
        module_cname: str,
        name_cname: str,
        value_cname: str,
        context_cname: str = "",
    ) -> str:
        ...

    def module_create(self, definition_cname: str, context_cname: str = "") -> str:
        ...

    def module_get_dict(self, module_cname: str, context_cname: str = "") -> str:
        ...

    def import_add_module_ref(self, name_cname: str, context_cname: str = "") -> str:
        ...

    def import_get_module_dict(self, context_cname: str = "") -> str:
        ...

    def module_slot_definition(
        self,
        slot_name: str,
        implementation_cname: str,
        pointer_cast: str = "",
    ) -> str:
        ...

    def module_slot_terminator(self) -> str:
        ...

    def module_definition_forward_declaration(
        self, definition_cname: str, linkage: str,
    ) -> str:
        ...

    def module_slot_array_declaration(self, slots_cname: str) -> str:
        ...

    def module_definition_declaration(
        self, definition_cname: str, linkage: str,
    ) -> str:
        ...

    def module_init_definition_result(self, definition_cname: str) -> str:
        ...

    def select_method_signature(self, method_flags) -> RuntimeMethodSignature:
        ...

    def method_definition_prefix(self, definition_cname: str) -> str:
        ...

    def method_definition_declaration(
        self, definition: RuntimeMethodDefinition,
    ) -> str:
        ...

    def method_implementation_declaration(
        self,
        definition: RuntimeMethodDefinition,
        context_cname: str = "",
        receiver_cname: str = "self",
        argument_cname: str = "arg",
    ) -> str:
        ...

    def method_table_declaration(self, table_cname: str) -> str:
        ...

    def method_table_entry(
        self, definition: RuntimeMethodDefinition, terminator: str,
    ) -> str:
        ...

    def method_table_terminator(self) -> str:
        ...

    def method_table_end(self) -> str:
        ...

    def type_definition(self) -> RuntimeTypeDefinition:
        ...

    def type_slot_definition(
        self,
        slot_name: str,
        definition_cname: str,
        implementation_cname: str,
    ) -> str:
        ...

    def type_definition_array_declaration(self, type_cname: str) -> str:
        ...

    def type_slot_table_entry(
        self,
        slot_name: str,
        definition_cname: str,
        implementation_cname: str,
        pointer_cast: str = "(void *)",
    ) -> str:
        ...

    def type_definition_array_terminator(self) -> str:
        ...

    def type_specification_declaration(self, type_cname: str) -> str:
        ...

    def type_from_spec(
        self, spec_cname: str, params_cname: str = "NULL",
        context_cname: str = "",
    ) -> str:
        ...


class RuntimeBackendOptionError(ValueError):
    """Raised when a runtime backend name is unknown or only reserved."""


class RuntimeBackendUnavailableError(CompileError):
    def __init__(self, backend, reason, guidance, position=None):
        self.backend = backend
        self.reason = reason
        self.guidance = guidance
        message = (
            "Runtime backend %r is not available for code generation. "
            "Reason: %s Migration guidance: %s"
        ) % (backend, reason, guidance)
        super().__init__(position, message)


class RuntimeCapabilityError(CompileError):
    def __init__(self, backend, capability, reason, guidance, position=None):
        self.backend = backend
        self.capability = capability
        self.reason = reason
        self.guidance = guidance
        capability_name = (
            capability.capability_name
            if isinstance(capability, RuntimeCapability)
            else str(capability)
        )
        message = (
            "Runtime backend %r does not provide capability %r. "
            "Reason: %s Migration guidance: %s"
        ) % (backend, capability_name, reason, guidance)
        super().__init__(position, message)


@dataclass(frozen=True)
class _RuntimeAPIBase:
    name: str
    capabilities: FrozenSet[RuntimeCapability]
    unavailable_reason: str = ""
    unavailable_guidance: str = ""

    def uses_handle_ownership(self):
        return False

    def code_generation_kind(self):
        return RuntimeCodeGenerationKind.CPYTHON

    def module_emitter(self):
        return None

    def supports(self, capability):
        return capability in self.capabilities

    def require_capability(
        self,
        capability,
        position=None,
        reason=None,
        guidance=None,
    ):
        if self.supports(capability):
            return
        raise RuntimeCapabilityError(
            self.name,
            capability,
            reason or "the selected backend has no implementation for this operation",
            guidance or "select a backend that supports the operation or rewrite the source",
            position,
        )

    def ensure_compilation_ready(self, position=None):
        if not self.unavailable_reason:
            return
        raise RuntimeBackendUnavailableError(
            self.name,
            self.unavailable_reason,
            self.unavailable_guidance,
            position,
        )

    def select_method_signature(self, method_flags):
        layouts = {
            ("METH_NOARGS",): RuntimeMethodSignature.NOARGS,
            ("METH_O",): RuntimeMethodSignature.ONEARG,
            ("METH_VARARGS",): RuntimeMethodSignature.POSITIONAL_VARARGS,
            ("METH_VARARGS", "METH_KEYWORDS"):
                RuntimeMethodSignature.VARARGS_KEYWORDS,
            ("__Pyx_METH_FASTCALL", "METH_KEYWORDS"):
                RuntimeMethodSignature.FASTCALL_KEYWORDS,
        }
        try:
            return layouts[tuple(method_flags)]
        except KeyError:
            raise ValueError(
                "unsupported runtime method flag layout: %r" %
                (tuple(method_flags),)
            ) from None

    @staticmethod
    def _validate_method_definition(definition):
        if not isinstance(definition, RuntimeMethodDefinition):
            raise TypeError(
                "expected RuntimeMethodDefinition, got %r" % (definition,))


class CPythonRuntimeAPI(_RuntimeAPIBase):
    _context_contract = RuntimeContextContract(
        kind=RuntimeContextKind.NONE,
        parameter_type_cname="",
        default_parameter_cname="",
        required_for_python_operations=False,
        may_be_persisted=False,
    )
    _global_storage = RuntimeGlobalStorage(
        kind=RuntimeGlobalStorageKind.CPYTHON_OBJECT,
        storage_type_cname="PyObject *",
        requires_module_registration=False,
        load_returns_owned_reference=False,
        store_consumes_reference=True,
        runtime_manages_stored_lifetime=False,
    )
    _module_definition = RuntimeModuleDefinition(
        kind=RuntimeModuleInitializationKind.CPYTHON_CONFIGURABLE,
        definition_type_cname="struct PyModuleDef",
        requires_multiphase_init=False,
        init_returns_definition=False,
        init_has_context=False,
        execution_uses_slot=False,
        execution_receives_context=False,
        supports_manual_creation=True,
        supports_legacy_methods=True,
        supports_registered_globals=False,
    )
    _type_definition = RuntimeTypeDefinition(
        kind=RuntimeTypeSpecificationKind.CPYTHON_SLOT_SPEC,
        specification_type_cname="PyType_Spec",
        uses_slot_array=True,
        uses_definition_array=False,
        requires_builtin_shape=False,
        supports_legacy_slots=True,
        pure_layout_omits_object_header=False,
    )

    def __init__(self):
        super().__init__(CPYTHON_BACKEND, frozenset(RuntimeCapability))

    def context_contract(self):
        return self._context_contract

    def context_constant(self, constant, context_cname=""):
        constants = {
            RuntimeContextConstant.NONE: "Py_None",
            RuntimeContextConstant.NOT_IMPLEMENTED: "Py_NotImplemented",
            RuntimeContextConstant.TRUE: "Py_True",
            RuntimeContextConstant.FALSE: "Py_False",
            RuntimeContextConstant.ELLIPSIS: "Py_Ellipsis",
            RuntimeContextConstant.TYPE_ERROR: "PyExc_TypeError",
            RuntimeContextConstant.BASE_EXCEPTION: "PyExc_BaseException",
            RuntimeContextConstant.TYPE_TYPE: "(PyObject *)&PyType_Type",
            RuntimeContextConstant.UNICODE_TYPE: "(PyObject *)&PyUnicode_Type",
            RuntimeContextConstant.SLICE_TYPE: "(PyObject *)&PySlice_Type",
            RuntimeContextConstant.LONG_TYPE: "(PyObject *)&PyLong_Type",
            RuntimeContextConstant.COMPLEX_TYPE: "(PyObject *)&PyComplex_Type",
            RuntimeContextConstant.LIST_TYPE: "(PyObject *)&PyList_Type",
            RuntimeContextConstant.TUPLE_TYPE: "(PyObject *)&PyTuple_Type",
        }
        try:
            return constants[constant]
        except KeyError:
            raise TypeError(
                "expected RuntimeContextConstant, got %r" % (constant,)) from None

    def builtin_exception(self, name, context_cname=""):
        if name not in _HPY_BUILTIN_EXCEPTIONS:
            raise ValueError("unsupported builtin exception %r" % name)
        return "PyExc_%s" % name

    def reference_type_cname(self):
        return "PyObject *"

    def execution_state_type_cname(self):
        return "PyThreadState *"

    def leave_python_execution(self, context_cname=""):
        return "PyEval_SaveThread()"

    def reenter_python_execution(self, state_cname, context_cname=""):
        return "PyEval_RestoreThread(%s)" % state_cname

    def signed_integer_from_cvalue(self, value_cname, context_cname=""):
        return "PyLong_FromLongLong(%s)" % value_cname

    def ssize_integer_from_cvalue(self, value_cname, context_cname=""):
        return "PyLong_FromSsize_t(%s)" % value_cname

    def unsigned_integer_from_cvalue(self, value_cname, context_cname=""):
        return "PyLong_FromUnsignedLongLong(%s)" % value_cname

    def floating_from_cvalue(self, value_cname, context_cname=""):
        return "PyFloat_FromDouble(%s)" % value_cname

    def signed_long_from_python(self, value_cname, context_cname=""):
        return "PyLong_AsLong(%s)" % value_cname

    def ssize_t_from_python(self, value_cname, context_cname=""):
        return "PyLong_AsSsize_t(%s)" % value_cname

    def type_check(self, value_cname, type_cname, context_cname=""):
        return "PyObject_TypeCheck(%s, (PyTypeObject *)%s)" % (
            value_cname, type_cname)

    def object_type(self, value_cname, context_cname=""):
        return "PyObject_Type(%s)" % value_cname

    def type_is_subtype(self, subtype_cname, type_cname, context_cname=""):
        return "PyType_IsSubtype((PyTypeObject *)%s, (PyTypeObject *)%s)" % (
            subtype_cname, type_cname)

    def object_hash(self, value_cname, context_cname=""):
        return "PyObject_Hash(%s)" % value_cname

    def signed_long_long_from_python(self, value_cname, context_cname=""):
        return "PyLong_AsLongLong(%s)" % value_cname

    def unsigned_long_from_python(self, value_cname, context_cname=""):
        return "PyLong_AsUnsignedLong(%s)" % value_cname

    def unsigned_long_long_from_python(self, value_cname, context_cname=""):
        return "PyLong_AsUnsignedLongLong(%s)" % value_cname

    def double_from_python(self, value_cname, context_cname=""):
        return "PyFloat_AsDouble(%s)" % value_cname

    def python_error_occurred(self, context_cname=""):
        return "PyErr_Occurred()"

    def unicode_from_utf8(self, value_cname, context_cname=""):
        return "PyUnicode_FromString(%s)" % value_cname

    def unicode_from_encoded_object(
        self, value_cname, encoding_cname, errors_cname, context_cname="",
    ):
        return "PyUnicode_FromEncodedObject(%s, %s, %s)" % (
            value_cname, encoding_cname, errors_cname)

    def bytes_from_data(self, value_cname, size_cname, context_cname=""):
        return "PyBytes_FromStringAndSize(%s, %s)" % (
            value_cname, size_cname)

    def argument_tracker_type_cname(self):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.MODULE_DEFINITIONS,
            "CPython bootstrap code does not use HPy argument trackers",
            "select the HPy Universal backend for HPyFunc_KEYWORDS emission",
        )

    def parse_keyword_arguments(
        self, tracker_cname, args_cname, nargs_cname, kwnames_cname,
        format_cname, keywords_cname, output_cnames, context_cname="",
    ):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.MODULE_DEFINITIONS,
            "CPython bootstrap keyword parsing has a different calling convention",
            "use the existing CPython wrapper generator",
        )

    def parse_keyword_dictionary(
        self, tracker_cname, args_cname, nargs_cname,
        keyword_dictionary_cname, format_cname, keywords_cname,
        output_cnames, context_cname="",
    ):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.TYPE_DEFINITIONS,
            "CPython constructor parsing uses the existing wrapper generator",
            "use the HPy Universal backend for HPy_tp_init emission",
        )

    def close_argument_tracker(self, tracker_cname, context_cname=""):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.OBJECT_LIFETIME,
            "CPython has no HPyTracker resource",
            "use CPython reference cleanup",
        )

    def length(self, value_cname, context_cname=""):
        return "PyObject_Length(%s)" % value_cname

    def item_get_index(self, receiver_cname, index_cname, context_cname=""):
        return "PySequence_GetItem(%s, %s)" % (
            receiver_cname, index_cname)

    def unicode_as_utf8_and_size(
        self, value_cname, size_cname, context_cname="",
    ):
        return "PyUnicode_AsUTF8AndSize(%s, &%s)" % (
            value_cname, size_cname)

    def truth_test(self, value_cname, context_cname=""):
        return "PyObject_IsTrue(%s)" % value_cname

    def binary_operation(
        self, operation, left_cname, right_cname, context_cname="",
    ):
        if operation is RuntimeBinaryOperation.POWER:
            return "PyNumber_Power(%s, %s, Py_None)" % (
                left_cname, right_cname)
        functions = {
            RuntimeBinaryOperation.ADD: "PyNumber_Add",
            RuntimeBinaryOperation.SUBTRACT: "PyNumber_Subtract",
            RuntimeBinaryOperation.MULTIPLY: "PyNumber_Multiply",
            RuntimeBinaryOperation.MATRIX_MULTIPLY: "PyNumber_MatrixMultiply",
            RuntimeBinaryOperation.TRUE_DIVIDE: "PyNumber_TrueDivide",
            RuntimeBinaryOperation.FLOOR_DIVIDE: "PyNumber_FloorDivide",
            RuntimeBinaryOperation.REMAINDER: "PyNumber_Remainder",
            RuntimeBinaryOperation.LEFT_SHIFT: "PyNumber_Lshift",
            RuntimeBinaryOperation.RIGHT_SHIFT: "PyNumber_Rshift",
            RuntimeBinaryOperation.BITWISE_AND: "PyNumber_And",
            RuntimeBinaryOperation.BITWISE_XOR: "PyNumber_Xor",
            RuntimeBinaryOperation.BITWISE_OR: "PyNumber_Or",
        }
        try:
            function = functions[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeBinaryOperation, got %r" % operation) from None
        return "%s(%s, %s)" % (function, left_cname, right_cname)

    def unary_operation(self, operation, operand_cname, context_cname=""):
        functions = {
            RuntimeUnaryOperation.POSITIVE: "PyNumber_Positive",
            RuntimeUnaryOperation.NEGATIVE: "PyNumber_Negative",
            RuntimeUnaryOperation.INVERT: "PyNumber_Invert",
        }
        try:
            function = functions[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeUnaryOperation, got %r" % operation) from None
        return "%s(%s)" % (function, operand_cname)

    def object_str(self, value_cname, context_cname=""):
        return "PyObject_Str(%s)" % value_cname

    def object_repr(self, value_cname, context_cname=""):
        return "PyObject_Repr(%s)" % value_cname

    def object_ascii(self, value_cname, context_cname=""):
        return "PyObject_ASCII(%s)" % value_cname

    def inplace_operation(
        self, operation, left_cname, right_cname, context_cname="",
    ):
        if operation is RuntimeInPlaceOperation.POWER:
            return "PyNumber_InPlacePower(%s, %s, Py_None)" % (
                left_cname, right_cname)
        functions = {
            RuntimeInPlaceOperation.ADD: "PyNumber_InPlaceAdd",
            RuntimeInPlaceOperation.SUBTRACT: "PyNumber_InPlaceSubtract",
            RuntimeInPlaceOperation.MULTIPLY: "PyNumber_InPlaceMultiply",
            RuntimeInPlaceOperation.MATRIX_MULTIPLY: "PyNumber_InPlaceMatrixMultiply",
            RuntimeInPlaceOperation.TRUE_DIVIDE: "PyNumber_InPlaceTrueDivide",
            RuntimeInPlaceOperation.FLOOR_DIVIDE: "PyNumber_InPlaceFloorDivide",
            RuntimeInPlaceOperation.REMAINDER: "PyNumber_InPlaceRemainder",
            RuntimeInPlaceOperation.LEFT_SHIFT: "PyNumber_InPlaceLshift",
            RuntimeInPlaceOperation.RIGHT_SHIFT: "PyNumber_InPlaceRshift",
            RuntimeInPlaceOperation.BITWISE_AND: "PyNumber_InPlaceAnd",
            RuntimeInPlaceOperation.BITWISE_XOR: "PyNumber_InPlaceXor",
            RuntimeInPlaceOperation.BITWISE_OR: "PyNumber_InPlaceOr",
        }
        try:
            function = functions[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeInPlaceOperation, got %r" % operation) from None
        return "%s(%s, %s)" % (function, left_cname, right_cname)

    def rich_compare(
        self, operation, left_cname, right_cname, context_cname="",
    ):
        operators = {
            RuntimeComparisonOperation.LESS_THAN: "Py_LT",
            RuntimeComparisonOperation.LESS_EQUAL: "Py_LE",
            RuntimeComparisonOperation.EQUAL: "Py_EQ",
            RuntimeComparisonOperation.NOT_EQUAL: "Py_NE",
            RuntimeComparisonOperation.GREATER_THAN: "Py_GT",
            RuntimeComparisonOperation.GREATER_EQUAL: "Py_GE",
        }
        try:
            operator = operators[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeComparisonOperation, got %r" % operation) from None
        return "PyObject_RichCompare(%s, %s, %s)" % (
            left_cname, right_cname, operator)

    def identity_test(self, left_cname, right_cname, context_cname=""):
        return "(%s == %s)" % (left_cname, right_cname)

    def contains(self, container_cname, key_cname, context_cname=""):
        return "PySequence_Contains(%s, %s)" % (
            container_cname, key_cname)

    def attribute_get_string(
        self, receiver_cname, name_cname, context_cname="",
    ):
        return "PyObject_GetAttrString(%s, %s)" % (
            receiver_cname, name_cname)

    def attribute_has_string(
        self, receiver_cname, name_cname, context_cname="",
    ):
        return "PyObject_HasAttrString(%s, %s)" % (
            receiver_cname, name_cname)

    def item_get(self, receiver_cname, key_cname, context_cname=""):
        return "PyObject_GetItem(%s, %s)" % (receiver_cname, key_cname)

    def item_set(
        self, receiver_cname, key_cname, value_cname, context_cname="",
    ):
        return "PyObject_SetItem(%s, %s, %s)" % (
            receiver_cname, key_cname, value_cname)

    def item_delete(self, receiver_cname, key_cname, context_cname=""):
        return "PyObject_DelItem(%s, %s)" % (receiver_cname, key_cname)

    def attribute_set_string(
        self, receiver_cname, name_cname, value_cname, context_cname="",
    ):
        return "PyObject_SetAttrString(%s, %s, %s)" % (
            receiver_cname, name_cname, value_cname)

    def attribute_delete_string(
        self, receiver_cname, name_cname, context_cname="",
    ):
        return "PyObject_DelAttrString(%s, %s)" % (
            receiver_cname, name_cname)

    def null_check(self, cname):
        return "!%s" % cname

    def error_occurred(self, use_utility_code=False):
        return "__Pyx_PyErr_Occurred()" if use_utility_code else "PyErr_Occurred()"

    def check_for_null_code(self, type_, cname):
        return type_.check_for_null_code(cname)

    def incref_code(self, type_, cname, nanny=True):
        return type_.get_incref_code(cname, nanny=nanny)

    def xincref_code(self, type_, cname, nanny=True):
        return type_.get_xincref_code(cname, nanny=nanny)

    def decref_code(self, type_, cname, nanny=True, have_gil=True):
        return type_.get_decref_code(cname, nanny=nanny, have_gil=have_gil)

    def xdecref_code(self, type_, cname, nanny=True, have_gil=True):
        return type_.get_xdecref_code(cname, nanny=nanny, have_gil=have_gil)

    def decref_clear_code(
        self, type_, cname, clear_before_decref=False, nanny=True, have_gil=True,
    ):
        return type_.get_decref_clear_code(
            cname,
            clear_before_decref=clear_before_decref,
            nanny=nanny,
            have_gil=have_gil,
        )

    def xdecref_clear_code(
        self, type_, cname, clear_before_decref=False, nanny=True, have_gil=True,
    ):
        return type_.get_xdecref_clear_code(
            cname,
            clear_before_decref=clear_before_decref,
            nanny=nanny,
            have_gil=have_gil,
        )

    def decref_set_code(self, type_, cname, rhs_cname):
        return type_.get_decref_set_code(cname, rhs_cname)

    def xdecref_set_code(self, type_, cname, rhs_cname):
        return type_.get_xdecref_set_code(cname, rhs_cname)

    def duplicate_reference(self, cname, null_safe=False, context_cname=""):
        operation = "Py_XINCREF" if null_safe else "Py_INCREF"
        return "%s(%s);" % (operation, cname)

    def close_reference(self, cname, null_safe=False, context_cname=""):
        operation = "Py_XDECREF" if null_safe else "Py_DECREF"
        return "%s(%s);" % (operation, cname)

    def clear_reference(self, cname):
        return "Py_CLEAR(%s);" % cname

    def empty_reference(self, cname):
        return "%s = 0;" % cname

    def null_reference_value(self):
        return "NULL"

    def call_tuple_dict(
        self,
        callable_cname,
        args_cname,
        kwargs_cname="NULL",
        use_utility_code=True,
        context_cname="",
    ):
        function = "__Pyx_PyObject_Call" if use_utility_code else "PyObject_Call"
        return "%s(%s, %s, %s)" % (
            function, callable_cname, args_cname, kwargs_cname)

    def call_no_args(self, callable_cname, context_cname=""):
        return "__Pyx_PyObject_CallNoArg(%s)" % callable_cname

    def call_one_arg(self, callable_cname, arg_cname, context_cname=""):
        return "__Pyx_PyObject_CallOneArg(%s, %s)" % (callable_cname, arg_cname)

    def call_positional_array(
        self, callable_cname, args_cname, nargs_cname, context_cname="",
    ):
        return "__Pyx_PyObject_FastCall(%s, %s, %s)" % (
            callable_cname, args_cname, nargs_cname)

    def call_array_with_keyword_names(
        self, callable_cname, args_cname, nargs_cname, kwnames_cname,
        context_cname="",
    ):
        return "__Pyx_Object_VectorcallKwds(%s, %s, %s, %s)" % (
            callable_cname, args_cname, nargs_cname, kwnames_cname)

    def call_method_no_args(self, receiver_cname, name_cname):
        return "__Pyx_PyObject_CallMethod0(%s, %s)" % (receiver_cname, name_cname)

    def call_method_array(
        self,
        name_cname,
        args_cname,
        nargs_cname,
        kwnames_cname="",
        context_cname="",
    ):
        raise RuntimeCapabilityError(
            self.name,
            "call_method_array",
            "CPython uses dedicated method call helpers rather than "
            "HPy_CallMethod argument-array layout",
            "keep method-call optimization on the CPython vectorcall helpers",
        )

    def select_array_call(self, includes_receiver, keyword_layout):
        implementations = {
            (True, RuntimeCallKeywordLayout.KEYWORD_NAMES): (
                "PyObjectVectorcallMethodKwds", "__Pyx_Object_VectorcallMethodKwds"),
            (True, RuntimeCallKeywordLayout.NONE): (
                "PyObjectFastCallMethod", "__Pyx_PyObject_FastCallMethod"),
            (False, RuntimeCallKeywordLayout.KEYWORD_NAMES): (
                "PyObjectVectorcallKwds", "__Pyx_Object_VectorcallKwds"),
            (False, RuntimeCallKeywordLayout.KEYWORD_DICT): (
                "PyObjectFastCall", "__Pyx_PyObject_FastCallDict"),
            (False, RuntimeCallKeywordLayout.NONE): (
                "PyObjectFastCall", "__Pyx_PyObject_FastCall"),
        }
        try:
            utility_code_name, function_cname = implementations[
                includes_receiver, keyword_layout]
        except KeyError:
            raise ValueError(
                "unsupported CPython array-call layout: receiver=%r, keywords=%s"
                % (includes_receiver, keyword_layout.value)
            ) from None
        return RuntimeArrayCall(
            utility_code_name,
            function_cname,
            keyword_layout,
            includes_receiver,
        )

    def call_array(
        self,
        call,
        callable_cname,
        args_cname,
        nargs_cname,
        keyword_cname="",
    ):
        expects_keywords = call.keyword_layout is not RuntimeCallKeywordLayout.NONE
        if bool(keyword_cname) != expects_keywords:
            raise ValueError(
                "array-call keyword operand does not match layout %s"
                % call.keyword_layout.value
            )
        operands = [callable_cname, args_cname, nargs_cname]
        if keyword_cname:
            operands.append(keyword_cname)
        return "%s(%s)" % (call.function_cname, ", ".join(operands))

    def sequence_builder(self, kind):
        if not isinstance(kind, RuntimeSequenceKind):
            raise TypeError("expected RuntimeSequenceKind, got %r" % (kind,))
        return RuntimeSequenceBuilder(
            kind=kind,
            builder_type_cname="PyObject *",
            result_type_cname="PyObject *",
            uses_separate_builder=False,
            set_item_steals_reference=True,
            creation_reports_error=True,
            supports_from_array=True,
        )

    def sequence_builder_new(self, builder, size_cname, context_cname=""):
        self._validate_sequence_builder(builder)
        function = "PyList_New" if builder.kind is RuntimeSequenceKind.LIST else "PyTuple_New"
        return "%s(%s)" % (function, size_cname)

    def sequence_builder_set(
        self, builder, builder_cname, index_cname, item_cname, context_cname="",
    ):
        self._validate_sequence_builder(builder)
        function = (
            "__Pyx_PyList_SET_ITEM"
            if builder.kind is RuntimeSequenceKind.LIST
            else "__Pyx_PyTuple_SET_ITEM"
        )
        return "%s(%s, %s, %s)" % (
            function, builder_cname, index_cname, item_cname)

    def sequence_builder_build(self, builder, builder_cname, context_cname=""):
        self._validate_sequence_builder(builder)
        return builder_cname

    def sequence_builder_cancel(self, builder, builder_cname, context_cname=""):
        self._validate_sequence_builder(builder)
        return self.close_reference(builder_cname)

    def select_sequence_from_array(self, kind):
        builder = self.sequence_builder(kind)
        assert builder.supports_from_array
        kind_name = "List" if kind is RuntimeSequenceKind.LIST else "Tuple"
        return RuntimeSequenceFromArray(
            kind=kind,
            function_cname="__Pyx_Py%s_FromArray" % kind_name,
            utility_code_name="%sFromArray" % kind_name,
            utility_code_file="ObjectHandling.c",
        )

    def sequence_from_array(
        self, operation, items_cname, size_cname, context_cname="",
    ):
        if operation != self.select_sequence_from_array(operation.kind):
            raise ValueError("array constructor belongs to a different runtime contract")
        return "%s(%s, %s)" % (
            operation.function_cname, items_cname, size_cname)

    def sequence_pack(self, kind, item_cnames, context_cname=""):
        if not isinstance(kind, RuntimeSequenceKind):
            raise TypeError("expected RuntimeSequenceKind, got %r" % (kind,))
        if kind is not RuntimeSequenceKind.TUPLE:
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.CONTAINER_BUILDERS,
                "CPython exposes PyTuple_Pack but no PyList_Pack operation",
                "construct the list through its fixed-size builder",
            )
        items = list(item_cnames)
        operands = [str(len(items))] + items
        return "PyTuple_Pack(%s)" % ", ".join(operands)

    def dict_new(self, presized_size_cname="", context_cname=""):
        if presized_size_cname:
            return "__Pyx_PyDict_NewPresized(%s)" % presized_size_cname
        return "PyDict_New()"

    def dict_set_item(self, dict_cname, key_cname, value_cname, context_cname=""):
        return "PyDict_SetItem(%s, %s, %s)" % (
            dict_cname, key_cname, value_cname)

    def dict_set_item_string(
        self, dict_cname, key_cname, value_cname, context_cname="",
    ):
        return "PyDict_SetItemString(%s, %s, %s)" % (
            dict_cname, key_cname, value_cname)

    def dict_copy(self, dict_cname, context_cname=""):
        return "PyDict_Copy(%s)" % dict_cname

    def to_python_conversion(
        self, conversion, source_code, result_code, result_type, to_py_function=None,
    ):
        if conversion.direction is not RuntimeConversionDirection.TO_PYTHON:
            raise ValueError("expected a to-Python conversion")
        return conversion.type_._cpython_to_py_call_code(
            source_code, result_code, result_type, to_py_function)

    def from_python_conversion(
        self,
        conversion,
        source_code,
        result_code,
        error_pos,
        code,
        from_py_function=None,
        error_condition=None,
        special_none_cvalue=None,
    ):
        if conversion.direction is not RuntimeConversionDirection.FROM_PYTHON:
            raise ValueError("expected a from-Python conversion")
        return conversion.type_._cpython_from_py_call_code(
            source_code,
            result_code,
            error_pos,
            code,
            from_py_function,
            error_condition,
            special_none_cvalue,
        )

    def error_set_string(self, exception_cname, message_cname, context_cname=""):
        return "PyErr_SetString(%s, %s)" % (exception_cname, message_cname)

    def error_set_from_errno(self, exception_cname, context_cname=""):
        return "PyErr_SetFromErrno(%s)" % exception_cname

    def error_set_object(self, exception_cname, value_cname, context_cname=""):
        return "PyErr_SetObject(%s, %s)" % (exception_cname, value_cname)

    def error_set_none(self, exception_cname, context_cname=""):
        return "PyErr_SetNone(%s)" % exception_cname

    def error_format(
        self, exception_cname, format_cname, arg_cnames, context_cname="",
    ):
        operands = [exception_cname, format_cname] + list(arg_cnames)
        return "PyErr_Format(%s)" % ", ".join(operands)

    def error_clear(self, context_cname=""):
        return "PyErr_Clear()"

    def error_no_memory(self, context_cname=""):
        return "PyErr_NoMemory()"

    def current_exception_type(self, use_utility_code=True, context_cname=""):
        if not use_utility_code:
            raise ValueError("current exception type requires utility code")
        return "__Pyx_PyErr_CurrentExceptionType()"

    def exception_matches(
        self,
        pattern_cname,
        exception_cname="",
        second_pattern_cname="",
        use_utility_code=False,
        context_cname="",
    ):
        if exception_cname:
            function = "__Pyx_PyErr_GivenExceptionMatches"
            operands = [exception_cname, pattern_cname]
        else:
            function = "__Pyx_PyErr_ExceptionMatches" if use_utility_code else "PyErr_ExceptionMatches"
            operands = [pattern_cname]
        if second_pattern_cname:
            if not use_utility_code:
                raise ValueError("two-pattern exception matching requires utility code")
            function += "2"
            operands.append(second_pattern_cname)
        return "%s(%s)" % (function, ", ".join(operands))

    def fetch_exception(
        self, type_ptr_cname, value_ptr_cname, traceback_ptr_cname, context_cname="",
    ):
        return "__Pyx_PyErr_FetchException(%s, %s, %s)" % (
            type_ptr_cname, value_ptr_cname, traceback_ptr_cname)

    def restore_exception(
        self, type_cname, value_cname, traceback_cname, context_cname="",
    ):
        return "__Pyx_PyErr_RestoreException(%s, %s, %s)" % (
            type_cname, value_cname, traceback_cname)

    def raise_exception(self, type_cname, value_cname, traceback_cname, cause_cname):
        return "__Pyx_Raise(%s, %s, %s, %s)" % (
            type_cname, value_cname, traceback_cname, cause_cname)

    def reraise_exception(self):
        return "__Pyx_ReraiseException()"

    def get_exception(self, arg_cnames):
        return "__Pyx_GetException(%s)" % ", ".join(arg_cnames)

    def save_exception(self, arg_cnames):
        return "__Pyx_ExceptionSave(%s)" % ", ".join(arg_cnames)

    def reset_exception(self, arg_cnames):
        return "__Pyx_ExceptionReset(%s)" % ", ".join(arg_cnames)

    def swap_exception(self, arg_ptr_cnames):
        return "__Pyx_ExceptionSwap(%s)" % ", ".join(arg_ptr_cnames)

    def name_lookup(
        self, lookup, result_cname, name_cname, namespace_cname="", context_cname="",
    ):
        if not isinstance(lookup, RuntimeNameLookup):
            raise TypeError("expected RuntimeNameLookup, got %r" % (lookup,))
        if lookup.kind is RuntimeNameLookupKind.MODULE_GLOBAL:
            if namespace_cname or lookup.namespace_is_type:
                raise ValueError("module-global lookup does not accept a namespace")
            return "__Pyx_GetModuleGlobalName(%s, %s)" % (result_cname, name_cname)
        if lookup.kind is RuntimeNameLookupKind.BUILTIN:
            if namespace_cname or lookup.namespace_is_type:
                raise ValueError("builtin lookup does not accept a namespace")
            return "%s = __Pyx_GetBuiltinName(%s)" % (result_cname, name_cname)
        if lookup.kind is RuntimeNameLookupKind.CLASS_NAMESPACE:
            if not namespace_cname:
                raise ValueError("class-namespace lookup requires a namespace")
            namespace = (
                "(PyObject*)%s" % namespace_cname
                if lookup.namespace_is_type else namespace_cname
            )
            return "__Pyx_GetNameInClass(%s, %s, %s)" % (
                result_cname, namespace, name_cname)
        raise ValueError("unsupported runtime name lookup kind: %r" % (lookup.kind,))

    def global_storage(self):
        return self._global_storage

    def global_load(self, storage_cname, context_cname=""):
        return storage_cname

    def global_store(self, storage_cname, value_cname, context_cname=""):
        return "%s = %s" % (storage_cname, value_cname)

    def field_load(self, owner_cname, field_cname, context_cname=""):
        return "Py_XNewRef(%s)" % field_cname

    def field_store(
        self, owner_cname, field_cname, value_cname, context_cname="",
    ):
        return "Py_XSETREF(%s, Py_XNewRef(%s))" % (
            field_cname, value_cname)

    def module_definition(self):
        return self._module_definition

    def import_module(self, name_cname, context_cname=""):
        return "PyImport_ImportModule(%s)" % name_cname

    def module_set_attr(
        self, module_cname, name_cname, value_cname, context_cname="",
    ):
        return "PyObject_SetAttr(%s, %s, %s)" % (
            module_cname, name_cname, value_cname)

    def module_set_attr_string(
        self, module_cname, name_cname, value_cname, context_cname="",
    ):
        return "PyObject_SetAttrString(%s, %s, %s)" % (
            module_cname, name_cname, value_cname)

    def module_create(self, definition_cname, context_cname=""):
        return "PyModule_Create(&%s)" % definition_cname

    def module_get_dict(self, module_cname, context_cname=""):
        return "PyModule_GetDict(%s)" % module_cname

    def import_add_module_ref(self, name_cname, context_cname=""):
        return "__Pyx_PyImport_AddModuleRef(%s)" % name_cname

    def import_get_module_dict(self, context_cname=""):
        return "PyImport_GetModuleDict()"

    def module_slot_definition(
        self, slot_name, implementation_cname, pointer_cast="",
    ):
        if not slot_name or not implementation_cname:
            raise ValueError("module slot name and implementation are required")
        return "{Py_%s, %s%s}," % (
            slot_name, pointer_cast, implementation_cname)

    def module_slot_terminator(self):
        return "{0, NULL}"

    def module_definition_forward_declaration(self, definition_cname, linkage):
        if linkage not in ("extern", "static"):
            raise ValueError("module definition linkage must be extern or static")
        return "%s %s %s;" % (
            linkage, self._module_definition.definition_type_cname,
            definition_cname)

    def module_slot_array_declaration(self, slots_cname):
        return "static PyModuleDef_Slot %s[] = {" % slots_cname

    def module_definition_declaration(self, definition_cname, linkage):
        if linkage not in ("", "static"):
            raise ValueError("module definition linkage must be empty or static")
        prefix = "%s " % linkage if linkage else ""
        return "%s%s %s =" % (
            prefix, self._module_definition.definition_type_cname,
            definition_cname)

    def module_init_definition_result(self, definition_cname):
        return "PyModuleDef_Init(&%s)" % definition_cname

    def method_definition_prefix(self, definition_cname):
        return "static PyMethodDef %s = " % definition_cname

    def method_definition_declaration(self, definition):
        self._validate_method_definition(definition)
        return ""

    def method_implementation_declaration(
        self, definition, context_cname="", receiver_cname="self",
        argument_cname="arg",
    ):
        self._validate_method_definition(definition)
        if definition.signature is RuntimeMethodSignature.NOARGS:
            return "static PyObject *%s(PyObject *%s, PyObject *unused)" % (
                definition.implementation_cname, receiver_cname)
        if definition.signature is RuntimeMethodSignature.ONEARG:
            return "static PyObject *%s(PyObject *%s, PyObject *%s)" % (
                definition.implementation_cname,
                receiver_cname,
                argument_cname,
            )
        if definition.signature is RuntimeMethodSignature.POSITIONAL_VARARGS:
            return "static PyObject *%s(PyObject *%s, PyObject *args)" % (
                definition.implementation_cname,
                receiver_cname,
            )
        raise ValueError(
            "bootstrap method declaration requires a supported signature")

    def method_table_declaration(self, table_cname):
        return "static PyMethodDef %s[] = {" % table_cname

    def method_table_entry(self, definition, terminator):
        self._validate_method_definition(definition)
        flags = {
            RuntimeMethodSignature.NOARGS: ["METH_NOARGS"],
            RuntimeMethodSignature.ONEARG: ["METH_O"],
            RuntimeMethodSignature.POSITIONAL_VARARGS: ["METH_VARARGS"],
            RuntimeMethodSignature.VARARGS_KEYWORDS:
                ["METH_VARARGS", "METH_KEYWORDS"],
            RuntimeMethodSignature.FASTCALL_KEYWORDS:
                ["__Pyx_METH_FASTCALL", "METH_KEYWORDS"],
        }[definition.signature]
        if definition.coexists_with_slot:
            flags.append("METH_COEXIST")
        cast = {
            RuntimeMethodSignature.NOARGS: "PyCFunction",
            RuntimeMethodSignature.ONEARG: "PyCFunction",
            RuntimeMethodSignature.POSITIONAL_VARARGS: "PyCFunction",
            RuntimeMethodSignature.VARARGS_KEYWORDS:
                "PyCFunctionWithKeywords",
            RuntimeMethodSignature.FASTCALL_KEYWORDS:
                "__Pyx_PyCFunction_FastCallWithKeywords",
        }[definition.signature]
        function = definition.implementation_cname
        if cast != "PyCFunction":
            function = "(void(*)(void))(%s)%s" % (cast, function)
        return "{%s, (PyCFunction)%s, %s, %s}%s" % (
            definition.python_name_cname,
            function,
            "|".join(flags),
            definition.doc_cname,
            terminator,
        )

    def method_table_terminator(self):
        return "{0, 0, 0, 0}"

    def method_table_end(self):
        return "};"

    def type_definition(self):
        return self._type_definition

    def type_slot_definition(
        self, slot_name, definition_cname, implementation_cname,
    ):
        if not slot_name or not definition_cname or not implementation_cname:
            raise ValueError("type slot names and implementation are required")
        return ""

    def type_definition_array_declaration(self, type_cname):
        return "static PyType_Slot %s_slots[] = {" % type_cname

    def type_slot_table_entry(
        self, slot_name, definition_cname, implementation_cname,
        pointer_cast="(void *)",
    ):
        if not slot_name or not definition_cname or not implementation_cname:
            raise ValueError("type slot names and implementation are required")
        return "{Py_%s, %s%s}," % (
            slot_name, pointer_cast, implementation_cname)

    def type_definition_array_terminator(self):
        return "{0, 0},"

    def type_specification_declaration(self, type_cname):
        return "static PyType_Spec %s_spec = {" % type_cname

    def type_from_spec(
        self, spec_cname, params_cname="NULL", context_cname="",
    ):
        if params_cname != "NULL":
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.TYPE_DEFINITIONS,
                "PyType_FromSpec does not accept HPy-style spec parameters",
                "use PyType_FromSpecWithBases for CPython base parameters",
            )
        return "PyType_FromSpec(&%s)" % spec_cname

    def _validate_sequence_builder(self, builder):
        if not isinstance(builder, RuntimeSequenceBuilder):
            raise TypeError("expected RuntimeSequenceBuilder, got %r" % (builder,))
        if builder != self.sequence_builder(builder.kind):
            raise ValueError("sequence builder belongs to a different runtime contract")


class _HPyRuntimeAPIBase(_RuntimeAPIBase):
    _context_contract = RuntimeContextContract(
        kind=RuntimeContextKind.CALL_SCOPED_HPY,
        parameter_type_cname="HPyContext *",
        default_parameter_cname="ctx",
        required_for_python_operations=True,
        may_be_persisted=False,
    )
    _global_storage = RuntimeGlobalStorage(
        kind=RuntimeGlobalStorageKind.REGISTERED_HPY_GLOBAL,
        storage_type_cname="HPyGlobal",
        requires_module_registration=True,
        load_returns_owned_reference=True,
        store_consumes_reference=False,
        runtime_manages_stored_lifetime=True,
    )
    _module_definition = RuntimeModuleDefinition(
        kind=RuntimeModuleInitializationKind.HPY_MULTIPHASE,
        definition_type_cname="HPyModuleDef",
        requires_multiphase_init=True,
        init_returns_definition=True,
        init_has_context=False,
        execution_uses_slot=True,
        execution_receives_context=True,
        supports_manual_creation=False,
        supports_legacy_methods=False,
        supports_registered_globals=True,
    )
    _type_definition = RuntimeTypeDefinition(
        kind=RuntimeTypeSpecificationKind.HPY_PURE_SPEC,
        specification_type_cname="HPyType_Spec",
        uses_slot_array=False,
        uses_definition_array=True,
        requires_builtin_shape=True,
        supports_legacy_slots=False,
        pure_layout_omits_object_header=True,
    )
    _supported_type_slots = frozenset({
        "bf_getbuffer", "bf_releasebuffer",
        "mp_ass_subscript", "mp_length", "mp_subscript",
        "nb_absolute", "nb_add", "nb_and", "nb_bool", "nb_divmod",
        "nb_float", "nb_floor_divide", "nb_index", "nb_inplace_add",
        "nb_inplace_and", "nb_inplace_floor_divide", "nb_inplace_lshift",
        "nb_inplace_matrix_multiply", "nb_inplace_multiply", "nb_inplace_or",
        "nb_inplace_power", "nb_inplace_remainder", "nb_inplace_rshift",
        "nb_inplace_subtract", "nb_inplace_true_divide", "nb_inplace_xor",
        "nb_int", "nb_invert", "nb_lshift", "nb_matrix_multiply",
        "nb_multiply", "nb_negative", "nb_or", "nb_positive", "nb_power",
        "nb_remainder", "nb_rshift", "nb_subtract", "nb_true_divide",
        "nb_xor", "sq_ass_item", "sq_concat", "sq_contains",
        "sq_inplace_concat", "sq_inplace_repeat", "sq_item", "sq_length",
        "sq_repeat", "tp_call", "tp_hash", "tp_init", "tp_new",
        "tp_finalize", "tp_repr", "tp_richcompare", "tp_str", "tp_traverse",
    })

    def uses_handle_ownership(self):
        return True

    def context_contract(self):
        return self._context_contract

    def context_constant(self, constant, context_cname=""):
        context_cname = self._require_context(context_cname)
        constants = {
            RuntimeContextConstant.NONE: "h_None",
            RuntimeContextConstant.NOT_IMPLEMENTED: "h_NotImplemented",
            RuntimeContextConstant.TRUE: "h_True",
            RuntimeContextConstant.FALSE: "h_False",
            RuntimeContextConstant.ELLIPSIS: "h_Ellipsis",
            RuntimeContextConstant.TYPE_ERROR: "h_TypeError",
            RuntimeContextConstant.BASE_EXCEPTION: "h_BaseException",
            RuntimeContextConstant.TYPE_TYPE: "h_TypeType",
            RuntimeContextConstant.UNICODE_TYPE: "h_UnicodeType",
            RuntimeContextConstant.SLICE_TYPE: "h_SliceType",
            RuntimeContextConstant.LONG_TYPE: "h_LongType",
            RuntimeContextConstant.COMPLEX_TYPE: "h_ComplexType",
            RuntimeContextConstant.LIST_TYPE: "h_ListType",
            RuntimeContextConstant.TUPLE_TYPE: "h_TupleType",
        }
        try:
            name = constants[constant]
        except KeyError:
            raise TypeError(
                "expected RuntimeContextConstant, got %r" % (constant,)) from None
        return "%s->%s" % (context_cname, name)

    def builtin_exception(self, name, context_cname=""):
        context_cname = self._require_context(context_cname)
        if name not in _HPY_BUILTIN_EXCEPTIONS:
            raise ValueError("unsupported builtin exception %r" % name)
        return "%s->h_%s" % (context_cname, name)

    def reference_type_cname(self):
        return "HPy"

    def execution_state_type_cname(self):
        return "HPyThreadState"

    def leave_python_execution(self, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_LeavePythonExecution(%s)" % context_cname

    def reenter_python_execution(self, state_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_ReenterPythonExecution(%s, %s)" % (
            context_cname, state_cname)

    def signed_integer_from_cvalue(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_FromLongLong(%s, %s)" % (
            context_cname, value_cname)

    def ssize_integer_from_cvalue(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_FromSsize_t(%s, %s)" % (
            context_cname, value_cname)

    def unsigned_integer_from_cvalue(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_FromUnsignedLongLong(%s, %s)" % (
            context_cname, value_cname)

    def floating_from_cvalue(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyFloat_FromDouble(%s, %s)" % (
            context_cname, value_cname)

    def signed_long_from_python(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_AsLong(%s, %s)" % (context_cname, value_cname)

    def ssize_t_from_python(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_AsSsize_t(%s, %s)" % (
            context_cname, value_cname)

    def type_check(self, value_cname, type_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_TypeCheck(%s, %s, %s)" % (
            context_cname, value_cname, type_cname)

    def object_type(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Type(%s, %s)" % (context_cname, value_cname)

    def type_is_subtype(self, subtype_cname, type_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyType_IsSubtype(%s, %s, %s)" % (
            context_cname, subtype_cname, type_cname)

    def object_hash(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Hash(%s, %s)" % (context_cname, value_cname)

    def signed_long_long_from_python(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_AsLongLong(%s, %s)" % (context_cname, value_cname)

    def unsigned_long_from_python(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_AsUnsignedLong(%s, %s)" % (
            context_cname, value_cname)

    def unsigned_long_long_from_python(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyLong_AsUnsignedLongLong(%s, %s)" % (
            context_cname, value_cname)

    def double_from_python(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyFloat_AsDouble(%s, %s)" % (context_cname, value_cname)

    def python_error_occurred(self, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyErr_Occurred(%s)" % context_cname

    def unicode_from_utf8(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyUnicode_FromString(%s, %s)" % (
            context_cname, value_cname)

    def unicode_from_encoded_object(
        self, value_cname, encoding_cname, errors_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPyUnicode_FromEncodedObject(%s, %s, %s, %s)" % (
            context_cname, value_cname, encoding_cname, errors_cname)

    def bytes_from_data(self, value_cname, size_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyBytes_FromStringAndSize(%s, %s, %s)" % (
            context_cname, value_cname, size_cname)

    def argument_tracker_type_cname(self):
        return "HPyTracker"

    def parse_keyword_arguments(
        self, tracker_cname, args_cname, nargs_cname, kwnames_cname,
        format_cname, keywords_cname, output_cnames, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        operands = [
            context_cname,
            "&%s" % tracker_cname,
            args_cname,
            nargs_cname,
            kwnames_cname,
            format_cname,
            keywords_cname,
        ]
        operands.extend("&%s" % cname for cname in output_cnames)
        return "HPyArg_ParseKeywords(%s)" % ", ".join(operands)

    def parse_keyword_dictionary(
        self, tracker_cname, args_cname, nargs_cname,
        keyword_dictionary_cname, format_cname, keywords_cname,
        output_cnames, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        operands = [
            context_cname,
            "&%s" % tracker_cname,
            args_cname,
            nargs_cname,
            keyword_dictionary_cname,
            format_cname,
            keywords_cname,
        ]
        operands.extend("&%s" % cname for cname in output_cnames)
        return "HPyArg_ParseKeywordsDict(%s)" % ", ".join(operands)

    def close_argument_tracker(self, tracker_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyTracker_Close(%s, %s);" % (
            context_cname, tracker_cname)

    def length(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Length(%s, %s)" % (context_cname, value_cname)

    def item_get_index(self, receiver_cname, index_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_GetItem_i(%s, %s, %s)" % (
            context_cname, receiver_cname, index_cname)

    def unicode_as_utf8_and_size(
        self, value_cname, size_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPyUnicode_AsUTF8AndSize(%s, %s, &%s)" % (
            context_cname, value_cname, size_cname)

    def truth_test(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_IsTrue(%s, %s)" % (context_cname, value_cname)

    def binary_operation(
        self, operation, left_cname, right_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        if operation is RuntimeBinaryOperation.POWER:
            return "HPy_Power(%s, %s, %s, %s->h_None)" % (
                context_cname, left_cname, right_cname, context_cname)
        functions = {
            RuntimeBinaryOperation.ADD: "HPy_Add",
            RuntimeBinaryOperation.SUBTRACT: "HPy_Subtract",
            RuntimeBinaryOperation.MULTIPLY: "HPy_Multiply",
            RuntimeBinaryOperation.MATRIX_MULTIPLY: "HPy_MatrixMultiply",
            RuntimeBinaryOperation.TRUE_DIVIDE: "HPy_TrueDivide",
            RuntimeBinaryOperation.FLOOR_DIVIDE: "HPy_FloorDivide",
            RuntimeBinaryOperation.REMAINDER: "HPy_Remainder",
            RuntimeBinaryOperation.LEFT_SHIFT: "HPy_Lshift",
            RuntimeBinaryOperation.RIGHT_SHIFT: "HPy_Rshift",
            RuntimeBinaryOperation.BITWISE_AND: "HPy_And",
            RuntimeBinaryOperation.BITWISE_XOR: "HPy_Xor",
            RuntimeBinaryOperation.BITWISE_OR: "HPy_Or",
        }
        try:
            function = functions[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeBinaryOperation, got %r" % operation) from None
        return "%s(%s, %s, %s)" % (
            function, context_cname, left_cname, right_cname)

    def unary_operation(self, operation, operand_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        functions = {
            RuntimeUnaryOperation.POSITIVE: "HPy_Positive",
            RuntimeUnaryOperation.NEGATIVE: "HPy_Negative",
            RuntimeUnaryOperation.INVERT: "HPy_Invert",
        }
        try:
            function = functions[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeUnaryOperation, got %r" % operation) from None
        return "%s(%s, %s)" % (function, context_cname, operand_cname)

    def object_str(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Str(%s, %s)" % (context_cname, value_cname)

    def object_repr(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Repr(%s, %s)" % (context_cname, value_cname)

    def object_ascii(self, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_ASCII(%s, %s)" % (context_cname, value_cname)

    def inplace_operation(
        self, operation, left_cname, right_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        if operation is RuntimeInPlaceOperation.POWER:
            return "HPy_InPlacePower(%s, %s, %s, %s->h_None)" % (
                context_cname, left_cname, right_cname, context_cname)
        functions = {
            RuntimeInPlaceOperation.ADD: "HPy_InPlaceAdd",
            RuntimeInPlaceOperation.SUBTRACT: "HPy_InPlaceSubtract",
            RuntimeInPlaceOperation.MULTIPLY: "HPy_InPlaceMultiply",
            RuntimeInPlaceOperation.MATRIX_MULTIPLY: "HPy_InPlaceMatrixMultiply",
            RuntimeInPlaceOperation.TRUE_DIVIDE: "HPy_InPlaceTrueDivide",
            RuntimeInPlaceOperation.FLOOR_DIVIDE: "HPy_InPlaceFloorDivide",
            RuntimeInPlaceOperation.REMAINDER: "HPy_InPlaceRemainder",
            RuntimeInPlaceOperation.LEFT_SHIFT: "HPy_InPlaceLshift",
            RuntimeInPlaceOperation.RIGHT_SHIFT: "HPy_InPlaceRshift",
            RuntimeInPlaceOperation.BITWISE_AND: "HPy_InPlaceAnd",
            RuntimeInPlaceOperation.BITWISE_XOR: "HPy_InPlaceXor",
            RuntimeInPlaceOperation.BITWISE_OR: "HPy_InPlaceOr",
        }
        try:
            function = functions[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeInPlaceOperation, got %r" % operation) from None
        return "%s(%s, %s, %s)" % (
            function, context_cname, left_cname, right_cname)

    def rich_compare(
        self, operation, left_cname, right_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        operators = {
            RuntimeComparisonOperation.LESS_THAN: "HPy_LT",
            RuntimeComparisonOperation.LESS_EQUAL: "HPy_LE",
            RuntimeComparisonOperation.EQUAL: "HPy_EQ",
            RuntimeComparisonOperation.NOT_EQUAL: "HPy_NE",
            RuntimeComparisonOperation.GREATER_THAN: "HPy_GT",
            RuntimeComparisonOperation.GREATER_EQUAL: "HPy_GE",
        }
        try:
            operator = operators[operation]
        except KeyError:
            raise TypeError(
                "expected RuntimeComparisonOperation, got %r" % operation) from None
        return "HPy_RichCompare(%s, %s, %s, %s)" % (
            context_cname, left_cname, right_cname, operator)

    def identity_test(self, left_cname, right_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Is(%s, %s, %s)" % (
            context_cname, left_cname, right_cname)

    def contains(self, container_cname, key_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Contains(%s, %s, %s)" % (
            context_cname, container_cname, key_cname)

    def attribute_get_string(
        self, receiver_cname, name_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_GetAttr_s(%s, %s, %s)" % (
            context_cname, receiver_cname, name_cname)

    def attribute_has_string(
        self, receiver_cname, name_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_HasAttr_s(%s, %s, %s)" % (
            context_cname, receiver_cname, name_cname)

    def item_get(self, receiver_cname, key_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_GetItem(%s, %s, %s)" % (
            context_cname, receiver_cname, key_cname)

    def item_set(
        self, receiver_cname, key_cname, value_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_SetItem(%s, %s, %s, %s)" % (
            context_cname, receiver_cname, key_cname, value_cname)

    def item_delete(self, receiver_cname, key_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_DelItem(%s, %s, %s)" % (
            context_cname, receiver_cname, key_cname)

    def attribute_set_string(
        self, receiver_cname, name_cname, value_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_SetAttr_s(%s, %s, %s, %s)" % (
            context_cname, receiver_cname, name_cname, value_cname)

    def attribute_delete_string(
        self, receiver_cname, name_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_DelAttr_s(%s, %s, %s)" % (
            context_cname, receiver_cname, name_cname)

    def empty_reference(self, cname):
        return "%s = HPy_NULL;" % cname

    def null_reference_value(self):
        return "HPy_NULL"

    def null_check(self, cname):
        return "HPy_IsNull(%s)" % cname

    def duplicate_reference(self, cname, null_safe=False, context_cname=""):
        context_cname = self._require_context(context_cname)
        duplicate = "HPy_Dup(%s, %s)" % (context_cname, cname)
        if null_safe:
            return "HPy_IsNull(%s) ? HPy_NULL : %s" % (cname, duplicate)
        return duplicate

    def close_reference(self, cname, null_safe=False, context_cname=""):
        context_cname = self._require_context(context_cname)
        close = "HPy_Close(%s, %s);" % (context_cname, cname)
        if null_safe:
            return "if (!HPy_IsNull(%s)) %s" % (cname, close)
        return close

    def call_tuple_dict(
        self,
        callable_cname,
        args_cname,
        kwargs_cname="HPy_NULL",
        use_utility_code=True,
        context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_CallTupleDict(%s, %s, %s, %s)" % (
            context_cname, callable_cname, args_cname, kwargs_cname)

    def call_no_args(self, callable_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Call(%s, %s, NULL, 0, HPy_NULL)" % (
            context_cname, callable_cname)

    def call_one_arg(self, callable_cname, arg_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_Call(%s, %s, &%s, 1, HPy_NULL)" % (
            context_cname, callable_cname, arg_cname)

    def call_positional_array(
        self, callable_cname, args_cname, nargs_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_Call(%s, %s, %s, %s, HPy_NULL)" % (
            context_cname, callable_cname, args_cname, nargs_cname)

    def call_array_with_keyword_names(
        self, callable_cname, args_cname, nargs_cname, kwnames_cname,
        context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_Call(%s, %s, %s, %s, %s)" % (
            context_cname, callable_cname, args_cname, nargs_cname,
            kwnames_cname)

    def call_method_no_args(self, receiver_cname, name_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_CallMethod(%s, %s, &%s, 1, HPy_NULL)" % (
            context_cname, name_cname, receiver_cname)

    def call_method_array(
        self,
        name_cname,
        args_cname,
        nargs_cname,
        kwnames_cname="",
        context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        if not kwnames_cname:
            kwnames_cname = "HPy_NULL"
        return "HPy_CallMethod(%s, %s, %s, %s, %s)" % (
            context_cname, name_cname, args_cname, nargs_cname,
            kwnames_cname)

    def sequence_builder(self, kind):
        if not isinstance(kind, RuntimeSequenceKind):
            raise TypeError("expected RuntimeSequenceKind, got %r" % (kind,))
        kind_name = "List" if kind is RuntimeSequenceKind.LIST else "Tuple"
        return RuntimeSequenceBuilder(
            kind=kind,
            builder_type_cname="HPy%sBuilder" % kind_name,
            result_type_cname="HPy",
            uses_separate_builder=True,
            set_item_steals_reference=False,
            creation_reports_error=False,
            supports_from_array=kind is RuntimeSequenceKind.TUPLE,
        )

    def sequence_builder_new(self, builder, size_cname, context_cname=""):
        self._validate_sequence_builder(builder)
        context_cname = self._require_context(context_cname)
        return "HPy%sBuilder_New(%s, %s)" % (
            self._sequence_kind_name(builder), context_cname, size_cname)

    def sequence_builder_set(
        self, builder, builder_cname, index_cname, item_cname, context_cname="",
    ):
        self._validate_sequence_builder(builder)
        context_cname = self._require_context(context_cname)
        return "HPy%sBuilder_Set(%s, %s, %s, %s)" % (
            self._sequence_kind_name(builder), context_cname, builder_cname,
            index_cname, item_cname)

    def sequence_builder_build(self, builder, builder_cname, context_cname=""):
        self._validate_sequence_builder(builder)
        context_cname = self._require_context(context_cname)
        return "HPy%sBuilder_Build(%s, %s)" % (
            self._sequence_kind_name(builder), context_cname, builder_cname)

    def sequence_builder_cancel(self, builder, builder_cname, context_cname=""):
        self._validate_sequence_builder(builder)
        context_cname = self._require_context(context_cname)
        return "HPy%sBuilder_Cancel(%s, %s);" % (
            self._sequence_kind_name(builder), context_cname, builder_cname)

    def select_sequence_from_array(self, kind):
        builder = self.sequence_builder(kind)
        if not builder.supports_from_array:
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.CONTAINER_BUILDERS,
                "HPy exposes HPyTuple_FromArray but no list-from-array operation",
                "construct the list with HPyListBuilder",
            )
        return RuntimeSequenceFromArray(
            kind=kind,
            function_cname="HPyTuple_FromArray",
        )

    def sequence_from_array(
        self, operation, items_cname, size_cname, context_cname="",
    ):
        if operation != self.select_sequence_from_array(operation.kind):
            raise ValueError("array constructor belongs to a different runtime contract")
        context_cname = self._require_context(context_cname)
        return "%s(%s, %s, %s)" % (
            operation.function_cname, context_cname, items_cname, size_cname)

    def sequence_pack(self, kind, item_cnames, context_cname=""):
        if kind is not RuntimeSequenceKind.TUPLE:
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.CONTAINER_BUILDERS,
                "HPy exposes HPyTuple_Pack but no HPyList_Pack operation",
                "construct the list with HPyListBuilder",
            )
        context_cname = self._require_context(context_cname)
        items = list(item_cnames)
        operands = [context_cname, str(len(items))] + items
        return "HPyTuple_Pack(%s)" % ", ".join(operands)

    def dict_new(self, presized_size_cname="", context_cname=""):
        # HPy currently exposes no presized dictionary constructor.
        context_cname = self._require_context(context_cname)
        return "HPyDict_New(%s)" % context_cname

    def dict_set_item(self, dict_cname, key_cname, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPy_SetItem(%s, %s, %s, %s)" % (
            context_cname, dict_cname, key_cname, value_cname)

    def dict_set_item_string(
        self, dict_cname, key_cname, value_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_SetItem_s(%s, %s, %s, %s)" % (
            context_cname, dict_cname, key_cname, value_cname)

    def dict_copy(self, dict_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyDict_Copy(%s, %s)" % (context_cname, dict_cname)

    def to_python_conversion(
        self, conversion, source_code, result_code, result_type, to_py_function=None,
    ):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.VALUE_CONVERSIONS,
            "HPy scalar conversion emission requires M2 handle/context storage",
            "use the CPython backend until the HPy ownership model is enabled",
        )

    def from_python_conversion(
        self,
        conversion,
        source_code,
        result_code,
        error_pos,
        code,
        from_py_function=None,
        error_condition=None,
        special_none_cvalue=None,
    ):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.VALUE_CONVERSIONS,
            "HPy scalar conversion emission requires M2 handle/context storage",
            "use the CPython backend until the HPy ownership model is enabled",
            error_pos,
        )

    def error_set_string(self, exception_cname, message_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyErr_SetString(%s, %s, %s)" % (
            context_cname, exception_cname, message_cname)

    def error_set_from_errno(self, exception_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyErr_SetFromErrno(%s, %s)" % (
            context_cname, exception_cname)

    def error_set_object(self, exception_cname, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyErr_SetObject(%s, %s, %s)" % (
            context_cname, exception_cname, value_cname)

    def error_set_none(self, exception_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyErr_SetObject(%s, %s, %s->h_None)" % (
            context_cname, exception_cname, context_cname)

    def error_format(
        self, exception_cname, format_cname, arg_cnames, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        operands = [context_cname, exception_cname, format_cname] + list(arg_cnames)
        return "HPyErr_Format(%s)" % ", ".join(operands)

    def error_clear(self, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyErr_Clear(%s)" % context_cname

    def error_no_memory(self, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyErr_NoMemory(%s)" % context_cname

    def current_exception_type(self, use_utility_code=True, context_cname=""):
        return self._unsupported_exception_triple()

    def exception_matches(
        self,
        pattern_cname,
        exception_cname="",
        second_pattern_cname="",
        use_utility_code=False,
        context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        if exception_cname or second_pattern_cname:
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.EXCEPTION_STATE,
                "HPy only exposes matching against the currently raised exception",
                "normalize control flow to current-exception matching or reject the feature",
            )
        return "HPyErr_ExceptionMatches(%s, %s)" % (context_cname, pattern_cname)

    def _unsupported_exception_triple(self):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.EXCEPTION_STATE,
            "HPy has no public CPython-style type/value/traceback exception triple API",
            "use HPy current-error operations or an explicitly validated backend helper",
        )

    def fetch_exception(self, *args, **kwargs):
        return self._unsupported_exception_triple()

    def restore_exception(self, *args, **kwargs):
        return self._unsupported_exception_triple()

    def raise_exception(self, *args, **kwargs):
        return self._unsupported_exception_triple()

    def reraise_exception(self):
        return self._unsupported_exception_triple()

    def get_exception(self, arg_cnames):
        return self._unsupported_exception_triple()

    def save_exception(self, arg_cnames):
        return self._unsupported_exception_triple()

    def reset_exception(self, arg_cnames):
        return self._unsupported_exception_triple()

    def swap_exception(self, arg_ptr_cnames):
        return self._unsupported_exception_triple()

    def name_lookup(
        self, lookup, result_cname, name_cname, namespace_cname="", context_cname="",
    ):
        if not isinstance(lookup, RuntimeNameLookup):
            raise TypeError("expected RuntimeNameLookup, got %r" % (lookup,))
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.MODULE_GLOBALS,
            "HPy name lookup requires registered global storage, module execution state, and owned local handles",
            "enable the M2 ownership/context model and M3 HPy module namespace helpers",
        )

    def global_storage(self):
        return self._global_storage

    def global_load(self, storage_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyGlobal_Load(%s, %s)" % (context_cname, storage_cname)

    def global_store(self, storage_cname, value_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyGlobal_Store(%s, &%s, %s)" % (
            context_cname, storage_cname, value_cname)

    def field_load(self, owner_cname, field_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyField_Load(%s, %s, %s)" % (
            context_cname, owner_cname, field_cname)

    def field_store(
        self, owner_cname, field_cname, value_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPyField_Store(%s, %s, &%s, %s)" % (
            context_cname, owner_cname, field_cname, value_cname)

    def module_definition(self):
        return self._module_definition

    def import_module(self, name_cname, context_cname=""):
        context_cname = self._require_context(context_cname)
        return "HPyImport_ImportModule(%s, %s)" % (context_cname, name_cname)

    def module_set_attr(
        self, module_cname, name_cname, value_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_SetAttr(%s, %s, %s, %s)" % (
            context_cname, module_cname, name_cname, value_cname)

    def module_set_attr_string(
        self, module_cname, name_cname, value_cname, context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPy_SetAttr_s(%s, %s, %s, %s)" % (
            context_cname, module_cname, name_cname, value_cname)

    def _unsupported_cpython_module_operation(self, operation):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.MODULE_DEFINITIONS,
            "%s has no public Universal HPy equivalent" % operation,
            "move initialization into HPy_mod_exec and use HPyModuleDef-managed state",
        )

    def module_create(self, definition_cname, context_cname=""):
        return self._unsupported_cpython_module_operation("manual module creation")

    def module_get_dict(self, module_cname, context_cname=""):
        return self._unsupported_cpython_module_operation("borrowed module-dict access")

    def import_add_module_ref(self, name_cname, context_cname=""):
        return self._unsupported_cpython_module_operation(
            "creating or retrieving a sys.modules entry")

    def import_get_module_dict(self, context_cname=""):
        return self._unsupported_cpython_module_operation(
            "borrowed sys.modules dictionary access")

    def module_slot_definition(
        self, slot_name, implementation_cname, pointer_cast="",
    ):
        if not slot_name or not implementation_cname:
            raise ValueError("module slot name and implementation are required")
        if slot_name not in ("mod_create", "mod_exec"):
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.MODULE_DEFINITIONS,
                "CPython module slot Py_%s has no enabled Universal HPy definition" %
                    slot_name,
                "express the policy through HPy module metadata or reject the feature",
            )
        return "HPyDef_SLOT(%s, HPy_%s)" % (
            implementation_cname, slot_name)

    def module_slot_terminator(self):
        return "NULL"

    def module_definition_forward_declaration(self, definition_cname, linkage):
        if linkage not in ("extern", "static"):
            raise ValueError("module definition linkage must be extern or static")
        return "%s %s %s;" % (
            linkage, self._module_definition.definition_type_cname,
            definition_cname)

    def module_slot_array_declaration(self, slots_cname):
        return "static HPyDef *%s[] = {" % slots_cname

    def module_definition_declaration(self, definition_cname, linkage):
        if linkage not in ("", "static"):
            raise ValueError("module definition linkage must be empty or static")
        prefix = "%s " % linkage if linkage else ""
        return "%s%s %s =" % (
            prefix, self._module_definition.definition_type_cname,
            definition_cname)

    def module_init_definition_result(self, definition_cname):
        raise RuntimeCapabilityError(
            self.name,
            RuntimeCapability.MODULE_DEFINITIONS,
            "HPy module init returns its definition through HPy_MODINIT, not an expression",
            "emit HPy_MODINIT after the complete HPyModuleDef and run setup in HPy_mod_exec",
        )

    def method_definition_prefix(self, definition_cname):
        return ""

    def method_definition_declaration(self, definition):
        self._validate_method_definition(definition)
        hpy_signature = {
            RuntimeMethodSignature.NOARGS: "HPyFunc_NOARGS",
            RuntimeMethodSignature.ONEARG: "HPyFunc_O",
            RuntimeMethodSignature.POSITIONAL_VARARGS: "HPyFunc_VARARGS",
            RuntimeMethodSignature.VARARGS_KEYWORDS: "HPyFunc_KEYWORDS",
            RuntimeMethodSignature.FASTCALL_KEYWORDS: "HPyFunc_KEYWORDS",
        }[definition.signature]
        expected_implementation = "%s_impl" % definition.definition_cname
        if definition.implementation_cname != expected_implementation:
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.MODULE_DEFINITIONS,
                "HPyDef_METH requires implementation symbol %s" %
                    expected_implementation,
                "generate the HPy method wrapper before emitting its definition",
            )
        doc_argument = (
            ", .doc = %s" % definition.doc_cname
            if definition.doc_cname not in ("0", "NULL") else ""
        )
        return "HPyDef_METH(%s, %s, %s%s)" % (
            definition.definition_cname,
            definition.python_name_cname,
            hpy_signature,
            doc_argument,
        )

    def method_implementation_declaration(
        self, definition, context_cname="", receiver_cname="self",
        argument_cname="arg",
    ):
        self._validate_method_definition(definition)
        context_cname = self._require_context(context_cname)
        if definition.signature is RuntimeMethodSignature.NOARGS:
            return "static HPy %s(HPyContext *%s, HPy %s)" % (
                definition.implementation_cname, context_cname, receiver_cname)
        if definition.signature is RuntimeMethodSignature.ONEARG:
            return "static HPy %s(HPyContext *%s, HPy %s, HPy %s)" % (
                definition.implementation_cname,
                context_cname,
                receiver_cname,
                argument_cname,
            )
        if definition.signature is RuntimeMethodSignature.POSITIONAL_VARARGS:
            return (
                "static HPy %s(HPyContext *%s, HPy %s, const HPy *args, "
                "size_t nargs)" % (
                    definition.implementation_cname,
                    context_cname,
                    receiver_cname,
                )
            )
        if definition.signature in (
            RuntimeMethodSignature.VARARGS_KEYWORDS,
            RuntimeMethodSignature.FASTCALL_KEYWORDS,
        ):
            return (
                "static HPy %s(HPyContext *%s, HPy %s, const HPy *args, "
                "size_t nargs, HPy kwnames)" % (
                    definition.implementation_cname,
                    context_cname,
                    receiver_cname,
                )
            )
        raise ValueError(
            "bootstrap method declaration requires a supported HPy signature")

    def method_table_declaration(self, table_cname):
        return "static HPyDef *%s[] = {" % table_cname

    def method_table_entry(self, definition, terminator):
        self._validate_method_definition(definition)
        return "&%s%s" % (definition.definition_cname, terminator)

    def method_table_terminator(self):
        return "NULL"

    def method_table_end(self):
        return "};"

    def type_definition(self):
        return self._type_definition

    def type_slot_definition(
        self, slot_name, definition_cname, implementation_cname,
    ):
        if not slot_name or not definition_cname or not implementation_cname:
            raise ValueError("type slot names and implementation are required")
        if slot_name not in self._supported_type_slots:
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.TYPE_DEFINITIONS,
                "CPython slot Py_%s has no enabled pure-HPy slot mapping" %
                    slot_name,
                "implement or reject the feature in the owning extension-type milestone",
            )
        expected_implementation = "%s_impl" % definition_cname
        if implementation_cname != expected_implementation:
            raise RuntimeCapabilityError(
                self.name,
                RuntimeCapability.TYPE_DEFINITIONS,
                "HPyDef_SLOT requires implementation symbol %s" %
                    expected_implementation,
                "generate a pure-HPy slot wrapper with the required signature",
            )
        return "HPyDef_SLOT(%s, HPy_%s)" % (definition_cname, slot_name)

    def type_definition_array_declaration(self, type_cname):
        return "static HPyDef *%s_defines[] = {" % type_cname

    def type_slot_table_entry(
        self, slot_name, definition_cname, implementation_cname,
        pointer_cast="(void *)",
    ):
        self.type_slot_definition(
            slot_name, definition_cname, implementation_cname)
        return "&%s," % definition_cname

    def type_definition_array_terminator(self):
        return "NULL"

    def type_specification_declaration(self, type_cname):
        return "static HPyType_Spec %s_spec = {" % type_cname

    def type_from_spec(
        self, spec_cname, params_cname="NULL", context_cname="",
    ):
        context_cname = self._require_context(context_cname)
        return "HPyType_FromSpec(%s, &%s, %s)" % (
            context_cname, spec_cname, params_cname)

    def _require_context(self, context_cname):
        return self._context_contract.require_cname(context_cname)

    @staticmethod
    def _sequence_kind_name(builder):
        return "List" if builder.kind is RuntimeSequenceKind.LIST else "Tuple"

    def _validate_sequence_builder(self, builder):
        if not isinstance(builder, RuntimeSequenceBuilder):
            raise TypeError("expected RuntimeSequenceBuilder, got %r" % (builder,))
        if builder != self.sequence_builder(builder.kind):
            raise ValueError("sequence builder belongs to a different runtime contract")


class HPyUniversalRuntimeAPI(_HPyRuntimeAPIBase):
    def __init__(self):
        super().__init__(
            HPY_UNIVERSAL_BACKEND,
            frozenset(),
        )

    def code_generation_kind(self):
        return RuntimeCodeGenerationKind.HPY_UNIVERSAL_BOOTSTRAP

    def module_emitter(self):
        from .HPyModuleWriter import emit_hpy_universal_module
        return RuntimeModuleEmitter(self.name, emit_hpy_universal_module)


class HPyCPythonRuntimeAPI(_HPyRuntimeAPIBase):
    def __init__(self):
        super().__init__(
            HPY_CPYTHON_BACKEND,
            frozenset(),
            "the test-only HPy CPython ABI lane is not implemented yet",
            "use 'cpython' or wait for the HPy conformance test lane",
        )


def validate_runtime_backend_name(name):
    if not isinstance(name, str):
        raise RuntimeBackendOptionError(
            "runtime_backend must be a string, got %s" % type(name).__name__
        )
    if name in ACCEPTED_RUNTIME_BACKENDS:
        return name
    if name in RESERVED_RUNTIME_BACKENDS:
        raise RuntimeBackendOptionError(
            "runtime backend %r is reserved but not enabled" % name
        )
    raise RuntimeBackendOptionError(
        "unknown runtime backend %r; expected one of: %s"
        % (name, ", ".join(ACCEPTED_RUNTIME_BACKENDS))
    )


def create_runtime_api(name):
    name = validate_runtime_backend_name(name)
    implementations = {
        CPYTHON_BACKEND: CPythonRuntimeAPI,
        HPY_UNIVERSAL_BACKEND: HPyUniversalRuntimeAPI,
        HPY_CPYTHON_BACKEND: HPyCPythonRuntimeAPI,
    }
    return implementations[name]()
