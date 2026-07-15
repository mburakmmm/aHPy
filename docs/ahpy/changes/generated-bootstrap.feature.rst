Enabled a strict Universal HPy bootstrap emitter for argument-free module
functions returning implemented scalar literals (``None``, booleans, signed
64-bit integers, finite floats, Unicode, and bytes), or empty, fixed-size, and
nested list/tuple literals over those values. Generated C uses
public HPy builders with ownership-checked item closing and reverse-order
failure cancellation, plus ownership-checked HPy dictionary insertion. It
also supports borrowed one-argument ``HPyFunc_O`` functions when the source
argument is positional-only, plus item and attribute reads with owned-error
cleanup, and zero/one-argument or bound-method calls. It passes `.hpy0`
normal/debug execution with explicit
leak detection; unsupported source forms receive positional diagnostics.
