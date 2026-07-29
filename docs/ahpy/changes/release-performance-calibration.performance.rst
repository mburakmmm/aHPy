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
   of the exact cohort identity.
