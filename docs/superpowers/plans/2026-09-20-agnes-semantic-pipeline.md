# Agnes Semantic Pipeline Implementation Plan

> **For agentic workers:** Use executing-plans task by task; independent structure, transport and benchmark modules may be implemented in parallel.

**Goal:** Make authorized recognition Agnes-led while retaining deterministic financial evidence validation and immutable history.
**Architecture:** A structural document map feeds semantic interpretation then whole-row extraction. Source coordinates, independent local results and completeness checks gate financial candidates. Shared transport enforces the model budget; stage artifacts provide resumability.
**Tech Stack:** Python 3.12, Pydantic, SQLAlchemy/PostgreSQL, FastAPI, existing React UI.
**Spec:** `docs/superpowers/specs/2026-09-20-agnes-semantic-pipeline.md`

## Global Constraints

- No company-specific production rules or external-reference backfill.
- No model calls without task-snapshot authorization; no credential/response-body logging.
- Source values and historical runs remain immutable; unverified/conflicting candidates cannot feed automatic formulas.
- Agnes limits: 20 RPM maximum, 18 default, 512000 context budget, 65000 maximum output; byte-based conservative input estimate explicitly labelled.
- No claim of real cross-company acceptance from synthetic fixtures.

## Review Focus

- A correct number assigned to the wrong year/scope/cell must not be marked verified.
- A partially recognized local table must not prevent Agnes from seeing the remaining tables.
- Repeated headings/merged cells/continuation pages must preserve physical provenance.
- HTTP retries, task retries and restart recovery must not cause unlimited duplicate calls.
- New extraction must not silently erase existing historical or human-reviewed candidates.

## Tasks

- [x] Structural document discovery: `document_structure.py`, `test_document_structure.py`; `build_document_map(markdown)` yields exact physical cell origins, no financial classification. Tests cover HTML spans, Markdown and duplicate cells.
- [x] Agnes transport: `agnes_client.py`, `test_agnes_client.py`; `AgnesClient(config, db_factory)(stage,payload,system=...,max_tokens=...)`. Test rolling window, shared Retry-After, bounded attempts, safe errors, output truncation.
- [x] Semantic contracts and validation: `financial_semantics.py`, schema exports, tests. Reject mismatched source cells and unsupported metadata; retain nullable concept/unmapped rows and raw values. Table/column coordinates remain stable across chunking.
- [x] Pipeline and checkpoints: `semantic_pipeline.py`, `extraction_stages.py`, tests. Map→interpret→extract→targeted completeness repair; reuse successful stages and enforce per-stage total attempt budgets.
- [x] Worker/history integration: `worker.py`, `db.py`, migration, API routes and tests. Authorized tasks use new pipeline, retain explicit offline path, renew leases, freeze inputs, publish a separate extraction batch atomically. Existing data remains accessible by run.
- [x] WebUI: concise recognition mode and quality state, intentional re-recognition and read-only verification summary; no full developer diagnostics in default financial table.
- [x] Benchmark: `extraction_benchmark.py`, manifest/example and tests, company-separated holdout and explicit false-verified metric.
- [x] Full tests/build, isolated live model smoke using synthetic material, deploy only after migration/rollback checks, document real-data benchmark gaps.

Each production module starts with regression tests, observes the expected failure, then passes its focused tests. Final verification runs the complete suite and browser/build checks. This workspace has no Git repository; retain a local pre-change archive instead of claiming commits.

## Delivery record

Implemented and deployed to the existing LAN service on 2026-09-20. Backend: 210 passed, 3 PostgreSQL-dependent skips; separate live PostgreSQL concurrency/migration checks passed. Frontend: 12 tests and production build passed. Actual deployed browser checks passed. Real Agnes synthetic development fixture: 36/36 source cells reconciled, 34 VERIFIED and 2 UNMAPPED. Real cross-company holdout acceptance remains explicitly unavailable, not counted as passed. See `docs/acceptance/agnes-semantic-2026-09-20.md`.
