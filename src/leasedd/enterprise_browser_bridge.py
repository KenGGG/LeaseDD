"""Local Unix socket access to the already authorised QYJ browser profile.

Only the three existing collection operations cross this boundary. Browser
credentials and captured request headers remain in the host process.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import socketserver
from playwright.sync_api import Error as PlaywrightError
import stat
import struct
from typing import Any, Callable

from .enterprise_warning import EnterpriseModule, EnterpriseWarningError, MODULES, _PlaywrightSession


_HEADER = struct.Struct('!Q')
_MAX_REQUEST = 16_384
_MAX_RESPONSE = 128 * 1024 * 1024
_CODE = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


def _read_exact(connection: socket.socket, size: int) -> bytes:
    chunks = []
    while size:
        chunk = connection.recv(min(size, 1024 * 1024))
        if not chunk:
            raise OSError('browser_bridge_closed')
        chunks.append(chunk)
        size -= len(chunk)
    return b''.join(chunks)


def _send(connection: socket.socket, value: Any, limit: int) -> None:
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    if len(data) > limit:
        raise EnterpriseWarningError('browser_unavailable')
    connection.sendall(_HEADER.pack(len(data)))
    connection.sendall(data)


def _receive(connection: socket.socket, limit: int) -> dict[str, Any]:
    length = _HEADER.unpack(_read_exact(connection, _HEADER.size))[0]
    if length > limit:
        raise EnterpriseWarningError('structure_changed')
    value = json.loads(_read_exact(connection, length))
    if not isinstance(value, dict):
        raise EnterpriseWarningError('structure_changed')
    return value


class RemoteBrowserSession:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path

    def _call(self, request: dict[str, Any]):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(5)
                connection.connect(self.socket_path)
                connection.settimeout(300)
                _send(connection, request, _MAX_REQUEST)
                reply = _receive(connection, _MAX_RESPONSE)
        except (OSError, ValueError, json.JSONDecodeError, struct.error):
            raise EnterpriseWarningError('browser_unavailable') from None
        if reply.get('ok') is True:
            return reply['value']
        code = reply.get('code')
        details = reply.get('details')
        if not isinstance(code, str):
            raise EnterpriseWarningError('browser_unavailable')
        raise EnterpriseWarningError(code, details if isinstance(details, dict) else None)

    def perform(self, action: str, **kwargs):
        if action == 'search':
            return self._call({'action': action, 'name': kwargs['name']})
        if action == 'collect':
            return self._call({'action': action, 'company_code': kwargs['company_code'],
                               'module_key': kwargs['module'].key})
        raise EnterpriseWarningError('structure_changed')

    def menu(self, company_code: str):
        return self._call({'action': 'menu', 'company_code': company_code})

    def close(self):
        pass


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(300)
        try:
            request = _receive(self.request, _MAX_REQUEST)
            answer = {'ok': True, 'value': self.server.execute(request)}
        except EnterpriseWarningError as error:
            answer = {'ok': False, 'code': error.code, 'details': error.details}
        except PlaywrightError as error:
            code = 'source_request_unavailable' if 'Failed to fetch' in str(error) else 'browser_unavailable'
            answer = {'ok': False, 'code': code}
        except (OSError, ValueError, json.JSONDecodeError, struct.error):
            answer = {'ok': False, 'code': 'structure_changed'}
        try:
            _send(self.request, answer, _MAX_RESPONSE)
        except (OSError, EnterpriseWarningError):
            return


class BrowserBrokerServer(socketserver.UnixStreamServer):
    request_queue_size = 16

    def __init__(self, socket_path: str, session_factory: Callable[[], Any] = _PlaywrightSession):
        if not os.path.isabs(socket_path) or len(socket_path.encode()) > 100:
            raise ValueError('invalid_browser_socket_path')
        directory = os.path.dirname(socket_path)
        os.makedirs(directory, mode=0o750, exist_ok=True)
        if os.path.lexists(socket_path):
            existing = os.lstat(socket_path)
            if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != os.getuid():
                raise ValueError('browser_socket_occupied')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                try:
                    probe.connect(socket_path)
                except ConnectionRefusedError:
                    os.unlink(socket_path)
                else:
                    raise ValueError('browser_socket_in_use')
        self.session_factory = session_factory
        super().__init__(socket_path, _Handler)
        os.chmod(socket_path, 0o660)
        self._inode = os.stat(socket_path).st_ino

    def execute(self, request: dict[str, Any]):
        action = request.get('action')
        if action == 'search':
            name = request.get('name')
            if not isinstance(name, str) or not 1 <= len(name) <= 128:
                raise EnterpriseWarningError('structure_changed')
            kwargs = {'name': name}
        elif action in {'menu', 'collect'}:
            company_code = request.get('company_code')
            if not isinstance(company_code, str) or not _CODE.fullmatch(company_code):
                raise EnterpriseWarningError('structure_changed')
            kwargs = {'company_code': company_code}
            if action == 'collect':
                entry = next((item for item in MODULES if item[0] == request.get('module_key')), None)
                if entry is None:
                    raise EnterpriseWarningError('structure_changed')
                key, name, category, endpoint, _trace, params = entry
                kwargs['module'] = EnterpriseModule(key, name, category, endpoint,
                                                     MODULES.index(entry), params)
        else:
            raise EnterpriseWarningError('structure_changed')
        session = self.session_factory()
        try:
            return session.menu(**kwargs) if action == 'menu' else session.perform(action, **kwargs)
        finally:
            session.close()

    def server_close(self):
        super().server_close()
        try:
            if os.stat(self.server_address).st_ino == self._inode:
                os.unlink(self.server_address)
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser(description='LeaseDD local QYJ browser connection')
    parser.add_argument('--socket', required=True)
    args = parser.parse_args()
    with BrowserBrokerServer(args.socket) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()
