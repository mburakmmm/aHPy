from unittest import TestCase
from types import SimpleNamespace
from itertools import product

from ..Code import CCodeConfig, CCodeWriter, FunctionState
from ..ExprNodes import CoerceToTempNode, ExprNode, TupleNode
from ..PyrexTypes import (
    hpy_handle_type,
    py_object_type,
    runtime_opaque_type,
)
from ..RuntimeAPI import (
    HPY_UNIVERSAL_BACKEND,
    RuntimeSequenceKind,
    create_runtime_api,
)
from ..HandleModel import (
    HandleArgumentEffect,
    HandleCleanupPlan,
    HandleBuilderManager,
    HandleBuilderState,
    HandleExitKind,
    HandleModelError,
    HandleOperation,
    HandleOwnership,
    HandleState,
    HandleStateTracker,
    HandleStorageKind,
    HandleTemporaryManager,
    HandleTrackerManager,
    HandleTrackerState,
    HandleTransfer,
    ContextPropagationModel,
    ContextRequirementKind,
    InvalidHandleStorageError,
    InvalidHandleTransitionError,
    RuntimeFunctionKind,
    operation_contract,
    storage_contract,
    validate_storage_declaration,
)


class HandleStorageTest(TestCase):
    def test_storage_kinds_have_distinct_runtime_representations(self):
        expected = {
            HandleStorageKind.LOCAL: ("HPy", False, True, False),
            HandleStorageKind.FIELD: ("HPyField", True, False, False),
            HandleStorageKind.GLOBAL: ("HPyGlobal", True, False, True),
            HandleStorageKind.CONTEXT_CONSTANT: ("HPy", False, True, False),
        }
        for kind, facts in expected.items():
            contract = storage_contract(kind)
            self.assertEqual(
                (contract.c_type_cname, contract.long_lived,
                 contract.directly_usable, contract.requires_module_registration),
                facts,
            )


class HandleOperationContractTest(TestCase):
    def test_every_declared_operation_has_an_ownership_contract(self):
        contracts = [operation_contract(operation) for operation in HandleOperation]
        self.assertEqual(
            {contract.operation for contract in contracts}, set(HandleOperation))

    def test_hpy_results_are_owned_local_handles(self):
        result_operations = {
            HandleOperation.DUPLICATE,
            HandleOperation.CALL,
            HandleOperation.CALL_METHOD,
            HandleOperation.SEQUENCE_BUILDER_BUILD,
            HandleOperation.SEQUENCE_FROM_ARRAY,
            HandleOperation.SEQUENCE_PACK,
            HandleOperation.DICT_NEW,
            HandleOperation.DICT_COPY,
            HandleOperation.TO_PYTHON,
            HandleOperation.NAME_LOOKUP,
            HandleOperation.GLOBAL_LOAD,
            HandleOperation.FIELD_LOAD,
            HandleOperation.IMPORT_MODULE,
        }
        for operation in HandleOperation:
            contract = operation_contract(operation)
            expected = HandleOwnership.OWNED if operation in result_operations else None
            self.assertIs(contract.result_ownership, expected, operation.value)
            if expected is not None:
                self.assertIs(contract.result_storage, HandleStorageKind.LOCAL)

    def test_hpy_inputs_are_borrowed_except_explicit_close(self):
        for operation in HandleOperation:
            contract = operation_contract(operation)
            expected = (
                HandleArgumentEffect.CLOSE
                if operation is HandleOperation.CLOSE
                else HandleArgumentEffect.BORROW
            )
            self.assertIs(contract.argument_effect, expected, operation.value)

    def test_builder_terminal_operations_consume_builder(self):
        self.assertTrue(operation_contract(
            HandleOperation.SEQUENCE_BUILDER_NEW).produces_builder)
        for operation in (
            HandleOperation.SEQUENCE_BUILDER_BUILD,
            HandleOperation.SEQUENCE_BUILDER_CANCEL,
        ):
            self.assertTrue(operation_contract(operation).consumes_builder)


class ContextPropagationModelTest(TestCase):
    def test_python_interacting_function_has_hidden_context_parameter(self):
        model = ContextPropagationModel()
        context = model.declare_function(
            "helper", RuntimeFunctionKind.PYTHON_INTERACTING)
        self.assertIs(context.requirement, ContextRequirementKind.REQUIRED)
        self.assertEqual(context.parameter_type_cname, "HPyContext *")
        self.assertEqual(context.parameter_cname, "ctx")

    def test_provably_pure_c_function_has_no_context_parameter(self):
        model = ContextPropagationModel()
        context = model.declare_function("add", RuntimeFunctionKind.PURE_C)
        self.assertIs(context.requirement, ContextRequirementKind.NONE)
        self.assertEqual(context.parameter_type_cname, "")
        self.assertEqual(context.parameter_cname, "")

    def test_context_propagates_only_to_context_requiring_callee(self):
        model = ContextPropagationModel()
        model.declare_function("caller", RuntimeFunctionKind.PYTHON_INTERACTING)
        model.declare_function("python_helper", RuntimeFunctionKind.PYTHON_INTERACTING)
        model.declare_function("c_helper", RuntimeFunctionKind.PURE_C)
        self.assertEqual(
            model.call_context_argument("caller", "python_helper"), "ctx")
        self.assertEqual(model.call_context_argument("caller", "c_helper"), "")

    def test_pure_c_caller_cannot_reach_python_interacting_helper(self):
        model = ContextPropagationModel()
        model.declare_function("caller", RuntimeFunctionKind.PURE_C)
        model.declare_function("callee", RuntimeFunctionKind.PYTHON_INTERACTING)
        with self.assertRaisesRegex(HandleModelError, "pure-C"):
            model.call_context_argument("caller", "callee")

    def test_advanced_entry_points_are_rejected_until_policy_exists(self):
        for function_kind in (
            RuntimeFunctionKind.CALLBACK,
            RuntimeFunctionKind.CLOSURE,
            RuntimeFunctionKind.GENERATOR,
            RuntimeFunctionKind.PUBLIC_C_API,
        ):
            model = ContextPropagationModel()
            model.declare_function("entry", function_kind)
            with self.assertRaisesRegex(
                HandleModelError, "not defined",
            ):
                model.require_enabled("entry")

    def test_context_cannot_be_persisted(self):
        model = ContextPropagationModel()
        model.declare_function("helper", RuntimeFunctionKind.PYTHON_INTERACTING)
        with self.assertRaisesRegex(
            InvalidHandleStorageError, "call-scoped",
        ):
            model.persist_context("helper", "a global variable")

    def test_function_state_binds_context_from_runtime_contract(self):
        funcstate = FunctionState(None, scope=SimpleNamespace(name="context"))
        hpy = create_runtime_api(HPY_UNIVERSAL_BACKEND)
        self.assertEqual(funcstate.bind_runtime_context(hpy), "ctx")
        self.assertEqual(funcstate.runtime_context_cname, "ctx")
        with self.assertRaisesRegex(ValueError, "context-free"):
            FunctionState(None, scope=SimpleNamespace(name="cpython")).bind_runtime_context(
                create_runtime_api("cpython"), "ctx")

    def test_local_hpyfield_is_rejected(self):
        with self.assertRaisesRegex(
            InvalidHandleStorageError, "function-local",
        ):
            validate_storage_declaration(
                HandleStorageKind.FIELD,
                "HPyField",
                is_function_local=True,
                is_long_lived=True,
            )

    def test_long_lived_plain_hpy_is_rejected(self):
        with self.assertRaisesRegex(
            InvalidHandleStorageError, "plain HPy",
        ):
            validate_storage_declaration(
                HandleStorageKind.LOCAL,
                "HPy",
                is_long_lived=True,
            )

    def test_wrong_runtime_storage_type_is_rejected(self):
        with self.assertRaisesRegex(
            InvalidHandleStorageError, "requires C type HPyGlobal",
        ):
            validate_storage_declaration(
                HandleStorageKind.GLOBAL,
                "HPyField",
                is_long_lived=True,
            )


class HandleStateTrackerTest(TestCase):
    def test_operation_contract_creates_owned_result_without_consuming_inputs(self):
        state = HandleStateTracker()
        state.declare_value(
            "callable", HandleStorageKind.LOCAL,
            HandleOwnership.BORROWED_ARGUMENT)
        result = state.apply_operation(
            HandleOperation.CALL, ("callable",), "result")
        self.assertIs(result.ownership, HandleOwnership.OWNED)
        self.assertIs(state.use("callable").state, HandleState.LIVE)

    def test_close_operation_applies_consuming_transition(self):
        state = HandleStateTracker()
        state.declare_value(
            "value", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        self.assertIsNone(state.apply_operation(
            HandleOperation.CLOSE, ("value",)))
        self.assertIs(state.value("value").state, HandleState.CLOSED)

    def test_operation_result_shape_is_enforced(self):
        state = HandleStateTracker()
        with self.assertRaisesRegex(HandleModelError, "requires a result"):
            state.apply_operation(HandleOperation.DICT_NEW)
        with self.assertRaisesRegex(HandleModelError, "does not produce"):
            state.apply_operation(HandleOperation.ERROR_SET_NONE, result_name="x")

    def test_owned_handle_can_close_exactly_once(self):
        state = HandleStateTracker()
        state.declare_value(
            "value", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        self.assertIs(state.close("value").state, HandleState.CLOSED)
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "cannot use closed",
        ):
            state.close("value")

    def test_moved_handle_cannot_be_used_or_closed(self):
        state = HandleStateTracker()
        state.declare_value(
            "value", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        self.assertIs(state.move("value").state, HandleState.MOVED)
        for operation in (state.use, state.close):
            with self.assertRaisesRegex(
                InvalidHandleTransitionError, "cannot use moved",
            ):
                operation("value")

    def test_borrowed_argument_cannot_be_closed_or_moved(self):
        state = HandleStateTracker()
        state.declare_value(
            "arg", HandleStorageKind.LOCAL,
            HandleOwnership.BORROWED_ARGUMENT)
        for operation in (state.close, state.move):
            with self.assertRaisesRegex(
                InvalidHandleTransitionError, "duplicate it first",
            ):
                operation("arg")

    def test_duplicate_of_borrowed_argument_is_owned(self):
        state = HandleStateTracker()
        state.declare_value(
            "arg", HandleStorageKind.LOCAL,
            HandleOwnership.BORROWED_ARGUMENT)
        duplicated = state.duplicate("arg", "copy")
        self.assertIs(duplicated.ownership, HandleOwnership.OWNED)
        state.close("copy")
        self.assertIs(state.use("arg").state, HandleState.LIVE)

    def test_context_constant_is_immortal_and_requires_dup_on_return(self):
        state = HandleStateTracker()
        state.declare_value(
            "none", HandleStorageKind.CONTEXT_CONSTANT,
            HandleOwnership.IMMORTAL)
        self.assertIs(state.prepare_return("none"), HandleTransfer.DUPLICATE)
        self.assertIs(state.use("none").state, HandleState.LIVE)
        with self.assertRaises(InvalidHandleTransitionError):
            state.close("none")

    def test_borrowed_argument_requires_dup_on_return(self):
        state = HandleStateTracker()
        state.declare_value(
            "arg", HandleStorageKind.LOCAL,
            HandleOwnership.BORROWED_ARGUMENT)
        self.assertIs(state.prepare_return("arg"), HandleTransfer.DUPLICATE)
        self.assertIs(state.use("arg").state, HandleState.LIVE)

    def test_owned_return_moves_value(self):
        state = HandleStateTracker()
        state.declare_value(
            "result", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        self.assertIs(state.prepare_return("result"), HandleTransfer.MOVE)
        self.assertIs(state.value("result").state, HandleState.MOVED)

    def test_global_and_field_loads_create_owned_locals(self):
        state = HandleStateTracker()
        state.declare_storage("global_value", HandleStorageKind.GLOBAL)
        state.declare_storage("field_value", HandleStorageKind.FIELD)
        for storage_name, target_name in (
            ("global_value", "from_global"),
            ("field_value", "from_field"),
        ):
            loaded = state.load_storage(storage_name, target_name)
            self.assertIs(loaded.storage.kind, HandleStorageKind.LOCAL)
            self.assertIs(loaded.ownership, HandleOwnership.OWNED)

    def test_long_lived_store_does_not_consume_input(self):
        state = HandleStateTracker()
        state.declare_storage("global_value", HandleStorageKind.GLOBAL)
        state.declare_value(
            "value", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        state.store_storage("global_value", "value")
        self.assertIs(state.use("value").state, HandleState.LIVE)

    def test_control_flow_exit_reports_only_live_owned_handles(self):
        state = HandleStateTracker()
        state.declare_value(
            "borrowed", HandleStorageKind.LOCAL,
            HandleOwnership.BORROWED_ARGUMENT)
        state.declare_value(
            "closed", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        state.close("closed")
        state.declare_value(
            "leaked", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        self.assertEqual(state.live_owned_handles(), ("leaked",))
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "leaked",
        ):
            state.assert_no_live_owned_handles()

    def test_exception_cleanup_closes_every_live_owned_intermediate(self):
        state = HandleStateTracker()
        state.declare_value(
            "outer", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        state.declare_value(
            "inner", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        plan = state.cleanup_plan(HandleExitKind.EXCEPTION)
        self.assertEqual(plan, HandleCleanupPlan(
            HandleExitKind.EXCEPTION, ("inner", "outer")))
        state.apply_cleanup_plan(plan)
        state.assert_no_live_owned_handles()

    def test_return_cleanup_preserves_result_and_closes_other_values(self):
        state = HandleStateTracker()
        state.declare_value(
            "result", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        state.declare_value(
            "intermediate", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        plan = state.cleanup_plan(
            HandleExitKind.RETURN, preserve_names=("result",))
        self.assertEqual(plan.close_names, ("intermediate",))
        state.apply_cleanup_plan(plan)
        self.assertIs(state.prepare_return("result"), HandleTransfer.MOVE)
        state.assert_no_live_owned_handles()

    def test_all_early_exit_kinds_receive_owned_cleanup(self):
        for exit_kind in HandleExitKind:
            state = HandleStateTracker()
            state.declare_value(
                "value", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
            plan = state.cleanup_plan(exit_kind)
            self.assertEqual(plan.close_names, ("value",), exit_kind.value)

    def test_branch_merge_rejects_mismatched_cleanup(self):
        initial = HandleStateTracker()
        initial.declare_value(
            "value", HandleStorageKind.LOCAL, HandleOwnership.OWNED)
        cleaned = initial.fork()
        cleaned.close("value")
        uncleaned = initial.fork()
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "matching cleanup",
        ):
            HandleStateTracker.merge(cleaned, uncleaned)
        uncleaned.close("value")
        merged = HandleStateTracker.merge(cleaned, uncleaned)
        merged.assert_no_live_owned_handles()

    def test_all_short_lifetime_transition_sequences_preserve_invariants(self):
        operations = ("use", "close", "move", "return")
        declarations = (
            (HandleStorageKind.LOCAL, HandleOwnership.OWNED),
            (HandleStorageKind.LOCAL, HandleOwnership.BORROWED_ARGUMENT),
            (HandleStorageKind.CONTEXT_CONSTANT, HandleOwnership.IMMORTAL),
        )
        for storage_kind, ownership in declarations:
            for length in range(5):
                for sequence in product(operations, repeat=length):
                    with self.subTest(
                        ownership=ownership.value, sequence=sequence,
                    ):
                        tracker = HandleStateTracker()
                        tracker.declare_value("value", storage_kind, ownership)
                        expected_state = HandleState.LIVE
                        for operation in sequence:
                            valid = expected_state is HandleState.LIVE
                            if operation in ("close", "move"):
                                valid = valid and ownership is HandleOwnership.OWNED
                            if not valid:
                                with self.assertRaises(
                                    InvalidHandleTransitionError,
                                ):
                                    if operation == "return":
                                        tracker.prepare_return("value")
                                    else:
                                        getattr(tracker, operation)("value")
                                continue
                            if operation == "return":
                                transfer = tracker.prepare_return("value")
                                if ownership is HandleOwnership.OWNED:
                                    self.assertIs(transfer, HandleTransfer.MOVE)
                                    expected_state = HandleState.MOVED
                                else:
                                    self.assertIs(
                                        transfer, HandleTransfer.DUPLICATE)
                            else:
                                getattr(tracker, operation)("value")
                                if operation == "close":
                                    expected_state = HandleState.CLOSED
                                elif operation == "move":
                                    expected_state = HandleState.MOVED
                        self.assertIs(
                            tracker.value("value").state, expected_state)

    def test_cleanup_property_for_all_terminal_states_exits_and_preserves(self):
        names = ("first", "second", "third")
        terminal_states = (
            HandleState.LIVE, HandleState.CLOSED, HandleState.MOVED)
        for states in product(terminal_states, repeat=len(names)):
            for exit_kind in HandleExitKind:
                for preserve_bits in product((False, True), repeat=len(names)):
                    preserve = tuple(
                        name for name, state, selected in zip(
                            names, states, preserve_bits)
                        if selected and state is HandleState.LIVE
                    )
                    tracker = HandleStateTracker()
                    for name, state in zip(names, states):
                        tracker.declare_value(
                            name, HandleStorageKind.LOCAL,
                            HandleOwnership.OWNED)
                        if state is HandleState.CLOSED:
                            tracker.close(name)
                        elif state is HandleState.MOVED:
                            tracker.move(name)
                    plan = tracker.cleanup_plan(
                        exit_kind, preserve_names=preserve)
                    expected = tuple(
                        name for name, state in reversed(tuple(zip(names, states)))
                        if state is HandleState.LIVE and name not in preserve
                    )
                    self.assertEqual(plan.close_names, expected)
                    tracker.apply_cleanup_plan(plan)
                    self.assertEqual(
                        tracker.live_owned_handles(), tuple(sorted(preserve)))
                    for name in preserve:
                        tracker.close(name)
                    tracker.assert_no_live_owned_handles()


class HandleTemporaryManagerTest(TestCase):
    def test_live_owned_temporary_cannot_be_released(self):
        temps = HandleTemporaryManager()
        temps.allocate("temp", HandleOwnership.OWNED)
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "close or move",
        ):
            temps.release("temp")

    def test_closed_slot_can_be_reused_as_a_distinct_handle(self):
        temps = HandleTemporaryManager()
        first = temps.allocate("temp", HandleOwnership.OWNED)
        temps.close("temp")
        temps.release("temp")
        second = temps.allocate("temp", HandleOwnership.OWNED)
        self.assertNotEqual(first.identity, second.identity)
        self.assertEqual(second.identity, "temp#2")
        temps.move("temp")
        temps.release("temp")

    def test_borrowed_temporary_can_be_released_without_close(self):
        temps = HandleTemporaryManager()
        temps.allocate("arg", HandleOwnership.BORROWED_ARGUMENT)
        temps.release("arg")
        self.assertEqual(temps.active_cnames(), ())

    def test_function_exit_reports_live_owned_temporary_by_cname(self):
        temps = HandleTemporaryManager()
        temps.allocate("result", HandleOwnership.OWNED)
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "result",
        ):
            temps.assert_no_live_owned_handles()

    def test_function_state_allocation_and_disposal_use_handle_lifetimes(self):
        funcstate = FunctionState(None, scope=SimpleNamespace(name="test"))
        name = funcstate.allocate_handle_temp(
            py_object_type, HandleOwnership.OWNED)
        funcstate.close_handle_temp(name)
        funcstate.release_handle_temp(name)
        funcstate.validate_exit()

        reused_name = funcstate.allocate_handle_temp(
            py_object_type, HandleOwnership.OWNED)
        self.assertEqual(reused_name, name)
        self.assertEqual(
            funcstate.handle_temps.binding(name).identity,
            "%s#2" % name,
        )
        funcstate.move_handle_temp(name)
        funcstate.release_handle_temp(name)
        funcstate.validate_exit()

    def test_function_state_rejects_live_owned_handle_at_exit(self):
        funcstate = FunctionState(None, scope=SimpleNamespace(name="test"))
        funcstate.allocate_handle_temp(py_object_type, HandleOwnership.OWNED)
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "function exit",
        ):
            funcstate.validate_exit()


class HandleBuilderManagerTest(TestCase):
    def test_runtime_opaque_builder_types_preserve_exact_c_spelling(self):
        list_builder = runtime_opaque_type("HPyListBuilder")
        self.assertIs(list_builder, runtime_opaque_type("HPyListBuilder"))
        self.assertEqual(
            list_builder.declaration_code("builder"),
            "HPyListBuilder builder",
        )

    def test_builder_requires_build_or_cancel_before_release(self):
        builders = HandleBuilderManager()
        builders.allocate("builder")
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "build or cancel",
        ):
            builders.release("builder")

    def test_build_and_cancel_are_distinct_terminal_states(self):
        builders = HandleBuilderManager()
        built = builders.allocate("builder")
        self.assertIs(builders.build("builder").state, HandleBuilderState.BUILT)
        builders.release("builder")
        cancelled = builders.allocate("builder")
        self.assertNotEqual(built.identity, cancelled.identity)
        self.assertIs(
            builders.cancel("builder").state, HandleBuilderState.CANCELLED)
        builders.release("builder")
        builders.assert_no_live_builders()

    def test_double_terminal_transition_is_rejected(self):
        builders = HandleBuilderManager()
        builders.allocate("builder")
        builders.build("builder")
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "cannot use built",
        ):
            builders.cancel("builder")

    def test_function_state_tracks_builder_temp_lifecycle(self):
        funcstate = FunctionState(None, scope=SimpleNamespace(name="builder"))
        name = funcstate.allocate_handle_builder_temp(py_object_type)
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "builders remain live",
        ):
            funcstate.validate_exit()
        funcstate.cancel_handle_builder_temp(name)
        funcstate.release_handle_builder_temp(name)
        funcstate.validate_exit()

    def test_sequence_emitter_uses_separate_hpy_builder_lifecycle(self):
        writer = CCodeWriter()
        writer.globalstate = SimpleNamespace(
            runtime_api=create_runtime_api(HPY_UNIVERSAL_BACKEND))
        writer.code_config = CCodeConfig()
        writer.funcstate = FunctionState(
            writer, scope=SimpleNamespace(name="builder_emitter"))
        writer.funcstate.bind_runtime_context(writer.globalstate.runtime_api)

        item = _BorrowedHandleExpression(None)
        sequence = TupleNode(None, args=[item])
        sequence.needs_subexpr_disposal = False
        builder = writer.globalstate.runtime_api.sequence_builder(
            RuntimeSequenceKind.TUPLE)
        sequence._generate_separate_sequence_builder_code(
            writer, "result", builder, 1, "", "")

        writer.funcstate.validate_exit()
        output = writer.getvalue()
        self.assertIn("HPyTupleBuilder_New(ctx, 1)", output)
        self.assertIn("HPyTupleBuilder_Set(ctx", output)
        self.assertIn("result = HPyTupleBuilder_Build(ctx", output)
        self.assertTrue(sequence.needs_subexpr_disposal)


class HandleTrackerManagerTest(TestCase):
    def test_tracker_requires_close_before_release(self):
        trackers = HandleTrackerManager()
        trackers.allocate("tracker")
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "close it first",
        ):
            trackers.release("tracker")

    def test_tracker_close_is_a_terminal_state(self):
        trackers = HandleTrackerManager()
        first = trackers.allocate("tracker")
        self.assertIs(
            trackers.close("tracker").state, HandleTrackerState.CLOSED)
        trackers.release("tracker")
        second = trackers.allocate("tracker")
        self.assertNotEqual(first.identity, second.identity)
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "trackers remain live",
        ):
            trackers.assert_no_live_trackers()
        trackers.close("tracker")
        trackers.release("tracker")
        trackers.assert_no_live_trackers()


class _HandleExpression(ExprNode):
    subexprs = []
    type = py_object_type
    is_temp = True


class _BorrowedHandleExpression(ExprNode):
    subexprs = []
    type = py_object_type
    is_temp = False

    def calculate_result_code(self):
        return "arg"


class _HandleExpressionCode:
    def __init__(self):
        self.globalstate = SimpleNamespace(
            runtime_api=create_runtime_api(HPY_UNIVERSAL_BACKEND),
            use_utility_code=lambda utility: None,
        )
        self.funcstate = FunctionState(
            self, scope=SimpleNamespace(name="expression"))
        self.lines = []

    def putln(self, line):
        self.lines.append(line)

    def put_decref_clear(self, cname, type_, have_gil=True):
        self.lines.append("close %s" % cname)

    def put_incref(self, cname, type_):
        self.lines.append("duplicate %s" % cname)


class HandleExpressionTemporaryTest(TestCase):
    def test_python_temp_contract_is_owned(self):
        expression = _HandleExpression(None)
        self.assertIs(
            expression.handle_temp_ownership(), HandleOwnership.OWNED)

    def test_hpy_expression_temp_uses_hpy_c_storage(self):
        code = _HandleExpressionCode()
        expression = _HandleExpression(None)
        expression.allocate_temp_result(code)
        temp_type, manage_ref = code.funcstate.temps_used_type[expression.result()]
        self.assertIs(temp_type, hpy_handle_type)
        self.assertFalse(manage_ref)
        expression.generate_disposal_code(code)
        expression.free_temps(code)

    def test_owned_expression_disposal_closes_then_releases_handle(self):
        code = _HandleExpressionCode()
        expression = _HandleExpression(None)
        expression.allocate_temp_result(code)
        cname = expression.result()
        self.assertTrue(code.funcstate.handle_temps.is_active(cname))
        expression.generate_disposal_code(code)
        expression.free_temps(code)
        self.assertFalse(code.funcstate.handle_temps.is_active(cname))
        self.assertIn("close %s" % cname, code.lines)
        code.funcstate.validate_exit()

    def test_absorbed_expression_moves_then_releases_handle(self):
        code = _HandleExpressionCode()
        expression = _HandleExpression(None)
        expression.allocate_temp_result(code)
        cname = expression.result()
        expression.generate_post_assignment_code(code)
        expression.free_temps(code)
        self.assertFalse(code.funcstate.handle_temps.is_active(cname))
        code.funcstate.validate_exit()

    def test_borrowed_expression_temp_is_rejected(self):
        code = _HandleExpressionCode()
        expression = _HandleExpression(None)
        expression.use_borrowed_ref = True
        with self.assertRaisesRegex(
            InvalidHandleTransitionError, "must be owned",
        ):
            expression.allocate_temp_result(code)

    def test_coerce_to_temp_duplicates_source_into_owned_result(self):
        code = _HandleExpressionCode()
        source = _BorrowedHandleExpression(None)
        coercion = CoerceToTempNode(source, env=None)
        coercion.allocate_temp_result(code)
        result = coercion.result()
        coercion.generate_result_code(code)
        self.assertIs(
            code.funcstate.handle_temps.use(result).ownership,
            HandleOwnership.OWNED)
        self.assertIn("duplicate %s" % result, code.lines)
        coercion.generate_disposal_code(code)
        coercion.free_temps(code)
        code.funcstate.validate_exit()


class RuntimeGlobalLoadOwnershipTest(TestCase):
    @staticmethod
    def _writer(backend):
        writer = CCodeWriter()
        writer.globalstate = SimpleNamespace(runtime_api=create_runtime_api(backend))
        writer.code_config = CCodeConfig()
        writer.funcstate = FunctionState(
            writer, scope=SimpleNamespace(name="global_load"))
        return writer

    def test_hpy_global_load_is_owned_temp_closed_exactly_once(self):
        writer = self._writer(HPY_UNIVERSAL_BACKEND)
        loaded = writer.load_runtime_global(
            py_object_type, "global_slot", "ctx")
        self.assertTrue(loaded.owns_local_reference)
        self.assertTrue(writer.funcstate.handle_temps.is_active(loaded.cname))
        writer.dispose_runtime_global_load(loaded)
        self.assertFalse(writer.funcstate.handle_temps.is_active(loaded.cname))
        writer.funcstate.validate_exit()
        output = writer.getvalue()
        self.assertIn("HPyGlobal_Load(ctx, global_slot)", output)
        self.assertIn("HPy_IsNull", output)
        self.assertIn("HPy_Close(ctx", output)
        with self.assertRaises(InvalidHandleTransitionError):
            writer.dispose_runtime_global_load(loaded)

    def test_cpython_global_load_remains_borrowed_expression(self):
        writer = self._writer("cpython")
        loaded = writer.load_runtime_global(py_object_type, "global_slot")
        self.assertEqual(loaded.cname, "global_slot")
        self.assertFalse(loaded.owns_local_reference)
        writer.dispose_runtime_global_load(loaded)
        writer.funcstate.validate_exit()
        self.assertEqual(writer.getvalue(), "")
