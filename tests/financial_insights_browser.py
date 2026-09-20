"""Exercise the deployed UI with synthetic authorized-project API responses."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from leasedd.financial_analytics import financial_analytics
from leasedd.financial_notes import index_notes, note_blocks, notes_matrix
from test_financial_insights import fixture, MARKDOWN

OUT=Path('runtime/acceptance/financial-insights');OUT.mkdir(parents=True,exist_ok=True)
statements=fixture()
for s in statements:
    for i in s['items']:
        i.update(source_text=i['source_name']+' '+i['raw_value'],confirmation_reason=None)
notes=index_notes(MARKDOWN,'doc','conversion')
for n in notes:n.update(markdown_sha256='a'*64,report_end='2026-06-30')
project={'id':'insights-fixture','name':'财务栏目合成验收','revision':1,'metrics':{},'metrics_current':False,'section_current':False,'production_template_status':'synthetic','members':[{'user_id':'writer','username':'测试编制员','role':'writer'}]}
user={'id':'writer','username':'测试编制员','admin':False,'csrf_token':'fixture'}
docs=[{'id':'doc','name':'合成半年报.pdf','sha256':'a'*64,'model_allowed':True,'parse_state':'completed'}]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/google-chrome')
    page=browser.new_page(viewport={'width':1600,'height':1100})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route_api(route):
        path=route.request.url.split('/api',1)[1]
        data=None
        if path=='/me':data=user
        elif path=='/projects':data=[project]
        elif path=='/projects/insights-fixture':data=project
        elif path.endswith('/documents'):data=docs
        elif path.endswith('/facts'):data={'facts':[],'history':[]}
        elif path.endswith('/financial-statements'):data=statements
        elif path.endswith('/financial-analytics'):data=financial_analytics(statements)
        elif path.endswith('/section'):data={'version':0,'draft':None,'current':False,'input_hash':''}
        elif path.endswith(('/tasks','/exports')):data=[]
        elif path.endswith('/financial-notes') or '/financial-notes?' in path:
            from urllib.parse import parse_qs,urlsplit
            from leasedd.financial_notes import CATEGORIES
            q=parse_qs(urlsplit(route.request.url).query).get('q',[''])[0]
            data={'categories':list(CATEGORIES),'notes':[{k:v for k,v in n.items() if k!='text'} for n in notes if q in n['text']]}
        elif '/financial-notes-matrix?' in path:
            from urllib.parse import parse_qs,urlsplit
            args=parse_qs(urlsplit(route.request.url).query)
            data=notes_matrix(notes,args['category'][0],args.get('scope',['consolidated'])[0])
        elif '/financial-notes/' in path:
            n=next(n for n in notes if n['id']==path.rsplit('/',1)[1])
            data={**n,'blocks':note_blocks(n['text']),'lines':n['text'].splitlines()}
        elif '/financial-items/' in path and path.endswith('/source'):
            iid=path.split('/financial-items/')[1].split('/source')[0]
            i=next(i for s in statements for i in s['items'] if i['id']==iid)
            data={'start_line':10,'end_line':10,'lines':[i['source_text']]}
        if data is None:raise AssertionError('Unexpected request '+path)
        route.fulfill(json=data)
    page.route('**/api/**',route_api)
    page.goto(os.getenv('LEASEDD_BROWSER_URL','http://172.30.10.150:5173'))
    page.get_by_role('button').filter(has_text=project['name']).click()
    page.get_by_role('button',name='财务核对',exact=True).click()
    page.get_by_role('button',name='主要财务指标',exact=True).click()
    table=page.locator('.finance-matrix')
    row=table.get_by_role('row').filter(has=page.get_by_role('rowheader',name='销售毛利率',exact=False))
    expect(row).to_contain_text('40.00')
    row.get_by_role('button').first.click()
    evidence=page.get_by_label('指标计算依据')
    expect(evidence).to_contain_text('营业收入 − 营业成本')
    evidence.get_by_role('button').filter(has_text='revenue').first.click()
    page.get_by_role('dialog').last.get_by_role('button',name='查看来源原文').click()
    expect(page.get_by_role('dialog').last).to_contain_text('revenue 1000')
    page.get_by_role('button',name='关闭财务来源').click()
    evidence.get_by_role('button',name='关闭',exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('button',name='导出 CSV').click()
    download.value.save_as(str(OUT/'metrics.csv'))
    page.screenshot(path=str(OUT/'metrics.png'),full_page=True)
    page.get_by_text('更多操作',exact=True).click()
    expect(page.get_by_label('导入事实 JSON')).to_have_count(1)
    page.get_by_role('button',name='财务分析',exact=True).click()
    page.get_by_role('button',name='成长能力',exact=True).click()
    growth=page.locator('.finance-matrix').get_by_role('row').filter(has=page.get_by_role('rowheader',name='净利润(%)',exact=True))
    expect(growth).to_contain_text('600.00')
    growth.get_by_role('button').first.click()
    expect(page.get_by_label('指标计算依据')).to_contain_text('|上年同期|')
    page.get_by_label('指标计算依据').get_by_role('button',name='关闭',exact=True).click()
    page.get_by_role('button',name='财务附注',exact=True).click()
    page.get_by_role('button',name='货币资金',exact=True).click()
    page.get_by_text('查看原文',exact=True).click()
    page.locator('.finance-notes-index').get_by_role('button').filter(has_text='1、货币资金').click()
    reader=page.get_by_label('附注正文')
    expect(reader).to_contain_text('银行存款')
    expect(reader.locator('td[rowspan="2"]')).to_contain_text('银行存款')
    reader.get_by_role('button',name='关闭',exact=True).click()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUT/'mobile-notes.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2')
    assert not errors,errors
    (OUT/'result.json').write_text(json.dumps({'status':'passed','checks':['uploaded-statement-calculation','formula-and-source','csv','compact-reference-layout','negative-base-growth','notes-table-spans','legacy-import-access','mobile-width'],'console_errors':errors},ensure_ascii=False,indent=2))
    browser.close()
print('financial insights browser acceptance passed')
