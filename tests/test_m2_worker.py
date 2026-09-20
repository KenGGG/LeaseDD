import hashlib

from leasedd.agnes_finance import extract_financial_data
from leasedd.db import DocumentConversion, ExtractionRun, FinancialItem, FinancialStatement, Task
from leasedd.worker import run_once
from test_platform import env


def test_explicit_half_year_tables_persist_all_periods_without_agnes_configuration(env):
    from test_statement_tables import report
    app,c,project,_=env
    d=c.post(f'/api/projects/{project}/documents',files={'file':('half-year.md',report().encode(),'text/markdown')}).json()
    c.post(f'/api/projects/{project}/documents/recognize',json={'document_ids':[d['id']],'model_allowed':False})
    assert run_once(app)
    task=c.get(f'/api/projects/{project}/tasks').json()[0]
    assert task['state']=='completed',task
    assert task['result']['item_count']==38
    assert task['result']['coverage']['status']=='complete'
    assert task['result']['coverage']['tables_parsed']==6
    statements=c.get(f'/api/projects/{project}/financial-statements').json()
    assert len(statements)==12
    cash=next(i for s in statements for i in s['items'] if i['concept']=='cash')
    assert cash['source_cells']==['货币资金','100.01','80']
    assert cash['source_headers']==['项目','期末余额','期初余额']
    assert cash['source_order']>0
    assert cash['source_section']=='资产负债表'
    assert c.post(f"/api/projects/{project}/financial-items/{cash['id']}/confirm",json={'decision':'confirm','reason':'人工核对原件'}).status_code==200
    refreshed=c.get(f'/api/projects/{project}/financial-statements').json()
    assert next(i for s in refreshed for i in s['items'] if i['id']==cash['id'])['status']=='human_confirmed'
    # Presentation metadata is derived read-only; no replacement rows are inserted.
    with app.state.db() as db:
        assert db.query(FinancialItem).count()==38


def test_two_stage_extraction_never_sends_full_long_document():
    lines = [f"普通说明 {i} " + "A" * 90 for i in range(1, 500)]
    lines[249:255] = [
        "# 合并资产负债表", "编制单位：脱敏公司", "2025年12月31日", "单位：万元",
        "| 项目 | 期末余额 |", "| 货币资金 | 1,234.50 |",
    ]
    markdown = "\n".join(lines)
    calls = []

    def model(stage, payload):
        calls.append((stage, payload))
        if stage == "locate":
            if "合并资产负债表" in payload["markdown"]:
                return {"statements": [{
                    "statement_type": "balance_sheet", "entity": "脱敏公司",
                    "scope": "consolidated", "period": "2025-12-31", "raw_unit": "万元",
                    "start_line": 250, "end_line": 255,
                }]}
            return {"statements": []}
        return {
            "statement_type": "balance_sheet", "entity": "脱敏公司", "scope": "consolidated",
            "period": "2025-12-31", "currency": "CNY", "raw_unit": "万元",
            "items": [{"concept": "cash", "source_name": "货币资金", "raw_value": "1,234.50", "source_text": "| 货币资金 | 1,234.50 |"}],
        }

    results = extract_financial_data(markdown, model, chunk_chars=4000, max_statement_chars=8000)
    assert len(results) == 1
    assert results[0]["items"][0]["status"] == "source_verified"
    assert results[0]["items"][0]["source_start_line"] == 255
    locate_payloads = [payload for stage, payload in calls if stage == "locate"]
    extract_payloads = [payload for stage, payload in calls if stage == "extract"]
    assert len(locate_payloads) > 5
    assert all(len(payload["markdown"]) <= 4000 for payload in locate_payloads)
    assert len(extract_payloads) == 1
    assert len(extract_payloads[0]["markdown"]) < len(markdown) / 5


def test_invalid_location_range_is_rejected_before_extraction():
    stages = []
    def model(stage, payload):
        stages.append(stage)
        return {"statements": [{
            "statement_type":"balance_sheet", "entity":"X", "scope":"consolidated",
            "period":"2025-12-31", "raw_unit":"元", "start_line":1, "end_line":99999,
        }]}
    assert extract_financial_data("资产负债表\n货币资金 1", model, chunk_chars=1000, max_statement_chars=2000) == []
    assert stages == ["locate"]


def test_invented_model_value_is_retained_only_as_rejected_candidate():
    markdown = "# 利润表\n2025年度 单位：元\n净利润 88"
    def model(stage, payload):
        if stage == "locate":
            return {"statements":[{"statement_type":"income_statement","entity":"X","scope":"parent","period":"2025年度","raw_unit":"元","start_line":1,"end_line":3}]}
        return {"statement_type":"income_statement","entity":"X","scope":"parent","period":"2025年度","currency":"CNY","raw_unit":"元","items":[{"concept":"net_profit","source_name":"净利润","raw_value":"99","source_text":"净利润 99"}]}
    item = extract_financial_data(markdown, model)[0]["items"][0]
    assert item["status"] == "source_value_not_found"
    assert item["normalized_value"] is None


def test_upload_task_converts_extracts_and_persists_candidates(env):
    from test_financial_semantics import MD
    from test_semantic_pipeline import model_fixture
    app, c, project, _ = env
    markdown = MD
    response = c.post(
        f"/api/projects/{project}/documents",
        files={"file": ("statement.md", markdown.encode(), "text/markdown")},
        data={"model_allowed":"true"},
    )
    assert response.status_code == 200
    document_id = response.json()["id"]
    queued = c.post(f"/api/projects/{project}/documents/recognize", json={"document_ids":[document_id],"model_allowed":True})
    assert queued.status_code == 200

    model,calls=model_fixture()
    app.state.finance_model_call = model
    assert run_once(app)
    tasks = c.get(f"/api/projects/{project}/tasks").json()
    task = next(task for task in tasks if task["kind"] == "extract_finance")
    assert task["state"] == "completed", task
    assert [stage.split(':')[0] for stage,_ in calls]==['map','interpret','extract']
    assert task["result"]["statement_count"] == 2
    assert task["result"]["pipeline_version"] == "agnes-semantic-v1"
    statements = c.get(f"/api/projects/{project}/financial-statements").json()
    assert any(item["normalized_value"] == "1255000.00" for statement in statements for item in statement["items"])
    with app.state.db.begin() as db:
        conversion = db.query(DocumentConversion).one()
        assert conversion.original_sha256 == hashlib.sha256(markdown.encode()).hexdigest()
        assert conversion.markdown_sha256
        assert db.query(ExtractionRun).one().state == "completed"
        assert db.query(FinancialStatement).count() == 2
        assert db.query(FinancialItem).count() == 10
        run=db.query(ExtractionRun).one();original_task=db.get(Task,run.task_id)
        run.state='processing';original_task.state='queued';original_task.lease_until=0
        run_id=run.id
    before=len(calls)
    app.state.finance_model_call=lambda *args: (_ for _ in ()).throw(AssertionError('persisted run must avoid model calls'))
    assert run_once(app)
    assert len(calls)==before
    with app.state.db.begin() as db:
        run=db.get(ExtractionRun,run_id);original_task=db.get(Task,run.task_id);conversion=db.get(DocumentConversion,run.conversion_id)
        assert run.state=='completed' and original_task.state=='completed'
        empty_task=Task(project_id=project,kind='extract_finance',mode='auto',state='completed',input_revision=original_task.input_revision,input_hash=original_task.input_hash,result={'document_id':document_id},created_by=original_task.created_by,created_at=original_task.created_at+1)
        db.add(empty_task);db.flush()
        db.add(ExtractionRun(task_id=empty_task.id,conversion_id=conversion.id,project_id=project,document_id=document_id,pipeline_version='agnes-semantic-v1',state='completed',manifest={'quality_state':'failed'},created_at=run.created_at+1))
    # A newer empty run remains inspectable but does not hide the last usable data.
    assert len(c.get(f"/api/projects/{project}/financial-statements").json())==2
    assert len(c.get(f"/api/projects/{project}/financial-statements?run_id={run_id}").json())==2
    assert len(c.get(f"/api/projects/{project}/financial-extractions").json())==2


def test_unlicensed_document_is_converted_but_not_sent_to_model(env):
    app, c, project, _ = env
    response = c.post(
        f"/api/projects/{project}/documents",
        files={"file": ("statement.md", b"# balance sheet\ncash 1", "text/markdown")},
        data={"model_allowed":"false"},
    )
    assert response.status_code == 200
    document_id = response.json()["id"]
    queued = c.post(f"/api/projects/{project}/documents/recognize", json={"document_ids":[document_id],"model_allowed":False})
    assert queued.status_code == 200
    called = []
    app.state.finance_model_call = lambda stage, payload: called.append(stage) or {"statements":[]}
    assert run_once(app)
    task = next(task for task in c.get(f"/api/projects/{project}/tasks").json() if task["kind"] == "extract_finance")
    assert task["state"] == "completed"
    assert task["result"]["extraction_status"] == "conversion_only"
    assert called == []
    with app.state.db() as db:
        assert db.query(DocumentConversion).one().state == "completed"


def test_local_tables_do_not_require_external_model_authorization(env):
    from test_statement_tables import report
    app,c,project,_=env
    app.state.finance_model_call=lambda *args: (_ for _ in ()).throw(AssertionError('No external call authorized'))
    d=c.post(f'/api/projects/{project}/documents',files={'file':('local.md',report().encode(),'text/markdown')}).json()
    c.post(f'/api/projects/{project}/documents/recognize',json={'document_ids':[d['id']],'model_allowed':False})
    assert run_once(app)
    task=c.get(f'/api/projects/{project}/tasks').json()[0]
    assert task['state']=='completed'
    assert task['result']['item_count']==38
    assert c.get(f'/api/projects/{project}/documents').json()[0]['model_allowed'] is False
