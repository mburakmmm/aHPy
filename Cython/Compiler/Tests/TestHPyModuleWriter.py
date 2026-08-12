from contextlib import redirect_stderr
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from .. import ExprNodes, Main, Nodes, Optimize, Options, PyrexTypes, UtilNodes
from ..Errors import CompileError
from ..HPyModuleWriter import (
    _ClosureCapture,
    _ClosureEnvSpec,
    _ClosureFnSpec,
    _ClosureRegistry,
    _HPyConstantRegistry,
    _HPyDefaultRegistry,
    _HPyNameRegistry,
    UniversalHPyFunctionWriter,
    UniversalHPyModuleWriter,
    _c_identifier_fragment,
    _external_c_scalar_kind,
    _extension_field_storage,
    _resolve_extension_field_storage_type,
    _supports_extension_field_storage,
)
from ..RuntimeAPI import (
    HPY_UNIVERSAL_BACKEND,
    RuntimeContextConstant,
    RuntimeInPlaceOperation,
    RuntimeMethodSignature,
    RuntimeSequenceKind,
    create_runtime_api,
)


class _OwnedNoneExpression:
    is_starred = False
    pos = None
    constant_result = None

    @staticmethod
    def generate_hpy_bootstrap_owned_result(writer):
        return writer.runtime_api.duplicate_reference(
            writer.runtime_api.context_constant(
                RuntimeContextConstant.NONE,
                context_cname=writer.context_cname,
            ),
            context_cname=writer.context_cname,
        )


class _OwnedKeywordNames(_OwnedNoneExpression):
    def __init__(self, args, mult_factor=None):
        self.args = list(args)
        self.mult_factor = mult_factor


class _EmitLineStatement:
    def __init__(self, line):
        self.line = line

    def generate_hpy_bootstrap_execution_code(self, writer):
        writer.putln(self.line)


class _CorruptLoopStackStatement:
    def generate_hpy_bootstrap_execution_code(self, writer):
        writer._loop_stack.append("corrupt")


class UniversalHPyEmitterContractTest(TestCase):
    def test_python_identifier_c_fragments_preserve_ascii_and_encode_unicode(self):
        self.assertEqual(_c_identifier_fragment("answer"), "answer")
        self.assertEqual(
            _c_identifier_fragment("değer"),
            "unicode_6465c49f6572",
        )

    def test_field_storage_helpers_reject_nonportable_types(self):
        external = PyrexTypes.create_typedef_type(
            "external_int", PyrexTypes.c_int_type, "external_int_t",
            is_external=1,
        )
        self.assertIsNone(_resolve_extension_field_storage_type(external))
        self.assertIsNone(_external_c_scalar_kind(external))
        self.assertFalse(
            _supports_extension_field_storage(PyrexTypes.c_void_type))
        self.assertIsNone(_external_c_scalar_kind(PyrexTypes.c_void_type))
        self.assertIsNone(
            _external_c_scalar_kind(PyrexTypes.c_py_ssize_t_type))
        with self.assertRaisesRegex(
            AssertionError, "unvalidated pure HPy extension field"
        ):
            _extension_field_storage(PyrexTypes.c_void_type, "field")
        fixed_array = PyrexTypes.CArrayType(PyrexTypes.c_long_type, 4)
        self.assertFalse(_supports_extension_field_storage(fixed_array))
        self.assertEqual(
            _extension_field_storage(fixed_array, "values"),
            ("long values[4]", None, "fixed-array:signed-long"),
        )
        with self.assertRaisesRegex(
            AssertionError, "unvalidated pure HPy extension array"
        ):
            _extension_field_storage(
                PyrexTypes.CArrayType(fixed_array, 2), "matrix")
        with self.assertRaisesRegex(
            AssertionError, "unvalidated pure HPy extension array element"
        ):
            _extension_field_storage(
                PyrexTypes.CArrayType(PyrexTypes.c_void_type, 4), "items")

    def test_buffer_metadata_layout_must_share_exported_field_struct(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)
        field = object()
        shape = object()
        stride = object()
        with self.assertRaisesRegex(
            AssertionError, "buffer metadata must share the field layout"
        ):
            module_writer._render_extension_buffer_slots(
                ((field, shape, stride, "l", 1),
                 "getbuffer", "releasebuffer"),
                {
                    id(field): ("Exporter", "value", "signed-long"),
                    id(shape): ("Other", "shape", "py-ssize"),
                    id(stride): ("Exporter", "stride", "py-ssize"),
                },
            )

    def test_closure_registry_layouts_are_identity_stable(self):
        entry = SimpleNamespace(name="captured")
        outer = object()
        inner_def = object()
        inner_node = object()
        capture = _ClosureCapture(
            "captured", entry, "__pyx_hpy_capture_captured")
        env_spec = _ClosureEnvSpec(2, outer, (capture,))
        fn_spec = _ClosureFnSpec(
            3, inner_def, inner_node, env_spec)
        registry = _ClosureRegistry((env_spec,), (fn_spec,))

        expected = (
            env_spec.struct_cname,
            "__pyx_hpy_capture_captured",
            "object",
        )
        env_layout = registry.field_layout_for_env(env_spec)
        self.assertEqual(env_layout[id(entry)], expected)
        self.assertEqual(env_layout[("field", "captured")], expected)
        self.assertEqual(
            registry.field_layout_for_fn_env_field(fn_spec),
            {
                ("field", fn_spec.env_field_cname): (
                    fn_spec.struct_cname,
                    fn_spec.env_field_cname,
                    "object",
                ),
            },
        )
        self.assertIs(registry.env_by_outer[id(outer)], env_spec)
        self.assertIs(registry.fn_by_inner_def[id(inner_def)], fn_spec)
        self.assertIs(registry.fn_by_inner_node[id(inner_node)], fn_spec)

    def test_name_constant_and_default_registries_cover_edge_contracts(self):
        names = _HPyNameRegistry()
        module_cname = names.require_module_global("value")
        self.assertEqual(names.require_module_global("value"), module_cname)
        with self.assertRaisesRegex(ValueError, "both module and builtin"):
            names.require_builtin("value")
        builtin_cname = names.require_builtin("len")
        self.assertEqual(
            list(names.entries("builtin")), [("len", builtin_cname)])

        constants = _HPyConstantRegistry()
        invalid_integer = ExprNodes.IntNode(None, value="not-an-integer")
        self.assertIsNone(constants.constant_key(invalid_integer))
        self.assertIsNone(constants.register_node(invalid_integer))
        supported = ExprNodes.NoneNode(None)
        attribute = constants.register_node(supported)
        self.assertEqual(constants.attribute_for_node(supported), attribute)
        cloned = ExprNodes.NoneNode(None)
        self.assertEqual(constants.attribute_for_node(cloned), attribute)
        self.assertEqual(list(constants.entries()), [(attribute, supported)])

        defaults = _HPyDefaultRegistry()
        no_default = SimpleNamespace(default=None)
        self.assertIsNone(defaults.register_argument(no_default))
        argument = SimpleNamespace(default=ExprNodes.IntNode(None, value="1"))
        explicit = ExprNodes.IntNode(None, value="2")
        default_attribute = defaults.register_argument(argument, explicit)
        self.assertEqual(
            defaults.attribute_for_argument(argument), default_attribute)
        self.assertEqual(
            defaults.argument_id_for_attribute(default_attribute),
            id(argument),
        )
        self.assertEqual(
            list(defaults.entries()), [(default_attribute, explicit)])

    def test_supported_default_classifier_covers_nested_dicts_and_rejections(self):
        key = ExprNodes.UnicodeNode(None, value="key")
        value = ExprNodes.ListNode(
            None, args=[ExprNodes.IntNode(None, value="1")])
        item = ExprNodes.DictItemNode(None, key=key, value=value)
        mapping = ExprNodes.DictNode(None, key_value_pairs=[item])
        self.assertTrue(UniversalHPyModuleWriter._is_supported_default(mapping))
        mapping.reject_duplicates = True
        self.assertFalse(UniversalHPyModuleWriter._is_supported_default(mapping))
        self.assertFalse(
            UniversalHPyModuleWriter._is_supported_default(
                ExprNodes.NameNode(None, name="dynamic")))

    def test_function_writer_internal_state_guards_are_fail_closed(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(AssertionError, "below zero"):
            writer.dedent()

        writer.bind_borrowed_argument("value", "arg")
        with self.assertRaisesRegex(AssertionError, "already bound"):
            writer.bind_borrowed_argument("value", "other")

        writer.bind_extension_runtime_owners("self")
        with self.assertRaisesRegex(AssertionError, "receiver changed"):
            writer.bind_extension_runtime_owners("other")
        unavailable = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(AssertionError, "owners are unavailable"):
            unavailable.ensure_extension_runtime_owners()

        writer._push_failure_scope("fail")
        with self.assertRaisesRegex(AssertionError, "nested"):
            writer._push_failure_scope("nested")
        with self.assertRaisesRegex(AssertionError, "changed"):
            writer._pop_failure_scope("wrong")
        with self.assertRaisesRegex(AssertionError, "stack is empty"):
            writer._pop_failure_scope("missing")

        writer._failure_scopes.append({"label": "live"})
        with self.assertRaisesRegex(AssertionError, "remain live"):
            writer.assert_function_exit()
        writer._failure_scopes.clear()
        writer.assert_function_exit()

    def test_starred_sequence_generator_covers_all_segment_shapes(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        writer = UniversalHPyFunctionWriter(runtime_api)
        plain = _OwnedNoneExpression()
        starred = SimpleNamespace(is_starred=True, target=_OwnedNoneExpression())
        result_cname = writer.generate_starred_sequence(
            RuntimeSequenceKind.LIST,
            (plain, starred, plain),
            factor=_OwnedNoneExpression(),
        )
        writer.close_owned_handle(result_cname)
        writer.assert_function_exit()
        output = "\n".join(writer.lines)
        self.assertIn("HPyListBuilder_New", output)
        self.assertIn("HPy_Call(ctx, ctx->h_ListType", output)
        self.assertGreaterEqual(output.count("HPy_Add(ctx,"), 2)
        self.assertIn("HPy_Multiply(ctx,", output)

        empty_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(AssertionError, "requires arguments"):
            empty_writer.generate_starred_sequence(
                RuntimeSequenceKind.TUPLE, ())
        empty_writer.assert_function_exit()

    def test_direct_inplace_emitters_balance_local_attribute_and_item_ownership(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        writer = UniversalHPyFunctionWriter(runtime_api)
        writer.bind_borrowed_argument("left", "left_arg")
        writer.inplace_local(
            SimpleNamespace(pos=None),
            "left",
            RuntimeInPlaceOperation.ADD,
            _OwnedNoneExpression(),
        )
        writer.delete_local(SimpleNamespace(pos=None), "left")

        writer.inplace_attribute(
            _OwnedNoneExpression(),
            '"value"',
            RuntimeInPlaceOperation.MULTIPLY,
            _OwnedNoneExpression(),
        )
        writer.inplace_item(
            _OwnedNoneExpression(),
            _OwnedNoneExpression(),
            RuntimeInPlaceOperation.SUBTRACT,
            _OwnedNoneExpression(),
        )
        writer._close_remaining_owned_handles()
        writer.assert_function_exit()
        output = "\n".join(writer.lines)
        self.assertIn("HPy_InPlaceAdd(ctx,", output)
        self.assertIn("HPy_GetAttr_s(ctx,", output)
        self.assertIn("HPy_SetAttr_s(ctx,", output)
        self.assertIn("HPy_GetItem(ctx,", output)
        self.assertIn("HPy_SetItem(ctx,", output)

    def test_owned_assignment_targets_cover_local_global_attribute_and_item(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        names = _HPyNameRegistry()
        names.require_module_global("global_value")
        writer = UniversalHPyFunctionWriter(
            runtime_api,
            name_registry=names,
            module_cname="m",
            rollback_module_publications=True,
        )

        local_target = ExprNodes.NameNode(None, name="local")
        local_target.entry = None
        value_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        writer.assign_target_from_owned_cname(local_target, value_cname)
        writer.delete_local(local_target, "local")

        global_target = ExprNodes.NameNode(None, name="global_value")
        global_target.entry = SimpleNamespace(is_pyglobal=True)
        value_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        writer.assign_target_from_owned_cname(global_target, value_cname)

        attribute_target = ExprNodes.AttributeNode(
            None, obj=_OwnedNoneExpression(), attribute="value")
        attribute_target.entry = None
        value_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        writer.assign_target_from_owned_cname(attribute_target, value_cname)

        item_target = ExprNodes.IndexNode(
            None, base=_OwnedNoneExpression(), index=_OwnedNoneExpression())
        value_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        writer.assign_target_from_owned_cname(item_target, value_cname)

        writer._close_remaining_owned_handles()
        writer.assert_function_exit()
        output = "\n".join(writer.lines)
        self.assertIn('HPy_SetAttr_s(ctx, m, "global_value"', output)
        self.assertIn("HPy_SetAttr_s(ctx,", output)
        self.assertIn("HPy_SetItem(ctx,", output)

    def test_native_scalar_conversion_contract_covers_every_storage_family(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        writer = UniversalHPyFunctionWriter(runtime_api)
        storage_kinds = (
            "bint", "py-ssize",
            "char", "signed-char", "signed-short", "signed-int", "signed-long",
            "signed-long-long",
            "unsigned-char", "unsigned-short", "unsigned-int",
            "unsigned-long", "unsigned-long-long",
            "float", "double", "long-double",
        )
        for storage_kind in storage_kinds:
            with self.subTest(storage_kind=storage_kind):
                value_cname = writer.allocate_owned_handle(
                    "HPy_Dup(ctx, ctx->h_None)")
                native_value = writer._convert_native_scalar_handle(
                    storage_kind, value_cname)
                self.assertTrue(native_value)
                writer.close_owned_handle(value_cname)

        invalid_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        with self.assertRaisesRegex(AssertionError, "unknown native"):
            writer._convert_native_scalar_handle(
                "unsupported", invalid_cname)
        writer.close_owned_handle(invalid_cname)
        writer.assert_function_exit()
        output = "\n".join(writer.lines)
        self.assertIn("HPyLong_AsLongLong(ctx,", output)
        self.assertIn("HPyLong_AsUnsignedLongLong(ctx,", output)
        self.assertIn("HPyFloat_AsDouble(ctx,", output)
        self.assertIn("value too large to convert", output)

    def test_extension_field_inplace_paths_cover_object_native_and_python_results(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        def emit(storage_kind, operation):
            entry = SimpleNamespace(name="field")
            writer = UniversalHPyFunctionWriter(
                runtime_api,
                extension_field_layout={
                    id(entry): ("ExampleObject", "field", storage_kind),
                },
            )
            field_node = SimpleNamespace(
                entry=entry, obj=_OwnedNoneExpression(), pos=None)
            writer.inplace_extension_field(
                field_node, operation, _OwnedNoneExpression())
            writer._close_remaining_owned_handles()
            writer.assert_function_exit()
            return "\n".join(writer.lines)

        native_output = emit(
            "signed-int", RuntimeInPlaceOperation.ADD)
        self.assertIn("->field +=", native_output)
        self.assertIn("HPyLong_AsLong(ctx,", native_output)

        python_result_output = emit(
            "signed-int", RuntimeInPlaceOperation.TRUE_DIVIDE)
        self.assertIn("HPy_InPlaceTrueDivide(ctx,", python_result_output)
        self.assertIn("->field =", python_result_output)

        object_output = emit(
            "object", RuntimeInPlaceOperation.MULTIPLY)
        self.assertIn("HPyField_Load(ctx,", object_output)
        self.assertIn("HPy_InPlaceMultiply(ctx,", object_output)
        self.assertIn("HPyField_Store(ctx,", object_output)

        guard_cases = (
            (
                "bint",
                RuntimeInPlaceOperation.TRUE_DIVIDE,
                "bint extension-field",
            ),
            (
                "signed-int",
                RuntimeInPlaceOperation.MATRIX_MULTIPLY,
                "native C extension fields currently support",
            ),
        )
        for storage_kind, operation, message in guard_cases:
            with self.subTest(message=message):
                entry = SimpleNamespace(name="field")
                writer = UniversalHPyFunctionWriter(
                    runtime_api,
                    extension_field_layout={
                        id(entry): ("ExampleObject", "field", storage_kind),
                    },
                )
                with self.assertRaisesRegex(CompileError, message):
                    writer.inplace_extension_field(
                        SimpleNamespace(
                            entry=entry,
                            obj=_OwnedNoneExpression(),
                            pos=None,
                        ),
                        operation,
                        _OwnedNoneExpression(),
                    )
                writer._close_remaining_owned_handles()
                writer.assert_function_exit()

        invalid_entry = SimpleNamespace(name="field")
        invalid_writer = UniversalHPyFunctionWriter(
            runtime_api,
            extension_field_layout={
                id(invalid_entry): (
                    "ExampleObject", "field", "unsupported"),
            },
        )
        with self.assertRaisesRegex(
            AssertionError, "unknown extension field storage kind"
        ):
            invalid_writer.load_extension_field(SimpleNamespace(
                entry=invalid_entry,
                obj=_OwnedNoneExpression(),
                pos=None,
            ))
        invalid_writer._close_remaining_owned_handles()
        invalid_writer.assert_function_exit()

    def test_keyword_duplicate_guard_covers_static_and_dynamic_names(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        unique_writer = UniversalHPyFunctionWriter(runtime_api)
        unique_writer._guard_keyword_name_duplicates(SimpleNamespace(args=[
            ExprNodes.UnicodeNode(None, value="left"),
            ExprNodes.UnicodeNode(None, value="right"),
        ]))
        unique_writer.assert_function_exit()
        self.assertEqual(unique_writer.lines, [])

        duplicate_writer = UniversalHPyFunctionWriter(runtime_api)
        duplicate_writer._guard_keyword_name_duplicates(SimpleNamespace(args=[
            ExprNodes.UnicodeNode(None, value="value"),
            ExprNodes.UnicodeNode(None, value="value"),
        ]))
        duplicate_writer.assert_function_exit()
        self.assertIn(
            "got multiple values for keyword argument",
            "\n".join(duplicate_writer.lines),
        )

        dynamic_writer = UniversalHPyFunctionWriter(runtime_api)
        dynamic_writer._guard_keyword_name_duplicates(SimpleNamespace(args=[
            _OwnedNoneExpression(),
            _OwnedNoneExpression(),
        ]))
        dynamic_writer.assert_function_exit()
        dynamic_output = "\n".join(dynamic_writer.lines)
        self.assertIn("HPyDict_New(ctx)", dynamic_output)
        self.assertIn("HPy_Contains(ctx,", dynamic_output)
        self.assertIn("HPy_SetItem(ctx,", dynamic_output)

    def test_external_scalar_literal_helpers_cover_portability_boundaries(self):
        literal_value = UniversalHPyFunctionWriter._external_c_scalar_literal_value
        render = UniversalHPyFunctionWriter._render_external_c_scalar_literal

        self.assertEqual(literal_value(ExprNodes.BoolNode(None, value=True)), True)
        self.assertEqual(literal_value(ExprNodes.CharNode(None, value="A")), 65)
        self.assertIsNone(
            literal_value(ExprNodes.IntNode(None, value="not-an-integer")))
        self.assertIsNone(
            literal_value(ExprNodes.FloatNode(None, value="not-a-float")))
        self.assertIsNone(literal_value(_OwnedNoneExpression()))

        positive = ExprNodes.UnaryPlusNode(
            None, operand=ExprNodes.IntNode(None, value="7"))
        negative = ExprNodes.UnaryMinusNode(
            None, operand=ExprNodes.IntNode(None, value="7"))
        invalid_unary = ExprNodes.UnaryMinusNode(
            None, operand=ExprNodes.IntNode(None, value="invalid"))
        self.assertEqual(literal_value(positive), 7)
        self.assertEqual(literal_value(negative), -7)
        self.assertIsNone(literal_value(invalid_unary))

        self.assertEqual(
            render(ExprNodes.BoolNode(None, value=False), "bint"), "0")
        self.assertEqual(
            render(ExprNodes.CharNode(None, value="A"), "char"),
            "((char)65)",
        )
        self.assertEqual(
            render(ExprNodes.IntNode(None, value="-128"), "signed-char"),
            "((signed char)-128)",
        )
        self.assertEqual(
            render(ExprNodes.IntNode(None, value="255"), "unsigned-char"),
            "((unsigned char)255ULL)",
        )
        self.assertIsNone(
            render(ExprNodes.IntNode(None, value="-1"), "unsigned-int"))
        self.assertIsNone(
            render(ExprNodes.IntNode(None, value="1"), "unsupported"))
        self.assertIsNone(
            render(ExprNodes.FloatNode(None, value="1e10000"), "double"))
        self.assertIsNone(
            render(
                ExprNodes.IntNode(None, value="1" + "0" * 4000),
                "double",
            ))
        self.assertIsNone(
            render(ExprNodes.FloatNode(None, value="1.25"), "signed-int"))
        self.assertEqual(
            render(ExprNodes.BoolNode(None, value=True), "float"),
            "((float)1.0)",
        )

    def test_external_scalar_call_guards_and_ssize_result_are_exercised(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        def call_node(
            storage_kind="py-ssize",
            *,
            cname="external_size",
            args=(),
            argument_kinds=(),
            receiver=None,
            coerced_receiver=None,
        ):
            entry = SimpleNamespace(
                cname=cname,
                ahpy_universal_external_c_scalar_kind=storage_kind,
                ahpy_universal_external_c_argument_kinds=argument_kinds,
            )
            node = SimpleNamespace(
                coerced_self=coerced_receiver,
                args=args,
                function=SimpleNamespace(entry=entry),
                pos=None,
            )
            # PyPy exposes SimpleNamespace.__init__() with a named ``self``
            # receiver, so passing an AST field with that name as a keyword
            # raises "multiple values for argument 'self'".
            node.self = receiver
            return node

        writer = UniversalHPyFunctionWriter(runtime_api)
        result_cname = writer.generate_external_c_scalar_call(call_node())
        writer.close_owned_handle(result_cname)
        writer.assert_function_exit()
        self.assertIn(
            "HPyLong_FromSsize_t(ctx, external_size())",
            "\n".join(writer.lines),
        )

        guard_cases = (
            (
                call_node(receiver=object()),
                "receiver injection",
            ),
            (
                call_node(args=None),
                "expanded external C call arguments",
            ),
            (
                call_node(storage_kind=None),
                "validated by a concrete",
            ),
            (
                call_node(cname="not-a-c-identifier"),
                "plain C identifiers",
            ),
        )
        for node, message in guard_cases:
            with self.subTest(message=message):
                guarded_writer = UniversalHPyFunctionWriter(runtime_api)
                with self.assertRaisesRegex(CompileError, message):
                    guarded_writer.generate_external_c_scalar_call(node)
                guarded_writer.assert_function_exit()

        with self.assertRaisesRegex(
            AssertionError, "validated external C signature changed"
        ):
            UniversalHPyFunctionWriter(
                runtime_api).generate_external_c_scalar_call(
                    call_node(args=(_OwnedNoneExpression(),)))

        with self.assertRaisesRegex(
            AssertionError, "unknown validated external C scalar kind"
        ):
            UniversalHPyFunctionWriter(
                runtime_api).generate_external_c_scalar_call(
                    call_node(storage_kind="unsupported"))

    def test_nogil_external_block_guards_cover_each_fail_closed_contract(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        def expression(
            *,
            storage_kind="signed-int",
            function_type=None,
            cname="tick",
            receiver=None,
            args=(),
            argument_kinds=(),
        ):
            if function_type is None:
                function_type = SimpleNamespace(
                    nogil=True,
                    exception_value=None,
                    exception_check=False,
                )
            entry = SimpleNamespace(
                ahpy_universal_external_c_scalar_kind=storage_kind,
                ahpy_universal_external_c_argument_kinds=argument_kinds,
                type=function_type,
                cname=cname,
            )
            node = ExprNodes.SimpleCallNode(
                None,
                function=SimpleNamespace(entry=entry),
                args=None if args is None else list(args),
            )
            node.self = receiver
            node.coerced_self = None
            return node

        def block(*, state="nogil", condition=None, statements=()):
            body = Nodes.StatListNode(None, stats=list(statements))
            return SimpleNamespace(
                state=state,
                condition=condition,
                body=body,
                pos=None,
            )

        valid_type = SimpleNamespace(
            nogil=True,
            exception_value=None,
            exception_check=False,
        )
        implicit_gil = Nodes.GILStatNode.__new__(Nodes.GILStatNode)
        implicit_gil.state = "gil"
        implicit_gil.internally_generated = True
        implicit_gil.condition = None
        implicit_gil.body = Nodes.StatListNode(
            None, stats=[_EmitLineStatement("implicit_gil();")])
        implicit_gil.pos = None
        conditional_gil = Nodes.GILStatNode.__new__(Nodes.GILStatNode)
        conditional_gil.state = "gil"
        conditional_gil.internally_generated = False
        conditional_gil.condition = object()
        conditional_gil.body = Nodes.StatListNode(
            None, stats=[_EmitLineStatement("conditional_gil();")])
        conditional_gil.pos = None
        invalid_cases = (
            (block(state="gil"), "with gil blocks"),
            (block(condition=object()), "conditional with nogil"),
            (
                block(statements=(implicit_gil,)),
                "only an explicit with gil block may interrupt",
            ),
            (
                block(statements=(conditional_gil,)),
                "conditional with gil blocks are not implemented",
            ),
            (
                block(statements=(SimpleNamespace(pos=None),)),
                "permits only discarded calls",
            ),
            (
                block(statements=(
                    Nodes.ExprStatNode(None, expr=_OwnedNoneExpression()),)),
                "permits only discarded calls",
            ),
            (
                block(statements=(
                    Nodes.ExprStatNode(
                        None, expr=expression(receiver=object())),)),
                "method calls are not implemented",
            ),
            (
                block(statements=(
                    Nodes.ExprStatNode(
                        None, expr=expression(args=None)),)),
                "expanded external C call arguments",
            ),
            (
                block(statements=(
                    Nodes.SingleAssignmentNode(
                        None,
                        lhs=ExprNodes.TupleNode(None, args=[]),
                        rhs=expression(),
                    ),)),
                "require a Python name, attribute, item, or slice target",
            ),
            (
                block(statements=(
                    Nodes.ExprStatNode(
                        None, expr=expression(storage_kind=None)),)),
                "validated by a concrete",
            ),
            (
                block(statements=(
                    Nodes.ExprStatNode(
                        None, expr=expression(function_type=SimpleNamespace(
                            nogil=False,
                            exception_value=None,
                            exception_check=False,
                        ))),)),
                "must be declared nogil",
            ),
            (
                block(statements=(
                    Nodes.ExprStatNode(
                        None, expr=expression(function_type=SimpleNamespace(
                            nogil=True,
                            exception_value="-1",
                            exception_check=False,
                        ))),)),
                "must be noexcept",
            ),
            (
                block(statements=(
                    Nodes.ExprStatNode(
                        None, expr=expression(
                            function_type=valid_type,
                            cname="not-a-c-identifier",
                        )),)),
                "plain C identifiers",
            ),
        )
        for node, message in invalid_cases:
            with self.subTest(message=message):
                writer = UniversalHPyFunctionWriter(runtime_api)
                with self.assertRaisesRegex(CompileError, message):
                    writer.generate_nogil_external_c_block(node)
                writer.assert_function_exit()

        converted_call = expression(
            args=(_OwnedNoneExpression(),),
            argument_kinds=("signed-long",),
        )
        writer = UniversalHPyFunctionWriter(runtime_api)
        writer.generate_nogil_external_c_block(block(statements=(
            Nodes.ExprStatNode(None, expr=converted_call),)))
        writer.assert_function_exit()
        generated = "\n".join(writer.lines)
        conversion = generated.index("HPyLong_AsLong(ctx,")
        close = generated.index("HPy_Close(ctx,", conversion)
        leave = generated.index("HPy_LeavePythonExecution(ctx)")
        native_call = generated.index("(void)tick(", leave)
        reenter = generated.index("HPy_ReenterPythonExecution(ctx,", native_call)
        self.assertLess(conversion, close)
        self.assertLess(close, leave)
        self.assertLess(leave, native_call)
        self.assertLess(native_call, reenter)

        mismatched_call = expression(
            args=(ExprNodes.IntNode(None, value="1"),),
            argument_kinds=(),
        )
        with self.assertRaisesRegex(
            AssertionError,
            "validated external C signature changed inside with nogil",
        ):
            UniversalHPyFunctionWriter(
                runtime_api).generate_nogil_external_c_block(
                    block(statements=(
                        Nodes.ExprStatNode(None, expr=mismatched_call),)))

    def test_duplicate_named_value_covers_missing_name_contracts(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        writer = UniversalHPyFunctionWriter(runtime_api)
        self.assertEqual(
            writer.duplicate_named_value(
                SimpleNamespace(pos=None, allow_null=True), "missing"),
            "HPy_NULL",
        )
        with self.assertRaisesRegex(
            CompileError, "has no initialized local HPy value"
        ):
            writer.duplicate_named_value(
                SimpleNamespace(pos=None), "unregistered")
        writer.assert_function_exit()

        invalid_entry = SimpleNamespace(
            is_builtin=False,
            scope=SimpleNamespace(is_builtin_scope=False),
            is_cclass_var_entry=False,
            is_pyglobal=False,
        )
        registry_writer = UniversalHPyFunctionWriter(
            runtime_api, name_registry=_HPyNameRegistry())
        with self.assertRaisesRegex(
            CompileError, "has no initialized local HPy value"
        ):
            registry_writer.duplicate_named_value(
                SimpleNamespace(pos=None, entry=invalid_entry), "invalid")
        registry_writer.assert_function_exit()

    def test_assert_without_literal_message_uses_public_error_operations(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        no_message_writer = UniversalHPyFunctionWriter(runtime_api)
        no_message_writer.generate_assert_statement(
            _OwnedNoneExpression(),
            SimpleNamespace(exc_value=None),
        )
        no_message_writer.assert_function_exit()
        no_message_output = "\n".join(no_message_writer.lines)
        self.assertIn(
            "HPyErr_SetObject(ctx, ctx->h_AssertionError, ctx->h_None)",
            no_message_output,
        )

        dynamic_writer = UniversalHPyFunctionWriter(runtime_api)
        dynamic_writer.generate_assert_statement(
            _OwnedNoneExpression(),
            SimpleNamespace(exc_value=_OwnedNoneExpression()),
        )
        dynamic_writer.assert_function_exit()
        dynamic_output = "\n".join(dynamic_writer.lines)
        self.assertIn("HPyErr_SetObject(ctx, ctx->h_AssertionError", dynamic_output)

    def test_ssize_result_reference_contract_and_loop_cleanup_are_balanced(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        writer = UniversalHPyFunctionWriter(runtime_api)
        pos = (
            SimpleNamespace(
                get_error_description=lambda: "test",
                get_lines=lambda: [],
            ),
            1,
            0,
        )

        bound_ref = UtilNodes.ResultRefNode(pos=pos)
        writer._c_temporary_values[id(bound_ref)] = "bound_ssize"
        self.assertEqual(
            writer._materialize_ssize_expression(bound_ref), "bound_ssize")

        fallback_ref = UtilNodes.ResultRefNode(pos=pos)
        fallback_ref.result_code = "fallback_ssize"
        self.assertEqual(
            writer._materialize_ssize_expression(fallback_ref),
            "fallback_ssize",
        )

        missing_ref = UtilNodes.ResultRefNode(pos=pos)
        missing_ref.result_code = None
        with self.assertRaisesRegex(
            CompileError, "C loop bound temporary is not bound"
        ):
            writer._materialize_ssize_expression(missing_ref)

        with self.assertRaisesRegex(
            AssertionError, "loop lifetime stack is empty"
        ):
            writer._emit_loop_body_cleanup()

        snapshot = writer._snapshot_lifetime_state()
        writer._loop_lifetime_stack.append(snapshot)
        writer.allocate_owned_handle("HPy_Dup(ctx, ctx->h_None)")
        builder = runtime_api.sequence_builder(RuntimeSequenceKind.TUPLE)
        writer.allocate_sequence_builder(builder, 1)
        writer._emit_loop_body_cleanup()
        writer._loop_lifetime_stack.pop()
        writer.assert_function_exit()
        output = "\n".join(writer.lines)
        self.assertIn("HPyTupleBuilder_Cancel(ctx,", output)
        self.assertIn("HPy_Close(ctx,", output)

    def test_sequence_unpacking_covers_fixed_starred_and_rejected_shapes(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        def name(value):
            node = ExprNodes.NameNode(None, name=value)
            node.entry = None
            return node

        fixed_writer = UniversalHPyFunctionWriter(runtime_api)
        fixed_sequence = fixed_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        fixed_writer._unpack_owned_sequence_into(
            ExprNodes.TupleNode(
                None,
                args=[name("left"), name("right")],
                mult_factor=None,
            ),
            fixed_sequence,
        )
        fixed_writer._close_remaining_owned_handles()
        fixed_writer.assert_function_exit()
        fixed_output = "\n".join(fixed_writer.lines)
        self.assertIn("not enough values to unpack", fixed_output)
        self.assertIn("too many values to unpack", fixed_output)

        starred_writer = UniversalHPyFunctionWriter(runtime_api)
        starred_sequence = starred_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        starred_writer._unpack_owned_sequence_into(
            ExprNodes.ListNode(
                None,
                args=[
                    name("head"),
                    ExprNodes.StarredUnpackingNode(
                        None, target=name("middle")),
                    name("tail"),
                ],
                mult_factor=None,
            ),
            starred_sequence,
        )
        starred_writer._close_remaining_owned_handles()
        starred_writer.assert_function_exit()
        starred_output = "\n".join(starred_writer.lines)
        self.assertIn("HPyListBuilder_New(ctx,", starred_output)
        self.assertIn("__pyx_hpy_unpack_rest_index_", starred_output)
        self.assertIn("__pyx_hpy_unpack_len_", starred_output)

        invalid_shapes = (
            (
                SimpleNamespace(pos=None),
                "requires a list or tuple target",
            ),
            (
                ExprNodes.TupleNode(
                    None, args=[], mult_factor=object()),
                "multiplied sequence unpacking targets",
            ),
            (
                ExprNodes.TupleNode(
                    None,
                    args=[
                        ExprNodes.StarredUnpackingNode(
                            None, target=name("first")),
                        ExprNodes.StarredUnpackingNode(
                            None, target=name("second")),
                    ],
                    mult_factor=None,
                ),
                "multiple starred unpack targets",
            ),
        )
        for target, message in invalid_shapes:
            with self.subTest(message=message):
                writer = UniversalHPyFunctionWriter(runtime_api)
                sequence_cname = writer.allocate_owned_handle(
                    "HPy_Dup(ctx, ctx->h_None)")
                with self.assertRaisesRegex(CompileError, message):
                    writer._unpack_owned_sequence_into(target, sequence_cname)
                writer.close_owned_handle(sequence_cname)
                writer.assert_function_exit()

    def test_for_from_loop_covers_offset_step_and_else_generation(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        writer = UniversalHPyFunctionWriter(runtime_api)
        target_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        writer._local_values["index"] = target_cname
        writer.generate_for_from_loop(
            ExprNodes.IntNode(None, value="0"),
            "<",
            "<=",
            ExprNodes.IntNode(None, value="8"),
            ExprNodes.IntNode(None, value="2"),
            "index",
            [_EmitLineStatement("body_marker();")],
            [_EmitLineStatement("else_marker();")],
        )
        writer.close_owned_handle(target_cname, null_safe=True)
        writer.assert_function_exit()
        output = "\n".join(writer.lines)
        self.assertIn("(__pyx_hpy_ssize_bound_0+1)", output)
        self.assertIn("+=__pyx_hpy_ssize_bound_", output)
        self.assertIn("body_marker();", output)
        self.assertIn("else_marker();", output)

    def test_owned_assignment_rejects_extension_fields_and_unknown_targets(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        entry = SimpleNamespace(name="field")
        writer = UniversalHPyFunctionWriter(
            runtime_api,
            extension_field_layout={
                id(entry): ("ExampleObject", "field", "object"),
            },
        )
        target = ExprNodes.AttributeNode(
            None, obj=_OwnedNoneExpression(), attribute="field")
        target.entry = entry
        value_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        with self.assertRaisesRegex(
            CompileError, "extension-field unpack targets"
        ):
            writer.assign_target_from_owned_cname(target, value_cname)
        writer.close_owned_handle(value_cname)

        value_cname = writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        with self.assertRaisesRegex(
            CompileError, "assignment target SimpleNamespace"
        ):
            writer.assign_target_from_owned_cname(
                SimpleNamespace(pos=None), value_cname)
        writer.close_owned_handle(value_cname)
        writer.assert_function_exit()

        slice_writer = UniversalHPyFunctionWriter(runtime_api)
        slice_target = ExprNodes.SliceIndexNode(
            None,
            base=_OwnedNoneExpression(),
            start=None,
            stop=None,
            slice=_OwnedNoneExpression(),
        )
        value_cname = slice_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        slice_writer.assign_target_from_owned_cname(slice_target, value_cname)
        slice_writer.assert_function_exit()
        self.assertIn("HPy_SetItem(ctx,", "\n".join(slice_writer.lines))

    def test_method_call_keyword_contract_covers_guards_and_array_path(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        def receiver(writer):
            return writer.allocate_owned_handle(
                "HPy_Dup(ctx, ctx->h_None)")

        keyword_names = _OwnedKeywordNames([_OwnedNoneExpression()])
        guard_cases = (
            (
                dict(keyword_names=keyword_names, keyword_values=None),
                AssertionError,
                "keyword names require keyword values",
            ),
            (
                dict(keyword_names=None, keyword_values=[_OwnedNoneExpression()]),
                AssertionError,
                "keyword values require keyword names",
            ),
            (
                dict(
                    keyword_names=_OwnedKeywordNames(
                        [_OwnedNoneExpression()], mult_factor=object()),
                    keyword_values=[_OwnedNoneExpression()],
                ),
                CompileError,
                "expanded keyword names",
            ),
            (
                dict(
                    keyword_names=keyword_names,
                    keyword_values=[],
                ),
                AssertionError,
                "keyword name/value count mismatch",
            ),
        )
        for kwargs, error_type, message in guard_cases:
            with self.subTest(message=message):
                writer = UniversalHPyFunctionWriter(runtime_api)
                receiver_cname = receiver(writer)
                with self.assertRaisesRegex(error_type, message):
                    writer.generate_method_call_on_cname(
                        receiver_cname, "method", (), **kwargs)
                writer._close_remaining_owned_handles()
                writer.assert_function_exit()

        writer = UniversalHPyFunctionWriter(runtime_api)
        result_cname = writer.generate_method_call_on_cname(
            receiver(writer),
            "method",
            (_OwnedNoneExpression(),),
            keyword_names=keyword_names,
            keyword_values=[_OwnedNoneExpression()],
        )
        writer.close_owned_handle(result_cname)
        writer.assert_function_exit()
        output = "\n".join(writer.lines)
        self.assertIn("HPy_CallMethod(ctx,", output)
        self.assertIn("__pyx_hpy_call_args_", output)
        self.assertIn("HPyDict_New(ctx)", output)

    def test_keyword_call_attribute_fast_path_and_guards_are_exercised(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        keyword_names = _OwnedKeywordNames([_OwnedNoneExpression()])

        writer = UniversalHPyFunctionWriter(runtime_api)
        function = ExprNodes.AttributeNode(
            None, obj=_OwnedNoneExpression(), attribute="method")
        function.entry = None
        result_cname = writer.generate_keyword_call(
            function,
            (),
            keyword_names,
            [_OwnedNoneExpression()],
        )
        writer.close_owned_handle(result_cname)
        writer.assert_function_exit()
        self.assertIn("HPy_CallMethod(ctx,", "\n".join(writer.lines))

        expanded_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(CompileError, "expanded keyword names"):
            expanded_writer.generate_keyword_call(
                _OwnedNoneExpression(),
                (),
                _OwnedKeywordNames([], mult_factor=object()),
                [],
            )
        expanded_writer.assert_function_exit()

        mismatch_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            AssertionError, "keyword name/value count mismatch"
        ):
            mismatch_writer.generate_keyword_call(
                _OwnedNoneExpression(),
                (),
                keyword_names,
                [],
            )
        mismatch_writer.assert_function_exit()

    def test_comprehension_contract_covers_rejections_and_nested_restoration(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        list_type = SimpleNamespace(
            is_pyset_type=False,
            is_pydict_type=False,
            is_pylist_type=True,
        )
        set_type = SimpleNamespace(
            is_pyset_type=True,
            is_pydict_type=False,
            is_pylist_type=False,
        )
        unknown_type = SimpleNamespace(
            is_pyset_type=False,
            is_pydict_type=False,
            is_pylist_type=False,
        )

        loop = Nodes.ForInStatNode(None)
        loop.generate_hpy_bootstrap_execution_code = (
            lambda writer: writer.putln("comprehension_loop();"))

        invalid_nodes = (
            (
                SimpleNamespace(
                    is_async=True,
                    loop=loop,
                    type=list_type,
                    pos=None,
                ),
                "async comprehensions",
            ),
            (
                SimpleNamespace(
                    is_async=False,
                    loop=SimpleNamespace(),
                    type=list_type,
                    pos=None,
                ),
                "only for-in/for-from",
            ),
            (
                SimpleNamespace(
                    is_async=False,
                    loop=loop,
                    type=set_type,
                    pos=None,
                ),
                "set comprehensions remain blocked",
            ),
            (
                SimpleNamespace(
                    is_async=False,
                    loop=loop,
                    type=unknown_type,
                    pos=None,
                ),
                "comprehension type",
            ),
        )
        for node, message in invalid_nodes:
            with self.subTest(message=message):
                writer = UniversalHPyFunctionWriter(runtime_api)
                with self.assertRaisesRegex(CompileError, message):
                    writer.generate_comprehension(node)
                writer.assert_function_exit()

        nested_node = SimpleNamespace(
            is_async=False,
            loop=loop,
            type=SimpleNamespace(
                is_pyset_type=False,
                is_pydict_type=True,
                is_pylist_type=False,
            ),
            pos=None,
        )
        writer = UniversalHPyFunctionWriter(runtime_api)
        writer._comprehension_targets[id(nested_node)] = "outer_container"
        result_cname = writer.generate_comprehension(nested_node)
        self.assertEqual(
            writer._comprehension_targets[id(nested_node)],
            "outer_container",
        )
        writer.close_owned_handle(result_cname)
        writer.assert_function_exit()
        self.assertIn("comprehension_loop();", "\n".join(writer.lines))

        with self.assertRaisesRegex(
            CompileError, "comprehension target container is not bound"
        ):
            UniversalHPyFunctionWriter(
                runtime_api).comprehension_target_cname(
                    SimpleNamespace(pos=None))

    def test_walrus_assignment_covers_global_stable_and_replacement_paths(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        invalid_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            CompileError, "walrus targets must be simple names"
        ):
            invalid_writer.generate_walrus(SimpleNamespace(
                lhs=SimpleNamespace(),
                rhs=_OwnedNoneExpression(),
                pos=None,
            ))
        invalid_writer.assert_function_exit()

        global_writer = UniversalHPyFunctionWriter(
            runtime_api,
            name_registry=_HPyNameRegistry(),
            module_cname="m",
            rollback_module_publications=True,
        )
        global_lhs = ExprNodes.NameNode(None, name="published")
        global_lhs.entry = SimpleNamespace(is_pyglobal=True)
        result_cname = global_writer.generate_walrus(SimpleNamespace(
            lhs=global_lhs,
            rhs=_OwnedNoneExpression(),
            pos=None,
        ))
        global_writer.close_owned_handle(result_cname)
        global_writer.assert_function_exit()
        self.assertIn(
            'HPy_SetAttr_s(ctx, m, "published"',
            "\n".join(global_writer.lines),
        )

        stable_writer = UniversalHPyFunctionWriter(runtime_api)
        stable_lhs = ExprNodes.NameNode(None, name="stable")
        stable_lhs.entry = None
        slot_cname = stable_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        stable_writer._local_values["stable"] = slot_cname
        stable_writer._stable_local_slots.add("stable")
        result_cname = stable_writer.generate_walrus(SimpleNamespace(
            lhs=stable_lhs,
            rhs=_OwnedNoneExpression(),
            pos=None,
        ))
        stable_writer.close_owned_handle(result_cname)
        stable_writer.close_owned_handle(slot_cname, null_safe=True)
        stable_writer.assert_function_exit()

        replacement_writer = UniversalHPyFunctionWriter(runtime_api)
        replacement_lhs = ExprNodes.NameNode(None, name="value")
        replacement_lhs.entry = None
        previous_cname = replacement_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        replacement_writer._local_values["value"] = previous_cname
        result_cname = replacement_writer.generate_walrus(SimpleNamespace(
            lhs=replacement_lhs,
            rhs=_OwnedNoneExpression(),
            pos=None,
        ))
        replacement_writer.close_owned_handle(result_cname)
        replacement_writer._close_remaining_owned_handles()
        replacement_writer.assert_function_exit()

    def test_joined_string_empty_and_none_check_formatting_paths(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        empty_writer = UniversalHPyFunctionWriter(runtime_api)
        empty_cname = empty_writer.generate_joined_string(())
        empty_writer.close_owned_handle(empty_cname)
        empty_writer.assert_function_exit()
        self.assertIn(
            'HPyUnicode_FromString(ctx, "")',
            "\n".join(empty_writer.lines),
        )

        joined_writer = UniversalHPyFunctionWriter(runtime_api)
        clone = ExprNodes.CloneNode(_OwnedNoneExpression())
        joined_cname = joined_writer.generate_joined_string(
            (clone, _OwnedNoneExpression()))
        joined_writer.close_owned_handle(joined_cname)
        joined_writer.assert_function_exit()
        self.assertIn("HPy_Add(ctx,", "\n".join(joined_writer.lines))

        formatted_writer = UniversalHPyFunctionWriter(runtime_api)
        value_cname = formatted_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        formatted_writer.generate_none_check(
            value_cname,
            "PyExc_TypeError",
            "argument %s may not be None",
            ("value",),
        )
        formatted_writer.close_owned_handle(value_cname)
        formatted_writer.assert_function_exit()
        self.assertIn(
            "argument value may not be None",
            "\n".join(formatted_writer.lines),
        )

        invalid_writer = UniversalHPyFunctionWriter(runtime_api)
        value_cname = invalid_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        with self.assertRaisesRegex(
            CompileError, "formatted None-check diagnostics"
        ):
            invalid_writer.generate_none_check(
                value_cname,
                "PyExc_TypeError",
                "argument %d may not be None",
                ("not-an-integer",),
            )
        invalid_writer.close_owned_handle(value_cname)
        invalid_writer.assert_function_exit()

    def test_module_render_preflight_guards_are_source_position_safe(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        with self.assertRaisesRegex(CompileError, "positionless"):
            UniversalHPyModuleWriter.unsupported(
                None, "positionless rejection")

        def module(contents, name="module"):
            node = SimpleNamespace(full_module_name=name, pos=None)
            node.hpy_bootstrap_contents = lambda writer: contents
            return node

        safe_method = SimpleNamespace(name="function", args=[], pos=None)
        reserved_method = SimpleNamespace(
            name="__pyx_hpy_const_reserved",
            args=[],
            pos=None,
        )
        empty_body = Nodes.StatListNode(None, stats=[])
        duplicate_class = SimpleNamespace(
            class_name="function",
            body=empty_body,
            pos=None,
        )
        reserved_class = SimpleNamespace(
            class_name="ReservedClass",
            body=empty_body,
            entry=SimpleNamespace(type=SimpleNamespace(scope=SimpleNamespace(
                var_entries=[
                    SimpleNamespace(name="__pyx_hpy_slot_owner_reserved"),
                ],
            ))),
            pos=None,
        )
        source = SimpleNamespace()
        reserved_type_method = Nodes.DefNode(
            (source, 1, 0),
            name="__pyx_hpy_slot_owner_reserved",
            args=[SimpleNamespace(
                default=None,
                pos_only=False,
                kw_only=False,
            )],
            body=Nodes.StatListNode(None, stats=[]),
        )
        reserved_type_method.hpy_bootstrap_signature = (
            lambda writer, receiver_argument=None:
                RuntimeMethodSignature.NOARGS)
        reserved_method_class = SimpleNamespace(
            class_name="ReservedMethods",
            body=Nodes.StatListNode(None, stats=[reserved_type_method]),
            entry=SimpleNamespace(type=SimpleNamespace(scope=SimpleNamespace(
                var_entries=[],
            ))),
            pos=None,
        )
        reserved_assignment = Nodes.SingleAssignmentNode(
            None,
            lhs=SimpleNamespace(name="__pyx_hpy_default_reserved"),
            rhs=_OwnedNoneExpression(),
        )
        star_import = SimpleNamespace(
            items=[("*", SimpleNamespace(name="ignored"))],
            pos=None,
        )
        reserved_import = SimpleNamespace(
            items=[
                (
                    "value",
                    SimpleNamespace(name="__pyx_hpy_slot_owner_reserved"),
                ),
            ],
            pos=None,
        )
        cases = (
            (
                module(([], [], [], []), name="invalid-module"),
                "module-name components must be C identifiers",
            ),
            (
                module(([safe_method], [], [duplicate_class], [])),
                "function/type names collide",
            ),
            (
                module(([], [], [reserved_class], [])),
                "type members use reserved runtime cache names",
            ),
            (
                module(([], [], [reserved_method_class], [])),
                "type members use reserved runtime cache names",
            ),
            (
                module(([reserved_method], [], [], [])),
                "function name uses a reserved",
            ),
            (
                module(([safe_method], [reserved_assignment], [], [])),
                "module name uses a reserved",
            ),
            (
                module(([safe_method], [star_import], [], [])),
                "star imports are not implemented",
            ),
            (
                module(([safe_method], [reserved_import], [], [])),
                "import target uses a reserved",
            ),
        )
        for module_node, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(CompileError, message):
                    UniversalHPyModuleWriter(
                        module_node, runtime_api).render()

    def test_native_field_assignment_guards_reject_unsafe_inplace_forms(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        def wrapped_inplace(operator):
            inplace = SimpleNamespace(
                inplace=True,
                operator=operator,
                operand2=_OwnedNoneExpression(),
                pos=None,
            )
            wrapper = ExprNodes.CoerceFromPyTypeNode.__new__(
                ExprNodes.CoerceFromPyTypeNode)
            wrapper.arg = inplace
            return wrapper

        cases = (
            ("bint", "+", "bint extension-field"),
            ("signed-int", "/", "native C extension fields currently support"),
        )
        for storage_kind, operator, message in cases:
            with self.subTest(message=message):
                writer = UniversalHPyFunctionWriter(runtime_api)
                owner_cname = writer.allocate_owned_handle(
                    "HPy_Dup(ctx, ctx->h_None)")
                with self.assertRaisesRegex(CompileError, message):
                    writer._assign_native_extension_field(
                        owner_cname,
                        "owner->field",
                        storage_kind,
                        wrapped_inplace(operator),
                    )
                writer.close_owned_handle(owner_cname)
                writer.assert_function_exit()

    def test_integer_temporary_comparison_and_global_inplace_edges(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        temporary_writer = UniversalHPyFunctionWriter(runtime_api)
        node = SimpleNamespace()
        temporary_writer._c_temporary_values[id(node)] = "bound_integer"
        self.assertEqual(
            temporary_writer.unbind_integer_temporary(node),
            "bound_integer",
        )
        with self.assertRaisesRegex(
            AssertionError, "C temporary is not bound"
        ):
            temporary_writer.unbind_integer_temporary(node)
        temporary_writer.assert_function_exit()

        comparison_writer = UniversalHPyFunctionWriter(runtime_api)
        for operator in ("is_not", "not_in"):
            with self.subTest(operator=operator):
                result_cname = comparison_writer.allocate_owned_handle(
                    "HPy_NULL")
                left_cname = comparison_writer.allocate_owned_handle(
                    "HPy_Dup(ctx, ctx->h_None)")
                right_cname = comparison_writer.allocate_owned_handle(
                    "HPy_Dup(ctx, ctx->h_None)")
                comparison_writer._assign_comparison_result(
                    SimpleNamespace(pos=None),
                    result_cname,
                    operator,
                    left_cname,
                    right_cname,
                )
                comparison_writer.close_owned_handle(right_cname)
                comparison_writer.close_owned_handle(left_cname)
                comparison_writer.close_owned_handle(result_cname)

        result_cname = comparison_writer.allocate_owned_handle("HPy_NULL")
        left_cname = comparison_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        right_cname = comparison_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        with self.assertRaisesRegex(
            CompileError, "comparison operator unsupported"
        ):
            comparison_writer._assign_comparison_result(
                SimpleNamespace(pos=None),
                result_cname,
                "unsupported",
                left_cname,
                right_cname,
            )
        comparison_writer.close_owned_handle(right_cname)
        comparison_writer.close_owned_handle(left_cname)
        comparison_writer.close_owned_handle(result_cname)
        comparison_writer.assert_function_exit()
        output = "\n".join(comparison_writer.lines)
        self.assertIn("!(HPy_Is(ctx,", output)
        self.assertIn("!__pyx_hpy_contains_", output)

        names = _HPyNameRegistry()
        names.require_module_global("value")
        global_writer = UniversalHPyFunctionWriter(
            runtime_api,
            name_registry=names,
            module_cname="m",
            rollback_module_publications=True,
        )
        global_writer.inplace_function_global(
            SimpleNamespace(pos=None),
            "value",
            RuntimeInPlaceOperation.ADD,
            _OwnedNoneExpression(),
        )
        global_writer.assert_function_exit()
        global_output = "\n".join(global_writer.lines)
        self.assertIn("HPy_InPlaceAdd(ctx,", global_output)
        self.assertIn('HPy_SetAttr_s(ctx, m, "value"', global_output)

    def test_module_publication_failure_guards_reject_invalid_contexts(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        disabled_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            AssertionError, "publication rollback is not enabled"
        ):
            disabled_writer._emit_module_failure_exit_preserving_memory()
        with self.assertRaisesRegex(
            AssertionError, "publication rollback is not enabled"
        ):
            disabled_writer.put_module_publication_error_if_negative("status")
        disabled_writer.assert_function_exit()

        scoped_writer = UniversalHPyFunctionWriter(
            runtime_api, rollback_module_publications=True)
        scoped_writer._failure_scopes.append({"label": "scope"})
        with self.assertRaisesRegex(
            AssertionError, "cannot occur inside failure scopes"
        ):
            scoped_writer._emit_module_failure_exit_preserving_memory()
        with self.assertRaisesRegex(
            AssertionError, "cannot occur inside failure scopes"
        ):
            scoped_writer.put_module_publication_error_if_negative("status")
        scoped_writer._failure_scopes.clear()
        scoped_writer.assert_function_exit()

    def test_nested_definition_discovery_and_validation_guards_are_complete(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)

        plain_outer = SimpleNamespace(
            body=Nodes.StatListNode(
                None, stats=[SimpleNamespace(pos=None)]))
        self.assertEqual(list(module_writer._iter_nested_defs(plain_outer)), [])

        missing_function = Nodes.DefNode(
            None,
            name="inner",
            args=[],
            body=Nodes.StatListNode(None, stats=[]),
        )
        missing_function.py_cfunc_node = None
        with self.assertRaisesRegex(
            CompileError, "requires InnerFunction closure synthesis"
        ):
            list(module_writer._iter_nested_defs(SimpleNamespace(
                body=Nodes.StatListNode(None, stats=[missing_function]))))

        missing_def_node = ExprNodes.InnerFunctionNode(None)
        missing_def_node.def_node = None
        assignment = Nodes.SingleAssignmentNode(
            None,
            lhs=SimpleNamespace(name="inner"),
            rhs=missing_def_node,
        )
        with self.assertRaisesRegex(
            CompileError, "requires InnerFunction closure synthesis"
        ):
            list(module_writer._iter_nested_defs(SimpleNamespace(
                body=Nodes.StatListNode(None, stats=[assignment]))))

        inner_node = ExprNodes.InnerFunctionNode(None)
        wrapped = ExprNodes.SimpleCallNode(
            None,
            function=SimpleNamespace(),
            args=[inner_node],
        )
        self.assertIs(module_writer._inner_function_from_expr(wrapped), inner_node)
        self.assertIsNone(module_writer._inner_function_from_expr(
            ExprNodes.SimpleCallNode(
                None, function=SimpleNamespace(), args=[])))

        self.assertFalse(module_writer._nested_def_contains_yield(
            SimpleNamespace(body=None)))
        self.assertTrue(module_writer._nested_def_contains_yield(
            SimpleNamespace(body=ExprNodes.YieldExprNode(None))))
        self.assertTrue(module_writer._nested_def_contains_yield(
            SimpleNamespace(body=Nodes.GeneratorDefNode(
                None,
                args=[],
                body=Nodes.StatListNode(None, stats=[]),
            ))))

        with self.assertRaisesRegex(
            CompileError, "requires InnerFunction closure synthesis"
        ):
            module_writer._validate_nested_closure(
                plain_outer,
                SimpleNamespace(pos=None),
                SimpleNamespace(),
            )

        def inner_definition(needs_closure):
            return SimpleNamespace(
                decorators=[],
                is_staticmethod=False,
                is_classmethod=False,
                is_generator=False,
                body=Nodes.StatListNode(None, stats=[]),
                needs_closure=needs_closure,
                star_arg=None,
                starstar_arg=None,
                args=[],
                pos=None,
            )

        decorated_def = inner_definition(
            Nodes.FuncDefNode.NeedsClosure.NO_CLOSURE)
        decorated_node = ExprNodes.InnerFunctionNode(None)
        decorated_node.def_node = decorated_def
        decorated_call = ExprNodes.SimpleCallNode(
            None,
            function=SimpleNamespace(),
            args=[decorated_node],
        )
        decorated_outer = SimpleNamespace(body=Nodes.StatListNode(
            None,
            stats=[Nodes.SingleAssignmentNode(
                None,
                lhs=SimpleNamespace(name="inner"),
                rhs=decorated_call,
            )],
        ))
        with self.assertRaisesRegex(
            CompileError, "decorated nested def functions"
        ):
            module_writer._validate_nested_closure(
                decorated_outer, decorated_def, decorated_node)

        full_def = inner_definition(
            Nodes.FuncDefNode.NeedsClosure.FULL_CLOSURE)
        full_node = ExprNodes.InnerFunctionNode(None)
        full_node.def_node = full_def
        with self.assertRaisesRegex(
            CompileError, "nested nested def closures"
        ):
            module_writer._validate_nested_closure(
                plain_outer, full_def, full_node)

    def test_extension_slot_preflight_guards_cover_all_slot_families(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)
        renderers = (
            module_writer._render_extension_call_slot,
            module_writer._render_extension_value_slot,
            module_writer._render_extension_length_slot,
            module_writer._render_extension_binary_value_slot,
            module_writer._render_extension_ternary_value_slot,
            module_writer._render_extension_hash_slot,
            module_writer._render_extension_bool_slot,
            module_writer._render_extension_contains_slot,
        )

        for renderer in renderers:
            with self.subTest(renderer=renderer.__name__, guard="annotation"):
                annotated = SimpleNamespace(
                    return_type_annotation=object(),
                    body=Nodes.StatListNode(None, stats=[]),
                    name="__slot__",
                    pos=None,
                )
                with self.assertRaisesRegex(
                    CompileError, "return annotations"
                ):
                    renderer(annotated, "slot_definition", {})

            with self.subTest(renderer=renderer.__name__, guard="termination"):
                unterminated = SimpleNamespace(
                    return_type_annotation=None,
                    body=Nodes.StatListNode(None, stats=[]),
                    name="__slot__",
                    pos=None,
                )
                with self.assertRaisesRegex(
                    CompileError, "body must end with"
                ):
                    renderer(unterminated, "slot_definition", {})

    def test_extension_property_and_status_special_cases_are_emitted(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)

        getter = SimpleNamespace(
            body=Nodes.StatListNode(None, stats=[]),
            pos=None,
        )
        with self.assertRaisesRegex(
            CompileError, "property getter body must end with"
        ):
            module_writer._render_extension_property(
                SimpleNamespace(pos=None),
                {"__get__": getter},
                "property_definition",
                {},
            )

        module_writer._render_extension_status_helper = (
            lambda *args, **kwargs: [])
        deleter_only = module_writer._render_extension_property(
            SimpleNamespace(pos=None),
            {"__del__": object()},
            "property_definition",
            {},
        )
        self.assertIn(
            "__set__",
            "\n".join(deleter_only),
        )

        annotated = SimpleNamespace(
            return_type_annotation=object(),
            body=Nodes.StatListNode(None, stats=[]),
            name="__set__",
            pos=None,
        )
        with self.assertRaisesRegex(CompileError, "return annotations"):
            UniversalHPyModuleWriter(
                SimpleNamespace(pos=None),
                runtime_api,
            )._render_extension_status_helper(
                annotated, "status_helper", ("self",), {})

        bad_return = Nodes.ReturnStatNode(
            None, value=ExprNodes.IntNode(None, value="1"))
        invalid_method = SimpleNamespace(
            return_type_annotation=None,
            body=Nodes.StatListNode(None, stats=[bad_return]),
            name="__set__",
            pos=None,
        )
        fresh_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)
        with self.assertRaisesRegex(CompileError, "may only return None"):
            fresh_writer._render_extension_status_helper(
                invalid_method, "status_helper", ("self",), {})
        with self.assertRaisesRegex(CompileError, "may only return None"):
            fresh_writer._render_extension_finalize_slot(
                invalid_method, "finalize_slot", {})
        with self.assertRaisesRegex(CompileError, "may only return None"):
            fresh_writer._render_extension_initializer(
                invalid_method, "initializer_slot", {})

    def test_reflected_only_numeric_slot_emits_right_precedence_branch(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)
        module_writer._render_extension_binary_value_slot = (
            lambda *args, **kwargs: [])
        output = module_writer._render_extension_numeric_binary_slot(
            {"__radd__": object()},
            "numeric_add",
            "__pyx_hpy_slot_owner_add",
            "__add__",
            "__radd__",
            {},
        )
        rendered = "\n".join(output)
        self.assertIn("if (left_matches && right_matches)", rendered)
        self.assertIn("right_matches = 0;", rendered)

    def test_inlined_generator_contract_covers_guards_containers_and_defaults(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        list_type = SimpleNamespace(
            is_pyset_type=False,
            is_pydict_type=False,
            is_pylist_type=True,
        )
        set_type = SimpleNamespace(
            is_pyset_type=True,
            is_pydict_type=False,
            is_pylist_type=False,
        )
        loop = Nodes.ForInStatNode(None)
        loop.generate_hpy_bootstrap_execution_code = (
            lambda writer: writer.putln("inlined_loop();"))

        def node(orig, *, selected_loop=loop, result_type=None, target=None):
            return SimpleNamespace(
                orig_func=orig,
                type=result_type,
                gen=SimpleNamespace(
                    loop=selected_loop,
                    def_node=None,
                    call_parameters=(),
                ),
                target=target,
                pos=None,
            )

        invalid_nodes = (
            (
                node("set", result_type=set_type),
                "set inlined generators remain blocked",
            ),
            (
                node("list", selected_loop=None, result_type=list_type),
                "has no loop body",
            ),
            (
                node(
                    "list",
                    selected_loop=SimpleNamespace(),
                    result_type=list_type,
                ),
                "only sequence-index/range",
            ),
            (
                node("unknown", result_type=None),
                "inlined generator expression 'unknown'",
            ),
        )
        for invalid, message in invalid_nodes:
            with self.subTest(message=message):
                writer = UniversalHPyFunctionWriter(runtime_api)
                with self.assertRaisesRegex(CompileError, message):
                    writer.generate_inlined_generator_expression(invalid)
                writer.assert_function_exit()

        arity_node = node("list", result_type=list_type)
        arity_node.gen.def_node = SimpleNamespace(args=[
            SimpleNamespace(entry=SimpleNamespace(name="iterator")),
        ])
        arity_node.gen.call_parameters = (
            _OwnedNoneExpression(),
            _OwnedNoneExpression(),
        )
        arity_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(CompileError, "parameter arity mismatch"):
            arity_writer.generate_inlined_generator_expression(arity_node)
        arity_writer.assert_function_exit()

        for orig in ("any", "all", "dict", "list", "sorted"):
            with self.subTest(orig=orig):
                target = object()
                generated_node = node(
                    orig,
                    result_type=list_type if orig in ("list", "sorted") else None,
                    target=target,
                )
                writer = UniversalHPyFunctionWriter(runtime_api)
                if orig == "sorted":
                    writer._comprehension_targets[id(target)] = "outer"
                result_cname = writer.generate_inlined_generator_expression(
                    generated_node)
                if orig == "sorted":
                    self.assertEqual(
                        writer._comprehension_targets[id(target)], "outer")
                writer.close_owned_handle(result_cname)
                writer.assert_function_exit()
                output = "\n".join(writer.lines)
                self.assertIn("inlined_loop();", output)
                if orig == "dict":
                    self.assertIn("HPyDict_New(ctx)", output)
                elif orig == "sorted":
                    self.assertIn("HPy_CallMethod(ctx,", output)

    def test_terminal_try_except_guards_cover_every_invalid_shape(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        return_statement = Nodes.ReturnStatNode(
            None, value=_OwnedNoneExpression())
        terminating_body = Nodes.StatListNode(
            None, stats=[return_statement])

        def clause(*, pattern=None, body=None, target=None, excinfo_target=None):
            return SimpleNamespace(
                pattern=pattern,
                body=terminating_body if body is None else body,
                target=target,
                excinfo_target=excinfo_target,
                pos=None,
            )

        def try_node(*, body=terminating_body, clauses=(), else_clause=None):
            return SimpleNamespace(
                body=body,
                except_clauses=list(clauses),
                else_clause=else_clause,
                pos=None,
            )

        scoped_writer = UniversalHPyFunctionWriter(runtime_api)
        scoped_writer._failure_scopes.append({"label": "outer"})
        with self.assertRaisesRegex(CompileError, "nested try/except"):
            scoped_writer.generate_terminal_try_except(
                try_node(clauses=[clause()]))
        scoped_writer._failure_scopes.clear()
        scoped_writer.assert_function_exit()

        invalid_cases = (
            (
                try_node(
                    clauses=[clause()],
                    else_clause=SimpleNamespace(pos=None),
                ),
                CompileError,
                "else clauses",
            ),
            (
                try_node(
                    body=Nodes.StatListNode(
                        None, stats=[Nodes.TryExceptStatNode(None)]),
                    clauses=[clause()],
                ),
                CompileError,
                "nested try/except",
            ),
            (
                try_node(
                    body=Nodes.StatListNode(
                        None, stats=[Nodes.PassStatNode(None)]),
                    clauses=[clause()],
                ),
                CompileError,
                "requires a terminating return or raise",
            ),
            (
                try_node(
                    body=Nodes.StatListNode(
                        None,
                        stats=[
                            SimpleNamespace(pos=None),
                            return_statement,
                        ],
                    ),
                    clauses=[clause()],
                ),
                CompileError,
                "try-body statements before",
            ),
            (
                try_node(clauses=[clause(target=SimpleNamespace())]),
                CompileError,
                "except targets require",
            ),
            (
                try_node(clauses=[clause(body=Nodes.StatListNode(
                    None, stats=[Nodes.PassStatNode(None)]))]),
                CompileError,
                "must end with a return or raise",
            ),
            (
                try_node(clauses=[clause(body=Nodes.StatListNode(
                    None,
                    stats=[
                        SimpleNamespace(pos=None),
                        return_statement,
                    ],
                ))]),
                CompileError,
                "handler statements before",
            ),
            (
                try_node(clauses=[clause(body=Nodes.StatListNode(
                    None,
                    stats=[
                        Nodes.TryExceptStatNode(None),
                        return_statement,
                    ],
                ))]),
                CompileError,
                "nested try/except",
            ),
            (
                try_node(clauses=[]),
                AssertionError,
                "has no clauses",
            ),
        )
        for invalid, error_type, message in invalid_cases:
            with self.subTest(message=message):
                writer = UniversalHPyFunctionWriter(runtime_api)
                with self.assertRaisesRegex(error_type, message):
                    writer.generate_terminal_try_except(invalid)
                writer.assert_function_exit()

        invalid_pattern = ExprNodes.NameNode(None, name="CustomError")
        invalid_pattern.entry = None
        writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            CompileError, "requires direct builtin exception names"
        ):
            writer.generate_terminal_try_except(try_node(
                clauses=[clause(pattern=[invalid_pattern])]))
        writer.assert_function_exit()

        unavailable_pattern = ExprNodes.NameNode(
            None, name="DefinitelyUnavailableError")
        unavailable_pattern.entry = SimpleNamespace(is_builtin=True)
        writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            CompileError, "is unavailable in HPy"
        ):
            writer.generate_terminal_try_except(try_node(
                clauses=[clause(pattern=[unavailable_pattern])]))
        writer.assert_function_exit()

        builtin_pattern = ExprNodes.NameNode(None, name="TypeError")
        builtin_pattern.entry = SimpleNamespace(is_builtin=True)
        writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            AssertionError, "default exception clause is not last"
        ):
            writer.generate_terminal_try_except(try_node(clauses=[
                clause(),
                clause(pattern=[builtin_pattern]),
            ]))
        writer.assert_function_exit()

    def test_inner_materialization_and_miscellaneous_writer_guards(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        inner_node = SimpleNamespace(pos=None)

        writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            CompileError, "without a closure registry"
        ):
            writer.materialize_inner_function(inner_node)
        writer.assert_function_exit()

        writer = UniversalHPyFunctionWriter(
            runtime_api, closure_registry=_ClosureRegistry((), ()))
        with self.assertRaisesRegex(
            CompileError, "not registered in the closure plan"
        ):
            writer.materialize_inner_function(inner_node)
        writer.assert_function_exit()

        env_spec = _ClosureEnvSpec(0, object(), ())
        fn_spec = _ClosureFnSpec(
            0, object(), inner_node, env_spec)
        writer = UniversalHPyFunctionWriter(
            runtime_api,
            closure_registry=_ClosureRegistry((env_spec,), (fn_spec,)),
        )
        with self.assertRaisesRegex(
            CompileError, "requires an active closure env"
        ):
            writer.materialize_inner_function(inner_node)
        writer.assert_function_exit()

        formatted_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            CompileError, "f-string conversion !x"
        ):
            formatted_writer.generate_formatted_value(
                _OwnedNoneExpression(), "x", None)
        formatted_writer._close_remaining_owned_handles()
        formatted_writer.assert_function_exit()

        rollback_writer = UniversalHPyFunctionWriter(
            runtime_api, rollback_module_publications=True)
        value_cname = rollback_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        rollback_writer.put_error_return_if_null_with_exception(value_cname)
        rollback_writer.close_owned_handle(value_cname)
        rollback_writer.assert_function_exit()
        self.assertIn(
            "HPyErr_ExceptionMatches(ctx, ctx->h_MemoryError)",
            "\n".join(rollback_writer.lines),
        )

        default_writer = UniversalHPyFunctionWriter(
            runtime_api, module_cname="m", default_registry=None)
        with self.assertRaisesRegex(
            AssertionError, "require interpreter-owned storage"
        ):
            default_writer._materialize_defaulted_arguments(
                "function", (), ())
        default_writer.assert_function_exit()

    def test_module_import_emitters_cover_relative_and_dotted_paths(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)

        def import_node(module_name, *, level=0, is_import_as_name=False):
            return ExprNodes.ImportNode(
                None,
                module_name=SimpleNamespace(value=module_name),
                level=level,
                is_import_as_name=is_import_as_name,
            )

        relative_writer = UniversalHPyFunctionWriter(
            runtime_api,
            name_registry=module_writer.name_registry,
            module_cname="m",
            rollback_module_publications=True,
        )
        with self.assertRaisesRegex(CompileError, "relative imports"):
            module_writer._emit_module_assignment(
                SimpleNamespace(
                    lhs=SimpleNamespace(name="pkg"),
                    rhs=import_node("pkg", level=1),
                    pos=None,
                ),
                relative_writer,
            )
        relative_writer.assert_function_exit()

        dotted_writer = UniversalHPyFunctionWriter(
            runtime_api,
            name_registry=module_writer.name_registry,
            module_cname="m",
            rollback_module_publications=True,
        )
        module_writer._emit_module_assignment(
            SimpleNamespace(
                lhs=SimpleNamespace(name="pkg"),
                rhs=import_node("pkg.submodule"),
                pos=None,
            ),
            dotted_writer,
        )
        dotted_writer.assert_function_exit()
        dotted_output = "\n".join(dotted_writer.lines)
        self.assertGreaterEqual(dotted_output.count(
            'HPyImport_ImportModule(ctx, "pkg'), 2)

        from_writer = UniversalHPyFunctionWriter(
            runtime_api,
            name_registry=module_writer.name_registry,
            module_cname="m",
            rollback_module_publications=True,
        )
        with self.assertRaisesRegex(CompileError, "relative imports"):
            module_writer._emit_from_import(
                SimpleNamespace(
                    module=import_node("pkg", level=1),
                    items=[],
                    pos=None,
                ),
                from_writer,
            )
        from_writer.assert_function_exit()

        statement = SimpleNamespace()
        self.assertEqual(
            UniversalHPyModuleWriter._stats(statement), [statement])
        stat_list = Nodes.StatListNode(None, stats=[statement])
        self.assertEqual(
            UniversalHPyModuleWriter._stats(stat_list), [statement])

    def test_remaining_function_writer_edge_contracts_are_fail_closed(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        owner_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            CompileError, "requires the current module/type owner"
        ):
            owner_writer.ensure_extension_runtime_owners(
                SimpleNamespace(pos=None))
        owner_writer.assert_function_exit()

        temporary_writer = UniversalHPyFunctionWriter(runtime_api)
        node = SimpleNamespace(pos=None)
        temporary_writer.bind_temporary_value(node, "borrowed")
        with self.assertRaisesRegex(
            AssertionError, "temporary is already bound"
        ):
            temporary_writer.bind_temporary_value(node, "other")
        self.assertEqual(
            temporary_writer.unbind_temporary_value(node), "borrowed")
        with self.assertRaisesRegex(
            AssertionError, "temporary is not bound"
        ):
            temporary_writer.unbind_temporary_value(node)
        with self.assertRaisesRegex(
            CompileError, "temporary HPy value is not bound"
        ):
            temporary_writer.duplicate_temporary_value(node)

        integer_node = SimpleNamespace(pos=None, result_code=None)
        temporary_writer._c_temporary_values[id(integer_node)] = "bound"
        with self.assertRaisesRegex(
            AssertionError, "C temporary is already bound"
        ):
            temporary_writer.bind_integer_temporary(
                integer_node, ExprNodes.IntNode(None, value="1"))
        temporary_writer.assert_function_exit()

        self.assertIsNone(
            temporary_writer._closure_capture_for_name("missing"))
        capture_entry = SimpleNamespace()
        capture = _ClosureCapture("captured", capture_entry, "field")
        env_spec = _ClosureEnvSpec(0, object(), (capture,))
        closure_writer = UniversalHPyFunctionWriter(
            runtime_api, closure_env_spec=env_spec)
        closure_node = SimpleNamespace(
            entry=SimpleNamespace(
                from_closure=True,
                in_closure=False,
                outer_entry=capture_entry,
            ),
            pos=None,
        )
        self.assertIsNone(
            closure_writer._duplicate_closure_capture(
                closure_node, "captured"))
        closure_writer._closure_env_owner_cname = "owner"
        unmatched_node = SimpleNamespace(
            entry=SimpleNamespace(
                from_closure=True,
                in_closure=False,
                outer_entry=SimpleNamespace(),
            ),
            pos=None,
        )
        self.assertIsNone(
            closure_writer._duplicate_closure_capture(
                unmatched_node, "missing"))
        value_cname = closure_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        with self.assertRaisesRegex(AssertionError, "unknown closure capture"):
            closure_writer._store_closure_capture("missing", value_cname)
        closure_writer.close_owned_handle(value_cname)
        closure_writer.assert_function_exit()

        local_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            CompileError, "has no initialized local HPy value"
        ):
            local_writer.inplace_local(
                SimpleNamespace(pos=None),
                "missing",
                RuntimeInPlaceOperation.ADD,
                _OwnedNoneExpression(),
            )
        owned_cname = local_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        local_writer._local_values["owned"] = owned_cname
        local_writer.inplace_local(
            SimpleNamespace(pos=None),
            "owned",
            RuntimeInPlaceOperation.ADD,
            _OwnedNoneExpression(),
        )
        local_writer._close_remaining_owned_handles()
        local_writer.delete_local(SimpleNamespace(pos=None), "missing")
        local_writer.assert_function_exit()

        registry_guard = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(
            AssertionError, "requires a name registry"
        ):
            registry_guard.store_module_global(
                SimpleNamespace(pos=None),
                "value",
                _OwnedNoneExpression(),
                "m",
            )
        registry_guard.assert_function_exit()

        raise_writer = UniversalHPyFunctionWriter(runtime_api)
        raise_writer.raise_builtin_object(
            "ValueError", _OwnedNoneExpression())
        raise_writer.assert_function_exit()

        sequence_writer = UniversalHPyFunctionWriter(runtime_api)
        starred_result = sequence_writer.generate_starred_sequence(
            RuntimeSequenceKind.TUPLE, (_OwnedNoneExpression(),))
        sequence_writer.close_owned_handle(starred_result)
        with self.assertRaisesRegex(
            AssertionError, "merged sequence generation requires arguments"
        ):
            sequence_writer.generate_merged_sequence(
                RuntimeSequenceKind.LIST, ())
        source_cname = sequence_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        normalized = sequence_writer.normalize_sequence_handle(
            RuntimeSequenceKind.TUPLE, source_cname)
        sequence_writer.close_owned_handle(normalized)
        sequence_writer._guard_keyword_name_duplicates(None)
        with self.assertRaisesRegex(
            AssertionError, "unexpected boolean operator"
        ):
            sequence_writer.generate_boolean_short_circuit(
                "xor", _OwnedNoneExpression(), _OwnedNoneExpression())
        sequence_writer.assert_function_exit()

        bytes_name = ExprNodes.BytesNode(
            None,
            value=SimpleNamespace(byteencode=lambda: b"name"),
        )
        self.assertEqual(
            UniversalHPyFunctionWriter._keyword_name_literal(bytes_name),
            b"name",
        )
        wrapped_name = ExprNodes.CoerceToTempNode.__new__(
            ExprNodes.CoerceToTempNode)
        wrapped_name.arg = ExprNodes.UnicodeNode(None, value="name")
        self.assertEqual(
            UniversalHPyFunctionWriter._keyword_name_literal(wrapped_name),
            "name",
        )

        loop_guard_writer = UniversalHPyFunctionWriter(runtime_api)
        with self.assertRaisesRegex(CompileError, "break statement"):
            loop_guard_writer.generate_loop_break(SimpleNamespace(pos=None))
        with self.assertRaisesRegex(CompileError, "continue statement"):
            loop_guard_writer.generate_loop_continue(SimpleNamespace(pos=None))
        loop_guard_writer.assert_function_exit()

        native_writer = UniversalHPyFunctionWriter(
            runtime_api, native_return_kind="unknown")
        native_cname = native_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        with self.assertRaisesRegex(
            AssertionError, "unknown native_return_kind"
        ):
            native_writer._return_native_from_owned_handle(native_cname)
        native_writer.close_owned_handle(native_cname)
        native_writer.assert_function_exit()

    def test_remaining_sequence_wrapper_and_loop_invariants_are_exercised(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        assignment_writer = UniversalHPyFunctionWriter(runtime_api)
        value_cname = assignment_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        assignment_writer.assign_target_from_owned_cname(
            ExprNodes.TupleNode(None, args=[], mult_factor=None),
            value_cname,
        )
        assignment_writer.assert_function_exit()

        wrapped = ExprNodes.CoerceToTempNode.__new__(
            ExprNodes.CoerceToTempNode)
        wrapped.arg = ExprNodes.IntNode(None, value="3")
        ssize_writer = UniversalHPyFunctionWriter(runtime_api)
        self.assertTrue(
            ssize_writer._materialize_ssize_expression(wrapped).startswith(
                "__pyx_hpy_ssize_bound_"))
        ssize_writer.assert_function_exit()

        sequence_writer = UniversalHPyFunctionWriter(runtime_api)
        for kind in (RuntimeSequenceKind.LIST, RuntimeSequenceKind.TUPLE):
            source_cname = sequence_writer.allocate_owned_handle(
                "HPy_Dup(ctx, ctx->h_None)")
            normalized = sequence_writer.normalize_sequence_handle(
                kind, source_cname)
            sequence_writer.close_owned_handle(normalized)
        sequence_writer.assert_function_exit()

        early_writer = UniversalHPyFunctionWriter(runtime_api)
        calls = []
        early_writer.generate_returning_if = (
            lambda clauses, else_body: calls.append((clauses, else_body)))
        condition = object()
        body = object()
        early_writer.generate_early_return_if(
            SimpleNamespace(), condition, body)
        self.assertEqual(calls, [(((condition, body),), None)])

        fallback_loop = Nodes.ForInStatNode(None)
        fallback_loop.generate_hpy_bootstrap_execution_code = (
            lambda writer: writer.putln("fallback_loop();"))
        fallback_node = SimpleNamespace(
            orig_func="list",
            type=SimpleNamespace(
                is_pyset_type=False,
                is_pydict_type=False,
                is_pylist_type=True,
            ),
            gen=SimpleNamespace(
                loop=None,
                def_node=SimpleNamespace(
                    args=[],
                    gbody=SimpleNamespace(body=fallback_loop),
                ),
                call_parameters=(),
            ),
            target=None,
            pos=None,
        )
        fallback_writer = UniversalHPyFunctionWriter(runtime_api)
        result_cname = fallback_writer.generate_inlined_generator_expression(
            fallback_node)
        fallback_writer.close_owned_handle(result_cname)
        fallback_writer.assert_function_exit()
        self.assertIn("fallback_loop();", "\n".join(fallback_writer.lines))

        wrapped_pattern = ExprNodes.CoerceToTempNode.__new__(
            ExprNodes.CoerceToTempNode)
        pattern = ExprNodes.NameNode(None, name="TypeError")
        wrapped_pattern.arg = pattern
        self.assertIs(
            UniversalHPyFunctionWriter._unwrap_exception_pattern(
                wrapped_pattern),
            pattern,
        )

        cleanup_writer = UniversalHPyFunctionWriter(runtime_api)
        builder = runtime_api.sequence_builder(RuntimeSequenceKind.TUPLE)
        cleanup_writer.allocate_sequence_builder(builder, 1)
        snapshot = cleanup_writer._snapshot_lifetime_state()
        cleanup_writer._loop_lifetime_stack.append(snapshot)
        cleanup_writer._emit_loop_body_cleanup()
        cleanup_writer._loop_lifetime_stack.pop()
        first_builder = cleanup_writer._builder_order[0]
        cleanup_writer._builder_temps.use(first_builder)
        cleanup_writer._builder_temps.cancel(first_builder)
        cleanup_writer._builder_temps.release(first_builder)
        cleanup_writer._builder_order.remove(first_builder)
        del cleanup_writer._builder_contracts[first_builder]
        snapshot = cleanup_writer._snapshot_lifetime_state()
        second_builder = cleanup_writer.allocate_sequence_builder(builder, 1)
        cleanup_writer._builder_temps.use(second_builder)
        cleanup_writer._builder_temps.cancel(second_builder)
        cleanup_writer._builder_temps.release(second_builder)
        cleanup_writer._loop_lifetime_stack.append(snapshot)
        cleanup_writer._emit_loop_body_cleanup()
        cleanup_writer._loop_lifetime_stack.pop()
        cleanup_writer.assert_function_exit()

        corrupt_cases = (
            "while",
            "sequence",
            "for-from",
        )
        for kind in corrupt_cases:
            with self.subTest(kind=kind):
                writer = UniversalHPyFunctionWriter(runtime_api)
                if kind == "while":
                    invoke = lambda: writer.generate_while_loop(
                        None, [_CorruptLoopStackStatement()], None)
                elif kind == "sequence":
                    slot_cname = writer.allocate_owned_handle(
                        "HPy_Dup(ctx, ctx->h_None)")
                    writer._local_values["item"] = slot_cname
                    invoke = lambda: writer.generate_sequence_for_loop(
                        _OwnedNoneExpression(),
                        "item",
                        [_CorruptLoopStackStatement()],
                        None,
                    )
                else:
                    slot_cname = writer.allocate_owned_handle(
                        "HPy_Dup(ctx, ctx->h_None)")
                    writer._local_values["item"] = slot_cname
                    invoke = lambda: writer.generate_for_from_loop(
                        ExprNodes.IntNode(None, value="0"),
                        "<=",
                        "<",
                        ExprNodes.IntNode(None, value="1"),
                        None,
                        "item",
                        [_CorruptLoopStackStatement()],
                        None,
                    )
                with self.assertRaisesRegex(
                    AssertionError, "loop stack changed"
                ):
                    invoke()

    def test_closure_and_extension_helper_edge_paths_are_rendered(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)

        inner_node = ExprNodes.InnerFunctionNode(None)
        inner_def = SimpleNamespace(
            body=Nodes.StatListNode(
                None, stats=[Nodes.ReturnStatNode(
                    None, value=_OwnedNoneExpression())]),
            name="inner",
            args=[],
            pos=None,
        )
        inner_def._hpy_bootstrap_statement_terminates = lambda stat: True
        env_spec = _ClosureEnvSpec(0, object(), ())
        fn_spec = _ClosureFnSpec(0, inner_def, inner_node, env_spec)
        registry = _ClosureRegistry((env_spec,), (fn_spec,))

        inner_def.hpy_bootstrap_signature = (
            lambda writer: RuntimeMethodSignature.VARARGS_KEYWORDS)
        call_lines = module_writer._render_closure_fn_call_impl(
            fn_spec, registry)
        self.assertIn(
            "static HPy __pyx_hpy_closure_fn_0_tp_call_impl",
            "\n".join(call_lines),
        )

        inner_def.hpy_bootstrap_signature = lambda writer: object()
        with self.assertRaisesRegex(
            CompileError, "unsupported nested def signature"
        ):
            module_writer._render_closure_fn_call_impl(fn_spec, registry)

        empty_def = SimpleNamespace(
            body=Nodes.StatListNode(None, stats=[]),
            name="empty",
            args=[],
            pos=None,
        )
        empty_def._hpy_bootstrap_statement_terminates = lambda stat: False
        empty_spec = _ClosureFnSpec(1, empty_def, inner_node, env_spec)
        with self.assertRaisesRegex(
            CompileError, "body must end with a return"
        ):
            module_writer._render_closure_fn_call_impl(empty_spec, registry)

        duplicate_env = _ClosureEnvSpec(0, object(), ())
        declaration_lines, _ = module_writer._render_closure_declarations(
            _ClosureRegistry((env_spec, duplicate_env), ()), "module")
        self.assertTrue(declaration_lines)

        capture_entry = SimpleNamespace(
            name="captured",
            cname="captured",
            type=SimpleNamespace(is_pyobject=True),
        )
        closure_entry_one = SimpleNamespace(
            from_closure=True, outer_entry=capture_entry)
        closure_entry_two = SimpleNamespace(
            from_closure=True, outer_entry=capture_entry)
        scope = SimpleNamespace(entries={
            "first": closure_entry_one,
            "second": closure_entry_two,
        })
        captures = module_writer._collect_captures(SimpleNamespace(
            local_scope=SimpleNamespace(
                iter_local_scopes=lambda: [scope]),
            pos=None,
        ))
        self.assertEqual(len(captures), 1)

        with self.assertRaisesRegex(
            AssertionError, "unknown custom extension field storage"
        ):
            module_writer._render_extension_custom_field_definition(
                "field_definition",
                "field",
                "Object",
                "field",
                "unsupported",
                False,
            )

        default_registry = _HPyDefaultRegistry()
        argument = SimpleNamespace(
            default=ExprNodes.IntNode(None, value="5"))
        attribute = default_registry.register_argument(argument)
        self.assertIs(
            list(default_registry.entries())[0][1],
            argument.default,
        )
        self.assertEqual(
            default_registry.attribute_for_argument(argument), attribute)

    def test_extension_helper_success_variants_and_property_shapes(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)

        argument = SimpleNamespace(entry=SimpleNamespace(name="self"))
        none_return = Nodes.ReturnStatNode(
            None, value=ExprNodes.NoneNode(None))
        method = SimpleNamespace(
            return_type_annotation=None,
            body=Nodes.StatListNode(None, stats=[none_return]),
            name="__del__",
            args=[argument],
            pos=None,
        )
        finalize = module_writer._render_extension_finalize_slot(
            method, "finalize_slot", {})
        self.assertIn("return;", "\n".join(finalize))

        annotated_finalize = SimpleNamespace(
            return_type_annotation=object(),
            body=Nodes.StatListNode(None, stats=[]),
            name="__del__",
            args=[argument],
            pos=None,
        )
        with self.assertRaisesRegex(CompileError, "return annotations"):
            module_writer._render_extension_finalize_slot(
                annotated_finalize, "finalize_slot", {})

        status_method = SimpleNamespace(
            return_type_annotation=None,
            body=Nodes.StatListNode(None, stats=[none_return]),
            name="__delete__",
            args=[argument],
            pos=None,
        )
        status = module_writer._render_extension_status_helper(
            status_method, "delete_helper", ("self",), {})
        self.assertIn("return 0;", "\n".join(status))

        init_method = SimpleNamespace(
            body=Nodes.StatListNode(None, stats=[none_return]),
            name="__cinit__",
            args=[argument],
            pos=None,
        )
        initializer = module_writer._render_extension_initializer(
            init_method, "initializer_slot", {})
        rendered_initializer = "\n".join(initializer)
        self.assertIn("(void)args;", rendered_initializer)
        self.assertIn("return 0;", rendered_initializer)

        plain_body = SimpleNamespace()
        extension_type = SimpleNamespace(body=plain_body)
        self.assertEqual(
            UniversalHPyModuleWriter._extension_type_methods(extension_type),
            [],
        )

        scope = SimpleNamespace(var_entries=[])
        property_node = Nodes.PropertyNode(
            None,
            name="property",
            body=plain_body,
        )
        extension_type = SimpleNamespace(
            body=property_node,
            entry=SimpleNamespace(type=SimpleNamespace(scope=scope)),
        )
        properties = UniversalHPyModuleWriter._extension_type_properties(
            extension_type)
        self.assertEqual(properties, [(property_node, {})])

    def test_nested_definition_success_assignment_and_directive_unwrap(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)
        inner_def = SimpleNamespace(pos=None)
        inner_node = ExprNodes.InnerFunctionNode(None)
        inner_node.def_node = inner_def
        assignment = Nodes.SingleAssignmentNode(
            None,
            lhs=SimpleNamespace(name="inner"),
            rhs=inner_node,
        )
        outer = SimpleNamespace(
            body=Nodes.StatListNode(None, stats=[assignment]))
        self.assertEqual(
            list(module_writer._iter_nested_defs(outer)),
            [(inner_def, inner_node)],
        )

        def_node = Nodes.DefNode(
            None,
            name="inner",
            args=[],
            body=Nodes.StatListNode(None, stats=[]),
        )
        directive = Nodes.CompilerDirectivesNode(
            None, body=def_node, directives={})
        self.assertIs(
            module_writer._unwrap_nested_def_stat(directive),
            def_node,
        )

    def test_inherited_field_layout_is_reused_by_extension_declarations(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        module_writer = UniversalHPyModuleWriter(
            SimpleNamespace(pos=None), runtime_api)

        base_field = SimpleNamespace(
            name="value",
            cname="value",
            type=PyrexTypes.c_int_type,
            visibility="private",
            is_inherited=False,
        )
        base_scope = SimpleNamespace(
            var_entries=[base_field],
            lookup_here=lambda name: base_field if name == "value" else None,
        )
        base_type = SimpleNamespace(
            scope=base_scope,
            is_final_type=False,
        )
        base_extension = SimpleNamespace(
            class_name="Base",
            body=Nodes.StatListNode(None, stats=[]),
            entry=SimpleNamespace(type=base_type),
            base_type=None,
        )

        inherited_field = SimpleNamespace(
            name="value",
            cname="value",
            type=PyrexTypes.c_int_type,
            visibility="private",
            is_inherited=True,
        )
        derived_scope = SimpleNamespace(
            var_entries=[inherited_field],
            lookup_here=lambda name: inherited_field,
        )
        derived_type = SimpleNamespace(
            scope=derived_scope,
            is_final_type=False,
        )
        derived_extension = SimpleNamespace(
            class_name="Derived",
            body=Nodes.StatListNode(None, stats=[]),
            entry=SimpleNamespace(type=derived_type),
            base_type=base_type,
        )

        declarations = module_writer._render_extension_type_declarations(
            [base_extension, derived_extension], "module")
        lines, *_, field_layouts = declarations
        self.assertIn(
            "__pyx_hpy_type_Base_object __pyx_hpy_base;",
            "\n".join(lines),
        )
        self.assertEqual(
            field_layouts[id(derived_extension)][id(inherited_field)],
            field_layouts[id(base_extension)][id(base_field)],
        )

    def test_recursive_comparison_closure_env_and_nogil_wrappers(self):
        runtime_api = create_runtime_api(HPY_UNIVERSAL_BACKEND)

        comparison_writer = UniversalHPyFunctionWriter(runtime_api)
        result_cname = comparison_writer.allocate_owned_handle("HPy_NULL")
        current_cname = comparison_writer.allocate_owned_handle(
            "HPy_Dup(ctx, ctx->h_None)")
        tail = SimpleNamespace(
            operand2=_OwnedNoneExpression(),
            operator="==",
            cascade=None,
            pos=None,
        )
        head = SimpleNamespace(
            operand2=_OwnedNoneExpression(),
            operator="==",
            cascade=tail,
            pos=None,
        )
        comparison_writer._generate_cascaded_comparison_tail(
            result_cname, current_cname, head)
        comparison_writer.close_owned_handle(current_cname, null_safe=True)
        comparison_writer.close_owned_handle(result_cname, null_safe=True)
        comparison_writer.assert_function_exit()

        capture = _ClosureCapture(
            "missing",
            SimpleNamespace(),
            "__pyx_hpy_capture_missing",
        )
        env_spec = _ClosureEnvSpec(0, object(), (capture,))
        closure_writer = UniversalHPyFunctionWriter(
            runtime_api,
            module_cname="m",
            closure_registry=_ClosureRegistry((env_spec,), ()),
        )
        closure_writer.allocate_closure_env_and_store_captures(
            env_spec.outer_def)
        closure_writer._close_remaining_owned_handles()
        closure_writer.assert_function_exit()

        function_type = SimpleNamespace(
            nogil=True,
            exception_value=None,
            exception_check=False,
        )
        entry = SimpleNamespace(
            ahpy_universal_external_c_scalar_kind="signed-int",
            ahpy_universal_external_c_argument_kinds=(),
            type=function_type,
            cname="tick",
        )
        call = ExprNodes.SimpleCallNode(
            None,
            function=SimpleNamespace(entry=entry),
            args=[],
        )
        wrapped_call = ExprNodes.CoerceToTempNode.__new__(
            ExprNodes.CoerceToTempNode)
        wrapped_call.arg = call
        statement = Nodes.ExprStatNode(None, expr=wrapped_call)
        nogil_writer = UniversalHPyFunctionWriter(runtime_api)
        nogil_writer.generate_nogil_external_c_block(SimpleNamespace(
            state="nogil",
            condition=None,
            body=Nodes.StatListNode(None, stats=[statement]),
            pos=None,
        ))
        nogil_writer.assert_function_exit()
        self.assertIn("(void)tick();", "\n".join(nogil_writer.lines))


class UniversalHPyModuleWriterTest(TestCase):
    def compile_source(self, source_text, module_name=None, **option_overrides):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        source = Path(temp_dir.name) / "bootstrap_case.pyx"
        output = Path(temp_dir.name) / "bootstrap_case.c"
        source.write_text(source_text, encoding="utf8")
        diagnostics = io.StringIO()
        with redirect_stderr(diagnostics):
            result = Main.compile(
                str(source),
                Options.CompilationOptions(
                    output_file=str(output),
                    language_level=3,
                    runtime_backend=HPY_UNIVERSAL_BACKEND,
                    **option_overrides,
                ),
                full_module_name=module_name,
            )
        generated = output.read_text(encoding="utf8") if output.exists() else ""
        return result, generated, diagnostics.getvalue()

    def test_output_and_instrumentation_modes_fail_closed(self):
        cases = (
            ({"cplus": True}, "C++ output is not implemented"),
            ({"annotate": True}, "annotated output is not implemented"),
            (
                {"compiler_directives": {"profile": True}},
                "generated profile instrumentation",
            ),
            (
                {"compiler_directives": {"linetrace": True}},
                "generated linetrace instrumentation",
            ),
            (
                {"compiler_directives": {"embedsignature": True}},
                "generated embedsignature instrumentation",
            ),
            (
                {"c_line_in_traceback": True},
                "generated C-line traceback instrumentation",
            ),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                result, generated, diagnostics = self.compile_source(
                    "def answer():\n    return 42\n",
                    **options,
                )
                self.assertEqual(result.num_errors, 1, diagnostics)
                self.assertFalse(generated)
                self.assertIn(expected, diagnostics)

    def test_qualified_module_name_uses_leaf_init_symbol(self):
        result, generated, diagnostics = self.compile_source(
            "'''qualified \"module\" documentation\n"
            "ikinci satır'''\n\n"
            "def answer():\n"
            "    '''answer documentation'''\n"
            "    return 42\n\n"
            "def selam_ç():\n"
            "    return 43\n\n"
            "cdef class QualifiedBox:\n"
            "    '''qualified box documentation'''\n"
            "    def answer(self):\n"
            "        '''box answer documentation'''\n"
            "        return 42\n\n"
            "    def değer(self):\n"
            "        return 44\n\n"
            "    property başlık:\n"
            "        def __get__(self):\n"
            "            return 46\n\n"
            "cdef class DeğerKutusu:\n"
            "    def answer(self):\n"
            "        return 45\n",
            module_name="ahpy_package.qualified_module",
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPy_MODINIT(qualified_module, __pyx_hpy_module)",
            generated,
        )
        self.assertNotIn("HPy_MODINIT(ahpy_package.", generated)
        self.assertIn(
            '.name = "ahpy_package.qualified_module.QualifiedBox"',
            generated,
        )
        self.assertIn(
            'HPyDef_METH(__pyx_hpy_def_0_answer, "answer", HPyFunc_NOARGS, '
            '.doc = "answer documentation")',
            generated,
        )
        self.assertIn(
            'HPyDef_METH(__pyx_hpy_type_0_QualifiedBox_method_0_answer, '
            '"answer", HPyFunc_NOARGS, .doc = "box answer documentation")',
            generated,
        )
        self.assertIn('    .doc = "qualified box documentation",', generated)
        self.assertIn(
            '    .doc = "qualified \\"module\\" documentation\\n'
            'ikinci sat\\304\\261r",',
            generated,
        )
        self.assertIn('"selam_\\303\\247"', generated)
        self.assertIn('"de\\304\\237er"', generated)
        self.assertIn("unicode_73656c616d5fc3a7", generated)
        self.assertIn("unicode_6465c49f6572", generated)
        self.assertIn('"ba\\305\\237l\\304\\261k"', generated)
        self.assertIn("unicode_6261c59f6cc4b16b", generated)
        self.assertIn(
            '.name = "ahpy_package.qualified_module.De\\304\\237erKutusu"',
            generated,
        )
        self.assertIn("unicode_4465c49f65724b7574757375", generated)

    def test_assignment_only_and_empty_modules_use_exec_definition(self):
        cases = (
            ("empty", ""),
            ("doc-only", "'''documentation only'''\n"),
            ("pass-only", "pass\n"),
            ("doc-and-pass", "'''documentation only'''\npass\n"),
            ("assignment-only", "VALUE = 47\nNAME = 'sabit'\n"),
        )
        for label, source in cases:
            with self.subTest(label=label):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 0, diagnostics)
                self.assertNotIn("HPyDef_METH(", generated)
                self.assertIn("HPyDef_SLOT(__pyx_hpy_mod_exec", generated)
                self.assertIn("&__pyx_hpy_mod_exec,", generated)
                self.assertIn("HPy_MODINIT(bootstrap_case,", generated)

    def test_hpy_early_builtin_filter_does_not_steal_base_handlers(self):
        base = Optimize.EarlyReplaceBuiltinCalls
        hpy = Optimize.HPyEarlyReplaceSequenceBuiltins
        self.assertIn("_function_is_builtin_name", base.__dict__)
        self.assertIn("_dispatch_to_handler", base.__dict__)
        self.assertIn("_handle_simple_function_float", base.__dict__)
        self.assertNotIn("_function_is_builtin_name", hpy.__dict__)
        self.assertIn("visit_SimpleCallNode", hpy.__dict__)
        self.assertIn("visit_GeneralCallNode", hpy.__dict__)

    def test_signed_64_bit_literal_boundaries_are_portable_c(self):
        result, generated, diagnostics = self.compile_source(
            "def minimum():\n"
            "    return -9223372036854775808\n\n"
            "def maximum():\n"
            "    return 9223372036854775807\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyLong_FromLongLong(ctx, (-9223372036854775807LL - 1LL))",
            generated,
        )
        self.assertIn(
            "HPyLong_FromLongLong(ctx, 9223372036854775807LL)", generated)

    def test_arbitrary_size_integer_uses_public_long_type_call(self):
        result, generated, diagnostics = self.compile_source(
            "def too_large():\n"
            "    return 1234567890123456789012345678901234567890\n\n"
            "def too_negative():\n"
            "    return -1234567890123456789012345678901234567890\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("ctx->h_LongType", generated)
        self.assertIn(
            '"1234567890123456789012345678901234567890"', generated)
        self.assertIn(
            '"-1234567890123456789012345678901234567890"', generated)

    def test_boolean_float_unicode_and_bytes_literals_use_runtime_api(self):
        result, generated, diagnostics = self.compile_source(
            "def true_value():\n"
            "    return True\n\n"
            "def false_value():\n"
            "    return False\n\n"
            "def float_value():\n"
            "    return 1.25\n\n"
            "def text_value():\n"
            "    return 'Türkçe 🐍'\n\n"
            "def bytes_value():\n"
            "    return b'a\\x00\\xff'\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Dup(ctx, ctx->h_True)", generated)
        self.assertIn("HPy_Dup(ctx, ctx->h_False)", generated)
        self.assertIn("HPyFloat_FromDouble(ctx, 1.25)", generated)
        self.assertIn("HPyUnicode_FromString(ctx,", generated)
        self.assertIn("HPyBytes_FromStringAndSize(ctx,", generated)
        self.assertIn(", 3)", generated)

    def test_unicode_nul_uses_length_aware_surrogatepass_construction(self):
        result, generated, diagnostics = self.compile_source(
            "def value():\n"
            "    return 'before\\x00after'\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyBytes_FromStringAndSize", generated)
        self.assertIn("HPyUnicode_FromEncodedObject", generated)
        self.assertIn('"surrogatepass"', generated)

    def test_non_finite_float_and_imaginary_literals_use_public_apis(self):
        result, generated, diagnostics = self.compile_source(
            "def positive_infinity():\n"
            "    return 1e10000\n\n"
            "def negative_infinity():\n"
            "    return -1e10000\n\n"
            "def imaginary():\n"
            "    return 2.5j\n\n"
            "def complex_value():\n"
            "    return 1 + 2.5j\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyFloat_FromDouble(ctx, HUGE_VAL)", generated)
        self.assertIn("ctx->h_ComplexType", generated)
        self.assertIn("HPy_Add(ctx,", generated)

    def test_lone_surrogate_unicode_uses_surrogatepass_construction(self):
        result, generated, diagnostics = self.compile_source(
            "def value():\n"
            "    return '\\ud800'\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyUnicode_FromEncodedObject", generated)
        self.assertIn('"surrogatepass"', generated)

    def test_fixed_list_and_tuple_use_hpy_builders_and_close_items(self):
        result, generated, diagnostics = self.compile_source(
            "def make_list():\n"
            "    return [1, None, 2]\n\n"
            "def make_tuple():\n"
            "    return (3, None)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyListBuilder __pyx_hpy_builder_0 = "
            "HPyListBuilder_New(ctx, 3);",
            generated,
        )
        self.assertIn(
            "HPyTupleBuilder __pyx_hpy_builder_0 = "
            "HPyTupleBuilder_New(ctx, 2);",
            generated,
        )
        self.assertIn(
            "HPyListBuilder_Set(ctx, __pyx_hpy_builder_0, 1, "
            "__pyx_hpy_temp_1);",
            generated,
        )
        self.assertIn(
            "HPyTupleBuilder_Build(ctx, __pyx_hpy_builder_0)", generated)
        self.assertGreaterEqual(
            generated.count("HPy_Close(ctx, __pyx_hpy_temp_"), 5)
        self.assertIn(
            'HPy_SetAttr_s(ctx, m, "__pyx_hpy_const_', generated)
        self.assertIn(
            'HPy_GetAttr_s(ctx, self, "__pyx_hpy_const_', generated)

    def test_multiplied_sequences_use_owned_base_and_factor_handles(self):
        result, generated, diagnostics = self.compile_source(
            "def repeated_list(factor, /):\n"
            "    return [1, None] * factor\n\n"
            "def repeated_tuple():\n"
            "    return (2, 'x') * 3\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyListBuilder_New(ctx, 2)", generated)
        self.assertIn("HPyTupleBuilder_New(ctx, 2)", generated)
        self.assertEqual(generated.count("HPy_Multiply(ctx,"), 2)
        self.assertIn("HPy_Close(ctx, __pyx_hpy_temp_", generated)

    def test_starred_sequences_normalize_iterables_and_concatenate_segments(self):
        result, generated, diagnostics = self.compile_source(
            "def expanded_list(values, /):\n"
            "    return [0, *values, 3]\n\n"
            "def expanded_tuple(values, /):\n"
            "    return (*values, 'x')\n\n"
            "def expanded_and_repeated(values, /):\n"
            "    return [*values] * 2\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("ctx->h_ListType", generated)
        self.assertIn("ctx->h_TupleType", generated)
        self.assertGreaterEqual(generated.count("HPy_Add(ctx,"), 2)
        self.assertIn("HPy_InPlaceMultiply(ctx,", generated)
        self.assertNotIn("HPy_GetIter", generated)

    def test_immutable_literal_caches_are_deduplicated_and_module_owned(self):
        result, generated, diagnostics = self.compile_source(
            "def text_one():\n"
            "    return 'same'\n\n"
            "def text_two():\n"
            "    return 'same'\n\n"
            "def bytes_one():\n"
            "    return b'same'\n\n"
            "def bytes_two():\n"
            "    return b'same'\n\n"
            "def tuple_one():\n"
            "    return (1, 'same', None)\n\n"
            "def tuple_two():\n"
            "    return (1, 'same', None)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        # unicode, bytes, tuple, nested int 1, nested None
        self.assertEqual(
            generated.count('HPy_SetAttr_s(ctx, m, "__pyx_hpy_const_'), 5)
        self.assertEqual(
            generated.count('HPy_GetAttr_s(ctx, self, "__pyx_hpy_const_'), 6)
        self.assertNotIn("static HPy __pyx_hpy_const_", generated)
        self.assertNotIn("HPyGlobal", generated)

    def test_scalar_literal_caches_are_deduplicated_and_module_owned(self):
        result, generated, diagnostics = self.compile_source(
            "def int_one():\n"
            "    return 7\n\n"
            "def int_two():\n"
            "    return 7\n\n"
            "def float_one():\n"
            "    return 1.5\n\n"
            "def float_two():\n"
            "    return 1.5\n\n"
            "def none_one():\n"
            "    return None\n\n"
            "def none_two():\n"
            "    return None\n\n"
            "def bool_one():\n"
            "    return True\n\n"
            "def bool_two():\n"
            "    return True\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(
            generated.count('HPy_SetAttr_s(ctx, m, "__pyx_hpy_const_'), 4)
        self.assertEqual(
            generated.count('HPy_GetAttr_s(ctx, self, "__pyx_hpy_const_'), 8)
        self.assertNotIn("static HPy __pyx_hpy_const_", generated)
        self.assertNotIn("HPyGlobal", generated)

    def test_constant_cache_prefix_is_reserved(self):
        result, generated, diagnostics = self.compile_source(
            "__pyx_hpy_const_0 = 1\n\n"
            "def answer():\n"
            "    return 42\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("reserved aHPy cache prefix", diagnostics)

    def test_literal_defaults_use_module_owned_storage_and_optional_parser(self):
        result, generated, diagnostics = self.compile_source(
            "def values(required, value=2, *, option=(3, None)):\n"
            "    return [required, value, option]\n\n"
            "def positional(value=5, /):\n"
            "    return value\n\n"
            "def mutable(bucket=[]):\n"
            "    return bucket\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"|OOO:values"', generated)
        self.assertIn('"|O:positional"', generated)
        self.assertEqual(
            generated.count('HPy_SetAttr_s(ctx, m, "__pyx_hpy_default_'), 4)
        self.assertGreaterEqual(
            generated.count('HPy_GetAttr_s(ctx, self, "__pyx_hpy_default_'), 4)
        self.assertIn("HPy_Dup(ctx, __pyx_hpy_arg_", generated)
        self.assertIn("HPyTracker_Close(ctx, __pyx_hpy_arg_tracker)", generated)
        self.assertNotIn("HPyGlobal", generated)

    def test_effectful_defaults_evaluate_once_during_module_exec(self):
        result, generated, diagnostics = self.compile_source(
            "MARKER = 7\n"
            "\n"
            "def value(item=len([1, 2]), tagged=MARKER):\n"
            "    return [item, tagged]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Call", generated)
        self.assertGreaterEqual(
            generated.count('HPy_SetAttr_s(ctx, m, "__pyx_hpy_default_'), 2)
        # Module-function defaults are evaluated after top-level assignments so
        # name references observe source order.
        marker_store = generated.index('HPy_SetAttr_s(ctx, m, "MARKER"')
        default_stores = [
            generated.index('HPy_SetAttr_s(ctx, m, "__pyx_hpy_default_0"'),
            generated.index('HPy_SetAttr_s(ctx, m, "__pyx_hpy_default_1"'),
        ]
        self.assertTrue(all(marker_store < offset for offset in default_stores))

    def test_sequence_item_failure_cancels_nested_builders_in_reverse_order(self):
        result, generated, diagnostics = self.compile_source(
            "def nested():\n"
            "    return [[1]]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        failure = generated[generated.index("if (HPy_IsNull(__pyx_hpy_temp_0)) {"):]
        inner_cancel = failure.index(
            "HPyListBuilder_Cancel(ctx, __pyx_hpy_builder_1);")
        outer_cancel = failure.index(
            "HPyListBuilder_Cancel(ctx, __pyx_hpy_builder_0);")
        error_return = failure.index("return HPy_NULL;")
        self.assertLess(inner_cancel, outer_cancel)
        self.assertLess(outer_cancel, error_return)
        self.assertNotIn(
            "HPy_Close(ctx, __pyx_hpy_temp_0);",
            failure[:error_return],
        )

    def test_empty_sequences_still_use_balanced_builders(self):
        result, generated, diagnostics = self.compile_source(
            "def empty_list():\n"
            "    return []\n\n"
            "def empty_tuple():\n"
            "    return ()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyListBuilder_New(ctx, 0)", generated)
        self.assertIn("HPyListBuilder_Build(ctx, __pyx_hpy_builder_0)", generated)
        self.assertIn("HPyTupleBuilder_New(ctx, 0)", generated)
        self.assertIn("HPyTupleBuilder_Build(ctx, __pyx_hpy_builder_0)", generated)

    def test_fixed_dictionary_owns_items_and_cleans_set_failure(self):
        result, generated, diagnostics = self.compile_source(
            "def mapping():\n"
            "    return {'one': 1, 2: [None]}\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyDict_New(ctx)", generated)
        self.assertIn("if (HPy_SetItem(ctx,", generated)
        set_failure = generated[generated.index("if (HPy_SetItem(ctx,"):]
        error_return = set_failure.index("return HPy_NULL;")
        cleanup = set_failure[:error_return]
        value_close = cleanup.index("HPy_Close(ctx, __pyx_hpy_temp_2);")
        key_close = cleanup.index("HPy_Close(ctx, __pyx_hpy_temp_1);")
        dict_close = cleanup.index("HPy_Close(ctx, __pyx_hpy_temp_0);")
        self.assertLess(value_close, key_close)
        self.assertLess(key_close, dict_close)

    def test_positional_only_argument_is_borrowed_and_duplicated(self):
        result, generated, diagnostics = self.compile_source(
            "def identity(value, /):\n"
            "    return value\n\n"
            "def wrap(value, /):\n"
            "    return [value, {'copy': value}]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            'HPyDef_METH(__pyx_hpy_def_0_identity, "identity", HPyFunc_O)',
            generated,
        )
        self.assertIn(
            "static HPy __pyx_hpy_def_0_identity_impl"
            "(HPyContext *ctx, HPy self, HPy arg)",
            generated,
        )
        self.assertIn("HPy __pyx_hpy_temp_0 = HPy_Dup(ctx, arg);", generated)
        self.assertIn("return __pyx_hpy_temp_0;", generated)
        self.assertNotIn("HPy_Close(ctx, arg)", generated)

    def test_attribute_and_item_get_close_owned_operands_before_error_return(self):
        result, generated, diagnostics = self.compile_source(
            "def item(value, /):\n"
            "    return value['key']\n\n"
            "def attribute(value, /):\n"
            "    return value.real\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_GetItem(ctx,", generated)
        self.assertIn('HPy_GetAttr_s(ctx,', generated)
        item_call = generated.index("HPy_GetItem(ctx,")
        item_error = generated.index(
            "if (HPy_IsNull(__pyx_hpy_temp_2))", item_call)
        self.assertIn("HPy_Close(ctx, __pyx_hpy_temp_1);", generated[item_call:item_error])
        self.assertIn("HPy_Close(ctx, __pyx_hpy_temp_0);", generated[item_call:item_error])
        attribute_impl = generated[generated.index("attribute_impl"):]
        attribute_impl = attribute_impl[:attribute_impl.index("\n}\n")]
        self.assertIn('HPy_GetAttr_s(ctx, arg, "real")', attribute_impl)
        self.assertNotIn("HPy_Dup(ctx, arg)", attribute_impl)
        self.assertNotIn("HPy_Close(ctx, arg)", attribute_impl)

    def test_zero_and_one_argument_calls_close_operands_before_error_return(self):
        result, generated, diagnostics = self.compile_source(
            "def invoke(func, /):\n"
            "    return func()\n\n"
            "def invoke_one(func, /):\n"
            "    return func(5)\n\n"
            "def invoke_method(value, /):\n"
            "    return value.upper()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        invoke_impl = generated[generated.index("invoke_impl"):]
        invoke_impl = invoke_impl[:invoke_impl.index("\n}\n")]
        self.assertIn("HPy_Call(ctx, arg, NULL, 0, HPy_NULL)", invoke_impl)
        self.assertNotIn("HPy_Dup(ctx, arg)", invoke_impl)
        self.assertNotIn("HPy_Close(ctx, arg)", invoke_impl)
        self.assertIn(
            "HPy_Call(ctx, __pyx_hpy_temp_0, &__pyx_hpy_temp_1, 1, HPy_NULL)",
            generated,
        )
        self.assertIn("HPy_CallMethod(ctx,", generated)
        self.assertIn('HPyUnicode_FromString(ctx, "upper")', generated)

    def test_direct_method_call_avoids_bound_method_getattr(self):
        result, generated, diagnostics = self.compile_source(
            "def invoke_method(value, /):\n"
            "    return value.upper()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_CallMethod(ctx,", generated)
        self.assertNotIn("HPy_GetAttr_s(ctx,", generated)
        self.assertNotIn("HPy_Call(ctx,", generated)

    def test_method_call_emits_receiver_as_callmethod_args0(self):
        result, generated, diagnostics = self.compile_source(
            "def invoke(value, left, right, /):\n"
            "    return value.join(left, right)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_CallMethod(ctx,", generated)
        self.assertNotIn("HPy_GetAttr_s(ctx,", generated.split("invoke_impl", 1)[1].split(
            "HPy_CallMethod", 1)[0]
        )
        impl = generated[generated.index("invoke_impl"):]
        call_method = impl.index("HPy_CallMethod(ctx,")
        prefix = impl[:call_method]
        # Receiver handle is args[0]; both positional args are in the same array.
        self.assertRegex(
            prefix,
            r"HPy __pyx_hpy_call_args_\d+\[\] = "
            r"\{__pyx_hpy_temp_\d+, __pyx_hpy_temp_\d+, __pyx_hpy_temp_\d+\};",
        )
        self.assertIn('HPyUnicode_FromString(ctx, "join")', prefix)

    def test_ellipsis_literal_duplicates_context_constant(self):
        result, generated, diagnostics = self.compile_source(
            "def value():\n"
            "    return ...\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("ctx->h_Ellipsis", generated)
        self.assertIn("HPy_Dup(ctx, ctx->h_Ellipsis)", generated)

    def test_fstring_uses_add_and_format_method_call(self):
        result, generated, diagnostics = self.compile_source(
            "def greet(name, /):\n"
            "    return f'hello {name!s}:{name!r}:{name!a}:{name:02d}'\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Str(ctx,", generated)
        self.assertIn("HPy_Repr(ctx,", generated)
        self.assertIn("HPy_ASCII(ctx,", generated)
        self.assertIn("__format__", generated)
        self.assertIn("HPy_CallMethod(ctx,", generated)
        self.assertIn("HPy_Add(ctx,", generated)

    def test_walrus_assigns_once_and_returns_owned_duplicate(self):
        result, generated, diagnostics = self.compile_source(
            "def decide(values, limit, /):\n"
            "    if (count := len(values)) > limit:\n"
            "        return count\n"
            "    return 0\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Dup(ctx,", generated)
        impl_start = generated.index("decide_impl")
        self.assertIn("HPy_Call(ctx,", generated[impl_start:])

    def test_sequence_unpacking_uses_length_and_indexed_getitem(self):
        result, generated, diagnostics = self.compile_source(
            "def unpack(values, /):\n"
            "    a, b = values\n"
            "    return a, b\n\n"
            "def starred(values, /):\n"
            "    head, *rest = values\n"
            "    return head, rest\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Length(ctx,", generated)
        self.assertIn("HPy_GetItem_i(ctx,", generated)
        self.assertIn("snprintf(", generated)
        self.assertIn("not enough values to unpack", generated)
        self.assertIn("too many values to unpack", generated)
        self.assertIn("HPyListBuilder_New(ctx,", generated)

    def test_parallel_and_cascaded_assignments_evaluate_rhs_once(self):
        result, generated, diagnostics = self.compile_source(
            "def parallel():\n"
            "    a, b = 1, 2\n"
            "    return a, b\n\n"
            "def cascaded(values, /):\n"
            "    a = b = values\n"
            "    return a, b\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Dup(ctx,", generated)
        cascaded_start = generated.index("cascaded_impl")
        self.assertGreaterEqual(
            generated[cascaded_start:].count("HPy_Dup(ctx,"), 1)

    def test_for_loop_unpacking_targets_use_getitem(self):
        result, generated, diagnostics = self.compile_source(
            "def walk():\n"
            "    total = 0\n"
            "    for left, right in [(1, 2), (3, 4)]:\n"
            "        total = total + left + right\n"
            "    return total\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_GetItem_i(ctx,", generated)
        self.assertIn("for (HPy_ssize_t", generated)

    def test_list_and_dict_comprehensions_over_literal_sequences(self):
        result, generated, diagnostics = self.compile_source(
            "def values():\n"
            "    return [item * 2 for item in (1, 2, 3) if item]\n\n"
            "def mapping():\n"
            "    return {key: key + 1 for key in (1, 2)}\n\n"
            "def nested():\n"
            "    return [left + right for left in (1, 2) for right in (10,)]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("ctx->h_ListType", generated)
        self.assertIn('HPyUnicode_FromString(ctx, "append")', generated)
        self.assertIn("HPy_CallMethod(ctx,", generated)
        self.assertIn("HPyDict_New(ctx)", generated)
        self.assertIn("HPy_SetItem(ctx,", generated)
        self.assertGreaterEqual(generated.count("for (HPy_ssize_t"), 2)

    def test_set_comprehension_has_actionable_hpy09_diagnostic(self):
        result, generated, diagnostics = self.compile_source(
            "def values():\n"
            "    return {item for item in (1, 2, 3)}\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("set comprehensions remain blocked", diagnostics)

    def test_inferred_len_local_stays_python_object_under_universal(self):
        result, generated, diagnostics = self.compile_source(
            "def decide(values, limit, /):\n"
            "    count = len(values)\n"
            "    if count > limit:\n"
            "        return count\n"
            "    return 0\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        # Universal keeps the inferred local as a Python object handle and
        # calls builtins.len instead of a typed C local assignment path.
        self.assertIn('HPy_GetAttr_s(ctx, __pyx_hpy_temp_0, "len")', generated)
        self.assertIn("HPy_Call(ctx,", generated)
        self.assertIn("HPy_RichCompare(ctx,", generated)

    def test_multiple_positional_call_uses_owned_handle_array(self):
        result, generated, diagnostics = self.compile_source(
            "def invoke_two(func, /):\n"
            "    return func(4, 5)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPy __pyx_hpy_call_args_0[] = {__pyx_hpy_temp_1, "
            "__pyx_hpy_temp_2};",
            generated,
        )
        self.assertIn(
            "HPy_Call(ctx, __pyx_hpy_temp_0, __pyx_hpy_call_args_0, 2, "
            "HPy_NULL)",
            generated,
        )
        call_end = generated.index("HPy_Close(ctx, __pyx_hpy_temp_2);")
        self.assertLess(
            generated.index("HPy_Call(ctx,", generated.index("invoke_two_impl")),
            call_end,
        )

    def test_keyword_and_mixed_calls_use_kwnames_tuple_and_value_array(self):
        result, generated, diagnostics = self.compile_source(
            "def keyword_call(func, /):\n"
            "    return func(left=4, right=5)\n\n"
            "def mixed_call(func, /):\n"
            "    return func(1, right=5)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyTupleBuilder_New(ctx, 2)", generated)
        self.assertIn(
            "HPy_Call(ctx, __pyx_hpy_temp_0, __pyx_hpy_call_args_0, 0, "
            "__pyx_hpy_temp_3)",
            generated,
        )
        mixed_start = generated.index("mixed_call_impl")
        self.assertIn(
            "HPy_Call(ctx, __pyx_hpy_temp_0, __pyx_hpy_call_args_0, 1, "
            "__pyx_hpy_temp_3)",
            generated[mixed_start:],
        )
        self.assertIn("HPy_Close(ctx, __pyx_hpy_temp_3);", generated)

    def test_starred_and_dynamic_keyword_calls_use_tuple_dict_api(self):
        result, generated, diagnostics = self.compile_source(
            "def expanded_call(func, values, /):\n"
            "    return func(0, *values, 3)\n\n"
            "def keyword_mapping_call(func, values, /):\n"
            "    return func(**values)\n\n"
            "def mixed_expanded_call(func, positional, keywords, /):\n"
            "    return func(1, *positional, named=4, **keywords)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_CallTupleDict(ctx,", generated)
        self.assertIn('HPy_GetAttr_s(ctx,', generated)
        self.assertIn('"keys"', generated)
        self.assertIn("HPy_Length(ctx,", generated)
        self.assertIn("HPy_GetItem_i(ctx,", generated)
        self.assertIn("got multiple values for keyword argument", generated)
        self.assertNotIn("PyObject_Call", generated)

    def test_keyword_signature_parses_tracked_handles_and_closes_tracker(self):
        result, generated, diagnostics = self.compile_source(
            "def ordinary(value):\n"
            "    return value\n\n"
            "def pair(first, second):\n"
            "    return [first, second]\n\n"
            "def mixed(first, /, second):\n"
            "    return {'first': first, 'second': second}\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            'HPyDef_METH(__pyx_hpy_def_0_ordinary, "ordinary", '
            'HPyFunc_KEYWORDS)',
            generated,
        )
        self.assertIn('"O:ordinary"', generated)
        self.assertIn(
            "const HPy *args, size_t nargs, HPy kwnames)", generated)
        self.assertIn(
            'static const char *keywords[] = {\n        "first",\n'
            '        "second",\n        NULL,',
            generated,
        )
        self.assertIn(
            'HPyArg_ParseKeywords(ctx, &__pyx_hpy_arg_tracker, args, nargs, '
            'kwnames, "OO:pair", keywords, &__pyx_hpy_arg_0, '
            '&__pyx_hpy_arg_1)',
            generated,
        )
        self.assertIn("HPy_Length(ctx, kwnames)", generated)
        self.assertIn("HPy_GetItem_i(ctx, kwnames, __pyx_hpy_kw_index)", generated)
        self.assertIn("HPyUnicode_AsUTF8AndSize(ctx, __pyx_hpy_kw_name", generated)
        self.assertIn("memcmp(__pyx_hpy_kw_utf8, \"first\"", generated)
        self.assertIn("ctx->h_TypeError", generated)
        self.assertIn("got an unexpected keyword argument", generated)
        self.assertIn("got multiple values for an argument", generated)
        self.assertIn(
            'static const char *keywords[] = {\n        "",\n'
            '        "second",',
            generated,
        )
        ordinary_start = generated.index(
            "static HPy __pyx_hpy_def_0_ordinary_impl")
        tracker_close = generated.index(
            "HPyTracker_Close(ctx, __pyx_hpy_arg_tracker);")
        result_return = generated.index(
            "return __pyx_hpy_temp_", ordinary_start)
        self.assertLess(tracker_close, result_return)

    def test_required_positional_signature_binds_borrowed_argument_array(self):
        result, generated, diagnostics = self.compile_source(
            "def add(left, right, /):\n"
            "    return left + right\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            'HPyDef_METH(__pyx_hpy_def_0_add, "add", HPyFunc_VARARGS)',
            generated,
        )
        start = generated.index("static HPy __pyx_hpy_def_0_add_impl")
        implementation = generated[start:generated.index("HPyDef_SLOT", start)]
        self.assertIn("const HPy *args, size_t nargs)", implementation)
        self.assertNotIn("HPy kwnames", implementation)
        self.assertIn("if (nargs != 2) {", implementation)
        self.assertIn("add() takes exactly 2 arguments", implementation)
        self.assertIn("HPy_Add(ctx, args[0], args[1])", implementation)
        self.assertNotIn("HPy_Dup", implementation)
        self.assertNotIn("HPy_Close", implementation)
        self.assertNotIn("HPyArg_ParseKeywords", implementation)
        self.assertNotIn("HPyTracker", implementation)

    def test_required_positional_instance_method_uses_varargs_contract(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Pair:\n"
            "    def combine(self, left, right, /):\n"
            "        return [left, right]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"combine", HPyFunc_VARARGS', generated)
        start = generated.index("_combine_impl")
        implementation = generated[start:generated.index("HPyDef_SLOT", start)]
        self.assertIn("const HPy *args, size_t nargs)", implementation)
        self.assertIn("if (nargs != 2) {", implementation)
        self.assertIn(
            "HPyListBuilder_Set(ctx, __pyx_hpy_builder_0, 0, args[0])",
            implementation,
        )
        self.assertNotIn("HPyArg_ParseKeywords", implementation)
        self.assertNotIn("HPyTracker", implementation)

    def test_required_keyword_only_and_positional_arity_are_validated(self):
        result, generated, diagnostics = self.compile_source(
            "def configure(value, *, option):\n"
            "    return [value, option]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("if (nargs > 1) {", generated)
        self.assertIn("received too many positional arguments", generated)
        self.assertIn('"OO:configure"', generated)
        self.assertIn(
            'static const char *keywords[] = {\n        "value",\n'
            '        "option",',
            generated,
        )

    def test_linear_local_statements_close_reassigned_and_discarded_handles(self):
        result, generated, diagnostics = self.compile_source(
            "def linear(value, /):\n"
            "    result = [value]\n"
            "    result\n"
            "    result = {'value': result}\n"
            "    pass\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyListBuilder_New(ctx, 1)", generated)
        self.assertIn("HPyDict_New(ctx)", generated)
        self.assertGreaterEqual(
            generated.count("HPy_Close(ctx, __pyx_hpy_temp_"), 6)
        return_line = generated.rindex("return __pyx_hpy_temp_")
        self.assertIn("HPy_Close(ctx,", generated[:return_line])

    def test_attribute_and_item_set_delete_close_operands_before_status_error(self):
        result, generated, diagnostics = self.compile_source(
            "def mutate(mapping, obj, /):\n"
            "    mapping['new'] = 7\n"
            "    obj.value = 8\n"
            "    del mapping['old']\n"
            "    del obj.old\n"
            "    return mapping\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_SetItem(ctx,", generated)
        self.assertIn('HPy_SetAttr_s(ctx,', generated)
        self.assertIn("HPy_DelItem(ctx,", generated)
        self.assertIn('HPy_DelAttr_s(ctx,', generated)
        set_call = generated.index("int __pyx_hpy_status_0 = HPy_SetItem(ctx,")
        first_close = generated.index("HPy_Close(ctx,", set_call)
        status_check = generated.index("if (__pyx_hpy_status_0 < 0)", set_call)
        self.assertLess(set_call, first_close)
        self.assertLess(first_close, status_check)

    def test_conditional_early_return_forks_cleanup_state(self):
        result, generated, diagnostics = self.compile_source(
            "def choose(condition, value, /):\n"
            "    local = [value]\n"
            "    if condition:\n"
            "        selected = {'early': local}\n"
            "        return selected\n"
            "    return local\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_IsTrue(ctx,", generated)
        self.assertIn("if (__pyx_hpy_truth_0) {", generated)
        branch = generated[generated.index("if (__pyx_hpy_truth_0) {"):]
        self.assertIn("HPy_Close(ctx,", branch[:branch.index("return ")])

    def test_if_elif_else_all_return_with_independent_cleanup_states(self):
        result, generated, diagnostics = self.compile_source(
            "def choose(first, second, value, /):\n"
            "    local = [value]\n"
            "    if first:\n"
            "        return {'branch': 'first', 'value': local}\n"
            "    elif second:\n"
            "        return {'branch': 'second', 'value': local}\n"
            "    else:\n"
            "        return {'branch': 'else', 'value': local}\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("if (__pyx_hpy_truth_0) {", generated)
        self.assertIn("if (__pyx_hpy_truth_1) {", generated)
        impl = generated[generated.index("choose_impl"):]
        self.assertNotIn("HPyTracker_Close(ctx,", impl.split("HPyDef_SLOT", 1)[0])
        self.assertGreaterEqual(impl.count("HPy_Close(ctx,"), 3)
        self.assertEqual(generated.count("return __pyx_hpy_temp_"), 3)

    def test_builtin_exception_literal_raise_closes_locals_and_tracker(self):
        result, generated, diagnostics = self.compile_source(
            "def fail(value):\n"
            "    local = [value]\n"
            "    raise ValueError('aHPy failure')\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            'HPyErr_SetString(ctx, ctx->h_ValueError, "aHPy failure");',
            generated,
        )
        error_set = generated.index(
            'HPyErr_SetString(ctx, ctx->h_ValueError, "aHPy failure")')
        local_close = generated.index("HPy_Close(ctx,", error_set)
        tracker_close = generated.index("HPyTracker_Close(ctx,", error_set)
        error_return = generated.index("return HPy_NULL;", error_set)
        self.assertLess(error_set, local_close)
        self.assertLess(local_close, tracker_close)
        self.assertLess(tracker_close, error_return)

    def test_builtin_exception_payload_uses_one_argument_tuple_and_cleanup(self):
        result, generated, diagnostics = self.compile_source(
            "def fail(value):\n"
            "    payload = [value]\n"
            "    raise ValueError(payload)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyTupleBuilder_New(ctx, 1)", generated)
        self.assertIn("HPyTupleBuilder_Set(ctx,", generated)
        self.assertIn(
            "HPyErr_SetObject(ctx, ctx->h_ValueError,", generated)
        error_set = generated.index(
            "HPyErr_SetObject(ctx, ctx->h_ValueError,")
        self.assertIn("HPy_Close(ctx,", generated[error_set:])
        self.assertIn("HPyTracker_Close(ctx,", generated[error_set:])

    def test_memory_error_uses_public_no_memory_api_and_cleanup(self):
        result, generated, diagnostics = self.compile_source(
            "def fail(value):\n"
            "    local = [value]\n"
            "    raise MemoryError\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        error_set = generated.index("HPyErr_NoMemory(ctx)")
        self.assertIn("HPy_Close(ctx,", generated[error_set:])
        self.assertIn("HPyTracker_Close(ctx,", generated[error_set:])

    def test_builtin_exception_zero_and_multiple_arguments_use_exact_tuple(self):
        result, generated, diagnostics = self.compile_source(
            "def fail_empty(value):\n"
            "    local = [value]\n"
            "    raise ValueError()\n\n"
            "def fail_bare(value):\n"
            "    local = [value]\n"
            "    raise ValueError\n\n"
            "def fail_multiple(first, second):\n"
            "    raise ValueError(first, second)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertGreaterEqual(generated.count("HPyTupleBuilder_New(ctx, 0)"), 2)
        self.assertIn("HPyTupleBuilder_New(ctx, 2)", generated)
        self.assertIn("HPyTupleBuilder_Set(ctx,", generated)
        self.assertGreaterEqual(
            generated.count("HPyErr_SetObject(ctx, ctx->h_ValueError,"), 3)

    def test_dynamic_exception_type_or_instance_uses_public_type_checks(self):
        result, generated, diagnostics = self.compile_source(
            "def fail(exception, value):\n"
            "    local = [value]\n"
            "    raise exception\n\n"
            "def fail_call(factory, value):\n"
            "    local = [value]\n"
            "    raise factory(value)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Type(ctx,", generated)
        self.assertIn("HPy_TypeCheck(ctx,", generated)
        self.assertIn("ctx->h_BaseException", generated)
        self.assertIn("ctx->h_TypeType", generated)
        self.assertIn("HPyType_IsSubtype(ctx,", generated)
        self.assertIn("exceptions must derive from BaseException", generated)
        self.assertGreaterEqual(generated.count("HPyErr_SetObject(ctx,"), 4)
        self.assertIn("HPyTracker_Close(ctx,", generated)

    def test_terminal_try_except_matches_current_hpy_error(self):
        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        return callable()\n"
            "    except ValueError:\n"
            "        return 42\n"
            "    except TypeError:\n"
            "        return 'type'\n"
            "    except:\n"
            "        return None\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("goto __pyx_hpy_except_0;", generated)
        self.assertIn(
            "HPyErr_ExceptionMatches(ctx, ctx->h_ValueError)", generated)
        self.assertIn(
            "HPyErr_ExceptionMatches(ctx, ctx->h_TypeError)", generated)
        self.assertGreaterEqual(generated.count("HPyErr_Clear(ctx);"), 3)
        self.assertNotIn("PyErr_Fetch", generated)
        self.assertNotIn("Python.h", generated)

    def test_terminal_try_except_catches_explicit_raise_and_returns_container(self):
        result, generated, diagnostics = self.compile_source(
            "def handled():\n"
            "    try:\n"
            "        raise ValueError('failure')\n"
            "    except ValueError:\n"
            "        return [1, 2]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        error_set = generated.index(
            'HPyErr_SetString(ctx, ctx->h_ValueError, "failure")')
        handler_jump = generated.index("goto __pyx_hpy_except_0;", error_set)
        handler_label = generated.index("__pyx_hpy_except_0:", handler_jump)
        self.assertLess(error_set, handler_jump)
        self.assertLess(handler_jump, handler_label)
        self.assertIn("HPyListBuilder_New(ctx, 2)", generated[handler_label:])

    def test_terminal_try_except_cleans_linear_try_temporaries(self):
        result, generated, diagnostics = self.compile_source(
            "def handled(callable, value):\n"
            "    try:\n"
            "        local = [value]\n"
            "        callable()\n"
            "        return local\n"
            "    except ValueError:\n"
            "        return ('handled',)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        call_index = generated.index("HPy_Call(ctx,")
        handler_jump = generated.index("goto __pyx_hpy_except_0;", call_index)
        self.assertIn("HPy_Close(ctx,", generated[call_index:handler_jump])
        self.assertIn("HPyTracker_Close(ctx,", generated[handler_jump:])

    def test_terminal_try_except_supports_general_handler_body_and_terminal_raise(self):
        result, generated, diagnostics = self.compile_source(
            "def handled(callable, value, /):\n"
            "    try:\n"
            "        return callable()\n"
            "    except ValueError:\n"
            "        local = [value]\n"
            "        if value:\n"
            "            local += [value]\n"
            "        return local\n\n"
            "def translated(callable, /):\n"
            "    try:\n"
            "        return callable()\n"
            "    except ValueError:\n"
            "        marker = ['translated']\n"
            "        raise TypeError(marker)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        handler_label = generated.index("__pyx_hpy_except_0:")
        clear = generated.index("HPyErr_Clear(ctx);", handler_label)
        builder = generated.index("HPyListBuilder_New(ctx, 1)", clear)
        branch = generated.index("if (__pyx_hpy_truth_", builder)
        return_index = generated.index("return ", branch)
        self.assertLess(clear, builder)
        self.assertLess(builder, branch)
        self.assertLess(branch, return_index)
        translated_label = generated.index(
            "__pyx_hpy_except_0:", handler_label + 1)
        translated_clear = generated.index(
            "HPyErr_Clear(ctx);", translated_label)
        type_error = generated.index("ctx->h_TypeError", translated_clear)
        self.assertLess(translated_clear, type_error)

    def test_try_except_target_and_observable_handler_state_remain_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        return callable()\n"
            "    except ValueError as error:\n"
            "        return 42\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("except targets require a public exception-state API", diagnostics)

        # Non-literal handler returns are supported after clear; keep
        # exception-binding and nested try as the residual rejection surface.
        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        try:\n"
            "            return callable()\n"
            "        except TypeError:\n"
            "            return 1\n"
            "    except ValueError:\n"
            "        return 2\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("nested try/except", diagnostics)

        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        return callable()\n"
            "    except ValueError:\n"
            "        if callable:\n"
            "            try:\n"
            "                return 1\n"
            "            except TypeError:\n"
            "                return 2\n"
            "        return 3\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("nested try/except", diagnostics)

    def test_nonterminal_and_else_try_except_forms_remain_rejected(self):
        # Pre-terminal if/while/for in the try body is supported; nested try
        # and try/except-else remain rejected.
        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        try:\n"
            "            return callable()\n"
            "        except TypeError:\n"
            "            return 0\n"
            "        return 1\n"
            "    except ValueError:\n"
            "        return 2\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("nested try/except", diagnostics)

        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        callable()\n"
            "    except ValueError:\n"
            "        return 2\n"
            "    else:\n"
            "        return 3\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("try/except else clauses", diagnostics)

        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        if callable():\n"
            "            pass\n"
            "        return 1\n"
            "    except ValueError:\n"
            "        return 2\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyErr_ExceptionMatches", generated)

    def test_tuple_exception_pattern_normalizes_to_current_error_matches(self):
        result, generated, diagnostics = self.compile_source(
            "def handled(callable):\n"
            "    try:\n"
            "        return callable()\n"
            "    except (ValueError, TypeError):\n"
            "        return 2\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyErr_ExceptionMatches(ctx, ctx->h_ValueError) || "
            "HPyErr_ExceptionMatches(ctx, ctx->h_TypeError)",
            generated,
        )

    def test_transformed_nested_statement_lists_are_flattened(self):
        result, generated, diagnostics = self.compile_source(
            "def loop_values():\n"
            "    counter = 3\n"
            "    values = []\n"
            "    while counter:\n"
            "        values += [counter]\n"
            "        counter -= 1\n"
            "    return values\n\n"
            "def sum_values():\n"
            "    total = 0\n"
            "    for item in [1, 2, 3]:\n"
            "        total += item\n"
            "    result = [0, total, 3]\n"
            "    result[1:2] = [7]\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("while (1) {", generated)
        self.assertIn("HPy_GetItem_i(ctx,", generated)

    def test_binary_number_operations_borrow_direct_name_operands(self):
        result, generated, diagnostics = self.compile_source(
            "def add(left, right, /):\n"
            "    return left + right\n\n"
            "def subtract(left, right, /):\n"
            "    return left - right\n\n"
            "def multiply(left, right, /):\n"
            "    return left * right\n\n"
            "def matrix_multiply(left, right, /):\n"
            "    return left @ right\n\n"
            "def true_divide(left, right, /):\n"
            "    return left / right\n\n"
            "def floor_divide(left, right, /):\n"
            "    return left // right\n\n"
            "def remainder(left, right, /):\n"
            "    return left % right\n\n"
            "def left_shift(left, right, /):\n"
            "    return left << right\n\n"
            "def right_shift(left, right, /):\n"
            "    return left >> right\n\n"
            "def bitwise_and(left, right, /):\n"
            "    return left & right\n\n"
            "def bitwise_xor(left, right, /):\n"
            "    return left ^ right\n\n"
            "def bitwise_or(left, right, /):\n"
            "    return left | right\n\n"
            "def power(left, right, /):\n"
            "    return left ** right\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Add(ctx,", generated)
        self.assertIn("HPy_Subtract(ctx,", generated)
        self.assertIn("HPy_Multiply(ctx,", generated)
        self.assertIn("HPy_MatrixMultiply(ctx,", generated)
        self.assertIn("HPy_TrueDivide(ctx,", generated)
        self.assertIn("HPy_FloorDivide(ctx,", generated)
        self.assertIn("HPy_Remainder(ctx,", generated)
        self.assertIn("HPy_Lshift(ctx,", generated)
        self.assertIn("HPy_Rshift(ctx,", generated)
        self.assertIn("HPy_And(ctx,", generated)
        self.assertIn("HPy_Xor(ctx,", generated)
        self.assertIn("HPy_Or(ctx,", generated)
        self.assertIn("HPy_Power(ctx,", generated)
        self.assertIn("ctx->h_None)", generated)
        add_start = generated.index("static HPy __pyx_hpy_def_0_add_impl")
        add_impl = generated[add_start:generated.index("static HPy", add_start + 1)]
        self.assertIn("HPy_Add(ctx, args[0], args[1])", add_impl)
        self.assertNotIn("HPy_Dup", add_impl)
        self.assertNotIn("HPy_Close", add_impl)

    def test_binary_borrowing_preserves_side_effectful_evaluation_order(self):
        result, generated, diagnostics = self.compile_source(
            "def left_then_call(left, make, /):\n"
            "    return left + make()\n\n"
            "def call_then_right(make, right, /):\n"
            "    return make() + right\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        left_start = generated.index("left_then_call_impl")
        left_end = generated.index("static HPy", left_start + 1)
        left_impl = generated[left_start:left_end]
        left_dup = left_impl.index("HPy_Dup(ctx, args[0])")
        right_call = left_impl.index("HPy_Call(ctx, args[1]")
        add_call = left_impl.index("HPy_Add(ctx,")
        self.assertLess(left_dup, right_call)
        self.assertLess(right_call, add_call)

        right_start = generated.index("call_then_right_impl")
        right_end = generated.index("HPyDef_SLOT", right_start)
        right_impl = generated[right_start:right_end]
        self.assertIn("HPy_Add(ctx, __pyx_hpy_temp_0, args[1])", right_impl)
        self.assertNotIn("HPy_Dup(ctx, args[1])", right_impl)

    def test_fixed_sequence_builder_borrows_direct_name_items(self):
        result, generated, diagnostics = self.compile_source(
            "def pair(left, right, /):\n"
            "    return [left, right]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        start = generated.index("pair_impl")
        implementation = generated[start:generated.index("HPyDef_SLOT", start)]
        self.assertIn(
            "HPyListBuilder_Set(ctx, __pyx_hpy_builder_0, 0, args[0])",
            implementation,
        )
        self.assertIn(
            "HPyListBuilder_Set(ctx, __pyx_hpy_builder_0, 1, args[1])",
            implementation,
        )
        self.assertNotIn("HPy_Dup", implementation)
        self.assertNotIn("HPy_Close", implementation)

    def test_rich_comparisons_return_owned_boolean_handles(self):
        result, generated, diagnostics = self.compile_source(
            "def equal(left, right, /):\n"
            "    return left == right\n\n"
            "def less(left, right, /):\n"
            "    return left < right\n\n"
            "def greater_equal(left, right, /):\n"
            "    return left >= right\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_RichCompare(ctx,", generated)
        self.assertIn("HPy_EQ", generated)
        self.assertIn("HPy_LT", generated)
        self.assertIn("HPy_GE", generated)

    def test_unary_number_operations_close_owned_operand(self):
        result, generated, diagnostics = self.compile_source(
            "def positive(value, /):\n"
            "    return +value\n\n"
            "def negative(value, /):\n"
            "    return -value\n\n"
            "def invert(value, /):\n"
            "    return ~value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Positive(ctx,", generated)
        self.assertIn("HPy_Negative(ctx,", generated)
        self.assertIn("HPy_Invert(ctx,", generated)
        negative_call = generated.index("HPy_Negative(ctx,")
        self.assertLess(
            negative_call, generated.index("HPy_Close(ctx,", negative_call))

    def test_boolean_operations_short_circuit_with_owned_result(self):
        result, generated, diagnostics = self.compile_source(
            "def choose_and(left, right, /):\n"
            "    return left and right\n\n"
            "def choose_or(left, right, /):\n"
            "    return left or right\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count("HPy_IsTrue(ctx,"), 2)
        self.assertIn("= HPy_NULL;", generated)
        self.assertIn("HPy_Dup(ctx,", generated)
        truth_test = generated.index("HPy_IsTrue(ctx,")
        self.assertLess(
            truth_test, generated.index("if (__pyx_hpy_truth_", truth_test))

    def test_boolean_not_checks_truth_status_and_duplicates_boolean(self):
        result, generated, diagnostics = self.compile_source(
            "def negate(value, /):\n"
            "    return not value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_IsTrue(ctx,", generated)
        self.assertIn("if (__pyx_hpy_truth_0 < 0)", generated)
        self.assertIn("ctx->h_False : ctx->h_True", generated)
        self.assertIn("HPy_Dup(ctx,", generated)

    def test_cascaded_comparisons_short_circuit_and_reuse_middle_operand(self):
        result, generated, diagnostics = self.compile_source(
            "def ordered(first, middle, last, /):\n"
            "    return first < middle < last\n\n"
            "def same_and_contained(first, middle, container, /):\n"
            "    return first is middle in container\n\n"
            "def called(first, middle, last, /):\n"
            "    return first() < middle() < last()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertGreaterEqual(generated.count("HPy_RichCompare(ctx,"), 4)
        self.assertIn("HPy_Is(ctx,", generated)
        self.assertIn("HPy_Contains(ctx,", generated)
        self.assertGreaterEqual(generated.count("HPy_IsTrue(ctx,"), 3)
        self.assertIn("if (!HPy_IsNull(", generated)

    def test_inplace_operations_cover_locals_attributes_and_items(self):
        operations = (
            ("add", "+", "HPy_InPlaceAdd"),
            ("subtract", "-", "HPy_InPlaceSubtract"),
            ("multiply", "*", "HPy_InPlaceMultiply"),
            ("matrix", "@", "HPy_InPlaceMatrixMultiply"),
            ("true_divide", "/", "HPy_InPlaceTrueDivide"),
            ("floor_divide", "//", "HPy_InPlaceFloorDivide"),
            ("remainder", "%", "HPy_InPlaceRemainder"),
            ("power", "**", "HPy_InPlacePower"),
            ("left_shift", "<<", "HPy_InPlaceLshift"),
            ("right_shift", ">>", "HPy_InPlaceRshift"),
            ("and", "&", "HPy_InPlaceAnd"),
            ("xor", "^", "HPy_InPlaceXor"),
            ("or", "|", "HPy_InPlaceOr"),
        )
        source = []
        for name, operator, _ in operations:
            source.extend((
                "def inplace_%s(left, right, /):" % name,
                "    left %s= right" % operator,
                "    return left",
                "",
            ))
        source.extend((
            "def inplace_attribute(obj, right, /):",
            "    obj.value += right",
            "    return obj",
            "",
            "def inplace_item(obj, key, right, /):",
            "    obj[key] += right",
            "    return obj",
        ))
        result, generated, diagnostics = self.compile_source("\n".join(source))
        self.assertEqual(result.num_errors, 0, diagnostics)
        for _, _, function in operations:
            self.assertIn("%s(ctx," % function, generated)
        self.assertIn("HPy_GetAttr_s(ctx,", generated)
        self.assertIn("HPy_SetAttr_s(ctx,", generated)
        self.assertIn("HPy_GetItem(ctx,", generated)
        self.assertIn("HPy_SetItem(ctx,", generated)
        self.assertIn("HPy_InPlacePower(ctx,", generated)
        self.assertIn("ctx->h_None", generated)

    def test_identity_comparisons_duplicate_context_boolean(self):
        result, generated, diagnostics = self.compile_source(
            "def same(left, right, /):\n"
            "    return left is right\n\n"
            "def different(left, right, /):\n"
            "    return left is not right\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Is(ctx,", generated)
        self.assertIn("!(HPy_Is(ctx,", generated)
        self.assertIn("? ctx->h_True : ctx->h_False", generated)

    def test_membership_comparisons_check_negative_status(self):
        result, generated, diagnostics = self.compile_source(
            "def contains(key, container, /):\n"
            "    return key in container\n\n"
            "def excludes(key, container, /):\n"
            "    return key not in container\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Contains(ctx,", generated)
        self.assertIn("if (__pyx_hpy_contains_0 < 0)", generated)
        self.assertIn("!__pyx_hpy_contains_0 ?", generated)

    def test_every_unsupported_bootstrap_shape_is_diagnosed(self):
        cases = (
            (
                "annotation",
                "def answer() -> object:\n    return 1\n",
                "return annotations are not implemented",
            ),
            (
                "return-value",
                "def answer():\n    return {1}\n",
                "HPy 0.9 exposes neither public set construction/add operations",
            ),
            (
                "duplicate",
                "def answer():\n    return 1\n\n"
                "def answer():\n    return 2\n",
                "duplicate function names are not implemented",
            ),
            (
                "module-statement",
                "print(1)\n",
                "module-level ExprStatNode is not implemented",
            ),
        )
        for label, source, expected in cases:
            with self.subTest(label=label):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn("aHPy bootstrap backend:", diagnostics)
                self.assertIn(expected, diagnostics)

    def test_module_exec_uses_per_interpreter_namespace_for_globals_and_builtins(self):
        result, generated, diagnostics = self.compile_source(
            "import math\n"
            "from operator import add as operator_add\n"
            "GLOBAL_VALUE = {'answer': 42}\n\n"
            "def read_global():\n"
            "    return GLOBAL_VALUE\n\n"
            "def square_root(value, /):\n"
            "    return math.sqrt(value)\n\n"
            "def add_values(left, right, /):\n"
            "    return operator_add(left, right)\n\n"
            "def value_length(value, /):\n"
            "    return len(value)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyDef_SLOT(__pyx_hpy_mod_exec, HPy_mod_exec)", generated)
        self.assertIn(
            "static int __pyx_hpy_mod_exec_impl(HPyContext *ctx, HPy m)",
            generated,
        )
        self.assertIn('HPyImport_ImportModule(ctx, "builtins")', generated)
        self.assertIn('HPyImport_ImportModule(ctx, "math")', generated)
        self.assertIn('HPyImport_ImportModule(ctx, "operator")', generated)
        self.assertIn('HPy_GetAttr_s(ctx,', generated)
        self.assertIn(
            'HPy_SetAttr_s(ctx, m, "__pyx_hpy_builtins"', generated)
        self.assertIn(
            'HPy_GetAttr_s(ctx, self, "GLOBAL_VALUE")', generated)
        self.assertIn(
            'HPy_GetAttr_s(ctx, self, "__pyx_hpy_builtins")', generated)
        self.assertIn(".globals = NULL", generated)
        self.assertNotIn("HPyGlobal", generated)
        self.assertIn("return -1;", generated)
        self.assertIn(
            '(void)HPy_DelAttr_s(ctx, m, "read_global");', generated)
        self.assertIn(
            '(void)HPy_DelAttr_s(ctx, m, "value_length");', generated)
        self.assertIn("return 0;", generated)
        self.assertNotIn("PyObject", generated)

    def test_module_exec_rolls_back_successful_publications_in_reverse_order(self):
        result, generated, diagnostics = self.compile_source(
            "FIRST = (1,)\n"
            "SECOND = (2,)\n\n"
            "THIRD = (3,)\n\n"
            "def values():\n"
            "    return FIRST, SECOND, THIRD\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        third_publication = generated.index(
            'HPy_SetAttr_s(ctx, m, "THIRD"')
        third_failure = generated.index(
            "if (__pyx_hpy_status_", third_publication)
        third_failure_end = generated.index("return -1;", third_failure)
        cleanup = generated[third_failure:third_failure_end]
        second_delete = cleanup.index(
            '(void)HPy_DelAttr_s(ctx, m, "SECOND");')
        first_delete = cleanup.index(
            '(void)HPy_DelAttr_s(ctx, m, "FIRST");')
        self.assertLess(second_delete, first_delete)
        self.assertEqual(
            cleanup.count('(void)HPy_DelAttr_s(ctx, m, "FIRST");'), 1)

    def test_module_exec_preserves_non_memory_import_errors(self):
        result, generated, diagnostics = self.compile_source(
            "from ahpy_retry_dependency import VALUE\n\n"
            "def dependency_value():\n"
            "    return VALUE\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        import_call = generated.index(
            'HPyImport_ImportModule(ctx, "ahpy_retry_dependency")')
        failure = generated.index("if (HPy_IsNull(", import_call)
        next_statement = generated.index("HPy_GetAttr_s(ctx,", failure)
        cleanup = generated[failure:next_statement]
        memory_branch_end = cleanup.index("HPyErr_NoMemory(ctx);")
        non_memory_exit = cleanup[memory_branch_end:]
        self.assertIn("return -1;", non_memory_exit)
        self.assertNotIn("HPy_DelAttr_s", non_memory_exit)

    def test_fieldless_methodless_cdef_class_uses_pure_hpy_type_spec(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Marker:\n"
            "    pass\n\n"
            "def make_marker():\n"
            "    return Marker()\n\n"
            "def marker_type():\n"
            "    return Marker\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyType_HELPERS(__pyx_hpy_type_Marker_object)", generated)
        self.assertIn("static HPyType_Spec __pyx_hpy_type_Marker_spec", generated)
        self.assertIn(".builtin_shape = SHAPE(__pyx_hpy_type_Marker_object)", generated)
        self.assertIn(
            "HPyType_FromSpec(ctx, &__pyx_hpy_type_Marker_spec, NULL)",
            generated,
        )
        self.assertIn('HPy_SetAttr_s(ctx, m, "Marker",', generated)
        self.assertIn('HPy_GetAttr_s(ctx, self, "Marker")', generated)
        self.assertNotIn("PyObject_HEAD", generated)
        self.assertNotIn("static PyType_Spec ", generated)

    def test_object_fields_use_subinterpreter_safe_hpyfield_getsets(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Box:\n"
            "    cdef public object value\n"
            "    cdef readonly object label\n"
            "    cdef object hidden\n\n"
            "def make_box():\n"
            "    return Box()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count("HPyField __pyx_hpy_field_"), 3)
        self.assertIn("HPyDef_SLOT(__pyx_hpy_type_Box_traverse, HPy_tp_traverse)", generated)
        self.assertEqual(generated.count("HPy_VISIT(&self->__pyx_hpy_field_"), 3)
        self.assertIn("HPyDef_GETSET(", generated)
        self.assertIn("HPyDef_GET(", generated)
        self.assertNotIn("HPyMember_OBJECT", generated)
        self.assertIn("HPyField_IsNull(data->", generated)
        self.assertIn("HPyField_Load(ctx, self, data->", generated)
        self.assertIn("HPyField_Store(ctx, self, &data->", generated)
        self.assertIn("value = ctx->h_None;", generated)
        self.assertEqual(generated.count('"value"'), 1)
        self.assertEqual(generated.count('"label"'), 1)
        self.assertNotIn('HPyDef_GETSET(__pyx_hpy_type_Box_member_2', generated)
        self.assertIn("HPy_TPFLAGS_HAVE_GC", generated)
        self.assertIn("#include <stddef.h>", generated)
        self.assertNotIn("PyObject_HEAD", generated)

    def test_native_int_and_double_fields_use_exact_member_layouts(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NumericBox:\n"
            "    cdef public int count\n"
            "    cdef public double ratio\n"
            "    cdef readonly int frozen\n\n"
            "def make_numeric_box():\n"
            "    return NumericBox()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("int __pyx_hpy_field_0_", generated)
        self.assertIn("double __pyx_hpy_field_1_", generated)
        self.assertIn('"count", HPyMember_INT', generated)
        self.assertIn('"ratio", HPyMember_DOUBLE', generated)
        self.assertIn('"frozen", HPyMember_INT', generated)
        self.assertNotIn("HPyField __pyx_hpy_field_", generated)
        self.assertNotIn("HPy_tp_traverse", generated)
        self.assertNotIn("HPy_TPFLAGS_HAVE_GC", generated)

    def test_methods_read_and_write_native_int_and_double_fields(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NumericBox:\n"
            "    cdef public int count\n"
            "    cdef double hidden_ratio\n\n"
            "    def read_count(self):\n"
            "        return self.count\n\n"
            "    def write_count(self, value, /):\n"
            "        self.count = value\n"
            "        return self.count\n\n"
            "    def read_hidden_ratio(self):\n"
            "        return self.hidden_ratio\n\n"
            "    def write_hidden_ratio(self, value, /):\n"
            "        self.hidden_ratio = value\n"
            "        return self.hidden_ratio\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyLong_FromLongLong(ctx,", generated)
        self.assertIn("HPyLong_AsLong(ctx,", generated)
        self.assertIn("HPyFloat_FromDouble(ctx,", generated)
        self.assertIn("HPyFloat_AsDouble(ctx,", generated)
        self.assertIn("HPyErr_Occurred(ctx)", generated)
        self.assertIn("INT_MIN", generated)
        self.assertIn("INT_MAX", generated)
        self.assertNotIn('HPy_GetAttr_s(ctx, self, "hidden_ratio")', generated)
        self.assertNotIn('HPy_SetAttr_s(ctx, self, "hidden_ratio"', generated)

    def test_remaining_exact_hpy_native_member_kinds(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NativeMembers:\n"
            "    cdef public signed char sbyte\n"
            "    cdef public unsigned char ubyte\n"
            "    cdef public short short_value\n"
            "    cdef public unsigned short ushort_value\n"
            "    cdef public unsigned int uint_value\n"
            "    cdef public long long_value\n"
            "    cdef public unsigned long ulong_value\n"
            "    cdef public long long longlong_value\n"
            "    cdef public unsigned long long ulonglong_value\n"
            "    cdef public float float_value\n\n"
            "    def values(self):\n"
            "        return [self.sbyte, self.ubyte, self.short_value, "
            "self.ushort_value, self.uint_value, self.long_value, "
            "self.ulong_value, self.longlong_value, self.ulonglong_value, "
            "self.float_value]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        for member_kind in (
            "HPyMember_BYTE", "HPyMember_UBYTE", "HPyMember_SHORT",
            "HPyMember_USHORT", "HPyMember_UINT", "HPyMember_LONG",
            "HPyMember_ULONG", "HPyMember_LONGLONG",
            "HPyMember_ULONGLONG", "HPyMember_FLOAT",
        ):
            self.assertIn(member_kind, generated)
        self.assertIn("HPyLong_FromUnsignedLongLong(ctx,", generated)
        self.assertIn("HPyFloat_FromDouble(ctx,", generated)

    def test_bint_fields_use_char_bool_members_and_truth_conversion(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Flags:\n"
            "    cdef public bint enabled\n"
            "    cdef bint hidden\n"
            "    cdef readonly bint frozen\n\n"
            "    def __init__(self, enabled):\n"
            "        self.enabled = enabled\n\n"
            "    def read_hidden(self):\n"
            "        return self.hidden\n\n"
            "    def write_hidden(self, value, /):\n"
            "        self.hidden = value\n"
            "        return self.hidden\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("char __pyx_hpy_field_", generated)
        self.assertIn("HPyMember_BOOL", generated)
        self.assertIn("HPy_IsTrue(ctx,", generated)
        self.assertIn("ctx->h_True", generated)
        self.assertIn("ctx->h_False", generated)
        self.assertNotIn("HPy_tp_traverse", generated)
        self.assertNotIn("HPy_TPFLAGS_HAVE_GC", generated)

    def test_py_ssize_t_fields_use_exact_hpy_ssize_member(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Sizes:\n"
            "    cdef public Py_ssize_t size\n"
            "    cdef Py_ssize_t hidden\n"
            "    cdef readonly Py_ssize_t frozen\n\n"
            "    def __init__(self, size):\n"
            "        self.size = size\n\n"
            "    def read_hidden(self):\n"
            "        return self.hidden\n\n"
            "    def write_hidden(self, value, /):\n"
            "        self.hidden = value\n"
            "        return self.hidden\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_ssize_t __pyx_hpy_field_", generated)
        self.assertIn("HPyMember_HPYSSIZET", generated)
        self.assertIn("HPyLong_AsSsize_t(ctx,", generated)
        self.assertIn("HPyLong_FromLongLong(ctx,", generated)
        self.assertNotIn("HPy_tp_traverse", generated)

    def test_plain_char_fields_preserve_member_and_direct_access_semantics(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Characters:\n"
            "    cdef public char letter\n"
            "    cdef char hidden\n"
            "    cdef readonly char frozen\n\n"
            "    def __init__(self, letter):\n"
            "        self.letter = letter\n\n"
            "    def read_letter(self):\n"
            "        return self.letter\n\n"
            "    def write_hidden(self, value, /):\n"
            "        self.hidden = value\n"
            "        return self.hidden\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("char __pyx_hpy_field_", generated)
        self.assertIn("HPyMember_CHAR", generated)
        self.assertIn("HPyLong_AsLong(ctx,", generated)
        self.assertIn("CHAR_MIN", generated)
        self.assertIn("CHAR_MAX", generated)
        self.assertIn("HPyLong_FromLongLong(ctx,", generated)
        self.assertNotIn("HPy_tp_traverse", generated)

    def test_local_scalar_typedef_fields_resolve_to_exact_base_storage(self):
        result, generated, diagnostics = self.compile_source(
            "ctypedef unsigned short Code\n\n"
            "cdef class Codes:\n"
            "    cdef public Code value\n"
            "    cdef Code hidden\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def write_hidden(self, value, /):\n"
            "        self.hidden = value\n"
            "        return self.hidden\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("unsigned short __pyx_hpy_field_", generated)
        self.assertIn("HPyMember_USHORT", generated)
        self.assertIn("USHRT_MAX", generated)
        self.assertIn("HPyLong_FromUnsignedLongLong(ctx,", generated)

    def test_external_typedef_fields_remain_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"external_count.h\":\n"
            "    ctypedef int ExternalCount\n\n"
            "cdef class Counts:\n"
            "    cdef ExternalCount value\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "typedefs, variables, structs, unions, and enums remain ABI-owned",
            diagnostics,
        )

    def test_python_independent_parameterless_external_c_scalars(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"ahpy_external.h\":\n"
            "    long long ahpy_signed_answer()\n"
            "    unsigned long long ahpy_unsigned_answer()\n"
            "    double ahpy_ratio()\n"
            "    bint ahpy_ready()\n\n"
            "def signed_answer():\n"
            "    return ahpy_signed_answer()\n\n"
            "def unsigned_answer():\n"
            "    return ahpy_unsigned_answer()\n\n"
            "def ratio():\n"
            "    return ahpy_ratio()\n\n"
            "def ready():\n"
            "    return ahpy_ready()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count('#include "ahpy_external.h"'), 1)
        self.assertIn(
            "HPyLong_FromLongLong(ctx, ahpy_signed_answer())", generated)
        self.assertIn(
            "HPyLong_FromUnsignedLongLong(ctx, ahpy_unsigned_answer())",
            generated,
        )
        self.assertIn("HPyFloat_FromDouble(ctx, ahpy_ratio())", generated)
        self.assertIn("ahpy_ready() ? ctx->h_True : ctx->h_False", generated)
        self.assertNotIn("Python.h", generated)

    def test_system_style_external_header_is_emitted_with_angle_brackets(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"<math.h>\":\n"
            "    double fabs(double value)\n\n"
            "def absolute(value):\n"
            "    return fabs(value)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("#include <math.h>", generated)

    def test_external_c_scalar_arguments_use_checked_hpy_conversions(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"math.h\":\n"
            "    double fabs(double value)\n\n"
            "def absolute(value):\n"
            "    return fabs(value)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyFloat_AsDouble(ctx,", generated)
        self.assertIn("HPyFloat_FromDouble(ctx, fabs(", generated)
        self.assertNotIn("Python.h", generated)

    def test_external_c_scalar_literals_bypass_hpy_round_trip(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"portable_scalars.h\":\n"
            "    long long add(long long left, long long right)\n"
            "    unsigned long long keep(unsigned long long value)\n"
            "    double scale(double value)\n"
            "    bint choose(bint value)\n\n"
            "def added():\n"
            "    return add(20, 22)\n\n"
            "def minimum():\n"
            "    return add(-9223372036854775808, 0)\n\n"
            "def unsigned_maximum():\n"
            "    return keep(18446744073709551615)\n\n"
            "def scaled():\n"
            "    return scale(1.25)\n\n"
            "def chosen():\n"
            "    return choose(True)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "add(((long long)20LL), ((long long)22LL))", generated)
        self.assertIn(
            "add(((long long)(-9223372036854775807LL - 1LL)), "
            "((long long)0LL))",
            generated,
        )
        self.assertIn(
            "keep(((unsigned long long)18446744073709551615ULL))",
            generated,
        )
        self.assertIn("scale(((double)1.25))", generated)
        self.assertIn("choose(1)", generated)

        self.assertNotIn("HPyLong_As", generated)
        self.assertNotIn("HPyFloat_As", generated)

    def test_external_c_out_of_portable_range_keeps_checked_conversion(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"portable_scalars.h\":\n"
            "    long keep_long(long value)\n\n"
            "def too_wide_for_portable_long():\n"
            "    return keep_long(4294967296)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyLong_AsLong(ctx,", generated)
        self.assertNotIn("keep_long(((long)4294967296", generated)

    def test_argumentless_noexcept_external_c_call_can_run_with_nogil(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"worker.h\":\n"
            "    long tick() noexcept nogil\n\n"
            "def run():\n"
            "    with nogil:\n"
            "        tick()\n"
            "    return 1\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyThreadState __pyx_hpy_thread_state_0", generated)
        self.assertIn(
            "HPy_LeavePythonExecution(ctx)", generated)
        self.assertIn("(void)tick();", generated)
        self.assertIn(
            "HPy_ReenterPythonExecution(ctx, __pyx_hpy_thread_state_0)",
            generated,
        )
        self.assertNotIn("PyThreadState *", generated)

    def test_nogil_external_c_arguments_are_preconverted_before_leave(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"worker.h\":\n"
            "    long tick(long value) noexcept nogil\n\n"
            "def run(value, /):\n"
            "    with nogil:\n"
            "        tick(1)\n"
            "        tick(value)\n"
            "    return 1\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        first_leave = generated.index("HPy_LeavePythonExecution(ctx)")
        literal_call = generated.index("(void)tick(((long)1));", first_leave)
        first_reenter = generated.index(
            "HPy_ReenterPythonExecution(ctx,", literal_call)
        conversion = generated.index("HPyLong_AsLong(ctx,", first_reenter)
        close = generated.index("HPy_Close(ctx,", conversion)
        second_leave = generated.index(
            "HPy_LeavePythonExecution(ctx)", close)
        converted_call = generated.index(
            "(void)tick((long)__pyx_hpy_native_long_", second_leave)
        second_reenter = generated.index(
            "HPy_ReenterPythonExecution(ctx,", converted_call)
        self.assertLess(first_leave, literal_call)
        self.assertLess(literal_call, first_reenter)
        self.assertLess(first_reenter, conversion)
        self.assertLess(conversion, close)
        self.assertLess(close, second_leave)
        self.assertLess(second_leave, converted_call)
        self.assertLess(converted_call, second_reenter)

    def test_nogil_external_c_result_is_boxed_only_after_reentry(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"worker.h\":\n"
            "    long tick(long value) noexcept nogil\n\n"
            "def run(value, /):\n"
            "    with nogil:\n"
            "        result = tick(value)\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        conversion = generated.index("HPyLong_AsLong(ctx,")
        close = generated.index("HPy_Close(ctx,", conversion)
        native_declaration = generated.index(
            "long __pyx_hpy_nogil_result_", close)
        leave = generated.index(
            "HPy_LeavePythonExecution(ctx)", native_declaration)
        native_call = generated.index(
            "= tick((long)__pyx_hpy_native_long_", leave)
        reenter = generated.index(
            "HPy_ReenterPythonExecution(ctx,", native_call)
        box = generated.index("HPyLong_FromLongLong(ctx,", reenter)
        self.assertLess(conversion, close)
        self.assertLess(close, native_declaration)
        self.assertLess(native_declaration, leave)
        self.assertLess(leave, native_call)
        self.assertLess(native_call, reenter)
        self.assertLess(reenter, box)

    def test_nogil_external_c_results_assign_supported_targets_after_reentry(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"worker.h\":\n"
            "    long tick(long value) noexcept nogil\n\n"
            "stored = 0\n\n"
            "def run(obj, mapping, /):\n"
            "    global stored\n"
            "    with nogil:\n"
            "        stored = tick(obj.amount)\n"
            "        obj.value = tick(mapping[0])\n"
            "        mapping[0] = tick(3)\n"
            "        mapping[1:2] = tick(4)\n"
            "    return stored, obj.value, mapping[0], mapping[1:2]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        first_argument = generated.index(
            'HPy_GetAttr_s(ctx, args[0], "amount")'
        )
        first_call = generated.index("= tick(", first_argument)
        first_leave = generated.rindex(
            "HPy_LeavePythonExecution(ctx)", first_argument, first_call
        )
        first_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", first_call)
        global_store = generated.index(
            'HPy_SetAttr_s(ctx, self, "stored"', first_reentry)
        second_argument = generated.index("HPy_GetItem(ctx,", global_store)
        second_call = generated.index("= tick(", second_argument)
        second_leave = generated.rindex(
            "HPy_LeavePythonExecution(ctx)", second_argument, second_call
        )
        second_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", second_call)
        attribute_store = generated.index(
            'HPy_SetAttr_s(ctx,', second_reentry)
        third_call = generated.index("= tick(((long)3));", attribute_store)
        third_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", third_call)
        item_store = generated.index("HPy_SetItem(ctx,", third_reentry)
        fourth_call = generated.index("= tick(((long)4));", item_store)
        fourth_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", fourth_call)
        slice_key = generated.index(
            "HPy_Call(ctx, ctx->h_SliceType", fourth_reentry
        )
        slice_store = generated.index("HPy_SetItem(ctx,", item_store + 1)
        self.assertLess(first_argument, first_leave)
        self.assertLess(first_leave, first_call)
        self.assertLess(first_call, first_reentry)
        self.assertLess(first_reentry, global_store)
        self.assertLess(global_store, second_call)
        self.assertLess(second_argument, second_leave)
        self.assertLess(second_leave, second_call)
        self.assertLess(second_call, second_reentry)
        self.assertLess(second_reentry, attribute_store)
        self.assertLess(attribute_store, third_call)
        self.assertLess(third_call, third_reentry)
        self.assertLess(third_reentry, item_store)
        self.assertLess(item_store, fourth_call)
        self.assertLess(fourth_call, fourth_reentry)
        self.assertLess(fourth_reentry, slice_key)
        self.assertLess(slice_key, slice_store)

        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"worker.h\":\n"
            "    long tick() noexcept nogil\n\n"
            "def run():\n"
            "    with nogil:\n"
            "        left, right = tick()\n"
            "    return left, right\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "Constructing Python tuple not allowed without gil",
            diagnostics,
        )

    def test_nogil_external_c_allows_explicit_with_gil_islands(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"worker.h\":\n"
            "    long tick(long value) noexcept nogil\n\n"
            "def run(callback, /):\n"
            "    with nogil:\n"
            "        before = tick(1)\n"
            "        with gil:\n"
            "            amount = callback(before)\n"
            "        after = tick(amount)\n"
            "    return before, amount, after\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        first_leave = generated.index("HPy_LeavePythonExecution(ctx)")
        first_call = generated.index("= tick(((long)1));", first_leave)
        first_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", first_call)
        gil_marker = generated.index(
            "explicit with gil: Python execution is active", first_reentry)
        callback_call = generated.index("HPy_Call(ctx,", gil_marker)
        conversion = generated.index("HPyLong_AsLong(ctx,", callback_call)
        second_leave = generated.index(
            "HPy_LeavePythonExecution(ctx)", conversion)
        second_call = generated.index("= tick(", second_leave)
        second_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", second_call)
        self.assertLess(first_leave, first_call)
        self.assertLess(first_call, first_reentry)
        self.assertLess(first_reentry, gil_marker)
        self.assertLess(gil_marker, callback_call)
        self.assertLess(callback_call, conversion)
        self.assertLess(conversion, second_leave)
        self.assertLess(second_leave, second_call)
        self.assertLess(second_call, second_reentry)

    def test_nogil_external_c_rejects_implicit_conditional_and_empty_gil_islands(self):
        sources = (
            (
                "conditional",
                "cdef extern from \"worker.h\":\n"
                "    long tick() noexcept nogil\n\n"
                "def run(flag, /):\n"
                "    with nogil:\n"
                "        tick()\n"
                "        with gil(flag):\n"
                "            value = 1\n"
                "    return value\n",
                "Non-constant condition in a `with gil(<condition>)` statement",
            ),
            (
                "empty",
                "cdef extern from \"worker.h\":\n"
                "    long tick() noexcept nogil\n\n"
                "def run():\n"
                "    with nogil:\n"
                "        tick()\n"
                "        with gil:\n"
                "            pass\n"
                "    return 1\n",
                "empty nested with gil blocks are not part",
            ),
        )
        for feature, source, expected in sources:
            with self.subTest(feature=feature):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(expected, diagnostics)

    def test_external_c_errno_sentinel_checks_after_native_calls(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"worker.h\":\n"
            "    long fail(long value) except -1 nogil\n\n"
            "def held(value, /):\n"
            "    return fail(value)\n\n"
            "def released(value, /):\n"
            "    with nogil:\n"
            "        result = fail(value)\n"
            "    return result\n\n"
            "def discarded():\n"
            "    with nogil:\n"
            "        fail(1)\n"
            "    return 1\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("#include <errno.h>", generated)

        held_reset = generated.index("errno = 0;")
        held_call = generated.index("= fail(", held_reset)
        held_save = generated.index("= errno;", held_call)
        held_check = generated.index("== ((long)-1)", held_save)
        held_os_error = generated.index(
            "HPyErr_SetFromErrno(ctx, ctx->h_OSError)", held_check)
        held_runtime_error = generated.index(
            "returned its -1 error sentinel without setting errno", held_check)
        held_box = generated.index("HPyLong_FromLongLong(ctx,", held_runtime_error)
        self.assertLess(held_reset, held_call)
        self.assertLess(held_call, held_save)
        self.assertLess(held_save, held_check)
        self.assertLess(held_check, held_os_error)
        self.assertLess(held_os_error, held_runtime_error)
        self.assertLess(held_runtime_error, held_box)

        released_leave = generated.index(
            "HPy_LeavePythonExecution(ctx)", held_box)
        released_reset = generated.index("errno = 0;", released_leave)
        released_call = generated.index("= fail(", released_reset)
        released_save = generated.index("= errno;", released_call)
        released_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", released_save)
        released_check = generated.index("== ((long)-1)", released_reentry)
        released_os_error = generated.index(
            "HPyErr_SetFromErrno(ctx, ctx->h_OSError)", released_check)
        released_box = generated.index(
            "HPyLong_FromLongLong(ctx,", released_os_error)
        self.assertLess(released_leave, released_reset)
        self.assertLess(released_reset, released_call)
        self.assertLess(released_call, released_save)
        self.assertLess(released_save, released_reentry)
        self.assertLess(released_reentry, released_check)
        self.assertLess(released_check, released_os_error)
        self.assertLess(released_os_error, released_box)

        discarded_leave = generated.index(
            "HPy_LeavePythonExecution(ctx)", released_box)
        discarded_call = generated.index("= fail(((long)1));", discarded_leave)
        discarded_reentry = generated.index(
            "HPy_ReenterPythonExecution(ctx,", discarded_call)
        discarded_check = generated.index("== ((long)-1)", discarded_reentry)
        self.assertLess(discarded_leave, discarded_call)
        self.assertLess(discarded_call, discarded_reentry)
        self.assertLess(discarded_reentry, discarded_check)

    def test_external_c_errno_contract_rejects_ambiguous_forms(self):
        sources = (
            (
                "checked",
                "cdef extern from \"worker.h\":\n"
                "    int fail() except? -1 nogil\n",
                "exception checks require Python exception state",
            ),
            (
                "other-sentinel",
                "cdef extern from \"worker.h\":\n"
                "    int fail() except 0 nogil\n",
                "require a signed integer result and exact except -1",
            ),
            (
                "unsigned",
                "cdef extern from \"worker.h\":\n"
                "    unsigned int fail() except -1 nogil\n",
                "require a signed integer result and exact except -1",
            ),
        )
        for feature, source, expected in sources:
            with self.subTest(feature=feature):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(expected, diagnostics)

    def test_empty_nogil_transition_is_fail_closed(self):
        result, generated, diagnostics = self.compile_source(
            "def run():\n"
            "    with nogil:\n"
            "        pass\n"
            "    return 1\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "empty with nogil blocks are not part of the initial",
            diagnostics,
        )

    def test_parallel_constructs_have_hpy09_worker_contract_diagnostic(self):
        sources = (
            (
                "prange",
                "from cython.parallel cimport prange\n\n"
                "def work():\n"
                "    cdef int i\n"
                "    for i in prange(4, nogil=True):\n"
                "        pass\n"
                "    return 4\n",
            ),
            (
                "parallel",
                "from cython.parallel cimport parallel\n\n"
                "def work():\n"
                "    with nogil, parallel():\n"
                "        pass\n"
                "    return 1\n",
            ),
        )
        for feature, source in sources:
            with self.subTest(feature=feature):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(
                    "public HPy worker-thread attach and error-transport",
                    diagnostics,
                )
                self.assertIn("HPy 0.9 only pairs Leave/Reenter", diagnostics)
                self.assertIn(
                    "CPython PyThreadState/exception triples are forbidden",
                    diagnostics,
                )

    def test_external_c_variadic_arguments_remain_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"stdio.h\":\n"
            "    int printf(const char *format, ...)\n\n"
            "def emit():\n"
            "    return printf(b\"value\")\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("variadic or optional C function parameters", diagnostics)

    def test_external_c_pointer_result_remains_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"external.h\":\n"
            "    const char *ahpy_name()\n\n"
            "def name():\n"
            "    return ahpy_name()\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("only direct function declarations", diagnostics)

    def test_external_c_requires_concrete_non_python_header(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from *:\n"
            "    long ahpy_answer()\n\n"
            "def answer():\n"
            "    return ahpy_answer()\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("require a concrete header", diagnostics)

        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"Python.h\":\n"
            "    long ahpy_answer()\n\n"
            "def answer():\n"
            "    return ahpy_answer()\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("CPython C API", diagnostics)

    def test_external_c_rejects_python_owned_ssize_type(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"external.h\":\n"
            "    Py_ssize_t ahpy_size(Py_ssize_t value)\n\n"
            "def size(value):\n"
            "    return ahpy_size(value)\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("external C parameters must be direct supported", diagnostics)

    def test_external_c_rejects_verbatim_and_unsafe_headers(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"external.h\":\n"
            "    \"\"\"#define AHPY_INJECTED 1\"\"\"\n"
            "    long ahpy_answer()\n\n"
            "def answer():\n"
            "    return ahpy_answer()\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("must not inject verbatim C code", diagnostics)

        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"bad\\\"header.h\":\n"
            "    long ahpy_answer()\n\n"
            "def answer():\n"
            "    return ahpy_answer()\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("literal safe path", diagnostics)

    def test_external_c_header_is_deduplicated_across_blocks(self):
        result, generated, diagnostics = self.compile_source(
            "cdef extern from \"external.h\":\n"
            "    long ahpy_first()\n\n"
            "cdef extern from \"external.h\":\n"
            "    long ahpy_second()\n\n"
            "def values():\n"
            "    return [ahpy_first(), ahpy_second()]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count('#include "external.h"'), 1)
        self.assertIn("ahpy_first()", generated)
        self.assertIn("ahpy_second()", generated)

    def test_enum_fields_are_rejected_without_guessing_int_storage(self):
        result, generated, diagnostics = self.compile_source(
            "cdef enum Status:\n"
            "    READY = 1\n"
            "    FAILED = 2\n\n"
            "cdef class StatusBox:\n"
            "    cdef Status value\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "C enum extension fields are not implemented in Universal HPy "
            "mode: compiler-selected enum layout must not be treated as a "
            "guessed C int/HPyMember_INT",
            diagnostics,
        )

    def test_long_double_fields_use_custom_hpy_getset_descriptors(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Precise:\n"
            "    cdef public long double value\n"
            "    cdef readonly long double frozen\n"
            "    cdef long double hidden\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def read_value(self):\n"
            "        return self.value\n\n"
            "    def write_hidden(self, value, /):\n"
            "        self.hidden = value\n"
            "        return self.hidden\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("long double __pyx_hpy_field_", generated)
        self.assertIn("HPyDef_GETSET(", generated)
        self.assertIn("HPyDef_GET(", generated)
        self.assertIn("HPyFloat_AsDouble(ctx,", generated)
        self.assertIn("HPyFloat_FromDouble(ctx,", generated)
        self.assertIn("(long double)", generated)
        self.assertIn("HPy_IsNull(value)", generated)
        self.assertNotIn("HPyMember_DOUBLE", generated)
        self.assertNotIn("HPy_tp_traverse", generated)

    def test_call_slot_uses_exact_hpy_keywords_signature_and_parser(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class CallableBox:\n"
            "    cdef object prefix\n\n"
            "    def __init__(self, prefix):\n"
            "        self.prefix = prefix\n\n"
            "    def __call__(self, left, /, right):\n"
            "        return [self.prefix, left, right]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyDef_SLOT(", generated)
        self.assertIn("HPy_tp_call", generated)
        self.assertIn("HPy_tp_new", generated)
        self.assertIn("HPy_New(ctx, type, &data)", generated)
        self.assertIn(
            "const HPy *args, size_t nargs, HPy kwnames)", generated)
        self.assertIn("HPyArg_ParseKeywordsDict(ctx,", generated)
        self.assertIn('"OO:__call__"', generated)
        self.assertNotIn('HPyDef_METH(', generated)

    def test_call_slot_without_initializer_rejects_constructor_arguments(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class CallableBox:\n"
            "    def __call__(self):\n"
            "        return self\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_new", generated)
        self.assertIn("HPy_Length(ctx, kw)", generated)
        self.assertIn('"CallableBox() takes no arguments"', generated)

    def test_call_slot_reuses_inherited_initializer_after_hpy_new(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Base:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "cdef class CallableDerived(Base):\n"
            "    def __call__(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_new", generated)
        self.assertIn("HPy_New(ctx, type, &data)", generated)
        self.assertNotIn('"CallableDerived() takes no arguments"', generated)

    def test_cinitializer_runs_from_tp_new_and_cleans_partial_objects(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class CInitBox:\n"
            "    cdef object value\n\n"
            "    def __cinit__(self, value):\n"
            "        self.value = value\n\n"
            "    def read(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_new", generated)
        self.assertIn(
            "HPy result = HPy_New(ctx, type, &data);", generated)
        self.assertIn(
            "__pyx_hpy_type_0_CInitBox_cinit_impl("
            "ctx, result, args, nargs, kw)",
            generated,
        )
        self.assertIn('"O:__cinit__"', generated)
        self.assertIn("HPy_Close(ctx, result);", generated)
        self.assertLess(
            generated.index("HPy_Close(ctx, result);"),
            generated.index("return HPy_NULL;", generated.index(
                "HPy_Close(ctx, result);")),
        )

    def test_cinitializer_inheritance_calls_base_before_derived(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class CInitBase:\n"
            "    cdef object base_value\n\n"
            "    def __cinit__(self, value):\n"
            "        self.base_value = value\n\n"
            "cdef class CInitDerived(CInitBase):\n"
            "    cdef object derived_value\n\n"
            "    def __cinit__(self, value):\n"
            "        self.derived_value = value\n\n"
            "    def values(self):\n"
            "        return [self.base_value, self.derived_value]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        derived_new = generated.index(
            "static HPy __pyx_hpy_type_1_CInitDerived_tp_new_impl")
        derived_new_end = generated.index("\n}", derived_new)
        derived_new_source = generated[derived_new:derived_new_end]
        base_call = derived_new_source.index(
            "__pyx_hpy_type_0_CInitBase_cinit_impl")
        derived_call = derived_new_source.index(
            "__pyx_hpy_type_1_CInitDerived_cinit_impl")
        self.assertLess(base_call, derived_call)
        self.assertEqual(derived_new_source.count("HPy_Close(ctx, result)"), 2)

    def test_cinitializer_and_initializer_have_separate_lifecycle_slots(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Constructed:\n"
            "    cdef object stages\n\n"
            "    def __cinit__(self, first, second):\n"
            "        self.stages = [first]\n\n"
            "    def __init__(self, first, second):\n"
            "        self.stages = self.stages + [second]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_new", generated)
        self.assertIn("HPy_tp_init", generated)
        self.assertIn('"OO:__cinit__"', generated)
        self.assertIn('"OO:__init__"', generated)

    def test_nullary_base_cinitializer_accepts_derived_constructor_arguments(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NullaryBase:\n"
            "    cdef object stage\n\n"
            "    def __cinit__(self):\n"
            "        self.stage = 'base'\n\n"
            "cdef class DerivedInit(NullaryBase):\n"
            "    def __init__(self, value):\n"
            "        self.stage = [self.stage, value]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        derived_new = generated.index(
            "static HPy __pyx_hpy_type_1_DerivedInit_tp_new_impl")
        derived_new_end = generated.index("\n}", derived_new)
        self.assertIn(
            "__pyx_hpy_type_0_NullaryBase_cinit_impl("
            "ctx, result, args, nargs, kw)",
            generated[derived_new:derived_new_end],
        )
        cinit_impl = generated.index(
            "static int __pyx_hpy_type_0_NullaryBase_cinit_impl(",
            derived_new_end,
        )
        cinit_impl_end = generated.index("\n}", cinit_impl)
        cinit_source = generated[cinit_impl:cinit_impl_end]
        self.assertIn("(void)args;", cinit_source)
        self.assertIn("(void)nargs;", cinit_source)
        self.assertIn("(void)kw;", cinit_source)
        self.assertNotIn("HPyArg_ParseKeywordsDict", cinit_source)

    def test_cinitializer_makes_callable_constructor_arguments_valid(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class CInitCallable:\n"
            "    cdef object value\n\n"
            "    def __cinit__(self, value):\n"
            "        self.value = value\n\n"
            "    def __call__(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_new", generated)
        self.assertIn("HPy_tp_call", generated)
        self.assertIn('"O:__cinit__"', generated)
        self.assertNotIn('"CInitCallable() takes no arguments"', generated)

    def test_cinitializer_defaults_are_owned_by_the_defining_type(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class CInitDefault:\n"
            "    cdef object value\n\n"
            "    def __cinit__(self, value=[83]):\n"
            "        self.value = value\n\n"
            "    def read(self):\n"
            "        return self.value\n\n"
            "cdef class DerivedCInitDefault(CInitDefault):\n"
            "    pass\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"|O:__cinit__"', generated)
        self.assertEqual(
            generated.count('HPy_SetAttr_s(ctx, m, "__pyx_hpy_default_'), 1)
        self.assertGreaterEqual(
            generated.count('"__pyx_hpy_default_0"'), 3)
        self.assertIn(
            "__pyx_hpy_type_0_CInitDefault_cinit_impl("
            "ctx, result, args, nargs, kw)",
            generated,
        )

    def test_deallocator_has_actionable_raw_storage_diagnostic(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NativeResource:\n"
            "    def __dealloc__(self):\n"
            "        pass\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("HPy_tp_destroy", diagnostics)
        self.assertIn("without HPyContext or an HPy self handle", diagnostics)
        self.assertIn("native-resource-only", diagnostics)

    def test_iterator_slots_have_actionable_hpy_09_api_diagnostic(self):
        for method_name in ("__iter__", "__next__"):
            with self.subTest(method_name=method_name):
                result, generated, diagnostics = self.compile_source(
                    "cdef class Iterator:\n"
                    "    def %s(self):\n"
                    "        return self\n" % method_name
                )
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn("HPy_tp_iter", diagnostics)
                self.assertIn("HPy_tp_iternext", diagnostics)
                self.assertIn("Universal ABI", diagnostics)

    def test_other_missing_hpy_09_slot_families_have_actionable_diagnostics(self):
        cases = (
            (
                "attribute",
                "    def __getattr__(self, name):\n"
                "        return name\n",
                "neither HPy_tp_getattro nor HPy_tp_setattro",
            ),
            (
                "descriptor",
                "    def __get__(self, instance, owner):\n"
                "        return self\n",
                "neither HPy_tp_descr_get nor HPy_tp_descr_set",
            ),
            (
                "async",
                "    def __aiter__(self):\n"
                "        return self\n",
                "no await/aiter/anext type slots",
            ),
        )
        for label, method, expected in cases:
            with self.subTest(label=label):
                result, generated, diagnostics = self.compile_source(
                    "cdef class ProtocolBox:\n" + method)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(expected, diagnostics)
                self.assertIn("Universal ABI", diagnostics)

    def test_custom_new_remains_frontend_rejected_before_hpy_allocation(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class CustomNew:\n"
            "    def __new__(cls):\n"
            "        return cls\n"
        )
        self.assertGreaterEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "__new__ method of extension type will change semantics",
            diagnostics,
        )
        self.assertIn("Use __cinit__ instead", diagnostics)

    def test_initializer_and_call_defaults_are_owned_by_the_type(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class DefaultCallable:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value=17):\n"
            "        self.value = value\n\n"
            "    def __call__(self, other=23):\n"
            "        return [self.value, other]\n\n"
            "    def choose(self, item=[29]):\n"
            "        return item\n\n"
            "    def keyword_default(self, first=31, *, named=37):\n"
            "        return [first, named]\n\n"
            "cdef class DerivedDefaultCallable(DefaultCallable):\n"
            "    def read(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"|O:__init__"', generated)
        self.assertIn('"|O:__call__"', generated)
        self.assertIn('"|O:choose"', generated)
        self.assertIn('"|OO:keyword_default"', generated)
        self.assertEqual(
            generated.count(
                'HPy_GetAttr_s(ctx, self, "__class__")'), 6)
        read_start = generated.index("_read_impl")
        read_impl = generated[read_start:generated.index("static int", read_start)]
        self.assertNotIn('HPy_GetAttr_s(ctx, self, "__class__")', read_impl)
        self.assertEqual(generated.count("HPy_tp_new"), 2)
        self.assertIn(
            ".flags = HPy_TPFLAGS_DEFAULT | HPy_TPFLAGS_BASETYPE | "
            "HPy_TPFLAGS_HAVE_GC,",
            generated,
        )
        self.assertIn(
            "__pyx_hpy_type_DefaultCallable_traverse_impl("
            "object, visit, arg)",
            generated,
        )
        self.assertNotIn(
            'HPy_GetAttr_s(ctx, __pyx_hpy_temp_0, "value")', generated)
        self.assertEqual(
            generated.count('HPy_SetAttr_s(ctx, m, "__pyx_hpy_default_'), 5)
        self.assertEqual(
            generated.count('HPy_SetAttr_s(ctx, __pyx_hpy_temp_'), 9)
        self.assertEqual(
            generated.count(
                '"__pyx_hpy_slot_owner_bootstrap_case_'), 2)
        self.assertGreaterEqual(
            generated.count('"__pyx_hpy_default_'), 20)
        self.assertNotIn("HPyGlobal", generated)

    def test_instance_methods_load_interpreter_owned_module_state(self):
        result, generated, diagnostics = self.compile_source(
            "TYPE_VALUE = 7\n\n"
            "cdef class Reader:\n"
            "    def read_global(self):\n"
            "        return TYPE_VALUE\n\n"
            "    def builtin_length(self, value, /):\n"
            "        return len(value)\n\n"
            "    def cached_constant(self):\n"
            "        return ('method', 9)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(
            generated.count(
                'HPy_SetAttr_s(ctx, __pyx_hpy_temp_'), 2)
        self.assertEqual(
            generated.count(
                '"__pyx_hpy_slot_owner_bootstrap_case_Reader"'), 1)
        self.assertIn('"__pyx_hpy_module", m)', generated)
        self.assertEqual(
            generated.count(
                'HPy_GetAttr_s(ctx, self, "__class__")'), 3)
        self.assertGreaterEqual(
            generated.count('"__pyx_hpy_module"'), 4)
        self.assertIn('HPy_HasAttr_s(ctx, __pyx_hpy_temp_', generated)
        self.assertIn('"TYPE_VALUE"', generated)
        self.assertIn('"__pyx_hpy_builtins"', generated)
        self.assertIn('"__pyx_hpy_const_', generated)
        self.assertNotIn("HPyGlobal", generated)

    def test_reserved_type_runtime_cache_names_are_rejected(self):
        cases = (
            "    cdef public object __pyx_hpy_module\n",
            "    def __pyx_hpy_default_0(self):\n"
            "        return self\n",
            "    def __pyx_hpy_slot_owner_collision(self):\n"
            "        return self\n",
        )
        for body in cases:
            with self.subTest(body=body):
                result, generated, diagnostics = self.compile_source(
                    "cdef class Value:\n" + body)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn("reserved runtime cache names", diagnostics)

    def test_special_slots_load_interpreter_owned_module_state(self):
        result, generated, diagnostics = self.compile_source(
            "TYPE_VALUE = 7\n"
            "TYPE_TEXT = 'slot'\n"
            "EVENTS = []\n\n"
            "cdef class Slots:\n"
            "    cdef object value\n\n"
            "    def __init__(self):\n"
            "        self.value = TYPE_VALUE\n\n"
            "    def __call__(self):\n"
            "        return TYPE_VALUE\n\n"
            "    def __repr__(self):\n"
            "        return TYPE_TEXT\n\n"
            "    def __str__(self):\n"
            "        return TYPE_TEXT\n\n"
            "    def __len__(self):\n"
            "        return TYPE_VALUE\n\n"
            "    def __getitem__(self, key):\n"
            "        return [TYPE_VALUE, key]\n\n"
            "    def __setitem__(self, key, value):\n"
            "        self.value = TYPE_VALUE\n\n"
            "    def __delitem__(self, key):\n"
            "        self.value = TYPE_VALUE\n\n"
            "    def __hash__(self):\n"
            "        return TYPE_VALUE\n\n"
            "    def __bool__(self):\n"
            "        return TYPE_VALUE\n\n"
            "    def __contains__(self, value):\n"
            "        return TYPE_VALUE\n\n"
            "    def __eq__(self, other):\n"
            "        return TYPE_TEXT\n\n"
            "    def __del__(self):\n"
            "        EVENTS.append(TYPE_VALUE)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertGreaterEqual(generated.count('"__pyx_hpy_module"'), 14)
        self.assertIn('"TYPE_VALUE"', generated)
        self.assertIn('"TYPE_TEXT"', generated)
        self.assertIn('"EVENTS"', generated)
        self.assertIn("HPy_tp_finalize", generated)
        self.assertNotIn("HPyGlobal", generated)

    def test_effectful_extension_method_defaults_evaluate_before_type_publish(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Value:\n"
            "    def __init__(self, value=len([1])):\n"
            "        self.value = value\n"
            "\n"
            "    def item(self, value=len([2, 3])):\n"
            "        return value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Call", generated)
        default_store = generated.index(
            'HPy_SetAttr_s(ctx, m, "__pyx_hpy_default_0"')
        type_publish = generated.index('HPy_SetAttr_s(ctx, m, "Value"')
        self.assertLess(default_store, type_publish)

    def test_richcompare_methods_share_exact_hpy_opcode_dispatch(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Compared:\n"
            "    cdef object less_result\n"
            "    cdef object equal_result\n\n"
            "    def __init__(self, less_result, equal_result):\n"
            "        self.less_result = less_result\n"
            "        self.equal_result = equal_result\n\n"
            "    def __lt__(self, other):\n"
            "        return self.less_result\n\n"
            "    def __eq__(self, other):\n"
            "        return self.equal_result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_richcompare", generated)
        self.assertIn("HPy_RichCmpOp op", generated)
        self.assertIn("case HPy_LT:", generated)
        self.assertIn("case HPy_EQ:", generated)
        self.assertNotIn("case HPy_NE:", generated)
        self.assertIn("HPy_Dup(ctx, ctx->h_NotImplemented)", generated)

    def test_add_reflected_add_and_inplace_add_use_exact_hpy_slots(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class AddBox:\n"
            "    def __add__(self, other):\n"
            "        return ['add', self, other]\n\n"
            "    def __radd__(self, other):\n"
            "        return ['radd', self, other]\n\n"
            "    def __iadd__(self, other):\n"
            "        return ['iadd', self, other]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_nb_add", generated)
        self.assertIn("HPy_nb_inplace_add", generated)
        self.assertIn(
            '"__pyx_hpy_slot_owner_bootstrap_case_AddBox"', generated)
        self.assertIn("HPy_Type(ctx, left)", generated)
        self.assertIn("HPy_Type(ctx, right)", generated)
        self.assertIn("HPy_HasAttr_s(ctx, left_type,", generated)
        self.assertIn(
            "_nb_add_left_impl(ctx, left, right)", generated)
        self.assertIn(
            "_nb_add_right_impl(ctx, right, left)", generated)
        self.assertIn(
            "HPy_Is(ctx, result, ctx->h_NotImplemented)", generated)
        self.assertIn("HPy_Dup(ctx, ctx->h_NotImplemented)", generated)

    def test_all_two_argument_numeric_families_use_public_hpy_slots(self):
        families = (
            ("nb_add", "__add__", "__radd__", "nb_inplace_add", "__iadd__"),
            ("nb_subtract", "__sub__", "__rsub__", "nb_inplace_subtract", "__isub__"),
            ("nb_multiply", "__mul__", "__rmul__", "nb_inplace_multiply", "__imul__"),
            ("nb_remainder", "__mod__", "__rmod__", "nb_inplace_remainder", "__imod__"),
            ("nb_divmod", "__divmod__", "__rdivmod__", None, None),
            ("nb_floor_divide", "__floordiv__", "__rfloordiv__", "nb_inplace_floor_divide", "__ifloordiv__"),
            ("nb_true_divide", "__truediv__", "__rtruediv__", "nb_inplace_true_divide", "__itruediv__"),
            ("nb_lshift", "__lshift__", "__rlshift__", "nb_inplace_lshift", "__ilshift__"),
            ("nb_rshift", "__rshift__", "__rrshift__", "nb_inplace_rshift", "__irshift__"),
            ("nb_and", "__and__", "__rand__", "nb_inplace_and", "__iand__"),
            ("nb_xor", "__xor__", "__rxor__", "nb_inplace_xor", "__ixor__"),
            ("nb_or", "__or__", "__ror__", "nb_inplace_or", "__ior__"),
            ("nb_matrix_multiply", "__matmul__", "__rmatmul__", "nb_inplace_matrix_multiply", "__imatmul__"),
        )
        method_names = []
        for _, left_name, right_name, _, inplace_name in families:
            method_names.extend((left_name, right_name))
            if inplace_name is not None:
                method_names.append(inplace_name)
        source = "cdef class NumericFamilies:\n" + "".join(
            "    def %s(self, other):\n"
            "        return self\n\n" % method_name
            for method_name in method_names
        )
        result, generated, diagnostics = self.compile_source(source)
        self.assertEqual(result.num_errors, 0, diagnostics)
        for slot_name, _, _, inplace_slot, _ in families:
            self.assertIn("HPy_%s" % slot_name, generated)
            if inplace_slot is not None:
                self.assertIn("HPy_%s" % inplace_slot, generated)
        self.assertEqual(generated.count("HPy_Type(ctx, left)"), len(families))
        self.assertNotIn("PyNumberMethods", generated)

    def test_numeric_override_merges_inherited_normal_and_reflected_methods(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Base:\n"
            "    cdef object label\n\n"
            "    def __add__(self, other):\n"
            "        return self.label\n\n"
            "cdef class Derived(Base):\n"
            "    def __radd__(self, other):\n"
            "        return self\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count("HPy_nb_add"), 2)
        self.assertIn(
            "__pyx_hpy_type_1_Derived_nb_add_left_impl", generated)
        self.assertIn(
            "__pyx_hpy_type_1_Derived_nb_add_right_impl", generated)
        self.assertIn(
            '"__pyx_hpy_slot_owner_bootstrap_case_Derived"', generated)
        self.assertIn("__pyx_hpy_type_Base_object_AsStruct(ctx,", generated)

    def test_power_family_uses_ternary_hpy_slots_and_marker_dispatch(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Power:\n"
            "    def __pow__(self, other, modulus=None):\n"
            "        return [self, other, modulus]\n\n"
            "    def __rpow__(self, other, modulus=None):\n"
            "        return [self, other, modulus]\n\n"
            "    def __ipow__(self, other, modulus=None):\n"
            "        return [self, other, modulus]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_nb_power", generated)
        self.assertIn("HPy_nb_inplace_power", generated)
        self.assertIn(
            "HPy left, HPy right, HPy modulus)", generated)
        self.assertIn(
            "_nb_power_left_impl(ctx, left, right, modulus)", generated)
        self.assertIn(
            "_nb_power_right_impl(ctx, right, left, modulus)", generated)
        self.assertIn(
            '"__pyx_hpy_slot_owner_bootstrap_case_Power"', generated)
        self.assertIn(
            "HPyListBuilder_Set(ctx, __pyx_hpy_builder_0, 2, modulus)",
            generated,
        )
        self.assertNotIn("HPy_Dup(ctx, modulus)", generated)
        self.assertNotIn("__pyx_hpy_default_", generated)

    def test_two_argument_power_rejects_non_none_modulus_in_slot(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class TwoArgPower:\n"
            "    def __pow__(self, other):\n"
            "        return self\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_nb_power", generated)
        self.assertIn(
            "if (!HPy_Is(ctx, modulus, ctx->h_None))", generated)
        self.assertIn("does not accept a modulus argument", generated)

    def test_finalize_slot_reports_errors_as_unraisable(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Finalized:\n"
            "    def __del__(self):\n"
            "        raise RuntimeError('finalize failure')\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_finalize", generated)
        self.assertIn(
            "static void __pyx_hpy_type_0_Finalized_tp_finalize_impl(",
            generated,
        )
        self.assertIn("HPyErr_WriteUnraisable(ctx, self)", generated)
        self.assertNotIn("HPyDef_METH", generated)

    def test_native_fields_support_strict_c_inplace_arithmetic_slice(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NumericBox:\n"
            "    cdef int count\n"
            "    cdef double ratio\n\n"
            "    def adjust(self, add, subtract, multiply):\n"
            "        self.count += add\n"
            "        self.count -= subtract\n"
            "        self.count *= multiply\n"
            "        self.ratio += add\n"
            "        self.ratio -= subtract\n"
            "        self.ratio *= multiply\n"
            "        return [self.count, self.ratio]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(" += (int)__pyx_hpy_native_long_", generated)
        self.assertIn(" -= (int)__pyx_hpy_native_long_", generated)
        self.assertIn(" *= (int)__pyx_hpy_native_long_", generated)
        self.assertIn(" += __pyx_hpy_native_double_", generated)
        self.assertIn(" -= __pyx_hpy_native_double_", generated)
        self.assertIn(" *= __pyx_hpy_native_double_", generated)
        self.assertNotIn("HPy_InPlaceAdd", generated)

    def test_native_integer_fields_support_direct_bitwise_inplace_slice(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class MaskBox:\n"
            "    cdef int value\n\n"
            "    def update(self, and_value, or_value, xor_value):\n"
            "        self.value &= and_value\n"
            "        self.value |= or_value\n"
            "        self.value ^= xor_value\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(" &= (int)__pyx_hpy_native_long_", generated)
        self.assertIn(" |= (int)__pyx_hpy_native_long_", generated)
        self.assertIn(" ^= (int)__pyx_hpy_native_long_", generated)
        self.assertNotIn("HPy_InPlaceAnd", generated)
        self.assertNotIn("HPy_InPlaceOr", generated)
        self.assertNotIn("HPy_InPlaceXor", generated)

    def test_native_integer_fields_support_direct_shift_inplace_slice(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class ShiftBox:\n"
            "    cdef int value\n\n"
            "    def update(self, left, right):\n"
            "        self.value <<= left\n"
            "        self.value >>= right\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(" <<= (int)__pyx_hpy_native_long_", generated)
        self.assertIn(" >>= (int)__pyx_hpy_native_long_", generated)
        self.assertNotIn("HPy_InPlaceLshift", generated)
        self.assertNotIn("HPy_InPlaceRshift", generated)

    def test_native_division_modulo_and_power_preserve_python_result_path(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NumericBox:\n"
            "    cdef int count\n\n"
            "    cdef double ratio\n\n"
            "    def update(self, value, /):\n"
            "        self.count //= value\n"
            "        self.count %= value\n"
            "        self.count **= value\n"
            "        self.ratio /= value\n"
            "        return [self.count, self.ratio]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_InPlaceFloorDivide(ctx,", generated)
        self.assertIn("HPy_InPlaceRemainder(ctx,", generated)
        self.assertIn("HPy_InPlacePower(ctx,", generated)
        self.assertIn("HPy_InPlaceTrueDivide(ctx,", generated)
        self.assertIn("HPyLong_AsLong(ctx,", generated)
        self.assertIn("HPyFloat_AsDouble(ctx,", generated)

    def test_ordinary_instance_methods_use_hpy_method_definitions(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Echo:\n"
            "    def owner(self):\n"
            "        return self\n\n"
            "    def identity(self, value, /):\n"
            "        return value\n\n"
            "    def combine(self, left, right):\n"
            "        return [self, left, right]\n\n"
            "def make_echo():\n"
            "    return Echo()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"owner", HPyFunc_NOARGS', generated)
        self.assertIn('"identity", HPyFunc_O', generated)
        self.assertIn('"combine", HPyFunc_KEYWORDS', generated)
        self.assertIn("HPyDef_METH(__pyx_hpy_type_0_Echo_method_", generated)
        self.assertIn("HPy_Dup(ctx, self)", generated)
        self.assertIn("HPy_Dup(ctx, arg)", generated)
        self.assertIn("HPyArg_ParseKeywords(ctx,", generated)
        self.assertNotIn("PyMethodDef", generated)

    def test_format_uses_an_ordinary_hpy_o_method_definition(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class FormatBox:\n"
            "    cdef object values\n\n"
            "    def __init__(self, values):\n"
            "        self.values = values\n\n"
            "    def __format__(self, spec, /):\n"
            "        return self.values[spec]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"__format__", HPyFunc_O', generated)
        self.assertIn("HPyDef_METH(__pyx_hpy_type_0_FormatBox_method_", generated)
        self.assertNotIn("HPy_tp_format", generated)

    def test_slotless_protocol_methods_use_ordinary_hpy_method_definitions(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class ProtocolBox:\n"
            "    cdef object bytes_value\n"
            "    cdef object complex_value\n"
            "    cdef object round_values\n\n"
            "    def __init__(self, bytes_value, complex_value, round_values):\n"
            "        self.bytes_value = bytes_value\n"
            "        self.complex_value = complex_value\n"
            "        self.round_values = round_values\n\n"
            "    def __bytes__(self):\n"
            "        return self.bytes_value\n\n"
            "    def __complex__(self):\n"
            "        return self.complex_value\n\n"
            "    def __round__(self, ndigits=None):\n"
            "        return self.round_values[ndigits]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"__bytes__", HPyFunc_NOARGS', generated)
        self.assertIn('"__complex__", HPyFunc_NOARGS', generated)
        self.assertIn('"__round__", HPyFunc_KEYWORDS', generated)
        self.assertIn(
            "HPyDef_METH(__pyx_hpy_type_0_ProtocolBox_method_", generated)
        self.assertNotIn("HPy_tp_bytes", generated)
        self.assertNotIn("HPy_tp_complex", generated)
        self.assertNotIn("HPy_tp_round", generated)

    def test_slotless_protocol_methods_reject_invalid_source_signatures(self):
        sources = (
            (
                "bytes",
                "cdef class BadBytes:\n"
                "    def __bytes__(self, value):\n"
                "        return value\n",
            ),
            (
                "complex",
                "cdef class BadComplex:\n"
                "    def __complex__(self, value):\n"
                "        return value\n",
            ),
            (
                "round",
                "cdef class BadRound:\n"
                "    def __round__(self, first, second):\n"
                "        return first\n",
            ),
        )
        for feature, source in sources:
            with self.subTest(feature=feature):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(
                    "slotless protocol methods require __bytes__(self), "
                    "__complex__(self), or __round__(self[, ndigits])",
                    diagnostics,
                )

    def test_context_manager_methods_use_ordinary_hpy_method_definitions(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Manager:\n"
            "    cdef object events\n"
            "    cdef object suppress\n\n"
            "    def __init__(self, events, suppress):\n"
            "        self.events = events\n"
            "        self.suppress = suppress\n\n"
            "    def __enter__(self):\n"
            "        self.events.append('enter')\n"
            "        return self\n\n"
            "    def __exit__(self, exc_type, exc_value, traceback):\n"
            "        self.events.append(exc_type)\n"
            "        return self.suppress\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('"__enter__", HPyFunc_NOARGS', generated)
        self.assertIn('"__exit__", HPyFunc_KEYWORDS', generated)
        self.assertIn(
            "HPyDef_METH(__pyx_hpy_type_0_Manager_method_", generated)
        self.assertNotIn("HPy_tp_enter", generated)
        self.assertNotIn("HPy_tp_exit", generated)

    def test_context_manager_methods_reject_invalid_source_signatures(self):
        sources = (
            (
                "enter",
                "cdef class BadEnter:\n"
                "    def __enter__(self, value):\n"
                "        return value\n",
            ),
            (
                "exit",
                "cdef class BadExit:\n"
                "    def __exit__(self, exc_type, exc_value):\n"
                "        return False\n",
            ),
        )
        for feature, source in sources:
            with self.subTest(feature=feature):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(
                    "synchronous context-manager methods require "
                    "__enter__(self) and "
                    "__exit__(self, exc_type, exc_value, traceback)",
                    diagnostics,
                )

    def test_instance_methods_load_and_store_object_fields_via_hpyfield(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Box:\n"
            "    cdef public object value\n"
            "    cdef object hidden\n\n"
            "    def read_hidden(self):\n"
            "        return self.hidden\n\n"
            "    def write_hidden(self, value, /):\n"
            "        self.hidden = value\n"
            "        return self\n\n"
            "    def extend_hidden(self, value, /):\n"
            "        self.hidden += value\n"
            "        return self.hidden\n\n"
            "    def read_value(self):\n"
            "        return self.value\n\n"
            "def make_box():\n"
            "    return Box()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("__pyx_hpy_type_Box_object_AsStruct(ctx,", generated)
        self.assertIn("HPyField_IsNull(", generated)
        self.assertIn("HPyField_Load(ctx,", generated)
        self.assertIn("HPyField_Store(ctx,", generated)
        self.assertIn("HPy_InPlaceAdd(ctx,", generated)
        self.assertIn("HPy_Dup(ctx, ctx->h_None)", generated)
        self.assertNotIn('HPy_GetAttr_s(ctx, __pyx_hpy_temp_0, "hidden")', generated)
        self.assertNotIn('HPy_SetAttr_s(ctx, __pyx_hpy_temp_0, "hidden"', generated)
        read_start = generated.index("_read_hidden_impl")
        read_impl = generated[read_start:generated.index("static HPy", read_start + 1)]
        self.assertIn("__pyx_hpy_type_Box_object_AsStruct(ctx, self)", read_impl)
        self.assertNotIn("HPy_Dup(ctx, self)", read_impl)
        self.assertNotIn("HPy_Close(ctx, self)", read_impl)

    def test_initializer_uses_tp_init_and_keyword_dictionary_parser(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Initialized:\n"
            "    cdef public object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "def make_initialized(value, /):\n"
            "    return Initialized(value)\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_Initialized_init, HPy_tp_init)",
            generated,
        )
        self.assertIn(
            "static int __pyx_hpy_type_0_Initialized_init_impl(", generated)
        self.assertIn("HPyArg_ParseKeywordsDict(ctx,", generated)
        self.assertIn("HPyField_Store(ctx,", generated)
        self.assertIn("return 0;", generated)
        self.assertNotIn('"__init__", HPyFunc_', generated)

    def test_positional_initializer_uses_borrowed_slot_arguments(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class PositionalInitialized:\n"
            "    cdef object value\n\n"
            "    def __cinit__(self, value, /):\n"
            "        self.value = value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        marker = "static int __pyx_hpy_type_0_PositionalInitialized_cinit_impl"
        declaration = generated.index(marker)
        start = generated.index(marker, declaration + len(marker))
        implementation = generated[start:generated.index("HPyDef_SLOT", start)]
        self.assertIn("if (nargs != 1) {", implementation)
        self.assertIn("HPy_Length(ctx, kw)", implementation)
        self.assertIn("AsStruct(ctx, self)", implementation)
        self.assertIn("HPyField_Store(ctx, self,", implementation)
        self.assertIn(", args[0]);", implementation)
        self.assertNotIn("HPyArg_ParseKeywords", implementation)
        self.assertNotIn("HPyTracker", implementation)
        self.assertNotIn("HPy_Dup(ctx, args[0])", implementation)
        self.assertNotIn("HPy_Close(ctx, args[0])", implementation)

    def test_initializer_converts_and_stores_native_fields(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class NativeInitialized:\n"
            "    cdef public int count\n"
            "    cdef public double ratio\n\n"
            "    def __init__(self, count, ratio):\n"
            "        self.count = count\n"
            "        self.ratio = ratio\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_init", generated)
        self.assertIn("HPyArg_ParseKeywordsDict(ctx,", generated)
        self.assertIn("HPyLong_AsLong(ctx,", generated)
        self.assertIn("HPyFloat_AsDouble(ctx,", generated)
        self.assertIn("return -1;", generated)
        self.assertIn("return 0;", generated)

    def test_repr_and_str_use_value_returning_type_slots(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Display:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def __repr__(self):\n"
            "        return self.value\n\n"
            "    def __str__(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_tp_repr", generated)
        self.assertIn("HPy_tp_str", generated)
        self.assertIn(
            "static HPy __pyx_hpy_type_0_Display_tp_repr_impl(", generated)
        self.assertIn(
            "static HPy __pyx_hpy_type_0_Display_tp_str_impl(", generated)
        self.assertNotIn('"__repr__", HPyFunc_', generated)
        self.assertNotIn('"__str__", HPyFunc_', generated)

    def test_len_uses_length_slot_and_ssize_conversion(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Sized:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def __len__(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_Sized_sq_length, HPy_sq_length)",
            generated,
        )
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_Sized_mp_length, HPy_mp_length)",
            generated,
        )
        self.assertIn(
            "static HPy_ssize_t __pyx_hpy_type_0_Sized_sq_length_impl(",
            generated,
        )
        self.assertIn("HPyLong_AsSsize_t(ctx,", generated)
        self.assertIn(
            "return __pyx_hpy_type_0_Sized_sq_length_impl(ctx, self);",
            generated,
        )
        self.assertIn('"__len__() should return >= 0"', generated)
        self.assertNotIn('"__len__", HPyFunc_', generated)

    def test_getitem_uses_mapping_subscript_slot(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class IndexBox:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def __getitem__(self, key):\n"
            "        return self.value[key]\n\n"
            "    def __setitem__(self, key, value):\n"
            "        self.value[key] = value\n\n"
            "    def __delitem__(self, key):\n"
            "        del self.value[key]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_IndexBox_mp_subscript, "
            "HPy_mp_subscript)",
            generated,
        )
        self.assertIn(
            "static HPy __pyx_hpy_type_0_IndexBox_mp_subscript_impl("
            "HPyContext *ctx, HPy self, HPy key)",
            generated,
        )
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_IndexBox_sq_item, HPy_sq_item)",
            generated,
        )
        self.assertIn("HPyLong_FromSsize_t(ctx, index)", generated)
        self.assertIn(
            "__pyx_hpy_type_0_IndexBox_mp_subscript_impl("
            "ctx, self, __pyx_hpy_index)",
            generated,
        )
        self.assertIn("HPy_GetItem(ctx,", generated)
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_IndexBox_mp_ass_subscript, "
            "HPy_mp_ass_subscript)",
            generated,
        )
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_IndexBox_sq_ass_item, "
            "HPy_sq_ass_item)",
            generated,
        )
        self.assertIn(
            "__pyx_hpy_type_0_IndexBox_mp_ass_subscript_impl("
            "ctx, self, key, value)",
            generated,
        )
        self.assertIn("if (HPy_IsNull(value))", generated)
        self.assertIn("HPy_SetItem(ctx,", generated)
        self.assertIn("HPy_DelItem(ctx,", generated)
        self.assertNotIn('"__getitem__", HPyFunc_', generated)
        self.assertNotIn('"__setitem__", HPyFunc_', generated)
        self.assertNotIn('"__delitem__", HPyFunc_', generated)

    def test_partial_assignment_slot_rejects_the_missing_operation(self):
        cases = (
            (
                "set-only",
                "    def __setitem__(self, key, value):\n"
                "        self.value[key] = value\n",
                "does not support item deletion",
            ),
            (
                "delete-only",
                "    def __delitem__(self, key):\n"
                "        del self.value[key]\n",
                "does not support item assignment",
            ),
        )
        for label, method, missing_message in cases:
            with self.subTest(label=label):
                result, generated, diagnostics = self.compile_source(
                    "cdef class PartialItems:\n"
                    "    cdef object value\n\n" + method
                )
                self.assertEqual(result.num_errors, 0, diagnostics)
                self.assertIn("HPy_mp_ass_subscript", generated)
                self.assertIn(missing_message, generated)

    def test_extension_properties_use_universal_getset_definitions(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class PropertyBox:\n"
            "    cdef object value\n\n"
            "    property managed:\n"
            "        '''managed \"documentation\" \\\\ path\n"
            "        ikinci satır\\tson'''\n"
            "        def __get__(self):\n"
            "            return self.value\n"
            "        def __set__(self, value):\n"
            "            self.value = value\n"
            "        def __del__(self):\n"
            "            self.value = None\n\n"
            "    property readonly:\n"
            "        def __get__(self):\n"
            "            return self.value\n\n"
            "    property writeonly:\n"
            "        def __set__(self, value):\n"
            "            self.value = value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyDef_GETSET(", generated)
        self.assertIn(
            '.doc = "managed \\"documentation\\" \\\\ path\\n'
            '        ikinci sat\\304\\261r\\tson"',
            generated,
        )
        self.assertIn("HPyDef_GET(", generated)
        self.assertIn("HPyDef_SET(", generated)
        self.assertIn("static HPy __pyx_hpy_type_0_PropertyBox_property_0_managed_get(", generated)
        self.assertIn("static int __pyx_hpy_type_0_PropertyBox_property_0_managed_set(", generated)
        self.assertIn("HPyField_Load(ctx,", generated)
        self.assertIn("HPyField_Store(ctx,", generated)
        self.assertNotIn('"__get__", HPyFunc_', generated)
        self.assertNotIn('"__set__", HPyFunc_', generated)
        self.assertNotIn('"__del__", HPyFunc_', generated)

        nul_doc_cases = (
            (
                "module",
                "'''before\\x00after'''\n\n"
                "def available():\n"
                "    return None\n",
            ),
            (
                "function",
                "def available():\n"
                "    '''before\\x00after'''\n"
                "    return None\n",
            ),
            (
                "type",
                "cdef class NulDoc:\n"
                "    '''before\\x00after'''\n"
                "    def available(self):\n"
                "        return None\n",
            ),
            (
                "method",
                "cdef class NulDoc:\n"
                "    def available(self):\n"
                "        '''before\\x00after'''\n"
                "        return None\n",
            ),
            (
                "property",
                "cdef class NulDoc:\n"
                "    property value:\n"
                "        '''before\\x00after'''\n"
                "        def __get__(self):\n"
                "            return None\n",
            ),
        )
        for subject, source in nul_doc_cases:
            with self.subTest(nul_doc_subject=subject):
                result, _, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertIn(
                    "%s docstrings containing NUL are not representable" %
                    subject,
                    diagnostics,
                )

    def test_hash_uses_hash_slot_and_integer_validation(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class HashBox:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def __hash__(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_HashBox_tp_hash, HPy_tp_hash)",
            generated,
        )
        self.assertIn(
            "static HPy_hash_t __pyx_hpy_type_0_HashBox_tp_hash_impl(",
            generated,
        )
        self.assertIn("HPy_TypeCheck(ctx,", generated)
        self.assertIn("ctx->h_LongType", generated)
        self.assertIn("HPyLong_AsSsize_t(ctx,", generated)
        self.assertIn(
            "HPyErr_ExceptionMatches(ctx, ctx->h_OverflowError)", generated)
        self.assertIn("HPyErr_Clear(ctx)", generated)
        self.assertIn("HPy_Hash(ctx,", generated)
        self.assertRegex(
            generated,
            r"if \(__pyx_hpy_hash_\d+ == -1\) "
            r"__pyx_hpy_hash_\d+ = -2;")
        self.assertIn("__hash__ method should return an integer", generated)

    def test_bool_uses_inquiry_slot_and_c_int_conversion(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class BoolBox:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def __bool__(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_BoolBox_nb_bool, HPy_nb_bool)",
            generated,
        )
        self.assertIn(
            "static int __pyx_hpy_type_0_BoolBox_nb_bool_impl(", generated)
        self.assertIn("HPyLong_AsLong(ctx,", generated)
        self.assertIn("INT_MIN", generated)
        self.assertIn("INT_MAX", generated)
        self.assertRegex(generated, r"return \(int\)__pyx_hpy_bool_\d+;")

    def test_unary_special_methods_use_value_returning_number_slots(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class UnaryBox:\n"
            "    cdef object value\n\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n\n"
            "    def __neg__(self):\n"
            "        return self.value\n\n"
            "    def __pos__(self):\n"
            "        return self.value\n\n"
            "    def __abs__(self):\n"
            "        return self.value\n\n"
            "    def __invert__(self):\n"
            "        return self.value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        for slot_name in (
            "nb_negative", "nb_positive", "nb_absolute", "nb_invert",
        ):
            self.assertIn("HPy_%s" % slot_name, generated)
            self.assertIn("_%s_impl(" % slot_name, generated)
        self.assertNotIn('"__neg__", HPyFunc_', generated)
        self.assertNotIn('"__pos__", HPyFunc_', generated)
        self.assertNotIn('"__abs__", HPyFunc_', generated)
        self.assertNotIn('"__invert__", HPyFunc_', generated)

    def test_conversion_special_methods_use_unary_number_slots(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class ConversionBox:\n"
            "    cdef object integer_value\n"
            "    cdef object float_value\n\n"
            "    def __init__(self, integer_value, float_value):\n"
            "        self.integer_value = integer_value\n"
            "        self.float_value = float_value\n\n"
            "    def __int__(self):\n"
            "        return self.integer_value\n\n"
            "    def __index__(self):\n"
            "        return self.integer_value\n\n"
            "    def __float__(self):\n"
            "        return self.float_value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        for slot_name in ("nb_int", "nb_index", "nb_float"):
            self.assertIn("HPy_%s" % slot_name, generated)
            self.assertIn("_%s_impl(" % slot_name, generated)

    def test_contains_uses_sequence_contains_status_slot(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class ContainsBox:\n"
            "    cdef object result\n\n"
            "    def __init__(self, result):\n"
            "        self.result = result\n\n"
            "    def __contains__(self, value):\n"
            "        return self.result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "HPyDef_SLOT(__pyx_hpy_type_0_ContainsBox_sq_contains, "
            "HPy_sq_contains)",
            generated,
        )
        self.assertIn(
            "static int __pyx_hpy_type_0_ContainsBox_sq_contains_impl(",
            generated,
        )
        self.assertIn("HPyLong_AsLong(ctx,", generated)
        self.assertRegex(generated, r"return \(int\)__pyx_hpy_bool_\d+;")

    def test_generated_pure_hpy_single_inheritance_layout_and_params(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Base:\n"
            "    cdef public object base_value\n\n"
            "    def __init__(self, value):\n"
            "        self.base_value = value\n\n"
            "cdef class Derived(Base):\n"
            "    cdef public object derived_value\n\n"
            "    def set_derived(self, value, /):\n"
            "        self.derived_value = value\n"
            "        return self\n\n"
            "    def values(self):\n"
            "        return [self.base_value, self.derived_value]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn(
            "__pyx_hpy_type_Base_object __pyx_hpy_base;", generated)
        self.assertIn("HPyType_SpecParam_Base", generated)
        self.assertIn(
            "HPyType_FromSpec(ctx, &__pyx_hpy_type_Derived_spec, "
            "__pyx_hpy_type_params_1)", generated)
        self.assertIn(
            "__pyx_hpy_type_Base_traverse_impl(object, visit, arg)", generated)
        self.assertIn("__pyx_hpy_type_Base_object_AsStruct(ctx,", generated)
        self.assertIn("__pyx_hpy_type_Derived_object_AsStruct(ctx,", generated)

    def test_external_extension_base_is_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Invalid(list):\n"
            "    pass\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "requires one generated pure HPy base declared earlier", diagnostics)

    def test_m5_shape_walls_have_actionable_compile_time_diagnostics(self):
        cases = (
            (
                "freelist",
                "cimport cython\n"
                "@cython.freelist(4)\n"
                "cdef class FreelistBox:\n"
                "    pass\n",
                "pure Universal HPy @cython.freelist is not implemented",
            ),
            (
                "multiple-inheritance",
                "cdef class BaseA:\n"
                "    pass\n\n"
                "cdef class BaseB:\n"
                "    pass\n\n"
                "cdef class Derived(BaseA, BaseB):\n"
                "    pass\n",
                "Only one extension type base class allowed",
            ),
            (
                "metaclass",
                "class MetaclassBox(metaclass=type):\n"
                "    pass\n",
                "pure Universal HPy metaclass customization is not implemented",
            ),
            (
                "general-array-layout",
                "cdef class VarSizeBox:\n"
                "    cdef int items[4]\n",
                "C array extension fields are only implemented as the private "
                "storage of the canonical one-dimensional fixed-array buffer",
            ),
            (
                "deallocator",
                "cdef class NativeResource:\n"
                "    def __dealloc__(self):\n"
                "        pass\n",
                "pure Universal HPy __dealloc__ is not implemented",
            ),
        )
        for label, source, expected_diagnostic in cases:
            with self.subTest(label=label):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1, diagnostics)
                self.assertFalse(generated)
                self.assertIn(expected_diagnostic, diagnostics)

    def test_unsupported_cdef_class_shapes_are_rejected_at_type_boundary(self):
        cases = (
            (
                "unsupported-native-field",
                "cdef class Value:\n    cdef int *item\n",
                "initial pure HPy cdef class support requires",
            ),
            (
                "typed-field",
                "cdef class Value:\n    cdef list item\n",
                "initial pure HPy cdef class support requires",
            ),
            (
                "special-method",
                "cdef class Value:\n    def __iter__(self):\n        return self\n",
                "exposes neither HPy_tp_iter nor HPy_tp_iternext",
            ),
        )
        for label, source, expected_diagnostic in cases:
            with self.subTest(label=label):
                result, generated, diagnostics = self.compile_source(
                    source + "\ndef answer():\n    return 1\n")
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(expected_diagnostic, diagnostics)

    def test_special_slot_defaults_remain_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Value:\n"
            "    def __getitem__(self, key=None):\n"
            "        return key\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("cannot have a default value", diagnostics)

    def test_weakref_layout_is_rejected_at_the_hpy_09_api_boundary(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Value:\n"
            "    cdef object __weakref__\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "HPy 0.9 provides no public weak-reference layout", diagnostics)
        self.assertIn("Universal ABI", diagnostics)

    def test_instance_dict_layout_is_rejected_at_the_hpy_09_api_boundary(self):
        result, generated, diagnostics = self.compile_source(
            "cdef class Value:\n"
            "    cdef dict __dict__\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "HPy 0.9 provides no public portable instance-dict layout",
            diagnostics,
        )
        self.assertIn("Universal ABI", diagnostics)

    def test_module_exec_emits_runtime_fallback_for_uninitialized_global(self):
        result, generated, diagnostics = self.compile_source(
            "SECOND = FIRST\n"
            "FIRST = 1\n\n"
            "def answer():\n"
            "    return SECOND\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('HPy_HasAttr_s(ctx, m, "FIRST")', generated)
        self.assertIn('HPy_GetAttr_s(ctx, m, "FIRST")', generated)
        self.assertIn('HPy_GetAttr_s(ctx, __pyx_hpy_temp_', generated)
        self.assertIn('HPy_HasAttr_s(ctx, __pyx_hpy_temp_', generated)
        function_code = generated[:generated.index(
            "HPyDef_SLOT(__pyx_hpy_mod_exec")]
        self.assertNotIn("HPyErr_ExceptionMatches", function_code)
        self.assertIn("ctx->h_NameError", generated)

    def test_function_global_assignment_inplace_delete_and_missing_lookup(self):
        result, generated, diagnostics = self.compile_source(
            "VALUE = 1\n"
            "MISSING = 2\n\n"
            "def set_value(value, /):\n"
            "    global VALUE\n"
            "    VALUE = value\n"
            "    return VALUE\n\n"
            "def add_value(value, /):\n"
            "    global VALUE\n"
            "    VALUE += value\n"
            "    return VALUE\n\n"
            "def delete_value():\n"
            "    global VALUE\n"
            "    del VALUE\n"
            "    return None\n\n"
            "def missing_value():\n"
            "    return MISSING\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('HPy_SetAttr_s(ctx, self, "VALUE"', generated)
        self.assertIn('HPy_DelAttr_s(ctx, self, "VALUE")', generated)
        self.assertIn('HPy_HasAttr_s(ctx, self, "VALUE")', generated)
        self.assertIn("HPy_InPlaceAdd(ctx,", generated)
        function_code = generated[:generated.index(
            "HPyDef_SLOT(__pyx_hpy_mod_exec")]
        self.assertNotIn("HPyErr_ExceptionMatches", function_code)
        self.assertIn("name 'MISSING' is not defined", generated)

    def test_local_deletion_uses_stable_null_slot_and_unbound_local(self):
        result, generated, diagnostics = self.compile_source(
            "def clear():\n"
            "    value = 1\n"
            "    del value\n"
            "    return 0\n\n"
            "def rebind():\n"
            "    value = 1\n"
            "    del value\n"
            "    value = 3\n"
            "    return value\n\n"
            "def maybe(flag, /):\n"
            "    value = 1\n"
            "    if flag:\n"
            "        del value\n"
            "    return value\n\n"
            "def looped(do_delete, /):\n"
            "    value = 1\n"
            "    for item in [0]:\n"
            "        if do_delete:\n"
            "            del value\n"
            "    return value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("ctx->h_UnboundLocalError", generated)
        self.assertIn("HPy_IsNull(", generated)
        self.assertIn(
            "local variable 'value' referenced before assignment", generated)
        maybe_impl = generated.index("__pyx_hpy_def_2_maybe_impl")
        maybe_code = generated[maybe_impl:generated.index(
            "__pyx_hpy_def_3_looped_impl", maybe_impl)]
        # Promote before the continuing ``if`` so merge keeps the nullled slot.
        promote_at = maybe_code.index("= HPy_NULL;")
        if_at = maybe_code.index("if (__pyx_hpy_truth_", promote_at)
        self.assertLess(promote_at, if_at)

    def test_function_locals_builds_dict_and_skips_null_slots(self):
        result, generated, diagnostics = self.compile_source(
            "def sample(left, /):\n"
            "    right = 2\n"
            "    gone = 3\n"
            "    del gone\n"
            "    return locals()\n\n"
            "def alias(left, /):\n"
            "    right = 2\n"
            "    return vars()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyDict_New", generated)
        self.assertIn("HPyErr_Occurred", generated)
        self.assertIn('HPyUnicode_FromString(ctx, "left")', generated)
        self.assertIn('HPyUnicode_FromString(ctx, "gone")', generated)
        # Must not call the interpreter ``builtins.locals``/``vars`` fallback.
        self.assertNotIn(', "locals")', generated)
        self.assertNotIn(', "vars")', generated)
        sample_impl = generated.index("__pyx_hpy_def_0_sample_impl")
        sample_code = generated[sample_impl:generated.index(
            "__pyx_hpy_def_1_alias_impl", sample_impl)]
        self.assertIn("HPy_SetItem(ctx,", sample_code)
        self.assertIn("HPy_IsNull(", sample_code)

    def test_globals_dir_genexp_and_reject_duplicate_keywords(self):
        result, generated, diagnostics = self.compile_source(
            "def names(left, /):\n"
            "    right = 1\n"
            "    return dir()\n\n"
            "def probe():\n"
            "    return 'x' in globals()\n\n"
            "def built():\n"
            "    return list(i for i in [1, 2])\n\n"
            "def any_items(values, /):\n"
            "    return any(v for v in values)\n\n"
            "def helper(x, a=0):\n"
            "    return (x, a)\n\n"
            "def call_dup():\n"
            "    return helper(1, a=2, **{'a': 3})\n\n"
            "MODULE_DIR = dir()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn('HPy_GetAttr_s(ctx, self, "__dict__")', generated)
        self.assertIn('"keys"', generated)
        self.assertIn("HPy_Call(ctx, ctx->h_ListType", generated)
        self.assertIn(
            "function() got multiple values for keyword argument", generated)
        self.assertIn('HPyUnicode_FromString(ctx, "left")', generated)
        self.assertNotIn(', "globals")', generated)

    def test_imag_literal_uses_constant_cache(self):
        result, generated, diagnostics = self.compile_source(
            "def a():\n"
            "    return 2j\n\n"
            "def b():\n"
            "    return 2j\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("__pyx_hpy_const_0", generated)
        self.assertEqual(generated.count("ctx->h_ComplexType"), 1)

    def test_module_exec_overwrites_globals_and_resolves_referenced_methods(self):
        result, generated, diagnostics = self.compile_source(
            "VALUE = ['old']\n"
            "VALUE = {'state': 'new'}\n\n"
            "def helper():\n"
            "    return VALUE\n\n"
            "def caller():\n"
            "    return helper()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count('HPy_SetAttr_s(ctx, m, "VALUE"'), 2)
        self.assertIn('HPy_GetAttr_s(ctx, self, "helper")', generated)
        self.assertIn('HPy_GetAttr_s(ctx, self, "VALUE")', generated)
        self.assertNotIn("HPyGlobal", generated)

    def test_continuing_conditionals_merge_stable_local_slots(self):
        result, generated, diagnostics = self.compile_source(
            "def merge_existing(flag, value, /):\n"
            "    result = value\n"
            "    if flag:\n"
            "        result = [value]\n"
            "    return result\n\n"
            "def merge_new(which, value, /):\n"
            "    if which == 1:\n"
            "        result = [value]\n"
            "    elif which == 2:\n"
            "        result = (value,)\n"
            "    else:\n"
            "        result = {'value': value}\n"
            "    return result\n\n"
            "def merge_nested(first, second, value, /):\n"
            "    result = value\n"
            "    if first:\n"
            "        if second:\n"
            "            result = [value]\n"
            "        else:\n"
            "            result = (value,)\n"
            "    else:\n"
            "        result = {'value': value}\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("= HPy_NULL;", generated)
        self.assertIn("if (!HPy_IsNull(", generated)
        self.assertGreaterEqual(generated.count("HPy_IsTrue(ctx,"), 5)

    def test_conditional_rejects_local_missing_on_a_path(self):
        result, generated, diagnostics = self.compile_source(
            "def missing(flag, /):\n"
            "    if flag:\n"
            "        result = 1\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "local result is not initialized on every conditional path",
            diagnostics,
        )

    def test_conditional_expression_uses_one_owned_result_slot(self):
        result, generated, diagnostics = self.compile_source(
            "def choose(condition, true_value, false_value, /):\n"
            "    return true_value if condition else false_value\n\n"
            "def choose_call(condition, true_value, false_value, /):\n"
            "    return true_value() if condition else false_value()\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count("HPy_IsTrue(ctx,"), 2)
        self.assertIn("= HPy_NULL;", generated)
        self.assertIn("if (!HPy_IsNull(", generated)

    def test_while_loop_supports_break_continue_else_and_stable_locals(self):
        result, generated, diagnostics = self.compile_source(
            "def consume(condition, value, /):\n"
            "    result = []\n"
            "    current = None\n"
            "    while condition():\n"
            "        current = value()\n"
            "        if current == 0:\n"
            "            continue\n"
            "        if current < 0:\n"
            "            break\n"
            "        result += [current]\n"
            "    else:\n"
            "        result += ['done']\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("while (1) {", generated)
        self.assertIn("continue;", generated)
        self.assertIn("break;", generated)
        self.assertIn("__pyx_hpy_loop_completed_0 = 0;", generated)
        self.assertIn("if (__pyx_hpy_loop_completed_0) {", generated)
        self.assertIn("HPy_InPlaceAdd(ctx,", generated)

    def test_while_and_for_loops_support_return_and_raise(self):
        result, generated, diagnostics = self.compile_source(
            "def leave_while(condition, value, /):\n"
            "    while condition():\n"
            "        return value\n"
            "    return None\n"
            "\n"
            "def raise_while(condition, /):\n"
            "    while condition():\n"
            "        raise ValueError('loop')\n"
            "    return None\n"
            "\n"
            "def leave_for(first, second, /):\n"
            "    for item in [first, second]:\n"
            "        if item:\n"
            "            return item\n"
            "    return None\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("while (1) {", generated)
        self.assertIn("for (HPy_ssize_t", generated)
        self.assertIn('HPyErr_SetString(ctx, ctx->h_ValueError, "loop");', generated)
        self.assertGreaterEqual(generated.count("return "), 4)

    def test_mixed_terminating_continuing_conditional_branches(self):
        result, generated, diagnostics = self.compile_source(
            "def choose(flag, value, /):\n"
            "    if flag:\n"
            "        value = [value]\n"
            "    else:\n"
            "        return value\n"
            "    return value\n"
            "\n"
            "def raise_or_wrap(flag, value, /):\n"
            "    if flag:\n"
            "        raise TypeError('blocked')\n"
            "    value = (value,)\n"
            "    return value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyListBuilder_New", generated)
        self.assertIn("HPyTupleBuilder_New", generated)
        self.assertIn('HPyErr_SetString(ctx, ctx->h_TypeError, "blocked");', generated)

    def test_while_loop_rejects_uninitialized_iteration_local(self):
        result, generated, diagnostics = self.compile_source(
            "def invalid(condition, /):\n"
            "    while condition:\n"
            "        result = 1\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "loop local result must be initialized before the loop",
            diagnostics,
        )

    def test_fixed_sequence_for_loop_uses_public_index_api(self):
        result, generated, diagnostics = self.compile_source(
            "def consume(first, second, third, /):\n"
            "    result = []\n"
            "    for item in [first, second, third]:\n"
            "        if item == 0:\n"
            "            continue\n"
            "        if item < 0:\n"
            "            break\n"
            "        result += [item]\n"
            "    else:\n"
            "        result += ['done']\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Length(ctx,", generated)
        self.assertIn("HPy_GetItem_i(ctx,", generated)
        self.assertIn("for (HPy_ssize_t", generated)
        self.assertIn("continue;", generated)
        self.assertIn("__pyx_hpy_loop_completed_", generated)

    def test_dynamic_sequence_for_loop_uses_public_index_api(self):
        result, generated, diagnostics = self.compile_source(
            "def consume(values, /):\n"
            "    result = []\n"
            "    for item in values:\n"
            "        if item == 0:\n"
            "            continue\n"
            "        if item < 0:\n"
            "            break\n"
            "        result += [item]\n"
            "    else:\n"
            "        result += ['done']\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Length(ctx,", generated)
        self.assertIn("HPy_GetItem_i(ctx,", generated)
        self.assertIn("for (HPy_ssize_t", generated)
        self.assertNotIn("HPy_Dup(ctx, arg)", generated)
        self.assertNotIn("HPy_Close(ctx, arg)", generated)

    def test_dynamic_sequence_loop_borrows_rebound_call_argument(self):
        result, generated, diagnostics = self.compile_source(
            "def consume(values, /):\n"
            "    result = []\n"
            "    for item in values:\n"
            "        values = None\n"
            "        result += [item]\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Length(ctx, arg)", generated)
        self.assertIn("HPy_GetItem_i(ctx, arg,", generated)
        self.assertEqual(generated.count("HPy_Dup(ctx, arg)"), 1)
        self.assertNotIn("HPy_Close(ctx, arg)", generated)

    def test_dynamic_sequence_comprehensions_use_public_index_api(self):
        result, generated, diagnostics = self.compile_source(
            "def values(items, /):\n"
            "    return [item * 2 for item in items if item]\n\n"
            "def mapping(items, /):\n"
            "    return {key: key + 1 for key in items}\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Length(ctx,", generated)
        self.assertIn("HPy_GetItem_i(ctx,", generated)
        self.assertIn("ctx->h_ListType", generated)
        self.assertIn("HPyDict_New(ctx)", generated)

    def test_generator_driven_for_loop_has_actionable_hpy09_diagnostic(self):
        result, generated, diagnostics = self.compile_source(
            "def unsupported():\n"
            "    result = []\n"
            "    for item in (value for value in (1, 2)):\n"
            "        result += [item]\n"
            "    return result\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("HPy 0.9 lacks a public generic iterator API", diagnostics)
        self.assertIn("generator expressions cannot drive for-loops", diagnostics)

    def test_generator_function_has_versioned_hpy09_diagnostic(self):
        for source in (
            "def values():\n"
            "    yield 1\n",
            "def delegated(values, /):\n"
            "    yield from values\n",
        ):
            with self.subTest(source=source):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(
                    "HPy 0.9 lacks the public iterator-next API", diagnostics)
                self.assertIn("without CPython emulation", diagnostics)

    def test_real_generator_expression_has_versioned_hpy09_diagnostic(self):
        result, generated, diagnostics = self.compile_source(
            "def values(items, /):\n"
            "    return (item for item in items)\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "HPy 0.9 lacks the public iterator-next API", diagnostics)
        self.assertIn("inlined sequence-safe consumers", diagnostics)

    def test_async_functions_have_versioned_hpy09_diagnostics(self):
        for source, feature in (
            (
                "async def consume(value):\n"
                "    return await value\n",
                "native coroutine objects and await",
            ),
            (
                "async def values():\n"
                "    yield 1\n",
                "async generator objects and async yield",
            ),
        ):
            with self.subTest(feature=feature):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn("HPy 0.9 lacks the public async protocol", diagnostics)
                self.assertIn(feature, diagnostics)
                self.assertIn("CPython coroutine utilities are forbidden", diagnostics)

    def test_typed_memoryview_argument_has_hpy09_consumer_diagnostic(self):
        result, generated, diagnostics = self.compile_source(
            "def first(double[:] values):\n"
            "    return values[0]\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("HPy_buffer producer slots", diagnostics)
        self.assertIn("no public buffer acquire/release consumer API", diagnostics)
        self.assertIn("cannot use CPython Py_buffer utilities", diagnostics)

    def test_scalar_buffer_producer_uses_public_hpy_slots(self):
        result, generated, diagnostics = self.compile_source(
            "from cpython.buffer cimport Py_buffer\n\n"
            "cdef class ScalarBuffer:\n"
            "    cdef public long value\n"
            "    cdef Py_ssize_t shape\n"
            "    cdef Py_ssize_t stride\n"
            "    def __getbuffer__(self, Py_buffer *view, int flags):\n"
            "        self.shape = 1\n"
            "        self.stride = sizeof(long)\n"
            "        view.buf = &self.value\n"
            "        view.obj = self\n"
            "        view.len = sizeof(long)\n"
            "        view.itemsize = sizeof(long)\n"
            "        view.readonly = 0\n"
            "        view.ndim = 1\n"
            "        view.format = 'l'\n"
            "        view.shape = &self.shape\n"
            "        view.strides = &self.stride\n"
            "        view.suboffsets = NULL\n"
            "        view.internal = NULL\n"
            "    def __releasebuffer__(self, Py_buffer *view):\n"
            "        pass\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_bf_getbuffer", generated)
        self.assertIn("HPy_bf_releasebuffer", generated)
        self.assertIn("HPy_buffer *view", generated)
        self.assertIn("view->obj = HPy_Dup(ctx, self);", generated)
        self.assertIn("view->shape = &data->", generated)
        self.assertIn("view->strides = &data->", generated)
        self.assertNotRegex(generated, r"\bPy_buffer\b")
        self.assertNotIn("Python.h", generated)

        for c_type, format_string in (
            ("char", "c"),
            ("signed char", "b"),
            ("unsigned char", "B"),
            ("short", "h"),
            ("unsigned short", "H"),
            ("int", "i"),
            ("unsigned int", "I"),
            ("long", "l"),
            ("unsigned long", "L"),
            ("long long", "q"),
            ("unsigned long long", "Q"),
            ("float", "f"),
            ("double", "d"),
        ):
            with self.subTest(c_type=c_type):
                scalar_result, scalar_generated, scalar_diagnostics = (
                    self.compile_source(
                        "from cpython.buffer cimport Py_buffer\n\n"
                        "cdef class ScalarBuffer:\n"
                        "    cdef %s value\n"
                        "    cdef Py_ssize_t shape\n"
                        "    cdef Py_ssize_t stride\n"
                        "    def __getbuffer__(self, Py_buffer *view, "
                        "int flags):\n"
                        "        self.shape = 1\n"
                        "        self.stride = sizeof(%s)\n"
                        "        view.buf = &self.value\n"
                        "        view.obj = self\n"
                        "        view.len = sizeof(%s)\n"
                        "        view.itemsize = sizeof(%s)\n"
                        "        view.readonly = 0\n"
                        "        view.ndim = 1\n"
                        "        view.format = %r\n"
                        "        view.shape = &self.shape\n"
                        "        view.strides = &self.stride\n"
                        "        view.suboffsets = NULL\n"
                        "        view.internal = NULL\n"
                        "    def __releasebuffer__(self, Py_buffer *view):\n"
                        "        pass\n" % (
                            c_type, c_type, c_type, c_type, format_string),
                    )
                )
                self.assertEqual(
                    scalar_result.num_errors, 0, scalar_diagnostics)
                self.assertIn(
                    'view->format = (char *)"%s";' % format_string,
                    scalar_generated,
                )
                self.assertNotRegex(scalar_generated, r"\bPy_buffer\b")

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "cpython_buffer.pyx"
            output = Path(temp_dir) / "cpython_buffer.c"
            source.write_text(
                "from cpython.buffer cimport Py_buffer\n\n"
                "cdef class ScalarBuffer:\n"
                "    cdef public long value\n"
                "    cdef Py_ssize_t shape\n"
                "    cdef Py_ssize_t stride\n"
                "    def __getbuffer__(self, Py_buffer *view, int flags):\n"
                "        self.shape = 1\n"
                "        self.stride = sizeof(long)\n"
                "        view.buf = &self.value\n"
                "        view.obj = self\n"
                "        view.len = sizeof(long)\n"
                "        view.itemsize = sizeof(long)\n"
                "        view.readonly = 0\n"
                "        view.ndim = 1\n"
                "        view.format = 'l'\n"
                "        view.shape = &self.shape\n"
                "        view.strides = &self.stride\n"
                "        view.suboffsets = NULL\n"
                "        view.internal = NULL\n"
                "    def __releasebuffer__(self, Py_buffer *view):\n"
                "        pass\n",
                encoding="utf8",
            )
            cpython_result = Main.compile(
                str(source),
                Options.CompilationOptions(
                    output_file=str(output), language_level=3),
            )
            self.assertEqual(cpython_result.num_errors, 0)
            self.assertIn("Py_buffer", output.read_text(encoding="utf8"))

    def test_scalar_buffer_producer_fails_closed_outside_contract(self):
        body = (
            "    def __getbuffer__(self, Py_buffer *view, int flags):\n"
            "        self.shape = 1\n"
            "        self.stride = sizeof(long)\n"
            "        view.buf = &self.value\n"
            "        view.obj = self\n"
            "        view.len = sizeof(long)\n"
            "        view.itemsize = sizeof(long)\n"
            "        view.readonly = 0\n"
            "        view.ndim = 1\n"
            "        view.format = {format!r}\n"
            "        view.shape = &self.shape\n"
            "        view.strides = &self.stride\n"
            "        view.suboffsets = NULL\n"
            "        view.internal = NULL\n"
        )
        cases = (
            (
                "from cpython.buffer cimport Py_buffer as BufferDescriptor\n",
                "only the exact Py_buffer frontend type is translated",
            ),
            (
                "from cpython.buffer cimport Py_buffer\n"
                "cdef class ScalarBuffer:\n"
                "    cdef public long value\n"
                "    cdef Py_ssize_t shape\n"
                "    cdef Py_ssize_t stride\n" + body.format(format="l"),
                "both methods must be declared exactly once",
            ),
            (
                "from cpython.buffer cimport Py_buffer\n"
                "cdef class ScalarBuffer:\n"
                "    cdef public long value\n"
                "    cdef Py_ssize_t shape\n"
                "    cdef Py_ssize_t stride\n" + body.format(format="i") +
                "    def __releasebuffer__(self, Py_buffer *view):\n"
                "        pass\n",
                "view.format must match the exported native field",
            ),
            (
                "from cpython.buffer cimport Py_buffer\n"
                "cdef class ScalarBuffer:\n"
                "    cdef readonly long value\n"
                "    cdef Py_ssize_t shape\n"
                "    cdef Py_ssize_t stride\n" + body.format(format="l") +
                "    def __releasebuffer__(self, Py_buffer *view):\n"
                "        pass\n",
                "producer slice supports writable fixed C",
            ),
            (
                "from cpython.buffer cimport Py_buffer\n"
                "cdef class ScalarBuffer:\n"
                "    cdef bint value\n"
                "    cdef Py_ssize_t shape\n"
                "    cdef Py_ssize_t stride\n" +
                body.replace("sizeof(long)", "sizeof(bint)").format(
                    format="?") +
                "    def __releasebuffer__(self, Py_buffer *view):\n"
                "        pass\n",
                "excluding bint, Py_ssize_t, and long double",
            ),
        )
        for source, expected in cases:
            with self.subTest(expected=expected):
                result, generated, diagnostics = self.compile_source(source)
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn(expected, diagnostics)

    def test_fixed_array_buffer_producer_uses_public_hpy_slots(self):
        source_text = (
            "from cpython.buffer cimport Py_buffer\n\n"
            "cdef class FixedArrayBuffer:\n"
            "    cdef long values[4]\n"
            "    cdef Py_ssize_t shape\n"
            "    cdef Py_ssize_t stride\n"
            "    def __getbuffer__(self, Py_buffer *view, int flags):\n"
            "        self.shape = 4\n"
            "        self.stride = sizeof(long)\n"
            "        view.buf = self.values\n"
            "        view.obj = self\n"
            "        view.len = sizeof(self.values)\n"
            "        view.itemsize = sizeof(long)\n"
            "        view.readonly = 0\n"
            "        view.ndim = 1\n"
            "        view.format = 'l'\n"
            "        view.shape = &self.shape\n"
            "        view.strides = &self.stride\n"
            "        view.suboffsets = NULL\n"
            "        view.internal = NULL\n"
            "    def __releasebuffer__(self, Py_buffer *view):\n"
            "        pass\n"
        )
        result, generated, diagnostics = self.compile_source(source_text)
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertRegex(generated, r"long __pyx_hpy_field_\d+_values\[4\]")
        self.assertRegex(
            generated,
            r"data->__pyx_hpy_field_\d+_shape = 4;",
        )
        self.assertRegex(
            generated,
            r"view->buf = \(void \*\)data->__pyx_hpy_field_\d+_values;",
        )
        self.assertRegex(
            generated,
            r"view->len = \(HPy_ssize_t\)sizeof\(data->"
            r"__pyx_hpy_field_\d+_values\);",
        )
        self.assertRegex(
            generated,
            r"view->itemsize = \(HPy_ssize_t\)sizeof\(data->"
            r"__pyx_hpy_field_\d+_values\[0\]\);",
        )
        self.assertNotRegex(generated, r"\bPy_buffer\b")
        self.assertNotIn("Python.h", generated)

        for c_type, format_string in (
            ("char", "c"),
            ("signed char", "b"),
            ("unsigned char", "B"),
            ("short", "h"),
            ("unsigned short", "H"),
            ("int", "i"),
            ("unsigned int", "I"),
            ("unsigned long", "L"),
            ("long long", "q"),
            ("unsigned long long", "Q"),
            ("float", "f"),
            ("double", "d"),
        ):
            with self.subTest(c_type=c_type):
                typed_source = source_text.replace(
                    "cdef long values[4]", "cdef %s values[4]" % c_type,
                ).replace(
                    "sizeof(long)", "sizeof(%s)" % c_type,
                ).replace(
                    "view.format = 'l'",
                    "view.format = %r" % format_string,
                )
                typed_result, typed_generated, typed_diagnostics = (
                    self.compile_source(typed_source))
                self.assertEqual(
                    typed_result.num_errors, 0, typed_diagnostics)
                self.assertIn(
                    'view->format = (char *)"%s";' % format_string,
                    typed_generated,
                )
                self.assertNotRegex(typed_generated, r"\bPy_buffer\b")

        typedef_source = source_text.replace(
            "from cpython.buffer cimport Py_buffer\n\n",
            "from cpython.buffer cimport Py_buffer\n\n"
            "ctypedef long buffer_value_t\n\n",
        ).replace(
            "cdef long values[4]", "cdef buffer_value_t values[4]",
        ).replace(
            "sizeof(long)", "sizeof(buffer_value_t)",
        )
        typedef_result, typedef_generated, typedef_diagnostics = (
            self.compile_source(typedef_source))
        self.assertEqual(typedef_result.num_errors, 0, typedef_diagnostics)
        self.assertRegex(
            typedef_generated, r"long __pyx_hpy_field_\d+_values\[4\]")
        self.assertNotIn("buffer_value_t", typedef_generated)

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "cpython_array_buffer.pyx"
            output = Path(temp_dir) / "cpython_array_buffer.c"
            source.write_text(source_text, encoding="utf8")
            cpython_result = Main.compile(
                str(source),
                Options.CompilationOptions(
                    output_file=str(output), language_level=3),
            )
            self.assertEqual(cpython_result.num_errors, 0)
            self.assertIn("Py_buffer", output.read_text(encoding="utf8"))

    def test_fixed_array_buffer_producer_fails_closed_outside_contract(self):
        source_template = (
            "from cpython.buffer cimport Py_buffer\n\n"
            "cdef class FixedArrayBuffer:\n"
            "    cdef {field_type} values{dimensions}\n"
            "    cdef Py_ssize_t shape\n"
            "    cdef Py_ssize_t stride\n"
            "    def __getbuffer__(self, Py_buffer *view, int flags):\n"
            "        self.shape = {shape}\n"
            "        self.stride = sizeof({field_type})\n"
            "        view.buf = self.values\n"
            "        view.obj = self\n"
            "        view.len = sizeof(self.values)\n"
            "        view.itemsize = sizeof({field_type})\n"
            "        view.readonly = 0\n"
            "        view.ndim = 1\n"
            "        view.format = {format!r}\n"
            "        view.shape = &self.shape\n"
            "        view.strides = &self.stride\n"
            "        view.suboffsets = NULL\n"
            "        view.internal = NULL\n"
            "    def __releasebuffer__(self, Py_buffer *view):\n"
            "        pass\n"
        )
        cases = (
            (
                dict(field_type="long", dimensions="[4]", shape=3,
                     format="l"),
                "shape field must match the exported element count",
            ),
            (
                dict(field_type="long", dimensions="[2][2]", shape=2,
                     format="l"),
                "one-dimensional C array",
            ),
            (
                dict(field_type="bint", dimensions="[4]", shape=4,
                     format="?"),
                "excluding bint, Py_ssize_t, and long double",
            ),
        )
        for values, expected in cases:
            with self.subTest(expected=expected):
                result, generated, diagnostics = self.compile_source(
                    source_template.format(**values))
                self.assertEqual(result.num_errors, 1, diagnostics)
                self.assertFalse(generated)
                self.assertIn(expected, diagnostics)

    def test_fused_functions_require_pure_hpy_dispatch(self):
        for declaration in ("def", "cpdef"):
            with self.subTest(declaration=declaration):
                result, generated, diagnostics = self.compile_source(
                    "ctypedef fused number:\n"
                    "    int\n"
                    "    double\n\n"
                    "%s identity(number value):\n"
                    "    return value\n" % declaration
                )
                self.assertEqual(result.num_errors, 1)
                self.assertFalse(generated)
                self.assertIn("pure HPy specialization dispatcher", diagnostics)
                self.assertIn("typed argument conversion", diagnostics)
                self.assertIn("interpreter-owned signature metadata", diagnostics)
                self.assertIn("CPython __Pyx_FusedFunction", diagnostics)

    def test_lambda_has_closure_slice_diagnostic(self):
        result, generated, diagnostics = self.compile_source(
            "def make_identity():\n"
            "    return lambda value: value\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("lambda closures are not implemented", diagnostics)
        self.assertIn("one-level nested def slice", diagnostics)

    def test_assert_uses_public_assertion_error(self):
        result, generated, diagnostics = self.compile_source(
            "def check(value, /):\n"
            "    assert value, 'blocked'\n"
            "    return value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("CYTHON_WITHOUT_ASSERTIONS", generated)
        self.assertIn("ctx->h_AssertionError", generated)
        self.assertIn("HPy_IsTrue(ctx,", generated)

    def test_range_and_for_from_use_ssize_counted_loops(self):
        result, generated, diagnostics = self.compile_source(
            "def literal():\n"
            "    total = 0\n"
            "    for i in range(1, 5, 2):\n"
            "        total = total + i\n"
            "    return total\n\n"
            "def counted(n, /):\n"
            "    total = 0\n"
            "    for i from 0 <= i < n:\n"
            "        total = total + i\n"
            "    return total\n\n"
            "def squares():\n"
            "    return [i * i for i in range(4)]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyLong_FromSsize_t(ctx,", generated)
        self.assertGreaterEqual(generated.count("for (HPy_ssize_t"), 2)
        self.assertIn("ctx->h_ListType", generated)

    def test_typed_c_range_target_has_actionable_diagnostic(self):
        result, generated, diagnostics = self.compile_source(
            "def unsupported(n, /):\n"
            "    cdef Py_ssize_t i\n"
            "    total = 0\n"
            "    for i in range(n):\n"
            "        total = total + i\n"
            "    return total\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "typed C for-from / range targets are not implemented",
            diagnostics,
        )

    def test_slice_get_set_delete_and_inplace_use_owned_slice_handle(self):
        result, generated, diagnostics = self.compile_source(
            "def get_slice(value, /):\n"
            "    return value[1:4:2]\n\n"
            "def set_slice(value, /):\n"
            "    value[1:3] = [8, 9]\n"
            "    return value\n\n"
            "def delete_slice(value, /):\n"
            "    del value[1:3]\n"
            "    return value\n\n"
            "def inplace_slice(value, /):\n"
            "    value[1:2] += [7]\n"
            "    return value\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("ctx->h_SliceType", generated)
        self.assertIn("HPy_Call(ctx, ctx->h_SliceType,", generated)
        self.assertIn("HPy_GetItem(ctx,", generated)
        self.assertIn("HPy_SetItem(ctx,", generated)
        self.assertIn("HPy_DelItem(ctx,", generated)
        self.assertIn("HPy_InPlaceAdd(ctx,", generated)

    def test_empty_module_is_supported(self):
        result, generated, diagnostics = self.compile_source("# empty\n")
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPyDef_SLOT(__pyx_hpy_mod_exec", generated)
        self.assertIn("HPy_MODINIT(bootstrap_case,", generated)
        self.assertNotIn("HPyDef_METH(", generated)

    def test_cpython_cimport_is_rejected_with_universal_guidance(self):
        result, generated, diagnostics = self.compile_source(
            "from cpython.ref cimport PyObject\n"
            "def answer():\n"
            "    return 1\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("cpython.* cimports expose the CPython C API", diagnostics)
        self.assertIn("port the dependency to public HPy APIs", diagnostics)

    def test_nested_def_closure_emits_env_and_callable_types(self):
        result, generated, diagnostics = self.compile_source(
            "def make_adder(x, /):\n"
            "    def add(y, /):\n"
            "        return x + y\n"
            "    return add\n\n"
            "def make_mutated_reader(x, /):\n"
            "    def read():\n"
            "        return x\n"
            "    x = x + 10\n"
            "    return read\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("__pyx_hpy_closure_env_0_object", generated)
        self.assertIn("__pyx_hpy_closure_fn_0_object", generated)
        self.assertIn("HPyField_Store", generated)
        self.assertIn("HPyField_Load", generated)
        self.assertIn("__pyx_hpy_closure_env_0", generated)
        self.assertIn("__pyx_hpy_closure_fn_0", generated)
        self.assertIn("HPyType_FromSpec", generated)

    def test_nested_positional_varargs_rejects_keywords_without_tracker(self):
        result, generated, diagnostics = self.compile_source(
            "def make_adder(base, /):\n"
            "    def add(left, right, /):\n"
            "        return base + left + right\n"
            "    return add\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("if (!HPy_IsNull(kwnames)) {", generated)
        self.assertIn("HPy_Length(ctx, kwnames)", generated)
        self.assertIn("if (__pyx_hpy_positional_kw_count != 0) {", generated)
        self.assertIn("add() does not accept keyword arguments", generated)
        self.assertIn("if (nargs != 2) {", generated)
        self.assertNotIn("HPyArg_ParseKeywords", generated)
        self.assertNotIn("HPyTracker", generated)

    def test_nested_noargs_and_onearg_reject_keywords(self):
        result, generated, diagnostics = self.compile_source(
            "def make_functions():\n"
            "    def zero():\n"
            "        return 0\n"
            "    def one(value, /):\n"
            "        return value\n"
            "    return [zero, one]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("HPy_Length(ctx, kwnames)", generated)
        self.assertIn("zero() does not accept keyword arguments", generated)
        self.assertIn("one() does not accept keyword arguments", generated)
        self.assertIn("if (nargs != 0) {", generated)
        self.assertIn("if (nargs != 1) {", generated)
        self.assertNotIn("HPyArg_ParseKeywords", generated)
        self.assertNotIn("HPyTracker", generated)

    def test_sibling_nested_defs_share_union_of_captures(self):
        result, generated, diagnostics = self.compile_source(
            "def make_readers(first, second, /):\n"
            "    def read_first():\n"
            "        return first\n"
            "    def read_second():\n"
            "        return second\n"
            "    return [read_first, read_second]\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertEqual(generated.count("HPyField __pyx_hpy_capture_"), 2)
        self.assertIn("__pyx_hpy_closure_fn_0_object", generated)
        self.assertIn("__pyx_hpy_closure_fn_1_object", generated)

    def test_nested_def_without_captures_still_has_an_environment_type(self):
        result, generated, diagnostics = self.compile_source(
            "def make_constant():\n"
            "    def constant():\n"
            "        return 7\n"
            "    return constant\n"
        )
        self.assertEqual(result.num_errors, 0, diagnostics)
        self.assertIn("__pyx_hpy_closure_env_0_object", generated)
        self.assertIn("char __pyx_hpy_reserved;", generated)
        self.assertIn("__pyx_hpy_closure_fn_0_object", generated)

    def test_c_typed_closure_capture_is_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "def outer(int value):\n"
            "    def inner():\n"
            "        return value\n"
            "    return inner\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "C-typed closure captures are not implemented", diagnostics)

    def test_nested_nested_def_is_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "def outer():\n"
            "    def inner():\n"
            "        def deepest():\n"
            "            return 1\n"
            "        return deepest\n"
            "    return inner\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("nested nested def closures are not implemented", diagnostics)

    def test_nested_def_defaults_are_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "def outer(value, /):\n"
            "    def inner(arg=value):\n"
            "        return arg\n"
            "    return inner\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("default arguments on nested def are not implemented", diagnostics)

    def test_nested_def_star_args_are_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "def outer():\n"
            "    def inner(*args):\n"
            "        return args\n"
            "    return inner\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("star arguments on nested def are not implemented", diagnostics)

    def test_nested_def_yield_is_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "def outer():\n"
            "    def inner():\n"
            "        yield 1\n"
            "    return inner\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "generators and yield in nested def are not implemented",
            diagnostics,
        )

    def test_decorated_nested_def_is_rejected(self):
        result, generated, diagnostics = self.compile_source(
            "def outer():\n"
            "    @staticmethod\n"
            "    def inner():\n"
            "        return 1\n"
            "    return inner\n"
        )
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn(
            "decorated nested def functions are not implemented",
            diagnostics,
        )
