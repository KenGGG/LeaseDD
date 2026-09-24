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
        heading = page.locator('.finance-heading').bounding_box()
        toolbar = page.locator('.enterprise-reference-toolbar').bounding_box()
        assert toolbar['y'] >= heading['y'] + heading['height'] - 2
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


def test_legacy_note_prompts_project_member_to_update_from_overview(monkeypatch):
    old = {**MODULE, 'parsed_payload': {
        **MODULE['parsed_payload'],
        'metadata': {'report': ['20251231'], 'precise_record': False},
    }}
    monkeypatch.setattr(__import__(__name__), 'MODULE', old)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
        page = browser.new_page(viewport={'width': 1600, 'height': 900})
        page.route('**/api/**', serve)
        page.goto(os.getenv('LEASEDD_BROWSER_URL', 'http://172.30.10.150:5173'))
        page.get_by_role('button', name='附注测试项目').click()
        page.get_by_role('button', name='财务核对', exact=True).click()
        page.get_by_role('button', name='财务附注', exact=True).click()
        page.get_by_role('button', name='⊞ 应收账款').click()
        page.get_by_role('button', name='前五名应收账款').click()
        alert = page.get_by_role('alert')
        assert '项目概览' in alert.inner_text()
        assert '企业预警通更新数据' in alert.inner_text()
        assert '管理员' not in alert.inner_text()
        browser.close()


def test_desktop_financial_table_matches_source_reading_area(monkeypatch):
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
        table_box = table.bounding_box()
        seventh_period = table.locator('thead th').nth(7).bounding_box()
        filters = page.locator('.enterprise-reference-filters').bounding_box()
        tools = page.locator('.enterprise-reference-tools').bounding_box()
        assert 200 <= nav_width <= 245
        assert 30 <= row_height <= 40
        assert page.get_by_role('button', name='报告期倒序', exact=True).count() == 1
        assert abs(filters['y'] - tools['y']) <= 4
        assert table_box['y'] <= 200
        assert seventh_period['x'] + seventh_period['width'] <= table_box['x'] + table_box['width'] + 2
        assert not page.locator('.finance-page .project-title').is_visible()
        assert '附注测试项目' in page.locator('.finance-mode .breadcrumb').inner_text()
        assert page.locator("body").evaluate("element => element.scrollWidth") <= 2048
        page.screenshot(path='/tmp/leasedd-main-toolbar-fixture.png', full_page=True)
        browser.close()


def test_analysis_toolbar_omits_source_absent_hide_empty_control(monkeypatch):
    monkeypatch.setattr(__import__(__name__), 'MODULE', {
        'module_key': 'per_share', 'module_name': '每股指标', 'category': 'analysis',
        'state': 'completed', 'response_sha256': 'c' * 64,
        'request_params': {'unit': '万元'}, 'raw_payload': {},
        'parsed_payload': {'periods': ['2026年中报', '2025年年报', '2024年年报',
                                       '2023年年报', '2022年年报', '2021年年报'], 'rows': [
            {'name': '上市公司披露', 'value': 'group', 'highlight': True,
             'values': [None] * 6, 'children': [
                 {'name': '基本每股收益(元)', 'value': 'eps', 'unit': '元',
                  'values': ['1.6300', '-2.9500', '-4.8100', '-5.8700', '14.2500', '8.9500'], 'children': []},
             ]},
        ]},
    })
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
        page = browser.new_page(viewport={'width': 1280, 'height': 720}, accept_downloads=True)
        page.route('**/api/**', serve)
        page.goto(os.getenv('LEASEDD_BROWSER_URL', 'http://172.30.10.150:5173'))
        page.get_by_role('button', name='附注测试项目').click()
        page.get_by_role('button', name='财务核对', exact=True).click()
        page.get_by_role('button', name='财务分析', exact=True).click()
        page.get_by_role('button', name='每股指标', exact=True).click()
        page.locator('.enterprise-source-table').wait_for()
        assert page.get_by_text('1.6300', exact=True).count() == 1
        assert page.locator('.enterprise-reference-tools').get_by_text('隐藏空行').count() == 0
        report_select = page.locator('details.reference-select').first
        report_select.locator('.reference-select-arrow').click()
        assert report_select.locator('.reference-select-options').get_by_role('button', name='确定').count() == 1
        report_select.locator('.reference-select-arrow').click()
        table = page.locator('.enterprise-source-table')
        table_box = table.bounding_box()
        sixth_period = table.locator('thead th').nth(6).bounding_box()
        assert table_box['y'] <= 190
        assert sixth_period['x'] + sixth_period['width'] <= table_box['x'] + table_box['width'] + 2
        page.get_by_role('button', name='报告期降序').click()
        assert table.locator('thead th').nth(1).inner_text() == '2021年年报'
        assert table.locator('thead th').nth(6).inner_text() == '2026年中报'
        assert page.get_by_role('button', name='报告期正序').count() == 1
        with page.expect_download() as event:
            page.get_by_role('button', name='导出Excel').click()
        book = openpyxl.load_workbook(BytesIO(event.value.path().read_bytes()), read_only=True)
        assert list(book.active.values)[0] == ('报告期', '2021年年报', '2022年年报',
                                                '2023年年报', '2024年年报', '2025年年报', '2026年中报')
        book.close()
        page.screenshot(path='/tmp/leasedd-per-share-toolbar-fixture.png', full_page=False)
        browser.close()


def test_cash_notes_preserve_source_values_and_five_period_reading_width(monkeypatch):
    monkeypatch.setattr(__import__(__name__), 'MODULE', {
        'module_key': 'cash_notes', 'module_name': '货币资金', 'category': 'notes',
        'state': 'completed', 'response_sha256': 'd' * 64,
        'request_params': {'child_type': 'notes_MonetaryResources'}, 'raw_payload': {},
        'parsed_payload': {
            'head': ['项目名称', '现金', '银行存款', '财务公司存款', '其他货币资金', '合计'],
            'rows': [
                ['20260630', '2.87万', '15.73亿', '', '16.57亿', '32.29亿'],
                ['20251231', '1.83万', '7.39亿', '', '11.80亿', '19.19亿'],
                ['20241231', '2.39万', '19.58亿', '', '10.78亿', '30.36亿'],
                ['20231231', '8.78万', '20.40亿', '', '8.24亿', '28.64亿'],
                ['20221231', '6.47万', '22.81亿', '', '12.32亿', '35.13亿'],
                ['20211231', '7.90万', '12.63亿', '', '6.03亿', '18.66亿'],
            ],
            'metadata': {'leftTreeShow': True},
        },
    })
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        page.route('**/api/**', serve)
        page.goto(os.getenv('LEASEDD_BROWSER_URL', 'http://172.30.10.150:5173'))
        page.get_by_role('button', name='附注测试项目').click()
        page.get_by_role('button', name='财务核对', exact=True).click()
        page.get_by_role('button', name='财务附注', exact=True).click()
        page.get_by_role('button', name='货币资金', exact=True).click()
        table = page.locator('.enterprise-source-table')
        table.wait_for()
        assert page.get_by_role('button', name='报告期倒序').count() == 0
        assert table.locator('tbody tr').count() == 4
        assert '2.87万' in table.locator('tbody tr').first.inner_text()
        assert '15.73亿' in table.locator('tbody tr').nth(1).inner_text()
        first_col = table.locator('thead th').first.bounding_box()
        first_header_style = table.locator('thead th').first.evaluate('(element) => ({color:getComputedStyle(element).color,align:getComputedStyle(element).textAlign,padding:getComputedStyle(element).paddingLeft})')
        assert first_header_style['align'] == 'left'
        assert first_header_style['color'] == 'rgb(255, 122, 26)'
        assert float(first_header_style['padding'].replace('px', '')) >= 24
        fifth_period = table.locator('thead th').nth(5).bounding_box()
        sixth_period = table.locator('thead th').nth(6).bounding_box()
        right = table.bounding_box()['x'] + table.bounding_box()['width']
        assert 300 <= first_col['width'] <= 330
        assert fifth_period['x'] + fifth_period['width'] <= right + 2
        assert sixth_period['x'] >= right - 2
        page.screenshot(path='/tmp/leasedd-cash-notes-width-fixture.png', full_page=False)
        page.get_by_role('button', name='移除最新筛选').click()
        assert table.locator('thead th').nth(1).inner_text() == '2025年年报'
        assert table.locator('thead th').filter(has_text='2026年中报').count() == 0
        report_select = page.locator('details.reference-select').first
        report_select.locator('.reference-select-arrow').click()
        assert report_select.locator('.reference-select-options').is_visible()
        assert report_select.locator('.reference-select-options button').count() == 0
        report_select.locator('.reference-select-options label').filter(has_text='中报').locator('input').check()
        assert table.locator('thead th').filter(has_text='2026年中报').count() == 1
        browser.close()


def test_financial_expense_note_does_not_invent_report_sort(monkeypatch):
    monkeypatch.setattr(__import__(__name__), 'MODULE', {
        'module_key': 'finance_costs', 'module_name': '财务费用', 'category': 'notes',
        'state': 'completed', 'response_sha256': 'e' * 64,
        'request_params': {'child_type': 'notes_FinancialExpenses'}, 'raw_payload': {},
        'parsed_payload': {
            'head': ['项目名称', '利息支出', '减：利息收入', '合计'],
            'rows': [['20260630', '1.22亿', '-654.91万', '1.27亿'],
                     ['20251231', '1.94亿', '-1,726.14万', '1.88亿']],
            'metadata': {'level': ['0', '1', '1', '1']},
        },
    })
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        page.route('**/api/**', serve)
        page.goto(os.getenv('LEASEDD_BROWSER_URL', 'http://172.30.10.150:5173'))
        page.get_by_role('button', name='附注测试项目').click()
        page.get_by_role('button', name='财务核对', exact=True).click()
        page.get_by_role('button', name='财务附注', exact=True).click()
        page.get_by_role('button', name='财务费用', exact=True).click()
        table = page.locator('.enterprise-source-table')
        table.wait_for()
        assert page.get_by_role('button', name='报告期倒序').count() == 0
        assert table.locator('tbody tr').nth(1).locator('td').first.inner_text() == '-654.91万'
        page.screenshot(path='/tmp/leasedd-financial-expense-toolbar-fixture.png', full_page=False)
        browser.close()


def test_major_customer_record_columns_and_export_match_source_reading_area(monkeypatch):
    company_code = '82544731E821017487F99C9A794EF6E9'
    monkeypatch.setattr(__import__(__name__), 'MODULE', {
        'module_key': 'major_customers', 'module_name': '主要销售客户', 'category': 'notes',
        'state': 'completed', 'response_sha256': 'f' * 64,
        'request_params': {}, 'raw_payload': {},
        'parsed_payload': {
            'head': [['客户名称', '宁德时代新能源科技股份有限公司', '第二名', '合计']],
            'rows': [[['销售额', '88.08亿', '53.12亿', '163.49亿'],
                      ['占销售总额比例', '51.90%', '31.30%', '96.32%']]],
            'metadata': {'report': ['20231231'], 'itcode': [['', company_code, '', '']]},
        },
    })
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        page.route('**/api/**', serve)
        page.goto(os.getenv('LEASEDD_BROWSER_URL', 'http://172.30.10.150:5173'))
        page.get_by_role('button', name='附注测试项目').click()
        page.get_by_role('button', name='财务核对', exact=True).click()
        page.get_by_role('button', name='财务附注', exact=True).click()
        page.get_by_role('button', name='主要销售客户', exact=True).click()
        table = page.locator('.enterprise-record-table .finance-matrix')
        table.wait_for()
        widths = [cell.bounding_box()['width'] for cell in table.locator('thead th').all()]
        header_style = table.locator('thead th').first.evaluate('(element) => ({color:getComputedStyle(element).color,align:getComputedStyle(element).textAlign})')
        assert header_style == {'color':'rgb(255, 122, 26)', 'align':'left'}
        section_weight = table.locator('tbody .enterprise-section-row th').first.evaluate('(element) => getComputedStyle(element).fontWeight')
        assert section_weight == '400'
        assert 300 <= widths[0] <= 340
        assert 120 <= widths[1] <= 170
        assert 120 <= widths[2] <= 170
        assert widths[3] >= 300
        label_padding = float(table.locator('tbody tr').nth(1).locator('th').first.evaluate('(element) => getComputedStyle(element).paddingLeft').replace('px', ''))
        assert 24 <= label_padding <= 34
        assert page.get_by_role('button', name='导出Excel').bounding_box()['y'] <= page.locator('.finance-heading h2').bounding_box()['y'] + 18
        assert table.bounding_box()['y'] <= 160
        assert '88.08亿' in table.locator('tbody').inner_text()
        assert '96.32%' in table.locator('tbody').inner_text()
        linked = table.get_by_role('link', name='宁德时代新能源科技股份有限公司')
        assert linked.get_attribute('href') == 'https://www.qyyjt.cn/detail/enterprise/overview?type=company&code='+company_code
        assert linked.evaluate('(element) => getComputedStyle(element).color') == 'rgb(22, 119, 255)'
        assert table.get_by_role('link', name='第二名').count() == 0
        with page.expect_download() as event:
            page.get_by_role('button', name='导出Excel').click()
        book = openpyxl.load_workbook(BytesIO(event.value.path().read_bytes()), read_only=True)
        assert book.active.max_column == 3
        book.close()
        page.screenshot(path='/tmp/leasedd-major-customer-layout-fixture.png', full_page=False)
        browser.close()
