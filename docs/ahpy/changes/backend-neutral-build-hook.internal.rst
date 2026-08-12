Remove aHPy's packaging-helper import from Cython's build core. Runtime backend
integrations now register an idempotent preparation hook through the public
``Cython.Build`` seam; conflicting hooks and invalid registrations fail closed,
while installed providers are discovered through a namespaced entry point and
the default CPython path remains inert.
