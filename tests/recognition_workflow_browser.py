"""Synthetic browser regression for Agnes recognition authorization and reprocessing."""
import json,os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect

OUT=Path('runtime/acceptance/recognition-workflow');OUT.mkdir(parents=True,exist_ok=True)
PROJECT='recognition-ui';DOC='recognized-doc';submitted=[]
user={'id':'writer','username':'合成编制员','admin':False,'csrf_token':'fixture'}
project={'id':PROJECT,'name':'语义识别流程验收','revision':2,'metrics':{},'metrics_current':False,'section_current':False,'production_template_status':'missing','members':[{'user_id':'writer','username':'合成编制员','role':'writer'}]}
doc={'id':DOC,'name':'合成财务报表.md','sha256':'a'*64,'model_allowed':True,'parse_state':'text_available'}
task={'id':'semantic-task','kind':'extract_finance','mode':'auto','state':'completed','attempts':1,'reason':None,'quality_state':'passed_with_gaps','review_state':'pending','result':{'document_id':DOC,'statement_count':2,'item_count':10,'pipeline_version':'agnes-semantic-v1','extraction_status':'semantic','manifest':{'quality_state':'passed_with_gaps','counts':{'VERIFIED':8,'UNMAPPED':1,'GAP':1},'issues':['missing_statement_types']},'coverage':None}}

with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path=os.getenv('LEASEDD_BROWSER_EXECUTABLE','/usr/bin/google-chrome'))
 page=browser.new_page(viewport={'width':1280,'height':900});errors=[]
 page.on('pageerror',lambda error:errors.append(str(error)))
 def api(route):
  path=urlsplit(route.request.url).path.removeprefix('/api')
  if route.request.method=='POST' and path==f'/projects/{PROJECT}/documents/recognize':
   submitted.append(route.request.post_data_json);route.fulfill(json={'queued':1,'skipped':0,'task_ids':['rerun']});return
  assert route.request.method=='GET',(route.request.method,path)
  data={'/me':user,'/projects':[project],f'/projects/{PROJECT}':project}.get(path)
  if path.endswith('/documents'):data=[doc]
  elif path.endswith('/facts'):data={'facts':[],'history':[]}
  elif path.endswith('/financial-statements'):data=[]
  elif path.endswith('/section'):data={'version':0,'draft':None,'current':False,'input_hash':''}
  elif path.endswith('/tasks'):data=[task]
  elif path.endswith('/exports'):data=[]
  assert data is not None,path
  route.fulfill(json=data)
 page.route('**/api/**',api)
 page.goto(os.getenv('LEASEDD_BROWSER_URL','http://127.0.0.1:5173'))
 page.get_by_role('button').filter(has_text=project['name']).click()
 page.get_by_role('button',name='资料与证据',exact=True).click()
 agnes=page.get_by_label('使用 Agnes 识别财务语义',exact=True)
 rerun=page.get_by_label('重新识别已完成资料',exact=True)
 select=page.get_by_label('选择 '+doc['name'],exact=True)
 expect(agnes).to_be_checked();expect(rerun).not_to_be_checked();expect(select).to_be_disabled()
 expect(page.get_by_text('识别结果：待核对 · 已核验 8 项 · 待核对/未匹配 2 项',exact=True)).to_be_visible()
 rerun.check();expect(select).to_be_enabled();select.check()
 page.get_by_role('button',name='批量识别（1）',exact=True).click()
 expect(page.locator('.alert.info')).to_contain_text('已提交 1 份资料识别任务。')
 assert submitted==[{'document_ids':[DOC],'model_allowed':True,'reprocess':True}],submitted
 assert not errors,errors
 page.screenshot(path=str(OUT/'recognition.png'),full_page=True)
 browser.close()
(OUT/'result.json').write_text(json.dumps({'status':'passed','payload':submitted[0],'errors':errors},ensure_ascii=False,indent=2))
print('Recognition workflow browser regression passed')
