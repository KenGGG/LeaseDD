import json
import pytest
from leasedd.extraction_benchmark import BenchmarkError, evaluate, validate_manifest, main


def manifest(files):
    return {"schema_version":"1","planned_categories":["annual_report","scanned_statement"],"files":files}


def file(doc, company, split, sha, origin="real"):
    return {"document_id":doc,"company_id":company,"split":split,"sha256":sha,"origin":origin,"category":"annual_report"}


def cell(**changes):
    row={"document_id":"d1","company_id":"c1","table_id":"t1","source_row":1,"source_column":2,
         "statement_type":"balance_sheet","scope":"consolidated","period":"2025-12-31",
         "currency":"CNY","unit_scale":"1","concept":"total_assets","source_name":"资产总计",
         "value":"100.00","verification_state":"VERIFIED"}
    row.update(changes);return row


def test_manifest_rejects_company_leakage_and_duplicate_document_content():
    with pytest.raises(BenchmarkError,match="company.*both"):
        validate_manifest(manifest([file("d1","same","dev","a"*64),file("d2","same","holdout","b"*64)]))
    with pytest.raises(BenchmarkError,match="sha256"):
        validate_manifest(manifest([file("d1","a","dev","c"*64),file("d2","b","holdout","c"*64)]))


def test_manifest_requires_truthful_origin_and_valid_split():
    with pytest.raises(BenchmarkError,match="origin"):
        validate_manifest(manifest([file("d1","c1","dev","a"*64,origin="unknown")]))
    with pytest.raises(BenchmarkError,match="split"):
        validate_manifest(manifest([file("d1","c1","test","a"*64)]))


def test_evaluator_anchors_cells_before_scoring_semantics_and_exposes_counts():
    expected=[cell(),cell(source_column=3,period="2024-12-31",value="90")]
    actual=[cell(period="2024-12-31"),cell(source_column=3,period="2024-12-31",value=None,verification_state="GAP")]
    result=evaluate(expected,actual)
    assert result["period_accuracy"] == {"numerator":1,"denominator":2,"value":0.5,"coverage_numerator":2,"coverage_denominator":2,"coverage":1.0}
    assert result["numeric_accuracy"]["numerator"] == 0
    assert result["numeric_accuracy"]["denominator"] == 2
    assert result["numeric_accuracy"]["coverage_numerator"] == 1
    assert result["false_verified_rate"] == {"numerator":1,"denominator":1,"value":1.0}


def test_evaluator_scores_discovery_concepts_and_unmatched_verified_as_false():
    expected=[cell(),cell(document_id="d2",table_id="t2",source_row=5,concept="net_profit",statement_type="income_statement")]
    actual=[cell(),cell(document_id="d9",table_id="hallucinated",source_row=1,value="7")]
    result=evaluate(expected,actual)
    assert result["main_table_discovery"]["numerator"] == 1
    assert result["main_table_discovery"]["denominator"] == 2
    assert result["core_concept_recall"]["numerator"] == 1
    assert result["core_concept_recall"]["denominator"] == 2
    assert result["false_verified_rate"] == {"numerator":1,"denominator":2,"value":0.5}


@pytest.mark.parametrize('field,wrong', [
    ('concept', 'total_liabilities'),
    ('statement_type', 'cash_flow_statement'),
    ('company_id', 'different_company'),
])
def test_verified_value_with_wrong_financial_meaning_is_false_verification(field, wrong):
    result = evaluate([cell()], [cell(**{field: wrong})])
    assert result['false_verified_rate'] == {'numerator': 1, 'denominator': 1, 'value': 1.0}
    # Numeric accuracy deliberately isolates values and their period/unit basis;
    # it is not the metric that certifies the complete financial meaning.
    assert result['numeric_accuracy']['numerator'] == 1


def test_equivalent_decimal_with_all_semantics_correct_is_not_false_verification():
    result = evaluate([cell()], [cell(value='100.000')])
    assert result['false_verified_rate'] == {'numerator': 0, 'denominator': 1, 'value': 0.0}


def test_evaluator_rejects_records_missing_normalized_fields():
    broken=cell();del broken["scope"]
    with pytest.raises(BenchmarkError,match="scope"):
        evaluate([broken],[])


def test_cli_evaluates_only_requested_manifest_split(tmp_path,capsys):
    m=manifest([file("d1","c1","dev","a"*64),file("d2","c2","holdout","b"*64)])
    expected=[cell(),cell(document_id="d2",company_id="c2")]
    actual=[cell(),cell(document_id="d2",company_id="c2")]
    paths=[]
    for name,payload in [("manifest.json",m),("expected.json",expected),("actual.json",actual)]:
        path=tmp_path/name;path.write_text(json.dumps(payload));paths.append(path)
    assert main(["evaluate",*[str(p) for p in paths],"--split","holdout"]) == 0
    output=json.loads(capsys.readouterr().out)
    assert output["split"]=="holdout" and output["expected_records"]==1
