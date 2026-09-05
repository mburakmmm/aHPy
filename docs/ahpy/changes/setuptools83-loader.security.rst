Replace HPy 0.9's generated ``pkg_resources`` loader lookup with an adjacent
standard-library path before Universal stubs are emitted, allowing the pinned
Setuptools 83 security update while preserving unchanged ``.hpy0`` loading.

Refresh the reproducible documentation dependency lock to the first patched
Setuptools, SoupSieve, idna, urllib3, Pygments, and Requests releases reported
by the repository dependency graph.
