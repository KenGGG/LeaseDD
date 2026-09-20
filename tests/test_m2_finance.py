from decimal import Decimal

import pytest

from leasedd.finance_extract import (
    chunk_markdown,
    normalize_period,
    normalize_source_number,
    validate_extracted_statement,
)


def statement(**overrides):
    payload = {
        "statement_type": "balance_sheet",
        "entity": "脱敏测试有限公司",
        "scope": "consolidated",
        "period": "2025-12-31",
        "currency": "CNY",
        "raw_unit": "万元",
        "items": [
            {
                "concept": "accounts_receivable",
                "source_name": "应收账款",
                "raw_value": "728,315.22",
                "source_text": "| 应收账款 | 728,315.22 |",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_markdown_chunks_never_exceed_budget_and_keep_line_ranges():
    text = "\n".join(f"第{i}行 " + "数据" * 20 for i in range(1, 101))
    chunks = chunk_markdown(text, max_chars=420, overlap_lines=2)
    assert len(chunks) > 5
    assert all(len(chunk.text) <= 420 for chunk in chunks)
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 100
    assert chunks[1].start_line <= chunks[0].end_line


def test_single_long_line_is_split_without_breaking_budget():
    chunks = chunk_markdown("A" * 1000, max_chars=128, overlap_lines=0)
    assert len(chunks) == 8
    assert all(len(chunk.text) <= 128 for chunk in chunks)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("728,315,221.36", Decimal("728315221.36")),
        ("（1,234.50）", Decimal("-1234.50")),
        ("- 8 000", Decimal("-8000")),
        ("12，345", Decimal("12345")),
    ],
)
def test_source_number_normalization(value, expected):
    assert normalize_source_number(value) == expected


def test_period_keeps_half_year_and_second_quarter_distinct():
    assert normalize_period("2026H1") == ("2026-01-01/2026-06-30", "half_year")
    assert normalize_period("2026Q2") == ("2026-04-01/2026-06-30", "quarter")
    assert normalize_period("2026年1-6月") == ("2026-01-01/2026-06-30", "half_year")
    assert normalize_period("2026-06-30") == ("2026-06-30", "instant")


def test_verified_raw_value_is_found_and_scaled_without_guessing():
    source = "# 合并资产负债表\n单位：万元\n| 项目 | 期末余额 |\n| 应收账款 | 728,315.22 |"
    result = validate_extracted_statement(statement(), source)
    item = result["items"][0]
    assert item["status"] == "source_verified"
    assert item["normalized_value"] == "7283152200"
    assert result["unit_scale"] == "10000"


def test_parentheses_negative_must_exist_in_source():
    payload = statement(items=[{
        "concept": "net_profit",
        "source_name": "净利润",
        "raw_value": "(1,234.50)",
        "source_text": "净利润 （1,234.50）",
    }], statement_type="income_statement", period="2025年度", raw_unit="元")
    result = validate_extracted_statement(payload, "利润表\n净利润 （1,234.50）")
    assert result["items"][0]["normalized_value"] == "-1234.5"
    assert result["items"][0]["status"] == "source_verified"


def test_invented_number_cannot_enter_verified_data():
    result = validate_extracted_statement(statement(), "应收账款 728,315.21")
    assert result["items"][0]["status"] == "source_value_not_found"
    assert result["items"][0]["normalized_value"] is None


def test_program_recovers_exact_markdown_line_when_model_source_text_is_paraphrased():
    source = '<table><tr><td>应收账款</td><td>728,315.22</td></tr></table>'
    payload = statement(items=[{
        "concept": "accounts_receivable", "source_name": "应收账款",
        "raw_value": "728,315.22", "source_text": "应收账款 728,315.22",
    }])
    item = validate_extracted_statement(payload, source)["items"][0]
    assert item["status"] == "source_verified"
    assert item["source_text"] == source


@pytest.mark.parametrize("field,value", [("scope", "unknown"), ("raw_unit", "未知"), ("period", "待确认")])
def test_uncertain_metadata_requires_human_confirmation(field, value):
    result = validate_extracted_statement(statement(**{field: value}), "| 应收账款 | 728,315.22 |")
    assert result["items"][0]["status"] == "pending_confirmation"


def test_duplicate_concept_values_are_conflicts_not_silently_selected():
    items = [
        {"concept": "cash", "source_name": "货币资金", "raw_value": "100", "source_text": "货币资金 100"},
        {"concept": "cash", "source_name": "货币资金", "raw_value": "200", "source_text": "货币资金 200"},
    ]
    result = validate_extracted_statement(statement(items=items), "货币资金 100\n货币资金 200")
    assert {item["status"] for item in result["items"]} == {"pending_confirmation"}
    assert "multiple_values_for_concept:cash" in result["issues"]


def test_unknown_concept_is_rejected_instead_of_becoming_free_text():
    payload = statement(items=[{
        "concept": "model_invented_metric",
        "source_name": "模型自创指标",
        "raw_value": "1",
        "source_text": "模型自创指标 1",
    }])
    with pytest.raises(ValueError, match="invalid_financial_statement"):
        validate_extracted_statement(payload, "模型自创指标 1")
