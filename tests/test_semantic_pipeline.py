from copy import deepcopy
from leasedd.semantic_pipeline import extract_semantic_financial_data,logical_table_parts
from leasedd.document_structure import build_document_map
from test_financial_semantics import fixture,MD


def model_fixture(omit=False):
 d,ids,m,r=fixture();calls=[]
 def call(stage,payload):
  calls.append((stage,payload))
  if stage.startswith('map:'):return {'tables':[{'block_ids':ids,'classification':'primary'}]}
  if stage.startswith('interpret:'):return deepcopy(m)
  if stage.startswith('repair:'):return deepcopy(r)
  if stage.startswith('extract:'):return {'rows':deepcopy(r['rows'][:1] if omit else r['rows'])}
  raise AssertionError(stage)
 return call,calls


def test_authorized_pipeline_never_short_circuits_to_local_parser():
 call,calls=model_fixture();result=extract_semantic_financial_data(MD,call,local_statements=[])
 assert [s.split(':')[0] for s,_ in calls]==['map','interpret','extract']
 assert len(result['statements'])==2
 assert result['pipeline_version']=='agnes-semantic-v1'
 assert result['manifest']['model_used'] is True
 assert result['manifest']['counts']['UNMAPPED']==1
 assert result['manifest']['quality_state']=='passed_with_gaps' # document has only balance sheet


def test_missing_rows_trigger_only_target_table_repair():
 call,calls=model_fixture(omit=True);result=extract_semantic_financial_data(MD,call)
 assert len([s for s,_ in calls if s.startswith('map:')])==1
 assert len([s for s,_ in calls if s.startswith('interpret:')])==1
 assert len([s for s,_ in calls if s.startswith('repair:')])==1
 assert result['coverage']['extracted_cells']==9
 assert result['manifest']['repaired_tables']==1


def test_invalid_scope_or_provider_failure_preserves_successful_other_tables():
 d,ids,m,r=fixture();call,calls=model_fixture()
 def bad(stage,payload):
  if stage.startswith('interpret:'):raise RuntimeError('agnes_http_error')
  return call(stage,payload)
 result=extract_semantic_financial_data(MD,bad)
 assert result['statements']==[]
 assert result['manifest']['quality_state']=='failed'
 assert any(v['code']=='agnes_http_error' for v in result['manifest']['errors'])


def test_whole_logical_tables_keep_continuation_blocks_under_budget():
 d=build_document_map(MD+'\n# continued\n<table><tr><td>科目</td><td>2025</td></tr><tr><td>新科目</td><td>10</td></tr></table>')
 ids=[b['id'] for b in d['blocks'] if b['kind']=='table']
 parts=logical_table_parts(d,ids,max_bytes=100000)
 assert len(parts)==1
 assert [b['block_id'] for b in parts[0]['blocks']]==ids
 assert [r['row'] for r in parts[0]['blocks'][0]['rows']]==list(range(1,7))


def test_over_budget_table_splits_rows_without_losing_physical_coordinates():
 md='# X\n<table><tr><td>项目</td><td>2025-12-31</td></tr>'+''.join(f'<tr><td>科目{i}</td><td>{i}</td></tr>' for i in range(100))+'</table>'
 d=build_document_map(md);bid=next(b['id'] for b in d['blocks'] if b['kind']=='table')
 parts=logical_table_parts(d,[bid],max_bytes=7000)
 assert len(parts)>1
 seen={row['row'] for p in parts for b in p['blocks'] for row in b['rows']}
 assert seen==set(range(1,102))
 assert all(p['blocks'][0]['rows'][0]['row']==1 for p in parts)


def test_foreign_model_block_and_unclassified_tables_cannot_count_as_complete():
 result=extract_semantic_financial_data(MD,lambda stage,payload:{'tables':[{'block_ids':['invented'],'classification':'primary'}]})
 assert result['manifest']['quality_state']=='failed'
 assert result['statements']==[]


def test_split_repeats_all_declared_header_rows():
 md='<table><tr><td rowspan="2">项目</td><td>本期</td></tr><tr><td>金额</td></tr>'+''.join(f'<tr><td>行{i}</td><td>{i}</td></tr>' for i in range(80))+'</table>'
 d=build_document_map(md);bid=next(b['id'] for b in d['blocks'] if b['kind']=='table')
 parts=logical_table_parts(d,[bid],max_bytes=7000,header_rows={bid:[1,2]})
 assert len(parts)>1
 assert all([r['row'] for r in p['blocks'][0]['rows'][:2]]==[1,2] for p in parts)


def test_lease_loss_aborts_pipeline_immediately():
 import pytest
 def lost(stage,payload):raise RuntimeError('stale_task_lease')
 with pytest.raises(RuntimeError,match='stale_task_lease'):
  extract_semantic_financial_data(MD,lost)


def test_output_budget_splits_wide_table_even_if_input_fits():
 md='<table><tr><td>项目</td>'+''.join(f'<td>{2020+i}</td>' for i in range(8))+'</tr>'+''.join('<tr><td>科目'+str(i)+'</td>'+''.join(f'<td>{i+j}</td>' for j in range(8))+'</tr>' for i in range(200))+'</table>'
 d=build_document_map(md);bid=next(b['id'] for b in d['blocks'] if b['kind']=='table')
 assert len(logical_table_parts(d,[bid],max_bytes=1_000_000))>1


def test_output_truncation_retries_smaller_row_parts_only():
 call,calls=model_fixture();failed=[]
 def truncate(stage,payload):
  if stage.startswith('extract:') and stage.count(':')==2:
   failed.append(stage);raise RuntimeError('agnes_output_truncated')
  if stage.startswith('extract:'):
   _,_,_,full=fixture();coords={(b['block_id'],r['row']) for b in payload['blocks'] for r in b['rows']}
   return {'rows':[r for r in full['rows'] if (r['block_id'],r['row']) in coords]}
  return call(stage,payload)
 result=extract_semantic_financial_data(MD,truncate)
 assert len(failed)==1
 assert result['coverage']['extracted_cells']==9
 assert not any(e['code']=='agnes_output_truncated' for e in result['manifest']['errors'])


def test_empty_model_map_gets_one_targeted_completeness_retry():
 call,calls=model_fixture();maps=[]
 def incomplete(stage,payload):
  if stage.startswith('map:'):
   maps.append(payload)
   if len(maps)==1:return {'tables':[]}
  return call(stage,payload)
 result=extract_semantic_financial_data(MD,incomplete)
 assert len(maps)==2
 assert maps[1]['repair_targets']==[maps[0]['blocks'][0]['block_id']]
 assert len(result['statements'])==2


def test_persistently_empty_map_stops_after_one_repair_and_reports_gap():
 calls=[]
 def empty(stage,payload):calls.append(stage);return {'tables':[]}
 result=extract_semantic_financial_data(MD,empty)
 assert len(calls)==2
 assert result['manifest']['quality_state']=='failed'
 assert 'unclassified_blocks' in result['manifest']['issues']


def test_wrong_metadata_coordinates_are_reinterpreted_before_extracting_rows():
 call,calls=model_fixture();interpretations=[]
 def shifted(stage,payload):
  response=call(stage,payload)
  if stage.startswith('interpret:'):
   interpretations.append(payload)
   if len(interpretations)==1:
    for column in response['columns']:column['column']-=1
  return response
 result=extract_semantic_financial_data(MD,shifted)
 assert len(interpretations)==2
 assert 'column_invalid' in interpretations[1]['validation_issues']
 assert result['manifest']['counts']['CONFLICT']==0
 assert result['manifest']['counts']['VERIFIED']==8
 assert not any(s.startswith('repair:') for s,p in calls)
