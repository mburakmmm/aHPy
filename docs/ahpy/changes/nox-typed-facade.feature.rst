Add deterministic typed NOX facade generation from validated schema-1
``nox-hpy`` manifests.  Generated public APIs use named NOX types over the
``nox.hpy`` host boundary, expose explicit module/object cleanup, retain the
failing export identity in ``HPyError`` translation, and reject unsupported
host call shapes or name collisions without leaving partial output.
