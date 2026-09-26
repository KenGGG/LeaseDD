"""Real UI, read-only API fixtures: global navigation stays above every page."""
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

project = {'id':'style-project','name':'样式验收项目','revision':1,'metrics':{},
           'metrics_current':False,'section_current':False,'production_template_status':'synthetic',
           'members':[{'user_id':'member','username':'验收成员','role':'reviewer'}]}
user = {'id':'member','username':'验收成员','admin':True,'csrf_token':'fixture'}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome')
    for width in (1440, 390):
        page = browser.new_page(viewport={'width':width,'height':900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def serve(route):
            assert route.request.method == 'GET', 'Navigation must not write data'
            path = urlsplit(route.request.url).path.split('/api',1)[1]
            if path == '/me': data = user
            elif path == '/projects': data = [project]
            elif path == '/projects/style-project': data = project
            elif path == '/users': data = [user]
            elif path == '/settings/agnes': data = {'base_url':'','model':'','credential_configured':False}
            elif path.endswith('/facts'): data = {'facts':[],'history':[]}
            elif path.endswith('/section'): data = {'version':0,'draft':None,'current':False,'input_hash':''}
            elif path.endswith('/enterprise'): data = {'source_type':None,'binding':None,'import':None}
            elif path.endswith('/enterprise/data'): data = {'import_id':None,'modules':[]}
            elif path.endswith(('/documents','/financial-statements','/tasks','/exports')): data = []
            else: raise AssertionError(path)
            route.fulfill(json=data)
        page.route('**/api/**', serve)
        page.goto(os.getenv('LEASEDD_BROWSER_URL','http://127.0.0.1:5174'))
        expect(page.get_by_role('heading',name='尽调项目',exact=True)).to_be_visible()
        def check_layout(label):
            nav = page.locator('.sidebar')
            box = nav.bounding_box()
            assert box and box['y'] == 0 and box['height'] <= 80 and abs(box['width']-width) < 2, (label, box)
            content = page.locator('.workspace').bounding_box()
            assert content and content['x'] < 2, (label, content)
            assert page.locator('.workspace>header').bounding_box()['y'] >= box['height']-1
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), label
            expect(nav.get_by_role('button',name=label,exact=label!='尽调项目')).to_have_class('nav active')
        check_layout('尽调项目')
        page.get_by_role('button').filter(has_text='样式验收项目').click()
        for label in ('项目概览','资料与证据','财务核对','报告章节','复核与导出','账号与服务配置'):
            button = page.locator('.sidebar').get_by_role('button',name=label,exact=True)
            button.click()
            expect(button).to_have_class('nav active')
            check_layout(label)
            if label == '财务核对':
                expect(page.get_by_role('navigation',name='财务数据栏目')).to_be_visible()
            page.screenshot(path=f'/tmp/leasedd-app-{width}-{label}.png',full_page=False)
        assert not errors, errors
        page.close()
    browser.close()
print('Global navigation: 14 page/viewport checks passed; no write requests or page errors')
