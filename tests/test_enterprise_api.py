import time

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from leasedd.app import create_app
from leasedd.contracts import EnterpriseImportRequest
from leasedd.db import Audit, Document, DocumentConversion, EnterpriseBinding, EnterpriseFinancialData, EnterpriseImport, FinancialStatement, Member, Project, Task, User
from leasedd.enterprise_warning import EnterpriseCandidate


class SearchCollector:
    def search(self, name):
        return [EnterpriseCandidate("a", "甲公司", {"symbol": "000001"}), EnterpriseCandidate("b", "甲科技", {})]


def endpoint(app, path, method):
    matches = [route.endpoint for route in app.routes if getattr(route, "path", None) == path and method in getattr(route, "methods", ())]
    assert len(matches) == 1
    return matches[0]


@pytest.fixture
def api(tmp_path):
    app = create_app(f"sqlite:///{tmp_path}/api.db", tmp_path / "files", secure_cookie=False)
    app.state.enterprise_collector = SearchCollector()
    with app.state.db.begin() as db:
        admin = User(username="admin", password_hash="x", admin=True)
        writer = User(username="writer", password_hash="x", admin=False)
        outsider = User(username="outsider", password_hash="x", admin=False)
        project = Project(name="甲公司")
        db.add_all([admin, writer, outsider, project]); db.flush()
        db.add_all([Member(project_id=project.id, user_id=admin.id, role="writer"), Member(project_id=project.id, user_id=writer.id, role="writer")])
        ids = project.id, admin.id, writer.id, outsider.id
    yield app, ids
    app.state.engine.dispose()


def test_exactly_four_routes_and_manual_search_then_binding(api):
    app, (pid, admin_id, _, _) = api
    paths = sorted(route.path for route in app.routes if "/enterprise" in getattr(route, "path", ""))
    assert paths == sorted([
        "/api/projects/{pid}/enterprise", "/api/projects/{pid}/enterprise/import",
        "/api/projects/{pid}/enterprise/retry", "/api/projects/{pid}/enterprise/data",
    ])
    import_route = endpoint(app, "/api/projects/{pid}/enterprise/import", "POST")
    with app.state.db() as db:
        admin = db.get(User, admin_id)
        result = import_route(pid, EnterpriseImportRequest(query="甲"), user=admin, db=db)
        assert [item["name"] for item in result["candidates"]] == ["甲公司", "甲科技"]
        assert db.scalar(select(func.count()).select_from(EnterpriseBinding)) == 0
        assert db.scalar(select(func.count()).select_from(Audit)) == 0
    with app.state.db() as db:
        result = import_route(pid, EnterpriseImportRequest(company_code="a", company_name="甲公司"), user=db.get(User, admin_id), db=db)
        assert result["kind"] == "enterprise_import" and result["state"] == "queued"
        assert db.scalar(select(func.count()).select_from(EnterpriseBinding)) == 1
        assert db.scalar(select(func.count()).select_from(Task)) == 1
        assert {event.action for event in db.scalars(select(Audit))} == {"bind_enterprise", "enqueue_enterprise_import"}
        duplicate = import_route(pid, EnterpriseImportRequest(company_code="a", company_name="甲公司"), user=db.get(User, admin_id), db=db)
        assert duplicate["id"] == result["id"]


def test_permissions_status_data_and_retry_audit(api):
    app, (pid, admin_id, writer_id, outsider_id) = api
    import_route = endpoint(app, "/api/projects/{pid}/enterprise/import", "POST")
    status_route = endpoint(app, "/api/projects/{pid}/enterprise", "GET")
    data_route = endpoint(app, "/api/projects/{pid}/enterprise/data", "GET")
    retry_route = endpoint(app, "/api/projects/{pid}/enterprise/retry", "POST")
    with app.state.db() as db:
        with pytest.raises(HTTPException) as denied:
            import_route(pid, EnterpriseImportRequest(query="甲"), user=db.get(User, writer_id), db=db)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as denied:
            status_route(pid, user=db.get(User, outsider_id), db=db)
        assert denied.value.status_code == 403
        assert status_route(pid, user=db.get(User, writer_id), db=db)["binding"] is None
        assert data_route(pid, category=None, module_key=None, user=db.get(User, writer_id), db=db)["modules"] == []
        import_route(pid, EnterpriseImportRequest(company_code="a", company_name="甲公司"), user=db.get(User, admin_id), db=db)
    with app.state.db.begin() as db:
        task = db.scalar(select(Task).where(Task.project_id == pid)); task.state = "completed"
        task.result = {**task.result, "failed_modules": ["module-5"]}
    with app.state.db() as db:
        retry = retry_route(pid, user=db.get(User, admin_id), db=db)
        assert retry["kind"] == "enterprise_import"
        assert "retry_enterprise_import" in {event.action for event in db.scalars(select(Audit))}


def test_readable_enterprise_import_replaces_pdf_statement_view(api):
    app, (pid, admin_id, _, _) = api
    import_route = endpoint(app, "/api/projects/{pid}/enterprise/import", "POST")
    statement_route = endpoint(app, "/api/projects/{pid}/financial-statements", "GET")
    with app.state.db() as db:
        import_route(pid, EnterpriseImportRequest(company_code="a", company_name="甲公司"), user=db.get(User, admin_id), db=db)
    with app.state.db.begin() as db:
        task = db.scalar(select(Task).where(Task.project_id == pid))
        record = db.scalar(select(EnterpriseImport).where(EnterpriseImport.project_id == pid))
        record.state = "completed"; record.completed_at = time.time()
        db.add(EnterpriseFinancialData(import_id=record.id, category="statements", module_key="balance", module_name="资产负债表", module_order=0,
            endpoint_path="/getThreeReports", request_params={"statement_type":"balance_sheet","unit":"元"}, raw_payload={"data":{}},
            parsed_payload={"periods":["2025-12-31"],"rows":[{"name":"资产总计","key":"assets","values":["100"]}]},
            response_sha256="a"*64, state="completed", error=None, collected_at=time.time()))
        document = Document(project_id=pid,name="old.pdf",sha256="b"*64,path="old.pdf",model_allowed=False,parse_state="text_available",created_by=admin_id)
        db.add(document); db.flush()
        conversion = DocumentConversion(project_id=pid,document_id=document.id,original_sha256=document.sha256,tool="mineru",tool_version="1",state="completed",markdown_path="old.md",markdown_sha256="c"*64,error=None,created_at=time.time(),completed_at=time.time())
        db.add(conversion); db.flush()
        db.add(FinancialStatement(project_id=pid,document_id=document.id,conversion_id=conversion.id,run_id=None,statement_type="income_statement",entity="旧PDF",scope="consolidated",period="2024",period_normalized="2024",period_kind="year",currency="CNY",raw_unit="元",unit_scale="1",source_start_line=1,source_end_line=2,state="extracted",issues=[],created_at=time.time()))
    with app.state.db() as db:
        views = statement_route(pid, run_id="", user=db.get(User, admin_id), db=db)
        assert len(views) == 1
        assert views[0]["source_type"] == "enterprise_warning"
        assert views[0]["statement_type"] == "balance_sheet"
