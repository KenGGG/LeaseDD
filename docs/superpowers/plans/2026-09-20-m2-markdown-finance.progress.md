# Progress — plan: docs/superpowers/plans/2026-09-20-m2-markdown-finance.md

Environment: no usable Git repository metadata is mounted, so commits/worktrees and the standard SDD workspace scripts cannot be used. Progress is tracked here and by test evidence.
Pre-flight: Task 1 models feed Tasks 3/4/5; Task 2 artifacts feed Tasks 3/4; Task 3 persistence feeds Tasks 4/5; interfaces are consistent with the goal.
Ruling: MarkItDown will be installed in the worker image as the same upstream package/version family already present on the host; calling the host CLI from a container is not reliable. Cost if wrong: a larger worker image.

Completed 2026-09-20: Tasks 1–6. All 76 tests pass (2 environment-dependent skips), frontend builds, browser M0/M1 regression passes, and Compose is deployed. Public PDF and a rasterized public financial-statement page both pass real MinerU conversion. Live DOCX/XLSX → MarkItDown → Agnes → PostgreSQL → API flows pass with all six fixture items source-verified. Evidence and remaining product-scope limits are recorded in `docs/acceptance/M2.md`.
