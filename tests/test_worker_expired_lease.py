"""A completed computation cannot commit under an expired worker lease."""
import hashlib
import time
from types import SimpleNamespace

import pytest

from leasedd.db import Base, Document, DocumentConversion, Export, ExtractionRun, Project, SectionRevision, Task, User, database
from leasedd import worker


@pytest.fixture
def lease_app(tmp_path):
    engine, sessions = database('sqlite:///' + str(tmp_path / 'lease.sqlite'))
    Base.metadata.create_all(engine)
    (tmp_path / 'source').write_bytes(b'synthetic')
    digest = hashlib.sha256(b'synthetic').hexdigest()
    with sessions.begin() as db:
        db.add(User(id='u', username='u', password_hash='synthetic'))
        db.add(Project(id='p', name='synthetic', section={'input_hash': 'input', 'synthetic': True}))
        db.flush()
        db.add(Document(id='d', project_id='p', name='synthetic.md', sha256=digest, path='source', parse_state='text_available', created_by='u'))
        db.flush()
        db.add(DocumentConversion(id='c', project_id='p', document_id='d', original_sha256=digest, tool='test', tool_version='1', state='completed', created_at=time.time()))
        db.add(Task(id='t', project_id='p', kind='extract_finance', mode='auto', state='queued', input_revision=1, input_hash='input', lease_token='owner', lease_until=time.time() - 60, result={'document_id': 'd'}, created_by='u', created_at=time.time()))
    yield SimpleNamespace(state=SimpleNamespace(db=sessions, root=tmp_path))
    engine.dispose()


def expire(app):
    with app.state.db.begin() as db:
        db.get(Task, 't').lease_until = time.time() - 60


def no_background_heartbeat(monkeypatch):
    monkeypatch.setattr(worker.LeaseHeartbeat, 'start', lambda self: None)
    monkeypatch.setattr(worker.LeaseHeartbeat, 'stop', lambda self: None)


@pytest.mark.parametrize('expired', [True, False])
def test_persistence_requires_unexpired_owned_lease(lease_app, expired):
    app = lease_app
    with app.state.db.begin() as db:
        task = db.get(Task, 't')
        task.state = 'running'
        task.lease_until = time.time() + (-60 if expired else 60)
    with app.state.db() as db:
        document = db.get(Document, 'd')
    output = {'statements': [], 'pipeline_version': 'agnes-semantic-v1', 'manifest': {}}
    if expired:
        with pytest.raises(worker.TaskError, match='lease_lost'):
            worker._persist_extraction(app, 't', 'owner', document, 'c', output)
    else:
        worker._persist_extraction(app, 't', 'owner', document, 'c', output)
    with app.state.db() as db:
        assert db.query(ExtractionRun).count() == (0 if expired else 1)


def test_expiry_after_persistence_cannot_complete_extraction(lease_app, monkeypatch):
    app = lease_app
    no_background_heartbeat(monkeypatch)

    def compute(app, task_id, lease):
        with app.state.db.begin() as db:
            db.add(ExtractionRun(id='run', task_id=task_id, conversion_id='c', project_id='p', document_id='d', pipeline_version='agnes-semantic-v1', state='processing', manifest={}, created_at=time.time()))
        expire(app)
        return {'run_id': 'run'}

    monkeypatch.setattr(worker, 'run_finance_extraction', compute)
    assert worker.run_once(app)
    with app.state.db() as db:
        assert db.get(ExtractionRun, 'run').state == 'processing'
        assert db.get(Task, 't').state != 'completed'


@pytest.mark.parametrize('kind', ['generate', 'render'])
def test_expiry_before_final_commit_cannot_publish_chapter_or_export(lease_app, monkeypatch, kind):
    app = lease_app
    no_background_heartbeat(monkeypatch)
    with app.state.db.begin() as db:
        task = db.get(Task, 't')
        task.kind = kind
        task.mode = 'synthetic'
    monkeypatch.setattr(worker, 'snapshot_hash', lambda db, project: 'input')
    monkeypatch.setattr(worker, 'synthetic_draft', lambda *_: {'input_hash': 'input', 'synthetic': True})

    def validate(draft, *_):
        if kind == 'generate':
            expire(app)
        return draft

    def render(*args, **kwargs):
        expire(app)
        return 'unpublished.docx', '0' * 64, {'quality_state': 'passed'}

    monkeypatch.setattr(worker, 'validate_draft', validate)
    monkeypatch.setattr(worker, 'render', render)
    assert worker.run_once(app)
    with app.state.db() as db:
        assert db.get(Task, 't').state != 'completed'
        assert db.query(Export).count() == 0
        assert db.query(SectionRevision).count() == 0
        assert db.get(Project, 'p').section_version == 0


@pytest.mark.parametrize('expired', [True, False])
def test_heartbeat_only_extends_still_active_lease(lease_app, expired):
    app = lease_app
    before = time.time() + (-60 if expired else 60)
    with app.state.db.begin() as db:
        task = db.get(Task, 't')
        task.state = 'running'
        task.lease_until = before
    beat = worker.LeaseHeartbeat(app, 't', 'owner')
    waits = iter([False, True])
    beat.stop_event = SimpleNamespace(wait=lambda _: next(waits))
    beat._run()
    with app.state.db() as db:
        after = db.get(Task, 't').lease_until
        assert (after == before) if expired else (after > before)
