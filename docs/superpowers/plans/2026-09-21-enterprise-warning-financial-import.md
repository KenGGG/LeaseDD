# Enterprise Warning Financial Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create LeaseDD projects immediately, then use the currently logged-in 企业预警通 browser session to copy every item under 财务数据 into immutable, traceable versions without Agnes or silent PDF mixing.

**Architecture:** Add a thin browser adapter that discovers and replays the site's existing structured XHR/export contracts through an attached browser session. Persist immutable import batches, source payload hashes, raw hierarchical cells, and a separate three-statement projection; reuse the existing deterministic statement checks as non-blocking quality diagnostics. Project creation only queues matching, while candidate selection, retry, refresh, and hierarchical display remain explicit project operations.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Playwright CDP, PostgreSQL/SQLite tests, React 19, TypeScript, pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-enterprise-warning-financial-import.md`

## Global Constraints

- Work only on `main`; do not create a worktree.
- Project creation must commit before enterprise matching begins.
- Reuse the current logged-in browser session; never read, return, log, or persist passwords or cookies.
- Prefer JSON/XHR, then Excel/CSV export, then structured DOM, then local HTML fragments.
- A complete batch contains 主要财务指标、资产负债表、利润表、现金流量表、财务分析及 every descendant, and 财务附注及 every descendant.
- Missing any required module leaves the batch `partial`; partial batches never replace the last `completed` batch.
- Enterprise-warning and document-extraction values never merge into one current financial version.
- Formula status is independent of collection status and never changes imported values.
- Do not call Agnes anywhere in the enterprise-warning path.
- Do not add scheduled synchronization, a correction platform, or a general website archiver.
- Do not migrate the existing 铭普光磁 project automatically.

## Review Focus

- A duplicate project name must create at most one new project per submitted request and must not bind the wrong same-name enterprise; Task 4 pins idempotent queuing and candidate confirmation.
- An expired browser login may return HTTP 200 with a login page; Task 1 and Task 3 require semantic login detection rather than status-code detection.
- A page may return values in scientific notation, parentheses, `--`, or Chinese units; Task 3 pins lossless raw values and Decimal-only normalization.
- A refresh can change module order or remove a descendant; Task 5 requires manifest comparison and keeps the batch `partial` instead of silently accepting reduced coverage.
- Formula conflicts and restated periods must not reject a structurally complete batch; Task 5 pins separate collection and quality states.

---

### Task 1: Freeze the real 企业预警通 acquisition contract

**Files:**
- Create: `tools/qyyjt_probe.py`
- Create: `tests/fixtures/qyyjt/search.json`
- Create: `tests/fixtures/qyyjt/financial-index.json`
- Create: `tests/fixtures/qyyjt/financial-payloads.json`
- Create: `docs/acceptance/qyyjt-acquisition-contract.md`
- Modify: `pyproject.toml`
- Modify: `compose.yaml`

**Interfaces:**
- Consumes: environment variable `QYYJT_CDP_URL`, pointing to the current Chrome DevTools endpoint reachable by the worker.
- Produces: redacted fixtures plus a documented `search`, `financial_index`, and `fetch_module` request/response contract; no authentication material.

- [ ] **Step 1: Write the fixture-safety test**

Create `tests/test_qyyjt_fixture_safety.py`:

```python
import json
from pathlib import Path

FIXTURES = Path('tests/fixtures/qyyjt')

def test_recorded_qyyjt_fixtures_are_redacted_and_cover_six_categories():
    text = '\n'.join(path.read_text() for path in FIXTURES.glob('*.json'))
    lowered = text.lower()
    assert 'cookie' not in lowered and 'authorization' not in lowered
    payload = json.loads((FIXTURES / 'financial-payloads.json').read_text())
    assert set(payload['categories']) == {
        '主要财务指标', '资产负债表', '利润表', '现金流量表', '财务分析', '财务附注'
    }
    assert payload['descendant_count']['财务分析'] > 0
    assert payload['descendant_count']['财务附注'] > 0
```

- [ ] **Step 2: Run the test and verify the fixtures are absent**

Run: `uv run pytest tests/test_qyyjt_fixture_safety.py -q`

Expected: FAIL because the fixture files do not exist.

- [ ] **Step 3: Add the read-only network probe**

Implement `tools/qyyjt_probe.py` with this public entry point:

```python
def capture_contract(cdp_url: str, company_name: str, output_dir: Path) -> dict:
    """Attach over CDP, search company_name, capture financial XHR/export payloads,
    redact headers/query secrets, and return category/descendant coverage."""
```

Use `playwright.sync_api.sync_playwright().chromium.connect_over_cdp(cdp_url)`. Register `page.on('response', ...)` before searching, retain only JSON/CSV/XLSX responses whose initiating page is on `qyyjt.cn`, and write SHA-256 plus redacted bodies. Reject a login page with `QyyjtProbeError('login_expired')`. Never call `browser.close()` on the attached browser.

Move Playwright from the dev group to production dependencies and pass `QYYJT_CDP_URL` only to the worker in `compose.yaml`.

- [ ] **Step 4: Capture and document the real contract**

Run against 铭普光磁 to minimize exploratory variability:

```bash
QYYJT_CDP_URL="$QYYJT_CDP_URL" uv run python tools/qyyjt_probe.py \
  --company 铭普光磁 --output /tmp/qyyjt-contract
```

Copy only redacted representative payloads into `tests/fixtures/qyyjt/`. In `docs/acceptance/qyyjt-acquisition-contract.md`, record request method, path template, required non-secret parameters, pagination/period behavior, all six category identifiers, descendant enumeration, and whether each category uses JSON, export, or DOM fallback.

- [ ] **Step 5: Run fixture safety**

Run: `uv run pytest tests/test_qyyjt_fixture_safety.py -q`

Expected: PASS, with all six categories and both descendant counts present.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock compose.yaml tools/qyyjt_probe.py tests/fixtures/qyyjt tests/test_qyyjt_fixture_safety.py docs/acceptance/qyyjt-acquisition-contract.md
git commit -m "test: freeze enterprise warning acquisition contract"
```

### Task 2: Add immutable enterprise bindings and import storage

**Files:**
- Modify: `src/leasedd/db.py`
- Create: `deployment/migrations/versions/0005_enterprise_warning.py`
- Create: `tests/test_enterprise_models.py`

**Interfaces:**
- Produces: `EnterpriseBinding`, `EnterpriseImportBatch`, `EnterpriseSourcePayload`, `EnterpriseFinancialCell`, `EnterpriseStatementProjection`, and `EnterpriseStatementItem` SQLAlchemy models.
- `EnterpriseImportBatch.collection_state`: `queued | running | partial | completed | failed`.
- `EnterpriseImportBatch.quality_state`: `not_checked | passed | warning | mixed`.

- [ ] **Step 1: Write failing persistence tests**

Create a temporary SQLite database and assert these invariants:

```python
def test_one_binding_per_project_and_immutable_versioned_batches(session):
    binding = EnterpriseBinding(project_id='p', provider='qyyjt', provider_code='C1',
        provider_name='测试股份有限公司', match_state='bound', listing_state='listed',
        finance_state='available', confirmed_by='u', confirmed_at=1)
    session.add(binding); session.flush()
    session.add(EnterpriseBinding(project_id='p', provider='qyyjt', provider_code='C2',
        provider_name='错误公司', match_state='bound', listing_state='listed',
        finance_state='available', confirmed_by='u', confirmed_at=2))
    with pytest.raises(IntegrityError): session.flush()

def test_raw_cells_keep_path_period_unit_value_and_payload_hash(session):
    cell = EnterpriseFinancialCell(batch_id='b', payload_id='s', category='资产负债表',
        module_path=['资产负债表'], row_path=['资产总计'], period='2024-12-31',
        raw_unit='万元', raw_field='2024年末', raw_value='1,234.50', source_order=1)
    session.add(cell); session.flush()
    assert cell.raw_value == '1,234.50'
```

Also test uniqueness of `(batch_id, category, module_path_hash, row_path_hash, period, raw_field)` and uniqueness of one current completed batch per project through `EnterpriseBinding.current_batch_id`.

- [ ] **Step 2: Run the tests and verify missing models**

Run: `uv run pytest tests/test_enterprise_models.py -q`

Expected: FAIL importing the four models.

- [ ] **Step 3: Implement models and migration**

Add focused models with JSON arrays for `module_path` and `row_path`, string raw values, payload SHA-256, source URL, timestamps, coverage JSON, and errors JSON. Enterprise statement projections reference `batch_id` and raw `cell_id`; they do not contain `document_id`, `conversion_id`, or `run_id`. Do not attach these rows to `Document`, `DocumentConversion`, or `ExtractionRun`; source isolation is structural.

Migration `0005` must create foreign keys, indexes on project/batch/category, the uniqueness constraints above, and nullable `current_batch_id` on the binding. Its downgrade drops the foreign key before the four tables.

- [ ] **Step 4: Verify models and migration**

Run:

```bash
uv run pytest tests/test_enterprise_models.py -q
uv run alembic upgrade head
uv run alembic downgrade 0004
uv run alembic upgrade head
```

Expected: tests PASS and both migration directions succeed on the disposable test database.

- [ ] **Step 5: Commit**

```bash
git add src/leasedd/db.py deployment/migrations/versions/0005_enterprise_warning.py tests/test_enterprise_models.py
git commit -m "feat: store versioned enterprise financial imports"
```

### Task 3: Implement the thin structured-data adapter

**Files:**
- Create: `src/leasedd/enterprise_warning.py`
- Create: `tests/test_enterprise_warning.py`
- Test: `tests/fixtures/qyyjt/*.json`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class EnterpriseCandidate:
    code: str; name: str; listed: bool | None; finance_available: bool | None

@dataclass(frozen=True)
class SourcePayload:
    category: str; module_path: tuple[str, ...]; url: str
    media_type: str; sha256: str; body: bytes

class EnterpriseWarningAdapter:
    def search(self, name: str) -> list[EnterpriseCandidate]: ...
    def collect(self, code: str) -> list[SourcePayload]: ...
```

- Consumes: `QYYJT_CDP_URL` and the Task 1 request contract.

- [ ] **Step 1: Write failing contract-parser tests**

Tests must assert:

```python
def test_search_preserves_multiple_candidates_without_choosing_first(adapter):
    candidates = adapter.search('金银河')
    assert len(candidates) >= 2
    assert not hasattr(adapter, 'selected_candidate')

def test_collect_requires_every_declared_descendant(adapter):
    payloads = adapter.collect('CODE')
    paths = {payload.module_path for payload in payloads}
    assert ('财务分析', '盈利能力') in paths
    assert ('财务附注', '应收账款') in paths

def test_login_html_is_not_empty_success(adapter_with_login_response):
    with pytest.raises(EnterpriseWarningError, match='login_expired'):
        adapter_with_login_response.search('金银河')
```

Add numeric parser cases for `1,234.50`, `(12.3)`, `1.2E+4`, `--`, empty string, `万元`, and `亿元`. Assert `raw_value` is unchanged and normalized values use `Decimal`, never float.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/test_enterprise_warning.py -q`

Expected: FAIL because `enterprise_warning` does not exist.

- [ ] **Step 3: Implement fixture-driven parsing and CDP transport**

Separate pure functions from transport:

```python
def parse_candidates(payload: bytes) -> list[EnterpriseCandidate]: ...
def enumerate_modules(index_payload: bytes) -> list[tuple[str, ...]]: ...
def parse_cells(source: SourcePayload) -> list[RawFinancialCell]: ...
def normalize_amount(raw_value: str, raw_unit: str) -> Decimal | None: ...
```

`EnterpriseWarningAdapter` may use DOM only to initiate search/module loading when the recorded contract cannot be replayed in page context. Validate that collected module paths exactly equal the index manifest; otherwise raise `EnterpriseWarningError('incomplete_module_coverage', missing_paths)`.

- [ ] **Step 4: Run adapter tests**

Run: `uv run pytest tests/test_enterprise_warning.py tests/test_qyyjt_fixture_safety.py -q`

Expected: PASS without network or a live browser.

- [ ] **Step 5: Commit**

```bash
git add src/leasedd/enterprise_warning.py tests/test_enterprise_warning.py
git commit -m "feat: parse enterprise warning financial data"
```

### Task 4: Make project matching asynchronous and candidate-safe

**Files:**
- Modify: `src/leasedd/contracts.py`
- Modify: `src/leasedd/app.py`
- Modify: `src/leasedd/worker.py`
- Create: `tests/test_enterprise_matching.py`

**Interfaces:**
- Adds task kinds `match_enterprise` and `import_enterprise_finance`.
- Adds `POST /api/projects/{pid}/enterprise/candidate` body `{"code": "..."}`.
- Adds `POST /api/projects/{pid}/enterprise/retry-match`.
- Project responses add `enterprise: {match_state, provider_name, provider_code, listing_state, finance_state, candidates, active_task_id}`.

- [ ] **Step 1: Write failing API and worker tests**

Assert project creation returns before the adapter is called:

```python
def test_create_project_commits_and_queues_match_without_calling_browser(env, monkeypatch):
    monkeypatch.setattr('leasedd.enterprise_warning.EnterpriseWarningAdapter.search',
                        lambda *_: (_ for _ in ()).throw(AssertionError('synchronous call')))
    response = admin.post('/api/projects', json=payload)
    assert response.status_code == 200
    project_id = response.json()['id']
    assert queued_task(project_id).kind == 'match_enterprise'
```

Also cover unique auto-bind, multiple candidates requiring exact code selection, login expiry leaving `pending`, non-listed/no-finance selecting document extraction, retry returning an existing queued/running task, and the review-focus duplicate-submit case.

- [ ] **Step 2: Run matching tests and verify failure**

Run: `uv run pytest tests/test_enterprise_matching.py -q`

Expected: FAIL because the endpoints and task kinds do not exist.

- [ ] **Step 3: Implement minimal asynchronous matching**

Extend `CreateTask.kind` and worker dispatch. Add:

```python
def run_enterprise_match(app, task_id: str, lease: str) -> dict: ...
def queue_unique_task(db, project_id: str, kind: str, user_id: str,
                      result: dict | None = None) -> Task: ...
```

Lock `Project` before `EnterpriseBinding` and `Task`. On one candidate, bind and queue import only when both `listed is True` and `finance_available is True`. On multiple candidates, store only non-secret candidate metadata in the binding. Audit creation, match result, selection, and retry.

- [ ] **Step 4: Run matching and existing platform tests**

Run: `uv run pytest tests/test_enterprise_matching.py tests/test_platform.py -q`

Expected: PASS; existing project creation semantics remain intact.

- [ ] **Step 5: Commit**

```bash
git add src/leasedd/contracts.py src/leasedd/app.py src/leasedd/worker.py tests/test_enterprise_matching.py
git commit -m "feat: match enterprise source after project creation"
```

### Task 5: Persist complete imports and project three statements

**Files:**
- Create: `src/leasedd/enterprise_import.py`
- Modify: `src/leasedd/financial_semantics.py`
- Modify: `src/leasedd/worker.py`
- Create: `tests/test_enterprise_import.py`

**Interfaces:**
- Produces:

```python
def import_enterprise_payloads(session_factory, project_id: str, task_id: str,
                               payloads: list[SourcePayload], actor_id: str) -> str: ...
def project_enterprise_statements(batch_id: str,
                                  cells: list[RawFinancialCell]) -> list[dict]: ...
```

- Reuses: `apply_statement_checks(statements)` from `financial_semantics.py` after extracting it as the common deterministic check entry point.

- [ ] **Step 1: Write failing import tests**

Cover complete and partial batches, source isolation, refresh removals, formula warnings, restatements, and raw fidelity:

```python
def test_formula_warning_does_not_fail_complete_import(result):
    assert result.batch.collection_state == 'completed'
    assert result.batch.quality_state == 'warning'
    assert result.statements[0].items['资产总计'].raw_value == '100'

def test_missing_note_descendant_keeps_new_batch_partial(previous_complete, result):
    assert result.batch.collection_state == 'partial'
    assert result.binding.current_batch_id == previous_complete.id
    assert ['财务附注', '应收账款'] in result.batch.coverage['missing_paths']

def test_enterprise_values_never_attach_to_document_runs(result):
    assert all(statement.document_id is None and statement.run_id is None
               for statement in result.enterprise_statements)
```

Use the `EnterpriseStatementProjection` and `EnterpriseStatementItem` tables from Task 2 rather than weakening `FinancialStatement` non-null document provenance. Keep the API serializer source-neutral.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/test_enterprise_import.py -q`

Expected: FAIL because import persistence and source-neutral projections do not exist.

- [ ] **Step 3: Implement transactional import**

Hash and store each source payload once, parse raw cells, compare the collected manifest with every required descendant, and compute the batch content hash from sorted payload hashes. Persist raw cells before projections. Only set `binding.current_batch_id` when coverage is complete. Store check results under the projected statement, never in raw cells.

Use a minimal explicit mapping dictionary for the concepts required by the seven checks; unmatched rows receive `mapping_state='unmapped'` and never become formula inputs. Preserve adjusted/unadjusted period labels as different columns.

- [ ] **Step 4: Run import and semantic regression tests**

Run:

```bash
uv run pytest tests/test_enterprise_import.py tests/test_financial_semantics.py tests/test_semantic_pipeline.py -q
```

Expected: PASS; existing PDF/Agnes checks remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/leasedd/enterprise_import.py src/leasedd/financial_semantics.py src/leasedd/worker.py src/leasedd/db.py deployment/migrations/versions/0005_enterprise_warning.py tests/test_enterprise_import.py
git commit -m "feat: import and validate enterprise financial versions"
```

### Task 6: Expose import status, hierarchy, evidence, refresh, and retry APIs

**Files:**
- Modify: `src/leasedd/contracts.py`
- Modify: `src/leasedd/app.py`
- Create: `tests/test_enterprise_api.py`

**Interfaces:**
- Adds:
  - `GET /api/projects/{pid}/enterprise`
  - `GET /api/projects/{pid}/enterprise/batches`
  - `GET /api/projects/{pid}/enterprise/batches/{batch_id}`
  - `GET /api/projects/{pid}/enterprise/tree?batch_id=...`
  - `GET /api/projects/{pid}/enterprise/statements?batch_id=...`
  - `POST /api/projects/{pid}/enterprise/refresh`
  - `POST /api/projects/{pid}/enterprise/retry`

- [ ] **Step 1: Write failing authorization and response tests**

Tests require project membership for all reads and admin for candidate selection, refresh, and retry. Assert responses contain provider code/name, collection state, quality state, category/descendant coverage, missing paths, source URL/hash/time per value, formula differences, and no payload body, cookie, or CDP URL.

- [ ] **Step 2: Run API tests and verify failure**

Run: `uv run pytest tests/test_enterprise_api.py -q`

Expected: FAIL with missing routes.

- [ ] **Step 3: Implement API serializers and operations**

Keep raw payload bodies server-side. `tree` returns nested module nodes with ordered rows/cells; `statements` returns the same view model keys used by the existing finance workspace plus `source_kind='enterprise_warning'`, `batch_id`, and cell provenance. Refresh always creates a new batch; retry resumes failed paths in the current partial batch and preserves successful payload hashes.

- [ ] **Step 4: Run API and membership regression tests**

Run: `uv run pytest tests/test_enterprise_api.py tests/test_m2_api.py tests/test_platform.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/leasedd/contracts.py src/leasedd/app.py tests/test_enterprise_api.py
git commit -m "feat: expose enterprise financial import APIs"
```

### Task 7: Add minimal project matching and financial hierarchy UI

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/FinancialWorkspace.tsx`
- Modify: `frontend/src/financial-view.ts`
- Modify: `frontend/src/financial.css`
- Modify: `frontend/tests/financial-view.test.mjs`
- Create: `tests/enterprise_warning_browser.py`

**Interfaces:**
- Consumes the Task 6 endpoints and source-neutral statement view model.
- Produces candidate confirmation, match/import status, admin refresh/retry actions, and hierarchical tabs for all six categories.

- [ ] **Step 1: Write failing view-model tests**

Add assertions that:

```javascript
assert.equal(importLabel({collection_state:'completed', quality_state:'warning'}),
  '导入完成 · 勾稽异常')
assert.equal(importLabel({collection_state:'partial', quality_state:'passed'}),
  '导入不完整 · 可重试')
assert.deepEqual(categoryOrder(tree), [
  '主要财务指标','资产负债表','利润表','现金流量表','财务分析','财务附注'
])
```

Also assert formulas do not hide amounts, partial descendants remain visible, and candidate selection never preselects the first candidate.

- [ ] **Step 2: Run frontend tests and verify failure**

Run: `cd frontend && npm test`

Expected: FAIL because enterprise view helpers do not exist.

- [ ] **Step 3: Implement the minimal UI**

Add an enterprise source panel above the finance workspace. Display matching/import status without blocking navigation. For multiple candidates, render an explicit select plus confirmation button with no default value. Render six ordered category tabs; use the current statement matrix for the three statements and an accessible `<details>` tree/table for metrics, analysis, and notes. Only admins see update/retry controls.

- [ ] **Step 4: Add browser acceptance**

`tests/enterprise_warning_browser.py` must route mocked API responses and assert desktop/mobile rendering for: pending match, multiple candidates, importing, completed-with-formula-warning, and partial-with-retry. Assert zero console errors and no amount disappears on a warning.

- [ ] **Step 5: Run frontend verification**

Run:

```bash
cd frontend && npm test && npm run build
cd .. && uv run python tests/enterprise_warning_browser.py
```

Expected: unit tests, TypeScript build, and browser acceptance PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src frontend/tests/financial-view.test.mjs tests/enterprise_warning_browser.py
git commit -m "feat: show enterprise financial import workspace"
```

### Task 8: Deploy and validate four real companies

**Files:**
- Create: `docs/acceptance/enterprise-warning-four-companies.csv`
- Create: `docs/acceptance/enterprise-warning-import.md`
- Modify: `docs/acceptance/test-results.json`
- Runtime only: `runtime/acceptance/enterprise-warning/`

**Interfaces:**
- Consumes the deployed APIs, worker, current logged-in browser, and users `tom`/`ken`.
- Produces four real projects and a reproducible acceptance record; it does not modify 铭普光磁.

- [ ] **Step 1: Run full automated regression before deployment**

Run:

```bash
uv run pytest -q
cd frontend && npm test && npm run build
```

Expected: all tests pass; only pre-existing documented skips remain.

- [ ] **Step 2: Deploy migration and services**

Run the repository's existing main deployment workflow, verify `alembic current` reports `0005`, `/api/health` is healthy, the worker sees `QYYJT_CDP_URL`, and the browser session is logged in. Do not print the CDP URL or any browser/session secret into acceptance artifacts.

- [ ] **Step 3: Create or reuse the four projects idempotently**

Create `金银河`, `德方纳米`, `气派科技`, and `昊志机电` only when an exact same-name project does not exist. Assign writer `tom` and reviewer `ken`. Record project IDs in `runtime/acceptance/enterprise-warning/projects.json`; do not touch 铭普光磁.

- [ ] **Step 4: Let matching/import finish with bounded monitoring**

For each project, record timestamps and status transitions. Confirm no Agnes request count increases. If a batch is partial, use the retry endpoint once after recording missing paths; do not silently switch to PDF.

- [ ] **Step 5: Verify complete financial-data coverage and fidelity**

Write one CSV row per category/module/period sample with columns:

```text
项目,企业代码,栏目,下级科目,期间,单位,企业预警通原值,LeaseDD原值,结果,来源URL,响应SHA256,批次状态,公式状态,耗时秒,失败原因
```

Require all six top-level categories and every index-declared descendant. Compare all periods for the three statements and principal indicators; for every analysis/note descendant compare the first, middle, and last visible period plus one blank when present. Missing or untraceable values are failures, not correct results.

- [ ] **Step 6: Record honest acceptance results**

In `docs/acceptance/enterprise-warning-import.md`, separate automated checks from manual browser comparison; report each company's complete/partial state, coverage counts, formula warnings, retries, elapsed time, and unresolved page-contract issues. Update `docs/acceptance/test-results.json` with commands, counts, artifact hashes, and the exact commit.

- [ ] **Step 7: Commit acceptance evidence**

```bash
git add docs/acceptance/enterprise-warning-four-companies.csv docs/acceptance/enterprise-warning-import.md docs/acceptance/test-results.json
git commit -m "test: validate enterprise financial imports"
```

### Task 9: Final regression and scope audit

**Files:**
- Modify only if verification finds a defect in files already named above.

**Interfaces:**
- Produces the release decision and remaining-issues list.

- [ ] **Step 1: Run migrations and all automated checks from a clean database**

Run:

```bash
uv run alembic upgrade head
uv run pytest -q
cd frontend && npm test && npm run build
```

Expected: all tests pass with no new skip or warning.

- [ ] **Step 2: Audit the delivered scope**

Confirm with database queries and API responses that every completed batch contains all six categories and index-declared descendants; no enterprise batch references a document extraction run; no partial batch is current; no formula warning changes collection state; and no source payload contains `cookie`, `authorization`, or the CDP endpoint.

- [ ] **Step 3: Review repository changes**

Run `git diff 840d1ef...HEAD --check` and inspect the diff for unrelated changes, credentials, captured cookies, full-site HTML archives, scheduled jobs, or automatic PDF fallback. Remove any such scope violation before completion.

- [ ] **Step 4: Commit any verification-only correction**

If Step 1–3 required a correction, commit only that correction with:

```bash
git add src/leasedd tests frontend/src frontend/tests deployment/migrations docs/acceptance compose.yaml pyproject.toml uv.lock tools/qyyjt_probe.py
git commit -m "fix: close enterprise import verification gaps"
```

If no correction was needed, do not create an empty commit.
