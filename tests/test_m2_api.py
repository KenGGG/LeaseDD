import hashlib
import time

from leasedd.db import DocumentConversion, FinancialItem, FinancialStatement, Task
from test_platform import env


def upload(c, project, name="report.pdf", content=b"%PDF-test"):
    response = c.post(
        f"/api/projects/{project}/documents",
        files={"file": (name, content, "application/octet-stream")},
        data={"model_allowed": "true"},
    )
    assert response.status_code == 200
    return response.json()


def seed_finance(app, project, document, creator):
    root = app.state.root
    markdown = "# 合并资产负债表\n单位：万元\n| 货币资金 | 100 |"
    path = root / project / "markdown" / f"{document['id']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown)
    with app.state.db.begin() as db:
        conversion = DocumentConversion(
            project_id=project, document_id=document["id"], original_sha256=document["sha256"],
            tool="mineru", tool_version="3.4.4", state="completed", markdown_path=str(path.relative_to(root)),
            markdown_sha256=hashlib.sha256(markdown.encode()).hexdigest(), error=None,
            created_at=time.time(), completed_at=time.time(),
        )
        db.add(conversion); db.flush()
        statement = FinancialStatement(
            project_id=project, document_id=document["id"], conversion_id=conversion.id,
            statement_type="balance_sheet", entity="脱敏公司", scope="consolidated",
            period="2025-12-31", period_normalized="2025-12-31", period_kind="instant",
            currency="CNY", raw_unit="万元", unit_scale="10000", source_start_line=1,
            source_end_line=3, state="extracted", issues=[], created_at=time.time(),
        )
        db.add(statement); db.flush()
        item = FinancialItem(
            statement_id=statement.id, concept="cash", source_name="货币资金", raw_value="100",
            raw_unit="万元", normalized_value="1000000", source_text="| 货币资金 | 100 |",
            source_start_line=3, source_end_line=3, status="source_verified",
            confirmed_by=None, confirmed_at=None, confirmation_reason=None,
        )
        db.add(item); db.flush()
        return conversion.id, statement.id, item.id


def test_upload_waits_for_explicit_batch_recognition(env):
    app, c, project, _ = env
    first = upload(c, project, "one.pdf")
    second = upload(c, project, "two.pdf")
    assert first["model_allowed"] is False
    tasks = c.get(f"/api/projects/{project}/tasks").json()
    assert [task for task in tasks if task["kind"] == "extract_finance"] == []
    status = c.get(f"/api/projects/{project}/documents/{first['id']}/conversion")
    assert status.status_code == 200
    assert status.json()["state"] == "not_started"

    response = c.post(f"/api/projects/{project}/documents/recognize", json={
        "document_ids": [first["id"], second["id"]], "model_allowed": True,
    })
    assert response.status_code == 200
    assert response.json()["queued"] == 2
    tasks = c.get(f"/api/projects/{project}/tasks").json()
    extraction = [task for task in tasks if task["kind"] == "extract_finance"]
    assert len(extraction) == 2
    assert all(task["result"]["model_allowed"] is True for task in extraction)

    repeated = c.post(f"/api/projects/{project}/documents/recognize", json={
        "document_ids": [first["id"], second["id"]], "model_allowed": True,
    })
    assert repeated.status_code == 200
    assert repeated.json() == {"queued": 0, "skipped": 2, "task_ids": []}


def test_member_can_view_markdown_and_finance_source(env):
    app, c, project, _ = env
    document = upload(c, project)
    conversion_id, statement_id, item_id = seed_finance(app, project, document, "writer")
    response = c.get(f"/api/projects/{project}/documents/{document['id']}/markdown")
    assert response.status_code == 200
    assert response.json()["conversion_id"] == conversion_id
    assert "货币资金" in response.json()["markdown"]
    statements = c.get(f"/api/projects/{project}/financial-statements").json()
    assert statements[0]["id"] == statement_id
    assert statements[0]["items"][0]["id"] == item_id
    source = c.get(f"/api/projects/{project}/financial-items/{item_id}/source")
    assert source.status_code == 200
    assert source.json()["lines"] == ["| 货币资金 | 100 |"]


def test_outsider_cannot_guess_markdown_statement_or_item_ids(env):
    app, c, project, login = env
    document = upload(c, project)
    _, statement_id, item_id = seed_finance(app, project, document, "writer")
    login("outsider", "long-password-123")
    assert c.get(f"/api/projects/{project}/documents/{document['id']}/markdown").status_code == 403
    assert c.get(f"/api/projects/{project}/financial-statements").status_code == 403
    assert c.get(f"/api/projects/{project}/financial-items/{item_id}/source").status_code == 403
    assert c.post(f"/api/projects/{project}/financial-items/{item_id}/confirm", json={"decision":"confirm","reason":"核对"}).status_code == 403


def test_writer_can_confirm_or_reject_and_reviewer_is_read_only(env):
    app, c, project, login = env
    document = upload(c, project)
    _, _, item_id = seed_finance(app, project, document, "writer")
    response = c.post(
        f"/api/projects/{project}/financial-items/{item_id}/confirm",
        json={"decision": "confirm", "reason": "已对照 Markdown 和原件"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "human_confirmed"
    login("reviewer", "long-password-123")
    assert c.post(
        f"/api/projects/{project}/financial-items/{item_id}/confirm",
        json={"decision": "reject", "reason": "表格错位"},
    ).status_code == 403


def test_cannot_confirm_value_not_found_without_replacing_extraction(env):
    app, c, project, _ = env
    document = upload(c, project)
    _, _, item_id = seed_finance(app, project, document, "writer")
    with app.state.db.begin() as db:
        db.get(FinancialItem, item_id).status = "source_value_not_found"
    response = c.post(
        f"/api/projects/{project}/financial-items/{item_id}/confirm",
        json={"decision": "confirm", "reason": "直接确认"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "source_value_not_found"
