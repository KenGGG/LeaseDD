# Enterprise Warning Acquisition Probe Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine exactly how the currently logged-in 企业预警通 browser obtains company search results and every dataset under 财务数据 before LeaseDD builds any production integration.

**Architecture:** Attach read-only to the existing browser session, observe the site's own network traffic while navigating one known company, and save only redacted request/response contracts plus structural summaries. This phase is a probe, not production code: it must stop after reporting whether the eventual adapter can use stable JSON/XHR or exports and how much DOM fallback is actually required.

**Tech Stack:** Existing logged-in Chromium/Chrome session, Playwright CLI or a throwaway Python Playwright probe, JSON/CSV/XLSX inspection, SHA-256.

**Spec:** `docs/superpowers/specs/2026-09-21-enterprise-warning-financial-import.md`

## Global Constraints

- Work only on `main`; do not create a worktree or delegate to subagents.
- Do not modify LeaseDD product code, database models, migrations, project creation, APIs, worker, or frontend in this phase.
- Do not create the four test projects in this phase.
- Reuse the current logged-in browser without closing, restarting, or replacing it.
- Never read, print, store, or commit passwords, cookies, authorization headers, browser profile data, CDP endpoints, or signed secret query parameters.
- Prefer observing the site's existing JSON/XHR and download/export traffic; use DOM only to cause the normal page to load data.
- Restrict observation to 企业搜索 and the 财务数据 column: 主要财务指标、资产负债表、利润表、现金流量表、财务分析及 descendants、财务附注及 descendants.
- Runtime captures stay under `runtime/acceptance/enterprise-warning-probe/` and remain uncommitted.
- Committed fixtures must be minimal, synthetic or irreversibly redacted, and contain no authentication material or licensed bulk financial values.
- **Hard stop:** after the acquisition contract and findings are committed, stop implementation and request human review. Do not start the adapter or persistence design.

## Review Focus

- HTTP 200 login pages or expired-session JSON must be reported as `login_expired`, not mistaken for an empty company or empty financial dataset.
- One visible module may trigger multiple requests; identify the authoritative payload rather than counting all network responses as distinct datasets.
- Lazy loading, pagination, period switching, scrolling, and expandable descendants must be exercised so “all data” is not inferred from the first screen.
- Query strings and response bodies can contain tokens or user identifiers; redact by allowlist and inspect the final artifacts before committing.
- The known company may have cached page data; repeat one request path after a fresh navigation to distinguish browser cache from a reproducible endpoint.

---

### Task A: Probe and document the real 企业预警通 acquisition contract

**Files:**
- Create: `tools/qyyjt_probe.py` only if Playwright CLI network inspection cannot export the required response metadata safely.
- Create: `docs/acceptance/qyyjt-acquisition-contract.md`
- Create: `docs/acceptance/qyyjt-acquisition-summary.json`
- Runtime only: `runtime/acceptance/enterprise-warning-probe/`

**Interfaces:**
- Consumes: the existing logged-in browser session and normal visible 企业预警通 pages.
- Produces: a redacted summary with these top-level keys:

```json
{
  "probe_company": "铭普光磁",
  "search": {"transport": "xhr|document", "method": "GET|POST", "path_template": "...", "candidate_fields": []},
  "categories": [],
  "history_loading": "single_response|per_period|pagination|mixed",
  "descendant_loading": "index_response|per_module|frontend_static|mixed",
  "exports": [],
  "dom_fallbacks": [],
  "recommended_shape": "direct_json|export_parser|hybrid|dom_heavy",
  "estimated_product_scope": "small|medium|large"
}
```

Each category entry must state its transport, endpoint path template, request count, whether one response contains all periods, unit location, value shape, descendant discovery mechanism, export availability, and any required DOM fallback.

- [ ] **Step 1: Establish a safe runtime capture directory**

Run:

```bash
mkdir -p runtime/acceptance/enterprise-warning-probe
git check-ignore runtime/acceptance/enterprise-warning-probe
```

Expected: the runtime directory is ignored. If it is not ignored, add only `runtime/` to `.gitignore`, verify again, and commit that one-line safety change before capturing anything.

- [ ] **Step 2: Verify the existing browser session without exposing credentials**

Use the existing browser-control mechanism to list tabs and inspect only page title, origin, and login-state UI. Do not dump storage, cookies, request headers, environment variables, process command lines, or browser profile paths.

Expected: an authenticated `qyyjt.cn` page is available. If the session is logged out or cannot be attached read-only, record `blocked: login_expired` or `blocked: browser_not_attachable` in the summary and stop without changing product code.

- [ ] **Step 3: Capture company-search behavior**

From the normal search UI, search `铭普光磁`, then one deliberately ambiguous short name such as `科技`. Record only:

```text
HTTP method
origin-relative path template
allowlisted non-secret parameters
response media type
candidate identity fields: enterprise code, full name, listing indicator, finance-availability indicator
multiple-candidate behavior
```

Replace enterprise-specific result values with field names in committed documentation. Keep raw response bodies only in the ignored runtime directory.

- [ ] **Step 4: Enumerate the complete 财务数据 navigation tree**

Open the known 铭普光磁 财务数据 page and enumerate these six top-level categories in displayed order:

```text
主要财务指标
资产负债表
利润表
现金流量表
财务分析
财务附注
```

Expand every 财务分析 and 财务附注 descendant. Compare the visible tree with any menu/index XHR payload. Record whether descendants come from an index response, frontend constants, or per-module discovery. A category is not considered enumerated until scrolling or pagination no longer reveals another descendant.

- [ ] **Step 5: Capture authoritative financial payloads**

For each top-level category and every descendant, trigger its normal load once and record the authoritative response. Determine:

```text
whether JSON/XHR exists
whether Excel/CSV export exists
whether all periods are in one response
whether period switching sends another request
whether scrolling or pagination sends another request
where currency/unit appears
how row labels, hierarchy, blank cells, adjusted periods, and values are encoded
```

For one three-statement module, one financial-analysis descendant, and one financial-note descendant, repeat after fresh navigation and compare response structure and content hash. Do not treat unstable request IDs or timestamps as schema fields.

- [ ] **Step 6: Test download/export paths without bulk archiving**

Where the page exposes Excel or CSV export, download one representative file into the ignored runtime directory. Record file type, sheet names, row/column organization, periods, units, and whether the export covers all descendants or only the selected module. Do not commit the downloaded file or its full financial contents.

- [ ] **Step 7: Produce the acquisition contract**

Write `docs/acceptance/qyyjt-acquisition-contract.md` with:

1. Browser attachment and login-state result.
2. Search request contract and candidate fields.
3. The complete six-category tree and every observed descendant name.
4. One table per category: transport, path template, method, periods, pagination, unit/value encoding, export, DOM fallback.
5. A minimal redacted response shape showing field names and types, not bulk values.
6. Evidence for whether endpoints can be replayed only inside page context or through ordinary HTTP with the attached session.
7. Known instability and the smallest recommended LeaseDD adapter.

Write `docs/acceptance/qyyjt-acquisition-summary.json` matching the output schema above. Use `null` or an explicit `unknown_reason` only when the probe could not observe a property; never infer a clean API that was not observed.

- [ ] **Step 8: Run a credential and completeness audit**

Run:

```bash
rg -ni 'cookie|authorization|bearer|password|token|session|set-cookie|cdp|websocket|user-data-dir' \
  docs/acceptance/qyyjt-acquisition-contract.md \
  docs/acceptance/qyyjt-acquisition-summary.json
python -m json.tool docs/acceptance/qyyjt-acquisition-summary.json >/dev/null
```

Expected: the JSON is valid. Every regex match is either a generic field-name discussion or is removed; no credential value, browser endpoint, profile path, or signed URL remains. Manually verify the category list contains all six entries and that 财务分析/财务附注 descendant counts are nonzero.

- [ ] **Step 9: Classify the minimum next implementation**

Use observed evidence to select exactly one recommendation:

- `direct_json / small`: stable structured search, index, and financial endpoints; no material DOM parsing.
- `export_parser / small`: stable complete Excel/CSV exports are simpler than endpoint replay.
- `hybrid / medium`: structured payloads cover most data, with bounded DOM fallback for named modules.
- `dom_heavy / large`: material data requires interactive expansion, scrolling, or visual DOM extraction.

State the estimated production entities, endpoints, and UI changes needed, but do not create them. Explicitly identify which parts of the former nine-task plan can be deleted.

- [ ] **Step 10: Commit only the redacted findings and stop**

Run:

```bash
git add docs/acceptance/qyyjt-acquisition-contract.md docs/acceptance/qyyjt-acquisition-summary.json
git diff --cached --check
git diff --cached
git commit -m "docs: record enterprise warning acquisition contract"
```

Expected: the commit contains only the two redacted findings files, plus `.gitignore` only when Step 1 required it. Runtime captures and probe downloads remain untracked/ignored.

After the commit, report the real interface shape, completeness mechanism, likely code size, and recommended next plan. **Stop. Do not implement Task B, C, D, or E until the user reviews these findings.**
