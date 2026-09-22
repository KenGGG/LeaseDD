import pytest

from leasedd.enterprise_warning import (
    EnterpriseModule,
    EnterpriseWarningError,
    QyjCollector,
    parse_analysis,
    parse_notes,
    parse_main_business,
    parse_search,
    parse_three_reports,
)


SEARCH = "/finchinaAPP/v1/finchina-search/v1/multipleSearch"
REPORTS = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getThreeReports"


def test_pure_parsers_preserve_strings_and_nulls():
    candidates = parse_search({"data": {"list": [
        {"code": "a", "name": "甲公司", "symbol": "000001", "stock": True},
        {"code": "b", "name": "甲科技", "symbol": "000002", "stock": True},
    ]}})
    assert [candidate.name for candidate in candidates] == ["甲公司", "甲科技"]

    statement = parse_three_reports({"data": {
        "head": ["报告期", "货币资金"], "key": ["reportDate", "cash"],
        "level": [0, 1], "value": [["2025-12-31", "1,234.00"], ["2024-12-31", None]],
    }})
    assert statement["periods"] == ["2025-12-31", "2024-12-31"]
    assert statement["rows"][0]["values"] == ["1,234.00", None]

    analysis = parse_analysis({"data": {"fieldList": [
        {"name": "净利率", "value": "margin", "unit": "%", "indent": 0}
    ], "dataList": [{"reportDate": "2025-12-31", "margin": "12.30"}], "total": 1}})
    assert analysis["rows"][0]["unit"] == "%"

    notes = parse_notes({"data": {
        "head": ["项目", "2025-12-31", "2024-12-31"],
        "value": [["库存现金", "10", None]], "level": [1],
    }})
    assert notes["values"][0][1] is None


def test_main_business_reuses_lossless_matrix_shape_with_units():
    parsed = parse_main_business({"data": {
        "head": ["报告期", "营业收入"],
        "key": ["reportDate", "revenue"],
        "unit": ["", "万元"],
        "level": [0, 1],
        "value": [["2025-12-31", "1,234.00"], ["2024-12-31", None]],
    }})
    assert parsed["periods"] == ["2025-12-31", "2024-12-31"]
    assert parsed["rows"][0]["unit"] == "万元"
    assert parsed["rows"][0]["values"] == ["1,234.00", None]


def test_error_codes_are_distinct():
    codes = {EnterpriseWarningError(code).code for code in (
        "login_expired", "structure_changed", "empty_module"
    )}
    assert codes == {"login_expired", "structure_changed", "empty_module"}


class FakeSession:
    def __init__(self, responses=None, menu=None):
        self.responses = responses or []
        self.menu_items = menu or []
        self.closed = False
        self.actions = []

    def perform(self, action, **kwargs):
        self.actions.append((action, kwargs))
        return self.responses

    def menu(self, company_code):
        self.actions.append(("menu", {"company_code": company_code}))
        return self.menu_items

    def close(self):
        self.closed = True


def test_collector_selects_authoritative_response_and_closes_session():
    search_session = FakeSession([
        ("https://x/support/ping", {"data": {"list": [{"name": "错误"}]}}),
        ("https://x" + SEARCH, {"data": {"list": [{"code": "a", "name": "甲公司"}]}}),
    ])
    collector = QyjCollector(session_factory=lambda: search_session)
    assert [candidate.name for candidate in collector.search("甲公司")] == ["甲公司"]
    assert search_session.actions == [("search", {"name": "甲公司"})]
    assert search_session.closed

    module = EnterpriseModule("balance", "资产负债表", "statements", REPORTS, 1, {"childType": "balance"})
    collect_session = FakeSession([
        ("https://x/support", {"data": {}}),
        ("https://x" + REPORTS, {"data": {"head": ["报告期", "资产总计"], "key": ["date", "assets"], "level": [0, 0], "value": [["2025-12-31", "100"]]}}),
    ])
    collected = QyjCollector(session_factory=lambda: collect_session).collect_module("a", module)
    assert collected.module == module
    assert collected.parsed["rows"][0]["values"] == ["100"]
    assert len(collected.response_sha256) == 64
    assert collect_session.closed


def test_main_business_ignores_other_legacy_get_data_responses():
    module = EnterpriseModule("main_business", "主营构成", "notes", "/getData.action", 12)
    data = {"data": {
        "head": ["报告期", "营业收入"], "key": ["reportDate", "revenue"],
        "unit": ["", "万元"], "value": [["2025-12-31", "100"]],
    }}
    session = FakeSession([
        ("https://x/getData.action?reportUrlType=mainBusiness", {"data": [{"list": []}]}),
        ("https://x/getData.action?unitCode=4", data),
        ("https://x/getData.action?_t=background", {"data": {"other": True}}),
    ])
    collected = QyjCollector(session_factory=lambda: session).collect_module("a", module)
    assert collected.parsed["rows"][0]["values"] == ["100"]


def test_collector_preserves_post_request_parameters():
    module = EnterpriseModule("cash_analysis", "现金流量", "analysis", "/header-and-data", 9)
    session = FakeSession([(
        "https://x/header-and-data",
        {"data": {"fieldList": [{"name": "现金比率", "value": "ratio"}],
                  "dataList": [{"reportDate": "2025-12-31", "ratio": "1.2"}]}},
        {"pageCode": "web-FinancialanalysisF9-Cashfow", "unit": "4", "reportRange": "1"},
    )])
    collected = QyjCollector(session_factory=lambda: session).collect_module("a", module)
    assert collected.module.request_params == {
        "pageCode": "web-FinancialanalysisF9-Cashfow", "unit": "4", "reportRange": "1"
    }


def test_collector_filters_menu_to_financial_modules():
    session = FakeSession(menu=[
        {"key": "balance", "name": "资产负债表", "category": "statements", "endpoint": REPORTS},
        {"key": "news", "name": "新闻", "category": "other", "endpoint": "/news"},
    ])
    modules = QyjCollector(session_factory=lambda: session).enumerate_modules("a")
    assert [module.key for module in modules] == ["balance"]
    assert session.closed


@pytest.mark.parametrize("responses,code", [
    ([("https://x/login", {"redirect": "login"})], "login_expired"),
    ([("https://x" + SEARCH, {"unexpected": {}})], "structure_changed"),
    ([("https://x" + SEARCH, {"data": {"list": []}})], "empty_module"),
])
def test_search_surfaces_login_shape_and_empty_failures(responses, code):
    session = FakeSession(responses)
    with pytest.raises(EnterpriseWarningError) as raised:
        QyjCollector(session_factory=lambda: session).search("甲")
    assert raised.value.code == code
    assert session.closed
