"""Shared, bounded Agnes transport. It never logs credentials or model contents.

The settings row is operational rate state, not a project artifact. All callers
using a credential share one rolling window, including retries and workers that
restart. A separate short transaction books each request before network I/O.
"""
import hashlib
import json
import math
import os
import time
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import Setting


PROVIDER_REQUESTS_PER_MINUTE = 20
DEFAULT_REQUESTS_PER_MINUTE = 18
PROVIDER_CONTEXT_TOKENS = 512_000
PROVIDER_OUTPUT_TOKENS = 65_000
MAX_HTTP_ATTEMPTS = 3
MAX_RESPONSE_BYTES = 4_000_000


class AgnesError(RuntimeError):
    """Only stable, non-sensitive error codes cross the transport boundary."""


def _bounded_positive(value, default, maximum):
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError):
        number = default
    return max(1, min(number, maximum))


class SharedRateLimiter:
    def __init__(self, db_factory, api_key: str, *, requests_per_minute=DEFAULT_REQUESTS_PER_MINUTE,
                 clock: Callable = time.time, sleep: Callable = time.sleep):
        self.db_factory = db_factory
        self.clock = clock
        self.sleep = sleep
        self.limit = _bounded_positive(requests_per_minute, DEFAULT_REQUESTS_PER_MINUTE,
                                       PROVIDER_REQUESTS_PER_MINUTE)
        # Stable across models/projects/base URLs; a credential owns its quota.
        # 128 digest bits fit the existing settings key column without secrets.
        self.key = 'agnes_r:' + hashlib.sha256(api_key.encode('utf-8')).hexdigest()[:32]

    def _locked_row(self, db):
        dialect = db.get_bind().dialect.name
        if dialect not in {'postgresql', 'sqlite'}:
            raise AgnesError('agnes_rate_database_unsupported')
        insert = pg_insert if dialect == 'postgresql' else sqlite_insert
        db.execute(insert(Setting).values(
            key=self.key, value={'requests': [], 'cooldown_until': 0}
        ).on_conflict_do_nothing(index_elements=['key']))
        # PostgreSQL locks the row. SQLite's preceding INSERT takes the write
        # lock, serializing read/modify/write even though FOR UPDATE is ignored.
        return db.scalar(select(Setting).where(Setting.key == self.key).with_for_update())

    def reserve(self) -> float:
        """Book one slot atomically, or return seconds until another attempt."""
        with self.db_factory.begin() as db:
            row = self._locked_row(db)
            # Read time after the row lock: lock contention must not age a slot
            # before the caller is actually allowed to send its request.
            now = self.clock()
            state = row.value
            requests = sorted(float(stamp) for stamp in state.get('requests', [])
                              if float(stamp) > now - 60)
            cooldown = float(state.get('cooldown_until', 0))
            wait = max(0.0, cooldown - now)
            if len(requests) >= self.limit:
                wait = max(wait, requests[-self.limit] + 60 - now)
            if wait == 0:
                requests.append(now)
            row.value = {'requests': requests, 'cooldown_until': cooldown}
            return wait

    def acquire(self, check_active=None):
        while True:
            if check_active is not None:
                check_active()
            delay = self.reserve()
            if not delay:
                return
            # Recheck shared state periodically, never hold a DB lock asleep.
            self.sleep(min(delay, 30))

    def defer(self, seconds: float):
        """Publish provider cooldown even if this caller has exhausted retries."""
        with self.db_factory.begin() as db:
            row = self._locked_row(db)
            row.value = {**row.value, 'cooldown_until': max(
                float(row.value.get('cooldown_until', 0)), self.clock() + max(0, seconds)
            )}


def estimate_input_tokens(messages: list[dict]) -> int:
    """Conservative UTF-8 byte upper estimate, not a vendor tokenizer claim.

    Reserving one token per byte deliberately overestimates normal Chinese and
    English inputs. Extra space covers message framing and provider metadata.
    This fails closed and asks the caller to split oversized semantic blocks.
    """
    serialized = json.dumps(messages, ensure_ascii=False, separators=(',', ':'))
    return len(serialized.encode('utf-8')) + 2048


def _retry_after(header: str | None, now: float, fallback: float) -> float:
    if header:
        try:
            seconds = float(header)
        except ValueError:
            try:
                seconds = parsedate_to_datetime(header).timestamp() - now
            except (TypeError, ValueError, OverflowError):
                seconds = fallback
        if math.isfinite(seconds):
            return max(0, seconds)
    return fallback


def _reject_nonfinite(_):
    raise ValueError('nonfinite_json_number')


class AgnesClient:
    def __init__(self, config: dict, db_factory, *, api_key: str | None = None,
                 http_client_factory=None, clock: Callable = time.time,
                 sleep: Callable = time.sleep, on_attempt: Callable | None = None,
                 check_active: Callable | None = None):
        self.api_key = api_key if api_key is not None else os.getenv('AGNES_API_KEY')
        if not self.api_key:
            raise AgnesError('agnes_not_configured')
        base_url = str(config.get('base_url', '')).rstrip('/')
        try:
            parts = urlsplit(base_url)
        except ValueError:
            raise AgnesError('agnes_invalid_configuration') from None
        if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise AgnesError('agnes_invalid_configuration')
        self.url = base_url + '/chat/completions'
        self.model = config.get('model')
        if not isinstance(self.model, str) or not self.model.strip():
            raise AgnesError('agnes_invalid_configuration')
        self.clock = clock
        self.sleep = sleep
        self.on_attempt = on_attempt
        self.check_active = check_active
        self.http_client_factory = http_client_factory or httpx.Client
        self.timeout = _bounded_positive(config.get('timeout_seconds'), 180, 900)
        self.context_limit = _bounded_positive(config.get('context_window_tokens'),
                                               PROVIDER_CONTEXT_TOKENS, PROVIDER_CONTEXT_TOKENS)
        self.output_limit = _bounded_positive(config.get('max_output_tokens'),
                                              PROVIDER_OUTPUT_TOKENS, PROVIDER_OUTPUT_TOKENS)
        self.limiter = SharedRateLimiter(db_factory, self.api_key,
                                        requests_per_minute=config.get('requests_per_minute', DEFAULT_REQUESTS_PER_MINUTE),
                                        clock=clock, sleep=sleep)
        self.last_attempts = 0
        self.last_usage = {}

    def __call__(self, stage: str, payload: dict, *, system: str, max_tokens: int) -> dict:
        return self.complete(system, payload, max_tokens=max_tokens, stage=stage)

    def _send(self, client, body):
        # Streaming bounds memory as well as the parsed output size. Error bodies
        # are not read: their content is neither evidence nor safe diagnostics.
        with client.stream('POST', self.url,
                           headers={'Authorization': 'Bearer ' + self.api_key}, json=body) as response:
            status, headers = response.status_code, response.headers
            if not 200 <= status < 300:
                return status, headers, b''
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise AgnesError('agnes_response_too_large')
                chunks.append(chunk)
            return status, headers, b''.join(chunks)

    def complete(self, system: str, payload: dict, *, max_tokens: int, stage: str = 'complete') -> dict:
        self.last_attempts = 0
        self.last_usage = {}
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
            raise AgnesError('agnes_invalid_output_budget')
        output_tokens = min(max_tokens, self.output_limit)
        try:
            user = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError):
            raise AgnesError('agnes_invalid_payload') from None
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        if estimate_input_tokens(messages) + output_tokens > self.context_limit:
            raise AgnesError('agnes_context_budget_exceeded')
        body = {'model': self.model, 'messages': messages,
                'response_format': {'type': 'json_object'},
                'chat_template_kwargs': {'enable_thinking': False},
                'temperature': 0, 'max_tokens': output_tokens, 'stream': False}
        with self.http_client_factory(timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
            for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
                self.limiter.acquire(self.check_active)
                if self.on_attempt is not None:
                    # A durable block budget observer may abort here; no network
                    # call follows a rejected reservation. The unused rate slot
                    # remains booked conservatively.
                    self.on_attempt(stage, attempt)
                self.last_attempts = attempt
                backoff = 2 ** (attempt - 1)
                try:
                    status, headers, content = self._send(client, body)
                except httpx.TransportError:
                    if attempt == MAX_HTTP_ATTEMPTS:
                        raise AgnesError('agnes_transport_error') from None
                    self.sleep(backoff)
                    continue
                if status == 429:
                    self.limiter.defer(_retry_after(headers.get('Retry-After'), self.clock(), backoff))
                    if attempt == MAX_HTTP_ATTEMPTS:
                        raise AgnesError('agnes_rate_limited')
                    continue
                if status in {408, 425} or 500 <= status < 600:
                    if attempt == MAX_HTTP_ATTEMPTS:
                        raise AgnesError(f'agnes_http_{status}')
                    if headers.get('Retry-After'):
                        self.limiter.defer(_retry_after(headers.get('Retry-After'), self.clock(), backoff))
                    else:
                        self.sleep(backoff)
                    continue
                if not 200 <= status < 300:
                    raise AgnesError(f'agnes_http_{status}')
                return self._decode(content)
        raise AgnesError('agnes_retry_limit_exceeded')

    def _decode(self, content: bytes) -> dict:
        try:
            response = json.loads(content, parse_constant=_reject_nonfinite)
            choice = response['choices'][0]
            finish = choice['finish_reason']
        except (ValueError, KeyError, IndexError, TypeError):
            raise AgnesError('agnes_invalid_json') from None
        if finish == 'length':
            raise AgnesError('agnes_output_truncated')
        if finish == 'content_filter':
            raise AgnesError('agnes_response_rejected')
        if finish != 'stop':
            raise AgnesError('agnes_invalid_response')
        try:
            result = json.loads(choice['message']['content'], parse_constant=_reject_nonfinite)
        except (ValueError, KeyError, TypeError):
            raise AgnesError('agnes_invalid_json') from None
        if not isinstance(result, dict):
            raise AgnesError('agnes_invalid_json')
        usage = response.get('usage')
        if isinstance(usage, dict):
            self.last_usage = {key: usage[key] for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                               if type(usage.get(key)) is int and usage[key] >= 0}
        return result
