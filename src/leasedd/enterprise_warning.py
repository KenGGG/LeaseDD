"""Thin 企业预警通 browser adapter and lossless response parsers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


SEARCH_ENDPOINT = "/finchinaAPP/v1/finchina-search/v1/multipleSearch"
MAIN_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getMainIndicators"
REPORT_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getThreeReports"
ANALYSIS_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/table/header-and-data"
NOTES_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data"
MAIN_BUSINESS_ENDPOINT = "/getData.action"
LEGACY_MATRIX_MODULES = {"main_business", "restricted_assets"}
FINANCIAL_CATEGORIES = {"indicators", "statements", "analysis", "notes"}
MODULES = (
    ("main_indicators", "主要财务指标", "indicators", MAIN_ENDPOINT, "Fin.Statement_MainInDicators", {}),
    ("balance_sheet", "资产负债表", "statements", REPORT_ENDPOINT, "Fin.Statement_Liabilities", {"statement_type": "balance_sheet"}),
    ("income_statement", "利润表", "statements", REPORT_ENDPOINT, "Fin.Statement_ProfitTable", {"statement_type": "income_statement"}),
    ("cash_flow_statement", "现金流量表", "statements", REPORT_ENDPOINT, "Fin.Statement_CashFlow", {"statement_type": "cash_flow_statement"}),
    ("per_share", "每股指标", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_PerIndex", {}),
    ("profitability", "盈利能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_Earning", {}),
    ("solvency", "偿债能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_SolvencyAbility", {}),
    ("operation", "营运能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_Operation", {}),
    ("growth", "成长能力", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_GrowthAbility", {}),
    ("cash_analysis", "现金流量", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_CashFlow", {}),
    ("dupont", "杜邦分析", "analysis", ANALYSIS_ENDPOINT, "Fin.Analysis_DuPont", {}),
    ("audit_report", "审计报告", "notes", NOTES_ENDPOINT, "Fin.Notes_AuditRep", {}),
    ("main_business", "主营构成", "notes", MAIN_BUSINESS_ENDPOINT, "Operation_MainBusinessComposition", {}),
    ("major_customers", "主要销售客户", "notes", NOTES_ENDPOINT, "Fin.Notes_MainCustomers", {}),
    ("major_suppliers", "主要供应商", "notes", NOTES_ENDPOINT, "Fin.Notes_MainSuppliers", {}),
    ("cash_notes", "货币资金", "notes", NOTES_ENDPOINT, "Fin.Notes_Cash", {}),
    ("inventory_notes", "存货", "notes", NOTES_ENDPOINT, "Fin.Notes_Inventory", {}),
    ("restricted_assets", "受限资产", "notes", MAIN_BUSINESS_ENDPOINT, "Fin.Notes_FinRestrictedAssets", {}),
    ("finance_costs", "财务费用", "notes", NOTES_ENDPOINT, "Fin.Notes_Fincosts", {}),
    ("nonrecurring_gains_losses", "非经常性损益", "notes", NOTES_ENDPOINT, "Fin.Notes_FinExtOrdItem", {}),
    ("long_term_receivables", "长期应收款", "notes", NOTES_ENDPOINT, "Fin.Notes_longTermReceivable",
     {"child_type": "notes_longTermReceivable"}),
)


class EnterpriseWarningError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


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
        self.session_factory = session_factory or _PlaywrightSession

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
            if module.key in LEGACY_MATRIX_MODULES:
                candidates = [self._parts(item) for item in responses if module.endpoint_path in item[0]
                              and isinstance(item[1].get("data"), dict)
                              and all(key in item[1]["data"] for key in ("head", "key", "value"))]
                if not candidates:
                    raise EnterpriseWarningError("structure_changed")
                url, raw, captured_params = candidates[-1]
            else:
                url, raw, captured_params = self._match(responses, module.endpoint_path)
            query = {key: values if len(values) > 1 else values[0] for key, values in parse_qs(urlparse(url).query).items()}
            params = {**module.request_params, **captured_params, **query}
            if params.get("unitCode") == "4": params["unit"] = "万元"
            if params.get("mergeRange") == "1": params["mergeRange"] = "consolidated"
            collected_module = replace(module, request_params=params)
            parser = parse_notes if module.key == "long_term_receivables" and isinstance(raw.get("data"), dict) else _parser(collected_module)
            parsed = parser(raw)
            return CollectedModule(collected_module, raw, parsed, _hash(raw))
        finally:
            session.close()


class _PlaywrightSession:
    """Small browser boundary; authentication remains inside the persistent profile."""

    def __init__(self):
        profile = os.getenv("QYJ_PROFILE_DIR")
        if not profile:
            raise EnterpriseWarningError("profile_missing")
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            profile, executable_path=os.getenv("QYJ_CHROME_EXECUTABLE", "/usr/bin/google-chrome"), headless=True,
            ignore_default_args=["--enable-automation", "--password-store=basic", "--use-mock-keychain"],
        )
        self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self.base = os.getenv("QYJ_BASE_URL", "https://www.qyyjt.cn")

    def _capture(self, action: Callable[[], None], *, wait_ms: int = 1500) -> list[tuple]:
        captured = []
        def record(response):
            try:
                if "finchinaAPP" in response.url or "getData.action" in response.url or "login" in response.url.lower():
                    query = {key: values if len(values) > 1 else values[0]
                             for key, values in parse_qs(urlparse(response.url).query).items()}
                    try:
                        post_data = response.request.post_data_json
                    except Exception:
                        post_data = None
                    params = {**(post_data if isinstance(post_data, dict) else {}), **query}
                    captured.append((response.url, response.json(), params))
            except Exception:
                pass
        self.page.on("response", record)
        action()
        self.page.wait_for_timeout(wait_ms)
        self.page.remove_listener("response", record)
        return captured

    def _menu_item(self, name: str):
        exact_name = re.compile(f"^{re.escape(name)}$")
        holder = self.page.locator(".ant-tree-list-holder")
        for ratio in (0, 0.25, 0.5, 0.75, 1):
            item = self.page.locator(".pro-menu-item").filter(has_text=exact_name)
            if item.count():
                return item.last
            holder.evaluate_all(
                "(els, ratio) => els.forEach(e => e.scrollTop = (e.scrollHeight - e.clientHeight) * ratio)",
                ratio,
            )
            self.page.wait_for_timeout(250)
        raise EnterpriseWarningError("structure_changed")

    def perform(self, action: str, **kwargs) -> list[tuple[str, dict[str, Any]]]:
        if action == "search":
            def run():
                self.page.goto(self.base, wait_until="domcontentloaded")
                trigger = self.page.locator("input[readonly][placeholder*='公司']").first
                if trigger.count():
                    trigger.click()
                box = self.page.locator("input:not([readonly])[placeholder*='企业']").last
                box.fill(kwargs["name"])
            return self._capture(run)
        if action == "collect":
            module = kwargs["module"]
            def run():
                self.page.goto(f"{self.base}/detail/enterprise/financialStatements?code={kwargs['company_code']}&type=company", wait_until="domcontentloaded")
                if module.category in ("analysis", "notes"):
                    self.page.get_by_text("财务分析" if module.category == "analysis" else "财务附注", exact=True).click(force=True)
                    self.page.wait_for_timeout(500)
                item = self._menu_item(module.name)
                item.click(force=True)
                if module.key == "long_term_receivables":
                    child_type = module.request_params["child_type"]
                    self.page.evaluate(
                        "async ([code, child]) => fetch(`/finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data?child_type=${child}&code=${code}&type=company`).then(r => r.json())",
                        [kwargs["company_code"], child_type],
                    )
            return self._capture(run, wait_ms=5000 if module.key == "main_business" else 2500)
        raise EnterpriseWarningError("structure_changed")

    def menu(self, company_code: str) -> list[dict[str, Any]]:
        self.page.goto(f"{self.base}/detail/enterprise/financialStatements?code={company_code}&type=company", wait_until="domcontentloaded")
        self.page.get_by_text("主要财务指标", exact=True).first.wait_for(timeout=15_000)
        seen = {name for _, name, *_ in MODULES if self.page.get_by_text(name, exact=True).count()}
        for group in ("财务分析", "财务附注"):
            self.page.get_by_text(group, exact=True).click(force=True)
            self.page.locator(".ant-tree-list-holder").evaluate_all("els => els.forEach(e => e.scrollTop = e.scrollHeight)")
            self.page.wait_for_timeout(800)
            seen.update(name for _, name, *_ in MODULES if self.page.get_by_text(name, exact=True).count())
        items = []
        for order, (key, name, category, endpoint, trace, params) in enumerate(MODULES):
            items.append({"key": key, "name": name, "category": category, "endpoint": endpoint,
                          "params": params, "order": order, "trace": trace})
        return items

    def close(self):
        self._context.close()
        self._playwright.stop()
