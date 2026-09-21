from types import SimpleNamespace

from leasedd.enterprise_views import enterprise_statement_views


def row(module_key, module_name, statement_type, names, values, unit="万元"):
    return SimpleNamespace(
        module_key=module_key, module_name=module_name, category="statements", response_sha256="a" * 64,
        request_params={"statement_type": statement_type, "unit": unit, "mergeRange": "consolidated", "displayCurrency": "CNY"},
        parsed_payload={"periods": ["2025-12-31", "2024-12-31"], "rows": [
            {"name": name, "key": f"k-{index}", "values": pair} for index, (name, pair) in enumerate(zip(names, values))
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
