import json,re
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from leasedd.financial_supplements import supplementary_statements
from leasedd.financial_analytics import financial_analytics
from leasedd.statement_tables import extract_statement_tables
s=json.load(open('runtime/reference/half-year-persisted.json'))['statements']
annual=extract_statement_tables(Path('runtime/reference/annual-upload.md').read_text())
for n,st in enumerate(annual):
 st.update(id='annual'+str(n),document_id='annual',conversion_id='annual',state='extracted')
 for j,i in enumerate(st['items']):i.update(id='annual'+str(n)+'-'+str(j))
s+=annual
for doc,file in [(s[0]['document_id'],'half-year-upload.md'),('annual','annual-upload.md')]:s+=supplementary_statements(Path('runtime/reference/'+file).read_text(),doc,doc,s)
r=financial_analytics(s)
p=next(g for g in r['groups'] if g['scope']=='consolidated')['periods'][0]
ref=Path('runtime/reference/主要财务指标.txt').read_text().splitlines();ref=[l.strip() for l in ref if l.strip()];pos=ref.index('截止日期')
rows=re.findall(r"row\('([^']*)','([^']*)','([^']*)'(?:,'([^']*)')?\)",Path('frontend/src/reference-finance.ts').read_text())
result=[]
for key,label,section,match in rows:
 try:ix=ref.index(label,pos)
 except ValueError:continue
 pos=ix+1
 expected=next((l.split()[0] for l in ref[ix+1:ix+6] if re.match(r'^-?[0-9,]+(?:\.\d+)?(?:\s|$)',l)),None)
 m=next((m for m in p['metrics'] if m['code']==key or match and m['label']==match),None)
 value=None
 if m and m['value'] is not None:
  d=Decimal(m['value'])/(10000 if m['unit']=='元' else 1);value=f"{d.quantize(Decimal('0.0001') if m['unit']=='元/股' else Decimal('0.01'),rounding=ROUND_HALF_UP):,}"
 result.append({'label':label,'key':key,'expected':expected,'actual':value,'status':'missing' if value is None else 'match' if value==expected else 'difference','reason':m['reason'] if m else 'no metric'})
out=Path('runtime/acceptance/reference-parity');out.mkdir(parents=True,exist_ok=True)
(out/'metrics-comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
(out/'analytics-local.json').write_text(json.dumps(r,ensure_ascii=False))
(out/'statements-local.json').write_text(json.dumps(s,ensure_ascii=False))
print({status:sum(x['status']==status for x in result) for status in ['match','difference','missing']})
print([x for x in result if x['status']!='match'])
ref=json.loads(Path('runtime/reference/analysis-row-reference.json').read_text())
rows=json.loads(Path('frontend/src/reference-analysis.json').read_text())
analysis=[]
for category,items in rows.items():
 for row,(_,expected) in zip(items,ref[category]):
  m=next((m for m in p['metrics'] if m['code']==row['key']),None) or next((m for m in p['metrics'] if m['label']==row.get('match') and m['category']==category),None)
  actual=None
  if m and m['value'] is not None:
   d=Decimal(m['value'])/(10000 if m['unit']=='元' else 1)
   actual=f"{d.quantize(Decimal('0.0001') if m['unit']=='元/股' else Decimal('0.01'),rounding=ROUND_HALF_UP):,}"
  status='match' if actual==expected or actual is None and expected=='-' else 'missing' if actual is None else 'difference'
  analysis.append({'category':category,'label':row['label'],'expected':expected,'actual':actual,'status':status})
(out/'analysis-comparison.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2))
print('analysis', {status:sum(x['status']==status for x in analysis) for status in ['match','missing','difference']})
print([x for x in analysis if x['status']!='match'])
from leasedd.financial_notes import index_notes,notes_matrix
from leasedd.statement_tables import report_end
notes=[]
for file in ['half-year-upload.md','annual-upload.md']:
 text=Path('runtime/reference/'+file).read_text()
 for note in index_notes(text,file,file):
  note['report_end']=report_end(text);notes.append(note)
inventory=notes_matrix(notes,'存货')
(out/'inventory-matrix.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2))
# Three available periods, each containing six groups x three inventory figures.
reftext=Path('runtime/reference/actual-存货.txt').read_text()
lines=[x.strip() for x in reftext[reftext.rfind('项目名称'):reftext.rfind('加载失败')].splitlines() if x.strip()]
pos=0;comparison=[]
for row in inventory['rows']:
 index=lines.index(row['label'],pos);pos=index+1
 for col,cell in enumerate(row['cells']):
  value=Decimal(cell['value']) if cell['value'] is not None else None
  scale=Decimal(100000000) if value is not None and abs(value)>=100000000 else Decimal(10000) if value is not None and abs(value)>=10000 else Decimal(1)
  actual='-' if value is None else f"{(value/scale).quantize(Decimal('.01'),rounding=ROUND_HALF_UP):,}"+('亿' if scale==100000000 else '万' if scale==10000 else '')
  expected=lines[index+col+1]
  comparison.append({'label':row['label'],'period':inventory['periods'][col],'actual':actual,'expected':expected,'status':'match' if actual==expected else 'difference'})
(out/'inventory-comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2))
print('inventory', {status:sum(x['status']==status for x in comparison) for status in ['match','difference']})
assert all(x['status']!='difference' for x in result+analysis+comparison)
