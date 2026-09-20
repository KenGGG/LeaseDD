import copy
import pytest
from leasedd.domain import calculate,synthetic_draft,validate_draft

def base():
 return [dict(fact_id='A',concept='total_assets',value='100',entity='E',scope='consolidated',period='2025-12-31',currency='CNY',unit='yuan'),dict(fact_id='L',concept='total_liabilities',value='80',entity='E',scope='consolidated',period='2025-12-31',currency='CNY',unit='yuan')]

@pytest.mark.parametrize('field,value',[('entity','OTHER'),('scope','parent'),('period','2024-12-31'),('currency','USD'),('unit','wan_yuan')])
def test_ratio_rejects_incompatible_inputs(field,value):
 f=base();f[1][field]=value
 m=calculate(f)['liabilities_to_assets']
 assert m['value'] is None and m['status']=='conflicted'

def test_zero_denominator_never_zero_or_infinite():
 f=base();f[0]['value']='0'
 assert calculate(f)['liabilities_to_assets']['status']=='zero_denominator'
 assert calculate(f)['liabilities_to_assets']['value'] is None

def test_duplicate_facts_remain_conflicted():
 f=base();f.append({**f[0],'fact_id':'A2','value':'120'})
 assert calculate(f)['liabilities_to_assets']['status']=='conflicted'

def test_decimal_keeps_precision_until_display():
 f=base();f[0]['value']='3';f[1]['value']='1'
 assert calculate(f)['liabilities_to_assets']['value'].startswith('0.333333333333333333333333333333333333')

@pytest.mark.parametrize('mutation',['title','ref','number','question','hash','block'])
def test_section_response_cannot_change_locked_contract(mutation):
 metrics=calculate(base());h='a'*64;draft=synthetic_draft(h,metrics)
 if mutation=='title':draft['title']='自由目录'
 if mutation=='ref':draft['blocks'][0]['segments'][1]['ref']='unknown'
 if mutation=='number':draft['blocks'][0]['segments'][0]['text']='资产负债率为99%'
 if mutation=='question':draft['question_answers'][1]['question_id']='Q001'
 if mutation=='hash':draft['input_hash']='b'*64
 if mutation=='block':draft['question_answers'][0]['block_ids']=['unknown']
 with pytest.raises(ValueError):validate_draft(draft,h,metrics)

@pytest.mark.parametrize('mutation',['synthetic','gap_answered','wrong_question_metric'])
def test_draft_cannot_hide_missing_data_or_test_status(mutation):
 metrics=calculate(base());h='a'*64;draft=synthetic_draft(h,metrics)
 if mutation=='synthetic':draft['synthetic']=False
 if mutation=='gap_answered':draft['question_answers'][2]['status']='answered'
 if mutation=='wrong_question_metric':draft['blocks'][2]['segments'][1]['ref']='liabilities_to_assets'
 with pytest.raises(ValueError):validate_draft(draft,h,metrics)
