"""Offline acceptance for provider limits; no Agnes traffic or real credentials."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from leasedd.agnes_client import AgnesClient, AgnesError, SharedRateLimiter
from leasedd.db import Base, Setting, database


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def sessions(tmp_path):
    engine, sessions = database('sqlite:///' + str(tmp_path / 'limits.sqlite'))
    Base.metadata.create_all(engine)
    yield sessions
    engine.dispose()


def response(value=None, *, reason='stop', status=200, headers=None):
    return httpx.Response(status, headers=headers, json={
        'choices': [{'finish_reason': reason, 'message': {'content': json.dumps(value or {'items': []})}}],
        'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30},
    })


def client(sessions, handler, clock=None, **kwargs):
    clock = clock or Clock()
    return AgnesClient(
        {'base_url': 'https://example.invalid/v1', 'model': 'agnes-2.5-flash'},
        sessions, api_key='synthetic-key', clock=clock, sleep=clock.sleep,
        http_client_factory=lambda **options: httpx.Client(transport=httpx.MockTransport(handler), **options),
        **kwargs,
    )


def test_shared_rolling_window_survives_client_recreation_and_never_stores_secret(sessions):
    clock = Clock()
    a = SharedRateLimiter(sessions, 'synthetic-key', clock=clock, sleep=clock.sleep)
    for _ in range(10):
        a.acquire()
    b = SharedRateLimiter(sessions, 'synthetic-key', clock=clock, sleep=clock.sleep)
    for _ in range(8):
        b.acquire()
    assert clock.sleeps == []
    b.acquire()
    assert clock.now >= 1060
    with sessions() as db:
        row = db.scalar(select(Setting))
        assert len(row.key) <= 40
        assert 'synthetic-key' not in row.key + json.dumps(row.value)
        assert len(row.value['requests']) == 1


def test_parallel_reservations_are_atomic_in_sqlite(sessions):
    def reserve(_):
        limiter = SharedRateLimiter(sessions, 'parallel-synthetic-key', clock=lambda: 1000)
        return limiter.reserve()

    with ThreadPoolExecutor(max_workers=8) as pool:
        delays = list(pool.map(reserve, range(28)))
    assert delays.count(0) == 18
    assert all(delay == 60 for delay in delays if delay)
    with sessions() as db:
        assert len(db.scalar(select(Setting)).value['requests']) == 18


def test_credentials_have_independent_limits_and_limit_never_exceeds_provider(sessions):
    clock = Clock()
    a = SharedRateLimiter(sessions, 'a', requests_per_minute=1000, clock=clock, sleep=clock.sleep)
    b = SharedRateLimiter(sessions, 'b', clock=clock, sleep=clock.sleep)
    for _ in range(20):
        assert a.reserve() == 0
    assert a.reserve() == 60
    assert b.reserve() == 0


def test_retry_after_is_shared_and_retries_count_as_requests(sessions):
    clock = Clock()
    calls = []
    attempts = []

    def handle(request):
        calls.append((clock.now, request))
        if len(calls) == 1:
            return response(status=429, headers={'Retry-After': '9'})
        return response({'accepted': True})

    model = client(sessions, handle, clock, on_attempt=lambda stage, attempt: attempts.append((stage, attempt)))
    assert model('locate', {}, system='data only', max_tokens=4000) == {'accepted': True}
    assert [now for now, _ in calls] == [1000, 1009]
    assert attempts == [('locate', 1), ('locate', 2)]
    assert model.last_attempts == 2
    assert model.last_usage == {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30}
    with sessions() as db:
        assert len(db.scalar(select(Setting)).value['requests']) == 2


def test_final_429_still_sets_shared_cooldown_and_http_date_is_supported(sessions):
    clock = Clock()
    model = client(sessions, lambda req: response(status=429, headers={'Retry-After': formatdate(clock.now + 10, usegmt=True)}), clock)
    with pytest.raises(AgnesError, match='agnes_rate_limited'):
        model('extract', {}, system='data', max_tokens=4000)
    assert model.last_attempts == 3
    limiter = SharedRateLimiter(sessions, 'synthetic-key', clock=clock, sleep=clock.sleep)
    assert limiter.reserve() == 10


def test_timeout_and_server_error_retry_with_backoff_but_never_more_than_three(sessions):
    clock = Clock()
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout('secret upstream body', request=request)
        return response(status=503)

    model = client(sessions, handle, clock)
    with pytest.raises(AgnesError, match='^agnes_http_503$') as error:
        model.complete('data', {}, max_tokens=3000)
    assert len(calls) == 3
    assert clock.sleeps == [1, 2]
    assert error.value.__cause__ is None
    assert 'secret' not in str(error.value)


def test_auth_errors_never_retry_or_expose_provider_body(sessions):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(401, text='synthetic-key sensitive financial body')

    model = client(sessions, handle)
    with pytest.raises(AgnesError, match='^agnes_http_401$'):
        model('extract', {}, system='data', max_tokens=3000)
    assert len(calls) == 1


@pytest.mark.parametrize('upstream,code', [
    (response({'partial': True}, reason='length'), 'agnes_output_truncated'),
    (response(reason='content_filter'), 'agnes_response_rejected'),
    (httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{ broken'}}]}), 'agnes_invalid_json'),
    (httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '[]'}}]}), 'agnes_invalid_json'),
    (httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"amount": NaN}'}}]}), 'agnes_invalid_json'),
])
def test_incomplete_or_invalid_output_cannot_be_accepted(sessions, upstream, code):
    calls = []
    model = client(sessions, lambda request: calls.append(request) or upstream)
    with pytest.raises(AgnesError, match='^' + code + '$'):
        model('extract', {}, system='data', max_tokens=4000)
    assert len(calls) == 1


def test_payload_budget_is_checked_before_rate_slot_and_output_is_capped(sessions):
    calls = []
    model = client(sessions, lambda request: calls.append(request) or response())
    with pytest.raises(AgnesError, match='agnes_context_budget_exceeded'):
        model('extract', {'markdown': '财' * 180000}, system='data', max_tokens=65000)
    with sessions() as db:
        assert db.scalar(select(Setting)) is None
    assert not calls
    model('extract', {'markdown': 'short'}, system='data', max_tokens=100000)
    body = json.loads(calls[0].content)
    assert body['max_tokens'] == 65000
    assert body['model'] == 'agnes-2.5-flash'
    assert str(calls[0].url) == 'https://example.invalid/v1/chat/completions'
    assert calls[0].headers['authorization'] == 'Bearer synthetic-key'


def test_attempt_observer_can_block_http_for_durable_budget(sessions):
    calls = []

    def stop(stage, attempt):
        raise RuntimeError('durable_attempt_budget_exhausted')

    model = client(sessions, lambda request: calls.append(request) or response(), on_attempt=stop)
    with pytest.raises(RuntimeError, match='durable_attempt_budget_exhausted'):
        model('extract', {}, system='data', max_tokens=4000)
    assert calls == []


def test_oversized_success_response_is_rejected_before_json_decode(sessions):
    model = client(sessions, lambda request: httpx.Response(200, content=b'x' * 4_000_001))
    with pytest.raises(AgnesError, match='agnes_response_too_large'):
        model('extract', {}, system='data', max_tokens=65000)


@pytest.mark.parametrize('base_url', ['https://[bad', 'https://user:synthetic-key@example.invalid/v1'])
def test_invalid_configuration_does_not_leak_url_secrets(sessions, base_url):
    with pytest.raises(AgnesError, match='^agnes_invalid_configuration$'):
        AgnesClient({'base_url': base_url, 'model': 'agnes-2.5-flash'}, sessions, api_key='synthetic-key')


def test_cancelled_task_aborts_during_shared_cooldown(sessions):
    clock = Clock()
    calls = []
    active = True

    def check_active():
        if not active:
            raise RuntimeError('stale_task_lease')

    def sleep_and_cancel(seconds):
        nonlocal active
        clock.sleep(seconds)
        active = False

    model = client(sessions, lambda request: calls.append(request) or response(status=429, headers={'Retry-After': '120'}),
                   clock, check_active=check_active)
    model.limiter.sleep = sleep_and_cancel
    with pytest.raises(RuntimeError, match='stale_task_lease'):
        model('extract', {}, system='data', max_tokens=4000)
    assert len(calls) == 1
    assert clock.sleeps == [30]


@pytest.fixture
def postgres_sessions():
    url = os.getenv('LEASEDD_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set LEASEDD_TEST_DATABASE_URL for isolated PostgreSQL limiter concurrency test')
    admin_engine = create_engine(url)
    schema = 'test_agnes_' + uuid.uuid4().hex
    engine = None
    with admin_engine.begin() as db:
        db.execute(text('CREATE SCHEMA ' + schema))
    try:
        engine = create_engine(url, connect_args={'options': '-csearch_path=' + schema},
                               pool_size=12, max_overflow=4)
        # Only this fresh schema receives a settings table; no live settings,
        # project, account or business table is accessed by the test.
        Setting.__table__.create(engine)
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine:
            engine.dispose()
        with admin_engine.begin() as db:
            db.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin_engine.dispose()


def test_postgresql_concurrent_clients_share_window_and_cooldown(postgres_sessions):
    def reserve(_):
        return SharedRateLimiter(postgres_sessions, 'postgres-synthetic-key', clock=lambda: 1000).reserve()

    with ThreadPoolExecutor(max_workers=12) as pool:
        delays = list(pool.map(reserve, range(40)))
    assert delays.count(0) == 18
    assert delays.count(60) == 22
    with postgres_sessions() as db:
        settings = list(db.scalars(select(Setting)))
        assert len(settings) == 1
        assert len(settings[0].value['requests']) == 18
    first = SharedRateLimiter(postgres_sessions, 'postgres-synthetic-key', clock=lambda: 1061)
    first.defer(25)
    second = SharedRateLimiter(postgres_sessions, 'postgres-synthetic-key', clock=lambda: 1061)
    assert second.reserve() == 25
