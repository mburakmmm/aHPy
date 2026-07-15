# Release-note fragments

Every user-visible change adds one file named
`<issue-or-pr>.<category>.rst` in this directory. Before an issue or pull
request exists, use a descriptive lowercase identifier.

Allowed categories:

- `feature`
- `bugfix`
- `breaking`
- `diagnostic`
- `performance`
- `build`
- `documentation`
- `internal`

A fragment explains observable behavior, affected backend and support tier,
required migration, and newly added tests. It does not claim support beyond the
checked support matrix. Release preparation moves fragments into
`docs/ahpy/changelog.rst` and removes the consumed files.
