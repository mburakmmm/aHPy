# M6 coroutine and async-generator HPy 0.9 gap validation

Date: 2026-07-16
Cython base: `b99cb0e3b5425e11414cadd24168a6cc850e8000`
Status: design accepted; implementation externally blocked

The focused emitter suite compiles one `async def` with `await` and one async
generator with `yield`. Each emits no C and reports exactly one source-located
diagnostic naming HPy 0.9's missing public async protocol/exception-state
surface and forbidding CPython coroutine utilities. ADR 0007 records the
field-backed async suspension, cancellation, cleanup, and enablement contract.

This is a diagnose-only gate, not an async support claim. Hosted memory,
shutdown, cancellation, and subinterpreter tests become mandatory only after a
selected HPy version exposes the prerequisite public API.
