"""Financial workspace UI contract tests using synthetic API responses only.

Uses the built WebUI, never writes a customer project or calls Agnes/QYJT.
Real project authorization and evidence hash tests remain in test_m2_api.py.
"""
import copy
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT=Path('runtime/acceptance/financial-workspace')
OUT.mkdir(parents=True,exist_ok=True)
PROJECT='financial-ui-synthetic'
user={'id':'writer','username':'合成验收编制员','admin':False,'csrf_token':'fixture'}
project={'id':PROJECT,'name':'财务展示验收（合成数据）','revision':1,'metrics':{},'metrics_current':False,'section_current':False,'production_template_status':'synthetic','members':[{'user_id':'writer','username':'合成验收编制员','role':'writer'}]}
docs=[{'id':'report','name':'合成年度财务报告.txt','sha256':'a'*64,'model_allowed':True,'parse_state':'text_available'}]
statements=[]
def add(period,kind='balance_sheet',scope='consolidated',currency='CNY',entity='合成制造有限公司',items=None):
 sid=str(len(statements))
 statement={'id':sid,'document_id':'report','statement_type':kind,'entity':entity,'scope':scope,'period':period,'period_normalized':period,'period_kind':'instant' if kind=='balance_sheet' else 'year','currency':currency,'raw_unit':'元','unit_scale':'1','state':'extracted','issues':[],'items':[]}
 for i,(concept,name,value,status) in enumerate(items or []):
  statement['items'].append({'id':sid+'-'+str(i),'concept':concept,'source_name':name,'raw_value':value,'raw_unit':'元','normalized_value':value,'status':status,'source_text':name+' '+value,'source_start_line':3,'source_end_line':3,'confirmation_reason':None})
 statements.append(statement)
 for index,item in enumerate(statement['items']):
  item.update(source_order=index,source_section='原表科目',source_cells=[item['source_name'],item['raw_value'],'80'],source_headers=['项目','本期','上期'])
 return statement
for year in range(2025,2019,-1):
 current=add(f'{year}-12-31',items=[('cash','货币资金',str((year-2015)*100000),'source_verified'),('inventory','存货','0','source_verified'),('total_current_assets','流动资产合计','2800000','source_verified'),('fixed_assets','固定资产','5000000','pending_confirmation'),('total_assets','资产总计','7800000','source_verified'),('short_term_borrowings','短期借款','1000000','source_verified'),('total_liabilities','负债合计','3500000','source_verified'),('total_equity','所有者权益合计','4300000','source_verified')])
 if year==2025:
  current.update(source_status='consistent',source_issues=[],formula_status='warning',semantic_review_count=1,manual_review_required=True,checks=[{'code':'assets_equal_liabilities_equity','status':'conflict','difference':'10000','tolerance':'0','missing_concepts':[],'involved_concepts':['total_assets','total_liabilities','total_equity'],'item_ids':[current['items'][4]['id'],current['items'][6]['id'],current['items'][7]['id']]}])
add('2025-12-31',items=[('inventory','存货','1','source_verified')])
add('2025-12-31',scope='parent',items=[('cash','货币资金','9990000','source_verified')])
add('2025-12-31',currency='USD',items=[('cash','货币资金','8880000','source_verified')])
add('2025-12-31',entity='另一主体',items=[('cash','货币资金','7770000','source_verified')])
add('2025-01-01/2025-12-31',kind='income_statement',items=[('revenue','营业收入','35000000','source_verified'),('net_profit','净利润','-1234500','source_verified')])
add('2025-01-01/2025-12-31',kind='cash_flow_statement',items=[('net_operating_cash_flow','经营活动现金流量净额','8000000','source_verified')])
source_requests=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path=os.getenv('LEASEDD_BROWSER_EXECUTABLE','/usr/bin/google-chrome'))
 page=browser.new_page(viewport={'width':1600,'height':1100})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route_api(route):
  path=route.request.url.split('/api',1)[1]
  data=None
  if path=='/me':data=user
  elif path=='/projects':data=[project]
  elif path==f'/projects/{PROJECT}':data=project
  elif path.endswith('/documents'):data=docs
  elif path.endswith('/facts'):data={'facts':[],'history':[]}
  elif path.endswith('/financial-statements'):data=statements
  elif path.endswith('/section'):data={'version':0,'draft':None,'current':False,'input_hash':''}
  elif path.endswith(('/tasks','/exports')):data=[]
  elif '/financial-items/' in path:
   iid=path.split('/financial-items/')[1].split('/')[0]
   item=next(i for s in statements for i in s['items'] if i['id']==iid)
   if path.endswith('/source'):
    source_requests.append(iid)
    data={'lines':[item['source_text']],'start_line':3,'end_line':3}
   elif path.endswith('/confirm'):
    payload=route.request.post_data_json
    assert payload['reason'].strip()
    item['status']='human_confirmed' if payload['decision']=='confirm' else 'human_rejected'
    item['confirmation_reason']=payload['reason']
    data=item
  if data is None:raise AssertionError('Unexpected fixture request '+path)
  route.fulfill(json=data)
 page.route('**/api/**',route_api)
 page.goto(os.getenv('LEASEDD_BROWSER_URL','http://127.0.0.1:5173'))
 page.get_by_role('button').filter(has_text=project['name']).click()
 page.get_by_role('button',name='财务核对',exact=True).click()
 table=page.locator('.finance-matrix')
 expect(table.get_by_role('columnheader',name='2025年年报',exact=False)).to_be_visible()
 expect(table.get_by_role('button',name='货币资金 2025年年报 100.00',exact=True)).to_be_visible()
 expect(table.get_by_role('button',name='存货 2025年年报 存在冲突',exact=True)).to_be_visible()
 expect(table.get_by_role('button',name='存货 2024年年报 0.00',exact=True)).to_be_visible()
 expect(page.get_by_text('资产负债表勾稽不一致',exact=True)).to_be_visible()
 page.get_by_text('资产负债表勾稽不一致',exact=True).click()
 expect(page.locator('.finance-diagnostics')).to_contain_text('差额 10000')
 expect(table.get_by_role('button',name='资产总计 2025年年报 780.00',exact=True)).to_be_visible()
 expect(table).not_to_contain_text('999.00')
 page.screenshot(path=str(OUT/'balance-sheet.png'),full_page=True)
 page.get_by_text('核对筛选',exact=True).click()
 page.get_by_role('button',name='存在冲突',exact=False).filter(has=page.locator('span')).click()
 expect(table.get_by_role('rowheader',name='货币资金',exact=True)).to_have_count(0)
 expect(table.get_by_role('rowheader',name='存货',exact=True)).to_be_visible()
 page.get_by_role('button',name='全部数值',exact=True).click()
 page.get_by_label('科目排列').select_option('standard')
 page.get_by_label('科目排列').select_option('source')
 page.get_by_label('显示单位',exact=True).select_option('元')
 expect(table.get_by_role('button',name='货币资金 2025年年报 1,000,000.00',exact=True)).to_be_visible()
 table.get_by_role('button',name='货币资金 2025年年报 1,000,000.00',exact=True).click()
 dialog=page.get_by_role('dialog')
 expect(dialog).to_contain_text('合成年度财务报告.txt')
 expect(dialog.locator('.finance-source-row')).to_contain_text('1000000')
 expect(dialog.locator('.finance-source-row')).to_contain_text('本期')
 dialog.get_by_role('button',name='查看来源原文').click()
 expect(dialog.locator('.finance-source')).to_contain_text('货币资金 1000000')
 expect(dialog.get_by_role('button',name='确认此值')).to_be_disabled()
 dialog.get_by_label('财务核对理由').fill('已对照合成原文和行号')
 dialog.get_by_role('button',name='确认此值').click()
 expect(dialog).to_contain_text('人工已确认')
 page.screenshot(path=str(OUT/'evidence.png'),full_page=True)
 dialog.get_by_role('button',name='关闭财务来源').click()
 expect(page.get_by_role('dialog')).to_have_count(0)
 page.get_by_role('button',name='已确认',exact=False).filter(has=page.locator('span')).click()
 expect(table.get_by_role('rowheader',name='货币资金',exact=True)).to_be_visible()
 expect(table.get_by_role('rowheader',name='存货',exact=True)).to_have_count(0)
 page.get_by_role('button',name='全部数值',exact=True).click()
 page.get_by_label('显示单位',exact=True).select_option('万元')
 page.get_by_label('搜索财务科目').fill('货币资金')
 expect(table.get_by_role('rowheader',name='存货',exact=True)).to_have_count(0)
 page.get_by_label('搜索财务科目').fill('')
 page.get_by_role('button',name='近 3 年',exact=True).click()
 expect(table.get_by_role('columnheader')).to_have_count(4)
 page.get_by_label('报告期倒序',exact=True).uncheck()
 expect(table.get_by_role('columnheader').nth(1)).to_contain_text('2023年年报')
 with page.expect_download() as download:
  page.get_by_role('button',name='导出 CSV',exact=True).click()
 csv_path=OUT/'financial-export.csv';download.value.save_as(str(csv_path))
 csv=csv_path.read_text(encoding='utf-8-sig')
 assert '来源对照' in csv and '存在冲突' in csv and '人工已确认' in csv
 page.get_by_role('button',name='全部',exact=True).click()
 page.get_by_label('财务主体口径').select_option(label='合成制造有限公司 · 母公司报表 · CNY')
 expect(table.get_by_role('button',name='货币资金 2025年年报 999.00',exact=True)).to_be_visible()
 page.get_by_label('财务主体口径').select_option(label='合成制造有限公司 · 合并报表 · CNY')
 page.get_by_role('button',name='利润表',exact=False).click()
 expect(table).to_contain_text('-123.45')
 page.get_by_role('button',name='现金流量表',exact=False).click()
 expect(table).to_contain_text('800.00')
 page.get_by_role('button',name='资产负债表',exact=False).click()
 page.get_by_label('隐藏空行',exact=True).uncheck()
 expect(table.get_by_role('rowheader',name='交易性金融资产',exact=True)).to_be_visible()
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'mobile overflow'
 page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
 # Reviewer never sees confirmation controls; real API restrictions are tested separately.
 project['members'][0]['role']='reviewer'
 page.reload()
 page.get_by_role('button').filter(has_text=project['name']).click()
 page.get_by_role('button',name='财务核对',exact=True).click()
 page.get_by_role('button',name='存货 2025年年报 存在冲突',exact=True).click()
 expect(page.get_by_role('button',name='确认此值')).to_have_count(0)
 expect(page.get_by_label('财务核对理由')).to_have_count(0)
 assert source_requests and not errors,errors
 browser.close()
result={'status':'passed','data':'synthetic API fixtures; no customer writes or model calls','checks':['multi-period matrix','zero vs missing','conflicts','source/formula diagnostics preserve values','unit precision','source drilldown','confirmation refresh','filtering','scope isolation','three statements','CSV provenance','mobile overflow','reviewer controls'],'page_errors':errors}
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
