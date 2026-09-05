# murmurhash scalar-boundary pilot

This maintained adapter is derived from the pinned upstream commit
`58831632dab79389a5cee7715fb688ef2297ff78` (MIT) and links its exact
`MurmurHash3.cpp` plus `MurmurHash3.h` sources. The integration runner verifies
the pristine checkout before copying those files.

The upstream Python API accepts `str` and `bytes`, which requires a buffer
pointer to cross the generated extension boundary and is unsupported by the
HPy 0.9 contract. This adapter deliberately exposes a fixed-width `uint64`
message and seed instead. The C++ shim serializes the integer into eight
little-endian bytes and keeps every pointer, buffer lifetime and call to
`MurmurHash3_x86_32` outside the Universal translation unit.

Both held and `with nogil` paths preserve the same MurmurHash3 result. This is
a partial scalar-boundary port and must not be reported as compatibility with
the complete upstream `hash(str | bytes)` API.
