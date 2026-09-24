"""Read-only verification of the four approved enterprise financial imports."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
from pathlib import Path

from sqlalchemy import select

from leasedd.app import create_app
from leasedd.db import EnterpriseBinding, EnterpriseFinancialData, EnterpriseImport, Project, Task
from leasedd.enterprise_views import enterprise_statement_views
from leasedd.enterprise_warning import MODULES


APPROVED = {"金银河", "德方纳米", "气派科技", "昊志机电"}
SAMPLES = ("total_assets", "total_liabilities", "net_profit", "net_operating_cash_flow")


def acceptance_result(db, project, binding, record, elapsed):
    rows = list(db.scalars(select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == record.id)))
    statuses = record.module_status or {}
    expected = len(MODULES)
    counts = {state: sum(row.state == state for row in rows) for state in ('completed', 'unavailable')}
    counts.update(failed=sum(value.get('state') == 'failed' for value in statuses.values()),
                  missing=max(0, expected-len(statuses)), expected=expected)
    views = enterprise_statement_views(record, [row for row in rows if row.category == "statements"])
    periods = {row.module_key: len(row.parsed_payload['periods']) for row in rows
               if isinstance((row.parsed_payload or {}).get('periods'), list)}
    record_groups = {}
    for row in rows:
        if row.state != 'completed':
            continue
        parsed = row.parsed_payload or {}
        head, records = parsed.get('head'), parsed.get('rows')
        if isinstance(head, list) and head and isinstance(head[0], list):
            record_groups[row.module_key] = len(head)
        elif isinstance(head, list) and isinstance(records, list) and records and all(
            isinstance(record, list) and record and re.fullmatch(r'\d{8}', str(record[0])) for record in records
        ):
            record_groups[row.module_key] = len(records)
    samples = []
    for concept in SAMPLES:
        item = next((item for view in views for item in view["items"] if item["concept"] == concept), None)
        samples.append({"concept": concept, "present": item is not None})
    checks = sorted({check["status"] for view in views for check in view.get("checks", [])})
    failed = [key for key, value in (record.module_status or {}).items() if value.get("state") == "failed"]
    return {"project": project.name, "matched_company_name": binding.company_name, "matched_company_code": binding.company_code,
            "import_state": record.state, "module_coverage": counts, "period_counts": periods,
            "record_group_counts": record_groups,
            "selected_samples": samples, "formula_statuses": checks, "enterprise_elapsed_seconds": elapsed,
            "pdf_agnes_elapsed_seconds": None, "failed_modules": failed, "agnes_calls": 0}


def verify_company(app, name):
    with app.state.db() as db:
        existing = db.scalar(select(Project).where(Project.name == name))
        binding = db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id == existing.id)) if existing else None
        record = db.scalar(select(EnterpriseImport).where(EnterpriseImport.project_id == existing.id, EnterpriseImport.state.in_(("completed", "partial"))).order_by(EnterpriseImport.completed_at.desc())) if existing else None
        if not binding or not record:
            raise RuntimeError(f"current_enterprise_import_missing:{name}")
        task = db.get(Task, record.task_id)
        company_code = (task.result or {}).get('company_code') if task else None
        if not company_code:
            codes = {str(code) for params in db.scalars(select(EnterpriseFinancialData.request_params).where(
                EnterpriseFinancialData.import_id == record.id))
                if (code := (params or {}).get('company_code') or (params or {}).get('code'))}
            company_code = next(iter(codes)) if len(codes) == 1 else None
        if company_code != binding.company_code:
            raise RuntimeError(f"source_company_mismatch:{name}")
        started_at = task.created_at if task else record.started_at
        return acceptance_result(db, existing, binding, record, round((record.completed_at or 0) - (started_at or 0), 3))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if set(args.companies) - APPROVED or len(args.companies) != 4:
        raise SystemExit("only_the_four_approved_companies_are_allowed")
    app = create_app(os.environ.get("LEASEDD_DATABASE_URL"), os.environ.get("LEASEDD_DATA_DIR"), initialize=False)
    results = [verify_company(app, name) for name in args.companies]
    payload = {"companies": results, "enterprise_median_seconds": statistics.median(item["enterprise_elapsed_seconds"] for item in results),
               "pdf_agnes_median_seconds": None, "speed_comparison": "unproven_without_comparable_pdf_timing",
               "scope": "Only the four approved companies and the current 企业预警通 version."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
