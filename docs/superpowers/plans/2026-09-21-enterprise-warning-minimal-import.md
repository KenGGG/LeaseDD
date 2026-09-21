# Enterprise Warning Minimal Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual, administrator-triggered path that imports the 17 verified 企业预警通 financial modules into LeaseDD without Agnes and exposes them through the existing financial workspace.

**Architecture:** A thin Playwright adapter reuses the Quantradar persistent-browser pattern and returns module-level JSON. Three new SQLAlchemy entities store the binding, one import, and one payload per module. Existing Task/worker infrastructure runs the import; read adapters convert the three statements into the current API view and reuse the seven deterministic checks without persisting projection rows.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, Playwright, pytest, React 19, TypeScript/Vite.

**Spec:** `docs/superpowers/specs/2026-09-21-enterprise-warning-financial-import.md`

## Global Constraints

- Work directly on `main`; do not create a worktree or delegate to subagents.
- Keep exactly three new persistent entities: `EnterpriseBinding`, `EnterpriseImport`, `EnterpriseFinancialData`.
- Keep project creation unchanged; import is manually triggered from the financial page by an administrator.
- Reuse `Task`/worker with only `kind="enterprise_import"`, `mode="qyyjt"` added.
- Persist one raw JSON payload per module; never persist one row per financial cell.
- Do not create statement projection tables or fake `Document`, `DocumentConversion`, or `ExtractionRun` rows.
- Do not invoke Agnes anywhere on the enterprise-import path.
- Keep exactly four enterprise API routes from the spec.
- Formula conflicts are warnings and never mutate source values or fail an otherwise complete import.
- Do not migrate the existing 铭普光磁 project.
- Preserve unrelated working-tree changes in `src/leasedd/financial_semantics.py`, `tests/test_semantic_pipeline.py`, and M2 acceptance artifacts.

## Review Focus

- A successful HTTP response containing a login page or invalid response shape must become `login_expired` or `structure_changed`, never an empty successful module.
- Search returning multiple candidates must return all candidates and must not bind the first one implicitly.
- A single missing module among the required 17 must produce `partial` with the exact failed module and preserve the other 16 payloads.
- A bound project with enterprise data must not merge PDF-derived statements into its current statement response.
- An unmapped or ambiguous line item must remain visible under its source name but must not become a formula input.

---

### Task 1: Add the three persistence entities and request contracts

**Files:**
- Modify: `src/leasedd/db.py`
- Modify: `src/leasedd/contracts.py`
- Create: `deployment/migrations/versions/0005_enterprise_import.py`
- Create: `tests/test_enterprise_models.py`

**Interfaces:**
- Produces: `EnterpriseBinding`, `EnterpriseImport`, `EnterpriseFinancialData` SQLAlchemy models.
- Produces: `EnterpriseImportRequest(query: str | None, company_code: str | None, company_name: str | None)`.

- [ ] **Step 1: Write failing model and migration tests**

Add tests that create an in-memory database and prove:

```python
binding = EnterpriseBinding(
    project_id=project.id,
    company_code="company-1",
    company_name="测试公司",
    identity={"symbol": "000001"},
    created_by=user.id,
    created_at=1.0,
)
db.add(binding)
db.flush()
assert db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id == project.id)) == binding
```

The tests must also assert the unique constraints `(project_id)`, `(task_id)`, and `(import_id, module_key)`, and that raw payload JSON containing `None` round-trips without becoming `0`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_enterprise_models.py -q`

Expected: collection fails because the three models do not exist.

- [ ] **Step 3: Implement only the three models and migration**

Use these columns:

```text
EnterpriseBinding:
  id, project_id(unique FK), company_code, company_name, identity(JSON),
  created_by(FK), created_at

EnterpriseImport:
  id, project_id(FK), task_id(unique FK), state, quality_state,
  module_status(JSON), error, content_sha256, started_at, completed_at

EnterpriseFinancialData:
  id, import_id(FK), category, module_key, module_name, module_order,
  endpoint_path, request_params(JSON), raw_payload(JSON), parsed_payload(JSON),
  response_sha256, state, error, collected_at,
  unique(import_id, module_key)
```

Add migration `0005` after `0004`. Add Playwright to production dependencies in `pyproject.toml`; do not add another browser library.

- [ ] **Step 4: Extend request contracts minimally**

```python
class EnterpriseImportRequest(Contract):
    query: str | None = Field(default=None, min_length=1, max_length=200)
    company_code: str | None = Field(default=None, min_length=1, max_length=100)
    company_name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_choice(self):
        if self.company_code and not self.company_name:
            raise ValueError("company_name_required")
        return self
```

Do not extend the public `CreateTask` contract: enterprise tasks are created only through the administrator-only import and retry routes.

- [ ] **Step 5: Run focused and migration tests**

Run: `pytest tests/test_enterprise_models.py tests/test_platform.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/leasedd/db.py src/leasedd/contracts.py deployment/migrations/versions/0005_enterprise_import.py tests/test_enterprise_models.py
git commit -m "feat: add enterprise financial import storage"
```

---

### Task 2: Implement the thin 企业预警通 adapter and pure parsers

**Files:**
- Create: `src/leasedd/enterprise_warning.py`
- Create: `tests/test_enterprise_warning.py`

**Interfaces:**
- Produces: immutable `EnterpriseCandidate`, `EnterpriseModule`, `CollectedModule` dataclasses.
- Produces: `QyjCollector.search(name)`, `QyjCollector.enumerate_modules(company_code)`, `QyjCollector.collect_module(company_code, module)`.
- Produces: `parse_search(payload)`, `parse_main_indicators(payload)`, `parse_three_reports(payload)`, `parse_analysis(payload)`, `parse_notes(payload)` pure functions.

- [ ] **Step 1: Write failing parser tests with small synthetic payloads**

Cover:

```python
assert [candidate.name for candidate in parse_search(search_payload)] == ["甲公司", "甲科技"]
assert parse_three_reports(statement_payload)["periods"] == ["2025-12-31", "2024-12-31"]
assert parse_three_reports(statement_payload)["rows"][0]["values"] == ["1,234.00", None]
assert parse_analysis(analysis_payload)["rows"][0]["unit"] == "%"
assert parse_notes(notes_payload)["values"][0][1] is None
```

Also assert `login_expired`, `structure_changed`, and `empty_module` are distinct `EnterpriseWarningError.code` values.

- [ ] **Step 2: Run parser tests and verify RED**

Run: `pytest tests/test_enterprise_warning.py -q`

Expected: collection fails because `enterprise_warning` does not exist.

- [ ] **Step 3: Implement dataclasses and parsers**

Keep original scalar strings and `None`; parsing may add row/period metadata but must not normalize values in place. Use `json.dumps(..., sort_keys=True, separators=(",", ":"))` plus SHA-256 for response hashes.

- [ ] **Step 4: Implement the browser adapter**

Follow the verified Quantradar launch pattern with environment configuration:

```text
QYJ_PROFILE_DIR       required in production
QYJ_CHROME_EXECUTABLE default /usr/bin/google-chrome
```

The adapter must:

- launch one persistent context per public method and always close only the context it launched;
- use the normal search UI to obtain the structured search response;
- enumerate current menu elements and return only the verified 4+7+6 financial modules;
- trigger the visible module event and capture exactly one authoritative finance response;
- save no headers, browser storage, credentials, or full page HTML;
- validate top-level and data keys before returning;
- expose no generic arbitrary-URL fetch method.

- [ ] **Step 5: Add adapter tests with a minimal fake browser boundary**

Inject a `session_factory` callable into `QyjCollector`. Tests must prove the three public methods select the correct authoritative endpoint, ignore support requests, close their context, and surface login/shape failures. Do not mock parser outputs.

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_enterprise_warning.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/leasedd/enterprise_warning.py tests/test_enterprise_warning.py
git commit -m "feat: add thin enterprise warning adapter"
```

---

### Task 3: Run imports through the existing Task worker

**Files:**
- Modify: `src/leasedd/worker.py`
- Create: `src/leasedd/enterprise_import.py`
- Create: `tests/test_enterprise_import_worker.py`

**Interfaces:**
- Consumes: Task 1 models and Task 2 `QyjCollector`.
- Produces: `run_enterprise_import(app, task_id, lease_token) -> dict`.
- Produces: `enqueue_enterprise_import(db, project, binding, user, failed_modules=None) -> tuple[Task, EnterpriseImport]`.

- [ ] **Step 1: Write failing worker tests**

Use an injected `app.state.enterprise_collector` fake returning synthetic modules. Test:

- 17 successes produce `completed`, 17 module rows, one total hash, and task `completed`;
- one module error produces import `partial`, preserves 16 rows, and task `completed` with quality gaps;
- all modules failing produces import `failed`;
- a formula conflict changes only `quality_state` to `warning`;
- no Agnes setting/client/model callback is read;
- repeated enqueue while an import task is queued/running returns the existing task;
- retry requests only failed module keys and reuses the same import record.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/test_enterprise_import_worker.py -q`

Expected: FAIL because the import runner does not exist.

- [ ] **Step 3: Implement enqueue and import orchestration**

`enterprise_import.py` owns required module keys, status calculation, module-level persistence, and total hashing. It must commit each module in its own short transaction while checking the active lease before durable writes.

Do not add a second retry counter. Existing `Task.attempts` covers network execution; module failure state stays in `EnterpriseImport.module_status`.

- [ ] **Step 4: Route the new kind in `run_once()`**

Treat `enterprise_import` like `extract_finance` for snapshot-staleness purposes, call `run_enterprise_import`, and finalize the existing Task without touching `Project.revision`.

- [ ] **Step 5: Run worker regressions**

Run: `pytest tests/test_enterprise_import_worker.py tests/test_worker_expired_lease.py tests/test_platform.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/leasedd/enterprise_import.py src/leasedd/worker.py tests/test_enterprise_import_worker.py
git commit -m "feat: import enterprise modules in existing worker"
```

---

### Task 4: Add four APIs and enterprise statement views

**Files:**
- Modify: `src/leasedd/app.py`
- Create: `src/leasedd/enterprise_views.py`
- Modify: `src/leasedd/statement_checks.py`
- Create: `tests/test_enterprise_api.py`
- Create: `tests/test_enterprise_views.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces exactly four new routes: `GET enterprise`, `POST enterprise/import`, `POST enterprise/retry`, `GET enterprise/data`.
- Produces: `enterprise_statement_views(import_record, module_rows) -> list[dict]`.

- [ ] **Step 1: Write failing API permission and flow tests**

Test that:

- project members can read status/data but non-members receive 403;
- project writers who are not admins cannot import/retry;
- an admin project member can search, receives all candidates, and no binding is written;
- the same admin can submit `company_code + company_name`, creating the binding and queued task;
- four route paths exist and no fifth enterprise route is registered;
- duplicate import returns the active task;
- audit events exist for binding/import/retry, but not search.

- [ ] **Step 2: Write failing view tests**

Synthetic `getThreeReports` payloads must prove:

- every period becomes a statement view with `source_type="enterprise_warning"`;
- `document_id` and `conversion_id` are `None`;
- source name, raw value, raw unit, response hash, module key, row and period coordinates remain available in evidence;
- unknown names remain visible with a deterministic `disclosed_...` concept and `mapping_state="unmapped"`;
- mapped totals run the seven existing checks;
- missing inputs return `not_checked_missing_disclosure`;
- conflicts produce `formula_status="warning"` without changing item raw values;
- a bound project returns enterprise statements only, even if PDF statement rows exist.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `pytest tests/test_enterprise_api.py tests/test_enterprise_views.py -q`

Expected: FAIL because routes and view adapter do not exist.

- [ ] **Step 4: Implement views and adapt checks without changing their equations**

Add only the source-verification compatibility needed for enterprise items. Keep `CHECKS` unchanged. Enterprise evidence must provide `mapping_state`, `source_increment`, response hash and coordinates before `_verified()` accepts the item.

- [ ] **Step 5: Implement the four routes**

Use existing `admin`, `project`, `audit`, `task_view`, and session dependencies. Search runs without persistence. Binding plus enqueue is one transaction. `GET enterprise/data` returns only the most recent readable import and supports `category` plus `module_key` filters.

Update the existing `/financial-statements` handler to branch early to enterprise views when a binding and readable import exist; never append PDF statements to that result.

- [ ] **Step 6: Run API and finance regressions**

Run: `pytest tests/test_enterprise_api.py tests/test_enterprise_views.py tests/test_m2_api.py tests/test_statement_checks.py tests/test_financial_presentation.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/leasedd/app.py src/leasedd/enterprise_views.py src/leasedd/statement_checks.py tests/test_enterprise_api.py tests/test_enterprise_views.py
git commit -m "feat: expose enterprise financial imports"
```

---

### Task 5: Add the minimal financial-page controls and raw module views

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/FinancialWorkspace.tsx`
- Modify: `frontend/src/financial.css`
- Modify: `frontend/tests/financial-view.test.mjs`

**Interfaces:**
- Consumes: Task 4 API.
- Produces: inline enterprise source/status panel inside `FinancialWorkspace`.

- [ ] **Step 1: Add failing frontend behavior tests**

Extract pure helpers where needed and test:

- candidate lists preserve all candidates and require explicit code selection;
- 17-module coverage groups render as 4/7/6;
- `partial` maps to “导入不完整” and lists failed modules;
- enterprise evidence links do not attempt PDF download/source endpoints;
- Task labels display “企业预警通财务导入” and never “Agnes”.

- [ ] **Step 2: Run frontend tests and verify RED**

Run: `npm test --prefix frontend`

Expected: FAIL on missing enterprise helpers/types.

- [ ] **Step 3: Implement API types and the inline panel**

Add `EnterpriseStatus`, `EnterpriseCandidate`, and `EnterpriseModuleData` types. Pass the existing `User.admin` flag from `main.tsx` into `FinancialWorkspace`. On financial workspace load, fetch status. Admins see search/import/retry controls; other project members see status only.

Candidate selection is a plain `<select>` plus confirmation button. Do not add a modal framework, state library, route, or management page.

- [ ] **Step 4: Connect existing tabs**

- Three statements continue to use `/financial-statements`.
- Metrics/analysis/notes fetch `/enterprise/data` only when source is `enterprise_warning`.
- PDF-only evidence buttons are hidden for enterprise items; endpoint path, module, period and response hash are shown instead.

- [ ] **Step 5: Run frontend tests and build**

Run: `npm test --prefix frontend && npm run build --prefix frontend`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/main.tsx frontend/src/FinancialWorkspace.tsx frontend/src/financial.css frontend/tests/financial-view.test.mjs
git commit -m "feat: add enterprise import controls to finance page"
```

---

### Task 6: Verify the four real companies and document results

**Files:**
- Create: `tests/enterprise_live_acceptance.py`
- Create: `docs/acceptance/enterprise-warning-four-companies.json`
- Create: `docs/acceptance/enterprise-warning-four-companies.md`

**Interfaces:**
- Consumes: complete implementation and the existing logged-in browser profile.
- Produces: repeatable live acceptance output with no credentials or licensed bulk values.

- [ ] **Step 1: Add a live acceptance command**

The script must create or reuse only 金银河、德方纳米、气派科技、昊志机电, copy the writer/reviewer membership pattern from 铭普光磁, invoke the public API/worker flow, and write only:

```text
project, matched company name/code, module coverage, period counts,
selected predeclared sample comparisons, formula statuses,
enterprise elapsed seconds, comparable PDF/Agnes elapsed seconds if present,
failed modules, Agnes call count
```

It must not migrate or alter 铭普光磁.

- [ ] **Step 2: Run the full automated suite before live writes**

Run: `pytest -q`

Expected: PASS, except any pre-existing unrelated failure must be reported by exact test name before live acceptance proceeds.

- [ ] **Step 3: Run frontend verification**

Run: `npm test --prefix frontend && npm run build --prefix frontend`

Expected: PASS.

- [ ] **Step 4: Run the four-company acceptance**

Run:

```bash
python tests/enterprise_live_acceptance.py \
  --companies 金银河 德方纳米 气派科技 昊志机电 \
  --output docs/acceptance/enterprise-warning-four-companies.json
```

Expected: all four companies matched explicitly, 17/17 modules completed or exact partial failures recorded, `agnes_calls=0`, and elapsed times recorded.

- [ ] **Step 5: Write the concise acceptance report**

Summarize evidence from the JSON without claiming general support. Compare median enterprise time with available PDF/Agnes task durations; if comparable PDF timing is absent, state that the speed comparison remains unproven rather than inventing a baseline.

- [ ] **Step 6: Credential and scope audit**

Run:

```bash
rg -ni 'cookie|authorization|bearer|password|token|session|set-cookie|cdp|websocket|user-data-dir' \
  docs/acceptance/enterprise-warning-four-companies.json \
  docs/acceptance/enterprise-warning-four-companies.md
git diff --check
git status --short
```

Expected: no credential values, no unexpected files, and unrelated user changes remain untouched.

- [ ] **Step 7: Commit**

```bash
git add tests/enterprise_live_acceptance.py docs/acceptance/enterprise-warning-four-companies.json docs/acceptance/enterprise-warning-four-companies.md
git commit -m "test: verify enterprise imports for four companies"
```

## Final Verification

Run:

```bash
pytest -q
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
```

Expected: all commands pass. Confirm the final diff contains exactly three new database entities, four new enterprise routes, no project-creation change, no statement projection model, and no Agnes call from enterprise-import code.
