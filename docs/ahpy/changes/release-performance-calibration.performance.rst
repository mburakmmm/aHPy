.. entry:: Fail-closed release performance calibration
   :type: performance

   Added exact source/GitHub run provenance to benchmark artifacts and a
   proposal-only calibration tool that requires at least five unique,
   successful hosted reports from one release commit and measurement cohort.
   Mixed commits, local evidence, duplicate attempts, budget violations, Debug
   failures, and non-reproducible footprint bytes are rejected before a
   release ceiling can be proposed. A manual read-only workflow now collects
   five isolated samples for one exact selected commit and aggregates only
   after the complete matrix succeeds. The proposal also validates and retains
   frontend/native build-time, peak-RSS, footprint, and large-type frontend/O0
   distributions without applying cross-host absolute limits. Platform,
   compiler command/flags, peak-memory iterations, and native timeout are part
   of the exact cohort identity; multiword compiler wrapper commands are
   parsed without losing the underlying compiler argument. Benchmark and
   proposal schemas are v3; older evidence without the complete budget-policy
   identity is rejected. The checked-in ceilings are machine-classified as
   regression-only, non-release, hosted-history-pending, and unbound to a
   candidate commit. Inconsistent policy combinations, mixed report policies,
   and CLI attempts to weaken the policy's five-report minimum fail closed.
   An approved release policy additionally requires GitHub Actions execution
   and exact equality between source commit and hosted GitHub SHA. It records
   the earlier calibration-source commit while the exact current candidate
   lives in the immutable report, avoiding an impossible self-referential Git
   hash inside the versioned policy. Local or stale-checkout runs cannot
   satisfy release performance gates.
   Schema-v3 benchmark artifacts now embed the complete validated budget
   contract rather than relying on a mutable file path. Calibration rejects
   compact-policy, environment, measurement, large-type enforcement, and
   cross-sample contract drift, then retains the exact input contract in the
   proposal for later audit.
   Regression contracts now reject uncalibrated absolute limits. Approved
   release contracts require six proposal-backed frontend/native build,
   generated peak-RSS/ratio, and large-type frontend/O0 ceilings; missing,
   non-finite, or exceeded evidence fails closed.
   Calibration proposals now include headroom-adjusted generated-source and
   generated-binary byte maxima. A separate read-only promotion validator
   proves that all ten runtime, three footprint, and six absolute release
   ceilings exactly match the reviewed schema-v3 proposal while rejecting
   contract, calibration-source, cohort-policy, and hosted-report-floor drift.
   Hosted samples and proposal aggregation also have explicit 90- and
   10-minute hard timeouts.
