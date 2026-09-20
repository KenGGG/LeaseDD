import uuid
from sqlalchemy import create_engine, String, Text, Integer, Boolean, Float, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def uid():
    return uuid.uuid4().hex

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[float] = mapped_column(Float)

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics_revision: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[dict] = mapped_column(JSON, default=dict)
    section_version: Mapped[int] = mapped_column(Integer, default=0)
    section_revision: Mapped[int] = mapped_column(Integer, default=0)
    production_template_status: Mapped[str] = mapped_column(String(30), default='missing')

class Member(Base):
    __tablename__ = 'members'
    __table_args__ = (UniqueConstraint('project_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    role: Mapped[str] = mapped_column(String(20))

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    model_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    parse_state: Mapped[str] = mapped_column(String(50))
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))

class DocumentConversion(Base):
    __tablename__ = 'document_conversions'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'))
    original_sha256: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(30))
    tool_version: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(30))
    markdown_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)

class FinancialStatement(Base):
    __tablename__ = 'financial_statements'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'))
    conversion_id: Mapped[str] = mapped_column(ForeignKey('document_conversions.id'))
    run_id: Mapped[str | None] = mapped_column(ForeignKey('extraction_runs.id'), nullable=True)
    statement_type: Mapped[str] = mapped_column(String(30))
    entity: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(50))
    period_normalized: Mapped[str | None] = mapped_column(String(50), nullable=True)
    period_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency: Mapped[str] = mapped_column(String(10))
    raw_unit: Mapped[str] = mapped_column(String(20))
    unit_scale: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_start_line: Mapped[int] = mapped_column(Integer)
    source_end_line: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30))
    issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[float] = mapped_column(Float)

class FinancialItem(Base):
    __tablename__ = 'financial_items'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    statement_id: Mapped[str] = mapped_column(ForeignKey('financial_statements.id'))
    concept: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(String(200))
    raw_value: Mapped[str] = mapped_column(String(100))
    raw_unit: Mapped[str] = mapped_column(String(20))
    normalized_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_text: Mapped[str] = mapped_column(Text)
    source_start_line: Mapped[int] = mapped_column(Integer)
    source_end_line: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    confirmed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)

class ExtractionRun(Base):
    __tablename__ = 'extraction_runs'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), unique=True)
    conversion_id: Mapped[str] = mapped_column(ForeignKey('document_conversions.id'))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'))
    pipeline_version: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(30))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float)

class FactBatch(Base):
    __tablename__ = 'fact_batches'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'))
    payload: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Float)

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    kind: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(30), default='queued')
    input_revision: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str] = mapped_column(String(32), default='')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Float)

class SectionRevision(Base):
    __tablename__ = 'section_revisions'
    __table_args__ = (UniqueConstraint('project_id','version'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    version: Mapped[int] = mapped_column(Integer)
    input_revision: Mapped[int] = mapped_column(Integer)
    draft: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Float)


class Export(Base):
    __tablename__ = 'exports'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), unique=True)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSON)

class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float)

class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

def database(url):
    engine = create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    if url.startswith('sqlite'):
        from sqlalchemy import event
        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine, sessionmaker(engine, expire_on_commit=False)
