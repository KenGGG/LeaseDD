"""Read-only browser acceptance against locally reconciled uploaded PDFs.
Requires tests/reconcile_full_financial.py artifacts, never changes projects.
"""
import json,os
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright,expect
from leasedd.financial_notes import index_notes,note_blocks,notes_matrix
from leasedd.statement_tables import report_end

OUT=Path('runtime/acceptance/full-reconciliation/browser');OUT.mkdir(parents=True,exist_ok=True)
DATA=Path('runtime/acceptance/full-reconciliation')
live=json.loads((DATA/'live-before.json').read_text())
statements=json.loads((DATA/'statements-after.json').read_text())
analytics=json.loads((DATA/'analytics-after.json').read_text())
docs=[dict(id=d['id'],name=d['name'],sha256=d['original_sha256'],model_allowed=False,parse_state='completed') for d in live['documents']]
notes=[]
for d in live['documents']:
 for note in index_notes(d['markdown'],d['id'],d['conversion_id']):note.update(report_end=report_end(d['markdown']),markdown_sha256=d['markdown_sha256']);notes.append(note)
project={'id':'reference-readonly','name':'铭普光磁','revision':1,'metrics':{},'metrics_current':False,'section_current':False,'production_template_status':'synthetic','members':[{'user_id':'reviewer','username':'只读验收','role':'reviewer'}]}
user={'id':'reviewer','username':'只读验收','admin':False,'csrf_token':'fixture'}
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/google-chrome')
 page=browser.new_page(viewport={'width':1600,'height':1000});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route_api(route):
  parsed=urlsplit(route.request.url);path=parsed.path.split('/api',1)[1];q=parse_qs(parsed.query);data=None
  assert route.request.method=='GET','Read-only browser made a write'
  if path=='/me':data=user
  elif path=='/projects':data=[project]
  elif path=='/projects/reference-readonly':data=project
  elif path.endswith('/documents'):data=docs
  elif path.endswith('/facts'):data={'facts':[],'history':[]}
  elif path.endswith('/financial-statements'):data=statements
  elif path.endswith('/financial-analytics'):data=analytics
  elif path.endswith('/section'):data={'version':0,'draft':None,'current':False,'input_hash':''}
  elif path.endswith(('/tasks','/exports')):data=[]
  elif path.endswith('/financial-notes'):data={'notes':[{k:v for k,v in n.items() if k!='text'} for n in notes],'categories':[]}
  elif path.endswith('/financial-notes-matrix'):
   selected=[n for n in notes if not q.get('document_id') or n['document_id']==q['document_id'][0]]
   data=notes_matrix(selected,q['category'][0],q.get('scope',['consolidated'])[0])
  elif '/financial-notes/' in path:
   n=next(n for n in notes if n['id']==path.rsplit('/',1)[1]);data={**n,'blocks':note_blocks(n['text']),'lines':n['text'].splitlines()}
  elif '/financial-items/' in path and path.endswith('/source'):
   iid=path.split('/financial-items/')[1].split('/')[0];i=next(i for s in statements for i in s['items'] if i['id']==iid)
   data={'start_line':i['source_start_line'],'end_line':i['source_end_line'],'lines':i['source_text'].splitlines()}
  assert data is not None,path
  route.fulfill(json=data)
 page.route('**/api/**',route_api)
 page.goto(os.getenv('LEASEDD_BROWSER_URL','http://172.30.10.150:5173'))
 page.get_by_role('button').filter(has_text=project['name']).click()
 page.get_by_role('button',name='财务核对',exact=True).click()
 selector=page.get_by_label('财务主体口径')
 consolidated=selector.locator('option').filter(has_text='合并报表').first.get_attribute('value')
 selector.select_option(consolidated)
 table=page.locator('.finance-matrix')
 expect(table.locator('thead')).not_to_contain_text('2023-01-01')
 expect(table.locator('thead').get_by_role('columnheader').filter(has_text='2022年年报')).to_have_count(1)
 cash=table.get_by_role('row').filter(has=page.get_by_role('rowheader',name='货币资金',exact=True))
 cash.get_by_role('button').filter(has_text='23,236.11').click()
 expect(page.get_by_role('dialog')).to_contain_text('2023-01-01（年初余额')
 page.get_by_role('button',name='关闭财务来源').click()
 page.screenshot(path=str(OUT/'periods.png'),full_page=True)
 page.get_by_role('button',name='财务附注',exact=True).click()
 expect(page.get_by_label('财务附注对比表')).to_contain_text('100.00万')
 for name,value in [('主要销售客户','2.40亿'),('主要供应商','6,782.71万'),('预付款项','674.62万'),('应付账款','496.89万'),('受限资产','5.09亿'),('非经常性损益','552.08万'),('存货','2,650.24万')]:
  page.get_by_role('button',name=name,exact=True).click()
  expect(page.locator('.finance-content')).to_contain_text(value)
  page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
 page.get_by_role('button',name='应收账款',exact=True).click()
 page.get_by_role('button',name='前五名应收账款',exact=True).click()
 expect(page.get_by_label('财务附注明细表')).to_contain_text('6,830.02万')
 page.get_by_role('button',name='计提坏账的重大应收账款',exact=True).click()
 expect(page.get_by_label('财务附注明细表')).to_contain_text('337.98万')
 page.get_by_role('button',name='预付款项',exact=True).click()
 page.get_by_role('button',name='前五名预付款',exact=True).click()
 expect(page.get_by_label('财务附注明细表')).to_contain_text('109.00万')
 page.get_by_role('button',name='主要供应商',exact=True).click()
 detail=page.get_by_label('财务附注明细表')
 detail.get_by_role('button',name='6,782.71万',exact=True).click()
 expect(page.get_by_label('附注正文')).to_contain_text('67,827,061.26')
 page.get_by_label('附注正文').get_by_role('button',name='关闭',exact=True).click()
 with page.expect_download() as download:page.get_by_role('button',name='导出 CSV',exact=True).click()
 download.value.save_as(str(OUT/'suppliers.csv'))
 assert '18.93%' in (OUT/'suppliers.csv').read_text(encoding='utf-8-sig')
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
 page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
 assert not errors,errors
 (OUT/'browser-result.json').write_text(json.dumps({'status':'passed','write_requests':0,'console_errors':errors,'checks':['opening-balance-single-column','original-date-evidence','audit-fees','customers-suppliers','note-submenus','restricted-asset-wrapped-number','inventory-wrapped-decimal','source-dialog','record-csv-percent-units','mobile']},ensure_ascii=False,indent=2))
 browser.close()
print('Full financial browser acceptance passed')
