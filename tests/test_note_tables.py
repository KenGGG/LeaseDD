from decimal import Decimal
from leasedd.financial_notes import index_notes,notes_matrix


def notes(text):
    result=index_notes('财务附注中报表的单位为：元\n'+text,'doc','conv')
    for n in result:n['report_end']='2025-12-31'
    return result


def test_customer_supplier_tables_inherit_combined_topic_and_keep_percentage_units():
    ns=notes('''## （8） 主要销售客户和主要供应商情况
<table><tr><td>序号</td><td>客户名称</td><td>销售额(元)</td><td>占年度销售总额比例</td></tr><tr><td>1</td><td>A</td><td>1200</td><td>12%</td></tr></table>
## 主要客户其他情况说明
<table><tr><td>序号</td><td>供应商名称</td><td>采购额(元)</td><td>占年度采购总额比例</td></tr><tr><td>1</td><td>B</td><td>500</td><td>5%</td></tr><tr><td>合计</td><td>--</td><td>500</td><td>5%</td></tr></table>''')
    m=notes_matrix(ns,'主要供应商')
    assert m['layout']=='records'
    assert m['records'][0]['cells'][1]['value']=='500'
    assert m['columns'][2]['unit']=='%'
    assert m['records'][1]['cells'][0]['value']=='合计'
    assert not notes_matrix(ns,'主要供应商','parent')['records']


def test_restricted_assets_uses_book_value_not_balance_or_cash_equivalent_restrictions():
    ns=notes('''## 七、合并财务报表项目注释
## 31、所有权或使用权受到限制的资产
<table><tr><td rowspan="2">项目</td><td colspan="2">期末</td><td colspan="2">期初</td></tr><tr><td>账面余额</td><td>账面价值</td><td>账面余额</td><td>账面价值</td></tr><tr><td>固定资产</td><td>1000</td><td>800</td><td>900</td><td>700</td></tr></table>
## （5） 使用范围受限但仍属于现金及现金等价物列示的情况
<table><tr><td>项目</td><td>本期金额</td><td>上期金额</td></tr><tr><td>募集资金</td><td>999</td><td>888</td></tr></table>''')
    m=notes_matrix(ns,'受限资产')
    assert m['periods']==['2025-12-31','2024-12-31']
    assert len(m['rows'])==1
    assert [c['value'] for c in m['rows'][0]['cells']]==['800','700']


def test_age_aliases_merge_annual_columns_without_adding_totals_or_provisions():
    ns=notes('''## 七、合并财务报表项目注释
## 5、应收账款
单位：万元
<table><tr><td>账龄</td><td>期末账面余额</td><td>期初账面余额</td></tr><tr><td>1年以内(含1年)</td><td>100</td><td>80</td></tr><tr><td>1至2年</td><td>0</td><td></td></tr><tr><td>合计</td><td>100</td><td>80</td></tr></table>''')
    m=notes_matrix(ns,'应收账款账龄分析')
    assert m['rows'][0]['label']=='1年内'
    assert Decimal(m['rows'][0]['cells'][0]['value'])==1000000
    assert next(r for r in m['rows'] if r['label']=='坏账准备')['cells'][0]['value'] is None
    assert next(r for r in m['rows'] if r['label']=='1-2年')['cells'][0]['value']=='0'


def test_nonrecurring_uses_explicit_years_and_deductions_not_note_report_year():
    ns=notes('''## 九、非经常性损益项目及金额
单位：元
<table><tr><td>项目</td><td>2025 年金额</td><td>2024 年金额</td></tr><tr><td>非流动资产处置损益</td><td>123</td><td>-456</td></tr><tr><td>减：所得税影响额</td><td>-10</td><td>20</td></tr></table>''')
    m=notes_matrix(ns,'非经常性损益')
    assert m['periods']==['2025-12-31','2024-12-31']
    assert [c['value'] for c in next(r for r in m['rows'] if r['label']=='所得税影响数')['cells']]==['10','-20']


def test_conflicting_note_values_never_choose_one_silently():
    ns=notes('''## 七、合并财务报表项目注释
## 1、货币资金
单位：元
<table><tr><td>项目</td><td>期末余额</td></tr><tr><td>库存现金</td><td>100</td></tr></table>''')
    m=notes_matrix(ns+[{**ns[-1],'id':'other','text':ns[-1]['text'].replace('100','101')}],'货币资金')
    assert m['rows'][0]['cells'][0]['conflict']
    assert m['rows'][0]['cells'][0]['value'] is None


def test_pdf_continuation_rows_rejoin_only_proven_numeric_fragments():
    from leasedd.financial_notes import join_wrapped_rows
    from leasedd.note_tables import number
    assert join_wrapped_rows([['固定资产','654,928,2','509,352,8'],['','96.90','17.46']])==[['固定资产','654,928,296.90','509,352,817.46']]
    assert join_wrapped_rows([['委托加工物资','30,000,514.4','26,502,389.4'],['','6','2']])==[['委托加工物资','30,000,514.46','26,502,389.42']]
    independent=[['合计','100.00'],['','20.00']]
    assert join_wrapped_rows(independent)==independent
    assert number('509,352,8') is None
