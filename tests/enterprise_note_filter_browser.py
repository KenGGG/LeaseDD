"""Browser check for the two source-filtered receivables note record pages."""

import os
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import openpyxl
from playwright.sync_api import sync_playwright

from leasedd.enterprise_export import export_enterprise_workbook


MODULE = {
    "module_key": "receivables_top_five", "module_name": "前五名应收账款", "category": "notes",
    "state": "completed", "response_sha256": "a" * 64,
    "request_params": {"menu_parent": "应收账款", "unit": "万元"}, "raw_payload": {},
    "parsed_payload": {
        "head": [["单位名称", "第一名"]] * 4,
        "rows": [
            [["期末余额", "68137.782993"]], [["期末余额", "59200.123456"]],
            [["期末余额", "40000.000000"]], [["期末余额", "30000.000000"]],
        ],
        "metadata": {"report": ["20251231", "20250630", "20231231", "20211231"],
                     "precise_record": True},
    },
}
PROJECT = {
    "id": "note-fixture", "name": "附注测试项目", "revision": 1, "metrics": {},
    "metrics_current": False, "section_current": False,
    "members": [{"user_id": "reviewer", "username": "附注验收", "role": "reviewer"}],
}


def serve(route):
    parsed = urlsplit(route.request.url)
    path = parsed.path
    assert route.request.method == "GET"
    query = parse_qs(parsed.query)
    if path.endswith("/enterprise/data") and query.get("export_format") == ["xlsx"]:
        content = export_enterprise_workbook(
            SimpleNamespace(**MODULE), report=query["report"][0],
            start=query.get("start", [""])[0], end=query.get("end", [""])[0],
            descending=query.get("descending", ["true"])[0] == "true",
            window_years=int(query.get("window_years", ["0"])[0]),
            unit=query.get("unit", ["万元"])[0], decimals=int(query.get("decimals", ["2"])[0]),
        )
        route.fulfill(body=content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return
    if path == "/api/me":
        value = {"id": "reviewer", "username": "附注验收", "admin": False, "csrf_token": "fixture"}
    elif path == "/api/projects":
        value = [PROJECT]
    elif path == "/api/projects/note-fixture":
        value = PROJECT
    elif path.endswith("/enterprise/data"):
        value = {"import_id": "import-1", "modules": [MODULE]}
    elif path.endswith("/enterprise"):
        value = {"source_type": "enterprise_warning", "binding": {"company_name": "附注测试项目"},
                 "import": {"id": "import-1", "state": "completed", "module_status": {}}}
    elif path.endswith("/facts"):
        value = {"facts": [], "history": []}
    elif path.endswith("/section"):
        value = {"version": 0, "draft": None, "current": False, "input_hash": ""}
    elif path.endswith(("/documents", "/financial-statements", "/tasks", "/exports")):
        value = []
    else:
        raise AssertionError(path)
    route.fulfill(json=value)


def test_note_record_screen_filter_and_excel_use_same_source_periods():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome")
        page = browser.new_page(viewport={"width": 1600, "height": 900}, accept_downloads=True)
        page.route("**/api/**", serve)
        page.goto(os.getenv("LEASEDD_BROWSER_URL", "http://172.30.10.150:5173"))
        page.get_by_role("button", name="附注测试项目").click()
        page.get_by_role("button", name="财务核对", exact=True).click()
        page.get_by_role("button", name="财务附注", exact=True).click()
        page.get_by_role("button", name="⊞ 应收账款").click()
        page.get_by_role("button", name="前五名应收账款").click()
        assert "68,137.78" in page.locator(".enterprise-record-table").inner_text()
        page.get_by_label("报告期筛选").click()
        page.locator(".reference-select-options label").filter(has_text="最新").locator("input").uncheck()
        page.locator(".reference-select-options label").filter(has_text="年报").locator("input").uncheck()
        page.locator(".reference-select-options label").filter(has_text="中报").locator("input").check()
        assert "59,200.12" in page.locator(".enterprise-record-table").inner_text()
        assert "68,137.78" not in page.locator(".enterprise-record-table").inner_text()
        page.get_by_label("显示单位").select_option("元")
        assert "592,001,234.56" in page.locator(".enterprise-record-table").inner_text()
        with page.expect_download() as event:
            page.get_by_role("button", name="导出Excel").click()
        book = openpyxl.load_workbook(BytesIO(event.value.path().read_bytes()), read_only=True)
        values = list(book.active.values)
        assert [row[0] for row in values if row[0] and "年" in str(row[0])] == ["2025年中报"]
        assert values[-1] == ("第一名", 592001234.56)
        book.close()
        browser.close()


def test_desktop_financial_table_keeps_source_readable_density(monkeypatch):
    periods = ["2026年中报", "2025年年报", "2025年三季报", "2024年年报",
               "2024年三季报", "2023年年报", "2023年三季报"]
    monkeypatch.setattr(
        __import__(__name__), "MODULE",
        {"module_key": "main_indicators", "module_name": "主要财务指标", "category": "indicators",
         "state": "completed", "response_sha256": "b" * 64,
         "request_params": {"unit": "万元"}, "raw_payload": {},
         "parsed_payload": {"periods": periods, "rows": [
             {"key": "dataType", "name": "报表类型", "values": ["合并期末"] * 7},
             {"key": "revenue", "name": "营业总收入", "unit": "万元",
              "values": ["1039981.78", "871649.24", "603612.55", "761294.12",
                         "653038.73", "1697250.89", "1430673.11"]},
         ]}},
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome")
        page = browser.new_page(viewport={"width": 2048, "height": 1132})
        page.route("**/api/**", serve)
        page.goto(os.getenv("LEASEDD_BROWSER_URL", "http://172.30.10.150:5173"))
        page.get_by_role("button", name="附注测试项目").click()
        page.get_by_role("button", name="财务核对", exact=True).click()
        page.get_by_role("button", name="主要财务指标", exact=True).click()
        first_row = page.locator(".enterprise-source-table .finance-matrix tbody tr").first
        first_row.wait_for()
        nav_width = page.locator(".enterprise-workspace .finance-nav").bounding_box()["width"]
        row_height = first_row.bounding_box()["height"]
        table = page.locator(".enterprise-source-table")
        overflow = table.evaluate("element => element.scrollWidth > element.clientWidth")
        assert nav_width >= 280
        assert row_height >= 44
        assert overflow
        assert page.locator("body").evaluate("element => element.scrollWidth") <= 2048
        browser.close()
