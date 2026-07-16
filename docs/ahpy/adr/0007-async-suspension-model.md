# ADR 0007: Native coroutine and async-generator suspension model

- Status: accepted design; blocked on the selected HPy 0.9 public API
- Date: 2026-07-16

## Context

Native coroutines and async generators share suspension mechanics with
generators but add awaitable delivery, cancellation, async iteration, injected
exceptions, and shutdown/finalization behavior. Cython's existing implementation
depends on CPython coroutine objects, code objects, exception triples, and
async slots. Those are not Universal HPy contracts, and HPy 0.9 does not expose
the public async protocol slots required to publish equivalent objects.

## Decision

1. Async state will use a dedicated pure-HPy object, not a flag on the
   synchronous generator implementation. Python values live across suspension
   only in traversed `HPyField`s; native resume/cancellation state contains no
   `HPyContext *`.
2. Every resume/await/cancel/close entry receives a fresh context and has one
   idempotent cleanup plan. Borrowed handles, trackers, builders, and unrecorded
   owned temporaries may not cross suspension.
3. Await result delivery, cancellation injection, `GeneratorExit`, async
   iteration termination, and finalization require public exception-state
   operations that preserve the exact active error. They will not be
   approximated through error clearing or CPython exception triples.
4. Async generators additionally require public async-iterator type slots and
   separate handling for yielded versus awaited values. Synchronous generator
   support does not imply this surface.
5. Until the selected HPy version supplies those contracts, top-level native
   coroutines and async generators receive a versioned diagnostic before the
   CPython `Coroutine.c` path or code-object generation can run.

## Enablement gate

The first enabled async subset needs normal/Trace/Debug semantics, cancellation
at every suspension point, never-awaited and partially-consumed cleanup,
injected failures, GC cycles, interpreter shutdown, subinterpreters, source and
binary audits, and CPython backend parity. Unsupported async context managers,
async comprehensions, delegation, hooks, or introspection remain diagnosed.

## Consequences

- M6 native coroutine and async-generator implementation remains open and
  externally blocked for HPy 0.9.
- ADR 0006's synchronous generator design may share low-level planning ideas
  but not public support status or cleanup assumptions.
- Private or legacy CPython async slots are never substituted.
