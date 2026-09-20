# LeaseDD M2 Markdown 财务提取实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PDF、图片、DOCX、XLSX 等原件转换为可追溯 Markdown，以两阶段 Agnes 任务定位并提取财务报表，校验每个来源数字，并在 WebUI 中完成人工确认。

**Architecture:** worker 负责转换和两阶段提取；MinerU 处理 PDF/图片，MarkItDown 处理 Office，文本格式直接规范化。数据库分别保存转换记录、报表候选和财务项目；API 只返回项目成员有权查看的数据与 Markdown 片段。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy/Alembic、Pydantic、httpx、MarkItDown、MinerU、PostgreSQL、React/TypeScript。

**Spec:** 当前线程 Goal「LeaseDD M2：资料 Markdown 化与财务数据提取」。

## Global Constraints

- 原件不可修改；转换前后复核原件 SHA256。
- 长文档按行与字符预算分块；定位阶段不抽取全表，提取阶段只发送命中的小范围。
- 模型返回的 raw_value 必须在实际发送的 Markdown 片段中经格式标准化后找到。
- 缺失值不得补零；主体、期间、单位、口径不明确时进入人工确认。
- 不开发 OCR、Office 转换引擎、完整报告、风险、审批、向量库或额外财务指标。
- 所有项目正文、Markdown 和财务数据接口继续执行项目成员鉴权。

## Review Focus

- 千分位、括号负数和全角字符的数字来源校验。
- `2026H1` 与 `2026Q2`、时点与期间的严格区分。
- 同一科目多值、未知单位和未知口径不能自动确认。
- Markdown 超长或恶意文档内容不得突破每次模型调用预算。
- 原件在转换期间被替换时任务必须失败且不得登记 Markdown。

---

### Task 1: 财务契约、科目表和来源数字校验

**Files:** Create `src/leasedd/finance_extract.py`; modify `src/leasedd/contracts.py`; test `tests/test_m2_finance.py`.

**Interfaces:** Produces `chunk_markdown`, `normalize_source_number`, `validate_extracted_statement` and strict statement models.

- [ ] Write failing tests for chunk budgets, periods, units, concept allow-list, source matching and uncertain states.
- [ ] Run the focused tests and confirm failures are caused by missing M2 interfaces.
- [ ] Implement the minimal pure functions and models.
- [ ] Run focused and existing rule tests.

### Task 2: 转换适配器与不可变产物

**Files:** Create `src/leasedd/conversion.py`; modify `pyproject.toml`, `uv.lock`; test `tests/test_m2_conversion.py`.

**Interfaces:** Consumes original path/hash; produces Markdown text plus tool/version metadata. MinerU and MarkItDown calls are dependency-injected for tests.

- [ ] Write failing tests for routing, success metadata, conversion errors and original-hash changes.
- [ ] Implement TXT/MD/CSV direct conversion, MarkItDown Office conversion and MinerU async conversion.
- [ ] Confirm each adapter records tool/version and never mutates originals.

### Task 3: 数据库迁移与 M2 API

**Files:** Modify `src/leasedd/db.py`, `src/leasedd/app.py`, `src/leasedd/contracts.py`; create `deployment/migrations/versions/0003_m2_finance.py`; test `tests/test_m2_api.py`.

**Interfaces:** Stores one immutable conversion per attempt, statement candidates and items; exposes conversion, Markdown source, financial statement listing and confirmation endpoints.

- [ ] Write failing API tests for membership, source visibility, status, confirmation and ambiguity.
- [ ] Add schema/migration and API behavior.
- [ ] Run API tests on SQLite and PostgreSQL.

### Task 4: worker 两阶段定位与提取

**Files:** Modify `src/leasedd/worker.py`; create `src/leasedd/agnes_finance.py`; test `tests/test_m2_worker.py`.

**Interfaces:** Upload queues `extract_finance`; worker converts, chunks, locates statement ranges, extracts only selected slices, validates source values and persists candidates.

- [ ] Write failing tests that capture model payload sizes and prove no full long document is sent.
- [ ] Add strict JSON parsing, range merging, retry-safe persistence and stable failure reasons.
- [ ] Test unknown citations, invented values, missing units, conflicting candidates and stale source hashes.

### Task 5: WebUI 财务数据与来源确认

**Files:** Modify `frontend/src/api.ts`, `frontend/src/main.tsx`, `frontend/src/style.css`; update browser acceptance.

**Interfaces:** Displays document conversion status and entity → statement → period → item hierarchy; source modal shows only the stored Markdown slice; writers can confirm/reject candidates.

- [ ] Add UI behavior and browser assertions for progress, source viewing and confirmation.
- [ ] Build TypeScript and run browser acceptance.

### Task 6: 实际工具与格式验收

**Files:** Add safe generated fixtures under `fixtures/m2/`; update `docs/acceptance/M2.md`, `docs/acceptance/test-results.json`, README and deployment environment.

**Interfaces:** Docker worker reaches host MinerU and contains MarkItDown; acceptance records original/Markdown hashes, tool versions, model call budgets and results.

- [ ] Exercise DOCX and XLSX through MarkItDown and PDF/image through MinerU.
- [ ] Exercise a public or explicitly de-identified financial sample without committing sensitive source files.
- [ ] Run all Python tests, frontend build, migrations, Compose smoke test and M0/M1 regression.
- [ ] Record remaining limits honestly.
