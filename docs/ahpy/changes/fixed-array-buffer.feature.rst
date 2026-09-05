Extend the validated Universal HPy buffer-producer subset to private,
positive, compile-time-sized one-dimensional native C arrays. All 13 enabled
integer/float formats compile in scalar and array layouts; retained writable
array views pass Normal, Trace, and Debug execution, and deterministic
``HPy_Dup`` failure covers both exporter layouts without admitting general
array fields or CPython buffer symbols.
