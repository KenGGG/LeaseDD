from types import SimpleNamespace

from sqlalchemy import func, select

from leasedd.db import (
    Base, EnterpriseBinding, EnterpriseFinancialData, EnterpriseImport,
    Project, Task, User, database,
)
from leasedd.enterprise_import import enqueue_enterprise_import
from leasedd.enterprise_warning import CollectedModule, EnterpriseModule, EnterpriseWarningError
from leasedd.worker import run_once


def modules():
    result = []
    for index in range(17):
        category = "statements" if index < 4 else ("analysis" if index < 11 else "notes")
        endpoint = "/report/getThreeReports" if category == "statements" else "/module"
        result.append(EnterpriseModule(f"module-{index}", f"模块{index}", category, endpoint, index))
    return result


class FakeCollector:
    def __init__(self, failures=(), warning=False):
        self.failures = set(failures)
        self.warning = warning
        self.collected = []
        self.agnes = property(lambda _: (_ for _ in ()).throw(AssertionError("Agnes accessed")))

    def enumerate_modules(self, company_code):
        return modules()

    def collect_module(self, company_code, module):
        self.collected.append(module.key)
        if module.key in self.failures:
            raise EnterpriseWarningError("structure_changed")
        parsed = {"periods": ["2025-12-31"], "rows": []}
        if self.warning and module.key == "module-0":
            parsed["checks"] = [{"status": "conflict"}]
        return CollectedModule(module, {"data": {"key": module.key}}, parsed, f"{module.order:064x}")


def seeded(tmp_path, collector):
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine, factory = database(f"sqlite:///{tmp_path}/enterprise.db")
    Base.metadata.create_all(engine)
    app = SimpleNamespace(state=SimpleNamespace(db=factory, engine=engine, enterprise_collector=collector))
    with factory.begin() as db:
        user = User(username="admin", password_hash="x", admin=True)
        project = Project(name="测试公司")
        db.add_all([user, project]); db.flush()
        binding = EnterpriseBinding(project_id=project.id, company_code="company-1", company_name="测试公司", identity={}, created_by=user.id, created_at=1)
        db.add(binding); db.flush()
        task, record = enqueue_enterprise_import(db, project, binding, user)
        return app, factory, project.id, user.id, binding.id, task.id, record.id


def test_worker_imports_all_modules_without_agnes(tmp_path):
    collector = FakeCollector()
    app, factory, project_id, _, _, task_id, import_id = seeded(tmp_path, collector)
    assert run_once(app)
    with factory() as db:
        task, record = db.get(Task, task_id), db.get(EnterpriseImport, import_id)
        assert task.state == "completed"
        assert record.state == "completed"
        assert record.quality_state == "passed"
        assert len(record.content_sha256) == 64
        assert db.scalar(select(func.count()).select_from(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_id)) == 17
    assert collector.collected == [f"module-{index}" for index in range(17)]


def test_partial_and_total_failure_are_recorded_without_losing_successes(tmp_path):
    collector = FakeCollector({"module-5"})
    app, factory, _, _, _, task_id, import_id = seeded(tmp_path, collector)
    assert run_once(app)
    with factory() as db:
        record = db.get(EnterpriseImport, import_id)
        assert db.get(Task, task_id).state == "completed"
        assert record.state == "partial"
        assert record.quality_state == "passed_with_gaps"
        assert record.module_status["module-5"] == {"state": "failed", "error": "structure_changed"}
        assert db.scalar(select(func.count()).select_from(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_id)) == 16

    collector = FakeCollector({f"module-{index}" for index in range(17)})
    app, factory, _, _, _, _, import_id = seeded(tmp_path / "all", collector)
    assert run_once(app)
    with factory() as db:
        assert db.get(EnterpriseImport, import_id).state == "failed"


def test_formula_conflict_is_warning_not_failed_import(tmp_path):
    app, factory, _, _, _, _, import_id = seeded(tmp_path, FakeCollector(warning=True))
    assert run_once(app)
    with factory() as db:
        record = db.get(EnterpriseImport, import_id)
        assert record.state == "completed"
        assert record.quality_state == "warning"


def test_enqueue_deduplicates_active_task_and_retry_reuses_import(tmp_path):
    collector = FakeCollector({"module-5"})
    app, factory, project_id, user_id, binding_id, task_id, import_id = seeded(tmp_path, collector)
    with factory.begin() as db:
        same_task, same_import = enqueue_enterprise_import(db, db.get(Project, project_id), db.get(EnterpriseBinding, binding_id), db.get(User, user_id))
        assert (same_task.id, same_import.id) == (task_id, import_id)
    assert run_once(app)
    with factory.begin() as db:
        retry_task, retry_import = enqueue_enterprise_import(
            db, db.get(Project, project_id), db.get(EnterpriseBinding, binding_id), db.get(User, user_id), failed_modules=["module-5"]
        )
        retry_task_id = retry_task.id
        assert retry_import.id == import_id
        assert retry_task.id != task_id
    collector.failures.clear(); collector.collected.clear()
    assert run_once(app)
    assert collector.collected == ["module-5"]
    with factory() as db:
        assert db.get(Task, retry_task_id).state == "completed"
        assert db.get(EnterpriseImport, import_id).state == "completed"
        assert db.scalar(select(func.count()).select_from(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_id)) == 17
