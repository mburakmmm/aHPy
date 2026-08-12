.. entry:: Fail-closed preview release contract validator
   :type: build

   Added a standalone text/JSON validator for the machine-readable release
   contract. It requires the exact package, Cython, HPy and Python identities;
   positive hosted evidence IDs; the six preview platform lanes; seven scoped
   build frontends; matching Universal workflow entries; and synchronized
   user-facing identity/evidence documentation. Unknown, missing or drifting
   values fail closed, and the Universal workflow invokes the validator before
   producing build evidence.
