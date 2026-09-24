"""The four-company acceptance command must not turn verification into collection."""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from leasedd.db import (
    Base, EnterpriseBinding, EnterpriseFinancialData, EnterpriseImport,
    Project, Task, User, database,
)
from enterprise_live_acceptance import acceptance_result, verify_company, main


def seeded(tmp_path):
    engine, factory = database(f"sqlite:///{tmp_path}/acceptance.db")
    Base.metadata.create_all(engine)
    with factory.begin() as db:
        user = User(username="writer", password_hash="x", admin=False)
        project = Project(name="德方纳米")
        db.add_all([user, project]); db.flush()
        binding = EnterpriseBinding(project_id=project.id, company_code="company-1",
                                    company_name="深圳市德方纳米科技股份有限公司",
                                    identity={"type": "company"}, created_by=user.id, created_at=1)
        task = Task(project_id=project.id, kind="enterprise_import", mode="qyyjt", state="completed",
                    input_revision=1, input_hash="a" * 64, attempts=1, lease_until=0,
                    lease_token="", result={"company_code": "company-1"},
                    created_by=user.id, created_at=1)
        db.add_all([binding, task]); db.flush()
        record = EnterpriseImport(project_id=project.id, task_id=task.id, state="completed",
                                  quality_state="passed_with_gaps", module_status={
                                      "audit_report": {"state": "completed"},
                                      "long_term_receivables": {"state": "unavailable"},
                                  }, content_sha256="b" * 64, started_at=2, completed_at=3)
        db.add(record); db.flush()
        for key, state in [("audit_report", "completed"), ("long_term_receivables", "unavailable")]:
            db.add(EnterpriseFinancialData(import_id=record.id, category="notes", module_key=key,
                                           module_name=key, module_order=0, endpoint_path="/source",
                                           request_params={"company_code": "company-1"}, raw_payload={},
                                           parsed_payload=({"head": [["项目名称", "审计意见"], ["项目名称", "审计意见"]],
                                                            "rows": [[["2025年年报", "标准无保留"]], [["2024年年报", "标准无保留"]]],
                                                            "metadata": {"report": ["20251231", "20241231"]}}
                                                           if state == "completed" else {"metadata": {"unavailable": True}}),
                                           response_sha256="c" * 64, state=state, collected_at=2))
        return factory, user.id, project.id, binding.id, record.id


def test_acceptance_separates_disclosed_data_from_source_disabled_modules(tmp_path):
    factory, _, project_id, binding_id, record_id = seeded(tmp_path)
    with factory() as db:
        result = acceptance_result(db, db.get(Project, project_id), db.get(EnterpriseBinding, binding_id),
                                   db.get(EnterpriseImport, record_id), 1.0)
    assert result["module_coverage"] == {"completed": 1, "unavailable": 1, "failed": 0,
                                          "missing": 38, "expected": 40}
    assert result["import_state"] == "completed"
    assert result["record_group_counts"] == {"audit_report": 2}
    assert "audit_report" not in result["period_counts"]


def test_existing_current_batch_is_verified_without_reimporting(tmp_path):
    factory, user_id, project_id, _, record_id = seeded(tmp_path)

    class ForbiddenCollector:
        def search(self, name):
            raise AssertionError("verification must not search provider")

        def enumerate_modules(self, code):
            raise AssertionError("verification must not collect provider")

    app = SimpleNamespace(state=SimpleNamespace(db=factory, enterprise_collector=ForbiddenCollector()))
    with factory() as db:
        user = db.get(User, user_id)
    result = verify_company(app, "德方纳米")
    assert result["module_coverage"]["unavailable"] == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id)) == 1
        assert db.scalar(select(func.count()).select_from(EnterpriseImport).where(EnterpriseImport.project_id == project_id)) == 1
        assert db.get(EnterpriseImport, record_id).state == "completed"


def test_acceptance_elapsed_uses_latest_retry_task_not_reused_batch_start(tmp_path):
    factory, _, _, _, record_id = seeded(tmp_path)
    with factory.begin() as db:
        record = db.get(EnterpriseImport, record_id)
        record.started_at = 10
        record.completed_at = 45
        db.get(Task, record.task_id).created_at = 30
    app = SimpleNamespace(state=SimpleNamespace(db=factory))
    result = verify_company(app, "德方纳米")
    assert result["enterprise_elapsed_seconds"] == 15


def test_flat_note_date_rows_count_as_report_groups(tmp_path):
    factory, _, project_id, binding_id, record_id = seeded(tmp_path)
    with factory.begin() as db:
        audit = db.scalar(select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == record_id,
                                                                 EnterpriseFinancialData.module_key == "audit_report"))
        audit.parsed_payload = {"head": ["报告期", "审计意见"],
                                "rows": [["20251231", "标准无保留"], ["20241231", "标准无保留"]],
                                "metadata": {}}
    with factory() as db:
        result = acceptance_result(db, db.get(Project, project_id), db.get(EnterpriseBinding, binding_id),
                                   db.get(EnterpriseImport, record_id), 1.0)
    assert result["record_group_counts"] == {"audit_report": 2}


def test_verifier_rejects_a_batch_from_a_previous_company_binding(tmp_path):
    factory, user_id, _, _, record_id = seeded(tmp_path)
    with factory.begin() as db:
        task = db.get(Task, db.get(EnterpriseImport, record_id).task_id)
        task.result = {"company_code": "previous-company"}
    app = SimpleNamespace(state=SimpleNamespace(db=factory, enterprise_collector=None))
    with factory() as db:
        user = db.get(User, user_id)
    with pytest.raises(RuntimeError, match="source_company_mismatch"):
        verify_company(app, "德方纳米")


def test_default_cli_never_uses_mingpu_as_a_membership_source(tmp_path, monkeypatch):
    factory, _, project_id, _, _ = seeded(tmp_path)
    monkeypatch.setenv("LEASEDD_DATABASE_URL", f"sqlite:///{tmp_path}/acceptance.db")
    monkeypatch.setenv("LEASEDD_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["enterprise_live_acceptance.py", "--companies", "德方纳米",
                                   "金银河", "气派科技", "昊志机电", "--output", str(tmp_path / "result.json")])
    with pytest.raises(RuntimeError, match="current_enterprise_import_missing:金银河"):
        main()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id)) == 1


def test_acceptance_cli_rejects_refresh_flag_before_database_mutation(tmp_path, monkeypatch):
    factory, _, project_id, _, _ = seeded(tmp_path)
    monkeypatch.setenv("LEASEDD_DATABASE_URL", f"sqlite:///{tmp_path}/acceptance.db")
    monkeypatch.setenv("LEASEDD_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["enterprise_live_acceptance.py", "--companies", "德方纳米",
                                   "金银河", "气派科技", "昊志机电", "--output", str(tmp_path / "result.json"),
                                   "--refresh-all"])
    with pytest.raises(SystemExit) as rejected:
        main()
    assert rejected.value.code == 2
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id)) == 1
