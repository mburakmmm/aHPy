# ADR 0001: Backend architecture and selection

- Status: accepted for bootstrap
- Date: 2026-07-14

## Context

Cython currently emits CPython C-API-oriented code from compiler nodes and a
large utility-code library. HPy differs in function names, calling conventions,
module/type definitions, object storage classes, ownership rules, and lifetime
constraints. A text-level conversion of generated CPython code cannot recover
these semantics reliably.

Cython PR #4490 explored a second code writer and later a collection of API
backend mappings. Maintainer feedback favored keeping syntax-specific structure
in compiler nodes, sharing code where semantics match, and avoiding duplicate
copies of generated user code.

## Decision

1. aHPy is developed on the current Cython source tree, not as a postprocessor.
2. Backend selection applies to a complete extension module.
3. Compiler nodes retain responsibility for syntax-specific code structure.
4. Runtime-dependent operations use a typed `RuntimeAPI` service with explicit
   capabilities and ownership contracts.
5. C macros/helpers may share operations only when CPython and HPy semantics are
   genuinely equivalent.
6. Structurally different operations such as builders, globals, module specs,
   type specs, and field traversal use backend-specific generation hooks.
7. The selected backend emits only its required runtime code. Universal builds
   do not carry a second CPython implementation behind preprocessor branches.
8. The existing CPython backend remains the regression oracle throughout the
   implementation.

## Consequences

- The first implementation work is backend-neutral refactoring.
- Handle storage and ownership must be modeled before broad feature support.
- Unsupported operations are capability errors, never implicit ABI changes.
- The design can be proposed upstream in small, independently testable changes.
