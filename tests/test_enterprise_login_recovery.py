"""Browser boundary doubles: exercise recovery without credentials or live accounts."""
import pytest
from types import SimpleNamespace

from leasedd.enterprise_warning import EnterpriseWarningError, _PlaywrightSession


class Element:
    def __init__(self, page, text):
        self.page, self.text = page, text

    @property
    def first(self):
        return self

    def is_visible(self):
        if self.text == "#username":
            return "登录" in self.page.visible
        return self.text in self.page.visible

    def is_enabled(self):
        return self.page.autofilled and self.page.fill_wait >= self.page.ready_after

    def click(self, **kwargs):
        self.page.clicks.append(self.text)
        if self.text == "我已知晓":
            self.page.visible.remove(self.text)
        if self.text == "登录" and self.page.login_succeeds and self.page.autofilled:
            self.page.visible = {"主要财务指标"}


class Page:
    def __init__(self, visible, login_succeeds=False, saved_login=True, ready_after=250):
        self.visible = set(visible)
        self.login_succeeds = login_succeeds
        self.clicks, self.urls = [], []
        self.saved_login = saved_login
        self.autofilled = False
        self.fill_wait = 0
        self.ready_after = ready_after
        self.keyboard = self

    def press(self, key):
        self.clicks.append(f"key:{key}")
        if key == "Enter" and self.saved_login:
            self.autofilled = True

    def locator(self, selector):
        return Element(self, "登录" if selector == "button[type='submit']" else selector)

    def goto(self, url, **kwargs):
        self.urls.append(url)

    def get_by_text(self, text, **kwargs):
        return Element(self, text)

    def wait_for_timeout(self, milliseconds):
        if self.autofilled:
            self.fill_wait += milliseconds


def session(page):
    instance = object.__new__(_PlaywrightSession)
    instance.page = page
    return instance


def test_displacement_notice_does_not_prevent_valid_session():
    page = Page(["我已知晓", "主要财务指标"])
    session(page)._navigate_authenticated("https://www.qyyjt.cn/finance")
    assert page.clicks == ["我已知晓"]


def test_login_is_attempted_once_and_target_is_reopened():
    page = Page(["我已知晓", "账户密码登录", "登录"], login_succeeds=True)
    session(page)._navigate_authenticated("https://www.qyyjt.cn/finance")
    assert page.clicks == ["我已知晓", "#username", "key:ArrowDown", "key:Enter", "登录"]
    assert page.urls == ["https://www.qyyjt.cn/finance"] * 2


def test_unsuccessful_login_stops_without_repeated_submissions():
    page = Page(["账户密码登录", "登录"])
    with pytest.raises(EnterpriseWarningError) as error:
        session(page)._navigate_authenticated("https://www.qyyjt.cn/finance")
    assert error.value.code == "authentication_required"
    assert page.clicks.count("登录") == 1


def test_qr_only_login_is_not_reported_as_missing_financial_data():
    page = Page(["手机扫码登录"])
    with pytest.raises(EnterpriseWarningError) as error:
        session(page)._navigate_authenticated("https://www.qyyjt.cn/finance")
    assert error.value.code == "authentication_required"
    assert page.clicks == []


def test_missing_saved_login_does_not_submit_disabled_form():
    page = Page(["账户密码登录", "登录"], saved_login=False)
    with pytest.raises(EnterpriseWarningError) as error:
        session(page)._navigate_authenticated("https://www.qyyjt.cn/finance")
    assert error.value.code == "authentication_required"
    assert "登录" not in page.clicks


def test_waits_for_saved_login_to_enable_submit():
    page = Page(["账户密码登录", "登录"], login_succeeds=True, ready_after=1000)
    session(page)._navigate_authenticated("https://www.qyyjt.cn/finance")
    assert page.clicks.count("登录") == 1


@pytest.mark.parametrize(('failing_group', 'expected_stage'), [
    ('财务分析', 'menu_group_analysis'),
    ('财务附注', 'menu_group_notes'),
])
def test_financial_menu_click_timeout_identifies_group_without_leaking_page(failing_group, expected_stage):
    from playwright.sync_api import Error

    class MenuElement:
        @property
        def first(self):
            return self

        def __init__(self, label):
            self.label = label

        def wait_for(self, **kwargs):
            pass

        def count(self):
            return 1

        def is_visible(self):
            return True

        def evaluate(self, script):
            return False

        def click(self, **kwargs):
            if self.label == failing_group:
                raise Error('Locator.click: Timeout 30000ms exceeded.\nCall log: secret-page-url')

    class MenuPage:
        def get_by_text(self, label, **kwargs):
            return MenuElement(label)

        def locator(self, selector):
            return SimpleNamespace(evaluate_all=lambda expression: None)

        def wait_for_timeout(self, milliseconds):
            pass

    browser = session(MenuPage())
    browser.base = 'https://www.qyyjt.cn'
    browser._navigate_authenticated = lambda url: None
    browser._menu_entry = lambda name, selector: MenuElement(name)
    with pytest.raises(EnterpriseWarningError) as caught:
        browser.menu('company-code')
    assert caught.value.code == 'browser_unavailable'
    assert caught.value.details == {'stage': expected_stage, 'timeout': True,
                                    'matches': 1, 'visible': True}
    assert 'secret-page-url' not in str(caught.value.details)


def test_financial_menu_uses_virtual_tree_lookup_for_notes_group():
    class TextElement:
        @property
        def first(self):
            return self

        def wait_for(self, **kwargs):
            pass

        def count(self):
            return 0

        def click(self, **kwargs):
            raise AssertionError('unmounted virtual note group must not be clicked')

    class LocatedGroup:
        def __init__(self, name, clicked):
            self.name, self.clicked = name, clicked

        def evaluate(self, script):
            return False

        def click(self, **kwargs):
            self.clicked.append(self.name)

    page = SimpleNamespace(get_by_text=lambda *args, **kwargs: TextElement(),
                           locator=lambda selector: SimpleNamespace(evaluate_all=lambda script: None),
                           wait_for_timeout=lambda milliseconds: None)
    browser = session(page)
    browser.base = 'https://www.qyyjt.cn'
    browser._navigate_authenticated = lambda url: None
    clicked = []
    browser._menu_entry = lambda name, selector: LocatedGroup(name, clicked)
    modules = browser.menu('company-code')
    assert len(modules) == 40
    assert clicked == ['财务分析', '财务附注']


class CapturePage:
    def __init__(self):
        self.listeners = []

    def on(self, event, listener):
        self.listeners.append(listener)

    def remove_listener(self, event, listener):
        self.listeners.remove(listener)

    def wait_for_timeout(self, milliseconds):
        pass


def test_failed_navigation_releases_response_listener():
    page = CapturePage()

    def fail():
        raise EnterpriseWarningError("authentication_required")

    with pytest.raises(EnterpriseWarningError):
        session(page)._capture(fail)
    assert page.listeners == []


def test_capture_never_reads_login_body_or_request_credentials():
    page = CapturePage()

    class LoginResponse:
        url = "https://www.qyyjt.cn/finchinaAPP/login?token=private"

        @property
        def request(self):
            pytest.fail("Must not read authentication request")

        def json(self):
            pytest.fail("Must not read authentication response")

    captured = session(page)._capture(lambda: page.listeners[0](LoginResponse()))
    assert captured == [("/login", {}, {})]
    assert page.listeners == []


def test_finance_headers_stay_ephemeral_and_never_enter_saved_payload():
    import json
    page = CapturePage()
    response = SimpleNamespace(
        url='https://www.qyyjt.cn/finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data?code=public',
        request=SimpleNamespace(post_data_json=None, headers={'pcuss':'test-session-only','accept':'application/json','cookie':'must-not-copy','password':'must-not-copy'}),
        json=lambda: {'data':{'head':[], 'value':[]}},
    )
    browser = session(page)
    captured = browser._capture(lambda: page.listeners[0](response))
    assert browser._finance_headers == {'pcuss':'test-session-only','accept':'application/json'}
    assert 'test-session-only' not in json.dumps(captured)
    assert 'must-not-copy' not in json.dumps(captured)


def test_legacy_headers_are_operation_specific_same_origin_and_never_persisted():
    import json
    page=CapturePage();browser=session(page)
    def response(host,operation,token):
        return SimpleNamespace(url=f'https://{host}/getData.action?_t={operation}&code=public',
            request=SimpleNamespace(post_data_json=None,headers={'pcuss':token,'dataid':operation,'cookie':'excluded'}),
            json=lambda:{'data':{'head':[],'value':[]}})
    def action():
        for item in [response('www.qyyjt.cn','1227','business-session'),response('www.qyyjt.cn','1072','filter-session'),response('other.example','1227','foreign-session')]:
            page.listeners[0](item)
    captured=browser._capture(action)
    assert browser._legacy_headers=={'1227':{'pcuss':'business-session','dataid':'1227'},'1072':{'pcuss':'filter-session','dataid':'1072'}}
    assert 'session' not in json.dumps(captured)
    assert 'excluded' not in json.dumps(captured)
    browser._capture(lambda:None)
    assert browser._legacy_headers=={}


def test_finance_bootstrap_waits_for_response_instead_of_declaring_login_failure():
    browser=session(CapturePage());browser._finance_headers={}
    waits=[]
    def wait(milliseconds):
        waits.append(milliseconds)
        if len(waits)==3:browser._finance_headers={'pcuss':'ephemeral'}
    browser.page.wait_for_timeout=wait
    assert browser._wait_finance_headers()=={'pcuss':'ephemeral'}
    assert len(waits)==3
    browser._finance_headers={};browser.page.wait_for_timeout=lambda milliseconds:None
    with pytest.raises(EnterpriseWarningError) as error:browser._wait_finance_headers()
    assert error.value.code=='finance_bootstrap_unavailable'


@pytest.mark.parametrize('threshold',[.5,1])
def test_menu_group_lookup_scrolls_virtual_navigation_before_reading_state(threshold):
    positions=[]
    class Node:
        @property
        def last(self):return self
        def filter(self,**kwargs):return self
        def count(self):return int(bool(positions) and positions[-1]>=threshold)
        def evaluate_all(self,script,ratio):positions.append(ratio)
    page=SimpleNamespace(locator=lambda selector:Node(),wait_for_timeout=lambda milliseconds:None)
    assert session(page)._menu_entry('其他应付款','.pro-menu-submenu-title').count()==1
    assert threshold in positions


def test_note_menu_evidence_does_not_close_already_expanded_antd_tree_groups():
    from leasedd.enterprise_warning import EnterpriseModule
    clicks=[]
    class Group:
        def evaluate(self,script):
            # Real source uses Ant Tree nodes, not a pro-menu-submenu ancestor.
            return True if 'ant-tree-treenode-switcher-open' in script else None
        def click(self,**kwargs):clicks.append(True)
    browser=session(SimpleNamespace(url='https://www.qyyjt.cn/detail/enterprise/financialNotes',wait_for_timeout=lambda milliseconds:None))
    browser._menu_entry=lambda name,selector:Group()
    browser._menu_item=lambda name:SimpleNamespace(evaluate=lambda script:{'name':name,'disabled':True})
    evidence=browser._note_menu_evidence(EnterpriseModule('x','前五名应付款','notes','/notes',0,{'menu_parent':'应付账款'}),'company')
    assert evidence['disabled'] and evidence['company_code']=='company'
    assert clicks==[]


@pytest.mark.parametrize("message, expected", [
    ("browser failed to start", "browser_unavailable"),
    ("Failed to create a ProcessSingleton for your profile directory", "profile_in_use"),
])
def test_browser_launch_failure_is_not_login_failure_and_releases_driver(monkeypatch, message, expected):
    from playwright.sync_api import Error
    stopped = []

    def fail_launch(*args, **kwargs):
        raise Error(message)

    driver = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=fail_launch),
                             stop=lambda: stopped.append(True))
    monkeypatch.setenv("QYJ_PROFILE_DIR", "/unused-test-profile")
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: SimpleNamespace(start=lambda: driver))
    with pytest.raises(EnterpriseWarningError) as error:
        _PlaywrightSession()
    assert error.value.code == expected
    assert stopped == [True]
