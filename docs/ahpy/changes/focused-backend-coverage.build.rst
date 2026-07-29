The focused dual-interpreter coverage gate now requires 100% executable
Python-line coverage for the Universal backend, reports exact missing
lines/ranges in schema 2 artifacts, and traces measured modules from source to
avoid stale-extension blind spots.
Nested coverage self-tests now restore the outer trace function instead of
silently undercounting alphabetically later quality-tool tests.
The corrected dual-interpreter baseline raises the quality-tool CI floor from
41% to 50%.
Reproducibility and direct-build integration control flow now has focused
unit coverage above 97% without replacing their real hosted integration gates.
The build-system contract CLI's JSON, CMake, Meson, stdout, and file-output
branches are also covered while real CMake/Meson builds remain separate gates.
The portability artifact builder's reproducible flags, generated-source and
binary audits, copied loaders, hashes, sizes, manifest, and CLI resolution now
have focused control-flow coverage above 95%.
CMake/Meson tool discovery, contract preparation, build commands, artifact
selection, normal/Debug loading, reports, and CLI selection now have focused
control-flow coverage above 98%.
The isolated scikit-build-core wheel path now has focused coverage for pinned
dependency materialization, wheel/tag inspection, Universal source/binary
audits, install, normal/Debug execution, evidence output, and CLI reporting.
