import pytest

from leasedd.enterprise_warning import (
    EnterpriseModule,
    EnterpriseWarningError,
    MODULES,
    QyjCollector,
    parse_analysis,
    parse_notes,
    parse_main_business,
    parse_search,
    parse_three_reports,
)


SEARCH = "/finchinaAPP/v1/finchina-search/v1/multipleSearch"
REPORTS = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getThreeReports"


def test_legacy_history_uses_source_nested_options_and_comma_separated_dates():
    from leasedd.enterprise_warning import legacy_history_request_params
    filters=[{'list':[{'list':[
        {'parameterName':'auditYear','list':[{'name':'自定义','value':'2024,2026'}]},
        {'parameterName':'reportDateType','list':[{'value':'20260630'},{'value':'1231'},{'value':'0630'}]},
        {'parameterName':'dataType','list':[{'value':'1'},{'value':'2'},{'value':'3'}]},
    ]}]}]
    original={'_t':'1227','reportDate':'20251231','dataType':'1','code':'company'}
    selected=legacy_history_request_params(original,filters)
    assert selected['reportDate']=='20240630,20241231,20250630,20251231,20260630'
    assert selected['dataType']=='1,2,3'
    assert selected['_t']=='1227' and selected['code']=='company'
    assert original['reportDate']=='20251231'
    with pytest.raises(EnterpriseWarningError):legacy_history_request_params(original,[])


def test_analysis_history_uses_filter_contract_without_inventing_scope_for_per_share():
    from leasedd.enterprise_warning import analysis_request_params
    filters=[{'parameterName':'reportDateType','children':[{'value':'20260630'},{'value':'1231'},{'value':'0630'}]},
             {'parameterName':'auditYear','children':[{'name':'5Y','value':'5'},{'name':'自定义','value':'2024'}]}]
    result=analysis_request_params({'pageCode':'source-page','auditYear':'5'},filters)
    assert result['auditYear']=='2024,2025,2026'
    assert result['reportDateType']=='20260630,1231,0630'
    assert 'reportRange' not in result
    filters.append({'parameterName':'reportRange','children':[{'value':'1'},{'value':'2'}]})
    assert analysis_request_params({},filters)['reportRange']=='1,2'


def test_history_parameters_use_source_years_and_latest_date_without_mutation():
    from leasedd.enterprise_warning import history_request_params
    original={'reportDate':['20260630','20251231'],'mergeRange':'1,2','unitCode':'4'}
    result=history_request_params(original,['2026','2025','2013'])
    assert result['auditYear']=='2013,2025,2026'
    assert result['reportDate']==['20260630','20260331','20251231','20250930','20250630','20250331','20131231','20130930','20130630','20130331']
    assert result['mergeRange']=='1,2'
    assert result['unitCode']=='4'
    assert result['displayCurrency']=='O'
    assert result['rateType']=='1'
    assert original['reportDate']==['20260630','20251231']
    with pytest.raises(EnterpriseWarningError):history_request_params(original,[])


def test_history_base_request_does_not_inherit_stale_currency_or_unit():
    from leasedd.enterprise_warning import history_request_params
    result=history_request_params({'reportDate':['20251231'],'unitCode':'8','displayCurrency':'USD','rateType':'2'},['2025'])
    assert (result['unitCode'],result['displayCurrency'],result['rateType'])==('4','O','1')


@pytest.mark.parametrize('child,scopes,kinds',[
    ('mainIndicatorsF9','1,2','1'),('assetsDebt','1,2,3,4','1,3,2,4,5,6'),
    ('profit','1,2,3,4','1,2,4'),('cashFlow','1,2,3,4','1,2')])
def test_history_requests_every_verified_scope_and_kind(child,scopes,kinds):
    from leasedd.enterprise_warning import history_request_params
    result=history_request_params({'childType':child,'reportDate':['20251231'],'mergeRange':'1','dataType':'1'},['2025'])
    assert (result['mergeRange'],result['dataType'])==(scopes,kinds)


def test_module_catalog_covers_all_current_financial_navigation_entries():
    assert len(MODULES) == 40
    assert [module[0] for module in MODULES[-4:]] == [
        "restricted_assets", "finance_costs", "nonrecurring_gains_losses", "long_term_receivables"
    ]
    notes = {module[1]: module[5] for module in MODULES if module[2] == 'notes'}
    assert notes['应收账款账龄分析']['child_type'] == 'notes_AccReceivableAging'
    assert notes['前五名其他应收款']['menu_parent'] == '其他应收款'
    assert notes['账龄超过1年的重要其他应付款']['child_type'] == 'notes_FinImportantOthPayables'
    assert notes['货币资金']['child_type']=='notes_MonetaryResources'
    assert notes['主要销售客户']['child_type']=='notes_MajorCustomers'
    assert notes['审计报告']['child_type']=='notes_AuditRep'
    assert notes['按款项性质分类']['child_type']=='notes_FinOthAccReceivableClassifybyProperty'
    assert notes['应付账款账龄分析']['child_type']=='notes_FinPayablesAging'
    assert notes['其他应付款账龄分析']['child_type']=='notes_FinOthpayablesAging'
    assert notes['预付款项账龄分析']['child_type']=='notes_FinPrepaymentsAging'
    assert notes['前五名预付款']['child_type']=='notes_FinPrePaymentsTopFive'
    assert notes['预收款项账龄分析']['child_type']=='notes_FinDepositreceivedAging'
    assert notes['账龄超过1年的重要预收款']['child_type']=='notes_FinImportantDepositReceived'
    for name in ['账龄超过1年的重要预付款','前五名应付款','前五名预收款','前五名其他应付款']:
        assert notes[name]['menu_only'] is True
        assert 'child_type' not in notes[name]


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


def test_analysis_uses_declared_period_field_and_excludes_it_from_metrics():
    parsed = parse_analysis({"data": {
        "fieldList": [
            {"name": "指标名称", "value": "reportDate2", "unit": ""},
            {"name": "每股收益", "value": "eps", "unit": "元"},
        ],
        "dataList": [{"reportDate2": "2026年中报", "eps": "0.42"}],
        "total": 1,
    }})
    assert parsed["periods"] == ["2026年中报"]
    assert [row["name"] for row in parsed["rows"]] == ["每股收益"]
    assert parsed["rows"][0]["values"] == ["0.42"]


def test_analysis_preserves_child_rows_with_their_period_values():
    parsed = parse_analysis({"data": {
        "fieldList": [
            {"name": "指标名称", "value": "reportDate2", "unit": ""},
            {"name": "上市公司披露", "value": "group", "highlight": True, "children": [
                {"name": "基本每股收益(元)", "value": "eps", "unit": "元", "children": []},
                {"name": "稀释每股收益(元)", "value": "diluted", "unit": "元", "children": []},
            ]},
        ],
        "dataList": [
            {"reportDate2": "2026年中报", "eps": "0.42", "diluted": None},
            {"reportDate2": "2025年年报", "eps": "0.38", "diluted": "0.37"},
        ],
        "total": 2,
    }})
    group = parsed["rows"][0]
    assert group["values"] == [None, None]
    assert group["children"][0]["values"] == ["0.42", "0.38"]
    assert group["children"][1]["values"] == [None, "0.37"]


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


def test_currency_variants_preserve_each_response_and_default_disclosed_values():
    module=EnterpriseModule('balance_sheet','资产负债表','statements',REPORTS,1)
    def response(value):return {'data':{'head':['报告期','资产总计'],'key':['date','assets'],'value':[['2025年年报',value]]}}
    original=response('100');usd=response('14.25')
    session=FakeSession([(REPORTS,original,{'displayCurrency':'O','rateType':'1','unitCode':'4'},'currency_variant'),
                         (REPORTS,usd,{'displayCurrency':'USD','rateType':'2','unitCode':'4'},'currency_variant')])
    result=QyjCollector(session_factory=lambda:session).collect_module('a',module)
    assert result.parsed['rows'][0]['values']==['100']
    assert result.raw['responses'][0]['payload']==original
    assert result.raw['responses'][1]['payload']==usd
    assert result.parsed['variants'][1]['parsed']['rows'][0]['values']==['14.25']
    assert result.parsed['variants'][1]['request_params']['rateType']=='2'
    assert result.module.request_params['displayCurrency']=='O'
    assert session.closed


def test_restricted_assets_uses_legacy_matrix_response():
    module = EnterpriseModule("restricted_assets", "受限资产", "notes", "/getData.action", 17)
    data = {"data": {
        "head": ["报告期", "货币资金"], "key": ["reportDateTitle", "cash"],
        "value": [["2025-12-31", "100"]],
    }}
    session = FakeSession([
        ("https://x/getData.action?pageCode=RestrictedAssets", {"data": [{"list": []}]}),
        ("https://x/getData.action?tabName=restricted-assets&unitCode=4", data),
    ])
    collected = QyjCollector(session_factory=lambda: session).collect_module("a", module)
    assert collected.parsed["periods"] == ["2025-12-31"]
    assert collected.parsed["rows"][0]["values"] == ["100"]
    assert collected.module.request_params["unit"] == "万元"


def test_long_term_receivables_preserves_confirmed_empty_response():
    module = EnterpriseModule("long_term_receivables", "长期应收款", "notes", "/getCompanyF9Data", 20)
    raw = {"info": "暂无数据", "returncode": 200, "total": 0}
    session = FakeSession([(
        "https://x/getCompanyF9Data?child_type=notes_longTermReceivable", raw,
        {"child_type": "notes_longTermReceivable"},
    )])
    collected = QyjCollector(session_factory=lambda: session).collect_module("a", module)
    assert collected.raw == raw
    assert collected.parsed == {"head": [], "values": [], "rows": [], "metadata": {"empty": True}}


@pytest.mark.parametrize('data',[{'leftTreeShow':True},{'leftTreeShow':True,'head':['科目'],'value':[]}])
def test_menu_only_response_requires_matching_disabled_evidence_not_just_left_tree_show(data):
    module=EnterpriseModule('long_term_receivables','长期应收款','notes','/getCompanyF9Data',20)
    raw={'returncode':0,'data':data}
    def collect(evidence):
        session=FakeSession([('https://x/getCompanyF9Data',raw,{'source_menu':evidence})])
        return QyjCollector(session_factory=lambda:session).collect_module('company',module)
    for evidence in ({},{'disabled':False,'name':'长期应收款','company_code':'company'},
                     {'disabled':True,'name':'长期应收款','company_code':'other'}):
        with pytest.raises(EnterpriseWarningError):collect(evidence)
    result=collect({'disabled':True,'name':'长期应收款','company_code':'company'})
    assert result.raw==raw
    assert result.parsed['metadata']['unavailable'] is True
    assert result.parsed['metadata'].get('empty') is not True


def test_dom_only_menu_keeps_explicit_evidence_without_fabricating_a_financial_response():
    module=EnterpriseModule('payables_top_five','前五名应付款','notes','/detail/enterprise/financialNotes',20,{'menu_only':True})
    menu={'name':module.name,'company_code':'company','disabled':True}
    raw={'source':'dom_menu','menu':menu}
    def collect(value):
        session=FakeSession([('https://www.qyyjt.cn/detail/enterprise/financialNotes',value,{'source_menu':menu})])
        return QyjCollector(session_factory=lambda:session).collect_module('company',module)
    result=collect(raw)
    assert result.raw==raw and result.parsed['metadata']['unavailable'] is True
    assert 'data' not in result.raw
    with pytest.raises(EnterpriseWarningError):collect({'source':'dom_menu','menu':{**menu,'disabled':False}})


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


def test_analysis_response_cannot_be_saved_under_another_page_code():
    module=EnterpriseModule('profitability','盈利能力','analysis','/header-and-data',1,{'pageCode':'profit-page'})
    session=FakeSession([('https://x/header-and-data',{'data':{'fieldList':[{'name':'比率','value':'ratio'}],'dataList':[{'reportDate':'2025','ratio':'1'}]}},{'pageCode':'other-page'})])
    with pytest.raises(EnterpriseWarningError):QyjCollector(session_factory=lambda:session).collect_module('a',module)


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
