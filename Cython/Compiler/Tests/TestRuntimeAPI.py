from contextlib import redirect_stderr
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from .. import Main, Options, PyrexTypes
from ..RuntimeAPI import (
    CPYTHON_BACKEND,
    HPY_CPYTHON_BACKEND,
    HPY_HYBRID_BACKEND,
    HPY_UNIVERSAL_BACKEND,
    RuntimeBackendOptionError,
    RuntimeBackendUnavailableError,
    RuntimeBinaryOperation,
    RuntimeCallKeywordLayout,
    RuntimeCapability,
    RuntimeCapabilityError,
    RuntimeConversionDirection,
    RuntimeConversionKind,
    RuntimeComparisonOperation,
    RuntimeCodeGenerationKind,
    RuntimeContextConstant,
    RuntimeContextKind,
    RuntimeGlobalStorageKind,
    RuntimeInPlaceOperation,
    RuntimeMethodDefinition,
    RuntimeMethodSignature,
    RuntimeModuleInitializationKind,
    RuntimeNameLookup,
    RuntimeNameLookupKind,
    RuntimeOperationGroup,
    RuntimeSequenceKind,
    RuntimeTypeSpecificationKind,
    RuntimeUnaryOperation,
    create_runtime_api,
)


class RuntimeAPITest(TestCase):
    def test_handle_ownership_policy_is_runtime_semantics(self):
        cpython = create_runtime_api(CPYTHON_BACKEND)
        self.assertFalse(cpython.uses_handle_ownership())
        self.assertIs(
            cpython.code_generation_kind(), RuntimeCodeGenerationKind.CPYTHON)
        self.assertIs(cpython.context_contract().kind, RuntimeContextKind.NONE)
        self.assertEqual(cpython.reference_type_cname(), "PyObject *")
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.NONE), "Py_None")
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.NOT_IMPLEMENTED),
            "Py_NotImplemented")
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.ELLIPSIS),
            "Py_Ellipsis")
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.TYPE_ERROR),
            "PyExc_TypeError",
        )
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.BASE_EXCEPTION),
            "PyExc_BaseException",
        )
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.TYPE_TYPE),
            "(PyObject *)&PyType_Type",
        )
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.LONG_TYPE),
            "(PyObject *)&PyLong_Type",
        )
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.COMPLEX_TYPE),
            "(PyObject *)&PyComplex_Type",
        )
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.LIST_TYPE),
            "(PyObject *)&PyList_Type",
        )
        self.assertEqual(
            cpython.context_constant(RuntimeContextConstant.TUPLE_TYPE),
            "(PyObject *)&PyTuple_Type",
        )
        self.assertEqual(
            cpython.builtin_exception("ValueError"), "PyExc_ValueError")
        self.assertEqual(
            cpython.signed_integer_from_cvalue("42LL"),
            "PyLong_FromLongLong(42LL)",
        )
        self.assertEqual(
            cpython.ssize_integer_from_cvalue("index"),
            "PyLong_FromSsize_t(index)",
        )
        self.assertEqual(
            cpython.unsigned_integer_from_cvalue("42ULL"),
            "PyLong_FromUnsignedLongLong(42ULL)",
        )
        self.assertEqual(
            cpython.floating_from_cvalue("1.5"), "PyFloat_FromDouble(1.5)")
        self.assertEqual(cpython.signed_long_from_python("value"),
                         "PyLong_AsLong(value)")
        self.assertEqual(cpython.ssize_t_from_python("value"),
                         "PyLong_AsSsize_t(value)")
        self.assertEqual(
            cpython.type_check("value", "type"),
            "PyObject_TypeCheck(value, (PyTypeObject *)type)",
        )
        self.assertEqual(cpython.object_type("value"), "PyObject_Type(value)")
        self.assertEqual(
            cpython.type_is_subtype("sub", "type"),
            "PyType_IsSubtype((PyTypeObject *)sub, (PyTypeObject *)type)",
        )
        self.assertEqual(cpython.object_hash("value"), "PyObject_Hash(value)")
        self.assertEqual(cpython.signed_long_long_from_python("value"),
                         "PyLong_AsLongLong(value)")
        self.assertEqual(cpython.unsigned_long_from_python("value"),
                         "PyLong_AsUnsignedLong(value)")
        self.assertEqual(cpython.unsigned_long_long_from_python("value"),
                         "PyLong_AsUnsignedLongLong(value)")
        self.assertEqual(cpython.double_from_python("value"),
                         "PyFloat_AsDouble(value)")
        self.assertEqual(cpython.python_error_occurred(), "PyErr_Occurred()")
        self.assertEqual(
            cpython.unicode_from_utf8('"value"'),
            'PyUnicode_FromString("value")',
        )
        self.assertEqual(
            cpython.unicode_from_encoded_object(
                "value", '"utf-8"', '"surrogatepass"'),
            'PyUnicode_FromEncodedObject(value, "utf-8", "surrogatepass")',
        )
        self.assertEqual(
            cpython.bytes_from_data('"data"', "4"),
            'PyBytes_FromStringAndSize("data", 4)',
        )
        self.assertEqual(
            cpython.attribute_get_string("obj", '"name"'),
            'PyObject_GetAttrString(obj, "name")',
        )
        self.assertEqual(
            cpython.attribute_has_string("obj", '"name"'),
            'PyObject_HasAttrString(obj, "name")',
        )
        self.assertEqual(
            cpython.item_get("obj", "key"), "PyObject_GetItem(obj, key)")
        self.assertEqual(cpython.empty_reference("value"), "value = 0;")
        self.assertEqual(cpython.null_reference_value(), "NULL")
        for backend in (HPY_UNIVERSAL_BACKEND, HPY_CPYTHON_BACKEND):
            hpy = create_runtime_api(backend)
            self.assertTrue(hpy.uses_handle_ownership())
            context = hpy.context_contract()
            self.assertIs(context.kind, RuntimeContextKind.CALL_SCOPED_HPY)
            self.assertEqual(context.parameter_type_cname, "HPyContext *")
            self.assertEqual(context.default_parameter_cname, "ctx")
            self.assertTrue(context.required_for_python_operations)
            self.assertFalse(context.may_be_persisted)
            self.assertEqual(hpy.reference_type_cname(), "HPy")
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.NONE, context_cname="ctx"),
                "ctx->h_None",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.NOT_IMPLEMENTED,
                    context_cname="ctx"),
                "ctx->h_NotImplemented",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.TYPE_ERROR, context_cname="ctx"),
                "ctx->h_TypeError",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.BASE_EXCEPTION,
                    context_cname="ctx"),
                "ctx->h_BaseException",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.TYPE_TYPE, context_cname="ctx"),
                "ctx->h_TypeType",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.LONG_TYPE, context_cname="ctx"),
                "ctx->h_LongType",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.COMPLEX_TYPE, context_cname="ctx"),
                "ctx->h_ComplexType",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.LIST_TYPE, context_cname="ctx"),
                "ctx->h_ListType",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.TUPLE_TYPE, context_cname="ctx"),
                "ctx->h_TupleType",
            )
            self.assertEqual(
                hpy.builtin_exception("ValueError", context_cname="ctx"),
                "ctx->h_ValueError",
            )
            self.assertEqual(
                hpy.signed_integer_from_cvalue("42LL", context_cname="ctx"),
                "HPyLong_FromLongLong(ctx, 42LL)",
            )
            self.assertEqual(
                hpy.ssize_integer_from_cvalue(
                    "index", context_cname="ctx"),
                "HPyLong_FromSsize_t(ctx, index)",
            )
            self.assertEqual(
                hpy.unsigned_integer_from_cvalue("42ULL", context_cname="ctx"),
                "HPyLong_FromUnsignedLongLong(ctx, 42ULL)",
            )
            self.assertEqual(
                hpy.floating_from_cvalue("1.5", context_cname="ctx"),
                "HPyFloat_FromDouble(ctx, 1.5)",
            )
            self.assertEqual(
                hpy.signed_long_from_python("value", context_cname="ctx"),
                "HPyLong_AsLong(ctx, value)",
            )
            self.assertEqual(
                hpy.ssize_t_from_python("value", context_cname="ctx"),
                "HPyLong_AsSsize_t(ctx, value)",
            )
            self.assertEqual(
                hpy.type_check("value", "type", context_cname="ctx"),
                "HPy_TypeCheck(ctx, value, type)",
            )
            self.assertEqual(
                hpy.object_type("value", context_cname="ctx"),
                "HPy_Type(ctx, value)",
            )
            self.assertEqual(
                hpy.type_is_subtype("sub", "type", context_cname="ctx"),
                "HPyType_IsSubtype(ctx, sub, type)",
            )
            self.assertEqual(
                hpy.object_hash("value", context_cname="ctx"),
                "HPy_Hash(ctx, value)",
            )
            self.assertEqual(
                hpy.signed_long_long_from_python(
                    "value", context_cname="ctx"),
                "HPyLong_AsLongLong(ctx, value)",
            )
            self.assertEqual(
                hpy.unsigned_long_from_python("value", context_cname="ctx"),
                "HPyLong_AsUnsignedLong(ctx, value)",
            )
            self.assertEqual(
                hpy.unsigned_long_long_from_python(
                    "value", context_cname="ctx"),
                "HPyLong_AsUnsignedLongLong(ctx, value)",
            )
            self.assertEqual(
                hpy.double_from_python("value", context_cname="ctx"),
                "HPyFloat_AsDouble(ctx, value)",
            )
            self.assertEqual(
                hpy.python_error_occurred(context_cname="ctx"),
                "HPyErr_Occurred(ctx)",
            )
            self.assertEqual(
                hpy.unicode_from_utf8('"value"', context_cname="ctx"),
                'HPyUnicode_FromString(ctx, "value")',
            )
            self.assertEqual(
                hpy.unicode_from_encoded_object(
                    "value", '"utf-8"', '"surrogatepass"',
                    context_cname="ctx"),
                'HPyUnicode_FromEncodedObject(ctx, value, "utf-8", "surrogatepass")',
            )
            self.assertEqual(
                hpy.bytes_from_data('"data"', "4", context_cname="ctx"),
                'HPyBytes_FromStringAndSize(ctx, "data", 4)',
            )
            self.assertEqual(
                hpy.attribute_get_string(
                    "obj", '"name"', context_cname="ctx"),
                'HPy_GetAttr_s(ctx, obj, "name")',
            )
            self.assertEqual(
                hpy.attribute_has_string(
                    "obj", '"name"', context_cname="ctx"),
                'HPy_HasAttr_s(ctx, obj, "name")',
            )
            self.assertEqual(
                hpy.item_get("obj", "key", context_cname="ctx"),
                "HPy_GetItem(ctx, obj, key)",
            )
            self.assertEqual(
                hpy.item_set("obj", "key", "value", context_cname="ctx"),
                "HPy_SetItem(ctx, obj, key, value)",
            )
            self.assertEqual(
                hpy.item_delete("obj", "key", context_cname="ctx"),
                "HPy_DelItem(ctx, obj, key)",
            )
            self.assertEqual(
                hpy.attribute_set_string(
                    "obj", '"name"', "value", context_cname="ctx"),
                'HPy_SetAttr_s(ctx, obj, "name", value)',
            )
            self.assertEqual(
                hpy.attribute_delete_string(
                    "obj", '"name"', context_cname="ctx"),
                'HPy_DelAttr_s(ctx, obj, "name")',
            )
            self.assertEqual(
                hpy.call_tuple_dict(
                    "callable", "args", "kwargs", context_cname="ctx"),
                "HPy_CallTupleDict(ctx, callable, args, kwargs)",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.ELLIPSIS, context_cname="ctx"),
                "ctx->h_Ellipsis",
            )
            self.assertEqual(
                hpy.call_no_args("callable", context_cname="ctx"),
                "HPy_Call(ctx, callable, NULL, 0, HPy_NULL)",
            )
            self.assertEqual(
                hpy.call_one_arg("callable", "arg", context_cname="ctx"),
                "HPy_Call(ctx, callable, &arg, 1, HPy_NULL)",
            )
            self.assertEqual(
                hpy.call_method_no_args(
                    "receiver", "name", context_cname="ctx"),
                "HPy_CallMethod(ctx, name, &receiver, 1, HPy_NULL)",
            )
            self.assertEqual(
                hpy.call_method_array(
                    "name", "args", "2", context_cname="ctx"),
                "HPy_CallMethod(ctx, name, args, 2, HPy_NULL)",
            )
            self.assertEqual(
                hpy.call_method_array(
                    "name", "args", "1", "kwnames", context_cname="ctx"),
                "HPy_CallMethod(ctx, name, args, 1, kwnames)",
            )
            self.assertEqual(
                hpy.call_positional_array(
                    "callable", "args", "2", context_cname="ctx"),
                "HPy_Call(ctx, callable, args, 2, HPy_NULL)",
            )
            self.assertEqual(
                hpy.call_array_with_keyword_names(
                    "callable", "args", "1", "kwnames", context_cname="ctx"),
                "HPy_Call(ctx, callable, args, 1, kwnames)",
            )
            self.assertEqual(hpy.argument_tracker_type_cname(), "HPyTracker")
            self.assertEqual(
                hpy.parse_keyword_arguments(
                    "tracker", "args", "nargs", "kwnames", '"OO:pair"',
                    "keywords", ("first", "second"), context_cname="ctx"),
                "HPyArg_ParseKeywords(ctx, &tracker, args, nargs, kwnames, "
                '"OO:pair", keywords, &first, &second)',
            )
            self.assertEqual(
                hpy.parse_keyword_dictionary(
                    "tracker", "args", "nargs", "kw", '"O:__init__"',
                    "keywords", ("value",), context_cname="ctx"),
                "HPyArg_ParseKeywordsDict(ctx, &tracker, args, nargs, kw, "
                '"O:__init__", keywords, &value)',
            )
            self.assertEqual(
                hpy.close_argument_tracker("tracker", context_cname="ctx"),
                "HPyTracker_Close(ctx, tracker);",
            )
            self.assertEqual(
                hpy.length("kwnames", context_cname="ctx"),
                "HPy_Length(ctx, kwnames)",
            )
            self.assertEqual(
                hpy.item_get_index("kwnames", "i", context_cname="ctx"),
                "HPy_GetItem_i(ctx, kwnames, i)",
            )
            self.assertEqual(
                hpy.unicode_as_utf8_and_size(
                    "name", "size", context_cname="ctx"),
                "HPyUnicode_AsUTF8AndSize(ctx, name, &size)",
            )
            self.assertEqual(
                hpy.truth_test("value", context_cname="ctx"),
                "HPy_IsTrue(ctx, value)",
            )
            self.assertEqual(
                hpy.binary_operation(
                    RuntimeBinaryOperation.ADD, "left", "right",
                    context_cname="ctx"),
                "HPy_Add(ctx, left, right)",
            )
            binary_functions = {
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
            for operation, function in binary_functions.items():
                self.assertEqual(
                    hpy.binary_operation(
                        operation, "left", "right", context_cname="ctx"),
                    "%s(ctx, left, right)" % function,
                )
            self.assertEqual(
                hpy.binary_operation(
                    RuntimeBinaryOperation.POWER, "left", "right",
                    context_cname="ctx"),
                "HPy_Power(ctx, left, right, ctx->h_None)",
            )
            unary_functions = {
                RuntimeUnaryOperation.POSITIVE: "HPy_Positive",
                RuntimeUnaryOperation.NEGATIVE: "HPy_Negative",
                RuntimeUnaryOperation.INVERT: "HPy_Invert",
            }
            for operation, function in unary_functions.items():
                self.assertEqual(
                    hpy.unary_operation(
                        operation, "operand", context_cname="ctx"),
                    "%s(ctx, operand)" % function,
                )
            inplace_functions = {
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
            for operation, function in inplace_functions.items():
                self.assertEqual(
                    hpy.inplace_operation(
                        operation, "left", "right", context_cname="ctx"),
                    "%s(ctx, left, right)" % function,
                )
            self.assertEqual(
                hpy.inplace_operation(
                    RuntimeInPlaceOperation.POWER, "left", "right",
                    context_cname="ctx"),
                "HPy_InPlacePower(ctx, left, right, ctx->h_None)",
            )
            self.assertEqual(
                hpy.rich_compare(
                    RuntimeComparisonOperation.EQUAL, "left", "right",
                    context_cname="ctx"),
                "HPy_RichCompare(ctx, left, right, HPy_EQ)",
            )
            self.assertEqual(
                hpy.identity_test("left", "right", context_cname="ctx"),
                "HPy_Is(ctx, left, right)",
            )
            self.assertEqual(
                hpy.contains("container", "key", context_cname="ctx"),
                "HPy_Contains(ctx, container, key)",
            )
            self.assertEqual(
                hpy.context_constant(
                    RuntimeContextConstant.SLICE_TYPE, context_cname="ctx"),
                "ctx->h_SliceType",
            )
            self.assertEqual(hpy.null_reference_value(), "HPy_NULL")
            self.assertEqual(
                hpy.empty_reference("value"), "value = HPy_NULL;")
            self.assertEqual(hpy.null_check("value"), "HPy_IsNull(value)")
            self.assertEqual(
                hpy.close_reference("value", context_cname="ctx"),
                "HPy_Close(ctx, value);",
            )
            self.assertEqual(
                hpy.duplicate_reference("value", context_cname="ctx"),
                "HPy_Dup(ctx, value)",
            )
            self.assertEqual(
                hpy.duplicate_reference(
                    "value", null_safe=True, context_cname="ctx"),
                "HPy_IsNull(value) ? HPy_NULL : HPy_Dup(ctx, value)",
            )
            self.assertEqual(
                hpy.close_reference(
                    "value", null_safe=True, context_cname="ctx"),
                "if (!HPy_IsNull(value)) HPy_Close(ctx, value);",
            )

    def test_backend_selection_is_confined_to_compilation_setup(self):
        compiler_dir = Path(__file__).parents[1]
        allowed = {"CmdLine.py", "Main.py", "Options.py", "RuntimeAPI.py"}
        bypasses = []
        for source_path in compiler_dir.glob("*.py"):
            if source_path.name in allowed:
                continue
            source = source_path.read_text(encoding="utf8")
            for spelling in (
                "hpy-universal", "hpy-cpython", "CPYTHON_BACKEND",
                "HPY_UNIVERSAL_BACKEND", "HPY_CPYTHON_BACKEND",
            ):
                if spelling in source:
                    bypasses.append("%s: %s" % (source_path.name, spelling))
        self.assertEqual(bypasses, [])

    def test_runtime_api_does_not_select_c_or_cpp_language(self):
        runtime_source = Path(__file__).parents[1].joinpath(
            "RuntimeAPI.py").read_text(encoding="utf8")
        for spelling in ("__cplusplus", "is_cpp(", ".cplus", "c_suffix"):
            self.assertNotIn(spelling, runtime_source)

    def test_module_slot_definitions_have_no_compiler_bypass(self):
        compiler_dir = Path(__file__).parents[1]
        source_path = compiler_dir / "ModuleNode.py"
        bypasses = []
        for line_number, line in enumerate(
            source_path.read_text(encoding="utf8").splitlines(), 1
        ):
            source = line.split("#", 1)[0]
            if any(spelling in source for spelling in (
                "{Py_mod_", "PyModuleDef_Init", "PyModuleDef_Slot",
                "extern struct PyModuleDef", "static struct PyModuleDef",
            )):
                bypasses.append("%s:%d" % (source_path.name, line_number))
        self.assertEqual(bypasses, [])

    def test_type_spec_slot_entries_have_no_compiler_bypass(self):
        compiler_dir = Path(__file__).parents[1]
        bypasses = []
        for emitter_name in ("ModuleNode.py", "TypeSlots.py"):
            source_path = compiler_dir / emitter_name
            for line_number, line in enumerate(
                source_path.read_text(encoding="utf8").splitlines(), 1
            ):
                if any(
                    spelling in line.split("#", 1)[0]
                    for spelling in (
                        "{Py_tp_", "{Py_nb_", "{Py_sq_", "{Py_mp_",
                        "{Py_bf_", "{Py_am_",
                    )
                ):
                    bypasses.append("%s:%d" % (source_path.name, line_number))
        self.assertEqual(bypasses, [])

    def test_method_definitions_have_no_compiler_bypass(self):
        compiler_dir = Path(__file__).parents[1]
        bypasses = []
        for emitter_name in ("Code.py", "ModuleNode.py", "Nodes.py"):
            source_path = compiler_dir / emitter_name
            for line_number, line in enumerate(
                source_path.read_text(encoding="utf8").splitlines(), 1
            ):
                if "PyMethodDef" in line.split("#", 1)[0]:
                    bypasses.append("%s:%d" % (source_path.name, line_number))
        self.assertEqual(bypasses, [])

    def test_core_module_operations_have_no_compiler_bypass(self):
        compiler_dir = Path(__file__).parents[1]
        forbidden_spellings = (
            "PyImport_ImportModule(",
            "PyObject_SetAttr(",
            "PyObject_SetAttrString(",
            "PyModule_Create(",
            "PyModule_GetDict(",
            "PyImport_GetModuleDict(",
            "__Pyx_PyImport_AddModuleRef(",
        )
        bypasses = []
        emitter_names = (
            "Code.py", "ExprNodes.py", "ModuleNode.py", "Nodes.py", "PyrexTypes.py",
        )
        for emitter_name in emitter_names:
            source_path = compiler_dir / emitter_name
            for line_number, line in enumerate(
                source_path.read_text(encoding="utf8").splitlines(), 1
            ):
                line = line.split("#", 1)[0]
                if not line.strip():
                    continue
                for spelling in forbidden_spellings:
                    if spelling in line:
                        bypasses.append(
                            "%s:%d: %s" % (
                                source_path.name, line_number, spelling)
                        )
        self.assertEqual(bypasses, [])

    def test_runtime_global_loads_use_the_ownership_aware_writer(self):
        compiler_dir = Path(__file__).parents[1]
        bypasses = []
        for source_path in compiler_dir.glob("*.py"):
            if source_path.name in {"Code.py", "RuntimeAPI.py"}:
                continue
            for line_number, line in enumerate(
                source_path.read_text(encoding="utf8").splitlines(), 1
            ):
                if ".global_load(" in line.split("#", 1)[0]:
                    bypasses.append("%s:%d" % (source_path.name, line_number))
        self.assertEqual(bypasses, [])

    def test_dynamic_name_lookups_have_no_compiler_bypass(self):
        compiler_dir = Path(__file__).parents[1]
        forbidden_spellings = (
            "__Pyx_GetModuleGlobalName(",
            "__Pyx_GetBuiltinName(",
            "__Pyx_GetNameInClass(",
        )
        bypasses = []
        emitter_names = (
            "Code.py", "ExprNodes.py", "ModuleNode.py", "Nodes.py", "PyrexTypes.py",
        )
        for emitter_name in emitter_names:
            source_path = compiler_dir / emitter_name
            for line_number, line in enumerate(
                source_path.read_text(encoding="utf8").splitlines(), 1
            ):
                line = line.split("#", 1)[0]
                if not line.strip():
                    continue
                for spelling in forbidden_spellings:
                    if spelling in line:
                        bypasses.append(
                            "%s:%d: %s" % (
                                source_path.name, line_number, spelling)
                        )
        self.assertEqual(bypasses, [])

    def test_core_exception_operations_have_no_compiler_bypass(self):
        compiler_dir = Path(__file__).parents[1]
        forbidden_spellings = (
            "PyErr_SetString(",
            "PyErr_SetObject(",
            "PyErr_SetNone(",
            "PyErr_Format(",
            "PyErr_Clear(",
            "PyErr_NoMemory(",
            "PyErr_ExceptionMatches(",
            "__Pyx_PyErr_GivenExceptionMatches(",
            "__Pyx_PyErr_CurrentExceptionType(",
            "__Pyx_PyErr_FetchException(",
            "__Pyx_PyErr_RestoreException(",
            "__Pyx_Raise(",
            "__Pyx_ReraiseException(",
            "__Pyx_GetException(",
            "__Pyx_ExceptionSave(",
            "__Pyx_ExceptionReset(",
            "__Pyx_ExceptionSwap(",
        )
        bypasses = []
        emitter_names = (
            "Buffer.py", "Code.py", "ExprNodes.py", "ModuleNode.py",
            "Nodes.py", "PyrexTypes.py",
        )
        for emitter_name in emitter_names:
            source_path = compiler_dir / emitter_name
            for line_number, line in enumerate(
                source_path.read_text(encoding="utf8").splitlines(), 1
            ):
                line = line.split("#", 1)[0]
                if not line.strip():
                    continue
                for spelling in forbidden_spellings:
                    if spelling in line:
                        bypasses.append(
                            "%s:%d: %s" % (
                                source_path.name, line_number, spelling)
                        )
        self.assertEqual(bypasses, [])

    def test_fixed_size_container_construction_has_no_compiler_bypass(self):
        compiler_dir = Path(__file__).parents[1]
        forbidden_spellings = (
            "PyList_New(",
            "PyTuple_New(",
            "PyDict_New(",
            "__Pyx_PyDict_NewPresized(",
            "__Pyx_PyList_SET_ITEM(",
            "__Pyx_PyTuple_SET_ITEM(",
            "PyDict_SetItem(",
            "PyDict_SetItemString(",
            "PyTuple_Pack(",
        )
        bypasses = []
        emitter_names = (
            "Code.py", "ExprNodes.py", "ModuleNode.py", "Nodes.py", "PyrexTypes.py",
        )
        for emitter_name in emitter_names:
            source_path = compiler_dir / emitter_name
            for line_number, line in enumerate(
                source_path.read_text(encoding="utf8").splitlines(), 1
            ):
                line = line.split("#", 1)[0]
                if not line.strip():
                    continue
                for spelling in forbidden_spellings:
                    if spelling in line:
                        bypasses.append(
                            "%s:%d: %s" % (
                                source_path.name, line_number, spelling)
                        )
        self.assertEqual(bypasses, [])

    def test_operation_groups_cover_initial_runtime_surface(self):
        self.assertEqual(
            {group.value for group in RuntimeOperationGroup},
            {
                "objects", "calls", "containers", "conversions",
                "exceptions", "globals", "modules", "types",
            },
        )
        self.assertEqual(
            {capability.group for capability in RuntimeCapability},
            set(RuntimeOperationGroup),
        )

    def test_cpython_supports_declared_capabilities(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        for capability in RuntimeCapability:
            self.assertTrue(runtime_api.supports(capability))
            self.assertIsNone(runtime_api.require_capability(capability))
        self.assertIsNone(runtime_api.ensure_compilation_ready())

    def test_cpython_untyped_reference_operations_preserve_spelling(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(runtime_api.duplicate_reference("value"), "Py_INCREF(value);")
        self.assertEqual(
            runtime_api.duplicate_reference("value", null_safe=True),
            "Py_XINCREF(value);",
        )
        self.assertEqual(runtime_api.close_reference("value"), "Py_DECREF(value);")
        self.assertEqual(
            runtime_api.close_reference("value", null_safe=True),
            "Py_XDECREF(value);",
        )
        self.assertEqual(runtime_api.clear_reference("value"), "Py_CLEAR(value);")
        self.assertEqual(runtime_api.error_occurred(), "PyErr_Occurred()")
        self.assertEqual(
            runtime_api.error_occurred(use_utility_code=True),
            "__Pyx_PyErr_Occurred()",
        )

    def test_cpython_call_operations_preserve_spelling(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(
            runtime_api.call_tuple_dict("func", "args"),
            "__Pyx_PyObject_Call(func, args, NULL)",
        )
        self.assertEqual(
            runtime_api.call_tuple_dict(
                "func", "args", "kwargs", use_utility_code=False),
            "PyObject_Call(func, args, kwargs)",
        )
        self.assertEqual(
            runtime_api.call_no_args("func"),
            "__Pyx_PyObject_CallNoArg(func)",
        )
        self.assertEqual(
            runtime_api.call_one_arg("func", "arg"),
            "__Pyx_PyObject_CallOneArg(func, arg)",
        )
        self.assertEqual(
            runtime_api.call_method_no_args("obj", "name"),
            "__Pyx_PyObject_CallMethod0(obj, name)",
        )

    def test_cpython_array_call_layouts_preserve_spelling(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        expected = {
            (False, RuntimeCallKeywordLayout.NONE): (
                "PyObjectFastCall", "__Pyx_PyObject_FastCall"),
            (False, RuntimeCallKeywordLayout.KEYWORD_NAMES): (
                "PyObjectVectorcallKwds", "__Pyx_Object_VectorcallKwds"),
            (False, RuntimeCallKeywordLayout.KEYWORD_DICT): (
                "PyObjectFastCall", "__Pyx_PyObject_FastCallDict"),
            (True, RuntimeCallKeywordLayout.NONE): (
                "PyObjectFastCallMethod", "__Pyx_PyObject_FastCallMethod"),
            (True, RuntimeCallKeywordLayout.KEYWORD_NAMES): (
                "PyObjectVectorcallMethodKwds", "__Pyx_Object_VectorcallMethodKwds"),
        }
        for (includes_receiver, keyword_layout), names in expected.items():
            call = runtime_api.select_array_call(includes_receiver, keyword_layout)
            self.assertEqual(
                (call.utility_code_name, call.function_cname),
                names,
            )
            self.assertEqual(call.includes_receiver, includes_receiver)
            self.assertIs(call.keyword_layout, keyword_layout)

        call = runtime_api.select_array_call(False, RuntimeCallKeywordLayout.NONE)
        self.assertEqual(
            runtime_api.call_array(call, "func", "args", "nargs"),
            "__Pyx_PyObject_FastCall(func, args, nargs)",
        )

        call = runtime_api.select_array_call(True, RuntimeCallKeywordLayout.KEYWORD_NAMES)
        self.assertEqual(
            runtime_api.call_array(call, "name", "args", "nargs", "kwnames"),
            "__Pyx_Object_VectorcallMethodKwds(name, args, nargs, kwnames)",
        )

        with self.assertRaisesRegex(ValueError, "unsupported CPython array-call layout"):
            runtime_api.select_array_call(True, RuntimeCallKeywordLayout.KEYWORD_DICT)

    def test_array_call_rejects_keyword_layout_mismatches(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        call = runtime_api.select_array_call(
            includes_receiver=False,
            keyword_layout=RuntimeCallKeywordLayout.KEYWORD_DICT,
        )
        with self.assertRaisesRegex(ValueError, "keyword operand"):
            runtime_api.call_array(call, "func", "args", "nargs")

    def test_cpython_sequence_builder_contract_preserves_spelling_and_ownership(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        expected_names = {
            RuntimeSequenceKind.LIST: ("PyList_New(3)", "__Pyx_PyList_SET_ITEM"),
            RuntimeSequenceKind.TUPLE: ("PyTuple_New(3)", "__Pyx_PyTuple_SET_ITEM"),
        }
        for kind, (new_code, set_function) in expected_names.items():
            builder = runtime_api.sequence_builder(kind)
            self.assertEqual(builder.builder_type_cname, "PyObject *")
            self.assertEqual(builder.result_type_cname, "PyObject *")
            self.assertFalse(builder.uses_separate_builder)
            self.assertTrue(builder.set_item_steals_reference)
            self.assertTrue(builder.creation_reports_error)
            self.assertTrue(builder.supports_from_array)
            self.assertEqual(
                runtime_api.sequence_builder_new(builder, "3"),
                new_code,
            )
            self.assertEqual(
                runtime_api.sequence_builder_set(builder, "result", "1", "item"),
                "%s(result, 1, item)" % set_function,
            )
            self.assertEqual(
                runtime_api.sequence_builder_build(builder, "result"),
                "result",
            )
            self.assertEqual(
                runtime_api.sequence_builder_cancel(builder, "result"),
                "Py_DECREF(result);",
            )

    def test_hpy_sequence_builder_contract_models_distinct_non_stealing_builder(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        expected_names = {
            RuntimeSequenceKind.LIST: "List",
            RuntimeSequenceKind.TUPLE: "Tuple",
        }
        for kind, kind_name in expected_names.items():
            builder = runtime_api.sequence_builder(kind)
            self.assertEqual(builder.builder_type_cname, "HPy%sBuilder" % kind_name)
            self.assertEqual(builder.result_type_cname, "HPy")
            self.assertTrue(builder.uses_separate_builder)
            self.assertFalse(builder.set_item_steals_reference)
            self.assertFalse(builder.creation_reports_error)
            self.assertEqual(
                builder.supports_from_array,
                kind is RuntimeSequenceKind.TUPLE,
            )
            self.assertEqual(
                runtime_api.sequence_builder_new(builder, "3", "ctx"),
                "HPy%sBuilder_New(ctx, 3)" % kind_name,
            )
            self.assertEqual(
                runtime_api.sequence_builder_set(
                    builder, "builder", "1", "item", "ctx"),
                "HPy%sBuilder_Set(ctx, builder, 1, item)" % kind_name,
            )
            self.assertEqual(
                runtime_api.sequence_builder_build(builder, "builder", "ctx"),
                "HPy%sBuilder_Build(ctx, builder)" % kind_name,
            )
            self.assertEqual(
                runtime_api.sequence_builder_cancel(builder, "builder", "ctx"),
                "HPy%sBuilder_Cancel(ctx, builder);" % kind_name,
            )

        with self.assertRaisesRegex(ValueError, "requires a context cname"):
            runtime_api.sequence_builder_new(
                runtime_api.sequence_builder(RuntimeSequenceKind.LIST), "3")

    def test_sequence_array_and_pack_construction_contracts(self):
        cpython = create_runtime_api(CPYTHON_BACKEND)
        for kind, kind_name in (
            (RuntimeSequenceKind.LIST, "List"),
            (RuntimeSequenceKind.TUPLE, "Tuple"),
        ):
            operation = cpython.select_sequence_from_array(kind)
            self.assertEqual(operation.function_cname, "__Pyx_Py%s_FromArray" % kind_name)
            self.assertEqual(operation.utility_code_name, "%sFromArray" % kind_name)
            self.assertEqual(operation.utility_code_file, "ObjectHandling.c")
            self.assertEqual(
                cpython.sequence_from_array(operation, "items", "3"),
                "__Pyx_Py%s_FromArray(items, 3)" % kind_name,
            )
        self.assertEqual(
            cpython.sequence_pack(
                RuntimeSequenceKind.TUPLE, ["first", "second"]),
            "PyTuple_Pack(2, first, second)",
        )

        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        operation = hpy.select_sequence_from_array(RuntimeSequenceKind.TUPLE)
        self.assertEqual(
            hpy.sequence_from_array(operation, "items", "3", "ctx"),
            "HPyTuple_FromArray(ctx, items, 3)",
        )
        self.assertEqual(
            hpy.sequence_pack(RuntimeSequenceKind.TUPLE, ["first"], "ctx"),
            "HPyTuple_Pack(ctx, 1, first)",
        )
        with self.assertRaises(RuntimeCapabilityError):
            hpy.select_sequence_from_array(RuntimeSequenceKind.LIST)
        with self.assertRaises(RuntimeCapabilityError):
            hpy.sequence_pack(RuntimeSequenceKind.LIST, [], "ctx")

    def test_dict_construction_contracts_preserve_cpython_and_model_hpy(self):
        cpython = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(cpython.dict_new(), "PyDict_New()")
        self.assertEqual(
            cpython.dict_new("size"), "__Pyx_PyDict_NewPresized(size)")
        self.assertEqual(
            cpython.dict_set_item("d", "key", "value"),
            "PyDict_SetItem(d, key, value)",
        )
        self.assertEqual(
            cpython.dict_set_item_string("d", '"key"', "value"),
            'PyDict_SetItemString(d, "key", value)',
        )
        self.assertEqual(cpython.dict_copy("d"), "PyDict_Copy(d)")

        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        self.assertEqual(hpy.dict_new(context_cname="ctx"), "HPyDict_New(ctx)")
        self.assertEqual(
            hpy.dict_new("size", "ctx"),
            "HPyDict_New(ctx)",
        )
        self.assertEqual(
            hpy.dict_set_item("d", "key", "value", "ctx"),
            "HPy_SetItem(ctx, d, key, value)",
        )
        self.assertEqual(
            hpy.dict_set_item_string("d", '"key"', "value", "ctx"),
            'HPy_SetItem_s(ctx, d, "key", value)',
        )
        self.assertEqual(hpy.dict_copy("d", "ctx"), "HPyDict_Copy(ctx, d)")

    def test_primitive_conversion_metadata_is_semantic(self):
        cases = (
            (PyrexTypes.c_bint_type, RuntimeConversionKind.BOOLEAN),
            (PyrexTypes.c_int_type, RuntimeConversionKind.SIGNED_INTEGER),
            (PyrexTypes.c_uint_type, RuntimeConversionKind.UNSIGNED_INTEGER),
            (PyrexTypes.c_double_type, RuntimeConversionKind.FLOAT),
            (PyrexTypes.c_double_complex_type, RuntimeConversionKind.COMPLEX),
            (PyrexTypes.c_py_ucs4_type, RuntimeConversionKind.UNICODE_CODEPOINT),
        )
        for type_, expected_kind in cases:
            conversion = type_.runtime_conversion(
                RuntimeConversionDirection.TO_PYTHON, "conversion_helper")
            self.assertIs(conversion.direction, RuntimeConversionDirection.TO_PYTHON)
            self.assertIs(conversion.kind, expected_kind)
            self.assertEqual(conversion.function_cname, "conversion_helper")
            self.assertIs(conversion.type_, type_)

    def test_hpy_conversion_contract_fails_explicitly_until_ownership_model(self):
        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        conversion = PyrexTypes.c_double_type.runtime_conversion(
            RuntimeConversionDirection.TO_PYTHON, "PyFloat_FromDouble")
        with self.assertRaises(RuntimeCapabilityError) as raised:
            hpy.to_python_conversion(
                conversion,
                "value",
                "result",
                PyrexTypes.py_object_type,
            )
        self.assertEqual(
            raised.exception.capability,
            RuntimeCapability.VALUE_CONVERSIONS,
        )

    def test_cpython_exception_operations_preserve_spelling(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(
            runtime_api.error_set_string("PyExc_TypeError", '"bad"'),
            'PyErr_SetString(PyExc_TypeError, "bad")',
        )
        self.assertEqual(
            runtime_api.error_set_object("PyExc_ValueError", "value"),
            "PyErr_SetObject(PyExc_ValueError, value)",
        )
        self.assertEqual(
            runtime_api.error_set_none("PyExc_StopIteration"),
            "PyErr_SetNone(PyExc_StopIteration)",
        )
        self.assertEqual(
            runtime_api.error_format("PyExc_TypeError", '"bad %s"', ["name"]),
            'PyErr_Format(PyExc_TypeError, "bad %s", name)',
        )
        self.assertEqual(runtime_api.error_clear(), "PyErr_Clear()")
        self.assertEqual(runtime_api.error_no_memory(), "PyErr_NoMemory()")
        self.assertEqual(
            runtime_api.current_exception_type(),
            "__Pyx_PyErr_CurrentExceptionType()",
        )
        self.assertEqual(
            runtime_api.exception_matches("PyExc_KeyError"),
            "PyErr_ExceptionMatches(PyExc_KeyError)",
        )
        self.assertEqual(
            runtime_api.exception_matches(
                "pattern", "exc", use_utility_code=True),
            "__Pyx_PyErr_GivenExceptionMatches(exc, pattern)",
        )
        self.assertEqual(
            runtime_api.exception_matches(
                "first", "exc", "second", use_utility_code=True),
            "__Pyx_PyErr_GivenExceptionMatches2(exc, first, second)",
        )
        self.assertEqual(
            runtime_api.fetch_exception("&type", "&value", "&tb"),
            "__Pyx_PyErr_FetchException(&type, &value, &tb)",
        )
        self.assertEqual(
            runtime_api.restore_exception("type", "value", "tb"),
            "__Pyx_PyErr_RestoreException(type, value, tb)",
        )
        self.assertEqual(
            runtime_api.raise_exception("type", "value", "tb", "cause"),
            "__Pyx_Raise(type, value, tb, cause)",
        )
        self.assertEqual(runtime_api.reraise_exception(), "__Pyx_ReraiseException()")
        self.assertEqual(
            runtime_api.get_exception(["&type", "&value", "&tb"]),
            "__Pyx_GetException(&type, &value, &tb)",
        )
        self.assertEqual(
            runtime_api.save_exception(["type", "value", "tb"]),
            "__Pyx_ExceptionSave(type, value, tb)",
        )
        self.assertEqual(
            runtime_api.reset_exception(["type", "value", "tb"]),
            "__Pyx_ExceptionReset(type, value, tb)",
        )
        self.assertEqual(
            runtime_api.swap_exception(["&type", "&value", "&tb"]),
            "__Pyx_ExceptionSwap(&type, &value, &tb)",
        )

    def test_hpy_exception_core_and_triple_contracts_are_distinct(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        self.assertEqual(
            runtime_api.error_set_string("ctx->h_TypeError", '"bad"', "ctx"),
            'HPyErr_SetString(ctx, ctx->h_TypeError, "bad")',
        )
        self.assertEqual(runtime_api.error_clear("ctx"), "HPyErr_Clear(ctx)")
        self.assertEqual(
            runtime_api.error_set_none("ctx->h_StopIteration", "ctx"),
            "HPyErr_SetObject(ctx, ctx->h_StopIteration, ctx->h_None)",
        )
        self.assertEqual(runtime_api.error_no_memory("ctx"), "HPyErr_NoMemory(ctx)")
        self.assertEqual(
            runtime_api.exception_matches("ctx->h_KeyError", context_cname="ctx"),
            "HPyErr_ExceptionMatches(ctx, ctx->h_KeyError)",
        )
        with self.assertRaises(RuntimeCapabilityError) as raised:
            runtime_api.fetch_exception("&type", "&value", "&tb", "ctx")
        self.assertEqual(
            raised.exception.capability,
            RuntimeCapability.EXCEPTION_STATE,
        )
        with self.assertRaises(RuntimeCapabilityError):
            runtime_api.exception_matches(
                "pattern", exception_cname="exc", context_cname="ctx")
        with self.assertRaises(RuntimeCapabilityError):
            runtime_api.current_exception_type(context_cname="ctx")

    def test_cpython_dynamic_name_lookups_preserve_spelling(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(
            runtime_api.name_lookup(
                RuntimeNameLookup(RuntimeNameLookupKind.MODULE_GLOBAL),
                "result", "name"),
            "__Pyx_GetModuleGlobalName(result, name)",
        )
        self.assertEqual(
            runtime_api.name_lookup(
                RuntimeNameLookup(RuntimeNameLookupKind.BUILTIN),
                "result", "name"),
            "result = __Pyx_GetBuiltinName(name)",
        )
        self.assertEqual(
            runtime_api.name_lookup(
                RuntimeNameLookup(RuntimeNameLookupKind.CLASS_NAMESPACE),
                "result", "name", "namespace"),
            "__Pyx_GetNameInClass(result, namespace, name)",
        )
        self.assertEqual(
            runtime_api.name_lookup(
                RuntimeNameLookup(
                    RuntimeNameLookupKind.CLASS_NAMESPACE,
                    namespace_is_type=True),
                "result", "name", "namespace"),
            "__Pyx_GetNameInClass(result, (PyObject*)namespace, name)",
        )

    def test_dynamic_name_lookup_contract_rejects_invalid_layouts(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        with self.assertRaises(TypeError):
            runtime_api.name_lookup("module", "result", "name")
        with self.assertRaises(ValueError):
            runtime_api.name_lookup(
                RuntimeNameLookup(RuntimeNameLookupKind.MODULE_GLOBAL),
                "result", "name", "namespace")
        with self.assertRaises(ValueError):
            runtime_api.name_lookup(
                RuntimeNameLookup(RuntimeNameLookupKind.CLASS_NAMESPACE),
                "result", "name")

    def test_hpy_dynamic_name_lookup_fails_until_global_ownership_model(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        with self.assertRaises(RuntimeCapabilityError) as raised:
            runtime_api.name_lookup(
                RuntimeNameLookup(RuntimeNameLookupKind.MODULE_GLOBAL),
                "result", "name", context_cname="ctx")
        self.assertEqual(
            raised.exception.capability,
            RuntimeCapability.MODULE_GLOBALS,
        )

    def test_global_storage_contract_exposes_ownership_and_registration(self):
        cpython = create_runtime_api(CPYTHON_BACKEND)
        cpython_storage = cpython.global_storage()
        self.assertIs(
            cpython_storage.kind,
            RuntimeGlobalStorageKind.CPYTHON_OBJECT,
        )
        self.assertEqual(cpython_storage.storage_type_cname, "PyObject *")
        self.assertFalse(cpython_storage.requires_module_registration)
        self.assertFalse(cpython_storage.load_returns_owned_reference)
        self.assertTrue(cpython_storage.store_consumes_reference)
        self.assertFalse(cpython_storage.runtime_manages_stored_lifetime)
        self.assertEqual(cpython.global_load("slot"), "slot")
        self.assertEqual(cpython.global_store("slot", "value"), "slot = value")
        self.assertEqual(
            cpython.field_load("owner", "owner->field"),
            "Py_XNewRef(owner->field)",
        )
        self.assertEqual(
            cpython.field_store("owner", "owner->field", "value"),
            "Py_XSETREF(owner->field, Py_XNewRef(value))",
        )

        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        hpy_storage = hpy.global_storage()
        self.assertIs(
            hpy_storage.kind,
            RuntimeGlobalStorageKind.REGISTERED_HPY_GLOBAL,
        )
        self.assertEqual(hpy_storage.storage_type_cname, "HPyGlobal")
        self.assertTrue(hpy_storage.requires_module_registration)
        self.assertTrue(hpy_storage.load_returns_owned_reference)
        self.assertFalse(hpy_storage.store_consumes_reference)
        self.assertTrue(hpy_storage.runtime_manages_stored_lifetime)
        self.assertEqual(
            hpy.global_load("slot", "ctx"),
            "HPyGlobal_Load(ctx, slot)",
        )
        self.assertEqual(
            hpy.global_store("slot", "value", "ctx"),
            "HPyGlobal_Store(ctx, &slot, value)",
        )
        self.assertEqual(
            hpy.field_load("owner", "data->field", "ctx"),
            "HPyField_Load(ctx, owner, data->field)",
        )
        self.assertEqual(
            hpy.field_store("owner", "data->field", "value", "ctx"),
            "HPyField_Store(ctx, owner, &data->field, value)",
        )

    def test_module_definition_contract_exposes_structural_difference(self):
        cpython = create_runtime_api(CPYTHON_BACKEND).module_definition()
        self.assertIs(
            cpython.kind,
            RuntimeModuleInitializationKind.CPYTHON_CONFIGURABLE,
        )
        self.assertEqual(cpython.definition_type_cname, "struct PyModuleDef")
        self.assertFalse(cpython.requires_multiphase_init)
        self.assertFalse(cpython.init_returns_definition)
        self.assertFalse(cpython.init_has_context)
        self.assertFalse(cpython.execution_uses_slot)
        self.assertFalse(cpython.execution_receives_context)
        self.assertTrue(cpython.supports_manual_creation)
        self.assertTrue(cpython.supports_legacy_methods)
        self.assertFalse(cpython.supports_registered_globals)

        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND).module_definition()
        self.assertIs(
            hpy.kind,
            RuntimeModuleInitializationKind.HPY_MULTIPHASE,
        )
        self.assertEqual(hpy.definition_type_cname, "HPyModuleDef")
        self.assertTrue(hpy.requires_multiphase_init)
        self.assertTrue(hpy.init_returns_definition)
        self.assertFalse(hpy.init_has_context)
        self.assertTrue(hpy.execution_uses_slot)
        self.assertTrue(hpy.execution_receives_context)
        self.assertFalse(hpy.supports_manual_creation)
        self.assertFalse(hpy.supports_legacy_methods)
        self.assertTrue(hpy.supports_registered_globals)

    def test_cpython_module_operations_preserve_spelling(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(
            runtime_api.import_module('"example"'),
            'PyImport_ImportModule("example")',
        )
        self.assertEqual(
            runtime_api.module_set_attr("module", "name", "value"),
            "PyObject_SetAttr(module, name, value)",
        )
        self.assertEqual(
            runtime_api.module_set_attr_string("module", '"name"', "value"),
            'PyObject_SetAttrString(module, "name", value)',
        )
        self.assertEqual(
            runtime_api.module_create("moduledef"),
            "PyModule_Create(&moduledef)",
        )
        self.assertEqual(
            runtime_api.module_get_dict("module"),
            "PyModule_GetDict(module)",
        )
        self.assertEqual(
            runtime_api.import_add_module_ref('"example"'),
            '__Pyx_PyImport_AddModuleRef("example")',
        )
        self.assertEqual(
            runtime_api.import_get_module_dict(),
            "PyImport_GetModuleDict()",
        )

    def test_hpy_equivalent_module_operations_use_context(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        self.assertEqual(
            runtime_api.import_module('"example"', "ctx"),
            'HPyImport_ImportModule(ctx, "example")',
        )
        self.assertEqual(
            runtime_api.module_set_attr("module", "name", "value", "ctx"),
            "HPy_SetAttr(ctx, module, name, value)",
        )
        self.assertEqual(
            runtime_api.module_set_attr_string(
                "module", '"name"', "value", "ctx"),
            'HPy_SetAttr_s(ctx, module, "name", value)',
        )
        for operation in (
            lambda: runtime_api.module_create("moduledef", "ctx"),
            lambda: runtime_api.module_get_dict("module", "ctx"),
            lambda: runtime_api.import_add_module_ref('"example"', "ctx"),
            lambda: runtime_api.import_get_module_dict("ctx"),
        ):
            with self.assertRaises(RuntimeCapabilityError) as raised:
                operation()
            self.assertEqual(
                raised.exception.capability,
                RuntimeCapability.MODULE_DEFINITIONS,
            )

    def test_module_slot_definition_contract_is_structural(self):
        cpython = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(
            cpython.module_slot_definition(
                "mod_exec", "exec_impl", pointer_cast="(void*)"),
            "{Py_mod_exec, (void*)exec_impl},",
        )
        self.assertEqual(
            cpython.module_slot_definition("mod_gil", "gil_policy"),
            "{Py_mod_gil, gil_policy},",
        )
        self.assertEqual(cpython.module_slot_terminator(), "{0, NULL}")
        self.assertEqual(
            cpython.module_definition_forward_declaration(
                "moduledef", "extern"),
            "extern struct PyModuleDef moduledef;",
        )
        self.assertEqual(
            cpython.module_slot_array_declaration("slots"),
            "static PyModuleDef_Slot slots[] = {",
        )
        self.assertEqual(
            cpython.module_definition_declaration("moduledef", "static"),
            "static struct PyModuleDef moduledef =",
        )
        self.assertEqual(
            cpython.module_init_definition_result("moduledef"),
            "PyModuleDef_Init(&moduledef)",
        )

        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        self.assertEqual(
            hpy.module_slot_definition("mod_exec", "exec_def"),
            "HPyDef_SLOT(exec_def, HPy_mod_exec)",
        )
        self.assertEqual(hpy.module_slot_terminator(), "NULL")
        self.assertEqual(
            hpy.module_definition_forward_declaration("moduledef", "extern"),
            "extern HPyModuleDef moduledef;",
        )
        self.assertEqual(
            hpy.module_slot_array_declaration("defines"),
            "static HPyDef *defines[] = {",
        )
        self.assertEqual(
            hpy.module_definition_declaration("moduledef", "static"),
            "static HPyModuleDef moduledef =",
        )
        with self.assertRaises(RuntimeCapabilityError):
            hpy.module_init_definition_result("moduledef")
        with self.assertRaises(RuntimeCapabilityError) as raised:
            hpy.module_slot_definition("mod_gil", "gil_policy")
        self.assertEqual(
            raised.exception.capability,
            RuntimeCapability.MODULE_DEFINITIONS,
        )

    def test_runtime_method_signature_selection_is_explicit(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        layouts = {
            ("METH_NOARGS",): RuntimeMethodSignature.NOARGS,
            ("METH_O",): RuntimeMethodSignature.ONEARG,
            ("METH_VARARGS", "METH_KEYWORDS"):
                RuntimeMethodSignature.VARARGS_KEYWORDS,
            ("__Pyx_METH_FASTCALL", "METH_KEYWORDS"):
                RuntimeMethodSignature.FASTCALL_KEYWORDS,
        }
        for flags, expected in layouts.items():
            self.assertIs(runtime_api.select_method_signature(flags), expected)
        with self.assertRaisesRegex(ValueError, "method flag layout"):
            runtime_api.select_method_signature(("METH_CLASS",))

    def test_cpython_method_definition_contract_preserves_spelling(self):
        runtime_api = create_runtime_api(CPYTHON_BACKEND)
        definition = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.FASTCALL_KEYWORDS,
            definition_cname="method_def",
            python_name_cname='"method"',
            implementation_cname="method_impl",
            doc_cname="method_doc",
            coexists_with_slot=True,
        )
        self.assertEqual(
            runtime_api.method_definition_prefix("method_def"),
            "static PyMethodDef method_def = ",
        )
        self.assertEqual(runtime_api.method_definition_declaration(definition), "")
        self.assertEqual(
            runtime_api.method_table_declaration("methods"),
            "static PyMethodDef methods[] = {",
        )
        self.assertEqual(
            runtime_api.method_table_entry(definition, ","),
            '{"method", (PyCFunction)(void(*)(void))'
            '(__Pyx_PyCFunction_FastCallWithKeywords)method_impl, '
            '__Pyx_METH_FASTCALL|METH_KEYWORDS|METH_COEXIST, method_doc},',
        )
        self.assertEqual(runtime_api.method_table_terminator(), "{0, 0, 0, 0}")
        self.assertEqual(runtime_api.method_table_end(), "};")
        noargs = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.NOARGS,
            definition_cname="noargs_def",
            python_name_cname='"noargs"',
            implementation_cname="noargs_impl",
            doc_cname="0",
        )
        self.assertEqual(
            runtime_api.method_implementation_declaration(noargs),
            "static PyObject *noargs_impl(PyObject *self, PyObject *unused)",
        )
        onearg = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.ONEARG,
            definition_cname="onearg",
            python_name_cname='"onearg"',
            implementation_cname="onearg_impl",
            doc_cname="0",
        )
        self.assertEqual(
            runtime_api.method_implementation_declaration(onearg),
            "static PyObject *onearg_impl(PyObject *self, PyObject *arg)",
        )

    def test_hpy_method_definition_contract_uses_definitions_array(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        definition = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.VARARGS_KEYWORDS,
            definition_cname="method_def",
            python_name_cname='"method"',
            implementation_cname="method_def_impl",
            doc_cname="method_doc",
        )
        self.assertEqual(
            runtime_api.method_definition_declaration(definition),
            'HPyDef_METH(method_def, "method", HPyFunc_KEYWORDS)',
        )
        self.assertEqual(
            runtime_api.method_table_declaration("methods"),
            "static HPyDef *methods[] = {",
        )
        self.assertEqual(
            runtime_api.method_table_entry(definition, ","),
            "&method_def,",
        )
        self.assertEqual(runtime_api.method_table_terminator(), "NULL")
        self.assertEqual(runtime_api.method_table_end(), "};")

        noargs = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.NOARGS,
            definition_cname="noargs_def",
            python_name_cname='"noargs"',
            implementation_cname="noargs_def_impl",
            doc_cname="0",
        )
        self.assertEqual(
            runtime_api.method_implementation_declaration(
                noargs, context_cname="ctx"),
            "static HPy noargs_def_impl(HPyContext *ctx, HPy self)",
        )
        onearg = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.ONEARG,
            definition_cname="onearg_def",
            python_name_cname='"onearg"',
            implementation_cname="onearg_def_impl",
            doc_cname="0",
        )
        self.assertEqual(
            runtime_api.method_implementation_declaration(
                onearg, context_cname="ctx", argument_cname="arg"),
            "static HPy onearg_def_impl(HPyContext *ctx, HPy self, HPy arg)",
        )
        keywords = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.VARARGS_KEYWORDS,
            definition_cname="keywords_def",
            python_name_cname='"keywords"',
            implementation_cname="keywords_def_impl",
            doc_cname="0",
        )
        self.assertEqual(
            runtime_api.method_implementation_declaration(
                keywords, context_cname="ctx"),
            "static HPy keywords_def_impl(HPyContext *ctx, HPy self, "
            "const HPy *args, size_t nargs, HPy kwnames)",
        )

        invalid = RuntimeMethodDefinition(
            signature=RuntimeMethodSignature.NOARGS,
            definition_cname="method_def",
            python_name_cname='"method"',
            implementation_cname="wrong_impl",
            doc_cname="0",
        )
        with self.assertRaises(RuntimeCapabilityError):
            runtime_api.method_definition_declaration(invalid)

    def test_type_definition_contract_exposes_pure_hpy_layout(self):
        cpython = create_runtime_api(CPYTHON_BACKEND).type_definition()
        self.assertIs(
            cpython.kind,
            RuntimeTypeSpecificationKind.CPYTHON_SLOT_SPEC,
        )
        self.assertEqual(cpython.specification_type_cname, "PyType_Spec")
        self.assertTrue(cpython.uses_slot_array)
        self.assertFalse(cpython.uses_definition_array)
        self.assertFalse(cpython.requires_builtin_shape)
        self.assertTrue(cpython.supports_legacy_slots)
        self.assertFalse(cpython.pure_layout_omits_object_header)

        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND).type_definition()
        self.assertIs(hpy.kind, RuntimeTypeSpecificationKind.HPY_PURE_SPEC)
        self.assertEqual(hpy.specification_type_cname, "HPyType_Spec")
        self.assertFalse(hpy.uses_slot_array)
        self.assertTrue(hpy.uses_definition_array)
        self.assertTrue(hpy.requires_builtin_shape)
        self.assertFalse(hpy.supports_legacy_slots)
        self.assertTrue(hpy.pure_layout_omits_object_header)

    def test_type_slot_contract_preserves_or_rejects_semantics(self):
        cpython = create_runtime_api(CPYTHON_BACKEND)
        self.assertEqual(
            cpython.type_slot_table_entry(
                "tp_repr", "repr_def", "repr_impl"),
            "{Py_tp_repr, (void *)repr_impl},",
        )
        self.assertEqual(
            cpython.type_slot_table_entry(
                "tp_members", "members_def", "members",
                pointer_cast="(void*)"),
            "{Py_tp_members, (void*)members},",
        )
        self.assertEqual(
            cpython.type_definition_array_declaration("Example"),
            "static PyType_Slot Example_slots[] = {",
        )
        self.assertEqual(
            cpython.type_definition_array_terminator(), "{0, 0},")
        self.assertEqual(
            cpython.type_specification_declaration("Example"),
            "static PyType_Spec Example_spec = {",
        )
        self.assertEqual(
            cpython.type_from_spec("Example"),
            "PyType_FromSpec(&Example)",
        )

        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        self.assertEqual(
            hpy.type_slot_definition(
                "tp_repr", "repr_def", "repr_def_impl"),
            "HPyDef_SLOT(repr_def, HPy_tp_repr)",
        )
        self.assertEqual(
            hpy.type_slot_table_entry(
                "tp_repr", "repr_def", "repr_def_impl"),
            "&repr_def,",
        )
        self.assertEqual(
            hpy.type_definition_array_declaration("Example"),
            "static HPyDef *Example_defines[] = {",
        )
        self.assertEqual(hpy.type_definition_array_terminator(), "NULL")
        self.assertEqual(
            hpy.type_specification_declaration("Example"),
            "static HPyType_Spec Example_spec = {",
        )
        self.assertEqual(
            hpy.type_from_spec("Example", context_cname="ctx"),
            "HPyType_FromSpec(ctx, &Example, NULL)",
        )
        with self.assertRaises(RuntimeCapabilityError) as raised:
            hpy.type_slot_definition(
                "tp_members", "members_def", "members_def_impl")
        self.assertEqual(
            raised.exception.capability,
            RuntimeCapability.TYPE_DEFINITIONS,
        )

    def test_capability_error_is_actionable(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        with self.assertRaises(RuntimeCapabilityError) as raised:
            runtime_api.require_capability(
                RuntimeCapability.TYPE_DEFINITIONS,
                reason="legacy type slots require an HPy type specification",
                guidance="replace the legacy slot or select the CPython backend",
            )
        error = raised.exception
        self.assertEqual(error.backend, HPY_UNIVERSAL_BACKEND)
        self.assertEqual(error.capability, RuntimeCapability.TYPE_DEFINITIONS)
        self.assertIn("type-definitions", str(error))
        self.assertIn("legacy type slots", str(error))
        self.assertIn("replace the legacy slot", str(error))

    def test_capability_error_preserves_source_position(self):
        class Source:
            def get_lines(self):
                return ["def example():", "    pass"]

            def get_error_description(self):
                return "example.pyx"

        position = (Source(), 2, 4)
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        with self.assertRaises(RuntimeCapabilityError) as raised:
            runtime_api.require_capability(
                RuntimeCapability.PYTHON_CALLS,
                position=position,
                reason="call form is unsupported",
                guidance="use positional arguments",
            )
        self.assertEqual(raised.exception.position, position)
        self.assertIn("example.pyx:2:4", str(raised.exception))

    def test_universal_backend_enters_strict_codegen_lane(self):
        options = Options.CompilationOptions(
            runtime_backend=HPY_UNIVERSAL_BACKEND)
        context = Main.Context.from_options(options)
        self.assertEqual(context.runtime_api.name, HPY_UNIVERSAL_BACKEND)
        self.assertIs(
            context.runtime_api.code_generation_kind(),
            RuntimeCodeGenerationKind.HPY_UNIVERSAL_BOOTSTRAP,
        )
        self.assertIsNone(context.runtime_api.ensure_compilation_ready())

    def test_hpy_cpython_backend_remains_unavailable(self):
        options = Options.CompilationOptions(runtime_backend=HPY_CPYTHON_BACKEND)
        with self.assertRaises(RuntimeBackendUnavailableError) as raised:
            Main.Context.from_options(options)
        self.assertEqual(raised.exception.backend, HPY_CPYTHON_BACKEND)

    def test_universal_backend_generates_public_hpy_translation_unit(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "bootstrap_answer.pyx"
            output = Path(temp_dir) / "bootstrap_answer.c"
            source.write_text(
                "def answer():\n"
                "    return 42\n\n"
                "def return_none():\n"
                "    return None\n",
                encoding="utf8",
            )
            result = Main.compile(
                str(source),
                Options.CompilationOptions(
                    output_file=str(output),
                    language_level=3,
                    runtime_backend=HPY_UNIVERSAL_BACKEND,
                ),
            )
            self.assertEqual(result.num_errors, 0)
            generated = output.read_text(encoding="utf8")
            for required in (
                "#include <hpy.h>",
                "HPyDef_METH",
                "HPyLong_FromLongLong(ctx, 42LL)",
                "HPy_Dup(ctx, ctx->h_None)",
                "HPy_MODINIT(bootstrap_answer, __pyx_hpy_module)",
            ):
                self.assertIn(required, generated)
            for forbidden in (
                "Python.h", "PyObject", "struct PyMethodDef", "struct PyModuleDef",
                "PyLong_FromLong(", "Py_INCREF", "Py_DECREF",
            ):
                self.assertNotIn(forbidden, generated)

    def test_universal_backend_rejects_unsupported_source_without_fallback(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "unsupported.pyx"
            output = Path(temp_dir) / "unsupported.c"
            source.write_text("value = 1\n", encoding="utf8")
            diagnostics = io.StringIO()
            with redirect_stderr(diagnostics):
                result = Main.compile(
                    str(source),
                    Options.CompilationOptions(
                        output_file=str(output),
                        language_level=3,
                        runtime_backend=HPY_UNIVERSAL_BACKEND,
                    ),
                )
            self.assertEqual(result.num_errors, 1)
            self.assertFalse(output.exists())
            message = diagnostics.getvalue()
            self.assertIn("unsupported.pyx:1:0", message)
            self.assertIn(
                "require at least one supported def", message)

    def test_unknown_and_reserved_backends_are_rejected(self):
        for backend in ("not-a-runtime", HPY_HYBRID_BACKEND):
            with self.assertRaises(RuntimeBackendOptionError):
                Options.CompilationOptions(runtime_backend=backend)

    def test_context_selection_has_no_process_global_state(self):
        first = Main.Context.from_options(Options.CompilationOptions())
        second = Main.Context.from_options(Options.CompilationOptions())
        self.assertEqual(first.runtime_api.name, CPYTHON_BACKEND)
        self.assertEqual(second.runtime_api.name, CPYTHON_BACKEND)
        self.assertIsNot(first.runtime_api, second.runtime_api)

    def test_backend_participates_in_cache_fingerprint(self):
        cpython = Options.CompilationOptions(runtime_backend=CPYTHON_BACKEND)
        hpy = Options.CompilationOptions(runtime_backend=HPY_UNIVERSAL_BACKEND)
        self.assertNotEqual(cpython.get_fingerprint(), hpy.get_fingerprint())

    def test_explicit_cpython_backend_preserves_generated_output(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "representative.pyx"
            output = Path(temp_dir) / "representative.c"
            source.write_text(
                "def answer(object value):\n"
                "    return {'value': value, 'items': [value, 42]}\n",
                encoding="utf8",
            )

            default_result = Main.compile(
                str(source),
                Options.CompilationOptions(output_file=str(output), language_level=3),
            )
            self.assertEqual(default_result.num_errors, 0)
            default_output = output.read_bytes()

            explicit_result = Main.compile(
                str(source),
                Options.CompilationOptions(
                    output_file=str(output),
                    language_level=3,
                    runtime_backend=CPYTHON_BACKEND,
                ),
            )
            self.assertEqual(explicit_result.num_errors, 0)
            self.assertEqual(output.read_bytes(), default_output)
