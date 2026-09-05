# frozenlist extension-type / GC / inheritance pilot

This maintained port is derived from `aio-libs/frozenlist` commit
`351ad4bb62b30d943b0aa7463a0f85f7339b6ada` under Apache-2.0. The integration
runner verifies the pristine upstream checkout, source hash and license before
building this fixture.

Recorded transformations:

1. replace `atomic[bint]` with a supported native `bint`; this pilot does not
   claim upstream free-threading synchronization semantics;
2. replace `PyBool_FromLong` with ordinary `bool()` through the public HPy
   boundary;
3. store `_items` as an object-valued HPy field instead of an extension-typed
   `list` field;
4. lower private `cdef` helpers to ordinary methods while preserving their
   success and exception behavior;
5. omit iterator-only, rich-comparison, copy/deepcopy and MutableSequence
   registration surfaces that are outside the HPy 0.9 preview contract;
6. add a same-module derived type solely to exercise supported field,
   constructor, mutation, freeze and cleanup inheritance.

The result is a supported-subset port, not a claim that the complete upstream
API or free-threading contract is compatible.
