"""Reconcile every captured reference cell against evidence from uploaded PDFs.

Reference snapshots are test expectations only. This script does not write a
project, invoke a model, or backfill missing figures from the reference service.
"""
import csv,json,re
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
from collections import Counter,defaultdict
from leasedd.financial_notes import index_notes,notes_matrix,CATEGORIES
from leasedd.note_tables import NOTE_GROUPS
from leasedd.financial_presentation import align_balance_period
from leasedd.financial_analytics import financial_analytics
from leasedd.statement_tables import report_end,concept_for,clean_label

OUT=Path('runtime/acceptance/full-reconciliation');REF=OUT/'reference'
snapshot=OUT/('live-after.json' if (OUT/'live-after.json').exists() else 'live-before.json')
x=json.loads(snapshot.read_text());statements=[align_balance_period(s) for s in x['statements']]
notes=[]
for d in x['documents']:
 for n in index_notes(d.get('markdown',''),d['id'],d.get('conversion_id','')):
  n.update(report_end=report_end(d['markdown']),markdown_sha256=d['markdown_sha256']);notes.append(n)
nd={n['id']:n for n in notes};docs={d['id']:d for d in x['documents']}
analytics=financial_analytics(statements)
g=next(g for g in analytics['groups'] if g['scope']=='consolidated')
results=[];coverage=[];matrices={}
EMPTY={'','-','—'}
def clean(s):return re.sub(r'[\ue000-\uf8ff\s]','',s).replace('（','(').replace('）',')').replace('：',':')
def date(label):
 m=re.search(r'(20\d{2})年(年报|中报|一季报|三季报)',label)
 return m[1]+{'年报':'-12-31','中报':'-06-30','一季报':'-03-31','三季报':'-09-30'}[m[2]] if m else None

def format_value(value,expected,unit='元',default_scale=1):
 if value is None:return '—'
 try:v=Decimal(value)
 except Exception:return str(value)
 scale=Decimal(100000000 if '亿' in expected else 10000 if '万' in expected else default_scale)
 suffix='亿' if '亿' in expected else '万' if '万' in expected else '元' if expected.endswith('元') else '%' if expected.endswith('%') else ''
 decimals=4 if unit=='元/股' else 2
 return f'{(v/scale).quantize(Decimal(1).scaleb(-decimals),rounding=ROUND_HALF_UP):,}'+suffix

def provenance(ids):
 return '; '.join(dict.fromkeys(docs[nd[i]['document_id']]['name']+':L'+str(nd[i]['start_line'])+'-'+str(nd[i]['end_line']) for i in ids if i in nd))

def add(cat,label,p,expected,value,ids=(),reason='',unit='元',scale=1,source=''):
 actual=format_value(value,expected,unit,scale)
 if expected in EMPTY and value is None:status='双方空值'
 elif expected in EMPTY:status='本地多出'
 elif value is None:status='本地缺失'
 elif clean(actual)==clean(expected):status='一致'
 else:status='数值差异'
 results.append(dict(栏目=cat,项目=label,期间=p,企业预警通=expected,LeaseDD=actual,结论=status,原因=reason,PDF来源=source or provenance(ids)))

# These menu entries did not open a distinct target module in the reference UI.
# Never treat the prior page left on screen as the selected submenu's data.
unavailable={'账龄超过1年的重要预付款','按款项性质分类','账龄超过1年的重要应付账款','前五名应付款','预收款项账龄分析','账龄超过1年的重要预收款','前五名预收款','其他应付款-按款项性质分类','其他应付款账龄分析','账龄超过1年的重要其他应付款','前五名其他应付款','按成本计量','按公允价值计量','长期应收款'}
valid_notes=['审计报告','主营构成','主要销售客户','主要供应商','应收账款账龄分析','前五名应收账款','计提坏账的重大应收账款','预付款项账龄分析','前五名预付款','其他应收款账龄分析','前五名其他应收款','应付账款账龄分析','货币资金','存货','受限资产','财务费用','非经常性损益']
for parent in CATEGORIES:
 for cat in NOTE_GROUPS.get(parent,[parent]):matrices[cat]=notes_matrix(notes,cat)
for cat in valid_notes:
 ref=json.loads((REF/(cat+'.json')).read_text());m=matrices[cat]
 grid=ref.get('grid') or [r for table in ref['tables'] for r in table]
 if not grid:coverage.append({'栏目':cat,'状态':'参考页面未取得有效表格'});continue
 header=grid[0];periods=[date(v) for v in header[1:]]
 if any(periods):
  context='';seen=Counter()
  local=defaultdict(list)
  for row in m['rows']:local[clean(row['label'])].append(row)
  for row in grid[1:]:
   if not row or not row[0] or row[0] in ('截止日期','数据类型','报表类型','显示币种','原始币种','转换汇率','汇率类型'):continue
   label=re.sub(r'[\ue000-\uf8ff]','',row[0]).strip()
   if label in ('期末余额','坏账准备','跌价准备'):
    key=context+'|'+('allowance' if label=='坏账准备' else 'balance' if '账龄' in cat else label)
    match=next((r for r in m['rows'] if r['key']==key),None)
    if cat=='存货':match=next((r for r in m['rows'] if r['key']==context+'|'+label),None)
   else:
    context=label
    same=local[clean(label)];match=same[seen[clean(label)]] if seen[clean(label)]<len(same) else None;seen[clean(label)]+=1
   for idx,p in enumerate(periods):
    if not p or p<'2022-01-01' or idx+1>=len(row):continue
    col=m['periods'].index(p) if p in m['periods'] else None
    cell=match['cells'][col] if match and col is not None else {}
    value=cell.get('value');reason='来源冲突，未采信' if cell.get('conflict') else ''
    if value is None and row[idx+1] not in EMPTY:reason=reason or ('未取得此期同口径披露' if col is None else '行名、字段或源表尚未匹配')
    add(cat,context+'/'+label if label in ('期末余额','坏账准备','跌价准备') else label,p,row[idx+1],value,cell.get('note_ids',[]),reason,scale=10000 if cat in ('主营构成','受限资产') else 1)
 elif m.get('layout')=='records':
  p=None
  for row in grid[1:]:
   if not row or not row[0]:continue
   if date(row[0]):p=date(row[0]);continue
   if not p or p<'2022-01-01':continue
   match=next((r for r in m['records'] if r['period']==p and clean(r['cells'][0]['value'] or '')==clean(row[0])),None)
   for i,expected in enumerate(row[1:],1):
    if not expected:continue
    cell=match['cells'][i] if match and i<len(match['cells']) else {}
    unit=m['columns'][i]['unit'] if i<len(m['columns']) else '%'
    add(cat,row[0]+'/'+header[i],p,expected,cell.get('value'),cell.get('note_ids',[]),'对应披露/字段未匹配' if not cell.get('value') else '',unit,scale=10000 if cat in ('前五名应收账款','前五名其他应收款') and i==1 else 1)
 coverage.append({'栏目':cat,'状态':'已逐格对账','本地行数':len(m.get('records',m['rows'])),'本地期间':','.join(m['periods'])})
for cat in sorted(unavailable):coverage.append({'栏目':cat,'状态':'参考菜单未打开独立数据页；不能把上一页算作此栏目'})
coverage.append({'栏目':'其他应收款按款项性质分类','状态':'参考菜单未打开独立数据页；本地按原报告展示'})
# Primary financial statements and all seven analytics sections.
mainrows=re.findall(r"row\('([^']*)','([^']*)','([^']*)'(?:,'([^']*)')?\)",Path('frontend/src/reference-finance.ts').read_text())
analysisrows=json.loads(Path('frontend/src/reference-analysis.json').read_text())
primary={'资产负债表':'balance_sheet','利润表':'income_statement','现金流量表':'cash_flow_statement'}
for cat in ['主要财务指标',*primary,*analysisrows]:
 ref=json.loads((REF/(cat+'.json')).read_text());tables=ref['tables']
 if len(tables)<2:continue
 periods=[date(v) for v in tables[0][0][1:]];data=tables[1];seen=Counter()
 available_labels={clean(label):[(key,match) for key,l,_,match in mainrows if clean(l)==clean(label)] for _,label,_,_ in mainrows} if cat=='主要财务指标' else {clean(r['label']):[(r['key'],r.get('match',''))] for r in analysisrows.get(cat,[])}
 for row in data:
  if not row or len(row)<2 or not any(v.strip() for v in row[1:]):continue
  label=re.sub(r'[\ue000-\uf8ff]','',row[0]).strip()
  if label in ('截止日期','显示币种','原始币种','转换汇率','汇率类型','审计意见','数据来源'):continue
  choices=available_labels.get(clean(label),[]);choice=choices[seen[clean(label)]] if seen[clean(label)]<len(choices) else None;seen[clean(label)]+=1
  for idx,p in enumerate(periods):
   if not p or p<'2022-01-01' or idx+1>=len(row):continue
   value=None;source='';reason='';unit='元'
   if cat in primary:
    typ=primary[cat];aliases={'预付账款':'预付款项','其他应收款项':'其他应收款','其他应付款项':'其他应付款','归属母公司股东的权益':'归属于母公司所有者权益合计','资产总计':'资产总计','负债和股东权益总计':'负债和所有者权益总计'}
    aliases.update({'一年内到期非流动负债':'一年内到期的非流动负债','实收资本(或股本)':'股本','归属于母公司的股东权益合计':'归属于母公司所有者权益合计','归属于母公司所有者的净利润':'归属于母公司股东的净利润','其他综合收益':'其他综合收益的税后净额','归属母公司股东的其他综合收益':'归属母公司所有者的其他综合收益','归属母公司股东的综合收益总额':'归属于母公司所有者的综合收益总额','基本每股收益（元）':'基本每股收益','稀释每股收益（元）':'稀释每股收益'})
    if typ=='cash_flow_statement':
     aliases.update({label:label.replace('的其他','其他').replace('所收到','收到').replace('所支付','支付').replace('而收到','收回').replace('借款收到','取得借款收到').replace('购买子公司','取得子公司')})
    concept=concept_for(aliases.get(label,label),typ)
    candidates=[(s,i) for s in statements if s['statement_type']==typ and s['scope']=='consolidated' and (s['period_normalized'] or s['period']).split('/')[-1]==p for i in s['items'] if not i.get('supplemental') and (i['concept']==concept or clean(clean_label(i['source_name']))==clean(label))]
    vals={Decimal(i['normalized_value']) for _,i in candidates if i.get('normalized_value') is not None and i['status'] in ('source_verified','human_confirmed')}
    if len(vals)==1:value=str(next(iter(vals)))
    if len(vals)>1:reason='不同报告对同科目披露存在差异，保留冲突'
    source='; '.join(dict.fromkeys(docs[s['document_id']]['name']+':L'+str(i['source_start_line']) for s,i in candidates))
    if candidates:unit=candidates[0][1]['raw_unit']
   elif choice:
    column=next((c for c in g['periods'] if c['period'].split('/')[-1]==p),None)
    metric=next((v for v in column['metrics'] if v['code']==choice[0]),None) if column else None
    if not metric and column and choice[1]:metric=next((v for v in column['metrics'] if v['label']==choice[1] and (cat=='主要财务指标' or v['category']==cat)),None)
    if metric:
     value=metric['value'];unit=metric['unit'];reason=metric.get('reason') or ''
     source='; '.join(dict.fromkeys(docs[i['document_id']]['name']+':L'+str(i.get('start_line','')) for i in metric.get('inputs',[]) if i.get('document_id') in docs))
   add(cat,label,p,row[idx+1],value,reason=reason or ('当前展示未匹配：需区分原报告未披露、分类差异和尚未实现字段' if value is None else ''),unit=unit,scale=10000 if unit=='元' else 1,source=source)
 coverage.append({'栏目':cat,'状态':'已逐格对账'})
for r in results:
 if r['结论']=='本地缺失':
  if r['期间'].endswith(('-03-31','-09-30')):r['原因']='未上传对应一季报/三季报；不能用年报代替'
  elif r['期间']=='2022-12-31' and r['栏目'] in ('审计报告','主要销售客户','主要供应商','前五名应收账款','前五名预付款','前五名其他应收款','计提坏账的重大应收账款'):r['原因']='未上传2022年年报；后续年报未披露此明细的对比列'
  elif r['期间']=='2025-06-30' and r['栏目'].startswith(('前五','计提')):r['原因']='未上传2025年中报；2026年中报未披露上年同期名单'
  elif '年增长率' in r['项目']:r['原因']='需确认跨年匿名客户是否同一主体；不能按A/B代号直接计算增长'
  elif r['栏目']=='主营构成':r['原因']='明细行/收入成本维度尚未完全映射参考分类；需按原表继续对齐'
 if r['结论']=='数值差异':
  if r['栏目']=='前五名应收账款':r['原因']='PDF披露的比例分母包含合同资产，参考平台该期使用纯应收账款口径；保留原披露'
  elif '账龄分析' in r['栏目']:r['原因']='参考平台2025年合计使用账面净值、此前年度使用账面余额；本地持续显示原表账龄余额'
  elif r['栏目']=='非经常性损益':r['原因']='PDF单列资金占用费73,540.74元；参考平台将其并入其他，分类口径不同'
  elif r['栏目']=='受限资产':r['原因']='2023年报披露的上年期末受限资产合计493,159,435.31元，与参考2022年数据不同；需2022原报告核实'
  elif r['期间']=='2023-12-31' and ('每股' in r['栏目'] or '每股' in r['项目']):r['原因']='2023报告股份变动表212,271,108股与股本附注211,520,000股不一致；需人工确认分母'
  elif r['期间']=='2022-12-31':r['原因']='本地来自2023年报的2022比较数，存在会计政策调整和披露精度差异；需2022原报告核实'
  else:r['原因']='计算公式/债务或现金范围与参考口径不同，尚不能宣布一致；见本地可追溯公式'
(OUT/'all-cells.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
(OUT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
(OUT/'notes-after.json').write_text(json.dumps(matrices,ensure_ascii=False))
(OUT/'statements-after.json').write_text(json.dumps(statements,ensure_ascii=False))
(OUT/'analytics-after.json').write_text(json.dumps(analytics,ensure_ascii=False))
with (OUT/'逐项数据比对.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
summary={c:dict(Counter(r['结论'] for r in results if r['栏目']==c)) for c in dict.fromkeys(r['栏目'] for r in results)}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
