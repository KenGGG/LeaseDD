from leasedd.finance_extract import validate_extracted_statement
from leasedd.financial_presentation import align_balance_period
from leasedd.financial_notes import index_notes, notes_matrix


def test_opening_balance_maps_to_previous_year_end_and_retains_source_date():
    original={'statement_type':'balance_sheet','period':'2023-01-01','period_normalized':'2023-01-01','period_kind':'instant'}
    result=align_balance_period(original)
    assert result['period_normalized']=='2022-12-31'
    assert result['period']=='2023-01-01'
    assert original['period_normalized']=='2023-01-01'
    assert result['period_basis']=='opening_balance'


def test_alignment_never_relabels_flow_periods_or_arbitrary_dates():
    for kind,date in [('income_statement','2023-01-01'),('cash_flow_statement','2023-01-01'),('balance_sheet','2023-06-01')]:
        original=dict(statement_type=kind,period=date,period_normalized=date,period_kind='instant')
        assert align_balance_period(original)==original


def test_inner_numbered_heading_does_not_remove_notes_scope():
    md='''# 七、合并财务报表项目注释
## 18、长期股权投资
### 二、联营企业
## 31、所有权或使用权受到限制的资产
单位：元
<table><tr><td>项目</td><td>期末余额</td><td>期初余额</td></tr><tr><td>货币资金</td><td>100</td><td>80</td></tr></table>
## 八、研发支出
## 十九、母公司财务报表主要项目注释
## 1、应收账款
'''
    notes=index_notes(md,'doc','conversion')
    restricted=next(n for n in notes if '受到限制' in n['title'])
    assert restricted['scope']=='consolidated'
    assert restricted['section']=='七、合并财务报表项目注释'
    parent=next(n for n in notes if n['title']=='1、应收账款')
    assert parent['scope']=='parent'
