from contextlib import redirect_stderr
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from .. import Main, Options
from ..RuntimeAPI import HPY_UNIVERSAL_BACKEND


class UniversalHPyModuleWriterTest(TestCase):
    def compile_source(self, source_text):
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
                ),
            )
        generated = output.read_text(encoding="utf8") if output.exists() else ""
        return result, generated, diagnostics.getvalue()

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
        self.assertIn("HPy_Call(ctx, __pyx_hpy_temp_0, NULL, 0, HPy_NULL)", generated)
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
        self.assertIn("HPy_Length(ctx,", generated[impl_start:])

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
        self.assertGreaterEqual(generated.count("HPyTracker_Close(ctx,"), 3)
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

    def test_binary_number_operations_use_owned_operands(self):
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
        add_call = generated.index("HPy_Add(ctx,")
        self.assertLess(
            add_call, generated.index("HPy_Close(ctx,", add_call))

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
                "value = 1\n",
                "require at least one supported def",
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
                'HPy_GetAttr_s(ctx, self, "__class__")'), 7)
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
        self.assertIn("HPy_Dup(ctx, modulus)", generated)
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
            "        '''managed documentation'''\n"
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
        self.assertIn('.doc = "managed documentation"', generated)
        self.assertIn("HPyDef_GET(", generated)
        self.assertIn("HPyDef_SET(", generated)
        self.assertIn("static HPy __pyx_hpy_type_0_PropertyBox_property_0_managed_get(", generated)
        self.assertIn("static int __pyx_hpy_type_0_PropertyBox_property_0_managed_set(", generated)
        self.assertIn("HPyField_Load(ctx,", generated)
        self.assertIn("HPyField_Store(ctx,", generated)
        self.assertNotIn('"__get__", HPyFunc_', generated)
        self.assertNotIn('"__set__", HPyFunc_', generated)
        self.assertNotIn('"__del__", HPyFunc_', generated)

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
        self.assertIn("HPy_Hash(ctx,", generated)
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

    def test_empty_module_is_rejected(self):
        result, generated, diagnostics = self.compile_source("# empty\n")
        self.assertEqual(result.num_errors, 1)
        self.assertFalse(generated)
        self.assertIn("require at least one supported def", diagnostics)

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
