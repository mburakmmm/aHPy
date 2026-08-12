The direct Universal build fallback linker command no longer inherits
compile-only optimization, PIC, definition, or include flags when the
selected HPy toolchain does not provide ``LDSHARED``; compiler and linker
argument lists are now constructed independently and covered by a regression
test.
