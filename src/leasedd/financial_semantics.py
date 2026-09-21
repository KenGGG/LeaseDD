"""Model contracts and deterministic cell-anchored checks; no company rules.

VERIFIED concerns machine evidence checks, never human approval. Semantic errors
remain possible and are measured by the independent extraction benchmark.
"""
import hashlib
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .document_structure import get_cell
from .finance_extract import FINANCIAL_CONCEPTS,UNIT_SCALES,normalize_period

VERSION='agnes-semantic-v1'
CONCEPTS=FINANCIAL_CONCEPTS|{'cash_and_cash_equivalents','exchange_rate_effect','beginning_cash_balance'}
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Proof(Strict):
    start_line:int=Field(ge=1)
    end_line:int=Field(ge=1)
    quote:str=Field(min_length=1,max_length=4000)
class ClassifiedTable(Strict):
    block_ids:list[str]=Field(min_length=1,max_length=100)
    classification:Literal['primary','note','other_financial','non_financial','unknown']
class DocumentClassification(Strict):
    tables:list[ClassifiedTable]=Field(max_length=5000)
EvidenceKey=Literal['entity','scope','currency','unit','statement_type','period']
class NonAmountColumn(Strict):
    block_id:str
    column:int=Field(ge=1,description='原物理表cells.column坐标，使用包含科目列的1-based绝对位置。')
    header_rows:list[int]=Field(min_length=1,max_length=30)
    raw_header:str=Field(min_length=1,max_length=500)
    kind:Literal['note_reference','sequence','other']
    evidence:Proof
class SemanticColumn(Strict):
    block_id:str
    column:int=Field(ge=1,description='原物理表cells.column坐标，包含科目列的1-based绝对位置；不得只对数值列从1重新编号。')
    label_column:int=Field(default=1,ge=1,description='科目原文所在列的cells.column坐标，不能与本数值列column相同。')
    header_rows:list[int]=Field(default_factory=lambda:[1],min_length=1,max_length=30)
    raw_header:str=Field(min_length=1,max_length=500,description='按原表头行顺序逐字返回本金额列的完整表头。')
    period:str=Field(min_length=1,max_length=50)
    period_kind:Literal['instant','year','half_year','quarter','duration']|None=Field(default=None,description='时点 instant；完整年度 year；半年 half_year；季度 quarter；其他起止区间 duration；无法确认 null。')
    period_basis:Literal['opening','closing','duration','unknown']='unknown'
    entity:str|None=None
    scope:Literal['consolidated','parent','standalone','unknown']|None=None
    raw_unit:str|None=None
    evidence:dict[EvidenceKey,Proof]=Field(default_factory=dict,description='必须用 period 键给出本列期间的原文证据；其他口径若覆盖表级值，使用 entity/scope/unit 键提供相应证据。quote是原文连续子串，行号用输入中的 source_start_line/context.line。')
class TableUnderstanding(Strict):
    statement_type:Literal['balance_sheet','income_statement','cash_flow_statement']
    entity:str=Field(min_length=1,max_length=200)
    scope:Literal['consolidated','parent','standalone','unknown']
    currency:str=Field(pattern=r'^(?:[A-Z]{3}|unknown)$',description='ISO币种代码：人民币 CNY，美元 USD，港币 HKD，欧元 EUR；无法确认 unknown。')
    raw_unit:str=Field(min_length=1,max_length=20)
    evidence:dict[EvidenceKey,Proof]=Field(description='使用固定键 entity、scope、currency、unit、statement_type，分别给出主体、口径、币种、单位、报表类型的逐字原文证据；无法找到时省略相应键，不编造。')
    columns:list[SemanticColumn]=Field(min_length=1,max_length=200)
    non_amount_columns:list[NonAmountColumn]=Field(default_factory=list,max_length=100)
class ModelValue(Strict):
    column:int=Field(ge=1)
    raw_value:str|None=Field(default=None,max_length=100)
class SemanticRow(Strict):
    block_id:str
    row:int=Field(ge=1)
    source_name:str=Field(min_length=1,max_length=200)
    concept:str|None=None
    role:Literal['data','total','section','header']='data'
    raw_unit:str|None=None
    values:list[ModelValue]=Field(default_factory=list,max_length=200)
class TableExtraction(Strict):
    rows:list[SemanticRow]=Field(max_length=15000)
SEMANTIC_CONTRACTS={c.__name__:c for c in (DocumentClassification,TableUnderstanding,TableExtraction)}


def compact(value):return re.sub(r'\s+','',value).replace('（','(').replace('）',')').replace('，',',')

def source_number(value):
    if value is None:return None
    s=compact(value)
    if s in ('','-','—','–','－','不适用'):return None
    neg=s.startswith('(') and s.endswith(')')
    if neg:s=s[1:-1]
    # Reject partial comma groups; a fragment is not a small amount.
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?',s):return None
    try:v=Decimal(s.replace(',',''))
    except InvalidOperation:return None
    return -v if neg else v


def normalized_period(raw,kind,statement_type):
    value=compact(raw)
    explicit=re.fullmatch(r'(\d{4})年(\d{1,2})月(\d{1,2})日(?:\((?:调整前|调整后)\))?',value)
    if explicit:value=date(*map(int,explicit.groups())).isoformat()
    if '/' in value:
        start,end=value.split('/',1);a,b=date.fromisoformat(start),date.fromisoformat(end)
        if a>b:raise ValueError('period_order')
        if statement_type=='balance_sheet':raise ValueError('balance_requires_instant')
        actual='duration'
        if a.year==b.year:
            bounds=(a.strftime('%m-%d'),b.strftime('%m-%d'))
            if bounds==('01-01','12-31'):actual='year'
            elif bounds==('01-01','06-30'):actual='half_year'
            elif bounds in (('01-01','03-31'),('04-01','06-30'),('07-01','09-30'),('10-01','12-31')):actual='quarter'
        if kind and kind not in ('duration',actual):raise ValueError('period_kind_mismatch')
        return value,kind or actual
    result=normalize_period(value,statement_type)
    if not result:raise ValueError('period_unknown')
    if result[1]=='instant':date.fromisoformat(value)
    if statement_type=='balance_sheet' and result[1]!='instant':raise ValueError('balance_requires_instant')
    if statement_type!='balance_sheet' and result[1]=='instant':raise ValueError('flow_requires_duration')
    if kind and kind!=result[1]:raise ValueError('period_kind_mismatch')
    return result


def _proof_matches(document,proof,blocks,*,document_context=False):
    """Bind a quote to exact source positions, not another matching string."""
    if not proof or proof.end_line<proof.start_line:return []
    raw=''.join(b['text'] for b in document['blocks'])
    starts=[0]+[m.end() for m in re.finditer('\n',raw)]
    if proof.start_line>len(starts) or proof.end_line>len(starts):return []
    begin=starts[proof.start_line-1]
    end=starts[proof.end_line] if proof.end_line<len(starts) else len(raw)
    allowed=[];all_blocks=document['blocks']
    for b in blocks:
        allowed.append((b['start_offset'],b['end_offset']))
        for heading in b['headings']:
            line=heading['line']
            allowed.append((starts[line-1],starts[line] if line<len(starts) else len(raw)))
        index=next(i for i,v in enumerate(all_blocks) if v['id']==b['id'])
        for adjacent in reversed(all_blocks[:index]):
            if adjacent['kind']=='table':break
            allowed.append((adjacent['start_offset'],adjacent['end_offset']))
    if document_context:
        # Only front-page prose can supply document-level entity identity.
        limit=starts[30] if len(starts)>30 else len(raw)
        allowed.extend((b['start_offset'],min(b['end_offset'],limit)) for b in all_blocks if b['kind']!='table' and b['start_offset']<limit)
    # Merge adjacent spans while preserving gaps occupied by unrelated tables.
    merged=[]
    for a,b in sorted(allowed):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    pattern=re.escape(proof.quote).replace('\\\n',r'\r?\n')
    result=[]
    for match in re.finditer(pattern,raw[begin:end]):
        a,b=begin+match.start(),begin+match.end()
        if any(left<=a and b<=right for left,right in merged):result.append((raw,a,b))
    return result


def proof_text(document,proof,blocks,*,document_context=False):
    return proof.quote if _proof_matches(document,proof,blocks,document_context=document_context) else ''


def metadata_issues(document,blocks,meta,column):
    issues=[];e={**meta.evidence,**column.evidence}
    current=[b for b in blocks if b['id']==column.block_id]
    texts={k:proof_text(document,p,current,document_context=k=='entity') for k,p in e.items()}
    entity=column.entity or meta.entity;scope=column.scope or meta.scope;unit=column.raw_unit or meta.raw_unit
    if compact(entity) not in compact(texts.get('entity','')):issues.append('entity_evidence_missing')
    required={'consolidated':('合并','consolidated'),'parent':('母公司','parent'),'standalone':('单体','个别','standalone')}
    if scope not in required or not any(s in texts.get('scope','').lower() for s in required.get(scope,())):issues.append('scope_evidence_missing')
    unit_proof=e.get('unit')
    unit_matches=_proof_matches(document,unit_proof,current)
    unit_verified=False
    for raw,left,right in unit_matches:
        # Match complete source tokens overlapping the quote: a quote of 元
        # inside 万元 is evidence for 万元, never evidence for 元.
        declared={m[0] for m in re.finditer(r'百万元|千元|万元|亿元|元/股|元',raw) if m.start()<right and m.end()>left}
        if declared=={unit}:unit_verified=True
    if unit not in UNIT_SCALES or not unit_verified:issues.append('unit_evidence_missing')
    currency_words={'CNY':('人民币','CNY','RMB'),'USD':('美元','USD'),'HKD':('港元','港币','HKD'),'EUR':('欧元','EUR')}
    if not any(w in texts.get('currency','') for w in currency_words.get(meta.currency,())):issues.append('currency_evidence_missing')
    if not texts.get('statement_type'):issues.append('statement_type_evidence_missing')
    if not texts.get('period'):issues.append('period_evidence_missing')
    try:period,kind=normalized_period(column.period,column.period_kind,meta.statement_type)
    except (ValueError,TypeError):period,kind=None,None;issues.append('period_invalid')
    block=next((b for b in blocks if b['id']==column.block_id),None)
    if not block or column.column==column.label_column:return issues+['column_invalid'],period,kind
    if block.get('issues'):issues.append('source_structure_issue')
    if not block['rows'] or column.column>len(block['rows'][0]) or column.label_column>len(block['rows'][0]):issues.append('column_invalid')
    if any(r<1 or r>len(block['rows']) for r in column.header_rows):issues.append('header_invalid')
    header=' '.join(block['rows'][r-1][column.column-1] for r in column.header_rows if 0<r<=len(block['rows']) and column.column<=len(block['rows'][r-1]))
    if not header:issues.append('header_missing')
    if compact(header)!=compact(column.raw_header):issues.append('raw_header_mismatch')
    try:
        header_period,_=normalized_period(header,None,meta.statement_type)
        if header_period!=period:issues.append('column_period_mismatch')
    except (ValueError,TypeError):
        dates=re.findall(r'((?:19|20)\d{2})[-年/]([01]?\d)[-月/]([0-3]?\d)日?',header)
        explicit_dates=[]
        for y,m,d in dates:
            try:explicit_dates.append(normalize_period(date(int(y),int(m),int(d)).isoformat(),meta.statement_type)[0])
            except ValueError:issues.append('header_date_invalid')
        if explicit_dates and period not in explicit_dates:issues.append('column_period_mismatch')
        years=set(re.findall(r'(?:19|20)\d{2}',header))
        expected=(period or column.period).split('/')[-1][:4]
        if years and expected not in years and period not in explicit_dates:issues.append('column_period_mismatch')
        elif not years:
            years=set(re.findall(r'(?:19|20)\d{2}',texts.get('period','')))
            permissible={expected}
            if column.period_basis=='opening' and expected.isdigit():permissible.add(str(int(expected)+1))
            if not years.intersection(permissible):issues.append('period_evidence_ambiguous')
    # Mixed scopes must agree with the actual numeric column header.
    if '母公司' in header and scope!='parent' or '合并' in header and scope!='consolidated':issues.append('column_scope_mismatch')
    return list(dict.fromkeys(issues)),period,kind


def non_amount_column_issues(document,blocks,meta):
    """Validate model-declared note/sequence columns before excluding them."""
    issues=[];valid=set();seen=set()
    amount={(c.block_id,c.column) for c in meta.columns}
    labels={(c.block_id,c.label_column) for c in meta.columns}
    for column in meta.non_amount_columns:
        key=(column.block_id,column.column);current=[]
        if key in seen:current.append('duplicate_non_amount_column')
        seen.add(key)
        block=next((b for b in blocks if b['id']==column.block_id),None)
        if key in amount or key in labels:current.append('non_amount_column_overlap')
        if not block or not block['rows'] or column.column>max(map(len,block['rows']),default=0):
            current.append('non_amount_column_invalid')
        elif any(r<1 or r>len(block['rows']) for r in column.header_rows):
            current.append('non_amount_header_invalid')
        else:
            header=' '.join(block['rows'][r-1][column.column-1] for r in column.header_rows if column.column<=len(block['rows'][r-1]))
            if compact(header)!=compact(column.raw_header):current.append('non_amount_header_mismatch')
            proof=proof_text(document,column.evidence,[block])
            if not proof or compact(proof) not in compact(column.raw_header):current.append('non_amount_evidence_missing')
        if not current:valid.add(key)
        issues.extend(current)
    return list(dict.fromkeys(issues)),valid


CORE={
 'balance_sheet':{'total_assets','total_liabilities','total_equity'},
 'income_statement':{'revenue','cost','total_profit','net_profit'},
 'cash_flow_statement':{'net_operating_cash_flow','net_investing_cash_flow','net_financing_cash_flow','net_increase_in_cash'},
}


def _physical_numeric_cells(block,columns,non_amount_columns=frozenset()):
    """Audit original numbers, independently of model omissions and repeats."""
    declared_headers={r for c in columns for r in c.header_rows}
    numbers={};hidden=set();origins={cell['id']:cell['row'] for cell in block['cells']}
    for cell in block['cells']:
        if (block['id'],cell['column']) in non_amount_columns:continue
        if source_number(cell['text']) is None:continue
        header=cell['row'] in declared_headers
        # Bare calendar years may be header values. Only trust their physical
        # header position, not an arbitrary data row named by the model.
        calendar=bool(re.fullmatch(r'(?:19|20)\d{2}',compact(cell['text'])))
        merged_label=any(origins.get(block['grid'][cell['row']-1][c.label_column-1],cell['row'])<cell['row'] for c in columns if c.label_column<=len(block['grid'][cell['row']-1]))
        if header and calendar and (cell['row']==1 or cell['is_header'] or merged_label):continue
        numbers[cell['id']]=cell
        if header:hidden.add(cell['row'])
    return numbers,hidden


def _merge_statement_fragments(fragments):
    """Link only compatible columns; retain every physical evidence item."""
    grouped={}
    for fragment in fragments:
        header=compact(fragment.get('raw_header') or fragment['period'])
        qualifier=next((q for q in ('调整前','调整后') if q in header),'')
        key=tuple(fragment[k] for k in ('statement_type','entity','scope','currency','period_kind','raw_unit'))+(fragment['period_normalized'] or fragment['period'],qualifier)
        source_blocks=list(dict.fromkeys(i['evidence']['cell']['block_id'] for i in fragment['items']))
        if fragment['issues']:
            # Contradictory or unproven metadata cannot borrow the grouping of
            # a valid column that merely has the same claimed period/scope.
            origin=fragment['items'][0]['evidence']['cell']
            key+=('unverified_metadata',origin['block_id'],origin['column'])
        if key not in grouped:
            grouped[key]={**fragment,'items':list(fragment['items']),'issues':list(fragment['issues']),'source_periods':[fragment['period']],'source_block_ids':source_blocks}
            continue
        statement=grouped[key]
        statement['items'].extend(fragment['items'])
        statement['issues']=list(dict.fromkeys(statement['issues']+fragment['issues']))
        statement['source_start_line']=min(statement['source_start_line'],fragment['source_start_line'])
        statement['source_end_line']=max(statement['source_end_line'],fragment['source_end_line'])
        statement['source_periods']=list(dict.fromkeys(statement['source_periods']+[fragment['period']]))
        statement['source_block_ids']=list(dict.fromkeys(statement['source_block_ids']+source_blocks))
    return list(grouped.values())


def _statement_checks(statement):
    """Check disclosed terms only, with no default zero for missing inputs."""
    verified={i['concept']:Decimal(i['normalized_value']) for i in statement['items'] if i['status']=='source_verified' and i['normalized_value'] is not None}
    checks=[];issues=[]
    definitions={
        'balance_sheet':[('assets_equal_liabilities_equity','balance_equation',{'total_assets':1,'total_liabilities':-1,'total_equity':-1})],
        'income_statement':[('profit_less_tax_equals_net_profit','income_equation',{'total_profit':1,'income_tax_expense':-1,'net_profit':-1})],
        'cash_flow_statement':[
            ('cash_flows_plus_fx_equal_net_increase','cash_flow_equation',{'net_operating_cash_flow':1,'net_investing_cash_flow':1,'net_financing_cash_flow':1,'exchange_rate_effect':1,'net_increase_in_cash':-1}),
            ('opening_cash_plus_change_equals_ending_cash','cash_balance_equation',{'beginning_cash_balance':1,'net_increase_in_cash':1,'ending_cash_balance':-1}),
        ],
    }
    conflicts=[]
    tolerance=UNIT_SCALES.get(statement['raw_unit'],Decimal(1))*Decimal('0.02')
    for code,issue_prefix,coefficients in definitions[statement['statement_type']]:
        missing=sorted(set(coefficients)-verified.keys())
        check={'code':code,'period':statement['period_normalized'],'scope':statement['scope'],'entity':statement['entity'],'currency':statement['currency'],'missing_concepts':missing}
        if missing:
            check.update(status='gap',difference=None)
            issues.append(issue_prefix+'_gap')
        else:
            difference=sum((verified[concept]*coefficient for concept,coefficient in coefficients.items()),Decimal(0))
            passed=abs(difference)<=tolerance
            check.update(status='passed' if passed else 'conflict',difference=str(difference))
            if not passed:
                reason=issue_prefix+'_conflict'
                issues.append(reason);conflicts.append((set(coefficients),reason))
        checks.append(check)
    # Evaluate all checks from the same verified snapshot, then mark every
    # conflicting term. A first failure cannot silently suppress a second one.
    for involved,reason in conflicts:
        for item in statement['items']:
            if item['concept'] in involved:
                item['normalized_value']=None
                item['status']='pending_confirmation'
                item['evidence']['verification_state']='CONFLICT'
                item['evidence']['issues']=list(dict.fromkeys(item['evidence']['issues']+[reason]))
    statement['issues']=list(dict.fromkeys(statement['issues']+issues))
    return checks,issues

def validate_table(document,block_ids,metadata,extracted,*,local_statements=None):
    meta=TableUnderstanding.model_validate(metadata);model=TableExtraction.model_validate(extracted)
    blocks=[b for b in document['blocks'] if b['id'] in block_ids and b['kind']=='table']
    if len(blocks)!=len(set(block_ids)):raise ValueError('unknown_table_block')
    document={**document,'_lines':document.get('_lines') or document.get('markdown','').splitlines()}
    if not document['_lines']:
        document['_lines']=''.join(b['text'] for b in document['blocks']).splitlines()
    cells={(r.block_id,r.row):r for r in model.rows}
    row_counts=Counter((r.block_id,r.row) for r in model.rows)
    duplicates={key for key,count in row_counts.items() if count>1}
    column_counts=Counter((c.block_id,c.column) for c in meta.columns)
    duplicate_columns={key for key,count in column_counts.items() if count>1}
    missing=[];statements=[];allissues=[]
    physical_numbers={};hidden_headers={};seen_columns=set();extracted_ids=set();blank_ids=set();unreadable_ids=set()
    non_amount_issues,validated_non_amount=non_amount_column_issues(document,blocks,meta)
    allissues.extend(non_amount_issues)
    for b in blocks:
        defined=[c for c in meta.columns if c.block_id==b['id']]
        numbers,hidden=_physical_numeric_cells(b,defined,validated_non_amount)
        physical_numbers.update(numbers);hidden_headers[b['id']]=hidden
        understood={c.column for c in defined}
        numeric_columns={cell['column'] for cell in numbers.values()}
        if numeric_columns-understood:allissues.append('unmapped_numeric_column')
        if hidden:allissues.append('numeric_data_declared_header')
    if duplicate_columns:allissues.append('duplicate_metadata_column')
    for column in meta.columns:
        if column.block_id not in block_ids:raise ValueError('foreign_column_block')
        column_key=(column.block_id,column.column)
        if column_key in seen_columns:continue
        seen_columns.add(column_key)
        issues,period,kind=metadata_issues(document,blocks,meta,column)
        if column_key in duplicate_columns:issues.append('duplicate_metadata_column')
        if hidden_headers.get(column.block_id):issues.append('numeric_data_declared_header')
        if (column.block_id,column.label_column) in column_counts:issues.append('label_column_is_value_column')
        block=next(b for b in blocks if b['id']==column.block_id)
        entity=column.entity or meta.entity;scope=column.scope or meta.scope;unit=column.raw_unit or meta.raw_unit
        statement={'statement_type':meta.statement_type,'entity':entity,'scope':scope,'period':column.period,'raw_header':column.raw_header,'period_normalized':period,'period_kind':kind,'currency':meta.currency,'raw_unit':unit,'unit_scale':str(UNIT_SCALES[unit]) if unit in UNIT_SCALES else None,'source_start_line':block['start_line'],'source_end_line':block['end_line'],'state':'candidate','issues':issues.copy(),'items':[]}
        for row_index,grid_row in enumerate(block['rows'],1):
            if row_index in column.header_rows:continue
            try:source=get_cell(document,column.block_id,row_index,column.column);name=get_cell(document,column.block_id,row_index,column.label_column)
            except (ValueError,KeyError,IndexError):continue
            if source['row']!=row_index or source['column']!=column.column:continue
            value=source_number(source['text'])
            raw=source['text'];source_name=name['text'].strip()
            if not source_name:continue
            if value is None:
                if compact(raw) in ('','-','—','–','－','不适用'):blank_ids.add(source['id'])
                else:unreadable_ids.add(source['id']);allissues.append('unreadable_numeric_cell')
            row=cells.get((column.block_id,row_index))
            if not row:
                if value is not None:missing.append({'block_id':column.block_id,'row':row_index,'column':column.column,'source_name':source_name})
                continue
            if row.role in ('header','section'):
                if value is not None:missing.append({'block_id':column.block_id,'row':row_index,'column':column.column,'source_name':source_name})
                continue
            item_issues=issues.copy()
            if source_number(source_name) is not None:item_issues.append('source_name_is_numeric')
            if (column.block_id,row_index) in duplicates:item_issues.append('duplicate_model_row')
            if compact(row.source_name)!=compact(source_name):item_issues.append('source_name_mismatch')
            supplied=[v for v in row.values if v.column==column.column]
            if len(supplied)!=1:item_issues.append('model_cell_missing_or_duplicate')
            claimed=source_number(supplied[0].raw_value) if len(supplied)==1 else None
            if value!=claimed:item_issues.append('source_value_mismatch')
            if value is None:item_issues.append('source_blank' if not raw.strip() or raw.strip() in ('-','—','–','－','不适用') else 'source_number_unreadable')
            concept=row.concept if row.concept in CONCEPTS else 'disclosed_'+hashlib.sha256((meta.statement_type+':'+compact(source_name)).encode()).hexdigest()[:32]
            mapped=row.concept in CONCEPTS
            item_unit=row.raw_unit or unit
            if row.raw_unit and row.raw_unit!=unit and not (row.raw_unit=='元/股' and '每股' in source_name):item_issues.append('row_unit_not_supported')
            scale=Decimal(1) if item_unit=='元/股' else UNIT_SCALES.get(item_unit)
            normalized=value*scale if value is not None and scale is not None else None
            local=[]
            for s in local_statements or []:
                if s.get('statement_type')!=meta.statement_type:continue
                for i in s['items']:
                    if i.get('source_start_line')!=source['start_line'] or compact(i['source_name'])!=compact(source_name):continue
                    # A one-line HTML table holds every period. Match the original column's period.
                    if s.get('period_normalized')!=period:continue
                    local.append({'concept':i['concept'],'value':i.get('normalized_value'),'scope':s.get('scope'),'entity':s.get('entity'),'currency':s.get('currency')})
                    if (s.get('scope')!=scope or s.get('entity')!=entity or s.get('currency')!=meta.currency or source_number(i.get('normalized_value'))!=normalized or i['concept']!=concept and not i['concept'].startswith('disclosed_')):item_issues.append('local_disagreement')
            item_issues=list(dict.fromkeys(item_issues))
            conflict=any(x in item_issues for x in ('source_value_mismatch','source_name_mismatch','local_disagreement','duplicate_model_row'))
            state='CONFLICT' if conflict else 'GAP' if item_issues else 'UNMAPPED' if not mapped else 'VERIFIED'
            status='source_verified' if state=='VERIFIED' else 'pending_confirmation' if state in ('CONFLICT','UNMAPPED') else 'source_value_not_found'
            safe_value=format(normalized,'f') if normalized is not None and state in ('VERIFIED','UNMAPPED') else None
            evidence={'pipeline_version':VERSION,'verification_state':state,'mapping_state':'mapped' if mapped else 'unmapped','model_concept':row.concept,'model_raw_value':supplied[0].raw_value if supplied else None,'cell':{k:source[k] for k in ('id','block_id','row','column','start_line','end_line')},'source_number':format(value,'f') if value is not None else None,'source_normalized_value':format(normalized,'f') if normalized is not None else None,'local_candidates':local,'agreement':'source_and_local' if local and state=='VERIFIED' else 'source_only','issues':item_issues}
            statement['items'].append({'concept':concept,'source_name':source_name,'raw_value':raw[:100],'raw_unit':item_unit,'normalized_value':safe_value,'source_text':source['raw'],'source_start_line':source['start_line'],'source_end_line':source['end_line'],'status':status,'evidence':evidence})
            if value is not None:extracted_ids.add(source['id'])
        allissues.extend(statement['issues'])
        if statement['items']:statements.append(statement)
    for row in model.rows:
        if row.block_id not in block_ids:
            allissues.append('foreign_model_row');continue
        block=next(b for b in blocks if b['id']==row.block_id)
        if row.row>len(block['rows']):
            allissues.append('model_row_out_of_bounds');continue
        if any(v.column>len(block['rows'][row.row-1]) for v in row.values):allissues.append('model_cell_out_of_bounds')
    # A logical statement may cross physical pages. Core and equation checks
    # operate only after compatible columns have been assembled.
    statements=_merge_statement_fragments(statements)
    # Detect repeated concepts with conflicting values within a period, not across years.
    candidates={}
    for s in statements:
        for i in s['items']:
            if i['normalized_value'] is not None and not i['concept'].startswith('disclosed_'):
                candidates.setdefault((s['statement_type'],s['entity'],s['scope'],s['currency'],s['period_kind'],s['period_normalized'],i['concept']),[]).append(i)
    for values in candidates.values():
        if len({Decimal(i['normalized_value']) for i in values})>1:
            for i in values:i['normalized_value']=None;i['status']='pending_confirmation';i['evidence']['verification_state']='CONFLICT';i['evidence']['issues'].append('duplicate_concept_conflict')
            allissues.append('duplicate_concept_conflict')
    checks=[]
    for s in statements:
        statement_checks,check_issues=_statement_checks(s)
        checks.extend(statement_checks);allissues.extend(check_issues)
        verified={i['concept'] for i in s['items'] if i['status']=='source_verified'}
        gaps=['missing_core:'+c for c in sorted(CORE[s['statement_type']]-verified)]
        s['issues']=list(dict.fromkeys(s['issues']+gaps));allissues.extend(gaps)
    bad=any(i['evidence']['verification_state'] in ('CONFLICT','GAP') and i['evidence']['source_number'] is not None for s in statements for i in s['items'])
    missing_numeric=set(physical_numbers)-extracted_ids
    if missing_numeric:allissues.append('unextracted_numeric_cells')
    coverage={'method':VERSION,'tables_found':len(blocks),'tables_parsed':len({c.block_id for c in meta.columns}),'numeric_cells':len(physical_numbers),'extracted_cells':len(extracted_ids),'blank_cells':len(blank_ids),'unreadable_cells':len(unreadable_ids),'missing_numeric_cells':len(missing_numeric),'status':'partial' if missing or allissues or bad else 'complete'}
    return {'statements':statements,'missing_rows':list({(r['block_id'],r['row']):r for r in missing}.values()),'issues':list(dict.fromkeys(allissues)),'checks':checks,'coverage':coverage}
