import threading

import pytest

from leasedd.enterprise_warning import EnterpriseModule, EnterpriseWarningError, MODULES, QyjCollector


class FakeBrowser:
    calls = []

    def perform(self, action, **kwargs):
        self.calls.append((action, kwargs))
        if action == 'search':
            return [('https://www.qyyjt.cn/finchinaAPP/v1/finchina-search/v1/multipleSearch',
                     {'returncode': 0, 'data': [{'code': 'ABC', 'name': '甲公司'}]},
                     {'name': kwargs['name']})]
        if kwargs['module'].key == 'balance_sheet':
            return [('https://www.qyyjt.cn/report', {'data': {'value': [['123.45']]}}, {'code': kwargs['company_code']}, 'currency_variant')]
        raise EnterpriseWarningError('module_interface_unverified')

    def menu(self, company_code):
        self.calls.append(('menu', company_code))
        return [{'key': key, 'name': name, 'category': category, 'endpoint': endpoint, 'params': params}
                for key, name, category, endpoint, _trace, params in MODULES]

    def close(self):
        self.calls.append(('close', None))


def test_unix_bridge_reuses_three_collector_actions_without_exposing_browser_profile(tmp_path):
    from leasedd.enterprise_browser_bridge import BrowserBrokerServer, RemoteBrowserSession

    socket_path = tmp_path / 'browser.sock'
    FakeBrowser.calls = []
    with BrowserBrokerServer(str(socket_path), FakeBrowser) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            remote = RemoteBrowserSession(str(socket_path))
            assert remote.menu('ABC')[0]['key'] == 'main_indicators'
            result = remote.perform('collect', company_code='ABC', module=EnterpriseModule(*MODULES[1][:4], 1, MODULES[1][5]))
            assert result[0][1]['data']['value'][0][0] == '123.45'
            assert result[0][3] == 'currency_variant'
            assert ('menu', 'ABC') in FakeBrowser.calls
            assert not any('profile' in str(call) for call in FakeBrowser.calls)
            with pytest.raises(EnterpriseWarningError, match='structure_changed'):
                remote.perform('collect', company_code='ABC', module=EnterpriseModule('invented', '假栏目', 'notes', '/unknown', 999))
            assert not any(call[0] == 'collect' and call[1].get('module').key == 'invented'
                           for call in FakeBrowser.calls if isinstance(call[1], dict))
        finally:
            server.shutdown()
            thread.join(timeout=2)
    assert not socket_path.exists()


def test_unix_bridge_forwards_source_error_and_unavailable_socket(tmp_path):
    from leasedd.enterprise_browser_bridge import BrowserBrokerServer, RemoteBrowserSession

    socket_path = tmp_path / 'browser.sock'
    with pytest.raises(EnterpriseWarningError, match='browser_unavailable'):
        RemoteBrowserSession(str(socket_path)).menu('ABC')
    with BrowserBrokerServer(str(socket_path), FakeBrowser) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            module = EnterpriseModule(*MODULES[0][:4], 0, MODULES[0][5])
            with pytest.raises(EnterpriseWarningError, match='module_interface_unverified'):
                RemoteBrowserSession(str(socket_path)).perform('collect', company_code='ABC', module=module)
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_unix_bridge_returns_source_request_error_when_page_fetch_fails(tmp_path):
    from playwright.sync_api import Error
    from leasedd.enterprise_browser_bridge import BrowserBrokerServer, RemoteBrowserSession

    class FailedFetchBrowser(FakeBrowser):
        def perform(self, action, **kwargs):
            raise Error('Page.evaluate: TypeError: Failed to fetch')

    socket_path = tmp_path / 'browser.sock'
    with BrowserBrokerServer(str(socket_path), FailedFetchBrowser) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            remote = RemoteBrowserSession(str(socket_path))
            module = EnterpriseModule(*MODULES[0][:4], 0, MODULES[0][5])
            with pytest.raises(EnterpriseWarningError, match='source_request_unavailable'):
                remote.perform('collect', company_code='ABC', module=module)
            assert remote.menu('ABC')[0]['key'] == 'main_indicators'
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_unix_bridge_reports_playwright_failure_stage_without_leaking_url(tmp_path):
    from playwright.sync_api import Error
    from leasedd.enterprise_browser_bridge import BrowserBrokerServer, RemoteBrowserSession

    class FailedMenuBrowser(FakeBrowser):
        def menu(self, company_code):
            raise Error('Page.goto: Timeout 30000ms exceeded.\nCall log: secret-token-in-url')

    socket_path = tmp_path / 'browser.sock'
    with BrowserBrokerServer(str(socket_path), FailedMenuBrowser) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with pytest.raises(EnterpriseWarningError) as caught:
                RemoteBrowserSession(str(socket_path)).menu('ABC')
            assert caught.value.code == 'browser_unavailable'
            assert caught.value.details == {'stage': 'Page.goto', 'timeout': True}
            assert 'secret-token-in-url' not in str(caught.value.details)
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_collector_selects_broker_only_when_explicitly_configured(monkeypatch, tmp_path):
    from leasedd.enterprise_browser_bridge import RemoteBrowserSession

    monkeypatch.setenv('QYJ_BRIDGE_SOCKET', str(tmp_path / 'browser.sock'))
    assert isinstance(QyjCollector().session_factory(), RemoteBrowserSession)
