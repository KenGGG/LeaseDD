import hashlib, json, re
from pathlib import Path
from decimal import Decimal, localcontext
from fastapi import HTTPException
from sqlalchemy import select
from .db import Document, FactBatch
from .contracts import SectionDraft

METRICS = {'liabilities_to_assets':'资产负债率','interest_bearing_debt_to_assets':'有息负债率','quick_ratio':'速动比率'}

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def facts_snapshot(db,p):
    batches=db.scalars(select(FactBatch).where(FactBatch.project_id==p.id).order_by(FactBatch.revision)).all()
    # Each import is an explicit selection of a complete candidate set; history remains immutable.
    if not batches: return []
    b=batches[-1]
    return [dict(f, fact_id=f'{b.id}:{i}', document_id=b.document_id) for i,f in enumerate(b.payload['facts'])]

def snapshot_hash(db,p):
    docs=db.scalars(select(Document).where(Document.project_id==p.id).order_by(Document.id)).all()
    return digest({'project_id':p.id,'revision':p.revision,'documents':[(d.id,d.sha256,d.model_allowed) for d in docs], 'facts':facts_snapshot(db,p),'formula':'synthetic-v1','framework':'synthetic-v1','template_sha256':hashlib.sha256((Path(__file__).parent/'assets'/'synthetic_template.docx').read_bytes()).hexdigest(),'section':p.section,'section_version':p.section_version})

def calculate(facts):
    out={}
    for metric, concepts in [('liabilities_to_assets',['total_liabilities','total_assets']),('interest_bearing_debt_to_assets',['interest_bearing_debt','total_assets']),('quick_ratio',['current_assets','inventory','current_liabilities'])]:
        chosen=[];reason=None;status='computed'
        for concept in concepts:
            candidates=[f for f in facts if f['concept']==concept]
            if not candidates: reason=f'missing_required_input:{concept}';status='unavailable';break
            if len(candidates)!=1: reason='unresolved_fact_conflict';status='conflicted';break
            chosen.append(candidates[0])
        if not reason and len({(f['entity'],f['scope'],f['period'],f['currency'],f['unit']) for f in chosen})!=1:
            reason='entity_scope_period_unit_conflict';status='conflicted'
        value=None
        if not reason:
            values=[Decimal(f['value']) for f in chosen]
            if values[-1]==0: reason='zero_denominator';status='zero_denominator'
            else:
                with localcontext() as ctx:
                    ctx.prec=50
                    value=str((values[0]-values[1])/values[2] if metric=='quick_ratio' else values[0]/values[1])
        out[metric]={'metric_id':metric,'value':value,'status':status,'reason':reason,'formula_version':'synthetic-v1','input_fact_ids':[f['fact_id'] for f in chosen]}
    return out

def synthetic_draft(input_hash,metrics):
    blocks=[];answers=[]
    for i,(key,label) in enumerate(METRICS.items(),1):
        good=metrics[key]['value'] is not None
        blocks.append({'block_id':f'P{i:03}','segments':[{'type':'text','text':f'{label}：'},{'type':'metric','ref':key}]})
        answers.append({'question_id':f'Q{i:03}','status':'answered' if good else 'gap','block_ids':[f'P{i:03}']})
    return {'section_id':'SYNTH_SECTION_FINANCE','title':'财务分析测试章节','input_hash':input_hash,'question_answers':answers,'blocks':blocks,'table_id':'SYNTH_FINANCE_TABLE','synthetic':True}

def validate_draft(draft,expected_hash,metrics):
    parsed=SectionDraft.model_validate(draft)
    if not parsed.synthetic:raise ValueError('synthetic_flag_required')
    if parsed.input_hash!=expected_hash: raise ValueError('stale_task_input')
    ids=[b.block_id for b in parsed.blocks]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate_block_id')
    if {q.question_id for q in parsed.question_answers}!={'Q001','Q002','Q003'}: raise ValueError('question_coverage')
    used=set()
    for q in parsed.question_answers:
        if not q.block_ids or not set(q.block_ids)<=set(ids): raise ValueError('unknown_block')
        expected_metric=dict(zip(['Q001','Q002','Q003'],METRICS))[q.question_id]
        refs={s.ref for b in parsed.blocks if b.block_id in q.block_ids for s in b.segments if s.type=='metric'}
        if expected_metric not in refs:raise ValueError('question_metric_binding_missing')
        if metrics[expected_metric]['value'] is None and q.status=='answered':raise ValueError('missing_metric_marked_answered')
        used.update(q.block_ids)
    if used!=set(ids): raise ValueError('unbound_block')
    for b in parsed.blocks:
        for s in b.segments:
            if s.type=='metric' and s.ref not in metrics: raise ValueError('unknown_metric_ref')
            if s.type=='text' and (re.search(r'\d|[０-９]',s.text) or any(x in s.text for x in ['已完成现场','无诉讼','已审核','还款有保障'])):
                raise ValueError('unbound_number_or_unverified_claim')
    return parsed.model_dump(exclude_none=True)

def reason_text(reason):
    labels={'total_assets':'资产总额','total_liabilities':'负债总额','interest_bearing_debt':'有息负债','current_assets':'流动资产','current_liabilities':'流动负债','inventory':'存货'}
    if reason.startswith('missing_required_input:'):return '缺少'+labels.get(reason.split(':')[1],'必要输入')+'数据'
    return {'zero_denominator':'分母为零','entity_scope_period_unit_conflict':'主体、范围、期间或单位不一致','unresolved_fact_conflict':'事实候选存在冲突'}.get(reason,reason)

def metric_display(key,m):
    if m['value'] is None: return '—（'+reason_text(m['reason'] or m['status'])+'）'
    with localcontext() as ctx:
        ctx.prec=110
        value=Decimal(m['value'])*(100 if key!='quick_ratio' else 1)
        return f'{value:.2f}'+('%' if key!='quick_ratio' else '')

def section_text(draft,metrics):
    return [''.join(s['text'] if s['type']=='text' else metric_display(s['ref'],metrics[s['ref']]) for s in b['segments']) for b in draft['blocks']]
