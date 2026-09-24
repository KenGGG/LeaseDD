"""Controlled browser check for the project-overview update flow; no external writes."""

import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


project = {
    'id': 'overview-fixture', 'name': '德方纳米', 'revision': 1, 'metrics': {},
    'metrics_current': False, 'section_current': False, 'production_template_status': 'synthetic',
    'members': [{'user_id': 'reviewer', 'username': '复核人员', 'role': 'reviewer'}],
}
user = {'id': 'reviewer', 'username': '复核人员', 'admin': False, 'csrf_token': 'fixture'}
binding = {'company_code': 'EE3886998BC906405B2889706A748814', 'company_name': '德方纳米', 'identity': {}}
state = {'import': {'id': 'previous', 'state': 'completed', 'quality_state': 'passed',
                    'module_status': {}, 'content_sha256': 'a' * 64,
                    'started_at': 1, 'completed_at': 2}, 'task': None, 'posted': []}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))

    def serve(route):
        path = urlsplit(route.request.url).path.split('/api', 1)[1]
        if route.request.method == 'POST':
            assert path == '/projects/overview-fixture/enterprise/import', path
            payload = route.request.post_data_json
            assert payload == {'company_code': binding['company_code'], 'company_name': binding['company_name']}
            state['posted'].append(payload)
            state['import'] = {**state['import'], 'id': 'new', 'state': 'queued', 'completed_at': None}
            state['task'] = {'id': 'new-task', 'kind': 'enterprise_import', 'mode': 'qyyjt', 'state': 'queued',
                             'attempts': 0, 'reason': None, 'quality_state': 'not_checked',
                             'review_state': 'pending', 'result': {}}
            route.fulfill(json=state['task'])
            return
        if path == '/me': data = user
        elif path == '/projects': data = [project]
        elif path == '/projects/overview-fixture': data = project
        elif path.endswith('/documents') or path.endswith('/financial-statements') or path.endswith('/exports'):
            data = []
        elif path.endswith('/facts'): data = {'facts': [], 'history': []}
        elif path.endswith('/section'): data = {'version': 0, 'draft': None, 'current': False, 'input_hash': ''}
        elif path.endswith('/tasks'): data = [state['task']] if state['task'] else []
        elif path.endswith('/enterprise'): data = {'source_type': 'enterprise_warning', 'binding': binding, 'import': state['import']}
        elif path.endswith('/enterprise/data'): data = {'import_id': state['import']['id'], 'modules': []}
        else: raise AssertionError(path)
        route.fulfill(json=data)

    page.route('**/api/**', serve)
    page.goto(os.getenv('LEASEDD_BROWSER_URL', 'http://172.30.10.150:5173'))
    page.get_by_role('button').filter(has_text='德方纳米').click()
    button = page.get_by_role('button', name='企业预警通更新数据')
    expect(button).to_be_enabled()
    button.click()
    expect(page.get_by_role('button', name='企业预警通更新中…')).to_be_disabled()
    expect(page.locator('.enterprise-overview-status')).to_contain_text('等待导入')
    assert len(state['posted']) == 1, state['posted']
    state['import'] = {**state['import'], 'state': 'completed', 'completed_at': 1780000000}
    state['task'] = {**state['task'], 'state': 'completed', 'quality_state': 'passed'}
    expect(button).to_be_enabled(timeout=8000)
    expect(page.locator('.enterprise-overview-status')).to_contain_text('最近更新')
    assert len(state['posted']) == 1, state['posted']
    state['import'] = {**state['import'], 'module_status': {'balance_sheet': {'state': 'failed', 'error': 'temporary'}}}
    page.get_by_role('button', name='财务核对', exact=True).click()
    page.locator('.enterprise-import-details summary').click()
    expect(page.get_by_role('button', name='重试失败模块')).to_be_visible()
    assert not errors, errors
    page.screenshot(path='/tmp/leasedd-enterprise-overview-update.png', full_page=True)
    browser.close()

print(json.dumps({'status': 'passed', 'post_count': len(state['posted']), 'page_errors': errors}, ensure_ascii=False))
