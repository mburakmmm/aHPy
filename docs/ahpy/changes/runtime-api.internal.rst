Added a context-local typed Runtime API, explicit ``cython`` backend selection,
actionable capability diagnostics, and output-neutral CPython reference/null
operation routing. Calls and container construction now use typed runtime
contracts, including HPy's distinct non-stealing list/tuple builder lifecycle.
Dynamic name resolution, registered global-storage metadata, and module-object
operations now cross the same boundary. The module-definition contract records
HPy's mandatory multi-phase init/exec structure and rejects CPython-only manual
creation and borrowed module-registry access. The Universal backend now enters
a strict bootstrap emitter through an explicit code-generation-kind contract;
the HPy CPython ABI lane remains unavailable.
Method layouts, method tables, type slots/specifications, and module
slots/definitions now use explicit structural hooks, with verified HPy
definitions and capability failures for unsupported mappings.
