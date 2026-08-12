"""Strict bootstrap emitter for Universal HPy module translation units.

This is deliberately a vertical slice, not a compatibility fallback.  It
accepts only the source constructs whose ownership and runtime behaviour are
implemented below and rejects every other construct at its source position.
"""

import copy
import math
import re

from . import ExprNodes, Nodes, Options, PyrexTypes
from .Errors import CompileError
from .HandleModel import (
    HandleBuilderManager,
    HandleOwnership,
    HandleTemporaryManager,
    HandleTrackerManager,
)
from .RuntimeAPI import (
    RuntimeBinaryOperation,
    RuntimeComparisonOperation,
    RuntimeContextConstant,
    RuntimeInPlaceOperation,
    RuntimeMethodDefinition,
    RuntimeMethodSignature,
    RuntimeSequenceKind,
)
from .StringEncoding import EncodedString
from ..Utils import GENERATED_BY_MARKER, open_new_file


_C_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _c_identifier_fragment(value):
    """Preserve ASCII identifiers and encode other Python identifiers for C."""
    if _C_IDENTIFIER.match(value):
        return value
    return "unicode_%s" % value.encode("utf8").hex()


def _resolve_extension_field_storage_type(field_type):
    while isinstance(field_type, PyrexTypes.CTypedefType):
        if field_type.typedef_is_external:
            return None
        field_type = field_type.typedef_base_type
    return field_type


def _extension_field_storage(field_type, field_cname):
    field_type = _resolve_extension_field_storage_type(field_type)
    if field_type is PyrexTypes.py_object_type:
        return "HPyField %s" % field_cname, "HPyMember_OBJECT", "object"
    native_types = {
        PyrexTypes.c_bint_type:
            ("char", "HPyMember_BOOL", "bint"),
        PyrexTypes.c_py_ssize_t_type:
            ("HPy_ssize_t", "HPyMember_HPYSSIZET", "py-ssize"),
        PyrexTypes.c_char_type:
            ("char", "HPyMember_CHAR", "char"),
        PyrexTypes.c_schar_type:
            ("signed char", "HPyMember_BYTE", "signed-char"),
        PyrexTypes.c_uchar_type:
            ("unsigned char", "HPyMember_UBYTE", "unsigned-char"),
        PyrexTypes.c_short_type:
            ("short", "HPyMember_SHORT", "signed-short"),
        PyrexTypes.c_ushort_type:
            ("unsigned short", "HPyMember_USHORT", "unsigned-short"),
        PyrexTypes.c_int_type:
            ("int", "HPyMember_INT", "signed-int"),
        PyrexTypes.c_uint_type:
            ("unsigned int", "HPyMember_UINT", "unsigned-int"),
        PyrexTypes.c_long_type:
            ("long", "HPyMember_LONG", "signed-long"),
        PyrexTypes.c_ulong_type:
            ("unsigned long", "HPyMember_ULONG", "unsigned-long"),
        PyrexTypes.c_longlong_type:
            ("long long", "HPyMember_LONGLONG", "signed-long-long"),
        PyrexTypes.c_ulonglong_type:
            ("unsigned long long", "HPyMember_ULONGLONG", "unsigned-long-long"),
        PyrexTypes.c_float_type:
            ("float", "HPyMember_FLOAT", "float"),
        PyrexTypes.c_double_type:
            ("double", "HPyMember_DOUBLE", "double"),
        PyrexTypes.c_longdouble_type:
            ("long double", None, "long-double"),
    }
    if field_type is not None and field_type.is_array:
        if (
            not isinstance(field_type.size, int)
            or field_type.size <= 0
            or field_type.base_type.is_array
        ):
            raise AssertionError(
                "unvalidated pure HPy extension array field type: %r" %
                field_type)
        element_type = _resolve_extension_field_storage_type(
            field_type.base_type)
        element_storage = native_types.get(element_type)
        if element_storage is None:
            raise AssertionError(
                "unvalidated pure HPy extension array element type: %r" %
                element_type)
        element_declaration, _, element_storage_kind = element_storage
        return (
            "%s %s[%d]" % (
                element_declaration, field_cname, field_type.size),
            None,
            "fixed-array:%s" % element_storage_kind,
        )
    storage = native_types.get(field_type)
    if storage is not None:
        declaration, member_kind, storage_kind = storage
        return "%s %s" % (declaration, field_cname), member_kind, storage_kind
    raise AssertionError("unvalidated pure HPy extension field type: %r" % field_type)


def _supports_extension_field_storage(field_type):
    resolved_type = _resolve_extension_field_storage_type(field_type)
    if resolved_type is not None and resolved_type.is_array:
        # Fixed arrays are admitted only by the stricter buffer-producer
        # validator; general field load/store and member exposure stay closed.
        return False
    try:
        _extension_field_storage(field_type, "field")
    except AssertionError:
        return False
    return True


def _external_c_scalar_kind(value_type):
    """Return the HPy conversion family for a portable direct C scalar."""
    value_type = _resolve_extension_field_storage_type(value_type)
    if value_type is None or value_type is PyrexTypes.py_object_type:
        return None
    try:
        _, _, storage_kind = _extension_field_storage(value_type, "value")
    except AssertionError:
        return None
    if storage_kind == "py-ssize":
        # Py_ssize_t is owned by Python.h, not a Python-independent C ABI.
        return None
    return storage_kind


class _ClosureCapture:
    __slots__ = ("name", "entry", "field_cname")

    def __init__(self, name, entry, field_cname):
        self.name = name
        self.entry = entry
        self.field_cname = field_cname


class _ClosureEnvSpec:
    __slots__ = (
        "index", "outer_def", "captures", "struct_cname", "type_cname",
        "spec_cname", "module_global",
    )

    def __init__(self, index, outer_def, captures):
        self.index = index
        self.outer_def = outer_def
        self.captures = captures
        self.type_cname = "__pyx_hpy_closure_env_%d" % index
        self.struct_cname = "%s_object" % self.type_cname
        self.spec_cname = "%s_spec" % self.type_cname
        self.module_global = self.type_cname


class _ClosureFnSpec:
    __slots__ = (
        "index", "inner_def", "inner_node", "env_spec", "struct_cname",
        "type_cname", "spec_cname", "module_global", "call_impl_cname",
        "env_field_cname",
    )

    def __init__(self, index, inner_def, inner_node, env_spec):
        self.index = index
        self.inner_def = inner_def
        self.inner_node = inner_node
        self.env_spec = env_spec
        self.type_cname = "__pyx_hpy_closure_fn_%d" % index
        self.struct_cname = "%s_object" % self.type_cname
        self.spec_cname = "%s_spec" % self.type_cname
        self.module_global = self.type_cname
        self.call_impl_cname = "%s_tp_call_impl" % self.type_cname
        self.env_field_cname = "__pyx_hpy_closure_env"


class _ClosureRegistry:
    __slots__ = ("env_by_outer", "fn_by_inner_def", "fn_by_inner_node", "env_specs", "fn_specs")

    def __init__(self, env_specs, fn_specs):
        self.env_specs = tuple(env_specs)
        self.fn_specs = tuple(fn_specs)
        self.env_by_outer = {id(spec.outer_def): spec for spec in env_specs}
        self.fn_by_inner_def = {id(spec.inner_def): spec for spec in fn_specs}
        self.fn_by_inner_node = {id(spec.inner_node): spec for spec in fn_specs}

    def field_layout_for_env(self, env_spec):
        layout = {}
        for capture in env_spec.captures:
            layout[id(capture.entry)] = (
                env_spec.struct_cname, capture.field_cname, "object")
            layout[("field", capture.name)] = layout[id(capture.entry)]
        return layout

    def field_layout_for_fn_env_field(self, fn_spec):
        return {
            ("field", fn_spec.env_field_cname): (
                fn_spec.struct_cname, fn_spec.env_field_cname, "object"),
        }


class UniversalHPyFunctionWriter:
    """Small line writer consumed by syntax-specific Cython AST nodes."""

    def __init__(
        self,
        runtime_api,
        name_registry=None,
        failure_return_value=None,
        available_module_globals=None,
        module_cname=None,
        constant_registry=None,
        default_registry=None,
        use_constant_cache=True,
        failure_epilogue=(),
        rollback_module_publications=False,
        extension_field_layout=None,
        native_return_kind=None,
        closure_registry=None,
        closure_env_spec=None,
        closure_env_owner_cname=None,
    ):
        self.runtime_api = runtime_api
        self.context_cname = runtime_api.context_contract().default_parameter_cname
        self.name_registry = name_registry
        self.failure_return_value = (
            runtime_api.null_reference_value()
            if failure_return_value is None else failure_return_value
        )
        self.available_module_globals = available_module_globals
        self.module_cname = module_cname
        self.default_owner_cname = module_cname
        self._extension_runtime_receiver_cname = None
        self.constant_registry = constant_registry
        self.default_registry = default_registry
        self.use_constant_cache = use_constant_cache
        self.failure_epilogue = tuple(failure_epilogue)
        self.rollback_module_publications = rollback_module_publications
        self._rollback_module_attributes = set()
        self._module_publication_rollbacks = []
        self.extension_field_layout = extension_field_layout or {}
        self.closure_registry = closure_registry
        self.closure_env_spec = closure_env_spec
        self._closure_env_owner_cname = closure_env_owner_cname
        self._closure_in_closure_names = set()
        if closure_env_spec is not None:
            self._closure_in_closure_names = {
                capture.name for capture in closure_env_spec.captures}
        # ``ssize`` / ``bool`` / ``hash`` convert HPy returns for native slots.
        self.native_return_kind = native_return_kind
        self.lines = []
        self._indent = 0
        self._handle_temps = HandleTemporaryManager()
        self._builder_temps = HandleBuilderManager()
        self._tracker_temps = HandleTrackerManager()
        self._builder_contracts = {}
        self._handle_order = []
        self._builder_order = []
        self._next_handle = 0
        self._next_builder = 0
        self._next_truth = 0
        self._next_call_array = 0
        self._next_status = 0
        self._next_loop = 0
        self._next_field_owner = 0
        self._next_native_field = 0
        self._next_exception_handler = 0
        self._next_thread_state = 0
        self._borrowed_arguments = {}
        self._local_values = {}
        self._temporary_values = {}
        self._c_temporary_values = {}
        self._comprehension_targets = {}
        self._stable_local_slots = set()
        self._tracker_owned_arguments = set()
        self._argument_tracker_cname = "__pyx_hpy_arg_tracker"
        self._loop_stack = []
        self._loop_lifetime_stack = []
        self._failure_scopes = []

    def putln(self, line):
        self.lines.append("    " * self._indent + line)

    def indent(self):
        self._indent += 1

    def dedent(self):
        if self._indent == 0:
            raise AssertionError("cannot dedent bootstrap HPy code below zero")
        self._indent -= 1

    @staticmethod
    def stats(node):
        flattened = []

        def append(statement):
            if type(statement) is Nodes.StatListNode:
                for child in statement.stats:
                    append(child)
            else:
                flattened.append(statement)

        append(node)
        return flattened

    @staticmethod
    def is_c_identifier(value):
        return bool(_C_IDENTIFIER.match(value))

    @staticmethod
    def unsupported(node, message):
        raise CompileError(
            getattr(node, "pos", None),
            "aHPy bootstrap backend: %s" % message,
        )

    def allocate_owned_handle(self, expression):
        cname = "__pyx_hpy_temp_%d" % self._next_handle
        self._next_handle += 1
        self._handle_temps.allocate(cname, HandleOwnership.OWNED)
        self._handle_order.append(cname)
        self.putln("%s %s = %s;" % (
            self.runtime_api.reference_type_cname(), cname, expression))
        return cname

    def materialize_owned_handle(self, result):
        if self._handle_temps.is_active(result):
            self._handle_temps.use(result)
            return result
        return self.allocate_owned_handle(result)

    def close_owned_handle(self, cname, null_safe=False):
        self._handle_temps.use(cname)
        self.putln(self.runtime_api.close_reference(
            cname, null_safe=null_safe, context_cname=self.context_cname))
        self._handle_temps.close(cname)
        self._handle_temps.release(cname)
        self._handle_order.remove(cname)

    def use_owned_handles(self, *cnames):
        for cname in cnames:
            self._handle_temps.use(cname)

    def bind_borrowed_argument(self, source_name, cname, tracker_owned=False):
        if source_name in self._borrowed_arguments:
            raise AssertionError("bootstrap argument is already bound")
        self._handle_temps.allocate(cname, HandleOwnership.BORROWED_ARGUMENT)
        self._borrowed_arguments[source_name] = cname
        if tracker_owned:
            self._tracker_owned_arguments.add(source_name)

    def bind_extension_runtime_owners(self, receiver_cname):
        if self._extension_runtime_receiver_cname not in (None, receiver_cname):
            raise AssertionError("extension runtime receiver changed")
        self._extension_runtime_receiver_cname = receiver_cname

    def ensure_extension_runtime_owners(self, node=None):
        """Return only after both the default owner and module handle exist."""
        if self.module_cname is not None and self.default_owner_cname is not None:
            return
        receiver_cname = self._extension_runtime_receiver_cname
        if receiver_cname is None:
            if node is None:
                raise AssertionError("extension runtime owners are unavailable")
            self.unsupported(
                node, "operation requires the current module/type owner")
        type_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                receiver_cname,
                UniversalHPyModuleWriter._c_string("__class__"),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(type_cname)
        self.default_owner_cname = type_cname
        module_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                type_cname,
                UniversalHPyModuleWriter._c_string(
                    UniversalHPyModuleWriter.MODULE_ATTRIBUTE),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(module_cname)
        self.module_cname = module_cname

    def _extension_field_storage(self, entry):
        if entry is None:
            return None
        storage = self.extension_field_layout.get(id(entry))
        if storage is None:
            storage = self.extension_field_layout.get(("field", entry.name))
        return storage

    def is_extension_field(self, node):
        entry = getattr(node, "entry", None)
        return self._extension_field_storage(entry) is not None

    def _materialize_extension_field_owner(self, field_node):
        struct_cname, field_cname, _ = self._extension_field_storage(
            field_node.entry)
        # Incoming arguments remain valid for the complete call.  Owned locals
        # are intentionally materialized: a side-effectful field-store RHS may
        # rebind and close such a local after receiver evaluation.
        owner_cname = self.borrow_direct_named_value(
            field_node.obj, borrowed_arguments_only=True)
        if owner_cname is None:
            owner_cname = self.materialize_owned_handle(
                field_node.obj.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(owner_cname)
        data_cname = "__pyx_hpy_field_owner_%d" % self._next_field_owner
        self._next_field_owner += 1
        self.putln("%s *%s = %s_AsStruct(%s, %s);" % (
            struct_cname,
            data_cname,
            struct_cname,
            self.context_cname,
            owner_cname,
        ))
        return owner_cname, "%s->%s" % (data_cname, field_cname)

    def _close_extension_field_owner(self, owner_cname):
        owner = self._handle_temps.use(owner_cname)
        if owner.ownership is HandleOwnership.OWNED:
            self.close_owned_handle(owner_cname)

    def _load_extension_field_value(self, owner_cname, field_cname):
        result_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        self.putln("if (HPyField_IsNull(%s)) {" % field_cname)
        self.indent()
        self.putln("%s = %s;" % (
            result_cname,
            self.runtime_api.duplicate_reference(
                self.runtime_api.context_constant(
                    RuntimeContextConstant.NONE,
                    context_cname=self.context_cname,
                ),
                context_cname=self.context_cname,
            ),
        ))
        self.dedent()
        self.putln("} else {")
        self.indent()
        self.putln("%s = %s;" % (
            result_cname,
            self.runtime_api.field_load(
                owner_cname, field_cname, context_cname=self.context_cname),
        ))
        self.dedent()
        self.putln("}")
        self.put_error_return_if_null(result_cname)
        return result_cname

    def load_extension_field(self, field_node):
        _, _, storage_kind = self._extension_field_storage(field_node.entry)
        owner_cname, field_cname = self._materialize_extension_field_owner(
            field_node)
        if storage_kind == "object":
            result_cname = self._load_extension_field_value(
                owner_cname, field_cname)
        elif storage_kind == "bint":
            result_cname = self.allocate_owned_handle(
                self.runtime_api.duplicate_reference(
                    "%s ? %s : %s" % (
                        field_cname,
                        self.runtime_api.context_constant(
                            RuntimeContextConstant.TRUE,
                            context_cname=self.context_cname),
                        self.runtime_api.context_constant(
                            RuntimeContextConstant.FALSE,
                            context_cname=self.context_cname),
                    ),
                    context_cname=self.context_cname,
                ))
            self.put_error_return_if_null(result_cname)
        elif (storage_kind.startswith("signed-")
              or storage_kind in ("char", "py-ssize")):
            result_cname = self.allocate_owned_handle(
                self.runtime_api.signed_integer_from_cvalue(
                    field_cname, context_cname=self.context_cname))
            self.put_error_return_if_null(result_cname)
        elif storage_kind.startswith("unsigned-"):
            result_cname = self.allocate_owned_handle(
                self.runtime_api.unsigned_integer_from_cvalue(
                    field_cname, context_cname=self.context_cname))
            self.put_error_return_if_null(result_cname)
        elif storage_kind in ("float", "double", "long-double"):
            result_cname = self.allocate_owned_handle(
                self.runtime_api.floating_from_cvalue(
                    field_cname, context_cname=self.context_cname))
            self.put_error_return_if_null(result_cname)
        else:
            raise AssertionError("unknown extension field storage kind")
        self._close_extension_field_owner(owner_cname)
        return result_cname

    def generate_external_c_scalar_call(self, call_node):
        """Call one declaration admitted by the strict extern-C validator."""
        if call_node.self is not None or call_node.coerced_self is not None:
            self.unsupported(
                call_node,
                "external C method receiver injection is not implemented",
            )
        if call_node.args is None:
            self.unsupported(
                call_node,
                "expanded external C call arguments are not implemented",
            )
        entry = getattr(call_node.function, "entry", None)
        storage_kind = getattr(
            entry, "ahpy_universal_external_c_scalar_kind", None)
        if storage_kind is None:
            self.unsupported(
                call_node,
                "only external C functions validated by a concrete, "
                "Python-independent header may be called",
            )
        function_cname = str(entry.cname)
        if not self.is_c_identifier(function_cname):
            self.unsupported(
                call_node,
                "external C function names must be plain C identifiers",
            )
        argument_kinds = getattr(
            entry, "ahpy_universal_external_c_argument_kinds", None)
        if argument_kinds is None or len(argument_kinds) != len(call_node.args):
            raise AssertionError("validated external C signature changed")
        argument_handles = []
        native_arguments = []
        for argument, argument_kind in zip(call_node.args, argument_kinds):
            while isinstance(
                argument,
                (ExprNodes.CoerceFromPyTypeNode, ExprNodes.CoerceToTempNode),
            ):
                argument = argument.arg
            literal_argument = self._render_external_c_scalar_literal(
                argument, argument_kind)
            if literal_argument is not None:
                native_arguments.append(literal_argument)
                continue
            argument_cname = self.materialize_owned_handle(
                argument.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(argument_cname)
            argument_handles.append(argument_cname)
            native_arguments.append(
                self._convert_native_scalar_handle(
                    argument_kind, argument_cname))
        call_expression = "%s(%s)" % (
            function_cname, ", ".join(native_arguments))
        errno_sentinel = getattr(
            entry, "ahpy_universal_external_c_errno_sentinel", None)
        if errno_sentinel is None:
            result_cname = self._box_external_c_scalar_result(
                storage_kind, call_expression)
        else:
            native_result_cname = "__pyx_hpy_external_result_%d" % (
                self._next_native_field)
            self._next_native_field += 1
            saved_errno_cname = "__pyx_hpy_external_errno_%d" % (
                self._next_status)
            self._next_status += 1
            self.putln("%s %s;" % (
                self._external_c_scalar_c_type(storage_kind),
                native_result_cname,
            ))
            self.putln("int %s;" % saved_errno_cname)
            self.putln("errno = 0;")
            self.putln("%s = %s;" % (
                native_result_cname, call_expression))
            self.putln("%s = errno;" % saved_errno_cname)
            self._emit_external_c_errno_failure(
                entry,
                storage_kind,
                native_result_cname,
                saved_errno_cname,
            )
            result_cname = self._box_external_c_scalar_result(
                storage_kind, native_result_cname)
        for argument_cname in reversed(argument_handles):
            self.close_owned_handle(argument_cname)
        return result_cname

    def _emit_external_c_errno_failure(
        self,
        entry,
        storage_kind,
        native_result_cname,
        saved_errno_cname,
    ):
        errno_sentinel = entry.ahpy_universal_external_c_errno_sentinel
        sentinel_expression = "((%s)%s)" % (
            self._external_c_scalar_c_type(storage_kind),
            errno_sentinel,
        )
        self.putln("if (%s == %s) {" % (
            native_result_cname, sentinel_expression))
        self.indent()
        self.putln("if (%s != 0) {" % saved_errno_cname)
        self.indent()
        self.putln("errno = %s;" % saved_errno_cname)
        self.putln("(void)%s;" % self.runtime_api.error_set_from_errno(
            self.runtime_api.builtin_exception(
                "OSError", context_cname=self.context_cname),
            context_cname=self.context_cname,
        ))
        self.dedent()
        self.putln("} else {")
        self.indent()
        message = UniversalHPyModuleWriter._c_string(
            "external C function '%s' returned its -1 error sentinel "
            "without setting errno" % entry.name)
        self.putln("%s;" % self.runtime_api.error_set_string(
            self.runtime_api.builtin_exception(
                "RuntimeError", context_cname=self.context_cname),
            message,
            context_cname=self.context_cname,
        ))
        self.dedent()
        self.putln("}")
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")

    def _box_external_c_scalar_result(self, storage_kind, native_expression):
        if storage_kind == "bint":
            expression = self.runtime_api.duplicate_reference(
                "%s ? %s : %s" % (
                    native_expression,
                    self.runtime_api.context_constant(
                        RuntimeContextConstant.TRUE,
                        context_cname=self.context_cname,
                    ),
                    self.runtime_api.context_constant(
                        RuntimeContextConstant.FALSE,
                        context_cname=self.context_cname,
                    ),
                ),
                context_cname=self.context_cname,
            )
        elif storage_kind == "py-ssize":
            expression = self.runtime_api.ssize_integer_from_cvalue(
                native_expression, context_cname=self.context_cname)
        elif storage_kind.startswith("signed-") or storage_kind == "char":
            expression = self.runtime_api.signed_integer_from_cvalue(
                native_expression, context_cname=self.context_cname)
        elif storage_kind.startswith("unsigned-"):
            expression = self.runtime_api.unsigned_integer_from_cvalue(
                native_expression, context_cname=self.context_cname)
        elif storage_kind in ("float", "double", "long-double"):
            expression = self.runtime_api.floating_from_cvalue(
                native_expression, context_cname=self.context_cname)
        else:
            raise AssertionError(
                "unknown validated external C scalar kind %r" % storage_kind)
        result_cname = self.allocate_owned_handle(expression)
        self.put_error_return_if_null(result_cname)
        return result_cname

    @staticmethod
    def _external_c_scalar_c_type(storage_kind):
        return {
            "bint": "char",
            "char": "char",
            "signed-char": "signed char",
            "unsigned-char": "unsigned char",
            "signed-short": "short",
            "unsigned-short": "unsigned short",
            "signed-int": "int",
            "unsigned-int": "unsigned int",
            "signed-long": "long",
            "unsigned-long": "unsigned long",
            "signed-long-long": "long long",
            "unsigned-long-long": "unsigned long long",
            "float": "float",
            "double": "double",
            "long-double": "long double",
        }[storage_kind]

    @staticmethod
    def _external_c_scalar_literal_value(node):
        """Return a side-effect-free Python numeric literal, if ``node`` is one.

        The caller still validates the value against the exact C destination.
        Keeping extraction separate from rendering prevents an AST constant
        from silently inheriting the host compiler's integer-width choices.
        """
        if isinstance(node, ExprNodes.BoolNode):
            return node.value
        if isinstance(node, ExprNodes.CharNode):
            return ord(node.value)
        if isinstance(node, ExprNodes.IntNode):
            try:
                return int(node.value, 0)
            except (TypeError, ValueError):
                return None
        if isinstance(node, ExprNodes.FloatNode):
            try:
                return float(node.value)
            except (TypeError, ValueError):
                return None
        if isinstance(node, (ExprNodes.UnaryPlusNode, ExprNodes.UnaryMinusNode)):
            value = UniversalHPyFunctionWriter._external_c_scalar_literal_value(
                node.operand)
            if value is None:
                return None
            return value if isinstance(node, ExprNodes.UnaryPlusNode) else -value
        return None

    @staticmethod
    def _render_external_c_scalar_literal(node, storage_kind):
        """Render a portable C scalar literal or require checked HPy conversion.

        Only values representable on every supported C data model take this
        zero-handle path.  Wider or otherwise ambiguous values deliberately
        fall back to HPy's checked conversions so overflow behaviour remains
        observable instead of becoming implementation-defined C conversion.
        """
        value = UniversalHPyFunctionWriter._external_c_scalar_literal_value(node)
        if value is None:
            return None

        if storage_kind in ("float", "double", "long-double"):
            if isinstance(value, bool):
                value = int(value)
            try:
                numeric_value = float(value)
            except (OverflowError, ValueError):
                return None
            if not math.isfinite(numeric_value):
                return None
            literal = repr(numeric_value)
            c_type = {
                "float": "float",
                "double": "double",
                "long-double": "long double",
            }[storage_kind]
            return "((%s)%s)" % (c_type, literal)

        if isinstance(value, bool):
            value = int(value)
        if not isinstance(value, int):
            return None
        if storage_kind == "bint":
            return "1" if value else "0"

        portable_ranges = {
            # Plain char signedness is implementation-defined.  Restricting it
            # to the common non-negative subset keeps the literal portable.
            "char": (0, (1 << 7) - 1, "char"),
            "signed-char": (-(1 << 7), (1 << 7) - 1, "signed char"),
            "unsigned-char": (0, (1 << 8) - 1, "unsigned char"),
            "signed-short": (-(1 << 15), (1 << 15) - 1, "short"),
            "unsigned-short": (0, (1 << 16) - 1, "unsigned short"),
            "signed-int": (-(1 << 31), (1 << 31) - 1, "int"),
            "unsigned-int": (0, (1 << 32) - 1, "unsigned int"),
            # C guarantees at least 32 bits for long, not the LP64 width.
            "signed-long": (-(1 << 31), (1 << 31) - 1, "long"),
            "unsigned-long": (0, (1 << 32) - 1, "unsigned long"),
            "signed-long-long": (
                -(1 << 63), (1 << 63) - 1, "long long"),
            "unsigned-long-long": (
                0, (1 << 64) - 1, "unsigned long long"),
        }
        literal_range = portable_ranges.get(storage_kind)
        if literal_range is None:
            return None
        minimum, maximum, c_type = literal_range
        if not minimum <= value <= maximum:
            return None
        if value == -(1 << 63):
            literal = "(-9223372036854775807LL - 1LL)"
        elif storage_kind == "signed-long-long":
            literal = "%sLL" % value
        elif storage_kind == "unsigned-long-long":
            literal = "%sULL" % value
        elif storage_kind.startswith("unsigned-"):
            literal = "%sULL" % value
        else:
            literal = str(value)
        return "((%s)%s)" % (c_type, literal)

    def generate_nogil_external_c_block(self, gil_node):
        """Emit the first strictly Python-independent ``with nogil`` slice."""
        if gil_node.state != "nogil":
            self.unsupported(
                gil_node,
                "with gil blocks are not implemented in Universal HPy mode",
            )
        if gil_node.condition is not None:
            self.unsupported(
                gil_node,
                "conditional with nogil blocks are not implemented; the "
                "HPy execution-state transition must be unconditional",
            )

        emitted_calls = 0
        for statement in self.stats(gil_node.body):
            if isinstance(statement, Nodes.ParallelStatNode):
                self.reject_parallel_construct(statement)
            if type(statement) is Nodes.GILStatNode:
                if (
                    statement.state != "gil"
                    or statement.internally_generated
                ):
                    self.unsupported(
                        statement,
                        "only an explicit with gil block may interrupt the "
                        "Universal HPy with nogil external-C lane",
                    )
                if statement.condition is not None:
                    self.unsupported(
                        statement,
                        "conditional with gil blocks are not implemented in "
                        "the Universal HPy with nogil lane",
                    )
                gil_body = self.stats(statement.body)
                if not gil_body:
                    self.unsupported(
                        statement,
                        "empty nested with gil blocks are not part of the "
                        "Universal HPy execution-state slice",
                    )
                self.putln(
                    "/* explicit with gil: Python execution is active between "
                    "native intervals */")
                for gil_statement in gil_body:
                    gil_statement.generate_hpy_bootstrap_execution_code(self)
                continue
            result_target = None
            if type(statement) is Nodes.ExprStatNode:
                expression = statement.expr
            elif type(statement) is Nodes.SingleAssignmentNode:
                if (
                    not isinstance(
                        statement.lhs,
                        (
                            ExprNodes.NameNode,
                            ExprNodes.AttributeNode,
                            ExprNodes.IndexNode,
                            ExprNodes.SliceIndexNode,
                        ),
                    )
                    or not statement.lhs.type.is_pyobject
                ):
                    self.unsupported(
                        statement.lhs,
                        "used with nogil results require a Python name, "
                        "attribute, item, or slice target",
                    )
                result_target = statement.lhs
                expression = statement.rhs
            else:
                self.unsupported(
                    statement,
                    "the with nogil lane permits only discarded calls or "
                    "assignments to supported Python targets from validated "
                    "external C functions",
                )
            while isinstance(
                expression,
                (
                    ExprNodes.CoerceFromPyTypeNode,
                    ExprNodes.CoerceToPyTypeNode,
                    ExprNodes.CoerceToTempNode,
                ),
            ):
                expression = expression.arg
            if not isinstance(expression, ExprNodes.SimpleCallNode):
                self.unsupported(
                    statement,
                    "the with nogil lane permits only discarded calls or "
                    "assignments to supported Python targets from validated "
                    "external C functions",
                )
            if expression.self is not None or expression.coerced_self is not None:
                self.unsupported(
                    expression,
                    "external C method calls are not implemented inside "
                    "with nogil",
                )
            if expression.args is None:
                self.unsupported(
                    expression,
                    "expanded external C call arguments are not implemented "
                    "inside with nogil",
                )
            entry = getattr(expression.function, "entry", None)
            function_type = getattr(entry, "type", None)
            if getattr(
                entry, "ahpy_universal_external_c_scalar_kind", None
            ) is None:
                self.unsupported(
                    expression,
                    "with nogil may call only external C functions validated "
                    "by a concrete, Python-independent header",
                )
            if function_type is None or not function_type.nogil:
                self.unsupported(
                    expression,
                    "external C calls inside with nogil must be declared nogil",
                )
            if (
                function_type.exception_value is not None
                or function_type.exception_check
            ) and getattr(
                entry, "ahpy_universal_external_c_errno_sentinel", None
            ) is None:
                self.unsupported(
                    expression,
                    "external C calls inside with nogil must be noexcept or use "
                    "the exact signed except -1 errno contract; Python exception "
                    "inspection requires active execution state",
                )
            function_cname = str(entry.cname)
            if not self.is_c_identifier(function_cname):
                self.unsupported(
                    expression,
                    "external C function names must be plain C identifiers",
                )
            argument_kinds = getattr(
                entry, "ahpy_universal_external_c_argument_kinds", None)
            if (
                argument_kinds is None
                or len(argument_kinds) != len(expression.args)
            ):
                raise AssertionError(
                    "validated external C signature changed inside with nogil")
            native_arguments = []
            for argument, argument_kind in zip(
                    expression.args, argument_kinds):
                while isinstance(
                    argument,
                    (
                        ExprNodes.CoerceFromPyTypeNode,
                        ExprNodes.CoerceToTempNode,
                    ),
                ):
                    argument = argument.arg
                literal_argument = self._render_external_c_scalar_literal(
                    argument, argument_kind)
                if literal_argument is not None:
                    native_arguments.append(literal_argument)
                    continue
                argument_cname = self.materialize_owned_handle(
                    argument.generate_hpy_bootstrap_owned_result(self))
                self.put_error_return_if_null(argument_cname)
                native_arguments.append(self._convert_native_scalar_handle(
                    argument_kind, argument_cname))
                self.close_owned_handle(argument_cname)
            call_expression = "%s(%s)" % (
                function_cname, ", ".join(native_arguments))
            errno_sentinel = getattr(
                entry, "ahpy_universal_external_c_errno_sentinel", None)
            native_result_cname = None
            if result_target is not None or errno_sentinel is not None:
                native_result_cname = "__pyx_hpy_nogil_result_%d" % (
                    self._next_native_field)
                self._next_native_field += 1
                self.putln("%s %s;" % (
                    self._external_c_scalar_c_type(
                        getattr(
                            entry,
                            "ahpy_universal_external_c_scalar_kind",
                        )),
                    native_result_cname,
                ))
            saved_errno_cname = None
            if errno_sentinel is not None:
                saved_errno_cname = "__pyx_hpy_nogil_errno_%d" % (
                    self._next_status)
                self._next_status += 1
                self.putln("int %s;" % saved_errno_cname)
            thread_state_cname = "__pyx_hpy_thread_state_%d" % (
                self._next_thread_state)
            self._next_thread_state += 1
            self.putln("{")
            self.indent()
            self.putln("%s %s = %s;" % (
                self.runtime_api.execution_state_type_cname(),
                thread_state_cname,
                self.runtime_api.leave_python_execution(
                    context_cname=self.context_cname),
            ))
            if errno_sentinel is not None:
                self.putln("errno = 0;")
            if native_result_cname is None:
                self.putln("(void)%s;" % call_expression)
            else:
                self.putln("%s = %s;" % (
                    native_result_cname, call_expression))
            if saved_errno_cname is not None:
                self.putln("%s = errno;" % saved_errno_cname)
            self.putln("%s;" % self.runtime_api.reenter_python_execution(
                thread_state_cname, context_cname=self.context_cname))
            self.dedent()
            self.putln("}")
            if errno_sentinel is not None:
                self._emit_external_c_errno_failure(
                    entry,
                    getattr(
                        entry, "ahpy_universal_external_c_scalar_kind"),
                    native_result_cname,
                    saved_errno_cname,
                )
            if result_target is not None:
                result_cname = self._box_external_c_scalar_result(
                    getattr(
                        entry, "ahpy_universal_external_c_scalar_kind"),
                    native_result_cname,
                )
                self.assign_target_from_owned_cname(
                    result_target, result_cname)
            emitted_calls += 1

        if not emitted_calls:
            self.unsupported(
                gil_node,
                "empty with nogil blocks are not part of the initial "
                "Universal HPy execution-state slice",
            )

    def reject_parallel_construct(self, node):
        self.unsupported(
            node,
            "prange/parallel requires backend-neutral scheduling and "
            "reduction IR plus a public HPy worker-thread attach and error-"
            "transport contract; HPy 0.9 only pairs Leave/Reenter on the "
            "originating thread, and CPython PyThreadState/exception triples "
            "are forbidden in Universal mode",
        )

    def assign_extension_field(self, field_node, value):
        _, _, storage_kind = self._extension_field_storage(field_node.entry)
        if storage_kind != "object":
            inplace_value = (
                value.arg
                if isinstance(value, ExprNodes.CoerceFromPyTypeNode)
                and getattr(value.arg, "inplace", False)
                else None
            )
            python_operations = {
                "/": RuntimeInPlaceOperation.TRUE_DIVIDE,
                "//": RuntimeInPlaceOperation.FLOOR_DIVIDE,
                "%": RuntimeInPlaceOperation.REMAINDER,
                "**": RuntimeInPlaceOperation.POWER,
            }
            python_operation = (
                python_operations.get(inplace_value.operator)
                if inplace_value is not None else None
            )
            if python_operation is not None:
                self.inplace_extension_field(
                    field_node, python_operation, inplace_value.operand2)
                return
            owner_cname, field_cname = (
                self._materialize_extension_field_owner(field_node))
            self._assign_native_extension_field(
                owner_cname, field_cname, storage_kind, value)
            return
        owner_cname, field_cname = self._materialize_extension_field_owner(
            field_node)
        value_cname = self.borrow_direct_named_value(value)
        value_is_owned = value_cname is None
        if value_cname is None:
            value_cname = self.materialize_owned_handle(
                value.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(value_cname)
        self.use_owned_handles(owner_cname, value_cname)
        self.putln("%s;" % self.runtime_api.field_store(
            owner_cname,
            field_cname,
            value_cname,
            context_cname=self.context_cname,
        ))
        if value_is_owned:
            self.close_owned_handle(value_cname)
        self._close_extension_field_owner(owner_cname)

    def _assign_native_extension_field(
            self, owner_cname, field_cname, storage_kind, value):
        inplace_value = (
            value.arg
            if isinstance(value, ExprNodes.CoerceFromPyTypeNode)
            and getattr(value.arg, "inplace", False)
            else None
        )
        if inplace_value is not None:
            if storage_kind == "bint":
                self.unsupported(
                    inplace_value,
                    "bint extension-field in-place operators require a "
                    "separate canonicalization gate",
                )
            operators = {
                "+": "+=", "-": "-=", "*": "*=",
                "&": "&=", "|": "|=", "^": "^=",
                "<<": "<<=", ">>": ">>=",
            }
            operator = operators.get(inplace_value.operator)
            if operator is None:
                self.unsupported(
                    inplace_value,
                    "native C extension fields currently support only "
                    "+=, -=, *=, &=, |=, ^=, <<=, and >>= in-place operations",
                )
            value_cname, native_value = (
                self._convert_native_extension_field_value(
                    owner_cname, storage_kind, inplace_value.operand2))
            self.putln("%s %s %s;" % (
                field_cname, operator, native_value))
            self.close_owned_handle(value_cname)
            self._close_extension_field_owner(owner_cname)
            return
        value_cname, native_value = self._convert_native_extension_field_value(
            owner_cname, storage_kind, value)
        self.putln("%s = %s;" % (field_cname, native_value))
        self.close_owned_handle(value_cname)
        self._close_extension_field_owner(owner_cname)

    def _convert_native_extension_field_value(
            self, owner_cname, storage_kind, value):
        while isinstance(value, (ExprNodes.CoerceFromPyTypeNode,
                                 ExprNodes.CoerceToTempNode)):
            value = value.arg
        value_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        native_value = self._convert_native_scalar_handle(
            storage_kind, value_cname, cleanup_owner_cname=owner_cname)
        return value_cname, native_value

    def _convert_native_scalar_handle(
            self, storage_kind, value_cname, cleanup_owner_cname=None):
        if cleanup_owner_cname is None:
            self.use_owned_handles(value_cname)
        else:
            self.use_owned_handles(cleanup_owner_cname, value_cname)
        native_index = self._next_native_field
        self._next_native_field += 1
        signed_long_types = {
            "char": ("char", "CHAR_MIN", "CHAR_MAX"),
            "signed-char": ("signed char", "SCHAR_MIN", "SCHAR_MAX"),
            "signed-short": ("short", "SHRT_MIN", "SHRT_MAX"),
            "signed-int": ("int", "INT_MIN", "INT_MAX"),
            "signed-long": ("long", None, None),
        }
        unsigned_long_types = {
            "unsigned-char": ("unsigned char", "UCHAR_MAX"),
            "unsigned-short": ("unsigned short", "USHRT_MAX"),
            "unsigned-int": ("unsigned int", "UINT_MAX"),
            "unsigned-long": ("unsigned long", None),
        }
        if storage_kind == "bint":
            native_cname = "__pyx_hpy_native_bool_%d" % native_index
            self.putln("int %s = %s;" % (
                native_cname,
                self.runtime_api.truth_test(
                    value_cname, context_cname=self.context_cname),
            ))
            self.put_error_return_if_negative(native_cname)
            native_value = "(char)(%s != 0)" % native_cname
        elif storage_kind == "py-ssize":
            native_cname = "__pyx_hpy_native_ssize_%d" % native_index
            self.putln("HPy_ssize_t %s = %s;" % (
                native_cname,
                self.runtime_api.ssize_t_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure("(%s == -1) && %s" % (
                native_cname,
                self.runtime_api.python_error_occurred(
                    context_cname=self.context_cname),
            ))
            native_value = native_cname
        elif storage_kind in signed_long_types:
            target_type, minimum, maximum = signed_long_types[storage_kind]
            native_cname = "__pyx_hpy_native_long_%d" % native_index
            self.putln("long %s = %s;" % (
                native_cname,
                self.runtime_api.signed_long_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure("(%s == -1) && %s" % (
                native_cname,
                self.runtime_api.python_error_occurred(
                    context_cname=self.context_cname),
            ))
            if minimum is not None:
                self._put_native_range_failure(
                    "(%s < %s) || (%s > %s)" % (
                        native_cname, minimum, native_cname, maximum),
                    target_type,
                )
            native_value = "(%s)%s" % (target_type, native_cname)
        elif storage_kind == "signed-long-long":
            native_cname = "__pyx_hpy_native_long_long_%d" % native_index
            self.putln("long long %s = %s;" % (
                native_cname,
                self.runtime_api.signed_long_long_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure("(%s == -1) && %s" % (
                native_cname,
                self.runtime_api.python_error_occurred(
                    context_cname=self.context_cname),
            ))
            native_value = native_cname
        elif storage_kind in unsigned_long_types:
            target_type, maximum = unsigned_long_types[storage_kind]
            native_cname = "__pyx_hpy_native_unsigned_long_%d" % native_index
            self.putln("unsigned long %s = %s;" % (
                native_cname,
                self.runtime_api.unsigned_long_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure(
                "(%s == (unsigned long)-1) && %s" % (
                    native_cname,
                    self.runtime_api.python_error_occurred(
                        context_cname=self.context_cname),
                ))
            if maximum is not None:
                self._put_native_range_failure(
                    "%s > %s" % (native_cname, maximum), target_type)
            native_value = "(%s)%s" % (target_type, native_cname)
        elif storage_kind == "unsigned-long-long":
            native_cname = "__pyx_hpy_native_unsigned_long_long_%d" % native_index
            self.putln("unsigned long long %s = %s;" % (
                native_cname,
                self.runtime_api.unsigned_long_long_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure(
                "(%s == (unsigned long long)-1) && %s" % (
                    native_cname,
                    self.runtime_api.python_error_occurred(
                        context_cname=self.context_cname),
                ))
            native_value = native_cname
        elif storage_kind in ("float", "double", "long-double"):
            native_cname = "__pyx_hpy_native_double_%d" % native_index
            self.putln("double %s = %s;" % (
                native_cname,
                self.runtime_api.double_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure("(%s == -1.0) && %s" % (
                native_cname,
                self.runtime_api.python_error_occurred(
                    context_cname=self.context_cname),
            ))
            native_value = (
                "(float)%s" % native_cname
                if storage_kind == "float" else
                "(long double)%s" % native_cname
                if storage_kind == "long-double" else native_cname)
        else:
            raise AssertionError("unknown native extension field storage kind")
        return native_value

    def _put_native_conversion_failure(self, condition):
        self.putln("if (%s) {" % condition)
        self.indent()
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")

    def _put_native_range_failure(self, condition, target_type):
        self.putln("if (%s) {" % condition)
        self.indent()
        self.putln("%s;" % self.runtime_api.error_set_string(
            self.runtime_api.builtin_exception(
                "OverflowError", context_cname=self.context_cname),
            '"value too large to convert to C %s"' % target_type,
            context_cname=self.context_cname,
        ))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")

    def inplace_extension_field(self, field_node, operation, value):
        storage_kind = self._extension_field_storage(field_node.entry)[2]
        python_result_operations = {
            RuntimeInPlaceOperation.TRUE_DIVIDE,
            RuntimeInPlaceOperation.FLOOR_DIVIDE,
            RuntimeInPlaceOperation.REMAINDER,
            RuntimeInPlaceOperation.POWER,
        }
        if storage_kind != "object" and operation in python_result_operations:
            if storage_kind == "bint":
                self.unsupported(
                    field_node,
                    "bint extension-field in-place operators require a "
                    "separate canonicalization gate",
                )
            current_cname = self.load_extension_field(field_node)
            result_cname = self._generate_inplace_result(
                operation, current_cname, value)
            self.close_owned_handle(current_cname)
            owner_cname, field_cname = self._materialize_extension_field_owner(
                field_node)
            native_value = self._convert_native_scalar_handle(
                storage_kind,
                result_cname,
                cleanup_owner_cname=owner_cname,
            )
            self.putln("%s = %s;" % (field_cname, native_value))
            self.close_owned_handle(result_cname)
            self._close_extension_field_owner(owner_cname)
            return
        owner_cname, field_cname = self._materialize_extension_field_owner(
            field_node)
        if storage_kind != "object":
            operators = {
                RuntimeInPlaceOperation.ADD: "+=",
                RuntimeInPlaceOperation.SUBTRACT: "-=",
                RuntimeInPlaceOperation.MULTIPLY: "*=",
                RuntimeInPlaceOperation.BITWISE_AND: "&=",
                RuntimeInPlaceOperation.BITWISE_OR: "|=",
                RuntimeInPlaceOperation.BITWISE_XOR: "^=",
                RuntimeInPlaceOperation.LEFT_SHIFT: "<<=",
                RuntimeInPlaceOperation.RIGHT_SHIFT: ">>=",
            }
            operator = operators.get(operation)
            if operator is None:
                self.unsupported(
                    field_node,
                    "native C extension fields currently support only "
                    "+=, -=, *=, &=, |=, ^=, <<=, and >>= in-place operations",
                )
            value_cname, native_value = (
                self._convert_native_extension_field_value(
                    owner_cname, storage_kind, value))
            self.putln("%s %s %s;" % (
                field_cname, operator, native_value))
            self.close_owned_handle(value_cname)
            self._close_extension_field_owner(owner_cname)
            return
        current_cname = self._load_extension_field_value(
            owner_cname, field_cname)
        result_cname = self._generate_inplace_result(
            operation, current_cname, value)
        self.close_owned_handle(current_cname)
        self.use_owned_handles(owner_cname, result_cname)
        self.putln("%s;" % self.runtime_api.field_store(
            owner_cname,
            field_cname,
            result_cname,
            context_cname=self.context_cname,
        ))
        self.close_owned_handle(result_cname)
        self._close_extension_field_owner(owner_cname)

    def duplicate_named_value(self, node, source_name):
        allow_null = bool(getattr(node, "allow_null", False))
        closure_value = self._duplicate_closure_capture(node, source_name)
        if closure_value is not None:
            return closure_value
        cname = self._local_values.get(source_name)
        if cname is None:
            cname = self._borrowed_arguments.get(source_name)
        if cname is None:
            if allow_null:
                # Unassigned / deleted slot for ``locals()`` — omit from dict.
                return self.runtime_api.null_reference_value()
            entry = getattr(node, "entry", None)
            if self.name_registry is None or entry is None:
                self.unsupported(
                    node, "name %s has no initialized local HPy value" % source_name)
            if entry.is_builtin or entry.scope.is_builtin_scope:
                self.name_registry.require_builtin(source_name)
                self.ensure_extension_runtime_owners(node)
                builtins_cname = self.allocate_owned_handle(
                    self.runtime_api.attribute_get_string(
                        self.module_cname,
                        UniversalHPyModuleWriter._c_string(
                            UniversalHPyModuleWriter.BUILTINS_ATTRIBUTE),
                        context_cname=self.context_cname,
                    ))
                self.put_error_return_if_null(builtins_cname)
                self._handle_temps.use(builtins_cname)
                result_cname = self.allocate_owned_handle(
                    self.runtime_api.attribute_get_string(
                        builtins_cname,
                        UniversalHPyModuleWriter._c_string(source_name),
                        context_cname=self.context_cname,
                    ))
                self.close_owned_handle(builtins_cname)
                return result_cname
            elif entry.is_cclass_var_entry:
                self.name_registry.require_module_global(source_name)
                self.ensure_extension_runtime_owners(node)
                result_cname = self.allocate_owned_handle(
                    self.runtime_api.attribute_get_string(
                        self.module_cname,
                        UniversalHPyModuleWriter._c_string(source_name),
                        context_cname=self.context_cname,
                    ))
                self.put_error_return_if_null(result_cname)
                return result_cname
            elif entry.is_pyglobal:
                self.name_registry.require_module_global(source_name)
                self.ensure_extension_runtime_owners(node)
                return self.load_module_global(source_name)
            else:
                self.unsupported(
                    node, "name %s has no initialized local HPy value" % source_name)
        self._handle_temps.use(cname)
        if source_name in self._stable_local_slots:
            if allow_null:
                result_cname = self.allocate_owned_handle(
                    self.runtime_api.null_reference_value())
                self.putln("if (!%s) {" % self.runtime_api.null_check(cname))
                self.indent()
                self.putln("%s = %s;" % (
                    result_cname,
                    self.runtime_api.duplicate_reference(
                        cname, context_cname=self.context_cname),
                ))
                self.put_error_return_if_null(result_cname)
                self.dedent()
                self.putln("}")
                return result_cname
            # Deleted locals keep a stable slot set to HPy_NULL.
            self.putln("if (%s) {" % self.runtime_api.null_check(cname))
            self.indent()
            self._raise_unbound_local_error(source_name)
            self.dedent()
            self.putln("}")
        return self.runtime_api.duplicate_reference(
            cname, context_cname=self.context_cname)

    def borrow_direct_named_value(self, node, borrowed_arguments_only=False):
        """Return a live local/name handle for an API that only borrows it.

        Global, builtin, extension-field, and closure loads still require an
        owned materialization.  A stable local slot is checked for deletion
        before its handle is exposed.  Ownership remains with the argument
        frame/tracker or local lifetime and the ordinary failure epilogue.
        """
        if not isinstance(node, ExprNodes.NameNode):
            return None
        source_name = node.name
        cname = self._borrowed_arguments.get(source_name)
        if cname is None and not borrowed_arguments_only:
            cname = self._local_values.get(source_name)
        if cname is None:
            return None
        self._handle_temps.use(cname)
        if source_name in self._stable_local_slots:
            self.putln("if (%s) {" % self.runtime_api.null_check(cname))
            self.indent()
            self._raise_unbound_local_error(source_name)
            self.dedent()
            self.putln("}")
        return cname

    def load_cached_constant(self, node, fallback_expression):
        """Load an interpreter-owned constant or use its construction expression."""
        attribute_name = None
        if self.constant_registry is not None and self.use_constant_cache:
            attribute_name = self.constant_registry.attribute_for_node(node)
        if attribute_name is None:
            return fallback_expression
        self.ensure_extension_runtime_owners(node)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                self.module_cname,
                UniversalHPyModuleWriter._c_string(attribute_name),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(result_cname)
        return result_cname

    def load_cached_sequence(self, node):
        """Return a tracked cached tuple handle, or None for dynamic sequences."""
        if self.constant_registry is None or not self.use_constant_cache:
            return None
        attribute_name = self.constant_registry.attribute_for_node(node)
        if attribute_name is None:
            return None
        self.ensure_extension_runtime_owners(node)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                self.module_cname,
                UniversalHPyModuleWriter._c_string(attribute_name),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(result_cname)
        return result_cname

    def load_module_global(self, source_name):
        """Implement Python's module-then-builtins LOAD_GLOBAL semantics."""
        self.ensure_extension_runtime_owners()
        name_cname = UniversalHPyModuleWriter._c_string(source_name)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        has_module_value = self._emit_status_operation(
            self.runtime_api.attribute_has_string(
                self.module_cname, name_cname,
                context_cname=self.context_cname))
        self.putln("if (%s) {" % has_module_value)
        self.indent()
        module_value_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                self.module_cname, name_cname,
                context_cname=self.context_cname))
        self.put_error_return_if_null(module_value_cname)
        self._move_into_owned_slot(result_cname, module_value_cname)
        self.dedent()
        self.putln("} else {")
        self.indent()
        builtins_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                self.module_cname,
                UniversalHPyModuleWriter._c_string(
                    UniversalHPyModuleWriter.BUILTINS_ATTRIBUTE),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(builtins_cname)
        self._handle_temps.use(builtins_cname)
        has_builtin_value = self._emit_status_operation(
            self.runtime_api.attribute_has_string(
                builtins_cname, name_cname,
                context_cname=self.context_cname))
        self.putln("if (!%s) {" % has_builtin_value)
        self.indent()
        name_error = self.runtime_api.builtin_exception(
            "NameError", context_cname=self.context_cname)
        message = UniversalHPyModuleWriter._c_string(
            "name '%s' is not defined" % source_name)
        self.putln("%s;" % self.runtime_api.error_set_string(
            name_error, message, context_cname=self.context_cname))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")
        self._handle_temps.use(builtins_cname)
        fallback_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                builtins_cname, name_cname,
                context_cname=self.context_cname))
        self.put_error_return_if_null(fallback_cname)
        self.close_owned_handle(builtins_cname)
        self._move_into_owned_slot(result_cname, fallback_cname)
        self.dedent()
        self.putln("}")
        return result_cname

    def bind_temporary_value(self, node, cname):
        key = id(node)
        if key in self._temporary_values:
            raise AssertionError("bootstrap temporary is already bound")
        self._temporary_values[key] = cname

    def duplicate_temporary_value(self, node):
        cname = self._temporary_values.get(id(node))
        if cname is None:
            self.unsupported(node, "temporary HPy value is not bound")
        self._handle_temps.use(cname)
        return self.runtime_api.duplicate_reference(
            cname, context_cname=self.context_cname)

    def unbind_temporary_value(self, node):
        try:
            return self._temporary_values.pop(id(node))
        except KeyError:
            raise AssertionError("bootstrap temporary is not bound") from None

    def bind_integer_temporary(self, node, expression):
        """Bind a LetRef-style C integer temporary used by for-from bounds."""
        key = id(node)
        if key in self._c_temporary_values:
            raise AssertionError("bootstrap C temporary is already bound")
        cname = self._materialize_ssize_expression(expression)
        self._c_temporary_values[key] = cname
        node.result_code = cname
        return cname

    def unbind_integer_temporary(self, node):
        try:
            return self._c_temporary_values.pop(id(node))
        except KeyError:
            raise AssertionError("bootstrap C temporary is not bound") from None

    def assign_local(self, node, source_name, value):
        cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(cname)
        self.assign_local_from_owned_cname(source_name, cname)

    def assign_local_from_owned_cname(self, source_name, cname):
        if (
            self._closure_env_owner_cname is not None
            and source_name in self._closure_in_closure_names
        ):
            self._store_closure_capture(source_name, cname)
            return
        if source_name in self._stable_local_slots:
            self._move_into_owned_slot(self._local_values[source_name], cname)
            return
        previous = self._local_values.get(source_name)
        if previous is not None:
            self.close_owned_handle(previous)
        self._local_values[source_name] = cname

    def assign_function_global(self, node, source_name, value):
        self.ensure_extension_runtime_owners(node)
        self.store_module_global(
            node, source_name, value, self.module_cname, publish=True)

    def _closure_capture_for_name(self, source_name):
        if self.closure_env_spec is None:
            return None
        for capture in self.closure_env_spec.captures:
            if capture.name == source_name:
                return capture
        return None

    def _duplicate_closure_capture(self, node, source_name):
        entry = getattr(node, "entry", None)
        if entry is None or self.closure_env_spec is None:
            return None
        if not (entry.from_closure or entry.in_closure):
            return None
        if self._closure_env_owner_cname is None:
            return None
        if entry.from_closure:
            capture_entry = entry.outer_entry
        else:
            capture_entry = entry
        capture = None
        for candidate in self.closure_env_spec.captures:
            if id(candidate.entry) == id(capture_entry):
                capture = candidate
                break
        if capture is None:
            return None
        owner_cname = self._closure_env_owner_cname
        self._handle_temps.use(owner_cname)
        data_cname = "__pyx_hpy_closure_data_%d" % self._next_field_owner
        self._next_field_owner += 1
        self.putln("%s *%s = %s_AsStruct(%s, %s);" % (
            self.closure_env_spec.struct_cname,
            data_cname,
            self.closure_env_spec.struct_cname,
            self.context_cname,
            owner_cname,
        ))
        return self._load_extension_field_value(
            owner_cname, "%s->%s" % (data_cname, capture.field_cname))

    def _store_closure_capture(self, source_name, value_cname):
        capture = self._closure_capture_for_name(source_name)
        if capture is None:
            raise AssertionError("unknown closure capture %s" % source_name)
        owner_cname = self._closure_env_owner_cname
        self._handle_temps.use(owner_cname)
        self._handle_temps.use(value_cname)
        data_cname = "__pyx_hpy_closure_data_%d" % self._next_field_owner
        self._next_field_owner += 1
        self.putln("%s *%s = %s_AsStruct(%s, %s);" % (
            self.closure_env_spec.struct_cname,
            data_cname,
            self.closure_env_spec.struct_cname,
            self.context_cname,
            owner_cname,
        ))
        field_cname = "%s->%s" % (data_cname, capture.field_cname)
        self.putln("%s;" % self.runtime_api.field_store(
            owner_cname,
            field_cname,
            value_cname,
            context_cname=self.context_cname,
        ))
        self.close_owned_handle(value_cname)

    def allocate_closure_env_and_store_captures(self, outer_def):
        if self.closure_registry is None:
            return
        env_spec = self.closure_registry.env_by_outer.get(id(outer_def))
        if env_spec is None:
            return
        self.ensure_extension_runtime_owners(outer_def)
        self.closure_env_spec = env_spec
        self._closure_in_closure_names = {
            capture.name for capture in env_spec.captures}
        env_type_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                self.module_cname,
                UniversalHPyModuleWriter._c_string(env_spec.module_global),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(env_type_cname)
        env_data_cname = "__pyx_hpy_closure_env_alloc_%d" % self._next_field_owner
        self._next_field_owner += 1
        self.putln("%s *%s;" % (env_spec.struct_cname, env_data_cname))
        env_owner_cname = self.allocate_owned_handle(
            "HPy_New(%s, %s, &%s)" % (
                self.context_cname,
                env_type_cname,
                env_data_cname,
            ))
        self.put_error_return_if_null(env_owner_cname)
        self.close_owned_handle(env_type_cname)
        self._closure_env_owner_cname = env_owner_cname
        # Store captures that are already live (typically args). Locals
        # assigned later update the shared env field via assign_local.
        for capture in env_spec.captures:
            source_cname = self._local_values.get(capture.name)
            if source_cname is None:
                source_cname = self._borrowed_arguments.get(capture.name)
            if source_cname is None:
                continue
            self._handle_temps.use(source_cname)
            value_cname = self.allocate_owned_handle(
                self.runtime_api.duplicate_reference(
                    source_cname, context_cname=self.context_cname))
            self.put_error_return_if_null(value_cname)
            self._store_closure_capture(capture.name, value_cname)

    def materialize_inner_function(self, inner_node):
        if self.closure_registry is None:
            self.unsupported(
                inner_node,
                "nested def closures are not available without a closure registry",
            )
        fn_spec = self.closure_registry.fn_by_inner_node.get(id(inner_node))
        if fn_spec is None:
            self.unsupported(
                inner_node,
                "nested def is not registered in the closure plan",
            )
        if self._closure_env_owner_cname is None:
            self.unsupported(
                inner_node,
                "nested def materialization requires an active closure env",
            )
        self.ensure_extension_runtime_owners(inner_node)
        fn_type_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                self.module_cname,
                UniversalHPyModuleWriter._c_string(fn_spec.module_global),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(fn_type_cname)
        fn_data_cname = "__pyx_hpy_closure_fn_alloc_%d" % self._next_field_owner
        self._next_field_owner += 1
        self.putln("%s *%s;" % (fn_spec.struct_cname, fn_data_cname))
        fn_owner_cname = self.allocate_owned_handle(
            "HPy_New(%s, %s, &%s)" % (
                self.context_cname,
                fn_type_cname,
                fn_data_cname,
            ))
        self.put_error_return_if_null(fn_owner_cname)
        self.close_owned_handle(fn_type_cname)
        self._handle_temps.use(self._closure_env_owner_cname)
        self._handle_temps.use(fn_owner_cname)
        env_field_cname = "%s->%s" % (fn_data_cname, fn_spec.env_field_cname)
        env_copy_cname = self.allocate_owned_handle(
            self.runtime_api.duplicate_reference(
                self._closure_env_owner_cname,
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(env_copy_cname)
        self.putln("%s;" % self.runtime_api.field_store(
            fn_owner_cname,
            env_field_cname,
            env_copy_cname,
            context_cname=self.context_cname,
        ))
        self.close_owned_handle(env_copy_cname)
        return fn_owner_cname

    def assign_unpacked_sequence(self, target, value):
        """Unpack ``value`` into a fixed or starred list/tuple assignment target."""
        sequence_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(sequence_cname)
        self._unpack_owned_sequence_into(target, sequence_cname)
        self.close_owned_handle(sequence_cname)

    def assign_target_from_owned_cname(self, target, value_cname):
        """Move an owned handle into a supported assignment target."""
        from . import ExprNodes
        from .StringEncoding import EncodedString

        if isinstance(target, ExprNodes.StarredUnpackingNode):
            target = target.target
        if isinstance(target, ExprNodes.NameNode):
            if target.entry is not None and target.entry.is_pyglobal:
                self.ensure_extension_runtime_owners(target)
                self.store_materialized_module_global(
                    target.name, value_cname, self.module_cname, publish=True)
            else:
                self.assign_local_from_owned_cname(target.name, value_cname)
            return
        if isinstance(target, (ExprNodes.TupleNode, ExprNodes.ListNode)):
            self._unpack_owned_sequence_into(target, value_cname)
            self.close_owned_handle(value_cname)
            return
        if isinstance(target, ExprNodes.AttributeNode):
            if self.is_extension_field(target):
                self.unsupported(
                    target, "extension-field unpack targets are not implemented")
            receiver_cname = self.materialize_owned_handle(
                target.obj.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(receiver_cname)
            self.use_owned_handles(receiver_cname, value_cname)
            status_cname = self._emit_status_operation(
                self.runtime_api.attribute_set_string(
                    receiver_cname,
                    EncodedString(target.attribute).as_c_string_literal(),
                    value_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(receiver_cname)
            self.close_owned_handle(value_cname)
            self.put_error_return_if_negative(status_cname)
            return
        if isinstance(target, (ExprNodes.IndexNode, ExprNodes.SliceIndexNode)):
            index = (
                target.index
                if isinstance(target, ExprNodes.IndexNode)
                else target.hpy_bootstrap_slice_node()
            )
            receiver_cname = self.materialize_owned_handle(
                target.base.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(receiver_cname)
            key_cname = self.materialize_owned_handle(
                index.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(key_cname)
            self.use_owned_handles(receiver_cname, key_cname, value_cname)
            status_cname = self._emit_status_operation(
                self.runtime_api.item_set(
                    receiver_cname, key_cname, value_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(value_cname)
            self.close_owned_handle(key_cname)
            self.close_owned_handle(receiver_cname)
            self.put_error_return_if_negative(status_cname)
            return
        self.unsupported(
            target,
            "assignment target %s is not implemented" % target.__class__.__name__,
        )

    def _unpack_owned_sequence_into(self, target, sequence_cname):
        from . import ExprNodes

        if not isinstance(target, (ExprNodes.TupleNode, ExprNodes.ListNode)):
            self.unsupported(
                target, "sequence unpacking requires a list or tuple target")
        if target.mult_factor is not None:
            self.unsupported(
                target, "multiplied sequence unpacking targets are not implemented")

        args = list(target.args)
        star_index = None
        for index, arg in enumerate(args):
            if arg.is_starred:
                if star_index is not None:
                    self.unsupported(
                        arg, "multiple starred unpack targets are not implemented")
                star_index = index
        fixed_count = len(args) if star_index is None else len(args) - 1

        self._handle_temps.use(sequence_cname)
        length_cname = "__pyx_hpy_unpack_len_%d" % self._next_loop
        self._next_loop += 1
        self.putln("HPy_ssize_t %s = %s;" % (
            length_cname,
            self.runtime_api.length(
                sequence_cname, context_cname=self.context_cname),
        ))
        self.put_error_return_if_negative(length_cname)

        if star_index is None:
            self.putln("if (%s != %d) {" % (length_cname, fixed_count))
            self.indent()
            self.putln("if (%s < %d) {" % (length_cname, fixed_count))
            self.indent()
            self._emit_unpack_value_error(
                "not enough values to unpack (expected %d, got %%zd)" % fixed_count,
                length_cname,
            )
            self.dedent()
            self.putln("}")
            self.putln("else {")
            self.indent()
            self.putln("%s;" % self.runtime_api.error_set_string(
                self.runtime_api.builtin_exception(
                    "ValueError", context_cname=self.context_cname),
                UniversalHPyModuleWriter._c_string(
                    "too many values to unpack (expected %d)" % fixed_count),
                context_cname=self.context_cname,
            ))
            self._emit_failure_exit()
            self.dedent()
            self.putln("}")
            self.dedent()
            self.putln("}")
            for index, arg in enumerate(args):
                self._handle_temps.use(sequence_cname)
                item_cname = self.allocate_owned_handle(
                    self.runtime_api.item_get_index(
                        sequence_cname, str(index),
                        context_cname=self.context_cname,
                    ))
                self.put_error_return_if_null(item_cname)
                self.assign_target_from_owned_cname(arg, item_cname)
            return

        left_count = star_index
        right_count = len(args) - star_index - 1
        self.putln("if (%s < %d) {" % (length_cname, fixed_count))
        self.indent()
        self._emit_unpack_value_error(
            "not enough values to unpack (expected at least %d, got %%zd)" %
            fixed_count,
            length_cname,
        )
        self.dedent()
        self.putln("}")

        for index in range(left_count):
            self._handle_temps.use(sequence_cname)
            item_cname = self.allocate_owned_handle(
                self.runtime_api.item_get_index(
                    sequence_cname, str(index),
                    context_cname=self.context_cname,
                ))
            self.put_error_return_if_null(item_cname)
            self.assign_target_from_owned_cname(args[index], item_cname)

        rest_size_cname = "__pyx_hpy_unpack_rest_%d" % self._next_loop
        self._next_loop += 1
        self.putln("HPy_ssize_t %s = %s - %d;" % (
            rest_size_cname, length_cname, fixed_count))
        builder = self.runtime_api.sequence_builder(RuntimeSequenceKind.LIST)
        builder_cname = self.allocate_sequence_builder(builder, rest_size_cname)
        rest_index_cname = "__pyx_hpy_unpack_rest_index_%d" % self._next_loop
        self._next_loop += 1
        self.putln("for (HPy_ssize_t %s = 0; %s < %s; %s++) {" % (
            rest_index_cname, rest_index_cname, rest_size_cname, rest_index_cname))
        self.indent()
        self._handle_temps.use(sequence_cname)
        item_cname = self.allocate_owned_handle(
            self.runtime_api.item_get_index(
                sequence_cname,
                "(%s + %d)" % (rest_index_cname, left_count),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(item_cname)
        self.set_sequence_builder_item(
            builder, builder_cname, rest_index_cname, item_cname)
        self.close_owned_handle(item_cname)
        self.dedent()
        self.putln("}")
        rest_cname = self.build_sequence(builder, builder_cname)
        self.put_error_return_if_null(rest_cname)
        self.assign_target_from_owned_cname(args[star_index], rest_cname)

        for offset in range(right_count):
            source_index = "(%s - %d)" % (length_cname, right_count - offset)
            self._handle_temps.use(sequence_cname)
            item_cname = self.allocate_owned_handle(
                self.runtime_api.item_get_index(
                    sequence_cname, source_index,
                    context_cname=self.context_cname,
                ))
            self.put_error_return_if_null(item_cname)
            self.assign_target_from_owned_cname(
                args[star_index + 1 + offset], item_cname)

    def _emit_unpack_value_error(self, format_without_got_placeholder, length_cname):
        """Emit ValueError with a snprintf-formatted unpacking message.

        Uses ``_emit_failure_exit`` so owned-handle bookkeeping stays intact for
        later success-path emission (unlike ``raise_builtin_string``).
        """
        message_cname = "__pyx_hpy_unpack_msg_%d" % self._next_loop
        self._next_loop += 1
        self.putln("char %s[96];" % message_cname)
        self.putln(
            'snprintf(%s, sizeof(%s), "%s", %s);' % (
                message_cname,
                message_cname,
                format_without_got_placeholder,
                length_cname,
            ))
        self.putln("%s;" % self.runtime_api.error_set_string(
            self.runtime_api.builtin_exception(
                "ValueError", context_cname=self.context_cname),
            message_cname,
            context_cname=self.context_cname,
        ))
        self._emit_failure_exit()

    def has_initialized_named_value(self, source_name):
        return (
            source_name in self._local_values
            or source_name in self._borrowed_arguments
        )

    def promote_local_slot(self, node, source_name):
        if source_name in self._stable_local_slots:
            return
        current_cname = self._local_values.get(source_name)
        borrowed_cname = None
        if current_cname is None:
            borrowed_cname = self._borrowed_arguments.get(source_name)
        slot_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        if current_cname is not None:
            self._move_into_owned_slot(slot_cname, current_cname)
        elif borrowed_cname is not None:
            self._handle_temps.use(borrowed_cname)
            duplicate_cname = self.allocate_owned_handle(
                self.runtime_api.duplicate_reference(
                    borrowed_cname, context_cname=self.context_cname))
            self.put_error_return_if_null(duplicate_cname)
            self._move_into_owned_slot(slot_cname, duplicate_cname)
        self._local_values[source_name] = slot_cname
        self._stable_local_slots.add(source_name)

    def prepare_conditional_locals(
        self, node, branch_assignments, has_else,
    ):
        assigned = set().union(*branch_assignments) if branch_assignments else set()
        definitely_assigned = (
            set.intersection(*branch_assignments)
            if has_else and branch_assignments else set()
        )
        for source_name in sorted(assigned):
            if (
                not self.has_initialized_named_value(source_name)
                and source_name not in definitely_assigned
            ):
                self.unsupported(
                    node,
                    "local %s is not initialized on every conditional path" %
                    source_name,
                )
            self.promote_local_slot(node, source_name)

    def assign_attribute(self, receiver, name_cname, value):
        value_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        receiver_cname = self.materialize_owned_handle(
            receiver.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(receiver_cname)
        self.use_owned_handles(receiver_cname, value_cname)
        operation = self.runtime_api.attribute_set_string(
            receiver_cname, name_cname, value_cname,
            context_cname=self.context_cname,
        )
        status_cname = self._emit_status_operation(operation)
        self.close_owned_handle(receiver_cname)
        self.close_owned_handle(value_cname)
        self.put_error_return_if_negative(status_cname)

    def assign_item(self, receiver, key, value):
        value_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        receiver_cname = self.materialize_owned_handle(
            receiver.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(receiver_cname)
        key_cname = self.materialize_owned_handle(
            key.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(key_cname)
        self.use_owned_handles(receiver_cname, key_cname, value_cname)
        operation = self.runtime_api.item_set(
            receiver_cname, key_cname, value_cname,
            context_cname=self.context_cname,
        )
        status_cname = self._emit_status_operation(operation)
        self.close_owned_handle(key_cname)
        self.close_owned_handle(receiver_cname)
        self.close_owned_handle(value_cname)
        self.put_error_return_if_negative(status_cname)

    def _generate_inplace_result(self, operation, current_cname, value):
        value_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        self.use_owned_handles(current_cname, value_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.inplace_operation(
                operation, current_cname, value_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(value_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def inplace_local(self, node, source_name, operation, value):
        current_cname = self._local_values.get(source_name)
        current_is_owned = current_cname is not None
        if current_cname is None:
            current_cname = self._borrowed_arguments.get(source_name)
        if current_cname is None:
            self.unsupported(
                node, "name %s has no initialized local HPy value" % source_name)
        result_cname = self._generate_inplace_result(
            operation, current_cname, value)
        if current_is_owned:
            self.close_owned_handle(current_cname)
        self._local_values[source_name] = result_cname

    def inplace_function_global(self, node, source_name, operation, value):
        current_cname = self.load_module_global(source_name)
        self.put_error_return_if_null(current_cname)
        result_cname = self._generate_inplace_result(
            operation, current_cname, value)
        self.close_owned_handle(current_cname)
        self.store_materialized_module_global(
            source_name, result_cname, self.module_cname, publish=True)

    def inplace_attribute(self, receiver, name_cname, operation, value):
        receiver_cname = self.materialize_owned_handle(
            receiver.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(receiver_cname)
        self.use_owned_handles(receiver_cname)
        current_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                receiver_cname, name_cname, context_cname=self.context_cname))
        self.put_error_return_if_null(current_cname)
        result_cname = self._generate_inplace_result(
            operation, current_cname, value)
        self.close_owned_handle(current_cname)
        self.use_owned_handles(receiver_cname, result_cname)
        status_cname = self._emit_status_operation(
            self.runtime_api.attribute_set_string(
                receiver_cname, name_cname, result_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(result_cname)
        self.close_owned_handle(receiver_cname)
        self.put_error_return_if_negative(status_cname)

    def inplace_item(self, receiver, key, operation, value):
        receiver_cname = self.materialize_owned_handle(
            receiver.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(receiver_cname)
        key_cname = self.materialize_owned_handle(
            key.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(key_cname)
        self.use_owned_handles(receiver_cname, key_cname)
        current_cname = self.allocate_owned_handle(
            self.runtime_api.item_get(
                receiver_cname, key_cname, context_cname=self.context_cname))
        self.put_error_return_if_null(current_cname)
        result_cname = self._generate_inplace_result(
            operation, current_cname, value)
        self.close_owned_handle(current_cname)
        self.use_owned_handles(receiver_cname, key_cname, result_cname)
        status_cname = self._emit_status_operation(
            self.runtime_api.item_set(
                receiver_cname, key_cname, result_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(result_cname)
        self.close_owned_handle(key_cname)
        self.close_owned_handle(receiver_cname)
        self.put_error_return_if_negative(status_cname)

    def delete_attribute(self, receiver, name_cname):
        receiver_cname = self.materialize_owned_handle(
            receiver.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(receiver_cname)
        self._handle_temps.use(receiver_cname)
        operation = self.runtime_api.attribute_delete_string(
            receiver_cname, name_cname, context_cname=self.context_cname)
        status_cname = self._emit_status_operation(operation)
        self.close_owned_handle(receiver_cname)
        self.put_error_return_if_negative(status_cname)

    def delete_function_global(self, node, source_name):
        self.ensure_extension_runtime_owners(node)
        name_cname = UniversalHPyModuleWriter._c_string(source_name)
        has_module_value = self._emit_status_operation(
            self.runtime_api.attribute_has_string(
                self.module_cname, name_cname,
                context_cname=self.context_cname))
        self.putln("if (!%s) {" % has_module_value)
        self.indent()
        name_error = self.runtime_api.builtin_exception(
            "NameError", context_cname=self.context_cname)
        message = UniversalHPyModuleWriter._c_string(
            "name '%s' is not defined" % source_name)
        self.putln("%s;" % self.runtime_api.error_set_string(
            name_error, message, context_cname=self.context_cname))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")
        status_cname = self._emit_status_operation(
            self.runtime_api.attribute_delete_string(
                self.module_cname, name_cname,
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_negative(status_cname)

    def delete_local(self, node, source_name):
        """Unbind a Python local/argument; later reads raise UnboundLocalError."""
        if not self.has_initialized_named_value(source_name):
            self._raise_unbound_local_error(source_name)
            return
        # Promote first so conditional ``del`` mutates a stable slot whose
        # bookkeeping name survives branch lifetime restores.
        self.promote_local_slot(node, source_name)
        slot_cname = self._local_values[source_name]
        self._handle_temps.use(slot_cname)
        self.putln("if (%s) {" % self.runtime_api.null_check(slot_cname))
        self.indent()
        self._raise_unbound_local_error(source_name)
        self.dedent()
        self.putln("}")
        null_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        self._move_into_owned_slot(slot_cname, null_cname)

    def _raise_unbound_local_error(self, source_name):
        exception_cname = self.runtime_api.builtin_exception(
            "UnboundLocalError", context_cname=self.context_cname)
        message = UniversalHPyModuleWriter._c_string(
            "local variable '%s' referenced before assignment" % source_name)
        self.putln("%s;" % self.runtime_api.error_set_string(
            exception_cname, message, context_cname=self.context_cname))
        self._emit_failure_exit()

    def delete_item(self, receiver, key):
        receiver_cname = self.materialize_owned_handle(
            receiver.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(receiver_cname)
        key_cname = self.materialize_owned_handle(
            key.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(key_cname)
        self.use_owned_handles(receiver_cname, key_cname)
        operation = self.runtime_api.item_delete(
            receiver_cname, key_cname, context_cname=self.context_cname)
        status_cname = self._emit_status_operation(operation)
        self.close_owned_handle(key_cname)
        self.close_owned_handle(receiver_cname)
        self.put_error_return_if_negative(status_cname)

    def _emit_status_operation(self, expression):
        cname = "__pyx_hpy_status_%d" % self._next_status
        self._next_status += 1
        self.putln("int %s = %s;" % (cname, expression))
        return cname

    def _close_remaining_owned_handles(self):
        for cname in reversed(tuple(self._handle_order)):
            if self._handle_temps.is_active(cname):
                # Stable local slots may be HPy_NULL after ``del``.
                self.close_owned_handle(cname, null_safe=True)

    def raise_builtin_string(self, exception_name, message_cname):
        exception_cname = self.runtime_api.builtin_exception(
            exception_name, context_cname=self.context_cname)
        self.putln("%s;" % self.runtime_api.error_set_string(
            exception_cname, message_cname, context_cname=self.context_cname))
        self._finish_raised_error()

    def raise_builtin_object(self, exception_name, value):
        self.raise_builtin_arguments(exception_name, [value])

    def raise_builtin_arguments(self, exception_name, arguments):
        tuple_builder = self.runtime_api.sequence_builder(
            RuntimeSequenceKind.TUPLE)
        builder_cname = self.allocate_sequence_builder(
            tuple_builder, len(arguments))
        for index, argument in enumerate(arguments):
            value_cname = self.materialize_owned_handle(
                argument.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(value_cname)
            self.set_sequence_builder_item(
                tuple_builder, builder_cname, index, value_cname)
            self.close_owned_handle(value_cname)
        args_cname = self.build_sequence(tuple_builder, builder_cname)
        self.put_error_return_if_null(args_cname)
        exception_cname = self.runtime_api.builtin_exception(
            exception_name, context_cname=self.context_cname)
        self.putln("%s;" % self.runtime_api.error_set_object(
            exception_cname, args_cname, context_cname=self.context_cname))
        self.close_owned_handle(args_cname)
        self._finish_raised_error()

    def raise_no_memory(self):
        self.putln("%s;" % self.runtime_api.error_no_memory(
            context_cname=self.context_cname))
        self._finish_raised_error()

    def raise_dynamic_exception(self, value):
        value_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        type_cname = self.allocate_owned_handle(self.runtime_api.object_type(
            value_cname, context_cname=self.context_cname))
        self.put_error_return_if_null(type_cname)
        args_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        base_exception = self.runtime_api.context_constant(
            RuntimeContextConstant.BASE_EXCEPTION,
            context_cname=self.context_cname,
        )
        type_type = self.runtime_api.context_constant(
            RuntimeContextConstant.TYPE_TYPE,
            context_cname=self.context_cname,
        )
        self.putln("if (%s) {" % self.runtime_api.type_check(
            value_cname, base_exception, context_cname=self.context_cname))
        self.indent()
        self.putln("%s;" % self.runtime_api.error_set_object(
            type_cname, value_cname, context_cname=self.context_cname))
        self.dedent()
        self.putln("} else if (%s) {" % self.runtime_api.type_check(
            value_cname, type_type, context_cname=self.context_cname))
        self.indent()
        self.putln("if (%s) {" % self.runtime_api.type_is_subtype(
            value_cname, base_exception, context_cname=self.context_cname))
        self.indent()
        tuple_builder = self.runtime_api.sequence_builder(
            RuntimeSequenceKind.TUPLE)
        builder_cname = "__pyx_hpy_builder_%d" % self._next_builder
        self._next_builder += 1
        self.putln("%s %s = %s;" % (
            tuple_builder.builder_type_cname,
            builder_cname,
            self.runtime_api.sequence_builder_new(
                tuple_builder, "0", context_cname=self.context_cname),
        ))
        self.putln("%s = %s;" % (
            args_cname,
            self.runtime_api.sequence_builder_build(
                tuple_builder, builder_cname, context_cname=self.context_cname),
        ))
        self.putln("if (%s) {" % self.runtime_api.null_check(args_cname))
        self.indent()
        self._emit_failure_exit(exclude_handles=(args_cname,))
        self.dedent()
        self.putln("}")
        self.putln("%s;" % self.runtime_api.error_set_object(
            value_cname, args_cname, context_cname=self.context_cname))
        self.dedent()
        self.putln("} else {")
        self.indent()
        self.putln("%s;" % self.runtime_api.error_set_string(
            self.runtime_api.builtin_exception(
                "TypeError", context_cname=self.context_cname),
            '"exceptions must derive from BaseException"',
            context_cname=self.context_cname,
        ))
        self.dedent()
        self.putln("}")
        self.dedent()
        self.putln("} else {")
        self.indent()
        self.putln("%s;" % self.runtime_api.error_set_string(
            self.runtime_api.builtin_exception(
                "TypeError", context_cname=self.context_cname),
            '"exceptions must derive from BaseException"',
            context_cname=self.context_cname,
        ))
        self.dedent()
        self.putln("}")
        self.close_owned_handle(args_cname, null_safe=True)
        self.close_owned_handle(type_cname)
        self.close_owned_handle(value_cname)
        self._finish_raised_error()

    def _finish_raised_error(self):
        if self._failure_scopes:
            self._emit_failure_exit()
            return
        self._close_remaining_owned_handles()
        self._close_argument_tracker()
        for line in self.failure_epilogue:
            self.putln(line)
        self.putln("return %s;" % self.failure_return_value)

    def discard_owned_result(self, value):
        cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(cname)
        self.close_owned_handle(cname)

    def store_module_global(
        self, node, source_name, value, module_cname, publish=True,
    ):
        if self.name_registry is None:
            raise AssertionError("module-global emission requires a name registry")
        value_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        self.store_materialized_module_global(
            source_name, value_cname, module_cname, publish=publish)

    def store_module_global_expression(
        self, source_name, expression, module_cname, publish=True,
    ):
        value_cname = self.allocate_owned_handle(expression)
        self.put_error_return_if_null(value_cname)
        self.store_materialized_module_global(
            source_name, value_cname, module_cname, publish=publish)

    def store_materialized_module_global(
        self, source_name, value_cname, module_cname, publish=True,
    ):
        if publish:
            self._handle_temps.use(value_cname)
            status_cname = self._emit_status_operation(
                self.runtime_api.module_set_attr_string(
                    module_cname,
                    UniversalHPyModuleWriter._c_string(source_name),
                    value_cname,
                    context_cname=self.context_cname,
                )
            )
            if self.rollback_module_publications:
                self.put_module_publication_error_if_negative(status_cname)
            else:
                self.put_error_return_if_negative(status_cname)
            self.record_module_publication(source_name, module_cname)
        self.name_registry.require_module_global(source_name)
        self.close_owned_handle(value_cname)
        if self.available_module_globals is not None:
            self.available_module_globals.add(source_name)

    def record_module_publication(self, source_name, module_cname):
        if not self.rollback_module_publications:
            return
        key = (module_cname, source_name)
        if key in self._rollback_module_attributes:
            return
        self._rollback_module_attributes.add(key)
        rollback = "(void)%s;" % self.runtime_api.attribute_delete_string(
            module_cname,
            UniversalHPyModuleWriter._c_string(source_name),
            context_cname=self.context_cname,
        )
        # Later publications depend on earlier ones.  Store rollback actions
        # in exact reverse order for the publication-specific error path.
        self._module_publication_rollbacks.insert(0, rollback)

    def generate_binary_operation(self, operation, left, right):
        # A direct right-hand name can always remain borrowed after the left
        # expression has been evaluated.  A direct left-hand name can remain
        # borrowed only when the right side is also a side-effect-free direct
        # name: evaluating an arbitrary right expression may rebind/delete the
        # left local, while Python keeps the already-evaluated left value alive.
        left_cname = self.borrow_direct_named_value(left)
        left_is_owned = left_cname is None
        if left_cname is None:
            left_cname = self.materialize_owned_handle(
                left.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(left_cname)
            right_cname = self.borrow_direct_named_value(right)
        else:
            right_cname = self.borrow_direct_named_value(right)
            if right_cname is None:
                left_cname = self.materialize_owned_handle(
                    left.generate_hpy_bootstrap_owned_result(self))
                self.put_error_return_if_null(left_cname)
                left_is_owned = True
        right_is_owned = right_cname is None
        if right_cname is None:
            right_cname = self.materialize_owned_handle(
                right.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(right_cname)
        self.use_owned_handles(left_cname, right_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.binary_operation(
                operation, left_cname, right_cname,
                context_cname=self.context_cname,
            ))
        if right_is_owned:
            self.close_owned_handle(right_cname)
        if left_is_owned:
            self.close_owned_handle(left_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def multiply_materialized_sequence(self, sequence_cname, factor):
        self.put_error_return_if_null(sequence_cname)
        factor_cname = self.materialize_owned_handle(
            factor.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(factor_cname)
        self.use_owned_handles(sequence_cname, factor_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.binary_operation(
                RuntimeBinaryOperation.MULTIPLY,
                sequence_cname,
                factor_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(factor_cname)
        self.close_owned_handle(sequence_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_starred_sequence(self, kind, arguments, factor=None):
        result_cname = None
        builder = self.runtime_api.sequence_builder(kind)
        type_constant = (
            RuntimeContextConstant.LIST_TYPE
            if kind is RuntimeSequenceKind.LIST
            else RuntimeContextConstant.TUPLE_TYPE
        )
        sequence_type = self.runtime_api.context_constant(
            type_constant, context_cname=self.context_cname)

        for argument in arguments:
            if argument.is_starred:
                source_cname = self.materialize_owned_handle(
                    argument.target.generate_hpy_bootstrap_owned_result(self))
                self.put_error_return_if_null(source_cname)
                self._handle_temps.use(source_cname)
                segment_cname = self.allocate_owned_handle(
                    self.runtime_api.call_one_arg(
                        sequence_type,
                        source_cname,
                        context_cname=self.context_cname,
                    ))
                self.close_owned_handle(source_cname)
                self.put_error_return_if_null(segment_cname)
            else:
                builder_cname = self.allocate_sequence_builder(builder, 1)
                item_cname = self.materialize_owned_handle(
                    argument.generate_hpy_bootstrap_owned_result(self))
                self.put_error_return_if_null(item_cname)
                self.set_sequence_builder_item(
                    builder, builder_cname, 0, item_cname)
                self.close_owned_handle(item_cname)
                segment_cname = self.build_sequence(builder, builder_cname)
                self.put_error_return_if_null(segment_cname)

            if result_cname is None:
                result_cname = segment_cname
                continue

            self.use_owned_handles(result_cname, segment_cname)
            combined_cname = self.allocate_owned_handle(
                self.runtime_api.binary_operation(
                    RuntimeBinaryOperation.ADD,
                    result_cname,
                    segment_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(segment_cname)
            self.close_owned_handle(result_cname)
            self.put_error_return_if_null(combined_cname)
            result_cname = combined_cname

        if result_cname is None:
            raise AssertionError("starred sequence generation requires arguments")
        if factor is not None:
            return self.multiply_materialized_sequence(result_cname, factor)
        return result_cname

    def generate_merged_sequence(self, kind, arguments):
        type_constant = (
            RuntimeContextConstant.LIST_TYPE
            if kind is RuntimeSequenceKind.LIST
            else RuntimeContextConstant.TUPLE_TYPE
        )
        sequence_type = self.runtime_api.context_constant(
            type_constant, context_cname=self.context_cname)
        result_cname = None
        for argument in arguments:
            source_cname = self.materialize_owned_handle(
                argument.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(source_cname)
            self._handle_temps.use(source_cname)
            segment_cname = self.allocate_owned_handle(
                self.runtime_api.call_one_arg(
                    sequence_type,
                    source_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(source_cname)
            self.put_error_return_if_null(segment_cname)
            if result_cname is None:
                result_cname = segment_cname
                continue
            self.use_owned_handles(result_cname, segment_cname)
            combined_cname = self.allocate_owned_handle(
                self.runtime_api.binary_operation(
                    RuntimeBinaryOperation.ADD,
                    result_cname,
                    segment_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(segment_cname)
            self.close_owned_handle(result_cname)
            self.put_error_return_if_null(combined_cname)
            result_cname = combined_cname
        if result_cname is None:
            raise AssertionError("merged sequence generation requires arguments")
        return result_cname

    def normalize_sequence_handle(self, kind, source_cname):
        type_constant = (
            RuntimeContextConstant.LIST_TYPE
            if kind is RuntimeSequenceKind.LIST
            else RuntimeContextConstant.TUPLE_TYPE
        )
        sequence_type = self.runtime_api.context_constant(
            type_constant, context_cname=self.context_cname)
        self.use_owned_handles(source_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.call_one_arg(
                sequence_type,
                source_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(source_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_none_check(
        self, value_cname, exception_type_cname, message, format_args=(),
    ):
        none_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.NONE, context_cname=self.context_cname)
        self.use_owned_handles(value_cname)
        condition = self.runtime_api.identity_test(
            value_cname, none_handle, context_cname=self.context_cname)
        self.putln("if (%s) {" % condition)
        self.indent()
        exception_name = exception_type_cname.removeprefix("PyExc_")
        if format_args:
            try:
                message = message % tuple(format_args)
            except (TypeError, ValueError):
                self.unsupported(
                    None, "formatted None-check diagnostics are not implemented")
        exception_handle = self.runtime_api.builtin_exception(
            exception_name, context_cname=self.context_cname)
        self.putln("%s;" % self.runtime_api.error_set_string(
            exception_handle,
            UniversalHPyModuleWriter._c_string(message),
            context_cname=self.context_cname,
        ))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")

    def generate_merged_dictionary(self, mappings, reject_duplicates=True):
        dictionary_cname = self.allocate_owned_handle(
            self.runtime_api.dict_new(context_cname=self.context_cname))
        self.put_error_return_if_null(dictionary_cname)
        tuple_type = self.runtime_api.context_constant(
            RuntimeContextConstant.TUPLE_TYPE,
            context_cname=self.context_cname,
        )

        for mapping in mappings:
            if isinstance(mapping, ExprNodes.DictNode):
                for item in mapping.key_value_pairs:
                    key_cname = self.materialize_owned_handle(
                        item.key.generate_hpy_bootstrap_owned_result(self))
                    self.put_error_return_if_null(key_cname)
                    value_cname = self.materialize_owned_handle(
                        item.value.generate_hpy_bootstrap_owned_result(self))
                    self.put_error_return_if_null(value_cname)
                    if reject_duplicates:
                        self._generate_keyword_duplicate_check(
                            dictionary_cname, key_cname)
                    self.use_owned_handles(
                        dictionary_cname, key_cname, value_cname)
                    status_cname = self._emit_status_operation(
                        self.runtime_api.dict_set_item(
                            dictionary_cname,
                            key_cname,
                            value_cname,
                            context_cname=self.context_cname,
                        ))
                    self.close_owned_handle(value_cname)
                    self.close_owned_handle(key_cname)
                    self.put_error_return_if_negative(status_cname)
                continue

            mapping_cname = self.materialize_owned_handle(
                mapping.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(mapping_cname)
            self.use_owned_handles(mapping_cname)
            keys_method_cname = self.allocate_owned_handle(
                self.runtime_api.attribute_get_string(
                    mapping_cname,
                    '"keys"',
                    context_cname=self.context_cname,
                ))
            self.putln("if (%s) {" % self.runtime_api.null_check(
                keys_method_cname))
            self.indent()
            attribute_error = self.runtime_api.builtin_exception(
                "AttributeError", context_cname=self.context_cname)
            self.putln("if (%s) {" % self.runtime_api.exception_matches(
                attribute_error, context_cname=self.context_cname))
            self.indent()
            self.putln("%s;" % self.runtime_api.error_clear(
                context_cname=self.context_cname))
            type_error = self.runtime_api.builtin_exception(
                "TypeError", context_cname=self.context_cname)
            self.putln("%s;" % self.runtime_api.error_set_string(
                type_error,
                '"argument after ** must be a mapping"',
                context_cname=self.context_cname,
            ))
            self.dedent()
            self.putln("}")
            self._emit_failure_exit(exclude_handles=(keys_method_cname,))
            self.dedent()
            self.putln("}")
            self.use_owned_handles(keys_method_cname)
            keys_iterable_cname = self.allocate_owned_handle(
                self.runtime_api.call_no_args(
                    keys_method_cname, context_cname=self.context_cname))
            self.close_owned_handle(keys_method_cname)
            self.put_error_return_if_null(keys_iterable_cname)
            self.use_owned_handles(keys_iterable_cname)
            keys_cname = self.allocate_owned_handle(
                self.runtime_api.call_one_arg(
                    tuple_type,
                    keys_iterable_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(keys_iterable_cname)
            self.put_error_return_if_null(keys_cname)

            count_cname = "__pyx_hpy_mapping_size_%d" % self._next_loop
            index_cname = "__pyx_hpy_mapping_index_%d" % self._next_loop
            self._next_loop += 1
            self.use_owned_handles(keys_cname)
            self.putln("HPy_ssize_t %s = %s;" % (
                count_cname,
                self.runtime_api.length(
                    keys_cname, context_cname=self.context_cname),
            ))
            self.put_error_return_if_negative(count_cname)
            self.putln("for (HPy_ssize_t %s = 0; %s < %s; %s++) {" % (
                index_cname, index_cname, count_cname, index_cname))
            self.indent()
            key_cname = self.allocate_owned_handle(
                self.runtime_api.item_get_index(
                    keys_cname, index_cname,
                    context_cname=self.context_cname,
                ))
            self.put_error_return_if_null(key_cname)
            if reject_duplicates:
                self._generate_keyword_duplicate_check(
                    dictionary_cname, key_cname)
            self.use_owned_handles(mapping_cname, key_cname)
            value_cname = self.allocate_owned_handle(
                self.runtime_api.item_get(
                    mapping_cname,
                    key_cname,
                    context_cname=self.context_cname,
                ))
            self.put_error_return_if_null(value_cname)
            self.use_owned_handles(dictionary_cname, key_cname, value_cname)
            status_cname = self._emit_status_operation(
                self.runtime_api.dict_set_item(
                    dictionary_cname,
                    key_cname,
                    value_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(value_cname)
            self.close_owned_handle(key_cname)
            self.put_error_return_if_negative(status_cname)
            self.dedent()
            self.putln("}")
            self.close_owned_handle(keys_cname)
            self.close_owned_handle(mapping_cname)
        return dictionary_cname

    def _generate_keyword_duplicate_check(
        self, dictionary_cname, key_cname,
    ):
        self.use_owned_handles(dictionary_cname, key_cname)
        contains_cname = self._emit_status_operation(
            self.runtime_api.contains(
                dictionary_cname,
                key_cname,
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_negative(contains_cname)
        self.putln("if (%s) {" % contains_cname)
        self.indent()
        type_error = self.runtime_api.builtin_exception(
            "TypeError", context_cname=self.context_cname)
        self.putln("%s;" % self.runtime_api.error_set_string(
            type_error,
            '"function() got multiple values for keyword argument"',
            context_cname=self.context_cname,
        ))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")

    @staticmethod
    def _keyword_name_literal(name_node):
        node = name_node
        while isinstance(
            node,
            (ExprNodes.CoerceToPyTypeNode, ExprNodes.CoerceToTempNode),
        ):
            node = node.arg
        if isinstance(node, (ExprNodes.UnicodeNode, ExprNodes.IdentifierStringNode)):
            return str(node.value)
        if isinstance(node, ExprNodes.BytesNode):
            return node.value.byteencode()
        return None

    def _guard_keyword_name_duplicates(self, keyword_names):
        """Reject duplicate keywords flattened into a kwnames tuple (call / ** merge)."""
        if keyword_names is None or not keyword_names.args:
            return
        literal_names = [
            self._keyword_name_literal(name_node)
            for name_node in keyword_names.args
        ]
        if all(name is not None for name in literal_names):
            if len(literal_names) == len(set(literal_names)):
                return
            # Compile-time duplicate keyword names: emit the public TypeError path.
            type_error = self.runtime_api.builtin_exception(
                "TypeError", context_cname=self.context_cname)
            self.putln("%s;" % self.runtime_api.error_set_string(
                type_error,
                '"function() got multiple values for keyword argument"',
                context_cname=self.context_cname,
            ))
            self._emit_failure_exit()
            return
        seen_cname = self.allocate_owned_handle(
            self.runtime_api.dict_new(context_cname=self.context_cname))
        self.put_error_return_if_null(seen_cname)
        none_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.NONE, context_cname=self.context_cname)
        for name_node in keyword_names.args:
            name_cname = self.materialize_owned_handle(
                name_node.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(name_cname)
            self._generate_keyword_duplicate_check(seen_cname, name_cname)
            self.use_owned_handles(seen_cname, name_cname)
            status_cname = self._emit_status_operation(
                self.runtime_api.dict_set_item(
                    seen_cname,
                    name_cname,
                    none_handle,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(name_cname)
            self.put_error_return_if_negative(status_cname)
        self.close_owned_handle(seen_cname)

    def generate_inplace_binary_operation(self, operation, left, right):
        left_cname = self.materialize_owned_handle(
            left.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(left_cname)
        right_cname = self.materialize_owned_handle(
            right.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(right_cname)
        self.use_owned_handles(left_cname, right_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.inplace_operation(
                operation, left_cname, right_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(right_cname)
        self.close_owned_handle(left_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_unary_operation(self, operation, operand):
        operand_cname = self.materialize_owned_handle(
            operand.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(operand_cname)
        self.use_owned_handles(operand_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.unary_operation(
                operation, operand_cname, context_cname=self.context_cname,
            ))
        self.close_owned_handle(operand_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_boolean_short_circuit(self, operator, left, right):
        if operator not in ("and", "or"):
            raise AssertionError("unexpected boolean operator %r" % operator)
        left_cname = self.materialize_owned_handle(
            left.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(left_cname)
        self._handle_temps.use(left_cname)
        truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
        self._next_truth += 1
        self.putln("int %s = %s;" % (
            truth_cname,
            self.runtime_api.truth_test(
                left_cname, context_cname=self.context_cname),
        ))
        self.put_error_return_if_negative(truth_cname)

        result_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        evaluate_right = truth_cname if operator == "and" else "!%s" % truth_cname
        self.putln("if (%s) {" % evaluate_right)
        self.indent()
        right_cname = self.materialize_owned_handle(
            right.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(right_cname)
        self._handle_temps.use(right_cname)
        self.putln("%s = %s;" % (result_cname, right_cname))
        self._handle_temps.move(right_cname)
        self._handle_temps.release(right_cname)
        self._handle_order.remove(right_cname)
        self.dedent()
        self.putln("} else {")
        self.indent()
        self._handle_temps.use(left_cname)
        self.putln("%s = %s;" % (
            result_cname,
            self.runtime_api.duplicate_reference(
                left_cname, context_cname=self.context_cname),
        ))
        self.dedent()
        self.putln("}")
        self.close_owned_handle(left_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_boolean_not(self, operand):
        operand_cname = self.materialize_owned_handle(
            operand.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(operand_cname)
        self._handle_temps.use(operand_cname)
        truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
        self._next_truth += 1
        self.putln("int %s = %s;" % (
            truth_cname,
            self.runtime_api.truth_test(
                operand_cname, context_cname=self.context_cname),
        ))
        self.close_owned_handle(operand_cname)
        self.put_error_return_if_negative(truth_cname)
        true_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.TRUE, context_cname=self.context_cname)
        false_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.FALSE, context_cname=self.context_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.duplicate_reference(
                "%s ? %s : %s" % (
                    truth_cname, false_handle, true_handle),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_conditional_expression(
        self, condition, true_value, false_value,
    ):
        condition_cname = self.materialize_owned_handle(
            condition.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(condition_cname)
        self._handle_temps.use(condition_cname)
        truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
        self._next_truth += 1
        self.putln("int %s = %s;" % (
            truth_cname,
            self.runtime_api.truth_test(
                condition_cname, context_cname=self.context_cname),
        ))
        self.close_owned_handle(condition_cname)
        self.put_error_return_if_negative(truth_cname)

        result_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        branch_state = self._snapshot_lifetime_state()
        self.putln("if (%s) {" % truth_cname)
        self.indent()
        true_cname = self.materialize_owned_handle(
            true_value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(true_cname)
        self._move_into_owned_slot(result_cname, true_cname)
        self.dedent()
        self.putln("} else {")
        true_state = self._snapshot_lifetime_state()
        self._restore_lifetime_state(copy.deepcopy(branch_state))
        self.indent()
        false_cname = self.materialize_owned_handle(
            false_value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(false_cname)
        self._move_into_owned_slot(result_cname, false_cname)
        self.dedent()
        self.putln("}")
        self._restore_lifetime_state(true_state)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_rich_compare(self, operation, left, right):
        left_cname = self.materialize_owned_handle(
            left.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(left_cname)
        right_cname = self.materialize_owned_handle(
            right.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(right_cname)
        self.use_owned_handles(left_cname, right_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.rich_compare(
                operation, left_cname, right_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(right_cname)
        self.close_owned_handle(left_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def _assign_comparison_result(self, node, result_cname, operator,
                                  left_cname, right_cname):
        self.use_owned_handles(left_cname, right_cname)
        rich_operations = {
            "<": RuntimeComparisonOperation.LESS_THAN,
            "<=": RuntimeComparisonOperation.LESS_EQUAL,
            "==": RuntimeComparisonOperation.EQUAL,
            "!=": RuntimeComparisonOperation.NOT_EQUAL,
            ">": RuntimeComparisonOperation.GREATER_THAN,
            ">=": RuntimeComparisonOperation.GREATER_EQUAL,
        }
        if operator in rich_operations:
            expression = self.runtime_api.rich_compare(
                rich_operations[operator], left_cname, right_cname,
                context_cname=self.context_cname,
            )
        elif operator in ("is", "is_not"):
            status_cname = "__pyx_hpy_identity_%d" % self._next_status
            self._next_status += 1
            identity = self.runtime_api.identity_test(
                left_cname, right_cname, context_cname=self.context_cname)
            if operator == "is_not":
                identity = "!(%s)" % identity
            self.putln("int %s = %s;" % (status_cname, identity))
            true_handle = self.runtime_api.context_constant(
                RuntimeContextConstant.TRUE, context_cname=self.context_cname)
            false_handle = self.runtime_api.context_constant(
                RuntimeContextConstant.FALSE, context_cname=self.context_cname)
            expression = self.runtime_api.duplicate_reference(
                "%s ? %s : %s" % (
                    status_cname, true_handle, false_handle),
                context_cname=self.context_cname,
            )
        elif operator in ("in", "not_in"):
            status_cname = "__pyx_hpy_contains_%d" % self._next_status
            self._next_status += 1
            self.putln("int %s = %s;" % (
                status_cname,
                self.runtime_api.contains(
                    right_cname, left_cname, context_cname=self.context_cname),
            ))
            self.put_error_return_if_negative(status_cname)
            true_handle = self.runtime_api.context_constant(
                RuntimeContextConstant.TRUE, context_cname=self.context_cname)
            false_handle = self.runtime_api.context_constant(
                RuntimeContextConstant.FALSE, context_cname=self.context_cname)
            condition = (
                "!%s" % status_cname
                if operator == "not_in" else status_cname)
            expression = self.runtime_api.duplicate_reference(
                "%s ? %s : %s" % (
                    condition, true_handle, false_handle),
                context_cname=self.context_cname,
            )
        else:
            self.unsupported(
                node, "comparison operator %s is not implemented" % operator)
        self.putln("%s = %s;" % (result_cname, expression))

    def _move_into_owned_slot(self, slot_cname, value_cname):
        self.use_owned_handles(slot_cname, value_cname)
        self.putln(self.runtime_api.close_reference(
            slot_cname, null_safe=True, context_cname=self.context_cname))
        self.putln("%s = %s;" % (slot_cname, value_cname))
        self._handle_temps.move(value_cname)
        self._handle_temps.release(value_cname)
        self._handle_order.remove(value_cname)

    def _clear_owned_slot(self, cname):
        self._handle_temps.use(cname)
        self.putln(self.runtime_api.close_reference(
            cname, context_cname=self.context_cname))
        self.putln(self.runtime_api.empty_reference(cname))

    def generate_cascaded_comparison(self, primary):
        current_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        result_cname = self.allocate_owned_handle(
            self.runtime_api.null_reference_value())
        left_cname = self.materialize_owned_handle(
            primary.operand1.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(left_cname)
        middle_cname = self.materialize_owned_handle(
            primary.operand2.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(middle_cname)
        self._move_into_owned_slot(current_cname, middle_cname)
        self._assign_comparison_result(
            primary, result_cname, primary.operator,
            left_cname, current_cname)
        self.close_owned_handle(left_cname)
        self.put_error_return_if_null(result_cname)
        self._generate_cascaded_comparison_tail(
            result_cname, current_cname, primary.cascade)
        self.close_owned_handle(current_cname, null_safe=True)
        return result_cname

    def _generate_cascaded_comparison_tail(
        self, result_cname, current_cname, cascade,
    ):
        self.use_owned_handles(result_cname)
        truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
        self._next_truth += 1
        self.putln("int %s = %s;" % (
            truth_cname,
            self.runtime_api.truth_test(
                result_cname, context_cname=self.context_cname),
        ))
        self.put_error_return_if_negative(truth_cname)
        self.putln("if (%s) {" % truth_cname)
        self.indent()
        self._clear_owned_slot(result_cname)
        next_cname = self.materialize_owned_handle(
            cascade.operand2.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(next_cname)
        self._assign_comparison_result(
            cascade, result_cname, cascade.operator,
            current_cname, next_cname)
        self._move_into_owned_slot(current_cname, next_cname)
        self.put_error_return_if_null(result_cname)
        if cascade.cascade is not None:
            self._generate_cascaded_comparison_tail(
                result_cname, current_cname, cascade.cascade)
        self.dedent()
        self.putln("} else {")
        self.indent()
        self._clear_owned_slot(current_cname)
        self.dedent()
        self.putln("}")

    def generate_identity_compare(self, negated, left, right):
        left_cname = self.materialize_owned_handle(
            left.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(left_cname)
        right_cname = self.materialize_owned_handle(
            right.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(right_cname)
        self.use_owned_handles(left_cname, right_cname)
        status_cname = "__pyx_hpy_identity_%d" % self._next_status
        self._next_status += 1
        expression = self.runtime_api.identity_test(
            left_cname, right_cname, context_cname=self.context_cname)
        if negated:
            expression = "!(%s)" % expression
        self.putln("int %s = %s;" % (status_cname, expression))
        self.close_owned_handle(right_cname)
        self.close_owned_handle(left_cname)
        true_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.TRUE, context_cname=self.context_cname)
        false_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.FALSE, context_cname=self.context_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.duplicate_reference(
                "%s ? %s : %s" % (
                    status_cname, true_handle, false_handle),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_membership_compare(self, negated, key, container):
        key_cname = self.materialize_owned_handle(
            key.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(key_cname)
        container_cname = self.materialize_owned_handle(
            container.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(container_cname)
        self.use_owned_handles(key_cname, container_cname)
        status_cname = "__pyx_hpy_contains_%d" % self._next_status
        self._next_status += 1
        self.putln("int %s = %s;" % (
            status_cname,
            self.runtime_api.contains(
                container_cname, key_cname, context_cname=self.context_cname),
        ))
        self.close_owned_handle(container_cname)
        self.close_owned_handle(key_cname)
        self.put_error_return_if_negative(status_cname)
        true_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.TRUE, context_cname=self.context_cname)
        false_handle = self.runtime_api.context_constant(
            RuntimeContextConstant.FALSE, context_cname=self.context_cname)
        condition = "!%s" % status_cname if negated else status_cname
        result_cname = self.allocate_owned_handle(
            self.runtime_api.duplicate_reference(
                "%s ? %s : %s" % (
                    condition, true_handle, false_handle),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(result_cname)
        return result_cname

    def _snapshot_lifetime_state(self):
        return copy.deepcopy((
            self._handle_temps,
            self._builder_temps,
            self._tracker_temps,
            self._builder_contracts,
            self._handle_order,
            self._builder_order,
            self._borrowed_arguments,
            self._local_values,
            self._temporary_values,
            self._stable_local_slots,
            self._tracker_owned_arguments,
            self.module_cname,
            self.default_owner_cname,
        ))

    def _restore_lifetime_state(self, snapshot):
        (
            self._handle_temps,
            self._builder_temps,
            self._tracker_temps,
            self._builder_contracts,
            self._handle_order,
            self._builder_order,
            self._borrowed_arguments,
            self._local_values,
            self._temporary_values,
            self._stable_local_slots,
            self._tracker_owned_arguments,
            self.module_cname,
            self.default_owner_cname,
        ) = snapshot

    @staticmethod
    def _unwrap_exception_pattern(pattern):
        while isinstance(
            pattern,
            (ExprNodes.CoerceToPyTypeNode, ExprNodes.CoerceToTempNode),
        ):
            pattern = pattern.arg
        return pattern

    @staticmethod
    def _find_nested_try_except(node):
        pending = [node]
        while pending:
            current = pending.pop()
            if current is None:
                continue
            if type(current) is Nodes.TryExceptStatNode:
                return current
            for child_name in getattr(current, "child_attrs", ()):
                child = getattr(current, child_name, None)
                if isinstance(child, (list, tuple)):
                    pending.extend(child)
                else:
                    pending.append(child)
        return None

    def generate_terminal_try_except(self, node):
        """Emit the HPy-0.9 current-error-only handler subset."""
        if self._failure_scopes:
            self.unsupported(
                node, "nested try/except statements are not implemented")
        if node.else_clause is not None:
            self.unsupported(
                node.else_clause,
                "try/except else clauses require general handler-state "
                "control flow and are not implemented",
            )
        try_body = self.stats(node.body)
        for statement in try_body:
            if type(statement) is Nodes.TryExceptStatNode:
                self.unsupported(
                    statement,
                    "nested try/except statements are not implemented",
                )
        if (
            not try_body
            or type(try_body[-1]) not in (Nodes.ReturnStatNode, Nodes.RaiseStatNode)
        ):
            self.unsupported(
                node.body,
                "the HPy try/except lane requires a terminating return or "
                "raise statement at the end of the try body",
            )
        allowed_statement_types = (
            Nodes.GlobalNode,
            Nodes.ExprStatNode,
            Nodes.SingleAssignmentNode,
            Nodes.InPlaceAssignmentNode,
            Nodes.DelStatNode,
            Nodes.PassStatNode,
            Nodes.IfStatNode,
            Nodes.WhileStatNode,
            Nodes.ForInStatNode,
            Nodes.ForFromStatNode,
        )
        for statement in try_body[:-1]:
            if type(statement) not in allowed_statement_types:
                self.unsupported(
                    statement,
                    "try-body statements before the terminal return or raise "
                    "must currently be linear assignments, expressions, "
                    "deletions, pass, or supported if/while/for control",
                )

        clauses = []
        default_seen = False
        for clause in node.except_clauses:
            if clause.target is not None or clause.excinfo_target is not None:
                self.unsupported(
                    clause,
                    "except targets require a public exception-state API; "
                    "HPy 0.9 exposes only the current error",
                )
            handler_body = self.stats(clause.body)
            if (
                not handler_body
                or type(handler_body[-1])
                not in (Nodes.ReturnStatNode, Nodes.RaiseStatNode)
            ):
                self.unsupported(
                    clause.body,
                    "an HPy exception handler must end with a return or raise "
                    "statement",
                )
            for statement in handler_body:
                nested_try = self._find_nested_try_except(statement)
                if nested_try is not None:
                    self.unsupported(
                        nested_try,
                        "nested try/except statements are not implemented",
                    )
            for statement in handler_body[:-1]:
                if type(statement) not in allowed_statement_types:
                    self.unsupported(
                        statement,
                        "handler statements before the terminal return or "
                        "raise must currently be linear assignments, "
                        "expressions, deletions, pass, or supported "
                        "if/while/for control",
                    )
            exception_names = []
            if clause.pattern:
                if default_seen:
                    raise AssertionError("default exception clause is not last")
                for pattern in clause.pattern:
                    pattern = self._unwrap_exception_pattern(pattern)
                    if not (
                        isinstance(pattern, ExprNodes.NameNode)
                        and pattern.entry is not None
                        and pattern.entry.is_builtin
                    ):
                        self.unsupported(
                            pattern,
                            "exception matching currently requires direct "
                            "builtin exception names",
                        )
                    try:
                        self.runtime_api.builtin_exception(
                            pattern.name, context_cname=self.context_cname)
                    except ValueError:
                        self.unsupported(
                            pattern,
                            "builtin exception %s is unavailable in HPy 0.9" %
                            pattern.name,
                        )
                    exception_names.append(pattern.name)
            else:
                default_seen = True
            clauses.append((exception_names, handler_body))

        if not clauses:
            raise AssertionError("try/except statement has no clauses")

        handler_label = "__pyx_hpy_except_%d" % self._next_exception_handler
        self._next_exception_handler += 1
        entry_state = self._snapshot_lifetime_state()
        self.putln("/* try: current-error handler subset */")
        self._push_failure_scope(handler_label)
        for statement in try_body:
            statement.generate_hpy_bootstrap_execution_code(self)
        self._pop_failure_scope(handler_label)
        terminal_state = None

        self._restore_lifetime_state(copy.deepcopy(entry_state))
        self.putln("%s:" % handler_label)
        for exception_names, handler_body in clauses:
            if exception_names:
                conditions = [
                    self.runtime_api.exception_matches(
                        self.runtime_api.builtin_exception(
                            exception_name,
                            context_cname=self.context_cname,
                        ),
                        context_cname=self.context_cname,
                    )
                    for exception_name in exception_names
                ]
                condition = " || ".join(conditions)
            else:
                condition = "1"
            self.putln("if (%s) {" % condition)
            self.indent()
            self.putln("%s;" % self.runtime_api.error_clear(
                context_cname=self.context_cname))
            self._restore_lifetime_state(copy.deepcopy(entry_state))
            for statement in handler_body:
                statement.generate_hpy_bootstrap_execution_code(self)
            if terminal_state is None:
                terminal_state = self._snapshot_lifetime_state()
            self.dedent()
            self.putln("}")

        if not default_seen:
            self._restore_lifetime_state(copy.deepcopy(entry_state))
            self._emit_failure_exit()
        self._restore_lifetime_state(terminal_state)

    def generate_early_return_if(self, node, condition, body):
        self.generate_returning_if(((condition, body),), None)

    def generate_conditional(self, clauses, else_body):
        self._generate_conditional_level(list(clauses), else_body)

    def generate_while_loop(self, condition, body, else_body):
        break_flag = None
        if else_body is not None:
            break_flag = "__pyx_hpy_loop_completed_%d" % self._next_loop
            self._next_loop += 1
            self.putln("int %s = 1;" % break_flag)
        self._loop_stack.append(break_flag)
        self.putln("while (1) {")
        self.indent()
        if condition is not None:
            condition_cname = self.materialize_owned_handle(
                condition.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(condition_cname)
            self._handle_temps.use(condition_cname)
            truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
            self._next_truth += 1
            self.putln("int %s = %s;" % (
                truth_cname,
                self.runtime_api.truth_test(
                    condition_cname, context_cname=self.context_cname),
            ))
            self.close_owned_handle(condition_cname)
            self.put_error_return_if_negative(truth_cname)
            self.putln("if (!%s) break;" % truth_cname)
        loop_state = self._snapshot_lifetime_state()
        self._loop_lifetime_stack.append(loop_state)
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(self)
        # Close body-iteration handles (e.g. nested-loop locals) before
        # rewinding the lifetime bookkeeping for the next iteration.
        self._emit_loop_body_cleanup()
        self._loop_lifetime_stack.pop()
        self.dedent()
        self.putln("}")
        popped_flag = self._loop_stack.pop()
        if popped_flag != break_flag:
            raise AssertionError("bootstrap loop stack changed")
        if else_body is not None:
            self.putln("if (%s) {" % break_flag)
            self.indent()
            for statement in else_body:
                statement.generate_hpy_bootstrap_execution_code(self)
            self.dedent()
            self.putln("}")

    def generate_comprehension(self, node):
        """Emit a list/dict comprehension over sequence-index for-in loops."""
        if getattr(node, "is_async", False):
            self.unsupported(
                node, "async comprehensions are not implemented")
        if not isinstance(
            node.loop, (Nodes.ForInStatNode, Nodes.ForFromStatNode),
        ):
            self.unsupported(
                node,
                "only for-in/for-from list/dict comprehensions over "
                "sequence-index or C-integer range iterables are implemented",
            )
        if node.type is not None and node.type.is_pyset_type:
            self.unsupported(
                node,
                "HPy 0.9 exposes neither public set construction/add operations "
                "nor a SetType context handle; set comprehensions remain blocked",
            )
        if node.type is not None and node.type.is_pydict_type:
            container_cname = self.allocate_owned_handle(
                self.runtime_api.dict_new(context_cname=self.context_cname))
        elif node.type is not None and node.type.is_pylist_type:
            list_type = self.runtime_api.context_constant(
                RuntimeContextConstant.LIST_TYPE,
                context_cname=self.context_cname,
            )
            container_cname = self.allocate_owned_handle(
                self.runtime_api.call_no_args(
                    list_type, context_cname=self.context_cname))
        else:
            self.unsupported(
                node,
                "comprehension type %s is not implemented" % node.type,
            )
        self.put_error_return_if_null(container_cname)
        previous = self._comprehension_targets.get(id(node))
        self._comprehension_targets[id(node)] = container_cname
        try:
            node.loop.generate_hpy_bootstrap_execution_code(self)
        finally:
            if previous is None:
                self._comprehension_targets.pop(id(node), None)
            else:
                self._comprehension_targets[id(node)] = previous
        return container_cname

    def comprehension_target_cname(self, node):
        cname = self._comprehension_targets.get(id(node))
        if cname is None:
            self.unsupported(
                node, "comprehension target container is not bound")
        return cname

    def comprehension_list_append(self, list_cname, item_cname):
        """Append via HPy_CallMethod('append'); keeps ``list_cname`` owned."""
        self._handle_temps.use(list_cname)
        receiver_cname = self.allocate_owned_handle(
            self.runtime_api.duplicate_reference(
                list_cname, context_cname=self.context_cname))
        self.put_error_return_if_null(receiver_cname)
        result_cname = self.call_method_owned_args(
            receiver_cname, "append", [item_cname])
        self.close_owned_handle(result_cname)

    def comprehension_dict_set_item(self, dict_cname, key_cname, value_cname):
        self.use_owned_handles(dict_cname, key_cname, value_cname)
        status_cname = self._emit_status_operation(
            self.runtime_api.dict_set_item(
                dict_cname, key_cname, value_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(value_cname)
        self.close_owned_handle(key_cname)
        self.put_error_return_if_negative(status_cname)

    def load_module_globals_dict(self, node):
        """Owned ``module.__dict__`` for ``globals()`` / module-scope ``locals()``."""
        self.ensure_extension_runtime_owners(node)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                self.module_cname,
                UniversalHPyModuleWriter._c_string("__dict__"),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_sorted_mapping_keys(self, mapping):
        """``list(mapping.keys())`` then ``.sort()`` — used by module ``dir()``."""
        mapping_cname = self.materialize_owned_handle(
            mapping.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(mapping_cname)
        keys_method_cname = self.allocate_owned_handle(
            self.runtime_api.attribute_get_string(
                mapping_cname,
                '"keys"',
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(keys_method_cname)
        self.use_owned_handles(keys_method_cname)
        keys_iterable_cname = self.allocate_owned_handle(
            self.runtime_api.call_no_args(
                keys_method_cname, context_cname=self.context_cname))
        self.close_owned_handle(keys_method_cname)
        self.close_owned_handle(mapping_cname)
        self.put_error_return_if_null(keys_iterable_cname)
        list_type = self.runtime_api.context_constant(
            RuntimeContextConstant.LIST_TYPE,
            context_cname=self.context_cname,
        )
        keys_cname = self.allocate_owned_handle(
            self.runtime_api.call_one_arg(
                list_type,
                keys_iterable_cname,
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(keys_iterable_cname)
        self.put_error_return_if_null(keys_cname)
        sort_receiver = self.allocate_owned_handle(
            self.runtime_api.duplicate_reference(
                keys_cname, context_cname=self.context_cname))
        self.put_error_return_if_null(sort_receiver)
        sort_result = self.call_method_owned_args(sort_receiver, "sort", [])
        self.close_owned_handle(sort_result)
        return keys_cname

    def generate_inlined_generator_expression(self, node):
        """Emit Optimize-inlined list/dict/any/all over sequence-index loops."""
        orig = getattr(node, "orig_func", None)
        if orig == "set" or (
            node.type is not None and node.type.is_pyset_type
        ):
            self.unsupported(
                node,
                "HPy 0.9 exposes neither public set construction/add operations "
                "nor a SetType context handle; set inlined generators remain blocked",
            )
        loop = getattr(node.gen, "loop", None)
        if loop is None and getattr(node.gen, "def_node", None) is not None:
            loop = node.gen.def_node.gbody.body
        if loop is None:
            self.unsupported(
                node, "inlined generator expression has no loop body")
        if not isinstance(
            loop, (Nodes.ForInStatNode, Nodes.ForFromStatNode),
        ):
            self.unsupported(
                node,
                "only sequence-index/range inlined generator expressions "
                "are implemented",
            )
        # Bind genexp free-variable parameters (``.0``, ...) into stable locals.
        def_node = getattr(node.gen, "def_node", None)
        call_parameters = getattr(node.gen, "call_parameters", None) or ()
        if def_node is not None and call_parameters:
            arguments = [
                argument for argument in def_node.args
                if argument.entry is not None and argument.entry.name
            ]
            if len(arguments) != len(call_parameters):
                self.unsupported(
                    node,
                    "inlined generator expression parameter arity mismatch",
                )
            for argument, parameter in zip(arguments, call_parameters):
                self.assign_local(node, argument.entry.name, parameter)
                self.promote_local_slot(node, argument.entry.name)
        if orig in ("any", "all"):
            # Loop body contains returning if/else from Optimize rewrite.
            # Empty iterators fall through to CPython defaults.
            loop.generate_hpy_bootstrap_execution_code(self)
            boolean = (
                RuntimeContextConstant.TRUE
                if orig == "all" else RuntimeContextConstant.FALSE
            )
            result_cname = self.allocate_owned_handle(
                self.runtime_api.duplicate_reference(
                    self.runtime_api.context_constant(
                        boolean, context_cname=self.context_cname),
                    context_cname=self.context_cname,
                ))
            self.put_error_return_if_null(result_cname)
            return result_cname
        if orig == "dict" or (
            node.type is not None and node.type.is_pydict_type
        ):
            container_cname = self.allocate_owned_handle(
                self.runtime_api.dict_new(context_cname=self.context_cname))
        elif orig in ("list", "sorted") or (
            node.type is not None and node.type.is_pylist_type
        ):
            list_type = self.runtime_api.context_constant(
                RuntimeContextConstant.LIST_TYPE,
                context_cname=self.context_cname,
            )
            container_cname = self.allocate_owned_handle(
                self.runtime_api.call_no_args(
                    list_type, context_cname=self.context_cname))
        else:
            self.unsupported(
                node,
                "inlined generator expression %r is not implemented" % orig,
            )
        self.put_error_return_if_null(container_cname)
        target = getattr(node, "target", None)
        target_key = id(target) if target is not None else id(node)
        previous = self._comprehension_targets.get(target_key)
        self._comprehension_targets[target_key] = container_cname
        # ComprehensionAppendNode looks up by target object identity.
        if target is not None:
            self._comprehension_targets[id(target)] = container_cname
        try:
            loop.generate_hpy_bootstrap_execution_code(self)
        finally:
            if previous is None:
                self._comprehension_targets.pop(target_key, None)
                if target is not None:
                    self._comprehension_targets.pop(id(target), None)
            else:
                self._comprehension_targets[target_key] = previous
                if target is not None:
                    self._comprehension_targets[id(target)] = previous
        if orig == "sorted":
            sort_receiver = self.allocate_owned_handle(
                self.runtime_api.duplicate_reference(
                    container_cname, context_cname=self.context_cname))
            self.put_error_return_if_null(sort_receiver)
            sort_result = self.call_method_owned_args(sort_receiver, "sort", [])
            self.close_owned_handle(sort_result)
        return container_cname

    def call_method_owned_args(self, receiver_cname, attribute_name, argument_cnames):
        """Call a method with already owned arg handles; closes receiver and args."""
        argument_cnames = [receiver_cname] + list(argument_cnames)
        name_cname = self.allocate_owned_handle(
            self.runtime_api.unicode_from_utf8(
                UniversalHPyModuleWriter._c_string(str(attribute_name)),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(name_cname)
        if len(argument_cnames) == 1:
            self.use_owned_handles(name_cname, receiver_cname)
            expression = self.runtime_api.call_method_no_args(
                receiver_cname, name_cname, context_cname=self.context_cname)
        else:
            args_cname = self.declare_call_argument_array(argument_cnames)
            self.use_owned_handles(name_cname)
            expression = self.runtime_api.call_method_array(
                name_cname,
                args_cname,
                str(len(argument_cnames)),
                kwnames_cname="",
                context_cname=self.context_cname,
            )
        result_cname = self.allocate_owned_handle(expression)
        for argument_cname in reversed(argument_cnames):
            self.close_owned_handle(argument_cname)
        self.close_owned_handle(name_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_sequence_for_loop(
        self, sequence, target_name, body, else_body, unpack_target=None,
    ):
        sequence_cname, sequence_is_borrowed = _borrow_sequence_source(
            self, sequence)
        length_cname = "__pyx_hpy_sequence_length_%d" % self._next_loop
        index_cname = "__pyx_hpy_sequence_index_%d" % self._next_loop
        self._next_loop += 1
        self._handle_temps.use(sequence_cname)
        self.putln("HPy_ssize_t %s = %s;" % (
            length_cname,
            self.runtime_api.length(
                sequence_cname, context_cname=self.context_cname),
        ))
        self.put_error_return_if_negative(length_cname)
        break_flag = None
        if else_body is not None:
            break_flag = "__pyx_hpy_loop_completed_%d" % self._next_loop
            self._next_loop += 1
            self.putln("int %s = 1;" % break_flag)
        self._loop_stack.append(break_flag)
        self.putln("for (HPy_ssize_t %s = 0; %s < %s; %s++) {" % (
            index_cname, index_cname, length_cname, index_cname))
        self.indent()
        self._handle_temps.use(sequence_cname)
        item_cname = self.allocate_owned_handle(
            self.runtime_api.item_get_index(
                sequence_cname, index_cname,
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(item_cname)
        if unpack_target is not None:
            self._unpack_owned_sequence_into(unpack_target, item_cname)
            self.close_owned_handle(item_cname)
        else:
            self._move_into_owned_slot(
                self._local_values[target_name], item_cname)
        loop_state = self._snapshot_lifetime_state()
        self._loop_lifetime_stack.append(loop_state)
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(self)
        # Nested loops/comprehensions allocate inner locals during the body;
        # close them before restoring the outer iteration snapshot.
        self._emit_loop_body_cleanup()
        self._loop_lifetime_stack.pop()
        self.dedent()
        self.putln("}")
        popped_flag = self._loop_stack.pop()
        if popped_flag != break_flag:
            raise AssertionError("bootstrap loop stack changed")
        if not sequence_is_borrowed:
            self.close_owned_handle(sequence_cname)
        if else_body is not None:
            self.putln("if (%s) {" % break_flag)
            self.indent()
            for statement in else_body:
                statement.generate_hpy_bootstrap_execution_code(self)
            self.dedent()
            self.putln("}")

    def generate_assert_statement(self, condition, exception):
        """Emit assert with optional message through public AssertionError."""
        from . import ExprNodes
        from . import StringEncoding
        self.putln("#ifndef CYTHON_WITHOUT_ASSERTIONS")
        condition_cname = self.materialize_owned_handle(
            condition.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(condition_cname)
        truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
        self._next_truth += 1
        self._handle_temps.use(condition_cname)
        self.putln("int %s = %s;" % (
            truth_cname,
            self.runtime_api.truth_test(
                condition_cname, context_cname=self.context_cname),
        ))
        self.close_owned_handle(condition_cname)
        self.put_error_return_if_negative(truth_cname)
        self.putln("if (!%s) {" % truth_cname)
        self.indent()
        message = getattr(exception, "exc_value", None)
        if message is None:
            exception_cname = self.runtime_api.builtin_exception(
                "AssertionError", context_cname=self.context_cname)
            self.putln("%s;" % self.runtime_api.error_set_none(
                exception_cname, context_cname=self.context_cname))
            self._finish_raised_error()
        elif (
            isinstance(message, ExprNodes.UnicodeNode)
            and "\0" not in message.value
            and not StringEncoding.string_contains_lone_surrogates(
                message.value)
        ):
            self.raise_builtin_string(
                "AssertionError", message.value.as_c_string_literal())
        else:
            # Match CPython assert: PyErr_SetObject(AssertionError, msg).
            value_cname = self.materialize_owned_handle(
                message.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(value_cname)
            exception_cname = self.runtime_api.builtin_exception(
                "AssertionError", context_cname=self.context_cname)
            self.putln("%s;" % self.runtime_api.error_set_object(
                exception_cname, value_cname,
                context_cname=self.context_cname))
            self.close_owned_handle(value_cname)
            self._finish_raised_error()
        self.dedent()
        self.putln("}")
        self.putln("#endif")

    def _materialize_ssize_expression(self, node):
        """Materialize an integer expression as an ``HPy_ssize_t`` C temporary."""
        from . import ExprNodes
        from . import UtilNodes
        while isinstance(node, ExprNodes.CoerceToTempNode):
            node = node.arg
        if isinstance(node, UtilNodes.ResultRefNode):
            cname = self._c_temporary_values.get(id(node))
            if cname is None:
                cname = getattr(node, "result_code", None)
            if cname is None:
                self.unsupported(
                    node, "C loop bound temporary is not bound")
            return cname
        if (
            isinstance(node, ExprNodes.IntNode)
            and node.has_constant_result()
        ):
            cname = "__pyx_hpy_ssize_bound_%d" % self._next_loop
            self._next_loop += 1
            self.putln("HPy_ssize_t %s = %s;" % (
                cname, int(node.constant_result)))
            return cname
        if isinstance(node, ExprNodes.CoerceFromPyTypeNode):
            node = node.arg
        value_cname = self.materialize_owned_handle(
            node.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        cname = "__pyx_hpy_ssize_bound_%d" % self._next_loop
        self._next_loop += 1
        self._handle_temps.use(value_cname)
        self.putln("HPy_ssize_t %s = %s;" % (
            cname,
            self.runtime_api.ssize_t_from_python(
                value_cname, context_cname=self.context_cname),
        ))
        self.putln("if ((%s == -1) && %s) {" % (
            cname,
            self.runtime_api.python_error_occurred(
                context_cname=self.context_cname),
        ))
        self.indent()
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")
        self.close_owned_handle(value_cname)
        return cname

    def generate_for_from_loop(
        self, bound1, relation1, relation2, bound2, step, target_name,
        body, else_body,
    ):
        """Emit a C-integer counted loop with Python-object iteration targets."""
        offset, incop = Nodes.ForFromStatNode.relation_table[relation1]
        start_cname = self._materialize_ssize_expression(bound1)
        stop_cname = self._materialize_ssize_expression(bound2)
        if step is not None:
            step_cname = self._materialize_ssize_expression(step)
            increment = "%s=%s" % (incop[0], step_cname)
        else:
            increment = incop
        if offset:
            start_expr = "(%s%s)" % (start_cname, offset)
        else:
            start_expr = start_cname
        loopvar = "__pyx_hpy_forfrom_%d" % self._next_loop
        self._next_loop += 1
        break_flag = None
        if else_body is not None:
            break_flag = "__pyx_hpy_loop_completed_%d" % self._next_loop
            self._next_loop += 1
            self.putln("int %s = 1;" % break_flag)
        self._loop_stack.append(break_flag)
        self.putln("for (HPy_ssize_t %s = %s; %s %s %s; %s%s) {" % (
            loopvar, start_expr,
            loopvar, relation2, stop_cname,
            loopvar, increment,
        ))
        self.indent()
        item_cname = self.allocate_owned_handle(
            self.runtime_api.ssize_integer_from_cvalue(
                loopvar, context_cname=self.context_cname))
        self.put_error_return_if_null(item_cname)
        self._move_into_owned_slot(
            self._local_values[target_name], item_cname)
        loop_state = self._snapshot_lifetime_state()
        self._loop_lifetime_stack.append(loop_state)
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(self)
        self._emit_loop_body_cleanup()
        self._loop_lifetime_stack.pop()
        self.dedent()
        self.putln("}")
        popped_flag = self._loop_stack.pop()
        if popped_flag != break_flag:
            raise AssertionError("bootstrap loop stack changed")
        if else_body is not None:
            self.putln("if (%s) {" % break_flag)
            self.indent()
            for statement in else_body:
                statement.generate_hpy_bootstrap_execution_code(self)
            self.dedent()
            self.putln("}")

    def _emit_loop_body_cleanup(self):
        """Close owned temps/builders created in the current loop body iteration."""
        if not self._loop_lifetime_stack:
            raise AssertionError("bootstrap loop lifetime stack is empty")
        entry = self._loop_lifetime_stack[-1]
        entry_handles = set(entry[4])
        entry_builders = set(entry[5])
        for cname in reversed(tuple(self._handle_order)):
            if cname in entry_handles:
                continue
            if self._handle_temps.is_active(cname):
                self.close_owned_handle(cname)
        for cname in reversed(tuple(self._builder_order)):
            if cname in entry_builders:
                continue
            if not self._builder_temps.is_active(cname):
                continue
            self._builder_temps.use(cname)
            self.putln(self.runtime_api.sequence_builder_cancel(
                self._builder_contracts[cname],
                cname,
                context_cname=self.context_cname,
            ))
            self._builder_temps.cancel(cname)
            self._builder_temps.release(cname)
            self._builder_order.remove(cname)
            del self._builder_contracts[cname]
        self._restore_lifetime_state(copy.deepcopy(entry))

    def generate_loop_break(self, node):
        if not self._loop_stack:
            self.unsupported(node, "break statement is not inside a supported loop")
        self._emit_loop_body_cleanup()
        break_flag = self._loop_stack[-1]
        if break_flag is not None:
            self.putln("%s = 0;" % break_flag)
        self.putln("break;")

    def generate_loop_continue(self, node):
        if not self._loop_stack:
            self.unsupported(node, "continue statement is not inside a supported loop")
        self._emit_loop_body_cleanup()
        self.putln("continue;")

    def _generate_conditional_level(self, clauses, else_body):
        condition, body = clauses[0]
        condition_cname = self.materialize_owned_handle(
            condition.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(condition_cname)
        truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
        self._next_truth += 1
        self._handle_temps.use(condition_cname)
        self.putln("int %s = %s;" % (
            truth_cname,
            self.runtime_api.truth_test(
                condition_cname, context_cname=self.context_cname),
        ))
        self.close_owned_handle(condition_cname)
        self.put_error_return_if_negative(truth_cname)

        merge_state = self._snapshot_lifetime_state()
        self.putln("if (%s) {" % truth_cname)
        self.indent()
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(self)
        self.dedent()
        self.putln("} else {")
        self._restore_lifetime_state(copy.deepcopy(merge_state))
        self.indent()
        if len(clauses) > 1:
            self._generate_conditional_level(clauses[1:], else_body)
        elif else_body is not None:
            for statement in else_body:
                statement.generate_hpy_bootstrap_execution_code(self)
        self.dedent()
        self.putln("}")
        self._restore_lifetime_state(merge_state)

    def generate_returning_if(self, clauses, else_body):
        for condition, body in clauses:
            self._generate_returning_if_clause(condition, body)
        if else_body is not None:
            self.putln("{")
            self.indent()
            for statement in else_body:
                statement.generate_hpy_bootstrap_execution_code(self)
            self.dedent()
            self.putln("}")

    def _generate_returning_if_clause(self, condition, body):
        condition_cname = self.materialize_owned_handle(
            condition.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(condition_cname)
        truth_cname = "__pyx_hpy_truth_%d" % self._next_truth
        self._next_truth += 1
        self._handle_temps.use(condition_cname)
        self.putln("int %s = %s;" % (
            truth_cname,
            self.runtime_api.truth_test(
                condition_cname, context_cname=self.context_cname),
        ))
        self.close_owned_handle(condition_cname)
        self.put_error_return_if_negative(truth_cname)

        false_path = self._snapshot_lifetime_state()
        self.putln("if (%s) {" % truth_cname)
        self.indent()
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(self)
        self.dedent()
        self.putln("}")
        self._restore_lifetime_state(false_path)

    def declare_call_argument_array(self, argument_cnames):
        cname = "__pyx_hpy_call_args_%d" % self._next_call_array
        self._next_call_array += 1
        self.use_owned_handles(*argument_cnames)
        self.putln("%s %s[] = {%s};" % (
            self.runtime_api.reference_type_cname(),
            cname,
            ", ".join(argument_cnames),
        ))
        return cname

    def generate_positional_call(self, function, arguments):
        if (
            isinstance(function, ExprNodes.AttributeNode)
            and not self.is_extension_field(function)
        ):
            return self.generate_method_call(
                function.obj, function.attribute, arguments)
        callable_cname = None
        callable_is_owned = True
        if not arguments:
            callable_cname = self.borrow_direct_named_value(function)
            callable_is_owned = callable_cname is None
        if callable_cname is None:
            callable_cname = self.materialize_owned_handle(
                function.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(callable_cname)
        argument_cnames = []
        for argument in arguments:
            argument_cname = self.materialize_owned_handle(
                argument.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(argument_cname)
            argument_cnames.append(argument_cname)
        if len(argument_cnames) == 1:
            self.use_owned_handles(callable_cname, argument_cnames[0])
            expression = self.runtime_api.call_one_arg(
                callable_cname,
                argument_cnames[0],
                context_cname=self.context_cname,
            )
        elif argument_cnames:
            args_cname = self.declare_call_argument_array(argument_cnames)
            self.use_owned_handles(callable_cname)
            expression = self.runtime_api.call_positional_array(
                callable_cname,
                args_cname,
                str(len(argument_cnames)),
                context_cname=self.context_cname,
            )
        else:
            self.use_owned_handles(callable_cname)
            expression = self.runtime_api.call_no_args(
                callable_cname, context_cname=self.context_cname)

        result_cname = self.allocate_owned_handle(expression)
        for argument_cname in reversed(argument_cnames):
            self.close_owned_handle(argument_cname)
        if callable_is_owned:
            self.close_owned_handle(callable_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_joined_string(self, values):
        """Concatenate Unicode pieces with HPy_Add (f-string join)."""
        from .ExprNodes import CloneNode, ProxyNode

        parts = []
        for value in values:
            while isinstance(value, (CloneNode, ProxyNode)):
                value = value.arg
            parts.append(value)
        if not parts:
            empty = self.allocate_owned_handle(
                self.runtime_api.unicode_from_utf8(
                    UniversalHPyModuleWriter._c_string(""),
                    context_cname=self.context_cname,
                ))
            self.put_error_return_if_null(empty)
            return empty

        result_cname = self.materialize_owned_handle(
            parts[0].generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(result_cname)
        for part in parts[1:]:
            next_cname = self.materialize_owned_handle(
                part.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(next_cname)
            self.use_owned_handles(result_cname, next_cname)
            combined_cname = self.allocate_owned_handle(
                self.runtime_api.binary_operation(
                    RuntimeBinaryOperation.ADD,
                    result_cname,
                    next_cname,
                    context_cname=self.context_cname,
                ))
            self.close_owned_handle(next_cname)
            self.close_owned_handle(result_cname)
            self.put_error_return_if_null(combined_cname)
            result_cname = combined_cname
        return result_cname

    def generate_formatted_value(self, value, conversion_char, format_spec):
        """Emit !s/!r/!a conversion plus value.__format__(spec) for f-strings."""
        from .StringEncoding import EncodedString

        value_cname = self.materialize_owned_handle(
            value.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)

        if conversion_char in (None, ''):
            converted_cname = value_cname
        elif conversion_char == 's':
            converted_cname = self.allocate_owned_handle(
                self.runtime_api.object_str(
                    value_cname, context_cname=self.context_cname))
            self.close_owned_handle(value_cname)
            self.put_error_return_if_null(converted_cname)
        elif conversion_char == 'r':
            converted_cname = self.allocate_owned_handle(
                self.runtime_api.object_repr(
                    value_cname, context_cname=self.context_cname))
            self.close_owned_handle(value_cname)
            self.put_error_return_if_null(converted_cname)
        elif conversion_char == 'a':
            converted_cname = self.allocate_owned_handle(
                self.runtime_api.object_ascii(
                    value_cname, context_cname=self.context_cname))
            self.close_owned_handle(value_cname)
            self.put_error_return_if_null(converted_cname)
        else:
            self.unsupported(
                value,
                "f-string conversion !%s is not implemented" % conversion_char)

        if format_spec is None:
            format_spec = ExprNodes.UnicodeNode(
                value.pos, value=EncodedString(""))

        return self.generate_method_call_on_cname(
            converted_cname, "__format__", [format_spec])

    def generate_method_call(
        self,
        receiver,
        attribute_name,
        positional_arguments,
        keyword_names=None,
        keyword_values=None,
    ):
        """Emit HPy_CallMethod with args[0] as the receiver (no bound method)."""
        receiver_cname = self.materialize_owned_handle(
            receiver.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(receiver_cname)
        return self.generate_method_call_on_cname(
            receiver_cname,
            attribute_name,
            positional_arguments,
            keyword_names=keyword_names,
            keyword_values=keyword_values,
        )

    def generate_method_call_on_cname(
        self,
        receiver_cname,
        attribute_name,
        positional_arguments,
        keyword_names=None,
        keyword_values=None,
    ):
        if keyword_names is not None and keyword_values is None:
            raise AssertionError("keyword names require keyword values")
        if keyword_values and keyword_names is None:
            raise AssertionError("keyword values require keyword names")

        argument_cnames = [receiver_cname]
        for argument in positional_arguments:
            argument_cname = self.materialize_owned_handle(
                argument.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(argument_cname)
            argument_cnames.append(argument_cname)

        kwnames_cname = None
        positional_count = len(argument_cnames)
        if keyword_names is not None:
            if keyword_names.mult_factor is not None:
                self.unsupported(
                    keyword_names, "expanded keyword names are not implemented")
            if len(keyword_names.args) != len(keyword_values):
                raise AssertionError("keyword name/value count mismatch")
            self._guard_keyword_name_duplicates(keyword_names)
            kwnames_cname = self.materialize_owned_handle(
                keyword_names.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(kwnames_cname)
            for value in keyword_values:
                value_cname = self.materialize_owned_handle(
                    value.generate_hpy_bootstrap_owned_result(self))
                self.put_error_return_if_null(value_cname)
                argument_cnames.append(value_cname)

        name_cname = self.allocate_owned_handle(
            self.runtime_api.unicode_from_utf8(
                UniversalHPyModuleWriter._c_string(str(attribute_name)),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(name_cname)

        if len(argument_cnames) == 1 and kwnames_cname is None:
            self.use_owned_handles(name_cname, receiver_cname)
            expression = self.runtime_api.call_method_no_args(
                receiver_cname, name_cname, context_cname=self.context_cname)
        else:
            args_cname = self.declare_call_argument_array(argument_cnames)
            self.use_owned_handles(name_cname)
            if kwnames_cname is not None:
                self.use_owned_handles(kwnames_cname)
            expression = self.runtime_api.call_method_array(
                name_cname,
                args_cname,
                str(positional_count),
                kwnames_cname="" if kwnames_cname is None else kwnames_cname,
                context_cname=self.context_cname,
            )

        result_cname = self.allocate_owned_handle(expression)
        for argument_cname in reversed(argument_cnames):
            self.close_owned_handle(argument_cname)
        if kwnames_cname is not None:
            self.close_owned_handle(kwnames_cname)
        self.close_owned_handle(name_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_walrus(self, assignment):
        """Evaluate rhs once, assign to a simple name, return an owned copy."""
        lhs = assignment.lhs
        if not isinstance(lhs, ExprNodes.NameNode):
            self.unsupported(
                assignment, "walrus targets must be simple names")
        rhs = assignment.rhs
        while isinstance(rhs, (ExprNodes.CloneNode, ExprNodes.ProxyNode)):
            rhs = rhs.arg
        while type(rhs) in (
            ExprNodes.CoerceToPyTypeNode,
            ExprNodes.CoerceToTempNode,
            ExprNodes.CoerceFromPyTypeNode,
        ):
            rhs = rhs.arg

        value_cname = self.materialize_owned_handle(
            rhs.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(value_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.duplicate_reference(
                value_cname, context_cname=self.context_cname))
        self.put_error_return_if_null(result_cname)

        source_name = lhs.name
        if lhs.entry is not None and lhs.entry.is_pyglobal:
            self.ensure_extension_runtime_owners(assignment)
            self.store_materialized_module_global(
                source_name, value_cname, self.module_cname, publish=True)
        elif source_name in self._stable_local_slots:
            self._move_into_owned_slot(self._local_values[source_name], value_cname)
        else:
            previous = self._local_values.get(source_name)
            if previous is not None:
                self.close_owned_handle(previous)
            self._local_values[source_name] = value_cname
        return result_cname

    def generate_general_call(self, function, positional_args, keyword_args):
        callable_cname = self.materialize_owned_handle(
            function.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(callable_cname)
        positional_cname = self.materialize_owned_handle(
            positional_args.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(positional_cname)
        keyword_cname = None
        if keyword_args is not None:
            keyword_cname = self.materialize_owned_handle(
                keyword_args.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(keyword_cname)

        self.use_owned_handles(callable_cname, positional_cname)
        kwargs_expression = self.runtime_api.null_reference_value()
        if keyword_cname is not None:
            self.use_owned_handles(keyword_cname)
            kwargs_expression = keyword_cname
        result_cname = self.allocate_owned_handle(
            self.runtime_api.call_tuple_dict(
                callable_cname,
                positional_cname,
                kwargs_expression,
                context_cname=self.context_cname,
            ))
        if keyword_cname is not None:
            self.close_owned_handle(keyword_cname)
        self.close_owned_handle(positional_cname)
        self.close_owned_handle(callable_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_arbitrary_integer_literal(self, decimal_value):
        text_cname = self.allocate_owned_handle(
            self.runtime_api.unicode_from_utf8(
                UniversalHPyModuleWriter._c_string(decimal_value),
                context_cname=self.context_cname,
            ))
        self.put_error_return_if_null(text_cname)
        self._handle_temps.use(text_cname)
        long_type = self.runtime_api.context_constant(
            RuntimeContextConstant.LONG_TYPE,
            context_cname=self.context_cname,
        )
        result_cname = self.allocate_owned_handle(
            self.runtime_api.call_one_arg(
                long_type, text_cname, context_cname=self.context_cname))
        self.close_owned_handle(text_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_unicode_from_encoded_bytes(self, data_cname, size):
        bytes_cname = self.allocate_owned_handle(
            self.runtime_api.bytes_from_data(
                data_cname, str(size), context_cname=self.context_cname))
        self.put_error_return_if_null(bytes_cname)
        self._handle_temps.use(bytes_cname)
        result_cname = self.allocate_owned_handle(
            self.runtime_api.unicode_from_encoded_object(
                bytes_cname, '"utf-8"', '"surrogatepass"',
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(bytes_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_imaginary_literal(self, imaginary_value):
        real_cname = self.allocate_owned_handle(
            self.runtime_api.floating_from_cvalue(
                "0.0", context_cname=self.context_cname))
        self.put_error_return_if_null(real_cname)
        imaginary_cname = self.allocate_owned_handle(
            self.runtime_api.floating_from_cvalue(
                imaginary_value, context_cname=self.context_cname))
        self.put_error_return_if_null(imaginary_cname)
        args_cname = self.declare_call_argument_array(
            [real_cname, imaginary_cname])
        complex_type = self.runtime_api.context_constant(
            RuntimeContextConstant.COMPLEX_TYPE,
            context_cname=self.context_cname,
        )
        result_cname = self.allocate_owned_handle(
            self.runtime_api.call_positional_array(
                complex_type, args_cname, "2",
                context_cname=self.context_cname,
            ))
        self.close_owned_handle(imaginary_cname)
        self.close_owned_handle(real_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_keyword_call(
        self, function, positional_arguments, keyword_names, keyword_values,
    ):
        if (
            isinstance(function, ExprNodes.AttributeNode)
            and not self.is_extension_field(function)
        ):
            return self.generate_method_call(
                function.obj,
                function.attribute,
                positional_arguments,
                keyword_names=keyword_names,
                keyword_values=keyword_values,
            )
        if keyword_names.mult_factor is not None:
            self.unsupported(keyword_names, "expanded keyword names are not implemented")
        if len(keyword_names.args) != len(keyword_values):
            raise AssertionError("keyword name/value count mismatch")

        self._guard_keyword_name_duplicates(keyword_names)

        callable_cname = self.materialize_owned_handle(
            function.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(callable_cname)
        argument_cnames = []
        for argument in positional_arguments:
            argument_cname = self.materialize_owned_handle(
                argument.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(argument_cname)
            argument_cnames.append(argument_cname)

        kwnames_cname = self.materialize_owned_handle(
            keyword_names.generate_hpy_bootstrap_owned_result(self))
        self.put_error_return_if_null(kwnames_cname)
        for value in keyword_values:
            value_cname = self.materialize_owned_handle(
                value.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(value_cname)
            argument_cnames.append(value_cname)

        args_cname = self.declare_call_argument_array(argument_cnames)
        self.use_owned_handles(callable_cname, kwnames_cname)
        expression = self.runtime_api.call_array_with_keyword_names(
            callable_cname,
            args_cname,
            str(len(positional_arguments)),
            kwnames_cname,
            context_cname=self.context_cname,
        )
        result_cname = self.allocate_owned_handle(expression)
        for argument_cname in reversed(argument_cnames):
            self.close_owned_handle(argument_cname)
        self.close_owned_handle(kwnames_cname)
        self.close_owned_handle(callable_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def generate_slice(self, start, stop, step):
        argument_cnames = []
        for argument in (start, stop, step):
            argument_cname = self.materialize_owned_handle(
                argument.generate_hpy_bootstrap_owned_result(self))
            self.put_error_return_if_null(argument_cname)
            argument_cnames.append(argument_cname)
        args_cname = self.declare_call_argument_array(argument_cnames)
        slice_type = self.runtime_api.context_constant(
            RuntimeContextConstant.SLICE_TYPE,
            context_cname=self.context_cname,
        )
        result_cname = self.allocate_owned_handle(
            self.runtime_api.call_positional_array(
                slice_type, args_cname, "3",
                context_cname=self.context_cname,
            ))
        for argument_cname in reversed(argument_cnames):
            self.close_owned_handle(argument_cname)
        self.put_error_return_if_null(result_cname)
        return result_cname

    def allocate_sequence_builder(self, builder, size):
        cname = "__pyx_hpy_builder_%d" % self._next_builder
        self._next_builder += 1
        self._builder_temps.allocate(cname)
        self._builder_contracts[cname] = builder
        self._builder_order.append(cname)
        expression = self.runtime_api.sequence_builder_new(
            builder, str(size), context_cname=self.context_cname)
        self.putln("%s %s = %s;" % (
            builder.builder_type_cname, cname, expression))
        return cname

    def set_sequence_builder_item(self, builder, builder_cname, index, item_cname):
        self._builder_temps.use(builder_cname)
        self._handle_temps.use(item_cname)
        self.putln("%s;" % self.runtime_api.sequence_builder_set(
            builder,
            builder_cname,
            str(index),
            item_cname,
            context_cname=self.context_cname,
        ))

    def build_sequence(self, builder, builder_cname):
        self._builder_temps.use(builder_cname)
        expression = self.runtime_api.sequence_builder_build(
            builder, builder_cname, context_cname=self.context_cname)
        self._builder_temps.build(builder_cname)
        self._builder_temps.release(builder_cname)
        self._builder_order.remove(builder_cname)
        del self._builder_contracts[builder_cname]
        return self.allocate_owned_handle(expression)

    def put_error_return_if_null(self, cname):
        self._handle_temps.use(cname)
        self.putln("if (%s) {" % self.runtime_api.null_check(cname))
        self.indent()
        if self.rollback_module_publications:
            self._emit_module_failure_exit_preserving_memory(
                exclude_handles=(cname,))
        else:
            self._emit_failure_exit(exclude_handles=(cname,))
        self.dedent()
        self.putln("}")

    def put_error_return_if_null_with_exception(self, cname):
        """Fail only when ``cname`` is null and an exception is set.

        Used by ``locals()``/``vars()`` so intentional unbound slots stay
        omitted while failed ``HPy_Dup`` still propagates.
        """
        self._handle_temps.use(cname)
        self.putln("if (%s) {" % self.runtime_api.null_check(cname))
        self.indent()
        self.putln("if (%s) {" % self.runtime_api.python_error_occurred(
            context_cname=self.context_cname))
        self.indent()
        if self.rollback_module_publications:
            self._emit_module_failure_exit_preserving_memory(
                exclude_handles=(cname,))
        else:
            self._emit_failure_exit(exclude_handles=(cname,))
        self.dedent()
        self.putln("}")
        self.dedent()
        self.putln("}")

    def put_error_return_if_negative(self, expression):
        self.putln("if (%s < 0) {" % expression)
        self.indent()
        if self.rollback_module_publications:
            self._emit_module_failure_exit_preserving_memory()
        else:
            self._emit_failure_exit()
        self.dedent()
        self.putln("}")

    def _emit_module_failure_exit_preserving_memory(
        self, exclude_handles=(),
    ):
        if not self.rollback_module_publications:
            raise AssertionError(
                "module publication rollback is not enabled")
        if self._failure_scopes:
            raise AssertionError(
                "module publications cannot occur inside failure scopes")
        memory_error = self.runtime_api.builtin_exception(
            "MemoryError", context_cname=self.context_cname)
        self.putln("if (%s) {" % self.runtime_api.exception_matches(
            memory_error, context_cname=self.context_cname))
        self.indent()
        self._put_failure_cleanup(exclude_handles=exclude_handles)
        for rollback in self._module_publication_rollbacks:
            self.putln(rollback)
        # HPy 0.9 has no public error fetch/restore API.  Successful rollback
        # deletions may clear the active error, so re-establish the error that
        # was positively matched before cleanup.
        self.putln("%s;" % self.runtime_api.error_no_memory(
            context_cname=self.context_cname))
        self.putln("return %s;" % self.failure_return_value)
        self.dedent()
        self.putln("}")
        # HPy 0.9 cannot fetch and restore an arbitrary active exception.
        # Deleting published attributes here can clear that exception on some
        # runtimes, making the loader report a SystemError. A failed module is
        # discarded, so close owned resources but leave its attributes alone.
        self._emit_failure_exit(
            exclude_handles=exclude_handles,
            include_failure_epilogue=False,
        )

    def put_module_publication_error_if_negative(self, expression):
        if not self.rollback_module_publications:
            raise AssertionError(
                "module publication rollback is not enabled")
        if self._failure_scopes:
            raise AssertionError(
                "module publications cannot occur inside failure scopes")
        self.putln("if (%s < 0) {" % expression)
        self.indent()
        self._emit_module_failure_exit_preserving_memory()
        self.dedent()
        self.putln("}")

    def parse_keyword_arguments(
            self, function_name, arguments, keyword_dictionary=False):
        has_defaults = any(argument.default is not None for argument in arguments)
        self._validate_positional_argument_count(function_name, arguments)
        if not keyword_dictionary:
            self._validate_keyword_arguments(function_name, arguments)
        tracker_cname = self._argument_tracker_cname
        self.putln("static const char *keywords[] = {")
        self.indent()
        for argument in arguments:
            keyword = '""' if argument.pos_only else argument.name_cstring
            self.putln("%s," % keyword)
        self.putln("NULL,")
        self.dedent()
        self.putln("};")
        self.putln("%s %s;" % (
            self.runtime_api.argument_tracker_type_cname(), tracker_cname))

        output_cnames = []
        for index, argument in enumerate(arguments):
            cname = "__pyx_hpy_arg_%d" % index
            output_cnames.append(cname)
            self.putln("%s %s = %s;" % (
                self.runtime_api.reference_type_cname(),
                cname,
                self.runtime_api.null_reference_value(),
            ))

        format_units = "O" * len(arguments)
        if has_defaults:
            format_units = "|" + format_units
        format_cname = '"%s:%s"' % (format_units, function_name)
        parse_method = (
            self.runtime_api.parse_keyword_dictionary
            if keyword_dictionary
            else self.runtime_api.parse_keyword_arguments
        )
        parse_call = parse_method(
            tracker_cname,
            "args",
            "nargs",
            "kw" if keyword_dictionary else "kwnames",
            format_cname,
            "keywords",
            output_cnames,
            context_cname=self.context_cname,
        )
        self.putln("if (!%s) {" % parse_call)
        self.indent()
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")

        self._tracker_temps.allocate(tracker_cname)
        if has_defaults:
            self._materialize_defaulted_arguments(
                function_name, arguments, output_cnames)
        else:
            for argument, cname in zip(arguments, output_cnames):
                self.bind_borrowed_argument(
                    argument.entry.name, cname, tracker_owned=True)

    def bind_required_positional_arguments(
            self, function_name, arguments, keyword_cname=None):
        """Bind an exact positional-only argument array without a tracker."""
        if keyword_cname is not None:
            self.reject_keyword_arguments(function_name, keyword_cname)
        type_error = self.runtime_api.context_constant(
            RuntimeContextConstant.TYPE_ERROR,
            context_cname=self.context_cname,
        )
        argument_count = len(arguments)
        self.putln("if (nargs != %d) {" % argument_count)
        self.indent()
        noun = "argument" if argument_count == 1 else "arguments"
        self.putln("%s;" % self.runtime_api.error_set_string(
            type_error,
            UniversalHPyModuleWriter._c_string(
                "%s() takes exactly %d %s" % (
                    function_name, argument_count, noun)),
            context_cname=self.context_cname,
        ))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")
        for index, argument in enumerate(arguments):
            self.bind_borrowed_argument(
                argument.entry.name, "args[%d]" % index)

    def reject_keyword_arguments(self, function_name, keyword_cname):
        self.putln("if (!%s) {" % self.runtime_api.null_check(keyword_cname))
        self.indent()
        keyword_count = "__pyx_hpy_positional_kw_count"
        self.putln("HPy_ssize_t %s = %s;" % (
            keyword_count,
            self.runtime_api.length(
                keyword_cname, context_cname=self.context_cname),
        ))
        self.putln("if (%s < 0) {" % keyword_count)
        self.indent()
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")
        self.putln("if (%s != 0) {" % keyword_count)
        self.indent()
        type_error = self.runtime_api.context_constant(
            RuntimeContextConstant.TYPE_ERROR,
            context_cname=self.context_cname,
        )
        self.putln("%s;" % self.runtime_api.error_set_string(
            type_error,
            UniversalHPyModuleWriter._c_string(
                "%s() does not accept keyword arguments" % function_name),
            context_cname=self.context_cname,
        ))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")
        self.dedent()
        self.putln("}")

    def _materialize_defaulted_arguments(
        self, function_name, arguments, output_cnames,
    ):
        self.ensure_extension_runtime_owners()
        if self.default_registry is None or self.default_owner_cname is None:
            raise AssertionError(
                "default arguments require interpreter-owned storage")
        null_value = self.runtime_api.null_reference_value()
        type_error = self.runtime_api.context_constant(
            RuntimeContextConstant.TYPE_ERROR,
            context_cname=self.context_cname,
        )
        for argument, parsed_cname in zip(arguments, output_cnames):
            slot_cname = self.allocate_owned_handle(null_value)
            self.putln("if (!%s) {" % self.runtime_api.null_check(parsed_cname))
            self.indent()
            self.putln("%s = %s;" % (
                slot_cname,
                self.runtime_api.duplicate_reference(
                    parsed_cname, context_cname=self.context_cname),
            ))
            self.dedent()
            attribute_name = self.default_registry.attribute_for_argument(argument)
            if attribute_name is not None:
                self.putln("} else {")
                self.indent()
                self.putln("%s = %s;" % (
                    slot_cname,
                    self.runtime_api.attribute_get_string(
                        self.default_owner_cname,
                        UniversalHPyModuleWriter._c_string(attribute_name),
                        context_cname=self.context_cname,
                    ),
                ))
                self.dedent()
                self.putln("}")
            else:
                self.putln("} else {")
                self.indent()
                message = UniversalHPyModuleWriter._c_string(
                    "%s() missing required argument '%s'" % (
                        function_name, argument.entry.name))
                self.putln("%s;" % self.runtime_api.error_set_string(
                    type_error, message, context_cname=self.context_cname))
                self._emit_failure_exit()
                self.dedent()
                self.putln("}")
            self.put_error_return_if_null(slot_cname)
            self._local_values[argument.entry.name] = slot_cname
        self._close_argument_tracker()

    def _validate_positional_argument_count(self, function_name, arguments):
        positional_limit = len(arguments)
        for index, argument in enumerate(arguments):
            if argument.kw_only:
                positional_limit = index
                break
        self.putln("if (nargs > %d) {" % positional_limit)
        self.indent()
        type_error = self.runtime_api.context_constant(
            RuntimeContextConstant.TYPE_ERROR,
            context_cname=self.context_cname,
        )
        message = '"%s() received too many positional arguments"' % function_name
        self.putln("%s;" % self.runtime_api.error_set_string(
            type_error, message, context_cname=self.context_cname))
        self._emit_failure_exit()
        self.dedent()
        self.putln("}")

    def _validate_keyword_arguments(self, function_name, arguments):
        """Restore call semantics missing from HPy 0.9's keyword parser."""
        keyword_arguments = [
            (index, argument)
            for index, argument in enumerate(arguments)
            if not argument.pos_only
        ]
        keyword_count = "__pyx_hpy_kw_count"
        keyword_index = "__pyx_hpy_kw_index"
        keyword_name = "__pyx_hpy_kw_name"
        keyword_size = "__pyx_hpy_kw_size"
        keyword_utf8 = "__pyx_hpy_kw_utf8"
        parameter_index = "__pyx_hpy_parameter_index"
        failure_value = self.failure_return_value

        self.putln("if (!%s) {" % self.runtime_api.null_check("kwnames"))
        self.indent()
        self.putln("HPy_ssize_t %s = %s;" % (
            keyword_count,
            self.runtime_api.length(
                "kwnames", context_cname=self.context_cname),
        ))
        self.putln("if (%s < 0) {" % keyword_count)
        self.indent()
        self._emit_failure_exit(failure_value=failure_value)
        self.dedent()
        self.putln("}")
        self.putln("for (HPy_ssize_t %s = 0; %s < %s; %s++) {" % (
            keyword_index, keyword_index, keyword_count, keyword_index))
        self.indent()
        self.putln("%s %s = %s;" % (
            self.runtime_api.reference_type_cname(),
            keyword_name,
            self.runtime_api.item_get_index(
                "kwnames", keyword_index, context_cname=self.context_cname),
        ))
        self.putln("if (%s) {" % self.runtime_api.null_check(keyword_name))
        self.indent()
        self._emit_failure_exit(failure_value=failure_value)
        self.dedent()
        self.putln("}")
        self.putln("HPy_ssize_t %s;" % keyword_size)
        self.putln("const char *%s = %s;" % (
            keyword_utf8,
            self.runtime_api.unicode_as_utf8_and_size(
                keyword_name, keyword_size,
                context_cname=self.context_cname,
            ),
        ))
        self.putln("if (%s == NULL) {" % keyword_utf8)
        self.indent()
        self.putln(self.runtime_api.close_reference(
            keyword_name, context_cname=self.context_cname))
        self._emit_failure_exit(failure_value=failure_value)
        self.dedent()
        self.putln("}")
        self.putln("int %s = -1;" % parameter_index)
        for branch_index, (index, argument) in enumerate(keyword_arguments):
            condition = (
                "%s == (HPy_ssize_t)(sizeof(%s) - 1) && "
                "memcmp(%s, %s, sizeof(%s) - 1) == 0" % (
                    keyword_size,
                    argument.name_cstring,
                    keyword_utf8,
                    argument.name_cstring,
                    argument.name_cstring,
                )
            )
            branch = "if" if branch_index == 0 else "else if"
            self.putln("%s (%s) {" % (branch, condition))
            self.indent()
            self.putln("%s = %d;" % (parameter_index, index))
            self.dedent()
            self.putln("}")
        self.putln(self.runtime_api.close_reference(
            keyword_name, context_cname=self.context_cname))
        type_error = self.runtime_api.context_constant(
            RuntimeContextConstant.TYPE_ERROR,
            context_cname=self.context_cname,
        )
        self.putln("if (%s < 0) {" % parameter_index)
        self.indent()
        message = '"%s() got an unexpected keyword argument"' % function_name
        self.putln("%s;" % self.runtime_api.error_set_string(
            type_error, message, context_cname=self.context_cname))
        self._emit_failure_exit(failure_value=failure_value)
        self.dedent()
        self.putln("}")
        self.putln("if ((size_t)%s < nargs) {" % parameter_index)
        self.indent()
        message = '"%s() got multiple values for an argument"' % function_name
        self.putln("%s;" % self.runtime_api.error_set_string(
            type_error, message, context_cname=self.context_cname))
        self._emit_failure_exit(failure_value=failure_value)
        self.dedent()
        self.putln("}")
        self.dedent()
        self.putln("}")
        self.dedent()
        self.putln("}")

    def _put_failure_cleanup(
        self, exclude_handles=(), include_failure_epilogue=True,
    ):
        failure_scope = (
            self._failure_scopes[-1] if self._failure_scopes else None)
        preserved_handles = (
            failure_scope["handles"] if failure_scope is not None else set())
        live_handles = (
            set(self._handle_temps.live_owned_handles())
            - set(exclude_handles)
            - preserved_handles
        )
        for cname in reversed(self._handle_order):
            if cname in live_handles:
                self.putln(self.runtime_api.close_reference(
                    cname,
                    null_safe=True,
                    context_cname=self.context_cname,
                ))
        preserved_builders = (
            failure_scope["builders"] if failure_scope is not None else set())
        live_builders = (
            set(self._builder_temps.live_builders()) - preserved_builders)
        for cname in reversed(self._builder_order):
            if cname in live_builders:
                self.putln(self.runtime_api.sequence_builder_cancel(
                    self._builder_contracts[cname],
                    cname,
                    context_cname=self.context_cname,
                ))
        preserved_trackers = (
            failure_scope["trackers"] if failure_scope is not None else set())
        for cname in reversed(tuple(self._tracker_temps.live_trackers())):
            if cname in preserved_trackers:
                continue
            self.putln(self.runtime_api.close_argument_tracker(
                cname, context_cname=self.context_cname))
        if failure_scope is None and include_failure_epilogue:
            for line in self.failure_epilogue:
                self.putln(line)

    def _push_failure_scope(self, label):
        if self._failure_scopes:
            raise AssertionError("nested bootstrap failure scopes are disabled")
        scope = {
            "label": label,
            "handles": set(self._handle_temps.live_owned_handles()),
            "builders": set(self._builder_temps.live_builders()),
            "trackers": set(self._tracker_temps.live_trackers()),
        }
        self._failure_scopes.append(scope)

    def _pop_failure_scope(self, label):
        if not self._failure_scopes:
            raise AssertionError("bootstrap failure scope stack is empty")
        scope = self._failure_scopes.pop()
        if scope["label"] != label:
            raise AssertionError("bootstrap failure scope changed")

    def _emit_failure_exit(
        self, exclude_handles=(), failure_value=None,
        include_failure_epilogue=True,
    ):
        self._put_failure_cleanup(
            exclude_handles=exclude_handles,
            include_failure_epilogue=include_failure_epilogue,
        )
        if self._failure_scopes:
            self.putln("goto %s;" % self._failure_scopes[-1]["label"])
        else:
            self.putln("return %s;" % (
                self.failure_return_value
                if failure_value is None else failure_value))

    def _close_argument_tracker(self):
        tracker_cname = self._argument_tracker_cname
        if not self._tracker_temps.is_active(tracker_cname):
            return
        for source_name in tuple(self._tracker_owned_arguments):
            cname = self._borrowed_arguments.pop(source_name)
            self._handle_temps.release(cname)
        self._tracker_owned_arguments.clear()
        self._tracker_temps.use(tracker_cname)
        self.putln(self.runtime_api.close_argument_tracker(
            tracker_cname, context_cname=self.context_cname))
        self._tracker_temps.close(tracker_cname)
        self._tracker_temps.release(tracker_cname)

    def return_owned_result(self, result):
        if not self._handle_temps.is_active(result):
            result = self.allocate_owned_handle(result)
            self.put_error_return_if_null(result)
        if self.native_return_kind is not None:
            self._return_native_from_owned_handle(result)
            return
        if self._handle_temps.is_active(result):
            self._handle_temps.move(result)
            self._handle_temps.release(result)
            self._handle_order.remove(result)
        self._close_remaining_owned_handles()
        self._close_argument_tracker()
        self.putln("return %s;" % result)

    def _return_native_from_owned_handle(self, value_cname):
        """Convert an owned HPy return for ``__len__``/``__bool__``/``__hash__``."""
        self._handle_temps.use(value_cname)
        if self.native_return_kind == "ssize":
            length_cname = "__pyx_hpy_length_%d" % self._next_status
            self._next_status += 1
            self.putln("HPy_ssize_t %s = %s;" % (
                length_cname,
                self.runtime_api.ssize_t_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure(
                "(%s == -1) && %s" % (
                    length_cname,
                    self.runtime_api.python_error_occurred(
                        context_cname=self.context_cname),
                ))
            self.close_owned_handle(value_cname)
            self.putln("if (%s < 0) {" % length_cname)
            self.indent()
            self.putln("%s;" % self.runtime_api.error_set_string(
                self.runtime_api.builtin_exception(
                    "ValueError", context_cname=self.context_cname),
                '"__len__() should return >= 0"',
                context_cname=self.context_cname,
            ))
            self._emit_failure_exit(failure_value="-1")
            self.dedent()
            self.putln("}")
            self._close_remaining_owned_handles()
            self._close_argument_tracker()
            self.putln("return %s;" % length_cname)
            return
        if self.native_return_kind == "bool":
            bool_cname = "__pyx_hpy_bool_%d" % self._next_status
            self._next_status += 1
            self.putln("long %s = %s;" % (
                bool_cname,
                self.runtime_api.signed_long_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure(
                "(%s == -1) && %s" % (
                    bool_cname,
                    self.runtime_api.python_error_occurred(
                        context_cname=self.context_cname),
                ))
            self._put_native_range_failure(
                "(%s < INT_MIN) || (%s > INT_MAX)" % (
                    bool_cname, bool_cname),
                "int",
            )
            self.close_owned_handle(value_cname)
            self._close_remaining_owned_handles()
            self._close_argument_tracker()
            self.putln("return (int)%s;" % bool_cname)
            return
        if self.native_return_kind == "hash":
            long_type = self.runtime_api.context_constant(
                RuntimeContextConstant.LONG_TYPE,
                context_cname=self.context_cname,
            )
            self.putln("if (!%s) {" % self.runtime_api.type_check(
                value_cname, long_type, context_cname=self.context_cname))
            self.indent()
            self.putln("%s;" % self.runtime_api.error_set_string(
                self.runtime_api.builtin_exception(
                    "TypeError", context_cname=self.context_cname),
                '"__hash__ method should return an integer"',
                context_cname=self.context_cname,
            ))
            self._emit_failure_exit(failure_value="-1")
            self.dedent()
            self.putln("}")
            hash_cname = "__pyx_hpy_hash_%d" % self._next_status
            self._next_status += 1
            converted_cname = "__pyx_hpy_hash_value_%d" % self._next_status
            self._next_status += 1
            self.putln("HPy_ssize_t %s = %s;" % (
                converted_cname,
                self.runtime_api.ssize_t_from_python(
                    value_cname, context_cname=self.context_cname),
            ))
            self.putln("HPy_hash_t %s;" % hash_cname)
            self.putln("if ((%s == -1) && %s) {" % (
                converted_cname,
                self.runtime_api.python_error_occurred(
                    context_cname=self.context_cname),
            ))
            self.indent()
            overflow_error = self.runtime_api.builtin_exception(
                "OverflowError", context_cname=self.context_cname)
            self.putln("if (!%s) {" % self.runtime_api.exception_matches(
                overflow_error, context_cname=self.context_cname))
            self.indent()
            self._emit_failure_exit()
            self.dedent()
            self.putln("}")
            self.putln("%s;" % self.runtime_api.error_clear(
                context_cname=self.context_cname))
            self.putln("%s = %s;" % (
                hash_cname,
                self.runtime_api.object_hash(
                    value_cname, context_cname=self.context_cname),
            ))
            self._put_native_conversion_failure(
                "(%s == -1) && %s" % (
                    hash_cname,
                    self.runtime_api.python_error_occurred(
                        context_cname=self.context_cname),
                ))
            self.dedent()
            self.putln("} else {")
            self.indent()
            self.putln("%s = (HPy_hash_t)%s;" % (
                hash_cname, converted_cname))
            self.dedent()
            self.putln("}")
            self.putln("if (%s == -1) %s = -2;" % (
                hash_cname, hash_cname))
            self.close_owned_handle(value_cname)
            self._close_remaining_owned_handles()
            self._close_argument_tracker()
            self.putln("return %s;" % hash_cname)
            return
        raise AssertionError(
            "unknown native_return_kind %r" % self.native_return_kind)

    def assert_function_exit(self):
        self._handle_temps.assert_no_live_owned_handles()
        self._builder_temps.assert_no_live_builders()
        self._tracker_temps.assert_no_live_trackers()
        if self._failure_scopes:
            raise AssertionError("bootstrap failure scopes remain live")


class _HPyNameRegistry:
    """Stable classification of module-global and builtin source names."""

    def __init__(self):
        self._entries = {}
        self._order = []

    def _require(self, source_name, kind):
        existing = self._entries.get(source_name)
        if existing is not None:
            if existing[0] != kind:
                raise ValueError(
                    "HPy global %s requested as both %s and %s" %
                    (source_name, existing[0], kind))
            return existing[1]
        cname = "__pyx_hpy_global_%d" % len(self._order)
        self._entries[source_name] = (kind, cname)
        self._order.append(source_name)
        return cname

    def require_module_global(self, source_name):
        return self._require(source_name, "module")

    def require_builtin(self, source_name):
        return self._require(source_name, "builtin")

    def entries(self, kind=None):
        for source_name in self._order:
            entry_kind, cname = self._entries[source_name]
            if kind is None or kind == entry_kind:
                yield source_name, cname


class _HPyConstantRegistry:
    """Deterministic interpreter-owned cache names for immutable literals."""

    ATTRIBUTE_PREFIX = "__pyx_hpy_const_"

    def __init__(self):
        self._entries = []
        self._key_to_attribute = {}
        self._node_attributes = {}

    @classmethod
    def constant_key(cls, node):
        node_type = type(node)
        if node_type is ExprNodes.NoneNode:
            return ("none",)
        if node_type is ExprNodes.BoolNode:
            return ("bool", bool(node.value))
        if node_type is ExprNodes.IntNode:
            try:
                return ("int", int(node.value, 0))
            except ValueError:
                return None
        if node_type is ExprNodes.FloatNode:
            return ("float", str(node.value))
        if node_type is ExprNodes.ImagNode:
            return ("imag", str(node.value))
        if node_type is ExprNodes.UnicodeNode:
            return ("unicode", str(node.value))
        if node_type is ExprNodes.BytesNode:
            return ("bytes", node.value.byteencode())
        if node_type is ExprNodes.TupleNode:
            if (
                node.mult_factor is not None
                or node.unpacked_items is not None
                or any(arg.is_starred for arg in node.args)
            ):
                return None
            item_keys = []
            for arg in node.args:
                item_key = cls.constant_key(arg)
                if item_key is None:
                    return None
                item_keys.append(item_key)
            return ("tuple", tuple(item_keys))
        return None

    def register_node(self, node):
        node_type = type(node)
        if node_type not in (
            ExprNodes.NoneNode,
            ExprNodes.BoolNode,
            ExprNodes.IntNode,
            ExprNodes.FloatNode,
            ExprNodes.ImagNode,
            ExprNodes.UnicodeNode,
            ExprNodes.BytesNode,
            ExprNodes.TupleNode,
        ):
            return None
        key = self.constant_key(node)
        if key is None:
            return None
        attribute_name = self._key_to_attribute.get(key)
        if attribute_name is None:
            attribute_name = "%s%d" % (self.ATTRIBUTE_PREFIX, len(self._entries))
            self._key_to_attribute[key] = attribute_name
            self._entries.append((attribute_name, node))
        self._node_attributes[id(node)] = attribute_name
        return attribute_name

    def attribute_for_node(self, node):
        attribute_name = self._node_attributes.get(id(node))
        if attribute_name is not None:
            return attribute_name
        # Coerced/cloned literals share the cache key, not the node id.
        key = self.constant_key(node)
        if key is None:
            return None
        return self._key_to_attribute.get(key)

    def entries(self):
        return iter(self._entries)


class _HPyDefaultRegistry:
    """Per-definition storage for defaults evaluated once by module exec."""

    ATTRIBUTE_PREFIX = "__pyx_hpy_default_"

    def __init__(self):
        self._entries = []
        self._argument_attributes = {}
        self._attribute_arguments = {}

    def register_argument(self, argument, default_node=None):
        if argument.default is None:
            return None
        if default_node is None:
            default_node = argument.default
        attribute_name = "%s%d" % (self.ATTRIBUTE_PREFIX, len(self._entries))
        self._entries.append((attribute_name, default_node))
        argument_id = id(argument)
        self._argument_attributes[argument_id] = attribute_name
        self._attribute_arguments[attribute_name] = argument_id
        return attribute_name

    def attribute_for_argument(self, argument):
        return self._argument_attributes.get(id(argument))

    def argument_id_for_attribute(self, attribute_name):
        return self._attribute_arguments.get(attribute_name)

    def entries(self):
        return iter(self._entries)


class UniversalHPyModuleWriter:
    """Render the currently supported Cython AST subset as Universal HPy C."""

    BUILTINS_ATTRIBUTE = "__pyx_hpy_builtins"
    MODULE_ATTRIBUTE = "__pyx_hpy_module"
    TYPE_SLOT_MARKER_PREFIX = "__pyx_hpy_slot_owner_"
    NUMERIC_BINARY_FAMILIES = (
        ("nb_add", "__add__", "__radd__", "nb_inplace_add", "__iadd__"),
        ("nb_subtract", "__sub__", "__rsub__", "nb_inplace_subtract", "__isub__"),
        ("nb_multiply", "__mul__", "__rmul__", "nb_inplace_multiply", "__imul__"),
        ("nb_remainder", "__mod__", "__rmod__", "nb_inplace_remainder", "__imod__"),
        ("nb_divmod", "__divmod__", "__rdivmod__", None, None),
        ("nb_floor_divide", "__floordiv__", "__rfloordiv__",
         "nb_inplace_floor_divide", "__ifloordiv__"),
        ("nb_true_divide", "__truediv__", "__rtruediv__",
         "nb_inplace_true_divide", "__itruediv__"),
        ("nb_lshift", "__lshift__", "__rlshift__", "nb_inplace_lshift", "__ilshift__"),
        ("nb_rshift", "__rshift__", "__rrshift__", "nb_inplace_rshift", "__irshift__"),
        ("nb_and", "__and__", "__rand__", "nb_inplace_and", "__iand__"),
        ("nb_xor", "__xor__", "__rxor__", "nb_inplace_xor", "__ixor__"),
        ("nb_or", "__or__", "__ror__", "nb_inplace_or", "__ior__"),
        ("nb_matrix_multiply", "__matmul__", "__rmatmul__",
         "nb_inplace_matrix_multiply", "__imatmul__"),
    )

    def __init__(self, module_node, runtime_api):
        self.module_node = module_node
        self.runtime_api = runtime_api
        self.name_registry = _HPyNameRegistry()
        self.constant_registry = _HPyConstantRegistry()
        self.default_registry = _HPyDefaultRegistry()

    def render(self):
        module_name = str(self.module_node.full_module_name)
        module_name_parts = module_name.split(".")
        if not all(_C_IDENTIFIER.match(part) for part in module_name_parts):
            self.unsupported(
                self.module_node,
                "Universal HPy module-name components must be C identifiers",
            )
        module_init_name = module_name_parts[-1]

        methods, module_stats, extension_types, external_c_blocks = (
            self.module_node.hpy_bootstrap_contents(self))

        defaultable_methods = list(methods)
        for extension_type in extension_types:
            defaultable_methods.extend(
                self._extension_type_methods(extension_type))
        for method in defaultable_methods:
            for argument_index, argument in enumerate(method.args):
                if argument.default is not None:
                    if (
                        method.name in ("__pow__", "__rpow__", "__ipow__")
                        and argument_index == 2
                    ):
                        # The ternary slot always supplies its modulus handle;
                        # Cython requires this source-level default to be None.
                        continue
                    # Any expression the Universal bootstrap emitter can evaluate
                    # is allowed. Unsupported forms fail at emission with a
                    # source-positioned diagnostic. Defaults are evaluated once
                    # during HPy_mod_exec in source-safe order (type methods
                    # before type publication; module functions after imports/
                    # assignments). HPy method objects are not Python functions,
                    # so __defaults__/__kwdefaults__ introspection remains blocked.
                    default_node = self._unwrap_default(argument.default)
                    self.default_registry.register_argument(argument, default_node)

        method_names = {method.name for method in methods}
        type_names = {extension_type.class_name for extension_type in extension_types}
        duplicate_public_names = method_names & type_names
        if duplicate_public_names:
            self.unsupported(
                self.module_node,
                "function/type names collide: %s" %
                ", ".join(sorted(duplicate_public_names)),
            )
        for extension_type in extension_types:
            self.name_registry.require_module_global(extension_type.class_name)
            reserved_type_names = [
                entry.name
                for entry in extension_type.entry.type.scope.var_entries
                if entry.name == self.MODULE_ATTRIBUTE
                or entry.name.startswith((
                    _HPyConstantRegistry.ATTRIBUTE_PREFIX,
                    _HPyDefaultRegistry.ATTRIBUTE_PREFIX,
                    self.TYPE_SLOT_MARKER_PREFIX,
                ))
            ]
            for method in self._extension_type_methods(extension_type):
                if (
                    method.name == self.MODULE_ATTRIBUTE
                    or method.name.startswith((
                        _HPyConstantRegistry.ATTRIBUTE_PREFIX,
                        _HPyDefaultRegistry.ATTRIBUTE_PREFIX,
                        self.TYPE_SLOT_MARKER_PREFIX,
                    ))
                ):
                    reserved_type_names.append(method.name)
                if method.name not in ("__getbuffer__", "__releasebuffer__"):
                    method.hpy_bootstrap_signature(
                        self, receiver_argument=method.args[0])
            if reserved_type_names:
                self.unsupported(
                    extension_type,
                    "pure HPy type members use reserved runtime cache names: %s" %
                    ", ".join(sorted(set(reserved_type_names))),
                )
        for method in methods:
            if method.name.startswith((
                _HPyConstantRegistry.ATTRIBUTE_PREFIX,
                _HPyDefaultRegistry.ATTRIBUTE_PREFIX,
                self.TYPE_SLOT_MARKER_PREFIX,
            )):
                self.unsupported(
                    method,
                    "function name uses a reserved aHPy cache prefix",
                )
        for stat in module_stats:
            if type(stat) is Nodes.SingleAssignmentNode:
                source_name = stat.lhs.name
                if source_name.startswith((
                    _HPyConstantRegistry.ATTRIBUTE_PREFIX,
                    _HPyDefaultRegistry.ATTRIBUTE_PREFIX,
                    self.TYPE_SLOT_MARKER_PREFIX,
                )):
                    self.unsupported(
                        stat,
                        "module name uses a reserved aHPy cache prefix",
                    )
                self.name_registry.require_module_global(source_name)
            else:
                for imported_name, target in stat.items:
                    if imported_name == "*":
                        self.unsupported(
                            stat, "star imports are not implemented")
                    if target.name.startswith((
                        _HPyConstantRegistry.ATTRIBUTE_PREFIX,
                        _HPyDefaultRegistry.ATTRIBUTE_PREFIX,
                        self.TYPE_SLOT_MARKER_PREFIX,
                    )):
                        self.unsupported(
                            stat,
                            "import target uses a reserved aHPy cache prefix",
                        )
                    self.name_registry.require_module_global(target.name)

        self._collect_referenced_names(methods)
        for extension_type in extension_types:
            self._collect_referenced_names([
                method
                for method in self._extension_type_methods(extension_type)
                if method.name not in ("__getbuffer__", "__releasebuffer__")
            ])
            self._collect_referenced_names([
                accessor
                for _, accessors in self._extension_type_properties(
                    extension_type)
                for accessor in accessors.values()
            ])
        self._collect_referenced_names(module_stats)
        (type_lines, type_specs, type_method_definitions,
         type_cinitializer_definitions,
         type_initializer_definitions, type_call_slot_definitions,
         type_value_slot_definitions,
         type_property_definitions,
         type_length_slot_definitions,
         type_binary_value_slot_definitions,
         type_sequence_subscript_slot_definitions,
         type_numeric_binary_slot_definitions,
         type_power_slot_definitions,
         type_inplace_power_slot_definitions,
         type_assignment_slot_definitions,
         type_hash_slot_definitions,
         type_bool_slot_definitions,
         type_contains_slot_definitions,
         type_richcompare_slot_definitions,
         type_finalize_slot_definitions,
         type_buffer_slot_definitions,
         type_field_layouts) = (
            self._render_extension_type_declarations(
            extension_types, module_name)
        )
        closure_registry = self._collect_closure_registry(methods, module_name)
        closure_lines, closure_fn_call_lines = (
            self._render_closure_declarations(closure_registry, module_name))
        method_lines = []
        definitions = []
        for index, method in enumerate(methods):
            definition_cname = "__pyx_hpy_def_%d_%s" % (
                index, _c_identifier_fragment(method.name))
            definition = RuntimeMethodDefinition(
                signature=method.hpy_bootstrap_signature(self),
                definition_cname=definition_cname,
                python_name_cname=self._c_string(method.name),
                implementation_cname="%s_impl" % definition_cname,
                doc_cname=self._doc_cname(
                    method, method.entry.doc, "function"),
            )
            function_writer = UniversalHPyFunctionWriter(
                self.runtime_api,
                name_registry=self.name_registry,
                module_cname="self",
                constant_registry=self.constant_registry,
                default_registry=self.default_registry,
                closure_registry=closure_registry,
            )
            method.generate_hpy_bootstrap_definition(definition, function_writer)
            method_lines.extend(function_writer.lines)
            definitions.append(definition)
        method_lines.extend(closure_fn_call_lines)

        for extension_type in extension_types:
            for (property_node, accessors,
                 definition_cname) in type_property_definitions[
                     id(extension_type)]:
                method_lines.extend(self._render_extension_property(
                    property_node,
                    accessors,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            for method, definition in type_method_definitions[id(extension_type)]:
                function_writer = UniversalHPyFunctionWriter(
                    self.runtime_api,
                    name_registry=self.name_registry,
                    module_cname=None,
                    constant_registry=self.constant_registry,
                    default_registry=self.default_registry,
                    extension_field_layout=type_field_layouts[
                        id(extension_type)],
                )
                method.generate_hpy_bootstrap_definition(
                    definition,
                    function_writer,
                    receiver_argument=method.args[0],
                    emit_declaration=False,
                )
                method_lines.extend(function_writer.lines)
            cinitializer = type_cinitializer_definitions[id(extension_type)]
            if cinitializer is not None:
                method, definition_cname = cinitializer
                method_lines.extend(self._render_extension_initializer(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            initializer = type_initializer_definitions[id(extension_type)]
            if initializer is not None:
                method, definition_cname = initializer
                method_lines.extend(self._render_extension_initializer(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            call_slot = type_call_slot_definitions[id(extension_type)]
            if call_slot is not None:
                method, definition_cname = call_slot
                method_lines.extend(self._render_extension_call_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            for method, definition_cname in type_value_slot_definitions[
                    id(extension_type)]:
                method_lines.extend(self._render_extension_value_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            length_slot = type_length_slot_definitions[id(extension_type)]
            if length_slot is not None:
                method, definition_cname, mapping_definition_cname = length_slot
                method_lines.extend(self._render_extension_length_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
                method_lines.extend(self._render_extension_length_alias_slot(
                    definition_cname,
                    mapping_definition_cname,
                ))
            for method, definition_cname in type_binary_value_slot_definitions[
                    id(extension_type)]:
                method_lines.extend(self._render_extension_binary_value_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            sequence_subscript_slot = (
                type_sequence_subscript_slot_definitions[id(extension_type)])
            if sequence_subscript_slot is not None:
                mapping_definition_cname, sequence_definition_cname = (
                    sequence_subscript_slot)
                method_lines.extend(
                    self._render_extension_sequence_subscript_slot(
                        mapping_definition_cname,
                        sequence_definition_cname,
                    ))
            for numeric_binary_slot in type_numeric_binary_slot_definitions[
                    id(extension_type)]:
                (methods_by_name, definition_cname, marker_attribute,
                 left_method_name, right_method_name) = numeric_binary_slot
                method_lines.extend(self._render_extension_numeric_binary_slot(
                    methods_by_name,
                    definition_cname,
                    marker_attribute,
                    left_method_name,
                    right_method_name,
                    type_field_layouts[id(extension_type)],
                ))
            power_slot = type_power_slot_definitions[id(extension_type)]
            if power_slot is not None:
                methods_by_name, definition_cname, marker_attribute = power_slot
                method_lines.extend(self._render_extension_numeric_binary_slot(
                    methods_by_name,
                    definition_cname,
                    marker_attribute,
                    "__pow__",
                    "__rpow__",
                    type_field_layouts[id(extension_type)],
                    ternary=True,
                ))
            inplace_power_slot = type_inplace_power_slot_definitions[
                id(extension_type)]
            if inplace_power_slot is not None:
                method, definition_cname = inplace_power_slot
                method_lines.extend(self._render_extension_ternary_value_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            assignment_slot = type_assignment_slot_definitions[
                id(extension_type)]
            if assignment_slot is not None:
                (set_method, del_method, definition_cname,
                 sequence_definition_cname, class_name) = assignment_slot
                method_lines.extend(self._render_extension_assignment_slot(
                    set_method,
                    del_method,
                    definition_cname,
                    sequence_definition_cname,
                    class_name,
                    type_field_layouts[id(extension_type)],
                ))
            hash_slot = type_hash_slot_definitions[id(extension_type)]
            if hash_slot is not None:
                method, definition_cname = hash_slot
                method_lines.extend(self._render_extension_hash_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            bool_slot = type_bool_slot_definitions[id(extension_type)]
            if bool_slot is not None:
                method, definition_cname = bool_slot
                method_lines.extend(self._render_extension_bool_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            contains_slot = type_contains_slot_definitions[id(extension_type)]
            if contains_slot is not None:
                method, definition_cname = contains_slot
                method_lines.extend(self._render_extension_contains_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            richcompare_slot = type_richcompare_slot_definitions[
                id(extension_type)]
            if richcompare_slot is not None:
                methods_by_name, definition_cname = richcompare_slot
                method_lines.extend(self._render_extension_richcompare_slot(
                    methods_by_name,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            finalize_slot = type_finalize_slot_definitions[id(extension_type)]
            if finalize_slot is not None:
                method, definition_cname = finalize_slot
                method_lines.extend(self._render_extension_finalize_slot(
                    method,
                    definition_cname,
                    type_field_layouts[id(extension_type)],
                ))
            buffer_slot = type_buffer_slot_definitions[id(extension_type)]
            if buffer_slot is not None:
                method_lines.extend(self._render_extension_buffer_slots(
                    buffer_slot,
                    type_field_layouts[id(extension_type)],
                ))

        exec_definition_cname = "__pyx_hpy_mod_exec"
        exec_lines = self._render_module_exec(
            exec_definition_cname,
            module_stats,
            method_names,
            extension_types,
            type_specs,
            closure_registry,
        )

        lines = [
            GENERATED_BY_MARKER,
            "/* aHPy Universal HPy bootstrap backend. */",
            "#include <hpy.h>",
            "#include <stddef.h>",
            "#include <errno.h>",
            "#include <limits.h>",
            "#include <math.h>",
            "#include <stdio.h>",
            "#include <string.h>",
        ]
        included_headers = set()
        for external_c_block in external_c_blocks:
            include_file = str(external_c_block.include_file)
            if include_file in included_headers:
                continue
            included_headers.add(include_file)
            if include_file.startswith("<"):
                lines.append("#include %s" % include_file)
            else:
                lines.append('#include "%s"' % include_file)
        lines.append("")
        lines.extend(type_lines)
        lines.extend(closure_lines)
        lines.extend(method_lines)
        lines.extend(exec_lines)

        definitions_cname = "__pyx_hpy_defines"
        module_cname = "__pyx_hpy_module"
        lines.append(self.runtime_api.method_table_declaration(definitions_cname))
        for definition in definitions:
            lines.append("    %s" % self.runtime_api.method_table_entry(definition, ","))
        lines.append("    &%s," % exec_definition_cname)
        lines.extend([
            "    %s," % self.runtime_api.method_table_terminator(),
            "};",
        ])
        lines.extend([
            "",
            "static HPyModuleDef %s = {" % module_cname,
            "    .doc = %s," % self._doc_cname(
                self.module_node, getattr(self.module_node, "doc", None),
                "module"),
            "    .size = 0,",
            "    .legacy_methods = NULL,",
            "    .defines = %s," % definitions_cname,
            "    .globals = NULL,",
            "};",
            "",
            "HPy_MODINIT(%s, %s)" % (module_init_name, module_cname),
            "",
        ])
        return "\n".join(lines)

    def _collect_referenced_names(self, roots):
        seen = set()

        def visit(value):
            if value is None or isinstance(value, (str, bytes, int, float, bool)):
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)
                return
            value_id = id(value)
            if value_id in seen:
                return
            seen.add(value_id)
            if isinstance(value, ExprNodes.NameNode):
                entry = value.entry
                if entry is not None:
                    if entry.is_builtin or entry.scope.is_builtin_scope:
                        self.name_registry.require_builtin(value.name)
                    elif entry.is_pyglobal:
                        self.name_registry.require_module_global(value.name)
            for child_name in getattr(value, "child_attrs", ()):
                visit(getattr(value, child_name, None))
            self.constant_registry.register_node(value)

        visit(roots)

    @staticmethod
    def _flatten_stats(node):
        flattened = []
        pending = [node]
        while pending:
            current = pending.pop()
            while type(current) is Nodes.CompilerDirectivesNode:
                current = current.body
            if type(current) is Nodes.StatListNode:
                pending.extend(reversed(current.stats))
            else:
                flattened.append(current)
        return flattened

    @staticmethod
    def _unwrap_nested_def_stat(stat):
        while type(stat) is Nodes.CompilerDirectivesNode:
            stat = stat.body
        if isinstance(stat, Nodes.DefNode):
            return stat
        return None

    def _iter_nested_defs(self, outer_def):
        seen = set()
        for stat in self._flatten_stats(outer_def.body):
            inner_def = self._unwrap_nested_def_stat(stat)
            if inner_def is None:
                continue
            inner_node = inner_def.py_cfunc_node
            if inner_node is None:
                self.unsupported(
                    inner_def,
                    "nested def requires InnerFunction closure synthesis",
                )
            seen.add(id(inner_node))
            yield inner_def, inner_node
        for stat in self._flatten_stats(outer_def.body):
            if type(stat) is not Nodes.SingleAssignmentNode:
                continue
            inner_node = self._inner_function_from_expr(stat.rhs)
            if inner_node is None or id(inner_node) in seen:
                continue
            inner_def = inner_node.def_node
            if inner_def is None:
                self.unsupported(
                    stat,
                    "nested def requires InnerFunction closure synthesis",
                )
            seen.add(id(inner_node))
            yield inner_def, inner_node

    def _contains_nested_def(self, def_node):
        for stat in self._flatten_stats(def_node.body):
            nested = self._unwrap_nested_def_stat(stat)
            if nested is None or type(nested) is Nodes.GeneratorBodyDefNode:
                continue
            return nested
        return None

    @staticmethod
    def _nested_def_contains_yield(def_node):
        pending = [def_node.body]
        while pending:
            node = pending.pop()
            if node is None:
                continue
            if isinstance(node, (ExprNodes.YieldExprNode, ExprNodes.YieldFromExprNode)):
                return True
            if type(node) is Nodes.GeneratorDefNode:
                return True
            for child_name in getattr(node, "child_attrs", ()):
                child = getattr(node, child_name, None)
                if child is None:
                    continue
                if isinstance(child, list):
                    pending.extend(child)
                else:
                    pending.append(child)
        return False

    def _inner_function_from_expr(self, expr):
        current = expr
        while isinstance(current, ExprNodes.SimpleCallNode):
            if not current.args:
                break
            current = current.args[0]
        if isinstance(current, ExprNodes.InnerFunctionNode):
            return current
        return None

    def _nested_def_assignment_is_decorated(self, outer_def, inner_node):
        for stat in self._flatten_stats(outer_def.body):
            if type(stat) is not Nodes.SingleAssignmentNode:
                continue
            if self._inner_function_from_expr(stat.rhs) is not inner_node:
                continue
            return type(stat.rhs) is not ExprNodes.InnerFunctionNode
        return False

    def _validate_nested_closure(self, outer_def, inner_def, inner_node):
        if not isinstance(inner_node, ExprNodes.InnerFunctionNode):
            self.unsupported(
                inner_def,
                "nested def requires InnerFunction closure synthesis",
            )
        if inner_def.decorators or inner_def.is_staticmethod or inner_def.is_classmethod:
            self.unsupported(
                inner_def,
                "decorated nested def functions are not implemented",
            )
        if self._nested_def_assignment_is_decorated(outer_def, inner_node):
            self.unsupported(
                inner_def,
                "decorated nested def functions are not implemented",
            )
        if inner_def.is_generator or self._nested_def_contains_yield(inner_def):
            self.unsupported(
                inner_def,
                "generators and yield in nested def are not implemented",
            )
        if inner_def.needs_closure == Nodes.FuncDefNode.NeedsClosure.FULL_CLOSURE:
            self.unsupported(
                inner_def,
                "nested nested def closures are not implemented",
            )
        nested_child = self._contains_nested_def(inner_def)
        if nested_child is not None:
            self.unsupported(
                nested_child,
                "nested nested def closures are not implemented",
            )
        if inner_def.star_arg is not None or inner_def.starstar_arg is not None:
            self.unsupported(
                inner_def,
                "star arguments on nested def are not implemented",
            )
        for argument in inner_def.args:
            if argument.default is not None:
                self.unsupported(
                    argument,
                    "default arguments on nested def are not implemented",
                )

    def _collect_captures(self, inner_def):
        captures = []
        seen = set()
        for scope in inner_def.local_scope.iter_local_scopes():
            for name, entry in sorted(scope.entries.items()):
                if not name or not entry.from_closure:
                    continue
                outer_entry = entry.outer_entry
                if not outer_entry.type.is_pyobject:
                    self.unsupported(
                        inner_def,
                        "C-typed closure captures are not implemented",
                    )
                key = id(outer_entry)
                if key in seen:
                    continue
                seen.add(key)
                field_cname = "__pyx_hpy_capture_%s" % (
                    outer_entry.cname.replace(".", "_"))
                captures.append(_ClosureCapture(
                    outer_entry.name, outer_entry, field_cname))
        return captures

    def _collect_closure_registry(self, methods, module_name):
        env_specs = {}
        fn_specs = []
        env_index = 0
        fn_index = 0
        for method in methods:
            for inner_def, inner_node in self._iter_nested_defs(method):
                self._validate_nested_closure(method, inner_def, inner_node)
                outer_id = id(method)
                captures = self._collect_captures(inner_def)
                if outer_id not in env_specs:
                    env_specs[outer_id] = _ClosureEnvSpec(
                        env_index, method, captures)
                    env_index += 1
                else:
                    # Sibling nested functions share one environment.  Its
                    # layout must therefore be the stable union of every
                    # sibling's captures, not merely the captures seen on the
                    # first nested function.
                    env_spec = env_specs[outer_id]
                    captured_entries = {
                        id(capture.entry) for capture in env_spec.captures}
                    env_spec.captures.extend(
                        capture for capture in captures
                        if id(capture.entry) not in captured_entries
                    )
                fn_specs.append(_ClosureFnSpec(
                    fn_index, inner_def, inner_node, env_specs[outer_id]))
                fn_index += 1
        for env_spec in env_specs.values():
            # Even a capture-free nested function owns an empty environment
            # object, so its synthetic type is still a required module cache.
            self.name_registry.require_module_global(env_spec.module_global)
        for fn_spec in fn_specs:
            self.name_registry.require_module_global(fn_spec.module_global)
        return _ClosureRegistry(env_specs.values(), fn_specs)

    def _render_closure_object_type(
            self, type_cname, struct_cname, spec_cname, module_name,
            qualified_name, field_cnames, slot_definition_cnames):
        lines = [
            "typedef struct {",
        ]
        if field_cnames:
            lines.extend("    HPyField %s;" % field_cname for field_cname in field_cnames)
        else:
            lines.append("    char __pyx_hpy_reserved;")
        lines.extend([
            "} %s;" % struct_cname,
            "HPyType_HELPERS(%s)" % struct_cname,
        ])
        if field_cnames:
            traverse_cname = "%s_traverse" % type_cname
            lines.extend([
                "static int %s_impl(void *object, "
                "HPyFunc_visitproc visit, void *arg)" % traverse_cname,
                "{",
                "    %s *self = (%s *)object;" % (struct_cname, struct_cname),
            ])
            lines.extend(
                "    HPy_VISIT(&self->%s);" % field_cname
                for field_cname in field_cnames
            )
            lines.extend([
                "    return 0;",
                "}",
                self.runtime_api.type_slot_definition(
                    "tp_traverse", traverse_cname, "%s_impl" % traverse_cname),
            ])
            slot_definition_cnames = list(slot_definition_cnames) + [traverse_cname]
            flags = "HPy_TPFLAGS_DEFAULT | HPy_TPFLAGS_HAVE_GC"
        else:
            flags = "HPy_TPFLAGS_DEFAULT"
        lines.append(
            self.runtime_api.type_definition_array_declaration(type_cname))
        lines.extend("    &%s," % cname for cname in slot_definition_cnames)
        lines.extend([
            "    %s," % self.runtime_api.type_definition_array_terminator(),
            "};",
            self.runtime_api.type_specification_declaration(type_cname),
            "    .name = %s," % self._c_string("%s.%s" % (module_name, qualified_name)),
            "    .basicsize = sizeof(%s)," % struct_cname,
            "    .itemsize = 0,",
            "    .flags = %s," % flags,
            "    .builtin_shape = SHAPE(%s)," % struct_cname,
            "    .legacy_slots = NULL,",
            "    .defines = %s_defines," % type_cname,
            "    .doc = NULL,",
            "};",
            "",
        ])
        return lines, spec_cname, flags

    def _render_closure_declarations(self, closure_registry, module_name):
        if not closure_registry.env_specs and not closure_registry.fn_specs:
            return [], []
        lines = []
        call_lines = []
        rendered_env = set()
        for env_spec in closure_registry.env_specs:
            if env_spec.index in rendered_env:
                continue
            rendered_env.add(env_spec.index)
            field_cnames = [capture.field_cname for capture in env_spec.captures]
            env_lines, _, _ = self._render_closure_object_type(
                env_spec.type_cname,
                env_spec.struct_cname,
                env_spec.spec_cname,
                module_name,
                env_spec.module_global,
                field_cnames,
                [],
            )
            lines.extend(env_lines)
        for fn_spec in closure_registry.fn_specs:
            slot_cnames = []
            call_definition_cname = "%s_tp_call" % fn_spec.type_cname
            lines.append(self.runtime_api.type_slot_definition(
                "tp_call",
                call_definition_cname,
                fn_spec.call_impl_cname,
            ))
            slot_cnames.append(call_definition_cname)
            fn_object_lines, _, _ = self._render_closure_object_type(
                fn_spec.type_cname,
                fn_spec.struct_cname,
                fn_spec.spec_cname,
                module_name,
                fn_spec.module_global,
                [fn_spec.env_field_cname],
                slot_cnames,
            )
            lines.extend(fn_object_lines)
            call_lines.extend(self._render_closure_fn_call_impl(
                fn_spec, closure_registry))
        return lines, call_lines

    def _render_closure_fn_call_impl(self, fn_spec, closure_registry):
        inner_def = fn_spec.inner_def
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            # Nested callables have no module receiver; construct literals
            # directly rather than reading interpreter-owned module caches.
            use_constant_cache=False,
            closure_registry=closure_registry,
            closure_env_spec=fn_spec.env_spec,
        )
        body = writer.stats(inner_def.body)
        if not body or not inner_def._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                inner_def.body,
                "nested def body must end with a return statement",
            )
        writer.putln(
            "static HPy %s(HPyContext *%s, HPy self, "
            "const HPy *args, size_t nargs, HPy kwnames)" % (
                fn_spec.call_impl_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.putln("%s *%s = %s_AsStruct(%s, self);" % (
            fn_spec.struct_cname,
            "__pyx_hpy_closure_self",
            fn_spec.struct_cname,
            writer.context_cname,
        ))
        env_field = "__pyx_hpy_closure_self->%s" % fn_spec.env_field_cname
        writer.putln("if (HPyField_IsNull(%s)) {" % env_field)
        writer.indent()
        writer.putln("%s;" % writer.runtime_api.error_set_string(
            writer.runtime_api.builtin_exception(
                "RuntimeError", context_cname=writer.context_cname),
            UniversalHPyModuleWriter._c_string(
                "closure callable is missing its capture env"),
            context_cname=writer.context_cname,
        ))
        writer._emit_failure_exit()
        writer.dedent()
        writer.putln("}")
        writer._closure_env_owner_cname = writer.allocate_owned_handle(
            writer.runtime_api.field_load(
                "self", env_field, context_cname=writer.context_cname))
        writer.put_error_return_if_null(writer._closure_env_owner_cname)
        signature = inner_def.hpy_bootstrap_signature(writer)
        if signature is RuntimeMethodSignature.VARARGS_KEYWORDS:
            writer.parse_keyword_arguments(inner_def.name, inner_def.args)
        elif signature is RuntimeMethodSignature.POSITIONAL_VARARGS:
            writer.bind_required_positional_arguments(
                inner_def.name, inner_def.args, keyword_cname="kwnames")
        elif signature is RuntimeMethodSignature.ONEARG:
            writer.reject_keyword_arguments(inner_def.name, "kwnames")
            writer.putln("if (nargs != 1) {")
            writer.indent()
            writer.putln("%s;" % writer.runtime_api.error_set_string(
                writer.runtime_api.builtin_exception(
                    "TypeError", context_cname=writer.context_cname),
                UniversalHPyModuleWriter._c_string(
                    "%s() takes exactly one argument" % inner_def.name),
                context_cname=writer.context_cname,
            ))
            writer._emit_failure_exit()
            writer.dedent()
            writer.putln("}")
            writer.bind_borrowed_argument(
                inner_def.args[0].entry.name, "args[0]")
        elif signature is RuntimeMethodSignature.NOARGS:
            writer.reject_keyword_arguments(inner_def.name, "kwnames")
            writer.putln("if (nargs != 0) {")
            writer.indent()
            writer.putln("%s;" % writer.runtime_api.error_set_string(
                writer.runtime_api.builtin_exception(
                    "TypeError", context_cname=writer.context_cname),
                UniversalHPyModuleWriter._c_string(
                    "%s() takes no arguments" % inner_def.name),
                context_cname=writer.context_cname,
            ))
            writer._emit_failure_exit()
            writer.dedent()
            writer.putln("}")
        else:
            writer.unsupported(
                inner_def, "unsupported nested def signature for closures")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _emit_closure_type_caches(self, writer, closure_registry):
        for env_spec in closure_registry.env_specs:
            type_cname = writer.allocate_owned_handle(
                self.runtime_api.type_from_spec(
                    env_spec.spec_cname,
                    context_cname=writer.context_cname,
                ))
            writer.put_error_return_if_null(type_cname)
            writer.store_materialized_module_global(
                env_spec.module_global, type_cname, "m", publish=True)
        for fn_spec in closure_registry.fn_specs:
            type_cname = writer.allocate_owned_handle(
                self.runtime_api.type_from_spec(
                    fn_spec.spec_cname,
                    context_cname=writer.context_cname,
                ))
            writer.put_error_return_if_null(type_cname)
            writer.store_materialized_module_global(
                fn_spec.module_global, type_cname, "m", publish=True)

    def _render_module_exec(
        self,
        definition_cname,
        module_stats,
        method_names,
        extension_types,
        type_specs,
        closure_registry,
    ):
        failure_epilogue = tuple(
            "(void)%s;" % self.runtime_api.attribute_delete_string(
                "m", self._c_string(method_name), context_cname="ctx")
            for method_name in sorted(method_names)
        )
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="-1",
            available_module_globals=set(),
            module_cname="m",
            constant_registry=self.constant_registry,
            default_registry=self.default_registry,
            use_constant_cache=False,
            failure_epilogue=failure_epilogue,
            rollback_module_publications=True,
        )
        writer.putln(self.runtime_api.module_slot_definition(
            "mod_exec", definition_cname))
        writer.putln("static int %s_impl(HPyContext *%s, HPy m)" % (
            definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()

        builtin_entries = list(self.name_registry.entries("builtin"))
        if builtin_entries:
            builtins_cname = writer.allocate_owned_handle(
                self.runtime_api.import_module(
                    self._c_string("builtins"),
                    context_cname=writer.context_cname,
                ))
            writer.put_error_return_if_null(builtins_cname)
            writer._handle_temps.use(builtins_cname)
            status_cname = writer._emit_status_operation(
                self.runtime_api.module_set_attr_string(
                    "m",
                    self._c_string(self.BUILTINS_ATTRIBUTE),
                    builtins_cname,
                    context_cname=writer.context_cname,
                ))
            writer.put_module_publication_error_if_negative(status_cname)
            writer.record_module_publication(
                self.BUILTINS_ATTRIBUTE, "m")
            writer.close_owned_handle(builtins_cname)
        self._emit_constant_caches(writer)
        type_default_argument_ids = set()
        for extension_type in extension_types:
            for method in self._extension_type_methods(extension_type):
                for argument in method.args:
                    if argument.default is not None:
                        type_default_argument_ids.add(id(argument))
        # Type-method defaults must exist as module attributes before types copy
        # them onto the defining type object during publication.
        self._emit_default_caches(
            writer, include_argument_ids=type_default_argument_ids)
        writer.available_module_globals.update(method_names)
        self._emit_type_caches(writer, extension_types, type_specs)
        self._emit_closure_type_caches(writer, closure_registry)

        for stat in module_stats:
            if type(stat) is Nodes.SingleAssignmentNode:
                self._emit_module_assignment(stat, writer)
            else:
                self._emit_from_import(stat, writer)

        # Module-function defaults evaluate after imports/assignments so
        # source-ordered names and imported callables are observable.
        self._emit_default_caches(
            writer, exclude_argument_ids=type_default_argument_ids)

        writer._close_remaining_owned_handles()
        writer.assert_function_exit()
        writer.putln("return 0;")
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_type_declarations(self, extension_types, module_name):
        lines = []
        type_specs = {}
        type_method_definitions = {}
        type_cinitializer_definitions = {}
        type_initializer_definitions = {}
        type_call_slot_definitions = {}
        type_value_slot_definitions = {}
        type_property_definitions = {}
        type_length_slot_definitions = {}
        type_binary_value_slot_definitions = {}
        type_sequence_subscript_slot_definitions = {}
        type_numeric_binary_slot_definitions = {}
        type_power_slot_definitions = {}
        type_inplace_power_slot_definitions = {}
        type_assignment_slot_definitions = {}
        type_hash_slot_definitions = {}
        type_bool_slot_definitions = {}
        type_contains_slot_definitions = {}
        type_richcompare_slot_definitions = {}
        type_finalize_slot_definitions = {}
        type_buffer_slot_definitions = {}
        type_field_layouts = {}
        type_struct_cnames = {}
        type_traverse_cnames = {}
        type_effective_initializer = {}
        type_effective_call = {}
        type_effective_numeric_binary_methods = {}
        type_effective_power_methods = {}
        type_cinitializer_chains = {}
        extension_nodes_by_type = {
            id(extension_type.entry.type): extension_type
            for extension_type in extension_types
        }
        for type_index, extension_type in enumerate(extension_types):
            python_class_name = extension_type.class_name
            class_name = _c_identifier_fragment(python_class_name)
            all_fields = list(extension_type.entry.type.scope.var_entries)
            fields = [
                field for field in all_fields
                if not getattr(field, "is_inherited", False)
            ]
            methods = self._extension_type_methods(extension_type)
            buffer_get_method = next(
                (method for method in methods
                 if hasattr(method, "ahpy_universal_buffer_spec")),
                None,
            )
            properties = self._extension_type_properties(extension_type)
            type_cname = "__pyx_hpy_type_%s" % class_name
            struct_cname = "%s_object" % type_cname
            type_struct_cnames[id(extension_type)] = struct_cname
            base_extension_type = (
                extension_nodes_by_type.get(id(extension_type.base_type))
                if extension_type.base_type is not None else None
            )
            initializer_method = next(
                (method for method in methods if method.name == "__init__"),
                None,
            )
            if initializer_method is None and base_extension_type is not None:
                initializer_method = type_effective_initializer[
                    id(base_extension_type)]
            type_effective_initializer[id(extension_type)] = initializer_method
            call_method = next(
                (method for method in methods if method.name == "__call__"),
                None,
            )
            if call_method is None and base_extension_type is not None:
                call_method = type_effective_call[id(base_extension_type)]
            type_effective_call[id(extension_type)] = call_method
            cinitializer_chain = (
                list(type_cinitializer_chains[id(base_extension_type)])
                if base_extension_type is not None else []
            )
            cinitializer_method = next(
                (method for method in methods if method.name == "__cinit__"),
                None,
            )
            if cinitializer_method is not None:
                cinitializer_cname = "__pyx_hpy_type_%d_%s_cinit" % (
                    type_index, class_name)
                cinitializer_chain.append(
                    (cinitializer_method, cinitializer_cname))
                type_cinitializer_definitions[id(extension_type)] = (
                    cinitializer_method, cinitializer_cname)
            type_cinitializer_chains[id(extension_type)] = cinitializer_chain
            has_initializer = initializer_method is not None
            is_callable = call_method is not None
            spec_cname = "%s_spec" % type_cname
            type_specs[id(extension_type)] = spec_cname
            flags = "HPy_TPFLAGS_DEFAULT"
            if not extension_type.entry.type.is_final_type:
                flags += " | HPy_TPFLAGS_BASETYPE"
            field_cnames = [
                "__pyx_hpy_field_%d_%s" % (index, field.cname)
                for index, field in enumerate(fields)
            ]
            field_storages = [
                _extension_field_storage(field.type, field_cname)
                for field, field_cname in zip(fields, field_cnames)
            ]
            field_layout = (
                dict(type_field_layouts[id(base_extension_type)])
                if base_extension_type is not None else {}
            )
            if base_extension_type is not None:
                base_scope = base_extension_type.entry.type.scope
                for inherited_field in all_fields:
                    if not getattr(inherited_field, "is_inherited", False):
                        continue
                    base_field = base_scope.lookup_here(inherited_field.name)
                    base_storage = field_layout.get(id(base_field))
                    if base_storage is not None:
                        field_layout[id(inherited_field)] = base_storage
            for field, field_cname, storage in zip(
                    fields, field_cnames, field_storages):
                field_storage = (struct_cname, field_cname, storage[2])
                field_layout[id(field)] = field_storage
                field_layout[("field", field.name)] = field_storage
            type_field_layouts[id(extension_type)] = field_layout
            lines.append("typedef struct {")
            if base_extension_type is not None:
                lines.append("    %s __pyx_hpy_base;" %
                             type_struct_cnames[id(base_extension_type)])
            if fields:
                lines.extend(
                    "    %s;" % storage[0]
                    for storage in field_storages
                )
            elif base_extension_type is None:
                lines.append("    char __pyx_hpy_reserved;")
            lines.extend([
                "} %s;" % struct_cname,
                "HPyType_HELPERS(%s)" % struct_cname,
            ])
            definition_cnames = []
            method_definitions = []
            property_definitions = []
            value_slot_definitions = []
            binary_value_slot_definitions = []
            richcompare_methods = {}
            assignment_methods = {
                method.name: method for method in methods
                if method.name in ("__setitem__", "__delitem__")
            }
            numeric_binary_method_names = {
                method_name
                for _, left_name, right_name, _, _
                in self.NUMERIC_BINARY_FAMILIES
                for method_name in (left_name, right_name)
            }
            local_numeric_binary_methods = {
                method.name: method for method in methods
                if method.name in numeric_binary_method_names
            }
            numeric_binary_methods = (
                dict(type_effective_numeric_binary_methods[
                    id(base_extension_type)])
                if base_extension_type is not None else {}
            )
            numeric_binary_methods.update(local_numeric_binary_methods)
            type_effective_numeric_binary_methods[id(extension_type)] = (
                numeric_binary_methods)
            local_power_methods = {
                method.name: method for method in methods
                if method.name in ("__pow__", "__rpow__")
            }
            power_methods = (
                dict(type_effective_power_methods[id(base_extension_type)])
                if base_extension_type is not None else {}
            )
            power_methods.update(local_power_methods)
            type_effective_power_methods[id(extension_type)] = power_methods
            numeric_inplace_slots = {
                method_name: slot_name
                for _, _, _, slot_name, method_name
                in self.NUMERIC_BINARY_FAMILIES
                if method_name is not None
            }
            if cinitializer_method is not None:
                lines.append(
                    "static int %s_impl(HPyContext *ctx, HPy self, "
                    "const HPy *args, HPy_ssize_t nargs, HPy kw);" %
                    cinitializer_cname)
            if is_callable or cinitializer_chain:
                new_definition_cname = (
                    "__pyx_hpy_type_%d_%s_tp_new" %
                    (type_index, class_name))
                new_lines = [
                    self.runtime_api.type_slot_definition(
                        "tp_new",
                        new_definition_cname,
                        "%s_impl" % new_definition_cname,
                    ),
                    "static HPy %s_impl(HPyContext *ctx, HPy type, "
                    "const HPy *args, HPy_ssize_t nargs, HPy kw)" %
                    new_definition_cname,
                    "{",
                ]
                if not cinitializer_chain:
                    if has_initializer:
                        new_lines.extend([
                            "    (void)args;",
                            "    (void)nargs;",
                            "    (void)kw;",
                        ])
                    else:
                        new_lines.extend([
                            "    (void)args;",
                            "    HPy_ssize_t nkw = 0;",
                            "    if (!HPy_IsNull(kw)) {",
                            "        nkw = HPy_Length(ctx, kw);",
                            "        if (nkw < 0)",
                            "            return HPy_NULL;",
                            "    }",
                            "    if (nargs != 0 || nkw != 0) {",
                            "        HPyErr_SetString(ctx, ctx->h_TypeError, "
                            "%s);" % self._c_string(
                                "%s() takes no arguments" % python_class_name),
                            "        return HPy_NULL;",
                            "    }",
                        ])
                new_lines.extend([
                    "    %s *data;" % struct_cname,
                    "    HPy result = HPy_New(ctx, type, &data);",
                    "    if (HPy_IsNull(result))",
                    "        return HPy_NULL;",
                ])
                for _, cinitializer_cname in cinitializer_chain:
                    new_lines.extend([
                        "    if (%s_impl(ctx, result, args, nargs, kw) < 0) {" %
                        cinitializer_cname,
                        "        HPy_Close(ctx, result);",
                        "        return HPy_NULL;",
                        "    }",
                    ])
                new_lines.extend([
                    "    return result;",
                    "}",
                ])
                lines.extend(new_lines)
                definition_cnames.append(new_definition_cname)
            if buffer_get_method is not None:
                get_definition_cname = (
                    "__pyx_hpy_type_%d_%s_bf_getbuffer" %
                    (type_index, class_name))
                release_definition_cname = (
                    "__pyx_hpy_type_%d_%s_bf_releasebuffer" %
                    (type_index, class_name))
                lines.append(self.runtime_api.type_slot_definition(
                    "bf_getbuffer",
                    get_definition_cname,
                    "%s_impl" % get_definition_cname,
                ))
                lines.append(self.runtime_api.type_slot_definition(
                    "bf_releasebuffer",
                    release_definition_cname,
                    "%s_impl" % release_definition_cname,
                ))
                definition_cnames.extend((
                    get_definition_cname, release_definition_cname))
                type_buffer_slot_definitions[id(extension_type)] = (
                    buffer_get_method.ahpy_universal_buffer_spec,
                    get_definition_cname,
                    release_definition_cname,
                )
            if initializer_method is not None:
                definition_cname = "__pyx_hpy_type_%d_%s_init" % (
                    type_index, class_name)
                lines.append(self.runtime_api.type_slot_definition(
                    "tp_init",
                    definition_cname,
                    "%s_impl" % definition_cname,
                ))
                definition_cnames.append(definition_cname)
                type_initializer_definitions[id(extension_type)] = (
                    initializer_method, definition_cname)
            if call_method is not None:
                definition_cname = "__pyx_hpy_type_%d_%s_tp_call" % (
                    type_index, class_name)
                lines.append(self.runtime_api.type_slot_definition(
                    "tp_call",
                    definition_cname,
                    "%s_impl" % definition_cname,
                ))
                definition_cnames.append(definition_cname)
                type_call_slot_definitions[id(extension_type)] = (
                    call_method, definition_cname)
            for property_index, (property_node, accessors) in enumerate(
                    properties):
                definition_cname = (
                    "__pyx_hpy_type_%d_%s_property_%d_%s" % (
                        type_index, class_name, property_index,
                        _c_identifier_fragment(property_node.name)))
                has_getter = "__get__" in accessors
                has_setter = any(
                    name in accessors for name in ("__set__", "__del__"))
                if has_getter and has_setter:
                    macro = "HPyDef_GETSET"
                elif has_getter:
                    macro = "HPyDef_GET"
                else:
                    macro = "HPyDef_SET"
                doc_argument = ""
                if property_node.doc is not None:
                    doc_argument = ", .doc = %s" % self._doc_cname(
                        property_node, property_node.doc, "property")
                lines.append("%s(%s, %s%s)" % (
                    macro,
                    definition_cname,
                    self._c_string(property_node.name),
                    doc_argument,
                ))
                definition_cnames.append(definition_cname)
                property_definitions.append((
                    property_node, accessors, definition_cname))
            for method_index, method in enumerate(methods):
                if method.name in ("__getbuffer__", "__releasebuffer__"):
                    continue
                if method.name in ("__cinit__", "__init__"):
                    continue
                if method.name == "__call__":
                    continue
                if method.name in local_numeric_binary_methods:
                    continue
                if method.name in local_power_methods:
                    continue
                value_slots = {
                    "__repr__": "tp_repr",
                    "__str__": "tp_str",
                    "__neg__": "nb_negative",
                    "__pos__": "nb_positive",
                    "__abs__": "nb_absolute",
                    "__invert__": "nb_invert",
                    "__int__": "nb_int",
                    "__float__": "nb_float",
                    "__index__": "nb_index",
                }
                if method.name in value_slots:
                    slot_name = value_slots[method.name]
                    definition_cname = "__pyx_hpy_type_%d_%s_%s" % (
                        type_index, class_name, slot_name)
                    lines.append(self.runtime_api.type_slot_definition(
                        slot_name,
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    value_slot_definitions.append((method, definition_cname))
                    continue
                if method.name == "__len__":
                    definition_cname = "__pyx_hpy_type_%d_%s_sq_length" % (
                        type_index, class_name)
                    lines.append(self.runtime_api.type_slot_definition(
                        "sq_length",
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    mapping_definition_cname = (
                        "__pyx_hpy_type_%d_%s_mp_length" %
                        (type_index, class_name))
                    lines.append(self.runtime_api.type_slot_definition(
                        "mp_length",
                        mapping_definition_cname,
                        "%s_impl" % mapping_definition_cname,
                    ))
                    definition_cnames.append(mapping_definition_cname)
                    type_length_slot_definitions[id(extension_type)] = (
                        method, definition_cname, mapping_definition_cname)
                    continue
                if method.name == "__getitem__":
                    definition_cname = "__pyx_hpy_type_%d_%s_mp_subscript" % (
                        type_index, class_name)
                    lines.append(self.runtime_api.type_slot_definition(
                        "mp_subscript",
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    binary_value_slot_definitions.append(
                        (method, definition_cname))
                    sequence_definition_cname = (
                        "__pyx_hpy_type_%d_%s_sq_item" %
                        (type_index, class_name))
                    lines.append(self.runtime_api.type_slot_definition(
                        "sq_item",
                        sequence_definition_cname,
                        "%s_impl" % sequence_definition_cname,
                    ))
                    definition_cnames.append(sequence_definition_cname)
                    type_sequence_subscript_slot_definitions[
                        id(extension_type)] = (
                            definition_cname, sequence_definition_cname)
                    continue
                if method.name in numeric_inplace_slots:
                    slot_name = numeric_inplace_slots[method.name]
                    definition_cname = (
                        "__pyx_hpy_type_%d_%s_%s" %
                        (type_index, class_name, slot_name))
                    lines.append(self.runtime_api.type_slot_definition(
                        slot_name,
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    binary_value_slot_definitions.append(
                        (method, definition_cname))
                    continue
                if method.name == "__ipow__":
                    definition_cname = (
                        "__pyx_hpy_type_%d_%s_nb_inplace_power" %
                        (type_index, class_name))
                    lines.append(self.runtime_api.type_slot_definition(
                        "nb_inplace_power",
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    type_inplace_power_slot_definitions[id(extension_type)] = (
                        method, definition_cname)
                    continue
                if method.name in assignment_methods:
                    continue
                if method.name == "__hash__":
                    definition_cname = "__pyx_hpy_type_%d_%s_tp_hash" % (
                        type_index, class_name)
                    lines.append(self.runtime_api.type_slot_definition(
                        "tp_hash",
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    type_hash_slot_definitions[id(extension_type)] = (
                        method, definition_cname)
                    continue
                if method.name == "__bool__":
                    definition_cname = "__pyx_hpy_type_%d_%s_nb_bool" % (
                        type_index, class_name)
                    lines.append(self.runtime_api.type_slot_definition(
                        "nb_bool",
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    type_bool_slot_definitions[id(extension_type)] = (
                        method, definition_cname)
                    continue
                if method.name == "__contains__":
                    definition_cname = "__pyx_hpy_type_%d_%s_sq_contains" % (
                        type_index, class_name)
                    lines.append(self.runtime_api.type_slot_definition(
                        "sq_contains",
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    type_contains_slot_definitions[id(extension_type)] = (
                        method, definition_cname)
                    continue
                if method.name in (
                        "__lt__", "__le__", "__eq__", "__ne__",
                        "__gt__", "__ge__"):
                    richcompare_methods[method.name] = method
                    continue
                if method.name == "__del__":
                    definition_cname = "__pyx_hpy_type_%d_%s_tp_finalize" % (
                        type_index, class_name)
                    lines.append(self.runtime_api.type_slot_definition(
                        "tp_finalize",
                        definition_cname,
                        "%s_impl" % definition_cname,
                    ))
                    definition_cnames.append(definition_cname)
                    type_finalize_slot_definitions[id(extension_type)] = (
                        method, definition_cname)
                    continue
                definition_cname = "__pyx_hpy_type_%d_%s_method_%d_%s" % (
                    type_index, class_name, method_index,
                    _c_identifier_fragment(method.name))
                definition = RuntimeMethodDefinition(
                    signature=method.hpy_bootstrap_signature(
                        self, receiver_argument=method.args[0]),
                    definition_cname=definition_cname,
                    python_name_cname=self._c_string(method.name),
                    implementation_cname="%s_impl" % definition_cname,
                    doc_cname=self._doc_cname(
                        method, method.entry.doc, "method"),
                )
                lines.append(
                    self.runtime_api.method_definition_declaration(definition))
                definition_cnames.append(definition_cname)
                method_definitions.append((method, definition))
            if assignment_methods:
                definition_cname = (
                    "__pyx_hpy_type_%d_%s_mp_ass_subscript" % (
                        type_index, class_name))
                lines.append(self.runtime_api.type_slot_definition(
                    "mp_ass_subscript",
                    definition_cname,
                    "%s_impl" % definition_cname,
                ))
                definition_cnames.append(definition_cname)
                sequence_definition_cname = (
                    "__pyx_hpy_type_%d_%s_sq_ass_item" % (
                        type_index, class_name))
                lines.append(self.runtime_api.type_slot_definition(
                    "sq_ass_item",
                    sequence_definition_cname,
                    "%s_impl" % sequence_definition_cname,
                ))
                definition_cnames.append(sequence_definition_cname)
                type_assignment_slot_definitions[id(extension_type)] = (
                    assignment_methods.get("__setitem__"),
                    assignment_methods.get("__delitem__"),
                    definition_cname,
                    sequence_definition_cname,
                    python_class_name,
                )
            if richcompare_methods:
                definition_cname = (
                    "__pyx_hpy_type_%d_%s_tp_richcompare" %
                    (type_index, class_name))
                lines.append(self.runtime_api.type_slot_definition(
                    "tp_richcompare",
                    definition_cname,
                    "%s_impl" % definition_cname,
                ))
                definition_cnames.append(definition_cname)
                type_richcompare_slot_definitions[id(extension_type)] = (
                    richcompare_methods, definition_cname)
            numeric_binary_slots = []
            for (slot_name, left_name, right_name, _, _
                    ) in self.NUMERIC_BINARY_FAMILIES:
                if not any(
                    method_name in local_numeric_binary_methods
                    for method_name in (left_name, right_name)
                ):
                    continue
                family_methods = {
                    method_name: numeric_binary_methods[method_name]
                    for method_name in (left_name, right_name)
                    if method_name in numeric_binary_methods
                }
                definition_cname = "__pyx_hpy_type_%d_%s_%s" % (
                    type_index, class_name, slot_name)
                lines.append(self.runtime_api.type_slot_definition(
                    slot_name,
                    definition_cname,
                    "%s_impl" % definition_cname,
                ))
                definition_cnames.append(definition_cname)
                numeric_binary_slots.append((
                    family_methods,
                    definition_cname,
                    self._type_slot_marker_attribute(
                        module_name, python_class_name),
                    left_name,
                    right_name,
                ))
            type_numeric_binary_slot_definitions[id(extension_type)] = (
                numeric_binary_slots)
            if local_power_methods:
                definition_cname = "__pyx_hpy_type_%d_%s_nb_power" % (
                    type_index, class_name)
                lines.append(self.runtime_api.type_slot_definition(
                    "nb_power",
                    definition_cname,
                    "%s_impl" % definition_cname,
                ))
                definition_cnames.append(definition_cname)
                type_power_slot_definitions[id(extension_type)] = (
                    power_methods,
                    definition_cname,
                    self._type_slot_marker_attribute(
                        module_name, python_class_name),
                )
            type_method_definitions[id(extension_type)] = method_definitions
            type_property_definitions[id(extension_type)] = property_definitions
            type_cinitializer_definitions.setdefault(id(extension_type), None)
            type_initializer_definitions.setdefault(id(extension_type), None)
            type_call_slot_definitions.setdefault(id(extension_type), None)
            type_value_slot_definitions[id(extension_type)] = (
                value_slot_definitions)
            type_length_slot_definitions.setdefault(id(extension_type), None)
            type_binary_value_slot_definitions[id(extension_type)] = (
                binary_value_slot_definitions)
            type_sequence_subscript_slot_definitions.setdefault(
                id(extension_type), None)
            type_power_slot_definitions.setdefault(id(extension_type), None)
            type_inplace_power_slot_definitions.setdefault(
                id(extension_type), None)
            type_assignment_slot_definitions.setdefault(
                id(extension_type), None)
            type_hash_slot_definitions.setdefault(id(extension_type), None)
            type_bool_slot_definitions.setdefault(id(extension_type), None)
            type_contains_slot_definitions.setdefault(id(extension_type), None)
            type_richcompare_slot_definitions.setdefault(
                id(extension_type), None)
            type_finalize_slot_definitions.setdefault(id(extension_type), None)
            type_buffer_slot_definitions.setdefault(id(extension_type), None)
            object_field_cnames = [
                field_cname
                for field_cname, storage in zip(field_cnames, field_storages)
                if storage[2] == "object"
            ]
            base_traverse_cname = (
                type_traverse_cnames.get(id(base_extension_type))
                if base_extension_type is not None else None
            )
            if object_field_cnames or base_traverse_cname is not None:
                traverse_cname = "%s_traverse" % type_cname
                type_traverse_cnames[id(extension_type)] = traverse_cname
                lines.extend([
                    "static int %s_impl(void *object, "
                    "HPyFunc_visitproc visit, void *arg)" % traverse_cname,
                    "{",
                ])
                if object_field_cnames:
                    lines.append("    %s *self = (%s *)object;" % (
                        struct_cname, struct_cname))
                if base_traverse_cname is not None:
                    lines.extend([
                        "    if (%s_impl(object, visit, arg) < 0)" %
                        base_traverse_cname,
                        "        return -1;",
                    ])
                lines.extend(
                    "    HPy_VISIT(&self->%s);" % field_cname
                    for field_cname in object_field_cnames
                )
                lines.extend([
                    "    return 0;",
                    "}",
                    self.runtime_api.type_slot_definition(
                        "tp_traverse", traverse_cname,
                        "%s_impl" % traverse_cname),
                ])
                definition_cnames.append(traverse_cname)
                flags += " | HPy_TPFLAGS_HAVE_GC"
            for index, (field, field_cname, storage) in enumerate(
                    zip(fields, field_cnames, field_storages)):
                if field.visibility not in ("public", "readonly"):
                    continue
                definition_cname = "%s_member_%d" % (type_cname, index)
                readonly = 1 if field.visibility == "readonly" else 0
                if storage[2] in ("object", "long-double"):
                    lines.extend(self._render_extension_custom_field_definition(
                        definition_cname,
                        field.name,
                        struct_cname,
                        field_cname,
                        storage[2],
                        readonly=bool(readonly),
                    ))
                else:
                    lines.append(
                        "HPyDef_MEMBER(%s, %s, %s, "
                        "offsetof(%s, %s), .readonly = %d)" % (
                            definition_cname,
                            self._c_string(field.name),
                            storage[1],
                            struct_cname,
                            field_cname,
                            readonly,
                        ))
                definition_cnames.append(definition_cname)
            lines.append(
                self.runtime_api.type_definition_array_declaration(type_cname))
            lines.extend(
                "    &%s," % definition_cname
                for definition_cname in definition_cnames
            )
            lines.extend([
                "    %s," % self.runtime_api.type_definition_array_terminator(),
                "};",
                self.runtime_api.type_specification_declaration(type_cname),
                "    .name = %s," % self._c_string(
                    "%s.%s" % (module_name, python_class_name)),
                "    .basicsize = sizeof(%s)," % struct_cname,
                "    .itemsize = 0,",
                "    .flags = %s," % flags,
                "    .builtin_shape = SHAPE(%s)," % struct_cname,
                "    .legacy_slots = NULL,",
                "    .defines = %s_defines," % type_cname,
                "    .doc = %s," % self._doc_cname(
                    extension_type,
                    getattr(extension_type.entry.type.scope, "doc", None),
                    "type",
                ),
                "};",
                "",
            ])
        return (
            lines,
            type_specs,
            type_method_definitions,
            type_cinitializer_definitions,
            type_initializer_definitions,
            type_call_slot_definitions,
            type_value_slot_definitions,
            type_property_definitions,
            type_length_slot_definitions,
            type_binary_value_slot_definitions,
            type_sequence_subscript_slot_definitions,
            type_numeric_binary_slot_definitions,
            type_power_slot_definitions,
            type_inplace_power_slot_definitions,
            type_assignment_slot_definitions,
            type_hash_slot_definitions,
            type_bool_slot_definitions,
            type_contains_slot_definitions,
            type_richcompare_slot_definitions,
            type_finalize_slot_definitions,
            type_buffer_slot_definitions,
            type_field_layouts,
        )

    def _render_extension_buffer_slots(
            self, buffer_slot, extension_field_layout):
        """Render an allocation-free one-dimensional native producer."""
        ((field, shape_field, stride_field, format_string, element_count),
         get_definition_cname, release_definition_cname) = buffer_slot
        struct_cname, field_cname, _ = extension_field_layout[id(field)]
        shape_struct_cname, shape_field_cname, _ = (
            extension_field_layout[id(shape_field)])
        stride_struct_cname, stride_field_cname, _ = (
            extension_field_layout[id(stride_field)])
        if (
            shape_struct_cname != struct_cname
            or stride_struct_cname != struct_cname
        ):
            raise AssertionError("buffer metadata must share the field layout")
        return [
            "static int %s_impl(HPyContext *ctx, HPy self, "
            "HPy_buffer *view, int flags)" % get_definition_cname,
            "{",
            "    %s *data;" % struct_cname,
            "    (void)flags;",
            "    if (view == NULL) {",
            "        HPyErr_SetString(ctx, ctx->h_BufferError, "
            "%s);" % self._c_string("buffer view must not be NULL"),
            "        return -1;",
            "    }",
            "    data = %s_AsStruct(ctx, self);" % struct_cname,
            "    data->%s = %d;" % (shape_field_cname, element_count),
            "    data->%s = " % stride_field_cname +
            "(HPy_ssize_t)sizeof(data->%s%s);" % (
                field_cname, "[0]" if element_count != 1 else ""),
            "    view->buf = (void *)%sdata->%s;" % (
                "" if element_count != 1 else "&", field_cname),
            "    view->obj = HPy_NULL;",
            "    view->len = (HPy_ssize_t)sizeof(data->%s);" % field_cname,
            "    view->itemsize = (HPy_ssize_t)sizeof(data->%s%s);" % (
                field_cname, "[0]" if element_count != 1 else ""),
            "    view->readonly = 0;",
            "    view->ndim = 1;",
            "    view->format = (char *)%s;" % self._c_string(format_string),
            "    view->shape = &data->%s;" % shape_field_cname,
            "    view->strides = &data->%s;" % stride_field_cname,
            "    view->suboffsets = NULL;",
            "    view->internal = NULL;",
            "    view->obj = HPy_Dup(ctx, self);",
            "    if (HPy_IsNull(view->obj))",
            "        return -1;",
            "    return 0;",
            "}",
            "",
            "static void %s_impl(HPyContext *ctx, HPy self, "
            "HPy_buffer *view)" % release_definition_cname,
            "{",
            "    (void)ctx;",
            "    (void)self;",
            "    (void)view;",
            "}",
            "",
        ]

    def _render_extension_call_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=self.default_registry,
            extension_field_layout=extension_field_layout,
        )
        if method.return_type_annotation is not None:
            self.unsupported(method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body, "__call__ body must end with a return statement")
        writer.putln(
            "static HPy %s_impl(HPyContext *%s, HPy self, "
            "const HPy *args, size_t nargs, HPy kwnames)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        writer.parse_keyword_arguments(method.name, method.args[1:])
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_custom_field_definition(
            self, definition_cname, field_name, struct_cname, field_cname,
            storage_kind, readonly):
        if storage_kind not in ("object", "long-double"):
            raise AssertionError("unknown custom extension field storage kind")
        macro = "HPyDef_GET" if readonly else "HPyDef_GETSET"
        lines = [
            "%s(%s, %s)" % (
                macro, definition_cname, self._c_string(field_name)),
            "static HPy %s_get(HPyContext *ctx, HPy self, void *closure)" %
            definition_cname,
            "{",
            "    %s *data = %s_AsStruct(ctx, self);" % (
                struct_cname, struct_cname),
        ]
        if storage_kind == "object":
            lines.extend([
                "    if (HPyField_IsNull(data->%s))" % field_cname,
                "        return HPy_Dup(ctx, ctx->h_None);",
                "    return HPyField_Load(ctx, self, data->%s);" %
                field_cname,
                "}",
            ])
        else:
            lines.extend([
                "    return HPyFloat_FromDouble(ctx, (double)data->%s);" %
                field_cname,
                "}",
            ])
        if readonly:
            return lines
        if storage_kind == "object":
            lines.extend([
                "static int %s_set(HPyContext *ctx, HPy self, HPy value, "
                "void *closure)" % definition_cname,
                "{",
                "    %s *data = %s_AsStruct(ctx, self);" % (
                    struct_cname, struct_cname),
                "    if (HPy_IsNull(value))",
                "        value = ctx->h_None;",
                "    HPyField_Store(ctx, self, &data->%s, value);" %
                field_cname,
                "    return 0;",
                "}",
            ])
            return lines
        delete_message = self._c_string(
            "attribute '%s' cannot be deleted" % field_name)
        lines.extend([
            "static int %s_set(HPyContext *ctx, HPy self, HPy value, "
            "void *closure)" % definition_cname,
            "{",
            "    if (HPy_IsNull(value)) {",
            "        HPyErr_SetString(ctx, ctx->h_AttributeError, %s);" %
            delete_message,
            "        return -1;",
            "    }",
            "    double converted = HPyFloat_AsDouble(ctx, value);",
            "    if ((converted == -1.0) && HPyErr_Occurred(ctx))",
            "        return -1;",
            "    %s *data = %s_AsStruct(ctx, self);" % (
                struct_cname, struct_cname),
            "    data->%s = (long double)converted;" % field_cname,
            "    return 0;",
            "}",
        ])
        return lines

    def _render_extension_property(
            self, property_node, accessors, definition_cname,
            extension_field_layout):
        lines = []
        getter = accessors.get("__get__")
        setter = accessors.get("__set__")
        deleter = accessors.get("__del__")
        if getter is not None:
            writer = UniversalHPyFunctionWriter(
                self.runtime_api,
                name_registry=self.name_registry,
                module_cname=None,
                constant_registry=self.constant_registry,
                default_registry=None,
                extension_field_layout=extension_field_layout,
            )
            body = writer.stats(getter.body)
            if (
                not body
                or not getter._hpy_bootstrap_statement_terminates(body[-1])
            ):
                self.unsupported(
                    getter.body,
                    "property getter body must end with a return statement",
                )
            writer.putln(
                "static HPy %s_get(HPyContext *%s, HPy self, void *closure)" %
                (definition_cname, writer.context_cname))
            writer.putln("{")
            writer.indent()
            writer.putln("(void)closure;")
            writer.bind_borrowed_argument(getter.args[0].entry.name, "self")
            writer.bind_extension_runtime_owners("self")
            for statement in body:
                statement.generate_hpy_bootstrap_execution_code(writer)
            writer.assert_function_exit()
            writer.dedent()
            writer.putln("}")
            writer.putln("")
            lines.extend(writer.lines)

        setter_helper = "%s_set_value" % definition_cname
        deleter_helper = "%s_delete" % definition_cname
        if setter is not None:
            lines.extend(self._render_extension_status_helper(
                setter,
                setter_helper,
                ("self", "value"),
                extension_field_layout,
            ))
        if deleter is not None:
            lines.extend(self._render_extension_status_helper(
                deleter,
                deleter_helper,
                ("self",),
                extension_field_layout,
            ))
        if setter is None and deleter is None:
            return lines

        lines.extend([
            "static int %s_set(HPyContext *ctx, HPy self, HPy value, "
            "void *closure)" % definition_cname,
            "{",
            "    (void)closure;",
            "    if (%s) {" % self.runtime_api.null_check("value"),
        ])
        if deleter is not None:
            lines.append("        return %s(ctx, self);" % deleter_helper)
        else:
            lines.extend([
                "        %s;" % self.runtime_api.error_set_string(
                    self.runtime_api.builtin_exception(
                        "NotImplementedError", context_cname="ctx"),
                    self._c_string("__delete__"),
                    context_cname="ctx",
                ),
                "        return -1;",
            ])
        lines.append("    }")
        if setter is not None:
            lines.append(
                "    return %s(ctx, self, value);" % setter_helper)
        else:
            lines.extend([
                "    %s;" % self.runtime_api.error_set_string(
                    self.runtime_api.builtin_exception(
                        "NotImplementedError", context_cname="ctx"),
                    self._c_string("__set__"),
                    context_cname="ctx",
                ),
                "    return -1;",
            ])
        lines.extend(["}", ""])
        return lines

    def _render_extension_value_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body,
                "%s body must end with a return statement" % method.name,
            )
        writer.putln("static HPy %s_impl(HPyContext *%s, HPy self)" % (
            definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_length_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="-1",
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
            native_return_kind="ssize",
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body,
                "__len__ body must end with a value-returning statement",
            )
        writer.putln(
            "static HPy_ssize_t %s_impl(HPyContext *%s, HPy self)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_binary_value_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body,
                "%s body must end with a return statement" % method.name,
            )
        writer.putln(
            "static HPy %s_impl(HPyContext *%s, HPy self, HPy key)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        writer.bind_borrowed_argument(method.args[1].entry.name, "key")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    @staticmethod
    def _render_extension_length_alias_slot(
            definition_cname, alias_definition_cname):
        return [
            "static HPy_ssize_t %s_impl(HPyContext *ctx, HPy self)" %
            alias_definition_cname,
            "{",
            "    return %s_impl(ctx, self);" % definition_cname,
            "}",
            "",
        ]

    def _render_extension_sequence_subscript_slot(
            self, mapping_definition_cname, sequence_definition_cname):
        index_cname = "__pyx_hpy_index"
        result_cname = "__pyx_hpy_result"
        return [
            "static HPy %s_impl(HPyContext *ctx, HPy self, "
            "HPy_ssize_t index)" % sequence_definition_cname,
            "{",
            "    HPy %s = %s;" % (
                index_cname,
                self.runtime_api.ssize_integer_from_cvalue(
                    "index", context_cname="ctx"),
            ),
            "    if (%s)" % self.runtime_api.null_check(index_cname),
            "        return HPy_NULL;",
            "    HPy %s = %s_impl(ctx, self, %s);" % (
                result_cname, mapping_definition_cname, index_cname),
            "    %s;" % self.runtime_api.close_reference(
                index_cname, context_cname="ctx"),
            "    return %s;" % result_cname,
            "}",
            "",
        ]

    def _render_extension_ternary_value_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body,
                "%s body must end with a return statement" % method.name,
            )
        writer.putln(
            "static HPy %s_impl(HPyContext *%s, HPy self, HPy other, "
            "HPy modulus)" % (definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        if len(method.args) == 2:
            writer.putln("if (!HPy_Is(ctx, modulus, ctx->h_None)) {")
            writer.indent()
            writer.putln(
                "HPyErr_SetString(ctx, ctx->h_TypeError, %s);" %
                self._c_string(
                    "%s() does not accept a modulus argument" % method.name))
            writer.putln("return HPy_NULL;")
            writer.dedent()
            writer.putln("}")
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        writer.bind_borrowed_argument(method.args[1].entry.name, "other")
        if len(method.args) == 3:
            writer.bind_borrowed_argument(method.args[2].entry.name, "modulus")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_numeric_binary_slot(
            self, methods_by_name, definition_cname, marker_attribute,
            left_method_name, right_method_name, extension_field_layout,
            ternary=False):
        lines = []
        helpers = {}
        for method_name, suffix in ((left_method_name, "left"),
                                    (right_method_name, "right")):
            method = methods_by_name.get(method_name)
            if method is None:
                continue
            helper_cname = "%s_%s" % (definition_cname, suffix)
            helpers[method_name] = helper_cname
            renderer = (
                self._render_extension_ternary_value_slot
                if ternary else self._render_extension_binary_value_slot
            )
            lines.extend(renderer(
                method, helper_cname, extension_field_layout))

        left_helper = helpers.get(left_method_name)
        right_helper = helpers.get(right_method_name)
        lines.extend([
            "static HPy %s_impl(HPyContext *ctx, HPy left, HPy right%s)" % (
                definition_cname, ", HPy modulus" if ternary else ""),
            "{",
            "    HPy left_type = HPy_Type(ctx, left);",
            "    HPy right_type = HPy_NULL;",
            "    HPy result;",
            "    int left_matches;",
            "    int right_matches;",
            "    if (HPy_IsNull(left_type))",
            "        return HPy_NULL;",
            "    right_type = HPy_Type(ctx, right);",
            "    if (HPy_IsNull(right_type)) {",
            "        HPy_Close(ctx, left_type);",
            "        return HPy_NULL;",
            "    }",
            "    left_matches = HPy_HasAttr_s(ctx, left_type, %s);" %
            self._c_string(marker_attribute),
            "    if (left_matches < 0)",
            "        goto bad;",
            "    right_matches = HPy_HasAttr_s(ctx, right_type, %s);" %
            self._c_string(marker_attribute),
            "    if (right_matches < 0)",
            "        goto bad;",
        ])

        def append_helper_call(helper_cname, receiver, other, indent="    "):
            lines.extend([
                "%sresult = %s_impl(ctx, %s, %s%s);" % (
                    indent, helper_cname, receiver, other,
                    ", modulus" if ternary else ""),
                "%sif (HPy_IsNull(result))" % indent,
                "%s    goto bad;" % indent,
                "%sif (!HPy_Is(ctx, result, ctx->h_NotImplemented)) {" %
                indent,
                "%s    HPy_Close(ctx, right_type);" % indent,
                "%s    HPy_Close(ctx, left_type);" % indent,
                "%s    return result;" % indent,
                "%s}" % indent,
                "%sHPy_Close(ctx, result);" % indent,
            ])

        if left_helper is None and right_helper is not None:
            lines.append("    if (left_matches && right_matches) {")
            append_helper_call(
                right_helper, "right", "left", indent="        ")
            lines.append("        right_matches = 0;")
            lines.append("    }")
        if left_helper is not None:
            lines.append("    if (left_matches) {")
            append_helper_call(
                left_helper, "left", "right", indent="        ")
            lines.append("    }")
        if right_helper is not None:
            lines.append("    if (right_matches) {")
            append_helper_call(
                right_helper, "right", "left", indent="        ")
            lines.append("    }")
        lines.extend([
            "    HPy_Close(ctx, right_type);",
            "    HPy_Close(ctx, left_type);",
            "    return HPy_Dup(ctx, ctx->h_NotImplemented);",
            "bad:",
            "    if (!HPy_IsNull(right_type)) HPy_Close(ctx, right_type);",
            "    HPy_Close(ctx, left_type);",
            "    return HPy_NULL;",
            "}",
            "",
        ])
        return lines

    def _render_extension_assignment_slot(
            self, set_method, del_method, definition_cname,
            sequence_definition_cname, class_name, extension_field_layout):
        lines = []
        set_helper = "%s_set" % definition_cname
        del_helper = "%s_del" % definition_cname
        if set_method is not None:
            lines.extend(self._render_extension_status_helper(
                set_method,
                set_helper,
                ("self", "key", "value"),
                extension_field_layout,
            ))
        if del_method is not None:
            lines.extend(self._render_extension_status_helper(
                del_method,
                del_helper,
                ("self", "key"),
                extension_field_layout,
            ))
        lines.extend([
            "static int %s_impl(HPyContext *ctx, HPy self, "
            "HPy key, HPy value)" % definition_cname,
            "{",
            "    if (%s) {" % self.runtime_api.null_check("value"),
        ])
        if del_method is not None:
            lines.append("        return %s(ctx, self, key);" % del_helper)
        else:
            lines.extend([
                "        %s;" % self.runtime_api.error_set_string(
                    self.runtime_api.builtin_exception(
                        "TypeError", context_cname="ctx"),
                    self._c_string(
                        "'%s' object does not support item deletion" %
                        class_name),
                    context_cname="ctx",
                ),
                "        return -1;",
            ])
        lines.append("    }")
        if set_method is not None:
            lines.append(
                "    return %s(ctx, self, key, value);" % set_helper)
        else:
            lines.extend([
                "    %s;" % self.runtime_api.error_set_string(
                    self.runtime_api.builtin_exception(
                        "TypeError", context_cname="ctx"),
                    self._c_string(
                        "'%s' object does not support item assignment" %
                        class_name),
                    context_cname="ctx",
                ),
                "    return -1;",
            ])
        lines.extend([
            "}",
            "",
            "static int %s_impl(HPyContext *ctx, HPy self, "
            "HPy_ssize_t index, HPy value)" % sequence_definition_cname,
            "{",
            "    HPy key = %s;" %
            self.runtime_api.ssize_integer_from_cvalue(
                "index", context_cname="ctx"),
            "    if (%s)" % self.runtime_api.null_check("key"),
            "        return -1;",
            "    int result = %s_impl(ctx, self, key, value);" %
            definition_cname,
            "    %s;" % self.runtime_api.close_reference(
                "key", context_cname="ctx"),
            "    return result;",
            "}",
            "",
        ])
        return lines

    def _render_extension_hash_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="-1",
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
            native_return_kind="hash",
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body,
                "__hash__ body must end with a value-returning statement",
            )
        writer.putln(
            "static HPy_hash_t %s_impl(HPyContext *%s, HPy self)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_bool_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="-1",
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
            native_return_kind="bool",
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body,
                "__bool__ body must end with a value-returning statement",
            )
        writer.putln(
            "static int %s_impl(HPyContext *%s, HPy self)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_contains_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="-1",
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
            native_return_kind="bool",
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        if not body or not method._hpy_bootstrap_statement_terminates(body[-1]):
            self.unsupported(
                method.body,
                "__contains__ body must end with a value-returning statement",
            )
        writer.putln(
            "static int %s_impl(HPyContext *%s, HPy self, HPy value)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        writer.bind_borrowed_argument(method.args[1].entry.name, "value")
        for statement in body:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer.assert_function_exit()
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_richcompare_slot(
            self, methods_by_name, definition_cname, extension_field_layout):
        operation_map = (
            ("__lt__", "HPy_LT", "lt"),
            ("__le__", "HPy_LE", "le"),
            ("__eq__", "HPy_EQ", "eq"),
            ("__ne__", "HPy_NE", "ne"),
            ("__gt__", "HPy_GT", "gt"),
            ("__ge__", "HPy_GE", "ge"),
        )
        lines = []
        helpers = {}
        for method_name, _, suffix in operation_map:
            method = methods_by_name.get(method_name)
            if method is None:
                continue
            helper_cname = "%s_%s" % (definition_cname, suffix)
            helpers[method_name] = helper_cname
            lines.extend(self._render_extension_binary_value_slot(
                method, helper_cname, extension_field_layout))
        lines.extend([
            "static HPy %s_impl(HPyContext *ctx, HPy self, HPy other, "
            "HPy_RichCmpOp op)" % definition_cname,
            "{",
            "    switch (op) {",
        ])
        for method_name, opcode, _ in operation_map:
            helper_cname = helpers.get(method_name)
            if helper_cname is not None:
                lines.extend([
                    "    case %s:" % opcode,
                    "        return %s_impl(ctx, self, other);" % helper_cname,
                ])
        lines.extend([
            "    default:",
            "        return %s;" % self.runtime_api.duplicate_reference(
                self.runtime_api.context_constant(
                    RuntimeContextConstant.NOT_IMPLEMENTED,
                    context_cname="ctx"),
                context_cname="ctx",
            ),
            "    }",
            "}",
            "",
        ])
        return lines

    def _render_extension_finalize_slot(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="",
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            failure_epilogue=("HPyErr_WriteUnraisable(ctx, self);",),
            extension_field_layout=extension_field_layout,
        )
        if method.return_type_annotation is not None:
            self.unsupported(method, "return annotations are not implemented")
        body = writer.stats(method.body)
        statements = body
        if body and type(body[-1]) is Nodes.ReturnStatNode:
            final_value = body[-1].value
            if (
                final_value is not None
                and type(final_value) is not ExprNodes.NoneNode
            ):
                self.unsupported(body[-1], "pure HPy __del__ may only return None")
            statements = body[:-1]
        writer.putln(
            "static void %s_impl(HPyContext *%s, HPy self)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        for statement in statements:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer._close_remaining_owned_handles()
        writer.assert_function_exit()
        writer.putln("return;")
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_status_helper(
            self, method, helper_cname, argument_cnames,
            extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="-1",
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=None,
            extension_field_layout=extension_field_layout,
        )
        if method.return_type_annotation is not None:
            self.unsupported(
                method, "return annotations are not implemented")
        body = writer.stats(method.body)
        statements = body
        if body and type(body[-1]) is Nodes.ReturnStatNode:
            final_value = body[-1].value
            if (
                final_value is not None
                and type(final_value) is not ExprNodes.NoneNode
            ):
                self.unsupported(
                    body[-1], "%s may only return None" % method.name)
            statements = body[:-1]
        parameters = ", ".join("HPy %s" % name for name in argument_cnames)
        writer.putln(
            "static int %s(HPyContext *%s, %s)" % (
                helper_cname, writer.context_cname, parameters))
        writer.putln("{")
        writer.indent()
        for argument, cname in zip(method.args, argument_cnames):
            writer.bind_borrowed_argument(argument.entry.name, cname)
        writer.bind_extension_runtime_owners("self")
        for statement in statements:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer._close_remaining_owned_handles()
        writer.assert_function_exit()
        writer.putln("return 0;")
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    def _render_extension_initializer(
            self, method, definition_cname, extension_field_layout):
        writer = UniversalHPyFunctionWriter(
            self.runtime_api,
            name_registry=self.name_registry,
            failure_return_value="-1",
            module_cname=None,
            constant_registry=self.constant_registry,
            default_registry=self.default_registry,
            extension_field_layout=extension_field_layout,
        )
        body = writer.stats(method.body)
        statements = body
        if body and type(body[-1]) is Nodes.ReturnStatNode:
            final_value = body[-1].value
            if (
                final_value is not None
                and type(final_value) is not ExprNodes.NoneNode
            ):
                self.unsupported(
                    body[-1], "pure HPy %s may only return None" % method.name)
            statements = body[:-1]
        writer.putln(
            "static int %s_impl(HPyContext *%s, HPy self, "
            "const HPy *args, HPy_ssize_t nargs, HPy kw)" % (
                definition_cname, writer.context_cname))
        writer.putln("{")
        writer.indent()
        writer.bind_borrowed_argument(method.args[0].entry.name, "self")
        writer.bind_extension_runtime_owners("self")
        if method.name == "__cinit__" and len(method.args) == 1:
            writer.putln("(void)args;")
            writer.putln("(void)nargs;")
            writer.putln("(void)kw;")
        elif all(
            argument.pos_only and argument.default is None
            for argument in method.args[1:]
        ):
            writer.bind_required_positional_arguments(
                method.name, method.args[1:], keyword_cname="kw")
        else:
            writer.parse_keyword_arguments(
                method.name, method.args[1:], keyword_dictionary=True)
        for statement in statements:
            statement.generate_hpy_bootstrap_execution_code(writer)
        writer._close_remaining_owned_handles()
        writer._close_argument_tracker()
        writer.assert_function_exit()
        writer.putln("return 0;")
        writer.dedent()
        writer.putln("}")
        writer.putln("")
        return writer.lines

    @staticmethod
    def _extension_type_methods(extension_type):
        class_stats = (
            list(extension_type.body.stats)
            if type(extension_type.body) is Nodes.StatListNode
            else [extension_type.body]
        )
        return [
            stat for stat in class_stats
            if type(stat) is Nodes.DefNode
            and stat.pos[0].__class__.__name__ != "StringSourceDescriptor"
        ]

    @staticmethod
    def _extension_type_properties(extension_type):
        class_stats = (
            list(extension_type.body.stats)
            if type(extension_type.body) is Nodes.StatListNode
            else [extension_type.body]
        )
        field_names = {
            field.name
            for field in extension_type.entry.type.scope.var_entries
        }
        properties = []
        for stat in class_stats:
            if (
                type(stat) is not Nodes.PropertyNode
                or stat.name in field_names
            ):
                continue
            accessor_stats = (
                list(stat.body.stats)
                if type(stat.body) is Nodes.StatListNode
                else [stat.body]
            )
            accessors = {
                accessor.name: accessor
                for accessor in accessor_stats
                if type(accessor) is Nodes.DefNode
            }
            properties.append((stat, accessors))
        return properties

    @classmethod
    def _type_slot_marker_attribute(cls, module_name, class_name):
        return "%s%s_%s" % (
            cls.TYPE_SLOT_MARKER_PREFIX, module_name, class_name)

    def _emit_type_caches(self, writer, extension_types, type_specs):
        extension_nodes_by_type = {
            id(extension_type.entry.type): extension_type
            for extension_type in extension_types
        }
        for type_index, extension_type in enumerate(extension_types):
            params_cname = "NULL"
            base_cname = None
            if extension_type.base_type is not None:
                base_extension_type = extension_nodes_by_type[
                    id(extension_type.base_type)]
                base_cname = writer.allocate_owned_handle(
                    self.runtime_api.attribute_get_string(
                        "m",
                        self._c_string(base_extension_type.class_name),
                        context_cname=writer.context_cname,
                    ))
                writer.put_error_return_if_null(base_cname)
                params_cname = "__pyx_hpy_type_params_%d" % type_index
                writer.putln("HPyType_SpecParam %s[] = {" % params_cname)
                writer.indent()
                writer.putln("{ HPyType_SpecParam_Base, %s }," % base_cname)
                writer.putln("{ 0 },")
                writer.dedent()
                writer.putln("};")
            type_cname = writer.allocate_owned_handle(
                self.runtime_api.type_from_spec(
                    type_specs[id(extension_type)],
                    params_cname=params_cname,
                    context_cname=writer.context_cname,
                ))
            writer.put_error_return_if_null(type_cname)
            if base_cname is not None:
                writer.close_owned_handle(base_cname)
            writer._handle_temps.use(type_cname)
            status_cname = writer._emit_status_operation(
                self.runtime_api.attribute_set_string(
                    type_cname,
                    self._c_string(self.MODULE_ATTRIBUTE),
                    "m",
                    context_cname=writer.context_cname,
                ))
            writer.put_module_publication_error_if_negative(status_cname)
            status_cname = writer._emit_status_operation(
                self.runtime_api.attribute_set_string(
                    type_cname,
                    self._c_string(self._type_slot_marker_attribute(
                        str(self.module_node.full_module_name),
                        extension_type.class_name,
                    )),
                    self.runtime_api.context_constant(
                        RuntimeContextConstant.TRUE,
                        context_cname=writer.context_cname,
                    ),
                    context_cname=writer.context_cname,
                ))
            writer.put_module_publication_error_if_negative(status_cname)
            for method in self._extension_type_methods(extension_type):
                for argument in method.args:
                    attribute_name = (
                        self.default_registry.attribute_for_argument(argument)
                    )
                    if attribute_name is None:
                        continue
                    default_cname = writer.allocate_owned_handle(
                        self.runtime_api.attribute_get_string(
                            "m",
                            self._c_string(attribute_name),
                            context_cname=writer.context_cname,
                        ))
                    writer.put_error_return_if_null(default_cname)
                    writer._handle_temps.use(type_cname)
                    writer._handle_temps.use(default_cname)
                    status_cname = writer._emit_status_operation(
                        self.runtime_api.attribute_set_string(
                            type_cname,
                            self._c_string(attribute_name),
                            default_cname,
                            context_cname=writer.context_cname,
                        ))
                    writer.put_module_publication_error_if_negative(status_cname)
                    writer.close_owned_handle(default_cname)
            writer.store_materialized_module_global(
                extension_type.class_name, type_cname, "m", publish=True)

    def _emit_constant_caches(self, writer):
        for attribute_name, node in self.constant_registry.entries():
            value_cname = writer.materialize_owned_handle(
                node.generate_hpy_bootstrap_owned_result(writer))
            writer.put_error_return_if_null(value_cname)
            writer.store_materialized_module_global(
                attribute_name, value_cname, "m", publish=True)

    def _emit_default_caches(
        self, writer, include_argument_ids=None, exclude_argument_ids=None,
    ):
        writer.use_constant_cache = True
        try:
            for attribute_name, node in self.default_registry.entries():
                argument_id = self.default_registry.argument_id_for_attribute(
                    attribute_name)
                if (
                    include_argument_ids is not None
                    and argument_id not in include_argument_ids
                ):
                    continue
                if (
                    exclude_argument_ids is not None
                    and argument_id in exclude_argument_ids
                ):
                    continue
                value_cname = writer.materialize_owned_handle(
                    node.generate_hpy_bootstrap_owned_result(writer))
                writer.put_error_return_if_null(value_cname)
                writer.store_materialized_module_global(
                    attribute_name, value_cname, "m", publish=True)
        finally:
            writer.use_constant_cache = False

    @classmethod
    def _is_supported_default(cls, node):
        """Whitelist for terminal-handler literals and similar pure forms.

        Argument defaults are not gated by this helper; they use the general
        bootstrap expression emitter and evaluate once in HPy_mod_exec.
        """
        node_type = type(node)
        if node_type in (
            ExprNodes.NoneNode,
            ExprNodes.BoolNode,
            ExprNodes.IntNode,
            ExprNodes.FloatNode,
            ExprNodes.UnicodeNode,
            ExprNodes.BytesNode,
        ):
            return True
        if node_type in (ExprNodes.ListNode, ExprNodes.TupleNode):
            return (
                node.mult_factor is None
                and node.unpacked_items is None
                and not any(arg.is_starred for arg in node.args)
                and all(cls._is_supported_default(arg) for arg in node.args)
            )
        if node_type is ExprNodes.DictNode:
            return (
                not node.exclude_null_values
                and not node.reject_duplicates
                and all(
                    cls._is_supported_default(item.key)
                    and cls._is_supported_default(item.value)
                    for item in node.key_value_pairs
                )
            )
        return False

    @staticmethod
    def _unwrap_default(node):
        while type(node) in (
            ExprNodes.CoerceToPyTypeNode,
            ExprNodes.DefaultLiteralArgNode,
        ):
            node = node.arg
        return node

    def _emit_module_assignment(self, stat, writer):
        source_name = stat.lhs.name
        if type(stat.rhs) is not ExprNodes.ImportNode:
            writer.store_module_global(
                stat, source_name, stat.rhs, "m", publish=True)
            return

        import_node = stat.rhs
        module_name = str(import_node.module_name.value)
        if import_node.level != 0:
            self.unsupported(
                stat, "relative imports are not implemented")
        imported_name = module_name
        if not import_node.is_import_as_name and "." in module_name:
            full_module_cname = writer.allocate_owned_handle(
                self.runtime_api.import_module(
                    self._c_string(module_name),
                    context_cname=writer.context_cname,
                ))
            writer.put_error_return_if_null(full_module_cname)
            writer.close_owned_handle(full_module_cname)
            imported_name = module_name.split(".", 1)[0]
        writer.store_module_global_expression(
            source_name,
            self.runtime_api.import_module(
                self._c_string(imported_name),
                context_cname=writer.context_cname,
            ),
            "m",
            publish=True,
        )

    def _emit_from_import(self, stat, writer):
        import_node = stat.module
        if import_node.level != 0:
            self.unsupported(
                stat, "relative imports are not implemented")
        module_cname = writer.allocate_owned_handle(
            self.runtime_api.import_module(
                self._c_string(str(import_node.module_name.value)),
                context_cname=writer.context_cname,
            ))
        writer.put_error_return_if_null(module_cname)
        for imported_name, target in stat.items:
            writer._handle_temps.use(module_cname)
            writer.store_module_global_expression(
                target.name,
                self.runtime_api.attribute_get_string(
                    module_cname,
                    self._c_string(str(imported_name)),
                    context_cname=writer.context_cname,
                ),
                "m",
                publish=True,
            )
        writer.close_owned_handle(module_cname)

    @staticmethod
    def _stats(node):
        if type(node) is Nodes.StatListNode:
            return list(node.stats)
        return [node]

    @staticmethod
    def _c_string(value):
        return EncodedString(value).as_c_string_literal()

    def _doc_cname(self, node, value, subject):
        if value is None:
            return "NULL"
        value = str(value)
        if "\x00" in value:
            self.unsupported(
                node,
                "%s docstrings containing NUL are not representable by "
                "the HPy definition API" % subject,
            )
        return self._c_string(value)

    @staticmethod
    def unsupported(node, message):
        raise CompileError(
            getattr(node, "pos", None),
            "aHPy bootstrap backend: %s" % message,
        )


def emit_hpy_universal_module(module_node, options, result):
    """Emit one complete Universal HPy module through the runtime contract."""
    if options.cplus:
        raise CompileError(
            module_node.pos,
            "aHPy bootstrap backend: C++ output is not implemented yet",
        )
    if Options.annotate or options.annotate:
        raise CompileError(
            module_node.pos,
            "aHPy bootstrap backend: annotated output is not implemented yet",
        )
    instrumentation = [
        directive
        for directive in ("profile", "linetrace", "embedsignature")
        if module_node.directives.get(directive)
    ]
    if instrumentation:
        raise CompileError(
            module_node.pos,
            "aHPy Universal preview does not implement generated %s "
            "instrumentation; disable these directives or use a "
            "separately selected CPython backend" %
            "/".join(instrumentation),
        )
    if options.c_line_in_traceback:
        raise CompileError(
            module_node.pos,
            "aHPy Universal preview does not implement generated C-line "
            "traceback instrumentation; disable c_line_in_traceback or "
            "use a separately selected CPython backend",
        )
    module_node.assure_safe_target(result.c_file, allow_failed=True)
    output = UniversalHPyModuleWriter(
        module_node, module_node.scope.context.runtime_api).render()
    with open_new_file(result.c_file) as output_file:
        output_file.write(output)
    result.c_file_generated = 1


def _borrow_sequence_source(writer, sequence):
    """Keep call arguments borrowed; materialize rebindable local sources."""
    # The HPy call frame (or its argument tracker) keeps an incoming argument
    # alive until return, even when its source name is rebound in the loop.
    # Owned locals are ineligible because rebinding closes their old handle.
    sequence_cname = writer.borrow_direct_named_value(
        sequence, borrowed_arguments_only=True)
    if sequence_cname is not None:
        return sequence_cname, True
    sequence_cname = writer.materialize_owned_handle(
        sequence.generate_hpy_bootstrap_owned_result(writer))
    writer.put_error_return_if_null(sequence_cname)
    return sequence_cname, False
