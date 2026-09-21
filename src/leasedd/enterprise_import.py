"""Enterprise module import orchestration on the existing task queue."""

from __future__ import annotations

import hashlib
import time

from sqlalchemy import select

from .db import EnterpriseFinancialData, EnterpriseImport, Task
from .domain import snapshot_hash


def enqueue_enterprise_import(db, project, binding, user, failed_modules=None):
    active = db.scalar(select(Task).where(
        Task.project_id == project.id, Task.kind == "enterprise_import", Task.state.in_(("queued", "running"))
    ).order_by(Task.created_at.desc()))
    if active:
        return active, db.scalar(select(EnterpriseImport).where(EnterpriseImport.task_id == active.id))

    record = None
    if failed_modules:
        record = db.scalar(select(EnterpriseImport).where(
            EnterpriseImport.project_id == project.id
        ).order_by(EnterpriseImport.started_at.desc()))
    task = Task(project_id=project.id, kind="enterprise_import", mode="qyyjt", state="queued",
                input_revision=project.revision, input_hash=snapshot_hash(db, project), result={
                    "binding_id": binding.id, "failed_modules": list(failed_modules or [])
                }, created_by=user.id, created_at=time.time())
    db.add(task); db.flush()
    if record:
        record.task_id = task.id
        record.state = "queued"
        record.error = None
        record.completed_at = None
    else:
        record = EnterpriseImport(project_id=project.id, task_id=task.id, state="queued", quality_state="not_checked",
                                  module_status={}, error=None, content_sha256=None, started_at=None, completed_at=None)
        db.add(record); db.flush()
    task.result = {**task.result, "import_id": record.id}
    return task, record


def _active(task, lease):
    if not task or task.state != "running" or task.lease_token != lease or task.lease_until <= time.time():
        from .worker import TaskError
        raise TaskError("lease_lost")


def _has_warning(parsed):
    return any(check.get("status") in ("conflict", "warning") for check in parsed.get("checks", []))


def run_enterprise_import(app, task_id, lease_token):
    collector = app.state.enterprise_collector
    with app.state.db() as db:
        task = db.get(Task, task_id)
        record = db.get(EnterpriseImport, task.result["import_id"])
        from .db import EnterpriseBinding
        binding = db.get(EnterpriseBinding, task.result["binding_id"])
        company_code = binding.company_code
        requested = set(task.result.get("failed_modules") or [])
    modules = collector.enumerate_modules(company_code)
    if len(modules) != 17 or len({module.key for module in modules}) != 17:
        from .worker import TaskError
        raise TaskError("structure_changed")
    if requested:
        modules = [module for module in modules if module.key in requested]

    with app.state.db.begin() as db:
        task = db.get(Task, task_id)
        _active(task, lease_token)
        record = db.get(EnterpriseImport, record.id)
        record.state = "running"
        record.started_at = record.started_at or time.time()

    warning = False
    for module in modules:
        try:
            collected = collector.collect_module(company_code, module)
        except Exception as error:
            code = getattr(error, "code", "module_collection_failed")
            with app.state.db.begin() as db:
                task = db.get(Task, task_id)
                _active(task, lease_token)
                record = db.get(EnterpriseImport, record.id)
                status = dict(record.module_status or {})
                status[module.key] = {"state": "failed", "error": code}
                record.module_status = status
            continue

        warning = warning or _has_warning(collected.parsed)
        with app.state.db.begin() as db:
            task = db.get(Task, task_id)
            _active(task, lease_token)
            record = db.get(EnterpriseImport, record.id)
            row = db.scalar(select(EnterpriseFinancialData).where(
                EnterpriseFinancialData.import_id == record.id,
                EnterpriseFinancialData.module_key == module.key,
            ))
            values = dict(category=module.category, module_key=module.key, module_name=module.name,
                          module_order=module.order, endpoint_path=module.endpoint_path,
                          request_params=module.request_params, raw_payload=collected.raw,
                          parsed_payload=collected.parsed, response_sha256=collected.response_sha256,
                          state="completed", error=None, collected_at=time.time())
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                db.add(EnterpriseFinancialData(import_id=record.id, **values))
            status = dict(record.module_status or {})
            status[module.key] = {"state": "completed", "error": None}
            record.module_status = status

    with app.state.db.begin() as db:
        task = db.get(Task, task_id)
        _active(task, lease_token)
        record = db.get(EnterpriseImport, record.id)
        statuses = record.module_status or {}
        successful = [key for key, value in statuses.items() if value.get("state") == "completed"]
        failed = [key for key, value in statuses.items() if value.get("state") == "failed"]
        record.state = "failed" if not successful else ("partial" if failed else "completed")
        if record.state == "failed":
            record.quality_state = "failed"
        elif failed:
            record.quality_state = "passed_with_gaps"
        else:
            all_rows = list(db.scalars(select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == record.id)))
            warning = warning or any(_has_warning(row.parsed_payload or {}) for row in all_rows)
            record.quality_state = "warning" if warning else "passed"
        hashes = list(db.execute(select(EnterpriseFinancialData.module_key, EnterpriseFinancialData.response_sha256).where(
            EnterpriseFinancialData.import_id == record.id
        ).order_by(EnterpriseFinancialData.module_key)))
        record.content_sha256 = hashlib.sha256("".join(f"{key}:{value}" for key, value in hashes).encode()).hexdigest() if hashes else None
        record.completed_at = time.time()
        return {"import_id": record.id, "state": record.state, "quality_state": record.quality_state,
                "failed_modules": failed, "module_count": len(successful), "content_sha256": record.content_sha256}
