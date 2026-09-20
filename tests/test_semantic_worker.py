from leasedd.worker import _semantic_item, durable_chapter_response, TaskError


def item(state, mapping="mapped", value="123"):
    return {"concept":"total_assets","source_name":"资产总计","normalized_value":value,
            "mapping_state":mapping,"verification_state":state,"evidence":{"table_id":"t1"}}


def test_verified_semantic_value_can_feed_formulas():
    result=_semantic_item(item("VERIFIED"))
    assert result["status"]=="source_verified"
    assert result["normalized_value"]=="123"
    assert result["evidence"]["verification_state"]=="VERIFIED"


def test_conflict_never_exposes_normalized_value_to_formulas():
    result=_semantic_item(item("CONFLICT"))
    assert result["status"]=="pending_confirmation"
    assert result["normalized_value"] is None
    assert result["evidence"]["original_normalized_value"]=="123"


def test_gap_and_unmapped_are_disclosed_without_becoming_known_concepts():
    assert _semantic_item(item("GAP",value=None))["status"]=="source_value_not_found"
    result=_semantic_item(item("UNMAPPED",mapping="unmapped"))
    assert result["concept"].startswith("disclosed_")
    assert result["evidence"]["disclosed_concept"]==result["concept"]


def test_core_evidence_state_is_used_and_distinct_unmapped_rows_stay_distinct():
    first=_semantic_item({"concept":"disclosed_aaa","source_name":"其他甲","normalized_value":"1","evidence":{"mapping_state":"unmapped","verification_state":"UNMAPPED"}})
    second=_semantic_item({"concept":"disclosed_bbb","source_name":"其他乙","normalized_value":"2","evidence":{"mapping_state":"unmapped","verification_state":"UNMAPPED"}})
    assert first["normalized_value"]=="1"
    assert first["concept"]!=second["concept"]


def test_runtime_chapter_uses_durable_stage_wrapper(monkeypatch):
    calls=[]
    def make(app,tid,lease,config,input_hash):
        calls.append((app,tid,lease,config,input_hash))
        return lambda stage,payload: calls.append((stage,payload)) or {"ok":True}
    monkeypatch.setattr('leasedd.extraction_stages.make_stage_call',make)
    app=object();config={"model":"m"};pack={"input_hash":"h"}
    assert durable_chapter_response(app,'task','lease',config,'hash',pack)=={"ok":True}
    assert calls==[(app,'task','lease',config,'hash'),('section:task',pack)]


def test_runtime_chapter_redacts_unknown_stage_errors(monkeypatch):
    from leasedd.extraction_stages import StageError
    monkeypatch.setattr('leasedd.extraction_stages.make_stage_call',lambda *args:lambda *args:(_ for _ in ()).throw(StageError('secret provider body!')))
    try:durable_chapter_response(object(),'task','lease',{},'hash',{})
    except TaskError as error:assert str(error)=='stage_call_failed'
    else:raise AssertionError('TaskError expected')
