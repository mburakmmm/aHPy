Universal HPy now emits ``assert`` through public ``ctx->h_AssertionError``
(with optional message) under ``#ifndef CYTHON_WITHOUT_ASSERTIONS``, and emits
counted ``for i in range(...)`` / ``for i from ...`` loops as
``HPy_ssize_t`` C for-loops that publish each index via
``HPyLong_FromSsize_t``. List/dict comprehensions over constant ``range``
forms reuse the same counted-loop path. Typed C loop targets remain rejected
with an actionable diagnostic until a Universal C-local model exists.
