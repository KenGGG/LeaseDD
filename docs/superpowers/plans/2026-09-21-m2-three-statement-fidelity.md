# LeaseDD M2 Three-Statement Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reliably reconstruct balance sheets, income statements, and cash-flow statements from public PDFs with cell-anchored source verification, seven non-destructive accounting checks, at most one targeted Agnes review per logical table, and separately reported PDF spot checks.

**Architecture:** Extend the existing Agnes map/interpret/extract contracts rather than replacing the pipeline. Keep Markdown-cell source verification and equation diagnostics as separate deterministic layers; persist both in the existing extraction manifest and project them onto statement API responses without a database migration. Exercise the implementation first with synthetic fixtures, then with a frozen six-company public-PDF corpus and a preselected human comparison sheet.

**Tech Stack:** Python 3.12, Pydantic 2, Decimal, FastAPI, SQLAlchemy, pytest, React 19, TypeScript, Node test runner, Playwright, MinerU, Agnes OpenAI-compatible API.

**Spec:** `docs/superpowers/specs/2026-09-21-m2-three-statement-fidelity.md`

## Global Constraints

- Accuracy is judged against the original PDF; Markdown verification is not human PDF confirmation.
- Agnes must not calculate, fill zeroes, infer missing values, or alter values to satisfy equations.
- Keep original account names and unknown-account values; do not build a large account catalog.
- Formula checks may warn but must never clear or change source-verified values.
- A missing disclosed input is `not_checked_missing_disclosure`, does not become zero, and does not trigger semantic review.
- Each logical table receives at most one semantic review; transport retries and semantic review are counted separately.
- Keep the shared Agnes limit at default 18 RPM and hard maximum 20 RPM, including retries and review calls.
- Reuse existing extraction runs, manifests, stage checkpoints, and history; do not add `financial_revision` or auto-rerun existing uploads.
- Do not expand metrics, notes, approval, manual-correction, formal-report, or benchmark-platform scope.
- The initial live corpus is exactly six non-financial listed companies: three annual and three half-year reports; expand only if a generic failure requires it, to at most ten.

## Review Focus

- Merged/multi-row headers with numeric-looking note indexes must classify note and sequence columns without hiding a real amount column; Task 1 tests both outcomes.
- Chinese period labels that share a year but differ between cumulative quarter, single quarter, and half-year must remain distinct; Task 2 tests all forms.
- Duplicate or uncertain standard mappings must not silently choose a formula input; Task 4 tests `not_checked_unverified_source`.
- A formula conflict must preserve normalized values and source status while identifying only involved items; Task 4 tests this invariant.
- A resumed task must reuse the same one-review checkpoint and must not send a second semantic review; Task 5 tests restart behavior.

---

### Task 1: Strengthen Agnes table contracts and prompts

**Files:**
- Modify: `src/leasedd/financial_semantics.py`
- Modify: `src/leasedd/semantic_pipeline.py`
- Modify: `tests/test_semantic_adversarial.py`
- Modify: `tests/test_semantic_pipeline.py`

**Interfaces:**
- Produces: `NonAmountColumn`, `SemanticColumn.raw_header`, `TableUnderstanding.non_amount_columns`.
- Preserves: `TableUnderstanding`, `TableExtraction`, and `SEMANTIC_CONTRACTS` as the model-call schema entry points.
- Consumed by Task 3 source-cell coverage auditing and Task 5 semantic review payloads.

- [ ] **Step 1: Add failing contract tests for raw headers and non-amount columns**

Add tests that validate this shape and reject missing/mismatched evidence:

```python
metadata = base_metadata()
metadata['columns'][0]['raw_header'] = '2025年1—6月\n本期金额'
metadata['non_amount_columns'] = [{
    'block_id': 'table-1', 'column': 2, 'header_rows': [1, 2],
    'raw_header': '附注', 'kind': 'note_reference',
    'evidence': {'start_line': 3, 'end_line': 4, 'quote': '附注'},
}]
parsed = TableUnderstanding.model_validate(metadata)
assert parsed.columns[0].raw_header.startswith('2025年1—6月')
assert parsed.non_amount_columns[0].kind == 'note_reference'
```

Also test that `column` cannot overlap an amount column or `label_column`, that header coordinates are absolute and in bounds, and that an undeclared numeric amount column still produces `unmapped_numeric_column`.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `uv run pytest tests/test_semantic_adversarial.py tests/test_semantic_pipeline.py -q`

Expected: FAIL because `raw_header` and `non_amount_columns` are not accepted by the strict Pydantic models.

- [ ] **Step 3: Implement the strict contract types**

In `financial_semantics.py`, add:

```python
class NonAmountColumn(Strict):
    block_id: str
    column: int = Field(ge=1)
    header_rows: list[int] = Field(min_length=1, max_length=30)
    raw_header: str = Field(min_length=1, max_length=500)
    kind: Literal['note_reference', 'sequence', 'other']
    evidence: Proof

class SemanticColumn(Strict):
    # retain existing fields
    raw_header: str = Field(min_length=1, max_length=500)

class TableUnderstanding(Strict):
    # retain existing fields
    non_amount_columns: list[NonAmountColumn] = Field(default_factory=list, max_length=100)
```

Validate raw header text from the declared header cells and validate each non-amount column's evidence/coordinates. Return explicit issues such as `raw_header_mismatch`, `non_amount_header_mismatch`, and `non_amount_column_overlap` instead of trusting the model declaration.

- [ ] **Step 4: Tighten interpret/extract/review instructions**

Update `stage_system()` so interpret explicitly returns all original header text and declares note/sequence columns, while extract repeats the fixed rules:

```text
不计算、不补零、不推导、不跨单元格拼数，也不得为了通过财务恒等式修改任何数字。
金额列和非金额列都使用原物理表的绝对列坐标；附注、序号列必须单独声明并给出表头原文证据。
```

Ensure `_block_payload()` already supplies every cell's absolute row/column and source line; add no alternate coordinate system.

- [ ] **Step 5: Run contract and pipeline tests**

Run: `uv run pytest tests/test_semantic_adversarial.py tests/test_semantic_pipeline.py -q`

Expected: PASS, including rejection of false non-amount declarations and continued detection of true omitted amount columns.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/leasedd/financial_semantics.py src/leasedd/semantic_pipeline.py tests/test_semantic_adversarial.py tests/test_semantic_pipeline.py
git commit -m "feat: tighten Agnes statement contracts"
```

### Task 2: Parse full Chinese periods without unsafe merging

**Files:**
- Modify: `src/leasedd/finance_extract.py`
- Modify: `src/leasedd/financial_semantics.py`
- Modify: `src/leasedd/financial_presentation.py`
- Modify: `tests/test_period_alignment.py`
- Modify: `tests/test_semantic_adversarial.py`
- Modify: `frontend/tests/financial-view.test.mjs`

**Interfaces:**
- Produces: `normalized_period(raw, kind, statement_type) -> tuple[str, str]` with distinct cumulative and single-quarter date ranges.
- Produces: a stable column identity that includes `raw_header` qualifiers such as 调整前/调整后.
- Preserves: API fields `period`, `period_normalized`, `period_kind`; `period` remains original disclosure text.

- [ ] **Step 1: Add failing period tests**

Cover these exact expectations:

```python
assert normalized_period('2025年1—3月', 'quarter', 'income_statement') == ('2025-01-01/2025-03-31', 'quarter')
assert normalized_period('2025年7—9月', 'quarter', 'income_statement') == ('2025-07-01/2025-09-30', 'quarter')
assert normalized_period('2025年1—6月', 'half_year', 'cash_flow_statement') == ('2025-01-01/2025-06-30', 'half_year')
assert normalized_period('2025年半年度', 'half_year', 'income_statement') == ('2025-01-01/2025-06-30', 'half_year')
```

Add a fixture with `2025年1—3月` and `2025年7—9月` to prove same-year columns do not match. Add balance-sheet columns `2025年1月1日（调整前）` and `2024年12月31日（调整后）` and assert they remain distinct even if a presentation helper maps an unqualified opening balance to a prior closing date.

- [ ] **Step 2: Run period tests and confirm failure**

Run: `uv run pytest tests/test_period_alignment.py tests/test_semantic_adversarial.py -q && npm --prefix frontend test`

Expected: at least the Chinese range cases fail before implementation.

- [ ] **Step 3: Implement full-label parsing and column identity**

Extend `normalize_period`/`normalized_period` with explicit Chinese separators `—`, `–`, `-`, `至`, and `到`. For flow statements, derive exact start/end dates and distinguish a Jan–Mar cumulative quarter from Jul–Sep single quarter by date range, not year. Do not strip 调整前/调整后 when constructing merge keys; include a normalized qualifier token in `_merge_statement_fragments`.

Keep original `period` and `raw_header` in output. Allow `align_balance_period` to align only an unqualified opening balance whose evidence and value agree with a corresponding prior closing disclosure; never rewrite the stored original label.

- [ ] **Step 4: Run focused period tests**

Run: `uv run pytest tests/test_period_alignment.py tests/test_semantic_adversarial.py -q && npm --prefix frontend test`

Expected: PASS; cumulative and single-period labels render separately and adjusted columns never merge.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/leasedd/finance_extract.py src/leasedd/financial_semantics.py src/leasedd/financial_presentation.py tests/test_period_alignment.py tests/test_semantic_adversarial.py frontend/tests/financial-view.test.mjs
git commit -m "fix: preserve complete financial periods"
```

### Task 3: Make source verification deterministic and precision-aware

**Files:**
- Modify: `src/leasedd/financial_semantics.py`
- Modify: `tests/test_semantic_adversarial.py`
- Modify: `tests/test_semantic_crosspage_checks.py`

**Interfaces:**
- Produces on every item evidence: `source_decimal_places: int | None`, `source_increment: str | None`, and the existing exact cell locator.
- Produces on every statement: `source_status: consistent | needs_review` and `source_issues: list[str]`.
- Consumed by Task 4 `evaluate_statement_checks(statement)`.

- [ ] **Step 1: Add failing cell, metadata, and coverage tests**

Add cases proving:

```python
assert item['raw_value'] == markdown_cell_text
assert item['evidence']['cell'] == {'id': cell_id, 'block_id': block_id, 'row': row, 'column': column, ...}
assert item['evidence']['source_decimal_places'] == 2
assert item['evidence']['source_increment'] == '0.01'
```

Test wrong label cell, wrong value cell, period-column mismatch, unsupported unit evidence, missing currency/entity/scope evidence, unknown account preservation, note indexes ignored as amounts, and a genuine undeclared amount column reported. Assert local-parser disagreement adds a diagnostic but cannot overwrite the source cell, concept, or normalized value.

- [ ] **Step 2: Run source-verification tests and confirm failure**

Run: `uv run pytest tests/test_semantic_adversarial.py tests/test_semantic_crosspage_checks.py -q`

Expected: FAIL on precision metadata and the new statement source summary.

- [ ] **Step 3: Implement precision extraction and source summary**

Add a pure helper:

```python
def disclosed_precision(raw: str) -> tuple[int, Decimal] | None:
    value = compact(raw)
    if source_number(value) is None:
        return None
    fraction = value.strip('()').replace(',', '').partition('.')[2]
    places = len(fraction)
    return places, Decimal(1).scaleb(-places)
```

Store the precision before unit scaling. Derive `source_status` only from deterministic source/metadata issues, not formula results. Update `_physical_numeric_cells` to exclude only validated `non_amount_columns`, while keeping undeclared numeric columns in the coverage audit.

- [ ] **Step 4: Preserve unknown values without trusting mappings**

Retain the existing `disclosed_<hash>` stable concept for unmapped rows and their normalized values for display. Keep `mapping_state='unmapped'`; Task 4 must exclude them from formulas. Ensure `local_disagreement` remains a diagnostic and never substitutes local values.

- [ ] **Step 5: Run source-verification tests**

Run: `uv run pytest tests/test_semantic_adversarial.py tests/test_semantic_crosspage_checks.py tests/test_semantic_worker.py -q`

Expected: PASS with zero cases where a wrong source cell becomes `VERIFIED`.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/leasedd/financial_semantics.py tests/test_semantic_adversarial.py tests/test_semantic_crosspage_checks.py tests/test_semantic_worker.py
git commit -m "feat: strengthen deterministic source verification"
```

### Task 4: Implement seven non-destructive accounting checks

**Files:**
- Create: `src/leasedd/statement_checks.py`
- Create: `tests/test_statement_checks.py`
- Modify: `src/leasedd/financial_semantics.py`
- Modify: `tests/test_semantic_crosspage_checks.py`
- Modify: `tests/test_semantic_worker.py`

**Interfaces:**
- Produces: `evaluate_statement_checks(statement: dict) -> list[dict]`.
- Each result contains `code`, `status`, `difference`, `tolerance`, `missing_concepts`, `involved_concepts`, `item_ids` or stable pre-persistence evidence locators, `entity`, `scope`, `period`, and `currency`.
- Status values: `passed`, `conflict`, `not_checked_missing_disclosure`, `not_checked_unverified_source`.

- [ ] **Step 1: Write the failing seven-equation test table**

Define the exact registry in the test:

```python
EXPECTED = {
 'assets_equal_liabilities_equity',
 'current_plus_noncurrent_assets_equal_assets',
 'current_plus_noncurrent_liabilities_equal_liabilities',
 'profit_less_tax_equals_net_profit',
 'operating_plus_nonoperating_equals_total_profit',
 'cash_flows_plus_fx_equal_net_increase',
 'opening_cash_plus_change_equals_ending_cash',
}
```

For each relation, test `passed`, `conflict`, missing disclosure, and present-but-unverified input. Test duplicate mapped concepts and unmapped disclosed rows produce `not_checked_unverified_source`, not arbitrary input selection.

- [ ] **Step 2: Add failing cumulative rounding tests**

Use inputs disclosed as `1.2`, `2.34`, and `3` in `万元`. Assert tolerance is `(0.05 + 0.005 + 0.5) * 10000 = 5550` yuan. Test an exact boundary passes and one increment beyond conflicts. Include every input on both sides in the sum.

- [ ] **Step 3: Add the non-destructive invariant test**

Snapshot each item's `raw_value`, `normalized_value`, `status`, and `verification_state`, run a conflicting equation, and assert the snapshot remains identical. Assert only the check result carries involved concepts and conflict state.

- [ ] **Step 4: Run checks and confirm failure**

Run: `uv run pytest tests/test_statement_checks.py tests/test_semantic_crosspage_checks.py tests/test_semantic_worker.py -q`

Expected: FAIL because only four checks exist and current conflicts clear values.

- [ ] **Step 5: Implement the pure check registry**

In `statement_checks.py`, define immutable coefficient maps for all seven equations. Select inputs only when there is exactly one item for the concept with `status == 'source_verified'`, `mapping_state == 'mapped'`, and non-null `normalized_value`. Compute with `Decimal`; calculate each half-increment tolerance from `source_increment × verified unit scale / 2`.

Return missing disclosure when no item exists for a concept; return unverified source when candidates exist but none is uniquely verified/mapped. Never mutate the statement or its items.

- [ ] **Step 6: Integrate checks after fragment merging**

Replace `_statement_checks` mutation with `evaluate_statement_checks`. Keep formula issues out of deterministic source issues. Attach `checks`, aggregate `formula_status`, and `manual_review_required=False` to each logical statement, and return the same check objects in the table manifest.

- [ ] **Step 7: Run focused check tests**

Run: `uv run pytest tests/test_statement_checks.py tests/test_semantic_crosspage_checks.py tests/test_semantic_worker.py -q`

Expected: PASS; all seven codes exist and formula conflicts preserve source values.

- [ ] **Step 8: Commit Task 4**

```bash
git add src/leasedd/statement_checks.py src/leasedd/financial_semantics.py tests/test_statement_checks.py tests/test_semantic_crosspage_checks.py tests/test_semantic_worker.py
git commit -m "feat: add seven non-destructive statement checks"
```

### Task 5: Replace row repair with one logical-table semantic review

**Files:**
- Modify: `src/leasedd/semantic_pipeline.py`
- Modify: `src/leasedd/extraction_stages.py`
- Modify: `tests/test_semantic_pipeline.py`
- Modify: `tests/test_extraction_stages.py`

**Interfaces:**
- Produces: `semantic_review_count: 0 | 1`, `manual_review_required: bool`, and review request/response summaries per manifest table.
- Uses existing `model_call(stage, payload, contract)` and stage names `review:{table_id}:1:interpret` and `review:{table_id}:1:extract:{part}`.
- Preserves transport retry count in stage checkpoints separately from semantic review count.

- [ ] **Step 1: Add failing review-trigger and stop-condition tests**

Use a deterministic fake model call and assert:

- source-coordinate issue triggers exactly one logical-table review;
- formula `conflict` triggers one review;
- only `not_checked_missing_disclosure` triggers no review;
- review receives original blocks, previous metadata/rows, source issues, formula difference/tolerance, and involved concepts;
- reviewed metadata may correct period/unit/columns and reviewed rows may correct related extraction;
- full source and all applicable formula checks run again;
- a remaining problem sets `manual_review_required=True` without a second review call.

- [ ] **Step 2: Add failing checkpoint/resume tests**

Persist a successful `review:{table_id}:1:*` response through the existing stage cache, simulate worker restart, and assert it is reused. Assert provider attempts remain bounded by the existing three-attempt stage rule while `semantic_review_count` stays one. Verify calls still pass through the existing shared rate limiter.

- [ ] **Step 3: Run review tests and confirm failure**

Run: `uv run pytest tests/test_semantic_pipeline.py tests/test_extraction_stages.py -q`

Expected: FAIL because the current `repair` stage only replaces selected rows and cannot revise metadata or report review state.

- [ ] **Step 4: Implement a single review decision helper**

Add pure helpers in `semantic_pipeline.py`:

```python
def review_reasons(result: dict) -> dict:
    source = sorted(source_problem_codes(result))
    conflicts = [c for c in result['checks'] if c['status'] == 'conflict']
    return {'source_issues': source, 'formula_conflicts': conflicts}

def should_review(reasons: dict) -> bool:
    return bool(reasons['source_issues'] or reasons['formula_conflicts'])
```

Do not include missing-disclosure checks in `formula_conflicts`.

- [ ] **Step 5: Implement review of metadata and relevant rows**

After initial validation, issue at most one interpret review with prior metadata and aggregated problems, then rebuild parts from corrected headers and issue extract review calls only for relevant rows plus headers. Re-run `validate_table` once using corrected metadata/rows. Store initial/final summaries, count 1, and `manual_review_required` based on remaining source issues or conflicts.

Delete the old open-ended row `repair` semantics or map its legacy manifest counter to the new one-review fields without sending both kinds of calls.

- [ ] **Step 6: Run review and rate-limit tests**

Run: `uv run pytest tests/test_semantic_pipeline.py tests/test_extraction_stages.py tests/test_agnes_client.py -q`

Expected: PASS; no logical table has more than one semantic review and every network attempt remains rate-limited.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/leasedd/semantic_pipeline.py src/leasedd/extraction_stages.py tests/test_semantic_pipeline.py tests/test_extraction_stages.py tests/test_agnes_client.py
git commit -m "feat: add bounded statement semantic review"
```

### Task 6: Expose diagnostics through existing runs and the web UI

**Files:**
- Modify: `src/leasedd/worker.py`
- Modify: `src/leasedd/app.py`
- Modify: `tests/test_m2_api.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/financial-view.ts`
- Modify: `frontend/src/FinancialWorkspace.tsx`
- Modify: `frontend/src/financial.css`
- Modify: `frontend/tests/financial-view.test.mjs`
- Modify: `tests/financial_browser_acceptance.py`

**Interfaces:**
- Produces API statement fields: `source_status`, `source_issues`, `formula_status`, `checks`, `semantic_review_count`, `manual_review_required`.
- Consumes diagnostics stored in `ExtractionRun.manifest.tables`; no migration and no new write endpoint.
- Enriches each manifest check's stable evidence locators/concepts with persisted `item_ids` while serializing the matching statement.
- UI displays source and formula states independently and opens check details using existing item/source dialogs.

- [ ] **Step 1: Add failing API projection tests**

Create an extraction run whose manifest table contains a statement key and diagnostics, then assert `/financial-statements` returns:

```python
assert statement['source_status'] == 'consistent'
assert statement['formula_status'] == 'warning'
assert statement['checks'][0]['difference'] == '10000'
assert statement['checks'][0]['involved_concepts'] == ['total_assets', 'total_equity', 'total_liabilities']
assert statement['semantic_review_count'] == 1
assert statement['manual_review_required'] is True
```

Also test legacy runs without diagnostics return safe defaults and current-run selection remains unchanged.

- [ ] **Step 2: Run API tests and confirm failure**

Run: `uv run pytest tests/test_m2_api.py -q`

Expected: FAIL because the statement serializer does not project manifest diagnostics.

- [ ] **Step 3: Implement stable manifest-to-statement association**

Give every logical statement a deterministic `statement_key` derived from table id, entity, scope, currency, raw unit, period kind, normalized period, and raw-header qualifier. Store it in manifest diagnostics and each persisted item's evidence. In `app.py`, load each active run once, index diagnostics by `statement_key`, match every check's involved concepts and evidence locators to the statement's persisted items, add `item_ids`, and return the six API fields. Legacy rows receive `source_status='not_available'`, `formula_status='not_checked'`, empty checks, zero review count, and false manual-review flag.

- [ ] **Step 4: Add failing frontend model tests**

Extend test statement factories with diagnostics. Test helpers that summarize:

- `warning` as “资产负债表勾稽不一致”;
- missing disclosure as “缺少披露项，未检查”;
- source problems separately as “来源待核对”;
- formula conflict without changing `cellState(...).value`.

- [ ] **Step 5: Implement minimal diagnostic UI**

Add a compact banner above the selected statement table. A details element/dialog lists check label, status, difference, tolerance, missing concepts, involved concepts, and buttons to open the existing evidence view for involved item IDs. Use original `source_name` as the primary row label; fall back to catalog label only for rows without a source name.

Do not add correction, approval, rerun, or metric controls.

- [ ] **Step 6: Run frontend and browser tests**

Run: `npm --prefix frontend test && npm --prefix frontend run build`

Run: `uv run python tests/financial_browser_acceptance.py`

Expected: unit tests and build PASS; browser result records separate source/formula banners, accessible detail control, unchanged values, and no write request.

- [ ] **Step 7: Run API tests**

Run: `uv run pytest tests/test_m2_api.py -q`

Expected: PASS for current and legacy runs without a migration.

- [ ] **Step 8: Commit Task 6**

```bash
git add src/leasedd/worker.py src/leasedd/app.py tests/test_m2_api.py frontend/src/api.ts frontend/src/financial-view.ts frontend/src/FinancialWorkspace.tsx frontend/src/financial.css frontend/tests/financial-view.test.mjs tests/financial_browser_acceptance.py
git commit -m "feat: show statement source and formula diagnostics"
```

### Task 7: Run the complete automated regression gate

**Files:**
- Modify: `docs/acceptance/test-results.json`
- Create: `runtime/acceptance/m2-three-statement/pytest.txt`
- Create: `runtime/acceptance/m2-three-statement/frontend-test.txt`
- Create: `runtime/acceptance/m2-three-statement/frontend-build.txt`
- Create: `runtime/acceptance/m2-three-statement/browser-result.json`

**Interfaces:**
- Produces reproducible command/result evidence for every automated acceptance item.
- Does not claim human PDF confirmation.

- [ ] **Step 1: Run the complete backend suite**

Run: `uv run pytest -q`

Expected: all repository tests pass; environment-dependent skips are named and counted, never reported as passes. Run `mkdir -p runtime/acceptance/m2-three-statement`, execute the command through `tee runtime/acceptance/m2-three-statement/pytest.txt`, and preserve the command exit status with `set -o pipefail`.

- [ ] **Step 2: Run the complete frontend suite and build**

Run: `npm --prefix frontend test`

Run: `npm --prefix frontend run build`

Expected: PASS. Save outputs separately in `frontend-test.txt` and `frontend-build.txt`.

- [ ] **Step 3: Run browser regressions**

Run: `uv run python tests/financial_browser_acceptance.py`

Run: `uv run python tests/ui_readability_browser.py`

Confirm both scripts use isolated route fixtures, no write request reaches customer/project data, no console errors occur, and formula warnings do not suppress amounts. Copy their structured summaries into `runtime/acceptance/m2-three-statement/browser-result.json` with keys `financial_workspace` and `ui_readability`.

- [ ] **Step 4: Update the test-results ledger**

Record commit, commands, passed/failed/skipped counts, skip reasons, artifact paths, and explicit scope labels:

```json
{
  "automatic_markdown_verification": "reported separately",
  "human_pdf_confirmation": "not established by automated tests"
}
```

- [ ] **Step 5: Commit Task 7**

```bash
git add docs/acceptance/test-results.json
git commit -m "test: record M2 automated regression evidence"
```

The `runtime/` evidence remains machine-local by repository policy; `docs/acceptance/test-results.json` records its paths and SHA-256 hashes without force-adding ignored runtime files.

### Task 8: Freeze and execute the six-company PDF acceptance set

**Files:**
- Create: `docs/acceptance/m2-three-statement-samples.json`
- Create: `docs/acceptance/m2-three-statement-sampling.csv`
- Create: `docs/acceptance/m2-three-statement-comparison.csv`
- Create: `docs/acceptance/m2-three-statement-results.md`
- Create: `docs/acceptance/m2-three-statement-remaining-issues.md`
- Create: `runtime/acceptance/m2-three-statement/live-runs.json`

**Interfaces:**
- Sample manifest fields: company, exchange/ticker, non-financial classification, report type, reporting period, public PDF URL, SHA-256, layout reasons, local document path.
- Sampling CSV is frozen before running LeaseDD and contains company, statement, account, selection seed/order.
- Comparison CSV columns are exactly: 公司, PDF页码, 科目, 期间, PDF原值, LeaseDD值, 结果, 失败原因.

- [ ] **Step 1: Select and freeze six public reports**

Choose three annual and three half-year reports from six different non-financial listed companies. Require the set collectively to contain cross-page statements, multi-level headers, and multiple disclosed units. Download only from issuer/exchange authoritative public sources, record URL and SHA-256, and verify each file opens as the stated report.

Reject financial institutions and do not use enterprise-warning data as truth.

- [ ] **Step 2: Preselect the comparison rows before extraction**

For every company, record the nine named headline items and choose five ordinary accounts from each of the three statements using a documented deterministic seed/order. Record all selected rows in `m2-three-statement-sampling.csv` before submitting any PDF to LeaseDD. Do not replace a failed sampled row with an easier one.

- [ ] **Step 3: Run all six PDFs through the real pipeline**

For each frozen PDF, run PDF → MinerU Markdown → Agnes → Python source verification → seven checks → at most one review. Capture run id, model, pipeline version, request count, semantic review count, three-table discovery, scope separation, automatic verification totals, and manifest hash in `live-runs.json`.

Do not automatically rerun any pre-existing user upload; use newly registered acceptance documents/projects.

- [ ] **Step 4: Perform the human PDF comparison**

Open the original PDF pages and manually transcribe the disclosed value for every headline and preselected ordinary account across all displayed periods. Fill `m2-three-statement-comparison.csv`. `结果` is only `正确` or `失败`; missing and pending-review LeaseDD values are `失败`. `失败原因` begins with exactly one of 转换, 找表, 期间, 列, 单位, 主体, 科目, followed by an optional concise note.

Any wrong number marked source-passed is listed separately in the results and blocks acceptance until its generic cause is addressed and all affected samples are rerun.

- [ ] **Step 5: Fix only generic failures and rerun affected frozen samples**

For each failure, first add a synthetic failing regression, implement the smallest generic fix through the owning Task 1–6 module, run the focused and full regression gates, then rerun every frozen PDF affected by the same pattern. Do not add company-name or report-specific rules. If new layout coverage is needed, add no more than four companies, preserving the same preselection-before-run rule.

- [ ] **Step 6: Write results and remaining issues**

`m2-three-statement-results.md` separately reports:

- automatic Markdown source-verification results;
- human original-PDF comparison results;
- three-table and consolidated/parent discovery per company;
- headline-item and sampled-row denominators, with missing/pending counted as failures;
- all false source-passed values;
- formula results and one-review stop behavior;
- exact test commands and artifact hashes.

`m2-three-statement-remaining-issues.md` lists every unresolved failure and explicitly states that sample performance does not establish support for arbitrary companies or PDFs.

- [ ] **Step 7: Commit Task 8**

```bash
git add docs/acceptance/m2-three-statement-samples.json docs/acceptance/m2-three-statement-sampling.csv docs/acceptance/m2-three-statement-comparison.csv docs/acceptance/m2-three-statement-results.md docs/acceptance/m2-three-statement-remaining-issues.md
git commit -m "docs: record six-company M2 PDF acceptance"
```

`runtime/acceptance/m2-three-statement/live-runs.json` remains machine-local; the committed results document records its SHA-256 and the immutable input/run identifiers needed to audit it.

### Task 9: Final requirement-by-requirement completion audit

**Files:**
- Modify: `docs/acceptance/m2-three-statement-results.md`
- Modify: `docs/acceptance/m2-three-statement-remaining-issues.md`

**Interfaces:**
- Produces the final delivery statement and evidence index.
- Completion is allowed only if every explicit goal requirement has direct current-state evidence.

- [ ] **Step 1: Audit every specification section against artifacts**

Build a table with one row for each contract field, source check, period rule, equation, review invariant, API/UI requirement, automated case, live-sample requirement, and deliverable. Link each row to code, a passing test/output, or a comparison-sheet range. Mark missing/indirect evidence as not complete.

- [ ] **Step 2: Verify the worktree and immutable history**

Run: `git status --short`

Run: `git log --oneline --decorate -12`

Confirm only intended files changed, no historical extraction batch was mutated, and no acceptance task silently reran existing uploaded material.

- [ ] **Step 3: Re-run final gates from the delivery commit**

Run: `uv run pytest -q`

Run: `npm --prefix frontend test && npm --prefix frontend run build`

Run the isolated browser acceptance and verify the six live-run manifest hashes still match the recorded inputs/results.

- [ ] **Step 4: Record honest completion status**

If any required live PDF, human comparison row, false source-passed remediation, or regression remains incomplete, keep the goal active and list the exact remaining item. Only when every row has direct evidence should the goal be marked complete.

- [ ] **Step 5: Commit the final audit**

```bash
git add docs/acceptance/m2-three-statement-results.md docs/acceptance/m2-three-statement-remaining-issues.md
git commit -m "docs: complete M2 three-statement audit"
```
