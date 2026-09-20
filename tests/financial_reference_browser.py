"""Read-only browser acceptance against locally reconciled uploaded PDFs.
Requires tests/reconcile_financial_reference.py artifacts, never changes projects.
"""
import json,os
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright,expect
from leasedd.financial_notes import index_notes,note_blocks,notes_matrix
from leasedd.statement_tables import report_end

OUT=Path('runtime/acceptance/reference-parity');OUT.mkdir(parents=True,exist_ok=True)
statements=json.loads((OUT/'statements-local.json').read_text())
analytics=json.loads((OUT/'analytics-local.json').read_text())
half=statements[0]['document_id']
docs=[{'id':half,'name':'铭普光磁：2026年半年度报告.pdf','sha256':'a'*64,'model_allowed':False,'parse_state':'completed'},{'id':'annual','name':'铭普光磁：2025年年度报告.pdf','sha256':'b'*64,'model_allowed':False,'parse_state':'completed'}]
notes=[]
for did,file in [(half,'half-year-upload.md'),('annual','annual-upload.md')]:
 text=Path('runtime/reference/'+file).read_text()
 for note in index_notes(text,did,did):note.update(report_end=report_end(text),markdown_sha256='a'*64);notes.append(note)
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
 page.get_by_role('button',name='主要财务指标',exact=True).click()
 table=page.get_by_label('财务指标对比表')
 expect(table).to_contain_text('106,316.02')
 for row,value in [('净资产收益率(ROE)(%)','-2.49'),('速动比率(%)','64.44'),('每股净资产(元)','2.6043'),('EBITDA','6,990.58')]:
  r=table.get_by_role('row').filter(has=page.get_by_role('rowheader',name=row,exact=True));expect(r).to_contain_text(value)
 expect(table.locator('button small')).to_have_count(0)
 expect(page.locator('.finance-calculation')).to_have_count(0)
 expect(page.locator('.stagebar')).not_to_be_visible()
 presentation=table.locator('.finance-number').first.evaluate(r"""e=>{
  const s=getComputedStyle(e);
  const rgb=c=>c.match(/[\d.]+/g).slice(0,3).map(Number);
  const luminance=c=>rgb(c).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((v,n,i)=>v+n*[.2126,.7152,.0722][i],0);
  let ancestor=e,background='rgb(255, 255, 255)';
  while(ancestor){const c=getComputedStyle(ancestor).backgroundColor;if(c!=='rgba(0, 0, 0, 0)'&&c!=='transparent'){background=c;break}ancestor=ancestor.parentElement}
  const foreground=luminance(s.color),back=luminance(background);
  return {font_size:parseFloat(s.fontSize),font_family:s.fontFamily,color:s.color,background,
          contrast:(Math.max(foreground,back)+.05)/(Math.min(foreground,back)+.05)};
 }""")
 assert presentation['font_size']>=14 and presentation['contrast']>=4.5,presentation
 page.screenshot(path=str(OUT/'main-metrics.png'),full_page=True)
 table.get_by_role('button',name='每股净资产(元) 2026年中报 2.6043',exact=True).click()
 dialog=page.get_by_label('指标计算依据');expect(dialog).to_contain_text('期末普通股股份总数')
 dialog.get_by_role('button').filter(has_text='期末股份总数').click()
 source=page.get_by_role('dialog').last
 source.get_by_role('button',name='查看来源原文').click();expect(source).to_contain_text('235,009,062')
 source.get_by_role('button',name='关闭财务来源').click();dialog.get_by_role('button',name='关闭',exact=True).click()
 page.get_by_role('button',name='财务分析',exact=True).click()
 expect(table).to_contain_text('加权净资产收益率(ROE)(%)')
 page.screenshot(path=str(OUT/'analysis-profit.png'),full_page=True)
 page.get_by_role('button',name='营运能力',exact=True).click();expect(table).to_contain_text('207.56');expect(table).to_contain_text('48.35')
 page.get_by_role('button',name='财务附注',exact=True).click()
 note_table=page.get_by_label('财务附注对比表');expect(note_table).to_contain_text('2026-04-23');expect(note_table).to_contain_text('标准无保留')
 page.get_by_role('button',name='存货',exact=True).click();expect(note_table).to_contain_text('8,357.42万')
 page.screenshot(path=str(OUT/'notes-inventory.png'),full_page=True)
 r=note_table.get_by_role('row').filter(has=page.get_by_role('rowheader',name='在产品及半成品',exact=True));r.get_by_role('button').first.click()
 note_dialog=page.get_by_label('附注正文');expect(note_dialog).to_contain_text('半成品');expect(note_dialog.locator('td[rowspan="2"]')).to_have_count(1)
 note_dialog.get_by_role('button',name='关闭',exact=True).click()
 page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2')
 assert not errors,errors
 (OUT/'browser-result.json').write_text(json.dumps({'status':'passed','write_requests':0,'presentation':presentation,'console_errors':errors,'checks':['reference-main-rows','reported-weighted-roe','percentage-ratios','source-shares','collapsed-evidence','analysis-period-policy','audit-disclosure','inventory-classification','mobile-layout']},ensure_ascii=False,indent=2))
 browser.close()
print('reference financial browser acceptance passed')
