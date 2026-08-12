Remove aHPy's packaging-helper import from Cython's build core. Runtime backend
integrations now register an idempotent preparation hook through the public
``Cython.Build`` seam; conflicting hooks and invalid registrations fail closed,
while the default CPython path remains inert.
