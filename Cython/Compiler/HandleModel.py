"""Compiler-visible HPy storage and ownership state.

The model is intentionally independent of C code generation.  It can therefore
reject invalid lifetime transitions before a backend chooses concrete syntax.
"""

from dataclasses import dataclass, replace
from enum import Enum


class HandleStorageKind(Enum):
    LOCAL = "local"
    FIELD = "field"
    GLOBAL = "global"
    CONTEXT_CONSTANT = "context-constant"


class HandleOwnership(Enum):
    OWNED = "owned"
    BORROWED_ARGUMENT = "borrowed-argument"
    IMMORTAL = "immortal"


class HandleState(Enum):
    LIVE = "live"
    MOVED = "moved"
    CLOSED = "closed"


class HandleTransfer(Enum):
    MOVE = "move"
    DUPLICATE = "duplicate"


class HandleExitKind(Enum):
    NORMAL = "normal"
    RETURN = "return"
    BREAK = "break"
    CONTINUE = "continue"
    GOTO = "goto"
    EXCEPTION = "exception"


class RuntimeFunctionKind(Enum):
    PURE_C = "pure-c"
    PYTHON_INTERACTING = "python-interacting"
    CALLBACK = "callback"
    CLOSURE = "closure"
    GENERATOR = "generator"
    PUBLIC_C_API = "public-c-api"


class ContextRequirementKind(Enum):
    NONE = "none"
    REQUIRED = "required"
    REJECTED = "rejected"


class HandleBuilderState(Enum):
    LIVE = "live"
    BUILT = "built"
    CANCELLED = "cancelled"


class HandleTrackerState(Enum):
    LIVE = "live"
    CLOSED = "closed"


class HandleArgumentEffect(Enum):
    BORROW = "borrow"
    CLOSE = "close"


class HandleOperation(Enum):
    """Semantic HPy operations exposed by the M1 Runtime API surface."""

    DUPLICATE = "duplicate"
    CLOSE = "close"
    CALL = "call"
    CALL_METHOD = "call-method"
    SEQUENCE_BUILDER_NEW = "sequence-builder-new"
    SEQUENCE_BUILDER_SET = "sequence-builder-set"
    SEQUENCE_BUILDER_BUILD = "sequence-builder-build"
    SEQUENCE_BUILDER_CANCEL = "sequence-builder-cancel"
    SEQUENCE_FROM_ARRAY = "sequence-from-array"
    SEQUENCE_PACK = "sequence-pack"
    DICT_NEW = "dict-new"
    DICT_SET_ITEM = "dict-set-item"
    DICT_SET_ITEM_STRING = "dict-set-item-string"
    DICT_COPY = "dict-copy"
    TO_PYTHON = "to-python"
    FROM_PYTHON = "from-python"
    ERROR_SET_OBJECT = "error-set-object"
    ERROR_SET_NONE = "error-set-none"
    ERROR_FORMAT = "error-format"
    EXCEPTION_MATCHES = "exception-matches"
    NAME_LOOKUP = "name-lookup"
    GLOBAL_LOAD = "global-load"
    GLOBAL_STORE = "global-store"
    FIELD_LOAD = "field-load"
    FIELD_STORE = "field-store"
    IMPORT_MODULE = "import-module"
    MODULE_SET_ATTR = "module-set-attr"
    MODULE_SET_ATTR_STRING = "module-set-attr-string"


class HandleModelError(ValueError):
    pass


class InvalidHandleStorageError(HandleModelError):
    pass


class InvalidHandleTransitionError(HandleModelError):
    pass


@dataclass(frozen=True)
class HandleStorage:
    kind: HandleStorageKind
    c_type_cname: str
    long_lived: bool
    directly_usable: bool
    load_returns_owned_local: bool
    requires_owner_object: bool
    requires_module_registration: bool


@dataclass(frozen=True)
class HandleValue:
    storage: HandleStorage
    ownership: HandleOwnership
    state: HandleState = HandleState.LIVE


@dataclass(frozen=True)
class HandleTemporaryBinding:
    cname: str
    identity: str
    ownership: HandleOwnership


@dataclass(frozen=True)
class HandleCleanupPlan:
    exit_kind: HandleExitKind
    close_names: tuple


@dataclass(frozen=True)
class RuntimeFunctionContext:
    function_name: str
    function_kind: RuntimeFunctionKind
    requirement: ContextRequirementKind
    parameter_type_cname: str = ""
    parameter_cname: str = ""


@dataclass(frozen=True)
class HandleBuilderBinding:
    cname: str
    identity: str
    state: HandleBuilderState = HandleBuilderState.LIVE


@dataclass(frozen=True)
class HandleTrackerBinding:
    cname: str
    identity: str
    state: HandleTrackerState = HandleTrackerState.LIVE




@dataclass(frozen=True)
class HandleOperationContract:
    operation: HandleOperation
    handle_arguments: tuple
    argument_effect: HandleArgumentEffect = HandleArgumentEffect.BORROW
    result_ownership: object = None
    result_storage: object = None
    produces_builder: bool = False
    consumes_builder: bool = False

    def __post_init__(self):
        if not isinstance(self.operation, HandleOperation):
            raise TypeError("expected HandleOperation, got %r" % (self.operation,))
        if not isinstance(self.argument_effect, HandleArgumentEffect):
            raise TypeError(
                "expected HandleArgumentEffect, got %r" %
                (self.argument_effect,))
        if (self.result_ownership is None) != (self.result_storage is None):
            raise ValueError(
                "handle result ownership and storage must be specified together")
        if self.result_ownership is not None:
            if not isinstance(self.result_ownership, HandleOwnership):
                raise TypeError(
                    "expected HandleOwnership result, got %r" %
                    (self.result_ownership,))
            if not isinstance(self.result_storage, HandleStorageKind):
                raise TypeError(
                    "expected HandleStorageKind result, got %r" %
                    (self.result_storage,))
        if self.produces_builder and self.consumes_builder:
            raise ValueError("one operation cannot both produce and consume a builder")


_STORAGE_CONTRACTS = {
    HandleStorageKind.LOCAL: HandleStorage(
        HandleStorageKind.LOCAL, "HPy",
        long_lived=False,
        directly_usable=True,
        load_returns_owned_local=False,
        requires_owner_object=False,
        requires_module_registration=False,
    ),
    HandleStorageKind.FIELD: HandleStorage(
        HandleStorageKind.FIELD, "HPyField",
        long_lived=True,
        directly_usable=False,
        load_returns_owned_local=True,
        requires_owner_object=True,
        requires_module_registration=False,
    ),
    HandleStorageKind.GLOBAL: HandleStorage(
        HandleStorageKind.GLOBAL, "HPyGlobal",
        long_lived=True,
        directly_usable=False,
        load_returns_owned_local=True,
        requires_owner_object=False,
        requires_module_registration=True,
    ),
    HandleStorageKind.CONTEXT_CONSTANT: HandleStorage(
        HandleStorageKind.CONTEXT_CONSTANT, "HPy",
        long_lived=False,
        directly_usable=True,
        load_returns_owned_local=False,
        requires_owner_object=False,
        requires_module_registration=False,
    ),
}


def _borrowed(operation, arguments=(), *, returns_owned=False,
              produces_builder=False, consumes_builder=False):
    return HandleOperationContract(
        operation=operation,
        handle_arguments=tuple(arguments),
        result_ownership=(HandleOwnership.OWNED if returns_owned else None),
        result_storage=(HandleStorageKind.LOCAL if returns_owned else None),
        produces_builder=produces_builder,
        consumes_builder=consumes_builder,
    )


_OPERATION_CONTRACTS = {
    HandleOperation.DUPLICATE:
        _borrowed(HandleOperation.DUPLICATE, ("source",), returns_owned=True),
    HandleOperation.CLOSE: HandleOperationContract(
        HandleOperation.CLOSE, ("handle",), HandleArgumentEffect.CLOSE),
    HandleOperation.CALL:
        _borrowed(HandleOperation.CALL, ("callable", "arguments", "keywords"),
                  returns_owned=True),
    HandleOperation.CALL_METHOD:
        _borrowed(HandleOperation.CALL_METHOD, ("name", "arguments"),
                  returns_owned=True),
    HandleOperation.SEQUENCE_BUILDER_NEW:
        _borrowed(HandleOperation.SEQUENCE_BUILDER_NEW, produces_builder=True),
    HandleOperation.SEQUENCE_BUILDER_SET:
        _borrowed(HandleOperation.SEQUENCE_BUILDER_SET, ("item",)),
    HandleOperation.SEQUENCE_BUILDER_BUILD:
        _borrowed(HandleOperation.SEQUENCE_BUILDER_BUILD,
                  returns_owned=True, consumes_builder=True),
    HandleOperation.SEQUENCE_BUILDER_CANCEL:
        _borrowed(HandleOperation.SEQUENCE_BUILDER_CANCEL,
                  consumes_builder=True),
    HandleOperation.SEQUENCE_FROM_ARRAY:
        _borrowed(HandleOperation.SEQUENCE_FROM_ARRAY, ("items",),
                  returns_owned=True),
    HandleOperation.SEQUENCE_PACK:
        _borrowed(HandleOperation.SEQUENCE_PACK, ("items",),
                  returns_owned=True),
    HandleOperation.DICT_NEW:
        _borrowed(HandleOperation.DICT_NEW, returns_owned=True),
    HandleOperation.DICT_SET_ITEM:
        _borrowed(HandleOperation.DICT_SET_ITEM,
                  ("dictionary", "key", "value")),
    HandleOperation.DICT_SET_ITEM_STRING:
        _borrowed(HandleOperation.DICT_SET_ITEM_STRING,
                  ("dictionary", "value")),
    HandleOperation.DICT_COPY:
        _borrowed(HandleOperation.DICT_COPY, ("dictionary",),
                  returns_owned=True),
    HandleOperation.TO_PYTHON:
        _borrowed(HandleOperation.TO_PYTHON, returns_owned=True),
    HandleOperation.FROM_PYTHON:
        _borrowed(HandleOperation.FROM_PYTHON, ("source",)),
    HandleOperation.ERROR_SET_OBJECT:
        _borrowed(HandleOperation.ERROR_SET_OBJECT, ("exception", "value")),
    HandleOperation.ERROR_SET_NONE:
        _borrowed(HandleOperation.ERROR_SET_NONE, ("exception", "none")),
    HandleOperation.ERROR_FORMAT:
        _borrowed(HandleOperation.ERROR_FORMAT, ("exception", "format-values")),
    HandleOperation.EXCEPTION_MATCHES:
        _borrowed(HandleOperation.EXCEPTION_MATCHES, ("pattern",)),
    HandleOperation.NAME_LOOKUP:
        _borrowed(HandleOperation.NAME_LOOKUP, ("namespace", "name"),
                  returns_owned=True),
    HandleOperation.GLOBAL_LOAD:
        _borrowed(HandleOperation.GLOBAL_LOAD, returns_owned=True),
    HandleOperation.GLOBAL_STORE:
        _borrowed(HandleOperation.GLOBAL_STORE, ("value",)),
    HandleOperation.FIELD_LOAD:
        _borrowed(HandleOperation.FIELD_LOAD, ("owner",), returns_owned=True),
    HandleOperation.FIELD_STORE:
        _borrowed(HandleOperation.FIELD_STORE, ("owner", "value")),
    HandleOperation.IMPORT_MODULE:
        _borrowed(HandleOperation.IMPORT_MODULE, returns_owned=True),
    HandleOperation.MODULE_SET_ATTR:
        _borrowed(HandleOperation.MODULE_SET_ATTR,
                  ("module", "name", "value")),
    HandleOperation.MODULE_SET_ATTR_STRING:
        _borrowed(HandleOperation.MODULE_SET_ATTR_STRING,
                  ("module", "value")),
}


if frozenset(_OPERATION_CONTRACTS) != frozenset(HandleOperation):
    raise AssertionError("every HPy handle operation requires an ownership contract")


def operation_contract(operation):
    if not isinstance(operation, HandleOperation):
        raise TypeError("expected HandleOperation, got %r" % (operation,))
    return _OPERATION_CONTRACTS[operation]


class ContextPropagationModel:
    """Call-scoped HPyContext requirements for generated C functions."""

    _REQUIREMENTS = {
        RuntimeFunctionKind.PURE_C: ContextRequirementKind.NONE,
        RuntimeFunctionKind.PYTHON_INTERACTING: ContextRequirementKind.REQUIRED,
        RuntimeFunctionKind.CALLBACK: ContextRequirementKind.REJECTED,
        RuntimeFunctionKind.CLOSURE: ContextRequirementKind.REJECTED,
        RuntimeFunctionKind.GENERATOR: ContextRequirementKind.REJECTED,
        RuntimeFunctionKind.PUBLIC_C_API: ContextRequirementKind.REJECTED,
    }

    def __init__(self):
        self._functions = {}

    def declare_function(self, function_name, function_kind):
        if not isinstance(function_kind, RuntimeFunctionKind):
            raise TypeError(
                "expected RuntimeFunctionKind, got %r" % (function_kind,))
        if function_name in self._functions:
            raise HandleModelError(
                "runtime function %r is already declared" % function_name)
        requirement = self._REQUIREMENTS[function_kind]
        context = RuntimeFunctionContext(
            function_name,
            function_kind,
            requirement,
            parameter_type_cname=(
                "HPyContext *"
                if requirement is ContextRequirementKind.REQUIRED else ""),
            parameter_cname=(
                "ctx"
                if requirement is ContextRequirementKind.REQUIRED else ""),
        )
        self._functions[function_name] = context
        return context

    def function(self, function_name):
        try:
            return self._functions[function_name]
        except KeyError:
            raise HandleModelError(
                "unknown runtime function %r" % function_name) from None

    def require_enabled(self, function_name):
        context = self.function(function_name)
        if context.requirement is ContextRequirementKind.REJECTED:
            raise HandleModelError(
                "%s context propagation is not defined for %s functions" % (
                    context.function_kind.value, function_name))
        return context

    def call_context_argument(self, caller_name, callee_name):
        caller = self.require_enabled(caller_name)
        callee = self.require_enabled(callee_name)
        if callee.requirement is ContextRequirementKind.NONE:
            return ""
        if caller.requirement is not ContextRequirementKind.REQUIRED:
            raise HandleModelError(
                "pure-C function %r cannot call context-requiring function %r" %
                (caller_name, callee_name))
        return caller.parameter_cname

    def persist_context(self, function_name, storage_description):
        context = self.require_enabled(function_name)
        if context.requirement is not ContextRequirementKind.REQUIRED:
            raise HandleModelError(
                "function %r has no HPyContext to persist" % function_name)
        raise InvalidHandleStorageError(
            "HPyContext * from %r is call-scoped and cannot be persisted in %s" %
            (function_name, storage_description))


def storage_contract(kind):
    if not isinstance(kind, HandleStorageKind):
        raise TypeError("expected HandleStorageKind, got %r" % (kind,))
    return _STORAGE_CONTRACTS[kind]


def validate_storage_declaration(
    kind,
    c_type_cname,
    *,
    is_function_local=False,
    is_long_lived=False,
):
    contract = storage_contract(kind)
    if c_type_cname != contract.c_type_cname:
        raise InvalidHandleStorageError(
            "%s storage requires C type %s, not %s" % (
                kind.value, contract.c_type_cname, c_type_cname))
    if is_function_local and kind in (
        HandleStorageKind.FIELD, HandleStorageKind.GLOBAL,
    ):
        raise InvalidHandleStorageError(
            "%s cannot be declared as function-local storage" % c_type_cname)
    if is_long_lived and c_type_cname == "HPy":
        raise InvalidHandleStorageError(
            "plain HPy cannot be stored across calls; use HPyField or HPyGlobal")
    if is_long_lived != contract.long_lived:
        expected = "long-lived" if contract.long_lived else "call-scoped"
        raise InvalidHandleStorageError(
            "%s storage must be declared %s" % (kind.value, expected))
    return contract


class HandleStateTracker:
    """Tracks HPy values and indirect storage within one control-flow state."""

    def __init__(self):
        self._storage = {}
        self._values = {}

    def _require_new_name(self, name):
        if name in self._storage or name in self._values:
            raise HandleModelError("handle name %r is already declared" % name)

    def declare_storage(self, name, kind, c_type_cname=None):
        self._require_new_name(name)
        contract = storage_contract(kind)
        c_type_cname = c_type_cname or contract.c_type_cname
        contract = validate_storage_declaration(
            kind,
            c_type_cname,
            is_function_local=False,
            is_long_lived=contract.long_lived,
        )
        self._storage[name] = contract
        return contract

    def declare_value(self, name, storage_kind, ownership, c_type_cname=None):
        self._require_new_name(name)
        if not isinstance(ownership, HandleOwnership):
            raise TypeError("expected HandleOwnership, got %r" % (ownership,))
        contract = storage_contract(storage_kind)
        c_type_cname = c_type_cname or contract.c_type_cname
        validate_storage_declaration(
            storage_kind,
            c_type_cname,
            is_function_local=True,
            is_long_lived=False,
        )
        if not contract.directly_usable:
            raise InvalidHandleStorageError(
                "%s is indirect storage; load it into a local HPy before use" %
                storage_kind.value)
        if storage_kind is HandleStorageKind.LOCAL:
            if ownership is HandleOwnership.IMMORTAL:
                raise InvalidHandleStorageError(
                    "immortal handles must be declared as context constants")
        elif storage_kind is HandleStorageKind.CONTEXT_CONSTANT:
            if ownership is not HandleOwnership.IMMORTAL:
                raise InvalidHandleStorageError(
                    "context constants must have immortal ownership")
        value = HandleValue(contract, ownership)
        self._values[name] = value
        return value

    def value(self, name):
        try:
            return self._values[name]
        except KeyError:
            raise HandleModelError("unknown local handle %r" % name) from None

    def storage(self, name):
        try:
            return self._storage[name]
        except KeyError:
            raise HandleModelError("unknown indirect storage %r" % name) from None

    def use(self, name):
        value = self.value(name)
        if value.state is not HandleState.LIVE:
            raise InvalidHandleTransitionError(
                "cannot use %s handle %r" % (value.state.value, name))
        return value

    def _consume_owned(self, name, target_state, operation):
        value = self.use(name)
        if value.ownership is not HandleOwnership.OWNED:
            raise InvalidHandleTransitionError(
                "cannot %s %s handle %r; duplicate it first" % (
                    operation, value.ownership.value, name))
        value = replace(value, state=target_state)
        self._values[name] = value
        return value

    def close(self, name):
        return self._consume_owned(name, HandleState.CLOSED, "close")

    def move(self, name):
        return self._consume_owned(name, HandleState.MOVED, "move")

    def duplicate(self, source_name, target_name):
        self.use(source_name)
        return self.declare_value(
            target_name, HandleStorageKind.LOCAL, HandleOwnership.OWNED)

    def apply_operation(self, operation, argument_names=(), result_name=None):
        """Apply one operation contract to concrete compiler value names."""
        contract = operation_contract(operation)
        argument_names = tuple(argument_names)
        if contract.argument_effect is HandleArgumentEffect.CLOSE:
            if len(argument_names) != 1:
                raise HandleModelError(
                    "%s requires exactly one handle argument" % operation.value)
            self.close(argument_names[0])
        else:
            for argument_name in argument_names:
                self.use(argument_name)

        if contract.result_ownership is None:
            if result_name is not None:
                raise HandleModelError(
                    "%s does not produce a handle result" % operation.value)
            return None
        if result_name is None:
            raise HandleModelError(
                "%s requires a result handle name" % operation.value)
        return self.declare_value(
            result_name,
            contract.result_storage,
            contract.result_ownership,
        )

    def load_storage(self, storage_name, target_name):
        contract = self.storage(storage_name)
        if not contract.load_returns_owned_local:
            raise InvalidHandleStorageError(
                "%s storage has no owned-load operation" % contract.kind.value)
        return self.declare_value(
            target_name, HandleStorageKind.LOCAL, HandleOwnership.OWNED)

    def store_storage(self, storage_name, value_name):
        contract = self.storage(storage_name)
        if contract.kind not in (
            HandleStorageKind.FIELD, HandleStorageKind.GLOBAL,
        ):
            raise InvalidHandleStorageError(
                "%s storage has no long-lived store operation" %
                contract.kind.value)
        return self.use(value_name)

    def prepare_return(self, name):
        value = self.use(name)
        if value.ownership is HandleOwnership.OWNED:
            self.move(name)
            return HandleTransfer.MOVE
        return HandleTransfer.DUPLICATE

    def cleanup_plan(self, exit_kind, preserve_names=()):
        if not isinstance(exit_kind, HandleExitKind):
            raise TypeError("expected HandleExitKind, got %r" % (exit_kind,))
        preserve_names = frozenset(preserve_names)
        for name in preserve_names:
            self.use(name)
        close_names = tuple(
            name for name, value in reversed(tuple(self._values.items()))
            if value.ownership is HandleOwnership.OWNED
            and value.state is HandleState.LIVE
            and name not in preserve_names
        )
        return HandleCleanupPlan(exit_kind, close_names)

    def apply_cleanup_plan(self, plan):
        if not isinstance(plan, HandleCleanupPlan):
            raise TypeError("expected HandleCleanupPlan, got %r" % (plan,))
        for name in plan.close_names:
            self.close(name)

    def fork(self):
        result = HandleStateTracker()
        result._storage = self._storage.copy()
        result._values = self._values.copy()
        return result

    @classmethod
    def merge(cls, *branches):
        if not branches:
            raise HandleModelError("at least one handle-state branch is required")
        if not all(isinstance(branch, cls) for branch in branches):
            raise TypeError("all merged branches must be HandleStateTracker values")
        first = branches[0]
        for branch in branches[1:]:
            if branch._storage != first._storage:
                raise InvalidHandleTransitionError(
                    "indirect handle storage differs across control-flow branches")
            if frozenset(branch._values) != frozenset(first._values):
                raise InvalidHandleTransitionError(
                    "handle values differ across control-flow branches")
            for name, first_value in first._values.items():
                branch_value = branch._values[name]
                if branch_value != first_value:
                    raise InvalidHandleTransitionError(
                        "handle %r has incompatible branch states %s and %s; "
                        "emit matching cleanup before merging" % (
                            name, first_value.state.value,
                            branch_value.state.value))
        return first.fork()

    def live_owned_handles(self):
        return tuple(sorted(
            name for name, value in self._values.items()
            if value.ownership is HandleOwnership.OWNED
            and value.state is HandleState.LIVE
        ))

    def assert_no_live_owned_handles(self):
        live = self.live_owned_handles()
        if live:
            raise InvalidHandleTransitionError(
                "owned handles remain live at control-flow exit: %s" %
                ", ".join(live))


class HandleTemporaryManager:
    """Maps reusable C temporary slots to distinct HPy handle lifetimes."""

    def __init__(self):
        self.state = HandleStateTracker()
        self._active = {}
        self._generations = {}

    def allocate(self, cname, ownership):
        if cname in self._active:
            raise HandleModelError(
                "handle temporary %r is already allocated" % cname)
        generation = self._generations.get(cname, 0) + 1
        self._generations[cname] = generation
        identity = "%s#%d" % (cname, generation)
        self.state.declare_value(
            identity, HandleStorageKind.LOCAL, ownership)
        binding = HandleTemporaryBinding(cname, identity, ownership)
        self._active[cname] = binding
        return binding

    def binding(self, cname):
        try:
            return self._active[cname]
        except KeyError:
            raise HandleModelError(
                "handle temporary %r is not allocated" % cname) from None

    def is_active(self, cname):
        return cname in self._active

    def use(self, cname):
        return self.state.use(self.binding(cname).identity)

    def close(self, cname):
        return self.state.close(self.binding(cname).identity)

    def move(self, cname):
        return self.state.move(self.binding(cname).identity)

    def release(self, cname):
        binding = self.binding(cname)
        value = self.state.value(binding.identity)
        if (value.ownership is HandleOwnership.OWNED and
                value.state is HandleState.LIVE):
            raise InvalidHandleTransitionError(
                "cannot release live owned handle temporary %r; "
                "close or move it first" % cname)
        del self._active[cname]
        return value

    def active_cnames(self):
        return tuple(sorted(self._active))

    def live_owned_handles(self):
        return tuple(sorted(
            cname for cname, binding in self._active.items()
            if self.state.value(binding.identity).ownership is HandleOwnership.OWNED
            and self.state.value(binding.identity).state is HandleState.LIVE
        ))

    def assert_no_live_owned_handles(self):
        live = self.live_owned_handles()
        if live:
            raise InvalidHandleTransitionError(
                "owned handle temporaries remain live at function exit: %s" %
                ", ".join(live))


class HandleBuilderManager:
    """Tracks non-handle HPy list/tuple builder resources."""

    def __init__(self):
        self._active = {}
        self._generations = {}

    def allocate(self, cname):
        if cname in self._active:
            raise HandleModelError(
                "HPy builder temporary %r is already allocated" % cname)
        generation = self._generations.get(cname, 0) + 1
        self._generations[cname] = generation
        binding = HandleBuilderBinding(
            cname, "%s#%d" % (cname, generation))
        self._active[cname] = binding
        return binding

    def binding(self, cname):
        try:
            return self._active[cname]
        except KeyError:
            raise HandleModelError(
                "HPy builder temporary %r is not allocated" % cname) from None

    def is_active(self, cname):
        return cname in self._active

    def use(self, cname):
        binding = self.binding(cname)
        if binding.state is not HandleBuilderState.LIVE:
            raise InvalidHandleTransitionError(
                "cannot use %s HPy builder %r" %
                (binding.state.value, cname))
        return binding

    def _finish(self, cname, state):
        binding = self.use(cname)
        binding = replace(binding, state=state)
        self._active[cname] = binding
        return binding

    def build(self, cname):
        return self._finish(cname, HandleBuilderState.BUILT)

    def cancel(self, cname):
        return self._finish(cname, HandleBuilderState.CANCELLED)

    def release(self, cname):
        binding = self.binding(cname)
        if binding.state is HandleBuilderState.LIVE:
            raise InvalidHandleTransitionError(
                "cannot release live HPy builder %r; build or cancel it first" %
                cname)
        del self._active[cname]
        return binding

    def live_builders(self):
        return tuple(sorted(
            cname for cname, binding in self._active.items()
            if binding.state is HandleBuilderState.LIVE
        ))

    def assert_no_live_builders(self):
        live = self.live_builders()
        if live:
            raise InvalidHandleTransitionError(
                "HPy builders remain live at function exit: %s" %
                ", ".join(live))


class HandleTrackerManager:
    """Tracks HPyTracker resources that own parsed argument handles."""

    def __init__(self):
        self._active = {}
        self._generations = {}

    def allocate(self, cname):
        if cname in self._active:
            raise HandleModelError(
                "HPy tracker %r is already allocated" % cname)
        generation = self._generations.get(cname, 0) + 1
        self._generations[cname] = generation
        binding = HandleTrackerBinding(
            cname, "%s#%d" % (cname, generation))
        self._active[cname] = binding
        return binding

    def binding(self, cname):
        try:
            return self._active[cname]
        except KeyError:
            raise HandleModelError(
                "HPy tracker %r is not allocated" % cname) from None

    def use(self, cname):
        binding = self.binding(cname)
        if binding.state is not HandleTrackerState.LIVE:
            raise InvalidHandleTransitionError(
                "cannot use %s HPy tracker %r" %
                (binding.state.value, cname))
        return binding

    def close(self, cname):
        binding = self.use(cname)
        binding = replace(binding, state=HandleTrackerState.CLOSED)
        self._active[cname] = binding
        return binding

    def release(self, cname):
        binding = self.binding(cname)
        if binding.state is HandleTrackerState.LIVE:
            raise InvalidHandleTransitionError(
                "cannot release live HPy tracker %r; close it first" % cname)
        del self._active[cname]
        return binding

    def is_active(self, cname):
        return cname in self._active

    def live_trackers(self):
        return tuple(sorted(
            cname for cname, binding in self._active.items()
            if binding.state is HandleTrackerState.LIVE
        ))

    def assert_no_live_trackers(self):
        live = self.live_trackers()
        if live:
            raise InvalidHandleTransitionError(
                "HPy trackers remain live at function exit: %s" %
                ", ".join(live))
