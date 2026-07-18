The direct Universal build CLI now discovers the aHPy frontend from its own
repository location, so clean checkouts no longer require an inherited
``PYTHONPATH``. A subprocess regression executes the CLI from an unrelated
working directory with ``PYTHONPATH`` removed.
