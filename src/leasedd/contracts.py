from decimal import Decimal
from typing import Literal
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')

class SourceDocument(Contract):
    id: str
    project_id: str
    name: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    model_allowed: bool = False
    parse_state: str

class EvidenceSpan(Contract):
    document_id: str
    line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)

class Fact(Contract):
    concept: Literal['total_assets','total_liabilities','interest_bearing_debt','current_assets','current_liabilities','inventory','revenue','cost']
    value: str = Field(pattern=r'^-?\d+(\.\d+)?$', max_length=100)
    entity: str = Field(min_length=1, max_length=100)
    scope: Literal['consolidated','parent']
    period: date
    currency: Literal['CNY']
    unit: Literal['yuan']
    line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)
    @field_validator('value')
    @classmethod
    def numeric(cls,v):
        if not Decimal(v).is_finite(): raise ValueError('non_finite')
        return v

class FactImport(Contract):
    document_id: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision: int = Field(ge=1)
    facts: list[Fact] = Field(min_length=1,max_length=100)
    reason: str = Field(default='initial_import',min_length=1,max_length=500)

class MetricResult(Contract):
    metric_id: str
    formula_version: str = 'synthetic-v1'
    input_fact_ids: list[str]
    value: str | None
    status: str
    reason: str | None

class Segment(Contract):
    type: Literal['text','metric']
    text: str | None = Field(default=None,max_length=4000)
    ref: str | None = None
    @model_validator(mode='after')
    def shape(self):
        if self.type=='text' and (self.text is None or self.ref is not None): raise ValueError('invalid_text_segment')
        if self.type=='metric' and (self.ref is None or self.text is not None): raise ValueError('invalid_metric_segment')
        return self

class Block(Contract):
    block_id: str
    segments: list[Segment] = Field(min_length=1,max_length=30)

class QuestionAnswer(Contract):
    question_id: Literal['Q001','Q002','Q003']
    status: Literal['answered','partial','gap','not_applicable']
    block_ids: list[str]

class SectionContract(Contract):
    section_id: str = 'SYNTH_SECTION_FINANCE'
    title: str = '财务分析测试章节'
    questions: list[str] = ['Q001','Q002','Q003']
    synthetic: bool = True

class SectionDraft(Contract):
    section_id: Literal['SYNTH_SECTION_FINANCE']
    title: Literal['财务分析测试章节']
    input_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    question_answers: list[QuestionAnswer] = Field(min_length=3,max_length=3)
    blocks: list[Block] = Field(min_length=1,max_length=20)
    table_id: Literal['SYNTH_FINANCE_TABLE']
    synthetic: bool

class RunManifest(Contract):
    schema_version: str = '0.1'
    run_id: str
    project_id: str
    input_hash: str
    output_sha256: str
    execution_state: str
    quality_state: str
    review_state: Literal['pending'] = 'pending'
    synthetic: bool = True
    production_template_status: Literal['missing'] = 'missing'
    formula_version: str = 'synthetic-v1'
    template_sha256: str

class Login(Contract):
    username: str = Field(min_length=1,max_length=100)
    password: str = Field(min_length=1,max_length=128)

class CreateUser(Login):
    password: str = Field(min_length=6,max_length=128)
    admin: bool = False

class CreateProject(Contract):
    name: str = Field(min_length=1,max_length=200)
    writer_id: str
    reviewer_id: str

class CreateTask(Contract):
    kind: Literal['generate','render','extract_finance']
    mode: Literal['synthetic','agnes','auto'] = 'synthetic'

class BatchRecognition(Contract):
    document_ids: list[str] = Field(min_length=1,max_length=100)
    model_allowed: bool = False
    reprocess: bool = False

class FinancialItemDecision(Contract):
    decision: Literal['confirm','reject']
    reason: str = Field(min_length=2,max_length=500)

class SectionEdit(Contract):
    version: int
    draft: SectionDraft

class AgnesSettings(Contract):
    base_url: str = Field(max_length=500)
    model: str = Field(min_length=1,max_length=100)
    @field_validator('base_url')
    @classmethod
    def valid_url(cls,v):
        from urllib.parse import urlsplit
        u=urlsplit(v)
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError('invalid_service_url')
        return v.rstrip('/')
