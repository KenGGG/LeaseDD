"""Thin 企业预警通 browser adapter and lossless response parsers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable


SEARCH_ENDPOINT = "/finchinaAPP/v1/finchina-search/v1/multipleSearch"
MAIN_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getMainIndicators"
REPORT_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/report/getThreeReports"
ANALYSIS_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/table/header-and-data"
NOTES_ENDPOINT = "/finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data"
FINANCIAL_CATEGORIES = {"indicators", "statements", "analysis", "notes"}


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
    periods = [row.get("reportDate") for row in values if isinstance(row, dict)]
    if len(periods) != len(values) or any(period is None for period in periods):
        raise EnterpriseWarningError("structure_changed")
    rows = []
    for item in fields:
        if not isinstance(item, dict) or not item.get("value"):
            raise EnterpriseWarningError("structure_changed")
        key = item["value"]
        rows.append({**item, "values": [row.get(key) for row in values]})
    return {"periods": periods, "rows": rows, "total": data.get("total")}


def parse_notes(payload: dict[str, Any]) -> dict[str, Any]:
    data = _data(payload, ("head", "value"))
    values = _not_empty(data["value"])
    if not isinstance(data["head"], list) or not isinstance(values, list) or any(not isinstance(row, list) for row in values):
        raise EnterpriseWarningError("structure_changed")
    return {"head": data["head"], "values": [row[1:] for row in values], "rows": values,
            "metadata": {key: value for key, value in data.items() if key not in ("head", "value")}}


def _hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _parser(module: EnterpriseModule) -> Callable[[dict[str, Any]], dict[str, Any]]:
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
    def _one(responses: list[tuple[str, dict[str, Any]]], endpoint: str) -> dict[str, Any]:
        matched = [payload for url, payload in responses if endpoint in url]
        if not matched and any("login" in url.lower() for url, _ in responses):
            raise EnterpriseWarningError("login_expired")
        if len(matched) != 1:
            raise EnterpriseWarningError("structure_changed")
        return matched[0]

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
            raw = self._one(session.perform("collect", company_code=company_code, module=module), module.endpoint_path)
            parsed = _parser(module)(raw)
            return CollectedModule(module, raw, parsed, _hash(raw))
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

    def _capture(self, action: Callable[[], None]) -> list[tuple[str, dict[str, Any]]]:
        captured = []
        def record(response):
            try:
                if "finchinaAPP" in response.url or "login" in response.url.lower():
                    captured.append((response.url, response.json()))
            except Exception:
                pass
        self.page.on("response", record)
        action()
        self.page.wait_for_timeout(1500)
        self.page.remove_listener("response", record)
        return captured

    def perform(self, action: str, **kwargs) -> list[tuple[str, dict[str, Any]]]:
        if action == "search":
            def run():
                self.page.goto(self.base, wait_until="domcontentloaded")
                box = self.page.locator("input[placeholder*='企业'], input[placeholder*='公司']").first
                box.fill(kwargs["name"])
                box.press("Enter")
            return self._capture(run)
        if action == "collect":
            module = kwargs["module"]
            def run():
                self.page.goto(f"{self.base}/detail/enterprise/financialStatements?code={kwargs['company_code']}&type=company", wait_until="domcontentloaded")
                self.page.get_by_text(module.name, exact=True).first.click()
            return self._capture(run)
        raise EnterpriseWarningError("structure_changed")

    def menu(self, company_code: str) -> list[dict[str, Any]]:
        self.page.goto(f"{self.base}/detail/enterprise/financialStatements?code={company_code}&type=company", wait_until="domcontentloaded")
        return self.page.evaluate("""() => Array.from(document.querySelectorAll('[data-module-key]')).map((node) => ({
          key: node.dataset.moduleKey, name: node.textContent.trim(), category: node.dataset.category,
          endpoint: node.dataset.endpoint, params: node.dataset.params ? JSON.parse(node.dataset.params) : {}
        }))""")

    def close(self):
        self._context.close()
        self._playwright.stop()
