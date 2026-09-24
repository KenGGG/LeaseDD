"""Thin 企业预警通 browser adapter and lossless response parsers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse


SEARCH_ENDPOINT = "/finchinaAPP/v1/finchina-search/v1/multipleSearch"
MAIN_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getMainIndicators"
REPORT_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getThreeReports"
ANALYSIS_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/table/header-and-data"
ANALYSIS_FILTER_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/table/filter"
NOTES_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data"
NOTES_MENU_PATH = '/detail/enterprise/financialNotes'
MAIN_BUSINESS_ENDPOINT = "/getData.action"
LEGACY_MATRIX_MODULES = {"main_business", "restricted_assets"}
LEGACY_RECORD_MODULES = {"receivables_top_five", "other_receivables_top_five"}
FINANCIAL_CATEGORIES = {"indicators", "statements", "analysis", "notes"}
MODULES = (
    ("main_indicators", "主要财务指标", "indicators", MAIN_ENDPOINT, "Fin.Statement_MainInDicators", {}),
    ("balance_sheet", "资产负债表", "statements", REPORT_ENDPOINT, "Fin.Statement_Liabilities", {"statement_type": "balance_sheet"}),
    ("income_statement", "利润表", "statements", REPORT_ENDPOINT, "Fin.Statement_ProfitTable", {"statement_type": "income_statement"}),
    ("cash_flow_statement", "现金流量表", "statements", REPORT_ENDPOINT, "Fin.Statement_CashFlow", {"statement_type": "cash_flow_statement"}),
    ("per_share", "每股指标", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_PerIndex", {"pageCode":"web-FinancialanalysisF9-Pershareindicators"}),
    ("profitability", "盈利能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_Earning", {"pageCode":"web-FinancialanalysisF9-Profitability"}),
    ("solvency", "偿债能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_SolvencyAbility", {"pageCode":"web-FinancialanalysisF9-Solvency"}),
    ("operation", "营运能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_Operation", {"pageCode":"web-FinancialanalysisF9-Operatingcapacity"}),
    ("growth", "成长能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_GrowthAbility", {"pageCode":"web-FinancialanalysisF9-Growthcapacity"}),
    ("cash_analysis", "现金流量", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_CashFlow", {"pageCode":"web-FinancialanalysisF9-Cashfow"}),
    ("dupont", "杜邦分析", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_DuPont", {"pageCode":"web-FinancialanalysisF9-DuPontanalysis"}),
    ("audit_report", "审计报告", "notes", NOTES_ENDPOINT, "Fin.Notes_AuditRep", {"child_type":"notes_AuditRep"}),
    ("main_business", "主营构成", "notes", MAIN_BUSINESS_ENDPOINT, "Operation_MainBusinessComposition", {}),
    ("major_customers", "主要销售客户", "notes", NOTES_ENDPOINT, "Fin.Notes_MainCustomers", {"child_type":"notes_MajorCustomers"}),
    ("major_suppliers", "主要供应商", "notes", NOTES_ENDPOINT, "Fin.Notes_MainSuppliers", {"child_type":"notes_MajorSuppliers"}),
    ("receivables_aging", "应收账款账龄分析", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_AccReceivableAging", "menu_parent": "应收账款"}),
    ("receivables_top_five", "前五名应收账款", "notes", MAIN_BUSINESS_ENDPOINT, "", {"child_type": "notes_FinDebtreceivalbeTopfive", "menu_parent": "应收账款", "legacy_tab": "debt-receivable"}),
    ("receivables_impairment", "计提坏账的重大应收账款", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_AccReceivableIndividualSignificantAmount", "menu_parent": "应收账款"}),
    ("prepayments_aging", "预付款项账龄分析", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinPrepaymentsAging", "menu_parent": "预付款项"}),
    ("prepayments_over_one_year", "账龄超过1年的重要预付款", "notes", NOTES_MENU_PATH, "", {"menu_only": True, "menu_parent": "预付款项"}),
    ("prepayments_top_five", "前五名预付款", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinPrePaymentsTopFive", "menu_parent": "预付款项"}),
    ("other_receivables_property", "按款项性质分类", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinOthAccReceivableClassifybyProperty", "menu_parent": "其他应收款"}),
    ("other_receivables_aging", "其他应收款账龄分析", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_OthAccReceivableAging", "menu_parent": "其他应收款"}),
    ("other_receivables_top_five", "前五名其他应收款", "notes", MAIN_BUSINESS_ENDPOINT, "", {"child_type": "notes_FinOthaccountsreceivableTopfive", "menu_parent": "其他应收款", "legacy_tab": "other-debt-receivable"}),
    ("other_receivables_impairment", "计提坏账的重大其他应收款", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_OthAccReceivableIndividualSignificantAmount", "menu_parent": "其他应收款"}),
    ("payables_aging", "应付账款账龄分析", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinPayablesAging", "menu_parent": "应付账款"}),
    ("payables_over_one_year", "账龄超过1年的重要应付账款", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinImportantPayables", "menu_parent": "应付账款"}),
    ("payables_top_five", "前五名应付款", "notes", NOTES_MENU_PATH, "", {"menu_only": True, "menu_parent": "应付账款"}),
    ("advances_aging", "预收款项账龄分析", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinDepositreceivedAging", "menu_parent": "预收款项"}),
    ("advances_over_one_year", "账龄超过1年的重要预收款", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinImportantDepositReceived", "menu_parent": "预收款项"}),
    ("advances_top_five", "前五名预收款", "notes", NOTES_MENU_PATH, "", {"menu_only": True, "menu_parent": "预收款项"}),
    ("other_payables_aging", "其他应付款账龄分析", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinOthpayablesAging", "menu_parent": "其他应付款"}),
    ("other_payables_over_one_year", "账龄超过1年的重要其他应付款", "notes", NOTES_ENDPOINT, "", {"child_type": "notes_FinImportantOthPayables", "menu_parent": "其他应付款"}),
    ("other_payables_top_five", "前五名其他应付款", "notes", NOTES_MENU_PATH, "", {"menu_only": True, "menu_parent": "其他应付款"}),
    ("cash_notes", "货币资金", "notes", NOTES_ENDPOINT, "Fin.Notes_Cash", {"child_type":"notes_MonetaryResources"}),
    ("inventory_notes", "存货", "notes", NOTES_ENDPOINT, "Fin.Notes_Inventory", {"child_type":"notes_Inventory"}),
    ("restricted_assets", "受限资产", "notes", MAIN_BUSINESS_ENDPOINT, "Fin.Notes_FinRestrictedAssets", {}),
    ("finance_costs", "财务费用", "notes", NOTES_ENDPOINT, "Fin.Notes_Fincosts", {"child_type":"notes_Fincosts"}),
    ("nonrecurring_gains_losses", "非经常性损益", "notes", NOTES_ENDPOINT, "Fin.Notes_FinExtOrdItem", {"child_type":"notes_FinExtOrdItem"}),
    ("long_term_receivables", "长期应收款", "notes", NOTES_ENDPOINT, "Fin.Notes_longTermReceivable",
     {"child_type": "notes_longTermReceivable"}),
)


class EnterpriseWarningError(RuntimeError):
    def __init__(self, code: str, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def fetch_core_variant(page, request: dict[str, Any]) -> dict[str, Any]:
    """Retry one transient provider-network failure without changing source values."""
    from playwright.sync_api import Error

    for attempt in range(2):
        try:
            return page.evaluate("""async ({path,params,headers})=>{
                const query=new URLSearchParams();
                for(const [key,value] of Object.entries(params))
                    for(const item of Array.isArray(value)?value:[value])query.append(key,String(item));
                const response=await fetch(path+'?'+query,{headers,credentials:'include',signal:AbortSignal.timeout(30000)});
                if(!response.ok)throw new Error('financial_request_failed');
                return response.json();
            }""", request)
        except Error as error:
            if 'Failed to fetch' not in str(error):
                raise
            if attempt:
                raise EnterpriseWarningError('source_request_unavailable') from None
            page.wait_for_timeout(2000)


def history_request_params(params: dict[str, Any], source_years: list[str]) -> dict[str, Any]:
    years=sorted({str(year) for year in source_years if re.fullmatch(r'\d{4}',str(year))})
    dates=params.get('reportDate') or []
    if isinstance(dates,str):dates=[dates]
    dates=[str(date) for date in dates if re.fullmatch(r'\d{8}',str(date))]
    if not years or not dates:raise EnterpriseWarningError('history_range_unavailable')
    latest=max(dates)
    verified={'mainIndicatorsF9':('1,2','1'),'assetsDebt':('1,2,3,4','1,3,2,4,5,6'),
              'profit':('1,2,3,4','1,2,4'),'cashFlow':('1,2,3,4','1,2')}.get(params.get('childType'))
    selection={'mergeRange':verified[0],'dataType':verified[1]} if verified else {}
    return {**params,**selection,'auditYear':','.join(years),'unitCode':'4','displayCurrency':'O','rateType':'1',
            'reportDate':[year+suffix for year in reversed(years) for suffix in ('1231','0930','0630','0331') if year+suffix<=latest],
            'reportDateType':latest+',1231,0930,0630,0331'}


def analysis_request_params(params: dict[str, Any], filters: list[dict[str, Any]]) -> dict[str, Any]:
    options={item.get('parameterName'):item.get('children') or [] for item in filters}
    reports=[str(item['value']) for item in options.get('reportDateType',[]) if item.get('value') is not None]
    latest=max((value for value in reports if re.fullmatch(r'\d{8}',value)),default='')
    starts=[str(item.get('value','')) for item in options.get('auditYear',[]) if item.get('name')=='自定义']
    if not latest or not starts or not re.fullmatch(r'\d{4}',starts[0]):raise EnterpriseWarningError('history_range_unavailable')
    first,last=int(starts[0]),int(latest[:4])
    if first>last or last-first>100:raise EnterpriseWarningError('history_range_unavailable')
    result={**params,'reportDateType':','.join(reports),'auditYear':','.join(str(year) for year in range(first,last+1)),'unit':'4'}
    if options.get('reportRange'):result['reportRange']=','.join(str(item['value']) for item in options['reportRange'])
    else:result.pop('reportRange',None)
    return result


def legacy_filter_options(filters: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    options = {}
    def visit(items):
        for item in items:
            if not isinstance(item, dict):
                continue
            children = item.get('list') or []
            if item.get('parameterName'):
                options[item['parameterName']] = children
            visit(children)
    visit(filters)
    return options


def legacy_history_request_params(params: dict[str, Any], filters: list[dict[str, Any]]) -> dict[str, Any]:
    options = legacy_filter_options(filters)
    reports = [str(item.get('value', '')) for item in options.get('reportDateType', [])]
    latest = max((value for value in reports if re.fullmatch(r'\d{8}', value)), default='')
    ranges = [str(item.get('value', '')) for item in options.get('auditYear', []) if item.get('name') == '自定义']
    if not latest or not ranges or not re.fullmatch(r'\d{4},\d{4}', ranges[0]):
        raise EnterpriseWarningError('history_range_unavailable')
    first, last = map(int, ranges[0].split(','))
    if first > last or last - first > 100:
        raise EnterpriseWarningError('history_range_unavailable')
    suffixes = [value for value in reports if value in {'0331', '0630', '0930', '1231'}]
    dates = {str(year)+suffix for year in range(first, last+1) for suffix in suffixes if str(year)+suffix <= latest}
    dates.add(latest)
    result = {**params, 'reportDate': ','.join(sorted(dates)), 'unitCode': '4'}
    if options.get('dataType'):
        result['dataType'] = ','.join(str(item['value']) for item in options['dataType'])
    return result


@dataclass(frozen=True)
class EnterpriseCandidate:
    code: str
    name: str
    identity: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnterpriseModule:
    key: str
    name: str
    category: str
    endpoint_path: str
    order: int
    request_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectedModule:
    module: EnterpriseModule
    raw: dict[str, Any]
    parsed: dict[str, Any]
    response_sha256: str


def _data(payload: dict[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise EnterpriseWarningError("structure_changed")
    data = payload["data"]
    if any(key not in data for key in required):
        raise EnterpriseWarningError("structure_changed")
    return data


def _not_empty(value: Any) -> Any:
    if value in (None, [], {}):
        raise EnterpriseWarningError("empty_module")
    return value


def parse_search(payload: dict[str, Any]) -> list[EnterpriseCandidate]:
    items = _not_empty(_data(payload, ("list",))["list"])
    if not isinstance(items, list):
        raise EnterpriseWarningError("structure_changed")
    result = []
    for item in items:
        if not isinstance(item, dict) or not item.get("code") or not item.get("name"):
            raise EnterpriseWarningError("structure_changed")
        result.append(EnterpriseCandidate(str(item["code"]), str(item["name"]), dict(item)))
    return result


def _parse_matrix(payload: dict[str, Any], *, units: bool) -> dict[str, Any]:
    required = ("head", "key", "value")
    data = _data(payload, required)
    heads, keys, values = data["head"], data["key"], _not_empty(data["value"])
    if not all(isinstance(item, list) for item in (heads, keys, values)) or len(heads) != len(keys):
        raise EnterpriseWarningError("structure_changed")
    if not heads or not values or any(not isinstance(row, list) or len(row) != len(heads) for row in values):
        raise EnterpriseWarningError("structure_changed")
    periods = [row[0] for row in values]
    levels = data.get("level", [])
    unit_values = data.get("unit", []) if units else []
    rows = []
    for index in range(1, len(heads)):
        row = {"name": heads[index], "key": keys[index], "values": [value[index] for value in values]}
        if index < len(levels):
            row["level"] = levels[index]
        if index < len(unit_values):
            row["unit"] = unit_values[index]
        rows.append(row)
    return {"periods": periods, "rows": rows, "metadata": {key: value for key, value in data.items() if key not in required}}


def parse_main_indicators(payload: dict[str, Any]) -> dict[str, Any]:
    return _parse_matrix(payload, units=True)


def parse_three_reports(payload: dict[str, Any]) -> dict[str, Any]:
    return _parse_matrix(payload, units=False)


def parse_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    data = _data(payload, ("fieldList", "dataList"))
    fields, values = data["fieldList"], _not_empty(data["dataList"])
    if not isinstance(fields, list) or not isinstance(values, list):
        raise EnterpriseWarningError("structure_changed")
    period_field = next((item.get("value") for item in fields if isinstance(item, dict)
                         and str(item.get("value") or "").startswith("reportDate")), "reportDate")
    periods = [row.get(period_field) for row in values if isinstance(row, dict)]
    if len(periods) != len(values) or any(period is None for period in periods):
        raise EnterpriseWarningError("structure_changed")
    def with_values(item: dict[str, Any]) -> dict[str, Any]:
        key = item["value"]
        children = item.get("children")
        return {
            **item,
            "values": [row.get(key) for row in values],
            **({"children": [with_values(child) for child in children]}
               if isinstance(children, list) else {}),
        }

    rows = []
    for item in fields:
        if not isinstance(item, dict) or not item.get("value"):
            raise EnterpriseWarningError("structure_changed")
        key = item["value"]
        if key == period_field:
            continue
        rows.append(with_values(item))
    return {"periods": periods, "rows": rows, "total": data.get("total")}


def parse_notes(payload: dict[str, Any]) -> dict[str, Any]:
    data = _data(payload, ("head", "value"))
    values = _not_empty(data["value"])
    if not isinstance(data["head"], list) or not isinstance(values, list) or any(not isinstance(row, list) for row in values):
        raise EnterpriseWarningError("structure_changed")
    return {"head": data["head"], "values": [row[1:] for row in values], "rows": values,
            "metadata": {key: value for key, value in data.items() if key not in ("head", "value")}}


def parse_precise_notes(payload: dict[str, Any]) -> dict[str, Any]:
    data = _data(payload, ("head", "value"))
    head, values = data["head"], _not_empty(data["value"])
    if (not isinstance(head, list) or not isinstance(values, list) or not head
            or any(not isinstance(row, list) or len(row) != len(head) for row in values)):
        raise EnterpriseWarningError("structure_changed")
    markers = [index for index, label in enumerate(head) if index and isinstance(label, str)
               and re.fullmatch(r"\d{4}年(?:年报|中报)", label)]
    if not markers or markers[0] != 1:
        raise EnterpriseWarningError("structure_changed")
    grouped_heads, grouped_rows, periods = [], [], []
    for position, start in enumerate(markers):
        end = markers[position + 1] if position + 1 < len(markers) else len(head)
        if end <= start + 1:
            raise EnterpriseWarningError("structure_changed")
        periods.append(head[start])
        grouped_heads.append([head[0], *head[start + 1:end]])
        grouped_rows.append([[row[0], *row[start + 1:end]] for row in values])
    return {"head": grouped_heads, "rows": grouped_rows,
            "metadata": {**{key: value for key, value in data.items() if key not in ("head", "value")},
                         "report": periods, "precise_record": True}}


def parse_main_business(payload: dict[str, Any]) -> dict[str, Any]:
    return _parse_matrix(payload, units=True)


def parse_empty_notes(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("returncode") != 200 or payload.get("total") not in (0, None) or "data" in payload:
        raise EnterpriseWarningError("structure_changed")
    return {"head": [], "values": [], "rows": [], "metadata": {"empty": True}}


def _hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _parser(module: EnterpriseModule) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if module.key in LEGACY_MATRIX_MODULES:
        return parse_main_business
    if module.key in LEGACY_RECORD_MODULES:
        return parse_precise_notes
    if module.key == "long_term_receivables":
        return parse_empty_notes
    if module.endpoint_path.endswith("getMainIndicators"):
        return parse_main_indicators
    if module.endpoint_path.endswith("getThreeReports"):
        return parse_three_reports
    if module.endpoint_path.endswith("header-and-data"):
        return parse_analysis
    if module.endpoint_path.endswith("getCompanyF9Data"):
        return parse_notes
    raise EnterpriseWarningError("structure_changed")


class QyjCollector:
    def __init__(self, session_factory: Callable[[], Any] | None = None):
        bridge = os.getenv('QYJ_BRIDGE_SOCKET')
        if session_factory is not None:
            self.session_factory = session_factory
        elif bridge:
            from .enterprise_browser_bridge import RemoteBrowserSession
            self.session_factory = lambda: RemoteBrowserSession(bridge)
        else:
            self.session_factory = _PlaywrightSession

    @staticmethod
    def _parts(item: tuple) -> tuple[str, dict[str, Any], dict[str, Any]]:
        url, payload, *rest = item
        return url, payload, (rest[0] if rest and isinstance(rest[0], dict) else {})

    @classmethod
    def _match(cls, responses: list[tuple], endpoint: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
        normalized = [cls._parts(item) for item in responses]
        matched = [item for item in normalized if endpoint in item[0]]
        if not matched and any("login" in url.lower() for url, _, _ in normalized):
            raise EnterpriseWarningError("login_expired")
        if not matched:
            raise EnterpriseWarningError("structure_changed")
        return matched[-1]

    @classmethod
    def _one(cls, responses: list[tuple[str, dict[str, Any]]], endpoint: str) -> dict[str, Any]:
        return cls._match(responses, endpoint)[1]

    def search(self, name: str) -> list[EnterpriseCandidate]:
        session = self.session_factory()
        try:
            return parse_search(self._one(session.perform("search", name=name), SEARCH_ENDPOINT))
        finally:
            session.close()

    def enumerate_modules(self, company_code: str) -> list[EnterpriseModule]:
        session = self.session_factory()
        try:
            items = session.menu(company_code)
            modules = []
            for order, item in enumerate(items):
                if item.get("category") not in FINANCIAL_CATEGORIES:
                    continue
                required = ("key", "name", "category", "endpoint")
                if any(not item.get(key) for key in required):
                    raise EnterpriseWarningError("structure_changed")
                modules.append(EnterpriseModule(item["key"], item["name"], item["category"],
                                                item["endpoint"], order, item.get("params", {})))
            return _not_empty(modules)
        finally:
            session.close()

    def collect_module(self, company_code: str, module: EnterpriseModule) -> CollectedModule:
        session = self.session_factory()
        try:
            responses = session.perform("collect", company_code=company_code, module=module)
            variants=[self._parts(item) for item in responses if len(item)>3 and item[3]=='currency_variant']
            if variants:
                parser=_parser(module)
                records=[];views=[]
                for url,payload,params in variants:
                    if module.endpoint_path not in url:raise EnterpriseWarningError('structure_changed')
                    parsed=parser(payload);digest=_hash(payload)
                    records.append({'request_params':params,'payload':payload,'response_sha256':digest})
                    views.append({'request_params':params,'parsed':parsed,'response_sha256':digest})
                default=next((index for index,(_,_,params) in enumerate(variants) if params.get('displayCurrency')=='O' and str(params.get('rateType'))=='1'),None)
                if default is None:raise EnterpriseWarningError('structure_changed')
                raw={'responses':records}
                params={**module.request_params,**variants[default][2],'unit':'万元'}
                return CollectedModule(replace(module,request_params=params),raw,{**views[default]['parsed'],'variants':views},_hash(raw))
            disabled_menu = next((self._parts(item) for item in responses
                                  if module.key in LEGACY_RECORD_MODULES
                                  and isinstance(item[1], dict) and item[1].get('source') == 'dom_menu'
                                  and item[1].get('menu', {}).get('disabled') is True), None)
            if disabled_menu:
                url, raw, captured_params = disabled_menu
            elif module.key in LEGACY_MATRIX_MODULES | LEGACY_RECORD_MODULES:
                candidates = []
                for item in responses:
                    candidate_url, candidate_raw, candidate_params = self._parts(item)
                    if module.endpoint_path not in candidate_url or not isinstance(candidate_raw.get('data'), dict):
                        continue
                    fields = ('head', 'key', 'value') if module.key in LEGACY_MATRIX_MODULES else ('head', 'value')
                    if not all(key in candidate_raw['data'] for key in fields):
                        continue
                    query = {key: values[-1] for key, values in parse_qs(urlparse(candidate_url).query).items()}
                    if module.key in LEGACY_RECORD_MODULES and {**query, **candidate_params}.get('tabName') != module.request_params.get('legacy_tab'):
                        continue
                    candidates.append((candidate_url, candidate_raw, candidate_params))
                if not candidates:
                    raise EnterpriseWarningError("structure_changed")
                url, raw, captured_params = candidates[-1]
            else:
                url, raw, captured_params = self._match(responses, module.endpoint_path)
            query = {key: values if len(values) > 1 else values[0] for key, values in parse_qs(urlparse(url).query).items()}
            params = {**module.request_params, **captured_params, **query}
            expected_page=module.request_params.get('pageCode')
            if expected_page and params.get('pageCode')!=expected_page:raise EnterpriseWarningError('module_identity_mismatch')
            if params.get("unitCode") == "4": params["unit"] = "万元"
            if params.get("mergeRange") == "1": params["mergeRange"] = "consolidated"
            collected_module = replace(module, request_params=params)
            menu = params.get('source_menu') or {}
            no_data = (raw.get('returncode') == 0
                    and isinstance(raw.get('data'), dict) and 'leftTreeShow' in raw['data']
                    and raw['data'].get('value') in (None, []))
            dom_only = (module.category == 'notes' and set(raw) == {'source','menu'}
                        and raw.get('source') == 'dom_menu' and raw.get('menu') == menu)
            if (module.category == 'notes' and (no_data or dom_only)
                    and menu.get('disabled') is True and menu.get('name') == module.name
                    and menu.get('company_code') == company_code):
                parsed = {'head': [], 'rows': [], 'metadata': {'unavailable': True, 'source_menu': menu}}
            else:
                parser = parse_notes if module.key == "long_term_receivables" and isinstance(raw.get("data"), dict) else _parser(collected_module)
                parsed = parser(raw)
            if module.key == 'audit_report':
                pdf_responses = [self._parts(item) for item in responses if len(item) > 3 and item[3] == 'audit_pdf']
                if pdf_responses:
                    disclosed = {str(row[0]) for row in parsed['rows'] if isinstance(row, list) and row}
                    links = {}
                    for pdf_url, pdf_payload, pdf_params in pdf_responses:
                        date = str(pdf_params.get('date', ''))
                        entries = pdf_payload.get('data') if pdf_payload.get('returncode') == 0 else None
                        if (date not in disclosed or not re.fullmatch(r'\d{8}', date)
                                or not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict)):
                            continue
                        entry = entries[0]
                        path = entry.get('filePath')
                        if (str(entry.get('reportDate', '')).replace('-', '') == date
                                and isinstance(path, str) and urlparse(path).scheme == 'https'
                                and urlparse(path).hostname == 'hwfile.finchina.com'
                                and path.lower().split('?')[0].endswith('.pdf')):
                            links[date] = path
                    raw = {**raw, '_audit_pdf_responses': [
                        {'source_url': url, 'request_params': params, 'payload': payload}
                        for url, payload, params in pdf_responses]}
                    parsed['metadata']['audit_pdf_links'] = links
            return CollectedModule(collected_module, raw, parsed, _hash(raw))
        finally:
            session.close()


class _PlaywrightSession:
    """Small browser boundary; authentication remains inside the persistent profile."""

    def __init__(self):
        profile = os.getenv("QYJ_PROFILE_DIR")
        if not profile:
            raise EnterpriseWarningError("profile_missing")
        from playwright.sync_api import Error, sync_playwright
        self._playwright = None
        self._context = None
        try:
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                profile, executable_path=os.getenv("QYJ_CHROME_EXECUTABLE", "/usr/bin/google-chrome"), headless=True,
                ignore_default_args=["--enable-automation", "--password-store=basic", "--use-mock-keychain"],
            )
            self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
        except Error as error:
            code = "profile_in_use" if "ProcessSingleton" in str(error) or "SingletonLock" in str(error) else "browser_unavailable"
            self.close()
            raise EnterpriseWarningError(code) from None
        self.base = os.getenv("QYJ_BASE_URL", "https://www.qyyjt.cn")

    def _navigate_authenticated(self, url: str):
        """Dismiss displacement notices and try the existing login form once.

        Never extract credentials, guess passwords, or retry a challenged login.
        Form submission can use browser-filled values; otherwise the operator
        must complete authentication in the browser.
        """
        def visible(text):
            return self.page.get_by_text(text, exact=True).first.is_visible()

        def login_visible():
            return visible("账户密码登录") or visible("手机扫码登录")

        def dismiss_notice():
            if visible("我已知晓"):
                self.page.get_by_text("我已知晓", exact=True).first.click()

        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1500)
        dismiss_notice()
        if not login_visible():
            return
        if not self.page.locator("#username").is_visible() and visible("账户密码登录"):
            self.page.get_by_text("账户密码登录", exact=True).first.click()
        if visible("登录"):
            # Match Quantradar: Chrome must activate its saved-login selection.
            # Masked dots alone do not prove that the form has received autofill.
            # Do not inspect field values or the browser's credential store.
            self.page.locator("#username").click()
            self.page.keyboard.press("ArrowDown")
            self.page.keyboard.press("Enter")
            submit = self.page.locator("button[type='submit']")
            for _ in range(20):
                self.page.wait_for_timeout(250)
                if submit.is_enabled():
                    break
            else:
                raise EnterpriseWarningError("authentication_required")
            submit.click(no_wait_after=True)
            for _ in range(20):
                self.page.wait_for_timeout(500)
                if not login_visible():
                    break
        dismiss_notice()
        if login_visible():
            raise EnterpriseWarningError("authentication_required")
        # Login can send the browser to the home page instead of the report.
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1500)
        dismiss_notice()
        if login_visible():
            raise EnterpriseWarningError("authentication_required")

    def _wait_finance_headers(self) -> dict[str, str]:
        # A rendered navigation menu does not mean its financial XHR has arrived.
        # Pump browser events for a bounded interval; a timeout is not proof of logout.
        for _ in range(20):
            if self._finance_headers.get('pcuss'):
                return dict(self._finance_headers)
            self.page.wait_for_timeout(250)
        if self._finance_headers.get('pcuss'):
            return dict(self._finance_headers)
        raise EnterpriseWarningError('finance_bootstrap_unavailable')

    def _capture(self, action: Callable[[], None], *, wait_ms: int = 1500) -> list[tuple]:
        captured = []
        self._finance_headers = {}
        self._legacy_headers = {}
        def record(response):
            try:
                # Login requests/responses may contain passwords or tokens.
                # Keep only a non-sensitive marker for existing error handling.
                if "login" in urlparse(response.url).path.lower():
                    captured.append(("/login", {}, {}))
                    return
                if "finchinaAPP" in response.url or "getData.action" in response.url or "login" in response.url.lower():
                    source = urlparse(response.url)
                    if source.netloc == urlparse(getattr(self, "base", "https://www.qyyjt.cn")).netloc and "/finchina-finance/" in source.path:
                        # Quantradar's authenticated in-page request pattern. Never
                        # persist headers or inspect passwords/cookie storage.
                        headers = response.request.headers
                        if headers.get("pcuss"):
                            self._finance_headers = {key: headers[key] for key in (
                                "accept", "client", "content-type", "pcuss", "system", "system1", "terminal", "user", "ver"
                            ) if key in headers}
                    query = {key: values if len(values) > 1 else values[0]
                             for key, values in parse_qs(urlparse(response.url).query).items()}
                    if source.netloc == urlparse(getattr(self, 'base', 'https://www.qyyjt.cn')).netloc and source.path == MAIN_BUSINESS_ENDPOINT:
                        headers = response.request.headers
                        if headers.get('pcuss') and headers.get('dataid') and query.get('_t'):
                            self._legacy_headers[str(query['_t'])] = {key: headers[key] for key in (
                                'accept', 'client', 'content-type', 'dataid', 'pcuss', 'system', 'system1',
                                'terminal', 'user', 'ver', 'x-request-id', 'x-request-url'
                            ) if key in headers}
                    try:
                        post_data = response.request.post_data_json
                    except Exception:
                        post_data = None
                    params = {**(post_data if isinstance(post_data, dict) else {}), **query}
                    captured.append((response.url, response.json(), params))
            except Exception:
                pass
        self.page.on("response", record)
        try:
            action()
            self.page.wait_for_timeout(wait_ms)
        finally:
            self.page.remove_listener("response", record)
        return captured

    def _menu_item(self, name: str):
        return self._menu_entry(name, '.pro-menu-item')

    def _menu_entry(self, name: str, selector: str):
        exact_name = re.compile(f"^{re.escape(name)}$")
        holder = self.page.locator(".ant-tree-list-holder")
        for ratio in (0, 0.25, 0.5, 0.75, 1):
            item = self.page.locator(selector).filter(has_text=exact_name)
            if item.count():
                return item.last
            holder.evaluate_all(
                "(els, ratio) => els.forEach(e => e.scrollTop = (e.scrollHeight - e.clientHeight) * ratio)",
                ratio,
            )
            self.page.wait_for_timeout(250)
        item = self.page.locator(selector).filter(has_text=exact_name)
        if item.count():
            return item.last
        raise EnterpriseWarningError("structure_changed", {'menu_name':name,'menu_selector':selector})

    def _note_menu_evidence(self, module: EnterpriseModule, company_code: str) -> dict[str, Any]:
        for name in ('财务附注', module.request_params.get('menu_parent')):
            if not name:
                continue
            group = self._menu_entry(name, '.pro-menu-submenu-title')
            if not group.evaluate("e=>e.closest('.ant-tree-treenode')?.classList.contains('ant-tree-treenode-switcher-open')"):
                group.click(force=True)
                self.page.wait_for_timeout(250)
        evidence = self._menu_item(module.name).evaluate("e=>({name:e.innerText.trim(),disabled:e.getAttribute('aria-disabled')==='true'})")
        return {**evidence, 'company_code':company_code, 'source_url':self.page.url}

    def perform(self, action: str, **kwargs) -> list[tuple[str, dict[str, Any]]]:
        if action == "search":
            def run():
                self._navigate_authenticated(self.base)
                trigger = self.page.locator("input[readonly][placeholder*='公司']").first
                if trigger.count():
                    trigger.click()
                box = self.page.locator("input:not([readonly])[placeholder*='企业']").last
                box.fill(kwargs["name"])
            return self._capture(run)
        if action == "collect":
            module = kwargs["module"]
            direct_responses = []
            def run():
                path = NOTES_MENU_PATH if module.request_params.get('menu_only') else '/detail/enterprise/financialStatements'
                self._navigate_authenticated(f"{self.base}{path}?code={kwargs['company_code']}&type=company")
                if module.request_params.get('menu_only'):
                    evidence = self._note_menu_evidence(module, kwargs['company_code'])
                    if not evidence['disabled']:
                        raise EnterpriseWarningError('module_interface_unverified')
                    direct_responses.append((self.page.url, {'source':'dom_menu','menu':evidence},
                                             {'code':kwargs['company_code'],'source_menu':evidence}))
                    return
                if module.endpoint_path==ANALYSIS_ENDPOINT and module.request_params.get('pageCode'):
                    return
                if module.category == "notes" and module.request_params.get("child_type") and module.key not in LEGACY_RECORD_MODULES:
                    headers = self._wait_finance_headers()
                    raw = self.page.evaluate(
                        "async ([code, child, headers]) => fetch(`/finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data?child_type=${encodeURIComponent(child)}&code=${encodeURIComponent(code)}&type=company`, {headers, credentials:'include'}).then(r => r.json())",
                        [kwargs["company_code"], module.request_params["child_type"], headers],
                    )
                    params = {'code': kwargs['company_code'], 'type': 'company', 'child_type': module.request_params['child_type']}
                    if (raw.get('returncode') == 0 and isinstance(raw.get('data'), dict)
                            and 'leftTreeShow' in raw['data'] and raw['data'].get('value') in (None, [])):
                        params['source_menu'] = self._note_menu_evidence(module, kwargs['company_code'])
                    direct_responses.append((self.base+module.endpoint_path, raw, params))
                    if module.key == 'audit_report' and isinstance(raw.get('data'), dict) and raw['data'].get('value'):
                        evidence = self._note_menu_evidence(module, kwargs['company_code'])
                        if evidence['disabled']:
                            return
                        self._menu_item(module.name).click(force=True)
                        visible_links = []
                        for _ in range(20):
                            visible_links = [item for item in self.page.get_by_text('查看', exact=True).all() if item.is_visible()]
                            if visible_links:
                                break
                            self.page.wait_for_timeout(250)
                        if not visible_links:
                            raise EnterpriseWarningError('audit_pdf_link_unavailable')
                        with self.page.expect_response(lambda response: response.url.startswith(self.base+MAIN_BUSINESS_ENDPOINT)
                                and parse_qs(urlparse(response.url).query).get('_t') == ['218'], timeout=20000):
                            visible_links[0].click(force=True)
                    return
                if module.category in ("analysis", "notes"):
                    self.page.get_by_text("财务分析" if module.category == "analysis" else "财务附注", exact=True).click(force=True)
                    self.page.wait_for_timeout(500)
                if module.key in LEGACY_RECORD_MODULES:
                    evidence = self._note_menu_evidence(module, kwargs['company_code'])
                    if evidence['disabled']:
                        direct_responses.append((self.page.url, {'source':'dom_menu','menu':evidence},
                                                 {'code':kwargs['company_code'],'source_menu':evidence}))
                        return
                item = self._menu_item(module.name)
                if module.endpoint_path in {REPORT_ENDPOINT,ANALYSIS_ENDPOINT}:
                    with self.page.expect_response(lambda response: module.endpoint_path in response.url,timeout=20000):
                        item.click(force=True)
                else:
                    item.click(force=True)
                if module.key == "long_term_receivables":
                    child_type = module.request_params["child_type"]
                    self.page.evaluate(
                        "async ([code, child]) => fetch(`/finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data?child_type=${child}&code=${code}&type=company`).then(r => r.json())",
                        [kwargs["company_code"], child_type],
                    )
            responses=self._capture(run, wait_ms=5000 if module.key == "main_business" else 2500)
            if direct_responses:
                if module.key == 'audit_report' and isinstance(direct_responses[0][1].get('data'), dict):
                    periods = [str(row[0]) for row in direct_responses[0][1]['data'].get('value', [])
                               if isinstance(row, list) and row and re.fullmatch(r'\d{8}', str(row[0]))]
                    captured = [entry for entry in responses if MAIN_BUSINESS_ENDPOINT in entry[0]
                                and str(entry[2].get('_t')) == '218'
                                and str(entry[2].get('code')) == kwargs['company_code']]
                    headers = dict(self._legacy_headers.get('218') or {})
                    if periods and not headers.get('dataid'):
                        raise EnterpriseWarningError('authentication_required')
                    for period in periods:
                        first = next((entry for entry in captured if str(entry[2].get('date')) == period), None)
                        if first:
                            direct_responses.append((*first[:3], 'audit_pdf'))
                            continue
                        self.page.wait_for_timeout(3100)
                        params = {'_t':'218', 'code':kwargs['company_code'], 'date':period, 'type':'company'}
                        url = self.base+MAIN_BUSINESS_ENDPOINT+'?'+urlencode(params)
                        response = self._context.request.post(url, headers=headers, timeout=30000)
                        if not response.ok:
                            raise EnterpriseWarningError('source_request_unavailable')
                        direct_responses.append((url, response.json(), params, 'audit_pdf'))
                return direct_responses
            if module.key in LEGACY_MATRIX_MODULES | LEGACY_RECORD_MODULES:
                operation = '1227' if module.key == 'main_business' else '1311'
                matches = [entry for entry in responses if MAIN_BUSINESS_ENDPOINT in entry[0]
                           and entry[2].get('code') == kwargs['company_code'] and str(entry[2].get('_t')) == operation
                           and (module.key not in LEGACY_RECORD_MODULES or entry[2].get('tabName') == module.request_params.get('legacy_tab'))]
                filters = [entry[1].get('data') for entry in responses if MAIN_BUSINESS_ENDPOINT in entry[0]
                           and entry[2].get('code') == kwargs['company_code'] and str(entry[2].get('_t')) == '1072'
                           and isinstance(entry[1].get('data'), list)]
                if not matches or not filters:
                    raise EnterpriseWarningError('structure_changed')
                headers = dict(self._legacy_headers.get(operation) or {})
                if not headers.get('dataid'):
                    raise EnterpriseWarningError('authentication_required')
                params = legacy_history_request_params(matches[-1][2], filters[-1])
                def fetch_legacy(selection):
                    return self.page.evaluate("""async ({params,headers})=>{
                        const response=await fetch('/getData.action?'+new URLSearchParams(params),
                            {headers,credentials:'include',signal:AbortSignal.timeout(30000)});
                        if(!response.ok)throw new Error('financial_request_failed');return response.json();
                    }""", {'params': selection, 'headers': headers})
                if module.key == 'restricted_assets':
                    raw = fetch_legacy(params)
                    parse_main_business(raw)
                    return [(self.base+MAIN_BUSINESS_ENDPOINT, raw, params)]
                if module.key in LEGACY_RECORD_MODULES:
                    raw = fetch_legacy(params)
                    parse_precise_notes(raw)
                    return [(self.base+MAIN_BUSINESS_ENDPOINT, raw, params)]
                options = legacy_filter_options(filters[-1])
                currencies = [str(item['value']) for item in options.get('displayCurrency', [])]
                rates = [str(item['value']) for item in options.get('rateType', [])]
                if 'O' not in currencies or '1' not in rates:
                    raise EnterpriseWarningError('structure_changed')
                variants = []
                for currency in currencies:
                    for rate in rates:
                        if variants:self.page.wait_for_timeout(3100)
                        selection = {**params, 'displayCurrency': currency, 'currencyType': currency, 'rateType': rate}
                        raw = fetch_legacy(selection)
                        parse_main_business(raw)
                        variants.append((self.base+MAIN_BUSINESS_ENDPOINT, raw, selection, 'currency_variant'))
                return variants
            if module.endpoint_path==ANALYSIS_ENDPOINT:
                matches=[entry for entry in responses if ANALYSIS_ENDPOINT in entry[0] and entry[2].get('code')==kwargs['company_code']]
                if module.request_params.get('pageCode'):
                    captured={'pageCode':module.request_params['pageCode'],'code':kwargs['company_code'],'type':'company'}
                elif matches:captured=matches[-1][2]
                else:raise EnterpriseWarningError('structure_changed')
                headers=dict(self._finance_headers)
                if not headers.get('pcuss'):raise EnterpriseWarningError('authentication_required')
                def post(path,params):
                    return self.page.evaluate("""async ({path,params,headers})=>{
                        const response=await fetch(path,{method:'POST',headers:{...headers,'content-type':'application/json'},credentials:'include',body:JSON.stringify(params),signal:AbortSignal.timeout(30000)});
                        if(!response.ok)throw new Error('financial_request_failed');return response.json();
                    }""",{'path':path,'params':params,'headers':headers})
                filters=post(ANALYSIS_FILTER_ENDPOINT,{key:captured[key] for key in ('pageCode','code','type')})
                if not isinstance(filters.get('data'),list):raise EnterpriseWarningError('structure_changed')
                params=analysis_request_params(captured,filters['data'])
                raw=post(ANALYSIS_ENDPOINT,params);parse_analysis(raw)
                return [(self.base+ANALYSIS_ENDPOINT,raw,params)]
            if module.endpoint_path in {MAIN_ENDPOINT,REPORT_ENDPOINT}:
                matches=[entry for entry in responses if module.endpoint_path in entry[0] and entry[2].get('code')==kwargs['company_code']]
                if not matches:raise EnterpriseWarningError('structure_changed')
                headers=dict(self._finance_headers)
                if not headers.get('pcuss'):raise EnterpriseWarningError('authentication_required')
                field=self.page.locator('.dzh-screen-form-item').filter(has=self.page.get_by_text('年度',exact=True))
                field.locator('.ant-dropdown-trigger').first.hover(timeout=10000,force=True)
                menu=self.page.locator('.ant-dropdown:visible').last
                menu.wait_for(state='visible',timeout=5000)
                years=re.findall(r'\d{4}',menu.inner_text())
                params=history_request_params(matches[-1][2],years)
                self.page.mouse.move(0,0)
                def fetch_variant(selection):
                    return fetch_core_variant(self.page, {'path':module.endpoint_path,'params':selection,'headers':headers})
                variants=[]
                for currency in ('O','CNY','USD','JPY','HKD','GBP','EUR','CAD','AUD'):
                    for rate in ('1','2'):
                        if variants:self.page.wait_for_timeout(3100)
                        selection={**params,'displayCurrency':currency,'rateType':rate}
                        raw=fetch_variant(selection)
                        try:
                            _parse_matrix(raw,units=module.endpoint_path==MAIN_ENDPOINT)
                        except EnterpriseWarningError as error:
                            data=raw.get('data') if isinstance(raw.get('data'),dict) else {}
                            raise EnterpriseWarningError(error.code,{
                                'module':module.key,'currency':currency,'rate':rate,
                                'returncode':raw.get('returncode'),'response_sha256':_hash(raw),
                                'head_count':len(data.get('head') or []),
                                'row_lengths':sorted({len(row) for row in data.get('value') or [] if isinstance(row,list)}),
                            }) from error
                        variants.append((self.base+module.endpoint_path,raw,selection,'currency_variant'))
                return variants
            return responses
        raise EnterpriseWarningError("structure_changed")

    def menu(self, company_code: str) -> list[dict[str, Any]]:
        from playwright.sync_api import Error as PlaywrightError
        self._navigate_authenticated(f"{self.base}/detail/enterprise/financialStatements?code={company_code}&type=company")
        self.page.get_by_text("主要财务指标", exact=True).first.wait_for(timeout=15_000)
        seen = {name for _, name, *_ in MODULES if self.page.get_by_text(name, exact=True).count()}
        for group, stage in (("财务分析", "menu_group_analysis"), ("财务附注", "menu_group_notes")):
            target = self._menu_entry(group, '.pro-menu-submenu-title')
            try:
                if not target.evaluate("e=>e.closest('.ant-tree-treenode')?.classList.contains('ant-tree-treenode-switcher-open')"):
                    target.click(force=True)
            except PlaywrightError as error:
                try:
                    matches = target.count()
                    visible = target.first.is_visible() if matches else False
                except PlaywrightError:
                    matches, visible = None, None
                raise EnterpriseWarningError('browser_unavailable', {
                    'stage': stage, 'timeout': 'Timeout' in str(error).splitlines()[0],
                    'matches': matches, 'visible': visible,
                }) from None
            self.page.locator(".ant-tree-list-holder").evaluate_all("els => els.forEach(e => e.scrollTop = e.scrollHeight)")
            self.page.wait_for_timeout(800)
            seen.update(name for _, name, *_ in MODULES if self.page.get_by_text(name, exact=True).count())
        items = []
        for order, (key, name, category, endpoint, trace, params) in enumerate(MODULES):
            items.append({"key": key, "name": name, "category": category, "endpoint": endpoint,
                          "params": params, "order": order, "trace": trace})
        return items

    def close(self):
        self._finance_headers = {}
        self._legacy_headers = {}
        try:
            if self._context is not None:
                self._context.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
