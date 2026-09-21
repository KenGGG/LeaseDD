import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from leasedd.contracts import EnterpriseImportRequest
from leasedd.db import (
    Base,
    EnterpriseBinding,
    EnterpriseFinancialData,
    EnterpriseImport,
    Project,
    Task,
    User,
    database,
)


@pytest.fixture
def session():
    engine, factory = database("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with factory() as db:
        yield db
    engine.dispose()


def seed(db):
    user = User(username="admin", password_hash="hash", admin=True)
    project = Project(name="测试项目")
    db.add_all([user, project])
    db.flush()
    task = Task(
        project_id=project.id,
        kind="enterprise_import",
        mode="qyyjt",
        input_revision=project.revision,
        input_hash="0" * 64,
        created_by=user.id,
        created_at=1.0,
    )
    db.add(task)
    db.flush()
    return user, project, task


def test_enterprise_models_round_trip_module_payload_without_changing_null(session):
    user, project, task = seed(session)
    binding = EnterpriseBinding(
        project_id=project.id,
        company_code="company-1",
        company_name="测试公司",
        identity={"symbol": "000001"},
        created_by=user.id,
        created_at=1.0,
    )
    import_record = EnterpriseImport(
        project_id=project.id,
        task_id=task.id,
        state="queued",
        quality_state="not_checked",
        module_status={},
        started_at=None,
        completed_at=None,
    )
    session.add_all([binding, import_record])
    session.flush()
    module = EnterpriseFinancialData(
        import_id=import_record.id,
        category="financial_notes",
        module_key="cash",
        module_name="货币资金",
        module_order=1,
        endpoint_path="/finance/getCompanyF9Data",
        request_params={"child_type": "cash"},
        raw_payload={"data": {"value": [["100", None]]}},
        parsed_payload={"values": [["100", None]]},
        response_sha256="1" * 64,
        state="completed",
        collected_at=2.0,
    )
    session.add(module)
    session.commit()

    assert session.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id == project.id)).company_name == "测试公司"
    stored = session.scalar(select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id == import_record.id))
    assert stored.raw_payload["data"]["value"][0] == ["100", None]
    assert stored.parsed_payload["values"][0] == ["100", None]


@pytest.mark.parametrize("duplicate", ["binding", "task", "module"])
def test_enterprise_models_enforce_required_unique_keys(session, duplicate):
    user, project, task = seed(session)
    binding = EnterpriseBinding(project_id=project.id, company_code="one", company_name="一", identity={}, created_by=user.id, created_at=1.0)
    import_record = EnterpriseImport(project_id=project.id, task_id=task.id, state="queued", quality_state="not_checked", module_status={})
    session.add_all([binding, import_record])
    session.flush()
    module = EnterpriseFinancialData(import_id=import_record.id, category="statements", module_key="balance", module_name="资产负债表", module_order=1, endpoint_path="/report/getThreeReports", request_params={}, raw_payload={}, parsed_payload={}, response_sha256="2" * 64, state="completed", collected_at=1.0)
    session.add(module)
    session.commit()

    if duplicate == "binding":
        session.add(EnterpriseBinding(project_id=project.id, company_code="two", company_name="二", identity={}, created_by=user.id, created_at=2.0))
    elif duplicate == "task":
        session.add(EnterpriseImport(project_id=project.id, task_id=task.id, state="queued", quality_state="not_checked", module_status={}))
    else:
        session.add(EnterpriseFinancialData(import_id=import_record.id, category="statements", module_key="balance", module_name="资产负债表", module_order=2, endpoint_path="/report/getThreeReports", request_params={}, raw_payload={}, parsed_payload={}, response_sha256="3" * 64, state="completed", collected_at=2.0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_enterprise_import_request_requires_name_for_selected_code():
    assert EnterpriseImportRequest(query="测试").query == "测试"
    assert EnterpriseImportRequest(company_code="code", company_name="测试公司").company_name == "测试公司"
    with pytest.raises(ValidationError):
        EnterpriseImportRequest(company_code="code")
