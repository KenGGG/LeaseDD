import pytest
from leasedd.agnes_finance import extract_financial_data


def table(header, rows):
    return '<table>'+''.join('<tr>'+''.join('<td>'+c+'</td>' for c in row)+'</tr>' for row in [header,*rows])+'</table>'


def report():
    intro='# 合成电子股份有限公司\n2026 年半年度报告\n'
    sections=[]
    for scope in ('合并','母公司'):
        sections += [f'## {scope}资产负债表\n编制单位：合成电子股份有限公司\n2026年6月30日\n单位：万元\n'+table(['项目','期末余额','期初余额'],[['货币资金','100.01','80'],['其他非流动资产','2','3'],['未列示科目','','0'],['资本公积','50','40']]),
                     f'## {scope}利润表\n单位：元\n'+table(['项目','2026年半年度','2025年半年度'],[['一、营业总收入','110','90'],['其中：营业收入','100','80'],['五、净利润（净亏损以“-”号填列）','(5.5)','4'],['（一）基本每股收益','-0.0123','0.04']]),
                     f'## {scope}现金流量表\n单位：元\n'+table(['项目','2026年半年度','2025年半年度'],[['经营活动产生的现金流量净额','20','-1'],['支付的各项税费','3','2']])]
    return intro+'\n'.join(sections)


def no_model(*args):
    raise AssertionError('Explicit complete tables must not require a model')


def test_half_year_reads_all_six_tables_and_both_columns_without_model():
    results=extract_financial_data(report(),no_model)
    assert len(results)==12
    assert {s['scope'] for s in results}=={'consolidated','parent'}
    assert {s['entity'] for s in results}=={'合成电子股份有限公司'}
    assert {s['period'] for s in results if s['statement_type']=='balance_sheet'}=={'2026-06-30','2025-12-31'}
    assert {s['period_normalized'] for s in results if s['statement_type']=='income_statement'}=={'2026-01-01/2026-06-30','2025-01-01/2025-06-30'}
    assert sum(len(s['items']) for s in results)==38
    assert all(i['status']=='source_verified' for s in results for i in s['items'])
    coverage=results[0]['coverage']
    assert coverage['tables_found']==6 and coverage['tables_parsed']==6
    assert coverage['numeric_cells']==coverage['extracted_cells']==38
    assert coverage['status']=='complete'


def test_unknown_disclosed_rows_and_zero_are_preserved_not_fabricated():
    results=extract_financial_data(report(),no_model)
    current=next(s for s in results if s['scope']=='consolidated' and s['period']=='2026-06-30')
    prior=next(s for s in results if s['scope']=='consolidated' and s['period']=='2025-12-31')
    assert not any(i['source_name']=='未列示科目' for i in current['items'])
    assert next(i for i in prior['items'] if i['source_name']=='未列示科目')['normalized_value']=='0'
    assert next(i for i in current['items'] if i['concept']=='cash')['normalized_value']=='1000100'
    extra=next(i for i in current['items'] if i['source_name']=='资本公积')
    assert extra['concept'].startswith('disclosed_')
    assert extra['concept']==next(i for i in prior['items'] if i['source_name']=='资本公积')['concept']


def test_number_evidence_is_its_own_row_and_column_not_another_cell():
    md=report();results=extract_financial_data(md,no_model)
    for s in results:
        for i in s['items']:
            assert i['source_text'] in md
            assert i['raw_value'] in i['source_text']
            source='\n'.join(md.splitlines()[i['source_start_line']-1:i['source_end_line']])
            assert i['source_text'] in source
            assert i['source_text'].count('<tr>')==1
    income=next(s for s in results if s['scope']=='consolidated' and s['period']=='2026H1')
    assert next(i for i in income['items'] if i['concept']=='revenue')['raw_value']=='100'
    eps=next(i for i in income['items'] if '每股收益' in i['source_name'])
    assert eps['raw_unit']=='元/股' and eps['normalized_value']=='-0.0123'


def test_notes_column_is_not_mistaken_for_a_period():
    md='# 合成公司\n2026年半年度报告\n## 合并资产负债表\n编制单位：合成公司\n单位：元\n'+table(['项目','附注','期末余额','期初余额'],[['货币资金','七、1','100','80']])
    results=extract_financial_data(md,no_model)
    assert [s['items'][0]['raw_value'] for s in results]==['100','80']


def test_unsupported_rows_are_reported_as_partial_not_successfully_complete():
    md=report().replace('<td>100.01</td>','<td>无法识别</td>',1)
    results=extract_financial_data(md,no_model)
    assert results[0]['coverage']['status']=='partial'
    assert results[0]['coverage']['unreadable_cells']==1


def test_multiline_html_and_continuation_tables_retain_both_periods():
    md='# 合成公司\n2026年半年度报告\n## 合并资产负债表\n编制单位：合成公司\n单位：元\n'+table(['项目','期末余额','期初余额'],[['货币资金','100','80']])+'\n续表\n'+table(['项目','期末余额','期初余额'],[['资本公积','50','40']])
    md=md.replace('</tr>','</tr>\n')
    results=extract_financial_data(md,no_model)
    assert len(results)==2
    assert all(len(s['items'])==2 for s in results)
    assert all(i['source_start_line']==i['source_end_line'] for s in results for i in s['items'])


def test_unit_immediately_before_title_is_part_of_table_metadata():
    from leasedd.statement_tables import extract_statement_tables
    md=report().replace('## 母公司现金流量表\n单位：元','单位：元\n\n## 母公司现金流量表')
    result=extract_statement_tables(md)
    assert len(result)==12
    assert result[0]['coverage']['tables_parsed']==6
    assert sum(len(s['items']) for s in result)==38


def test_preceding_unit_does_not_jump_over_unrelated_text():
    from leasedd.statement_tables import extract_statement_tables
    md=report().replace('## 母公司现金流量表\n单位：元','单位：元\n其他说明\n## 母公司现金流量表')
    result=extract_statement_tables(md)
    assert result[0]['coverage']['status']=='partial'
