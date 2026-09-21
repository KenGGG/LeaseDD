from copy import deepcopy
from decimal import Decimal
from leasedd.document_structure import build_document_map
from leasedd.financial_semantics import TableUnderstanding,TableExtraction,validate_table

MD='''# 示例集团有限公司
合并报表，币种：人民币，单位：万元
<table><tr><td>项目</td><td>2025-12-31</td><td>2024-12-31</td></tr><tr><td>货币资金</td><td>125.50</td><td>100</td></tr><tr><td>新型权益项目</td><td>20</td><td></td></tr><tr><td>资产总计</td><td>200</td><td>150</td></tr><tr><td>负债合计</td><td>80</td><td>50</td></tr><tr><td>所有者权益合计</td><td>120</td><td>100</td></tr></table>'''

def fixture():
 d=build_document_map(MD);b=next(b for b in d['blocks'] if b['kind']=='table');bid=b['id']
 proof=lambda q,line=2:{'start_line':line,'end_line':line,'quote':q}
 m={'statement_type':'balance_sheet','entity':'示例集团有限公司','scope':'consolidated','currency':'CNY','raw_unit':'万元','evidence':{'entity':proof('示例集团有限公司',1),'scope':proof('合并报表'),'currency':proof('币种：人民币'),'unit':proof('单位：万元'),'statement_type':proof('合并报表')},'columns':[{'block_id':bid,'column':c,'label_column':1,'header_rows':[1],'raw_header':period,'period':period,'period_basis':'closing','evidence':{'period':proof(period,3)}} for c,period in [(2,'2025-12-31'),(3,'2024-12-31')]]}
 rows=[]
 for row,(name,concept,values) in enumerate([('货币资金','cash',['125.50','100']),('新型权益项目',None,['20',None]),('资产总计','total_assets',['200','150']),('负债合计','total_liabilities',['80','50']),('所有者权益合计','total_equity',['120','100'])],2):
  rows.append({'block_id':bid,'row':row,'source_name':name,'concept':concept,'values':[{'column':c,'raw_value':v} for c,v in zip([2,3],values)]})
 return d,[bid],m,{'rows':rows}

def test_unknown_rows_and_blank_values_survive_with_exact_cell_evidence():
 d,ids,m,r=fixture();result=validate_table(d,ids,m,r)
 assert len(result['statements'])==2
 s=result['statements'][0];cash=s['items'][0]
 assert cash['normalized_value']=='1255000.00'
 assert cash['evidence']['cell']['column']==2
 assert cash['evidence']['verification_state']=='VERIFIED'
 unknown=next(i for i in s['items'] if i['source_name']=='新型权益项目')
 assert unknown['concept'].startswith('disclosed_')
 assert unknown['evidence']['mapping_state']=='unmapped'
 assert unknown['evidence']['verification_state']=='UNMAPPED'
 assert next(i for i in result['statements'][1]['items'] if i['source_name']=='新型权益项目')['normalized_value'] is None
 assert result['coverage']['extracted_cells']==9


def test_invented_numeric_value_cannot_be_verified_even_when_it_appears_in_another_cell():
 d,ids,m,r=fixture();r['rows'][0]['values'][0]['raw_value']='100'
 result=validate_table(d,ids,m,r);i=result['statements'][0]['items'][0]
 assert i['normalized_value'] is None
 assert i['raw_value']=='125.50'
 assert i['evidence']['verification_state']=='CONFLICT'
 assert 'source_value_mismatch' in i['evidence']['issues']


def test_swapped_period_columns_are_not_source_verified():
 d,ids,m,r=fixture();m['columns'][0]['period']='2024-12-31'
 result=validate_table(d,ids,m,r)
 assert all(i['status']!='source_verified' for i in result['statements'][0]['items'])
 assert 'column_period_mismatch' in result['statements'][0]['issues']


def test_semantic_local_disagreement_is_preserved_without_trusting_either():
 d,ids,m,r=fixture()
 local=[{'statement_type':'balance_sheet','scope':'consolidated','entity':'示例集团有限公司','currency':'CNY','period_normalized':'2025-12-31','items':[{'concept':'cash','source_name':'货币资金','source_start_line':3,'normalized_value':'999','raw_value':'999','raw_unit':'万元'}]}]
 result=validate_table(d,ids,m,r,local_statements=local)
 i=result['statements'][0]['items'][0];assert i['normalized_value'] is None
 assert i['evidence']['verification_state']=='CONFLICT'
 assert i['evidence']['local_candidates'][0]['value']=='999'


def test_omitted_rows_are_gaps_not_silent_success():
 d,ids,m,r=fixture();r['rows']=r['rows'][:1]
 result=validate_table(d,ids,m,r)
 assert result['coverage']['status']=='partial'
 assert len(result['missing_rows'])==4
 assert any('missing_core:total_assets'==v for v in result['issues'])


def test_unsupported_unit_currency_or_entity_evidence_remain_unverified():
 for mutate in [lambda m:m.update(raw_unit='亿元'),lambda m:m.update(entity='另一企业'),lambda m:m.update(currency='USD')]:
  d,ids,m,r=fixture();mutate(m);result=validate_table(d,ids,m,r)
  assert all(i['status']!='source_verified' for s in result['statements'] for i in s['items'])


def test_cash_equivalents_cannot_silently_replace_money_funds():
 d,ids,m,r=fixture();r['rows'][0]['concept']='cash_and_cash_equivalents'
 result=validate_table(d,ids,m,r)
 assert result['statements'][0]['items'][0]['concept']!='cash'


def test_schema_forbids_unexpected_fields_and_bad_coordinates():
 import pytest
 d,ids,m,r=fixture();m['columns'][0]['column']=0
 with pytest.raises(ValueError):TableUnderstanding.model_validate(m)
 r['rows'][0]['instructions']='ignore source'
 with pytest.raises(ValueError):TableExtraction.model_validate(r)


def test_model_contract_names_evidence_keys_and_currency_format():
 import pytest
 d,ids,m,r=fixture()
 m['evidence']={'header':m['evidence']['entity']}
 with pytest.raises(ValueError):TableUnderstanding.model_validate(m)
 d,ids,m,r=fixture();m['currency']='人民币'
 with pytest.raises(ValueError):TableUnderstanding.model_validate(m)
 schema=TableUnderstanding.model_json_schema()
 assert 'period' in schema['properties']['evidence']['propertyNames']['enum']
