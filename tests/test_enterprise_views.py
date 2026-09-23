from types import SimpleNamespace

from leasedd.enterprise_views import enterprise_statement_views


def row(module_key, module_name, statement_type, names, values, unit="万元", keys=None):
    keys = keys or [f"k-{index}" for index in range(len(names))]
    return SimpleNamespace(
        module_key=module_key, module_name=module_name, category="statements", response_sha256="a" * 64,
        request_params={"statement_type": statement_type, "unit": unit, "mergeRange": "consolidated", "displayCurrency": "CNY"},
        parsed_payload={"periods": ["2025-12-31", "2024-12-31"], "rows": [
            {"name": name, "key": keys[index], "values": pair} for index, (name, pair) in enumerate(zip(names, values))
        ]},
    )


def test_enterprise_views_preserve_evidence_unknowns_and_all_periods():
    module = row("balance", "资产负债表", "balance_sheet", ["资产总计", "自定义项目"], [["100.00", "90.00"], ["1", None]])
    views = enterprise_statement_views(SimpleNamespace(id="import-1"), [module])
    assert [view["period"] for view in views] == ["2025-12-31", "2024-12-31"]
    assert all(view["source_type"] == "enterprise_warning" for view in views)
    assert all(view["document_id"] is None and view["conversion_id"] is None for view in views)
    item = views[0]["items"][0]
    assert (item["source_name"], item["raw_value"], item["raw_unit"]) == ("资产总计", "100.00", "万元")
    assert item["evidence"] == {
        "mapping_state": "mapped", "source_increment": "0.01", "response_sha256": "a" * 64,
        "module_key": "balance", "row": 0, "period_column": 0, "source_key": "k-0",
    }
    unknown = views[0]["items"][1]
    assert unknown["source_name"] == "自定义项目"
    assert unknown["concept"].startswith("disclosed_")
    assert unknown["evidence"]["mapping_state"] == "unmapped"


def test_enterprise_views_run_checks_as_non_destructive_warnings():
    module = row("balance", "资产负债表", "balance_sheet",
                 ["资产总计", "负债合计", "所有者权益合计"],
                 [["100", "90"], ["80", "70"], ["10", "20"]], unit="元")
    first, second = enterprise_statement_views(SimpleNamespace(id="import-1"), [module])
    assert first["formula_status"] == "warning"
    assert first["checks"][0]["status"] == "conflict"
    assert first["items"][0]["raw_value"] == "100"
    assert second["checks"][0]["status"] == "passed"
    assert first["checks"][1]["status"] == "not_checked_missing_disclosure"


def test_enterprise_views_map_noncurrent_totals_and_run_all_balance_checks():
    module = row(
        "balance", "资产负债表", "balance_sheet",
        ["流动资产合计", "非流动资产合计", "资产总计", "流动负债合计", "非流动负债合计", "负债合计", "所有者权益合计"],
        [["40", "36"], ["60", "54"], ["100", "90"], ["30", "27"], ["20", "18"], ["50", "45"], ["50", "45"]],
        unit="元",
    )
    first, second = enterprise_statement_views(SimpleNamespace(id="import-1"), [module])
    assert {item["source_name"]: item["concept"] for item in first["items"]}[
        "非流动资产合计"
    ] == "total_noncurrent_assets"
    assert {item["source_name"]: item["concept"] for item in first["items"]}[
        "非流动负债合计"
    ] == "total_noncurrent_liabilities"
    assert [check["status"] for check in first["checks"]] == ["passed", "passed", "passed"]
    assert [check["status"] for check in second["checks"]] == ["passed", "passed", "passed"]


def test_enterprise_views_clean_prefixed_formula_labels():
    income = row(
        "income", "利润表", "income_statement",
        ["营业利润", "加:营业外收入", "减:营业外支出", "利润总额", "减:所得税费用", "净利润"],
        [["80", "72"], ["5", "4"], ["3", "2"], ["82", "74"], ["12", "11"], ["70", "63"]],
        unit="元",
    )
    cash = row(
        "cash", "现金流量表", "cash_flow_statement",
        ["经营活动产生的现金流量净额", "投资活动产生的现金流量净额", "筹资活动产生的现金流量净额",
         "汇率变动对现金及现金等价物的影响", "现金及现金等价物净增加额", "加:期初现金及现金等价物余额",
         "期末现金及现金等价物余额", "现金及现金等价物净增加额"],
        [["10", "8"], ["-2", "-1"], ["3", "2"], ["1", "1"], ["12", "10"], ["100", "90"], ["112", "100"], ["12", None]],
        unit="元",
        keys=["op", "inv", "fin", "fx", "130036", "opening", "ending", "130065"],
    )
    views = enterprise_statement_views(SimpleNamespace(id="import-1"), [income, cash])
    assert all(check["status"] == "passed" for view in views for check in view["checks"])
    concepts = {item["source_name"]: item["concept"] for view in views for item in view["items"]}
    assert concepts["减:所得税费用"] == "income_tax_expense"
    assert concepts["加:营业外收入"] == "nonoperating_income"
    assert concepts["汇率变动对现金及现金等价物的影响"] == "exchange_rate_effect"
    assert concepts["加:期初现金及现金等价物余额"] == "beginning_cash_balance"
    supplemental = [item for view in views for item in view["items"] if item["evidence"]["source_key"] == "130065"]
    assert all(item["concept"].startswith("disclosed_") for item in supplemental)
