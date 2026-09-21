"""Run the explicitly approved four-company 企业预警通 acceptance sample."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

from sqlalchemy import select

from leasedd.app import create_app
from leasedd.db import EnterpriseBinding, EnterpriseFinancialData, EnterpriseImport, Member, Project, Task, User
from leasedd.enterprise_import import enqueue_enterprise_import, run_enterprise_import
from leasedd.enterprise_views import enterprise_statement_views
from leasedd.enterprise_warning import QyjCollector


APPROVED = {"金银河", "德方纳米", "气派科技", "昊志机电"}
SAMPLES = ("total_assets", "total_liabilities", "net_profit", "net_operating_cash_flow")


def project_members(db, name):
    source = db.scalar(select(Project).where(Project.name.contains(name)))
    if not source:
        raise RuntimeError("membership_source_project_missing")
    return [(member.user_id, member.role) for member in db.scalars(select(Member).where(Member.project_id == source.id))]


def ensure_project(db, name, members):
    project = db.scalar(select(Project).where(Project.name == name))
    if project:
        return project
    project = Project(name=name)
    db.add(project); db.flush()
    for user_id, role in members:
        db.add(Member(project_id=project.id, user_id=user_id, role=role))
    return project


def finish_task(app, task_id, lease, result):
    with app.state.db.begin() as db:
        task = db.get(Task, task_id)
        if task.lease_token != lease:
            raise RuntimeError("lease_lost")
        task.state = "completed"; task.result = {**task.result, **result}; task.reason = None; task.lease_until = 0


def acceptance_result(db, project, binding, record, elapsed):
    rows = list(db.scalars(select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == record.id)))
    views = enterprise_statement_views(record, [row for row in rows if row.category == "statements"])
    periods = {row.module_key: len((row.parsed_payload or {}).get("periods", [])) for row in rows}
    samples = []
    for concept in SAMPLES:
        item = next((item for view in views for item in view["items"] if item["concept"] == concept), None)
        samples.append({"concept": concept, "present": item is not None})
    checks = sorted({check["status"] for view in views for check in view.get("checks", [])})
    failed = [key for key, value in (record.module_status or {}).items() if value.get("state") == "failed"]
    return {"project": project.name, "matched_company_name": binding.company_name, "matched_company_code": binding.company_code,
            "module_coverage": {"completed": len(rows), "expected": 17}, "period_counts": periods,
            "selected_samples": samples, "formula_statuses": checks, "enterprise_elapsed_seconds": elapsed,
            "pdf_agnes_elapsed_seconds": None, "failed_modules": failed, "agnes_calls": 0}


def import_company(app, name, creator, members):
    collector = app.state.enterprise_collector
    resume = None
    with app.state.db() as db:
        existing = db.scalar(select(Project).where(Project.name == name))
        binding = db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id == existing.id)) if existing else None
        record = db.scalar(select(EnterpriseImport).where(EnterpriseImport.project_id == existing.id, EnterpriseImport.state.in_(("completed", "partial"))).order_by(EnterpriseImport.completed_at.desc())) if existing else None
        if binding and record:
            count = len(list(db.scalars(select(EnterpriseFinancialData.id).where(EnterpriseFinancialData.import_id == record.id))))
            if count == 17:
                return acceptance_result(db, existing, binding, record, round((record.completed_at or 0) - (record.started_at or 0), 3))
            resume = (binding.company_code, binding.company_name, binding.identity,
                      [key for key, value in (record.module_status or {}).items() if value.get("state") == "failed"])
    if resume:
        from leasedd.enterprise_warning import EnterpriseCandidate
        candidate = EnterpriseCandidate(resume[0], resume[1], resume[2]); failed_modules = resume[3]
    else:
        try:
            candidates = collector.search(name)
        except Exception:
            candidates = collector.search(name)
        exact = [candidate for candidate in candidates if name in candidate.name and candidate.identity.get("type") == "company" and candidate.name.endswith("股份有限公司")]
        if len(exact) != 1:
            raise RuntimeError(f"explicit_match_required:{name}:{len(exact)}")
        candidate = exact[0]; failed_modules = None
    with app.state.db.begin() as db:
        project = ensure_project(db, name, members)
        binding = db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id == project.id))
        if not binding:
            binding = EnterpriseBinding(project_id=project.id, company_code=candidate.code, company_name=candidate.name,
                                        identity=candidate.identity, created_by=creator.id, created_at=time.time())
            db.add(binding); db.flush()
        task, record = enqueue_enterprise_import(db, project, binding, creator, failed_modules=failed_modules)
        if task.state == "completed":
            task.state = "queued"
        task.state = "running"; task.attempts += 1; task.lease_token = os.urandom(16).hex(); task.lease_until = time.time() + 1800
        task_id, import_id, lease, project_id = task.id, record.id, task.lease_token, project.id
    started = time.monotonic()
    result = run_enterprise_import(app, task_id, lease)
    finish_task(app, task_id, lease, result)
    elapsed = round(time.monotonic() - started, 3)
    with app.state.db() as db:
        return acceptance_result(db, db.get(Project, project_id), db.get(EnterpriseBinding, binding.id), db.get(EnterpriseImport, import_id), elapsed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if set(args.companies) - APPROVED or len(args.companies) != 4:
        raise SystemExit("only_the_four_approved_companies_are_allowed")
    app = create_app(os.environ.get("LEASEDD_DATABASE_URL"), os.environ.get("LEASEDD_DATA_DIR"), initialize=False)
    app.state.enterprise_collector = QyjCollector()
    with app.state.db() as db:
        members = project_members(db, "铭普光磁")
        creator = next((db.get(User, user_id) for user_id, role in members if role == "writer"), None)
        if not creator:
            raise RuntimeError("writer_missing")
        db.expunge(creator)
    results = [import_company(app, name, creator, members) for name in args.companies]
    payload = {"companies": results, "enterprise_median_seconds": statistics.median(item["enterprise_elapsed_seconds"] for item in results),
               "pdf_agnes_median_seconds": None, "speed_comparison": "unproven_without_comparable_pdf_timing",
               "scope": "Only the four approved companies and the current 企业预警通 version."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
