"""Run against an isolated local dev stack; never against customer projects."""
import hashlib,json,os,re,time,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

url=os.getenv('LEASEDD_BROWSER_URL','http://127.0.0.1:5173')
admin=os.getenv('LEASEDD_BROWSER_ADMIN','browser-admin')
password=os.getenv('LEASEDD_BROWSER_PASSWORD','browser-test-password-only')
suffix=str(int(time.time()));writer='writer-'+suffix;reviewer='reviewer-'+suffix
project_name='合成租赁项目 · 浏览器验收 '+suffix
out=Path('runtime/acceptance');out.mkdir(parents=True,exist_ok=True)
source=Path('fixtures/synthetic_statement.txt');source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
template=Path('src/leasedd/assets/synthetic_template.docx');template_sha=hashlib.sha256(template.read_bytes()).hexdigest()
with sync_playwright() as pw:
 launch={"headless":True}
 if os.getenv('LEASEDD_BROWSER_EXECUTABLE'):launch['executable_path']=os.environ['LEASEDD_BROWSER_EXECUTABLE']
 browser=pw.chromium.launch(**launch)
 page=browser.new_page(viewport={'width':1440,'height':1024},device_scale_factor=1,ignore_https_errors=os.getenv('LEASEDD_BROWSER_IGNORE_HTTPS_ERRORS')=='1')
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def login(name):
  page.get_by_label('账号',exact=True).fill(name)
  page.get_by_label('密码',exact=True).fill(password)
  page.get_by_role('button',name='登录',exact=True).click()
  expect(page.get_by_role('button',name='退出登录')).to_be_visible()
 def logout():
  page.get_by_role('button',name='退出登录').click()
  expect(page.get_by_role('heading',name='登录工作台')).to_be_visible()
 page.goto(url);login(admin)
 page.get_by_role('button',name='账号与服务配置').click()
 for name in [writer,reviewer]:
  page.get_by_label('账号',exact=True).fill(name)
  page.get_by_label('初始密码').fill(password)
  page.get_by_role('button',name='创建账号',exact=True).click()
  expect(page.locator('.user-list')).to_contain_text(name)
 page.get_by_label('项目名称',exact=True).fill(project_name)
 page.get_by_role('combobox',name='编制人员',exact=True).select_option(label=writer)
 page.get_by_role('combobox',name='独立审核人员',exact=True).select_option(label=reviewer)
 page.get_by_role('button',name='创建项目',exact=True).click()
 expect(page.get_by_role('status')).to_contain_text('项目已创建')
 logout();login(writer)
 page.get_by_role('button').filter(has_text=project_name).click()
 expect(page.get_by_role('heading',name=project_name)).to_be_visible()
 page.screenshot(path=str(out/'overview.png'),full_page=True)
 page.get_by_role('button',name='资料与证据',exact=True).click()
 page.get_by_label('上传资料').set_input_files(str(source))
 expect(page.get_by_text('synthetic_statement.txt',exact=True)).to_be_visible()
 page.get_by_role('button',name=re.compile('批量识别')).click()
 expect(page.get_by_text(re.compile('已转换 Markdown · 未调用 AI'))).to_be_visible(timeout=15000)
 body=page.locator('main').inner_text()
 document_id=re.search(r'文档 ID：([0-9a-f]{32})',body).group(1)
 expect(page.get_by_text('SHA256：'+source_sha)).to_be_visible()
 page.get_by_role('button',name='查看原文',exact=True).click()
 expect(page.get_by_text('total_assets: 100',exact=True)).to_be_visible()
 payload=json.loads(Path('fixtures/synthetic_facts.json').read_text());payload['document_id']=document_id
 facts_file=out/'browser-facts.json';facts_file.write_text(json.dumps(payload))
 page.get_by_role('button',name='财务核对',exact=True).click()
 page.get_by_role('button',name='主要财务指标',exact=True).click()
 page.get_by_text('更多操作',exact=True).click()
 page.get_by_label('导入事实 JSON').set_input_files(str(facts_file))
 expect(page.get_by_role('cell',name='资产总额',exact=True)).to_be_visible()
 page.get_by_role('button',name='计算当前事实',exact=True).click()
 expect(page.get_by_text('80.00%',exact=True)).to_be_visible()
 expect(page.get_by_text('30.00%',exact=True)).to_be_visible()
 expect(page.get_by_text('缺少存货数据',exact=True)).to_be_visible()
 page.screenshot(path=str(out/'finance.png'),full_page=True)
 page.get_by_role('button',name='报告章节',exact=True).click()
 page.get_by_role('button',name='生成测试章节',exact=True).click()
 expect(page.get_by_role('heading',name='财务分析测试章节',exact=True)).to_be_visible(timeout=15000)
 expect(page.get_by_text('80.00%',exact=True)).to_be_visible()
 page.get_by_role('button',name='复核与导出',exact=True).click()
 page.get_by_role('button',name='生成 Word',exact=True).click()
 expect(page.get_by_role('link',name='下载',exact=True)).to_be_visible(timeout=15000)
 with page.expect_download() as download:
  page.get_by_role('link',name='下载',exact=True).click()
 report=out/'report_review.docx';download.value.save_as(report)
 xml=zipfile.ZipFile(report).read('word/document.xml').decode()
 assert '<w:tbl>' in xml and '80.00%' in xml and '30.00%' in xml and '待复核' in xml and '{{' not in xml
 page.screenshot(path=str(out/'export.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 page.screenshot(path=str(out/'mobile.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'mobile_overflow'
 page.set_viewport_size({'width':1440,'height':1024})
 logout();login(reviewer)
 page.get_by_role('button').filter(has_text=project_name).click()
 expect(page.get_by_role('heading',name=project_name)).to_be_visible()
 page.get_by_role('button',name='财务核对',exact=True).click()
 expect(page.get_by_role('button',name='计算当前事实',exact=True)).to_have_count(0)
 assert not errors,errors
 browser.close()
assert hashlib.sha256(source.read_bytes()).hexdigest()==source_sha
assert hashlib.sha256(template.read_bytes()).hexdigest()==template_sha
result={'status':'passed','flow':'login → create accounts/project → batch upload → batch recognition → source locator → fact import → calculate → generate → DOCX download → reviewer read-only','desktop':'1440x1024','mobile':'390x844','source_sha256':source_sha,'template_sha256':template_sha,'report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),'page_errors':errors,'synthetic':True}
(out/'browser-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
