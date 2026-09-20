"""Read-only visual smoke checks for every workspace page, using synthetic API data."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

OUT = Path('runtime/acceptance/ui-readability')
OUT.mkdir(parents=True, exist_ok=True)
user = dict(id='visual-writer', username='样式验收', admin=True, csrf_token='fixture')
project = dict(id='visual-project', name='铭普光磁（样式验收）', revision=3,
               metrics_current=True, section_current=True, production_template_status='synthetic',
               members=[dict(user_id=user['id'], username=user['username'], role='writer')],
               metrics={'liabilities_to_assets':dict(value='0.625', display_value='62.50%', status='valid', reason=None, input_fact_ids=[])})
section = dict(version=1, current=True, input_hash='fixture', draft=dict(
    section_id='finance', title='财务分析测试章节', input_hash='fixture', synthetic=True, table_id='finance',
    question_answers=[dict(question_id='Q1', status='answered', block_ids=['b1'])],
    blocks=[dict(block_id='b1', segments=[dict(type='text', text='根据已核对的资料，资产负债率为'),
                                           dict(type='metric', ref='liabilities_to_assets'),
                                           dict(type='text', text='。本段仅为界面验收合成内容。')])]))
docs = [dict(id='visual-document', name='铭普光磁：2026年半年度报告.pdf', sha256='a'*64, model_allowed=False, parse_state='text_available')]
results = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
    page = browser.new_page(viewport=dict(width=1600, height=1000))
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    authenticated = False

    def route_api(route):
        assert route.request.method == 'GET', 'Visual checks must never write project data'
        path = urlsplit(route.request.url).path.removeprefix('/api')
        if path == '/me':
            route.fulfill(status=200 if authenticated else 401, json=user if authenticated else {'detail':'authentication_required'})
            return
        data = {
            '/projects':[project], '/projects/visual-project':project, '/users':[user],
            '/settings/agnes':dict(base_url='https://example.invalid/v1',model='agnes-2.5-flash',credential_configured=False),
        }.get(path)
        if path.endswith('/documents'): data = docs
        elif path.endswith('/facts'): data = dict(facts=[], history=[])
        elif path.endswith('/financial-statements'): data = []
        elif path.endswith('/section'): data = section
        elif path.endswith('/tasks'): data = [dict(id='visual-task',kind='extract_finance',mode='auto',state='completed',attempts=1,reason=None,quality_state='passed',review_state='pending',result=dict(document_id=docs[0]['id'],statement_count=12,item_count=422))]
        elif path.endswith('/exports'): data = [dict(id='visual-export',sha256='b'*64,manifest=dict(input_hash='fixture'))]
        assert data is not None, path
        route.fulfill(json=data)

    page.route('**/api/**', route_api)

    def capture(name):
        for width, height in [(1600,1000),(1024,768),(390,844)]:
            page.set_viewport_size(dict(width=width,height=height))
            page.screenshot(path=str(OUT/f'{name}-{width}.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), (name,width,'page overflow')
            if name == 'documents':
                assert page.locator('.document-row .badge').evaluate('e => e.scrollWidth <= e.clientWidth + 2'), 'Document status is clipped'
            samples = page.locator('main h1, .login-side h2, .document-row strong, .report-paragraph, .form label, .button.primary, .page-title p').evaluate_all('''nodes => nodes.filter(e=>e.getClientRects().length).map(e=>{
                const s=getComputedStyle(e);return {text:e.textContent.slice(0,40),size:parseFloat(s.fontSize),color:s.color,background:s.backgroundColor};
            })''')
            assert all(s['size'] >= 13 for s in samples), (name, samples)
            results.append(dict(page=name,width=width,samples=samples))
        page.set_viewport_size(dict(width=1600,height=1000))

    page.goto(os.getenv('LEASEDD_BROWSER_URL','http://172.30.10.150:5173'))
    expect(page.get_by_role('heading',name='登录工作台')).to_be_visible()
    capture('login')
    page.locator('.login-side input').first.focus()
    page.keyboard.press('Tab')
    assert page.locator('input[type=password]').evaluate('e=>e===document.activeElement')
    authenticated = True
    page.reload()
    expect(page.get_by_role('heading',name='尽调项目',exact=True)).to_be_visible()
    capture('projects')
    page.get_by_role('button').filter(has_text=project['name']).click()
    expect(page.get_by_role('heading',name='下一步工作')).to_be_visible()
    capture('overview')
    for tab,name,heading in [('资料与证据','documents','项目资料 1'),('报告章节','section','章节编制'),('复核与导出','review','Word 待复核稿'),('账号与服务配置','admin','账号与服务配置')]:
        page.get_by_role('button',name=tab,exact=True).click()
        expect(page.get_by_role('heading',name=heading,exact=True)).to_be_visible()
        capture(name)
    assert not errors, errors
    (OUT/'browser-result.json').write_text(json.dumps(dict(status='passed',business_writes=0,errors=errors,results=results),ensure_ascii=False,indent=2))
    browser.close()
print('Whole-workspace readability browser acceptance passed (7 pages, 3 viewport sizes)')
