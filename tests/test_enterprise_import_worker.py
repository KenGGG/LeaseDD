from dataclasses import replace
from types import SimpleNamespace

import pytest

from sqlalchemy import func, select

from leasedd.db import (
    Base, EnterpriseBinding, EnterpriseFinancialData, EnterpriseImport,
    Project, Task, User, database,
)
from leasedd.enterprise_import import enqueue_enterprise_import
from leasedd.enterprise_warning import CollectedModule, EnterpriseModule, EnterpriseWarningError, MODULES
from leasedd.worker import run_once


def modules():
    result = []
    for index in range(len(MODULES)):
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
        collected_module = replace(module, request_params={"unit": "万元", "source": "xhr"})
        return CollectedModule(collected_module, {"data": {"key": module.key}}, parsed, f"{module.order:064x}")


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


def test_queued_import_keeps_original_company_when_binding_changes(tmp_path):
    class IdentityCollector(FakeCollector):
        def enumerate_modules(self, company_code):
            assert company_code == 'company-1'
            return super().enumerate_modules(company_code)

        def collect_module(self, company_code, module):
            assert company_code == 'company-1'
            return super().collect_module(company_code, module)

    app, factory, _, _, binding_id, task_id, import_id = seeded(tmp_path, IdentityCollector())
    with factory.begin() as db:
        db.get(EnterpriseBinding, binding_id).company_code = 'company-2'
    assert run_once(app)
    with factory() as db:
        assert db.get(Task, task_id).state == 'completed'
        assert db.get(EnterpriseImport, import_id).state == 'completed'


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
        assert db.scalar(select(func.count()).select_from(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_id)) == len(MODULES)
        row = db.scalar(select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_id))
        assert row.request_params == {"unit": "万元", "source": "xhr", "company_code":"company-1", "company_name":"测试公司"}
    assert collector.collected == [f"module-{index}" for index in range(len(MODULES))]


def test_source_disabled_modules_are_saved_but_not_counted_as_data_successes(tmp_path):
    class DisabledCollector(FakeCollector):
        def collect_module(self,company_code,module):
            result=super().collect_module(company_code,module)
            if module.key=='module-12':return replace(result,parsed={'rows':[],'metadata':{'unavailable':True}})
            return result
    app,factory,_,_,_,task_id,import_id=seeded(tmp_path,DisabledCollector())
    assert run_once(app)
    with factory() as db:
        record=db.get(EnterpriseImport,import_id);task=db.get(Task,task_id)
        assert record.module_status['module-12']['state']=='unavailable'
        assert record.state=='completed'
        assert record.quality_state=='passed_with_gaps'
        assert task.result['module_count']==len(MODULES)-1
        assert task.result['unavailable_modules']==['module-12']


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
        assert db.scalar(select(func.count()).select_from(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_id)) == len(MODULES)-1

    collector = FakeCollector({f"module-{index}" for index in range(len(MODULES))})
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


@pytest.mark.parametrize("code", ["authentication_required", "login_expired", "browser_unavailable", "profile_missing", "profile_in_use"])
def test_session_failure_stops_remaining_modules_and_preserves_successes(tmp_path, code):
    class InterruptedCollector(FakeCollector):
        def collect_module(self, company_code, module):
            if module.order >= 1:
                self.collected.append(module.key)
                raise EnterpriseWarningError(code)
            return super().collect_module(company_code, module)

    collector = InterruptedCollector()
    app, factory, _, _, _, _, import_id = seeded(tmp_path, collector)
    assert run_once(app)
    assert collector.collected == ["module-0", "module-1"]
    with factory() as db:
        record = db.get(EnterpriseImport, import_id)
        assert record.state == "partial"
        assert record.error == code
        assert record.module_status["module-0"]["state"] == "completed"
        assert record.module_status["module-20"] == {"state": "failed", "error": code}
        assert db.scalar(select(func.count()).select_from(EnterpriseFinancialData).where(
            EnterpriseFinancialData.import_id == import_id)) == 1


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
        assert db.scalar(select(func.count()).select_from(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_id)) == len(MODULES)
