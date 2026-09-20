"""Lease-guarded durable checkpoints for individual semantic model stages."""
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import update

from .agnes_client import AgnesClient, AgnesError, MAX_HTTP_ATTEMPTS
from .db import Task


class StageError(RuntimeError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _load(path, signature):
    if not path.exists():
        return None
    try:
        if path.is_symlink() or path.stat().st_size > 12_000_000:
            raise ValueError()
        cache = json.loads(path.read_text(encoding='utf-8'))
        checksum = cache.pop('cache_sha256')
        if checksum != _hash(cache) or cache['signature'] != signature:
            raise ValueError()
        if cache['signature_sha256'] != _hash(signature):
            raise ValueError()
        if type(cache['attempts']) is not int or not 0 <= cache['attempts'] <= MAX_HTTP_ATTEMPTS:
            raise ValueError()
        if cache['state'] not in {'pending', 'failed', 'completed'}:
            raise ValueError()
        if cache['state'] == 'completed':
            if not isinstance(cache['response'], dict) or cache['response_sha256'] != _hash(cache['response']):
                raise ValueError()
        return cache
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise StageError('stage_cache_invalid') from None


def _write(path, cache):
    encoded = _canonical({**cache, 'cache_sha256': _hash(cache)})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.stage-', suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # Persist directory entry as well as file data before counting a send.
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _owned_task(app, task_id, lease_token):
    with app.state.db.begin() as db:
        # Conditional no-op UPDATE both validates and locks the lease. Unlike
        # SELECT FOR UPDATE alone, this also serializes SQLite test writers.
        owned = db.execute(update(Task).where(
            Task.id == task_id, Task.lease_token == lease_token,
            Task.state == 'running', Task.lease_until > time.time()
        ).values(lease_until=Task.lease_until))
        if owned.rowcount != 1:
            raise StageError('stale_task_lease')
        yield db.get(Task, task_id)


def _progress(task, stage, key, *, completed=False, attempts=0):
    previous = task.result.get('recognition_progress', {})
    completed_keys = list(previous.get('completed_stage_keys', []))
    if completed and key not in completed_keys:
        completed_keys.append(key)
    task.result = {**task.result, 'recognition_progress': {
        **previous, 'stage': stage.split(':', 1)[0], 'current_stage': stage,
        'completed_stages': len(completed_keys), 'completed_stage_keys': completed_keys,
        'stage_attempts': attempts,
    }}


def _safe_config(config):
    # Never serialize arbitrary provider configuration: it may include keys,
    # custom authentication headers or future credential fields.
    endpoint = str(config.get('base_url', '')).rstrip('/')
    try:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
    except ValueError:
        raise StageError('agnes_invalid_configuration') from None
    return {key: config.get(key) for key in (
        'base_url', 'model', 'requests_per_minute', 'timeout_seconds',
        'context_window_tokens', 'max_output_tokens',
    )}


def make_stage_call(app, task_id, lease_token, config, markdown_sha256, *, client_factory=AgnesClient):
    """Return call(stage, payload), reusing only verified exact-input successes.

    A stage can send at most three requests for this task and signature across
    HTTP retries, task retries and worker restarts. Temporary/network failures
    preserve earlier stages; authorization remains the worker's responsibility.
    """
    with app.state.db() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise StageError('stage_task_not_found')
        project_id = task.project_id
    safe_config = _safe_config(config)
    root = Path(app.state.root).resolve()
    directory = root / project_id / 'extractions' / task_id / 'stages'
    if not directory.resolve().is_relative_to(root):
        raise StageError('stage_cache_path_invalid')

    def call(stage, payload):
        from .semantic_pipeline import VERSION, stage_system, stage_output_tokens
        system = stage_system(stage)
        max_tokens = stage_output_tokens(stage, payload)
        signature = {'version': VERSION, 'config': safe_config, 'markdown_sha256': markdown_sha256,
                     'stage': stage, 'payload': payload, 'system': system, 'max_tokens': max_tokens}
        try:
            key = _hash(signature)
        except (ValueError, TypeError):
            raise StageError('stage_payload_invalid') from None
        path = directory / (key + '.json')
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise StageError('stage_cache_path_invalid')
        with _owned_task(app, task_id, lease_token) as task:
            directory.mkdir(parents=True, exist_ok=True)
            cached = _load(path, signature)
            if cached and cached['state'] == 'completed':
                _progress(task, stage, key, completed=True, attempts=cached['attempts'])
                return cached['response']
            if cached and cached['attempts'] >= MAX_HTTP_ATTEMPTS:
                raise StageError('stage_attempt_limit_exceeded')

        def current():
            return _load(path, signature) or {
                'signature': signature, 'signature_sha256': key,
                'state': 'pending', 'attempts': 0,
            }

        def on_attempt(called_stage, attempt):
            if called_stage != stage:
                raise StageError('stage_attempt_mismatch')
            with _owned_task(app, task_id, lease_token) as task:
                cache = current()
                if cache['attempts'] >= MAX_HTTP_ATTEMPTS:
                    raise StageError('stage_attempt_limit_exceeded')
                cache.update(state='pending', attempts=cache['attempts'] + 1)
                _write(path, cache)
                _progress(task, stage, key, attempts=cache['attempts'])

        def check_active():
            # A shared provider cooldown can be much longer than a task lease.
            # Stop a displaced worker during the wait, without charging another
            # stage attempt or waiting for its next eventual HTTP reservation.
            with _owned_task(app, task_id, lease_token):
                pass

        try:
            client = client_factory(config, app.state.db, on_attempt=on_attempt, check_active=check_active)
            response = client(stage, payload, system=system, max_tokens=max_tokens)
            if not isinstance(response, dict):
                raise StageError('stage_response_invalid')
            try:
                response_sha = _hash(response)
            except (TypeError, ValueError):
                raise StageError('stage_response_invalid') from None
            with _owned_task(app, task_id, lease_token) as task:
                cache = current()
                cache.update(state='completed', response=response, response_sha256=response_sha)
                cache.pop('last_error', None)
                _write(path, cache)
                _progress(task, stage, key, completed=True, attempts=cache['attempts'])
            return response
        except Exception as error:
            if isinstance(error, StageError) and str(error) in {
                'stale_task_lease', 'stage_cache_invalid', 'stage_attempt_limit_exceeded',
            }:
                raise
            known = isinstance(error, (AgnesError, StageError))
            code = str(error) if known and re.fullmatch(r'[a-z][a-z0-9_]{0,99}', str(error)) else 'stage_call_failed'
            with _owned_task(app, task_id, lease_token) as task:
                cache = current()
                cache.update(state='failed', last_error=code)
                _write(path, cache)
                _progress(task, stage, key, attempts=cache['attempts'])
            if known and code == str(error):
                raise
            raise StageError(code) from None

    return call
