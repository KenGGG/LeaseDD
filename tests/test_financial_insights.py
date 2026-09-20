import copy
import hashlib
from decimal import Decimal

from leasedd.financial_analytics import financial_analytics
from leasedd.financial_notes import index_notes, note_blocks
from leasedd.statement_tables import concept_for
from leasedd.db import DocumentConversion
from test_m2_api import seed_finance, upload
from test_platform import env


def statement(table, period, values, **extra):
    return dict(id=table+period,document_id='doc',statement_type=table,entity='公司',scope='consolidated',currency='CNY',period=period,period_normalized=period,period_kind='instant' if table=='balance_sheet' else 'half_year',raw_unit='元',unit_scale='1',state='extracted',issues=[],items=[dict(id=table+period+c,concept=c,source_name=c,normalized_value=str(v),raw_value=str(v),raw_unit='元',status='source_verified',source_start_line=10,source_end_line=10) for c,v in values.items()],**extra)


def fixture():
    return [statement('balance_sheet','2026-06-30',dict(total_assets=1200,total_liabilities=600,total_equity=600,total_current_assets=500,total_current_liabilities=250,inventory=100,accounts_receivable=200)),statement('balance_sheet','2025-12-31',dict(total_assets=800,total_equity=400,inventory=100,accounts_receivable=200)),statement('income_statement','2026-01-01/2026-06-30',dict(revenue=1000,cost=600,net_profit=100)),statement('income_statement','2025-01-01/2025-06-30',dict(revenue=800,net_profit=-20))]


def metric(source,code,period='2026-01-01/2026-06-30',scope='consolidated'):
    group=next(g for g in financial_analytics(source)['groups'] if g['scope']==scope)
    column=next(p for p in group['periods'] if p['period']==period)
    return next(m for m in column['metrics'] if m['code']==code)


def test_exact_decimal_average_balances_reference_360_day_policy_and_evidence():
    source=fixture()
    for code,expected in [('gross_margin','40'),('debt_ratio','50'),('quick_ratio','160'),('roa','10'),('roe_total','20'),('inventory_turnover_days',str(Decimal(180)/6)),('revenue_growth','25'),('balance_difference','0')]:
        actual=metric(source,code)
        assert abs(Decimal(actual['value'])-Decimal(expected))<Decimal('1e-25')
        assert actual['status']=='pending_review'
        assert actual['inputs'] and all(i['item_id'] and i['document_id']=='doc' for i in actual['inputs'])
    assert Decimal(metric(source,'net_profit_growth')['value'])==600


def test_missing_opening_not_replaced_by_ending_and_scopes_do_not_mix():
    source=fixture()
    source[1]['scope']='parent'
    assert metric(source,'roa')['value'] is None
    assert '2025-12-31' in metric(source,'roa')['reason']
    assert metric(source,'debt_ratio')['value']=='50.0'


def test_conflicts_unverified_values_and_zero_denominator_block_calculation():
    source=fixture()
    duplicate=copy.deepcopy(source[0]);duplicate['items'][0]['normalized_value']='999'
    assert '冲突' in metric(source+[duplicate],'debt_ratio')['reason']
    source[0]['items'][0]['normalized_value']='0'
    assert metric(source,'debt_ratio')['reason']=='分母为零'
    source[0]['items'][0]['status']='pending_confirmation'
    assert metric(source,'debt_ratio')['value'] is None
    source=fixture()
    for s in source:
        for i in s['items']:i['status']='human_confirmed'
    assert metric(source,'roa')['status']=='confirmed_inputs'
    source[0]['items'][0]['status']='human_rejected'
    assert metric(source,'debt_ratio')['value'] is None


def test_halfyear_never_uses_single_quarter_cash_flow_or_previous_year():
    source=fixture()+[statement('cash_flow_statement','2026-04-01/2026-06-30',dict(net_operating_cash_flow=9000))]
    source[-1]['period_kind']='quarter'
    assert metric(source,'net_operating_cash_flow')['value'] is None
    source[3]['period_kind']='quarter'
    assert metric(source,'revenue_growth')['value'] is None


def test_per_share_unit_and_unknown_period_are_not_treated_as_money():
    source=fixture()
    concept=concept_for('基本每股收益','income_statement')
    item=dict(source[2]['items'][0],id='eps',concept=concept,normalized_value='0.1234',raw_unit='元/股')
    source[2]['items'].append(item)
    assert metric(source,concept)['value']=='0.1234'
    item['raw_unit']='元'
    assert metric(source,concept)['reason']=='输入单位不一致'
    source[2]['period_kind']=None
    assert metric(source,'gross_margin')['value'] is None


MARKDOWN='''## 七、合并财务报表项目注释
## 1、货币资金
单位：元
<table><tr><td rowspan="2">银行存款</td><td colspan="2">100</td></tr><tr><td>80</td><td>20</td></tr></table>
## （1） 受限说明
资金受到限制，见协议。
## 2、应收账款
债务人为合成客户甲。
## 十九、母公司财务报表主要项目注释
## 1、应收账款
母公司余额。
'''


def test_notes_preserve_parent_scope_lines_nested_content_and_table_spans():
    notes=index_notes(MARKDOWN,'doc','conv')
    receivables=[n for n in notes if n['title']=='1、应收账款']
    assert receivables[0]['scope']=='parent'
    money=next(n for n in notes if n['title']=='1、货币资金')
    assert money['scope']=='consolidated' and money['start_line']==2
    blocks=note_blocks(money['text'])
    row=next(b for b in blocks if b['type']=='table')['rows'][0]
    assert row[0]['rowspan']==2 and row[1]['colspan']==2
    assert '银行存款'==row[0]['text']
    assert index_notes('## 普通合同\n没有财务附注','doc','conv')==[]
    assert note_blocks('<table><tr><td><img src=x onerror=alert(1)>文本</td></tr></table>')[0]['rows'][0][0]['text']=='文本'


def test_insights_endpoints_permissions_search_and_hash_validation(env):
    app,c,pid,login=env
    doc=upload(c,pid)
    cid,_,_=seed_finance(app,pid,doc,'writer')
    with app.state.db.begin() as db:
        conv=db.get(DocumentConversion,cid)
        path=app.state.root/conv.markdown_path
        path.write_text(MARKDOWN)
        conv.markdown_sha256=hashlib.sha256(MARKDOWN.encode()).hexdigest()
    root=f'/api/projects/{pid}'
    assert c.get(root+'/financial-analytics').status_code==200
    notes=c.get(root+'/financial-notes').json()['notes']
    assert notes and 'text' not in notes[0]
    found=c.get(root+'/financial-notes',params={'q':'合成客户甲'}).json()['notes']
    assert len(found)==1 and found[0]['title']=='2、应收账款'
    assert c.get(root+'/financial-notes/'+found[0]['id']).json()['blocks']
    assert c.get(root+'/financial-notes/invalid').status_code==404
    login('outsider','long-password-123')
    for endpoint in ['/financial-analytics','/financial-notes','/financial-notes/'+found[0]['id']]:
        assert c.get(root+endpoint).status_code==403
    login('writer','long-password-123')
    path.write_text(MARKDOWN+'篡改')
    for endpoint in ['/financial-analytics','/financial-notes','/financial-notes/'+found[0]['id']]:
        assert c.get(root+endpoint).status_code==409


def test_supplements_extract_reported_percent_and_share_count_without_using_capital():
    from leasedd.financial_supplements import supplementary_statements
    source=fixture()
    markdown='''公司 2026 年半年度报告
<table><tr><td></td><td>本报告期</td><td>上年同期</td></tr><tr><td>加权平均净资产收益率</td><td>-2.49%</td><td>-8.48%</td></tr></table>
<table><tr><td></td><td>本次变动前</td><td>本次变动后</td></tr><tr><td>三、股份总数</td><td>900</td><td>100%</td><td>1000</td><td>100%</td></tr></table>
## 1、合并资产负债表
<table><tr><td>股本</td><td>999999</td></tr></table>
'''
    supplement=supplementary_statements(markdown,'doc','conversion',source)
    items=[i for s in supplement for i in s['items']]
    assert all(i['supplemental'] and i['id'].startswith('sup_') for i in items)
    assert [i['normalized_value'] for i in items if i['concept']=='ordinary_share_count']==['1000','900']
    assert Decimal(metric(source+supplement,'roe')['value'])==Decimal('-2.49')
    assert metric(source+supplement,'roe')['status']=='pending_review'
    source[0]['scope']='parent';source[1]['scope']='parent';source[2]['scope']='parent';source[3]['scope']='parent'
    assert supplementary_statements(markdown,'doc','conversion',source)==[]


def test_note_matrix_expands_inventory_headers_and_aggregates_disclosed_classes():
    from leasedd.financial_notes import notes_matrix
    markdown='''## 七、合并财务报表项目注释
## 1、存货
单位：万元
<table><tr><td rowspan="2">项目</td><td colspan="3">期末余额</td><td colspan="3">期初余额</td></tr><tr><td>账面余额</td><td>跌价准备</td><td>账面价值</td><td>账面余额</td><td>跌价准备</td><td>账面价值</td></tr><tr><td>在产品</td><td>12</td><td>2</td><td>10</td><td>8</td><td>1</td><td>7</td></tr><tr><td>半成品</td><td>30</td><td>5</td><td>25</td><td>20</td><td>3</td><td>17</td></tr><tr><td>空白类别</td><td></td><td></td><td></td><td></td><td></td><td></td></tr></table>
'''
    notes=index_notes(markdown,'doc','conversion')
    for n in notes:n['report_end']='2026-06-30'
    matrix=notes_matrix(notes,'存货')
    assert matrix['periods']==['2026-06-30','2025-12-31']
    assert [r['label'] for r in matrix['rows']]==['在产品及半成品','期末余额','跌价准备']
    assert matrix['rows'][0]['cells'][0]['value']=='350000'
    assert matrix['rows'][0]['cells'][1]['value']=='240000'
    assert notes_matrix(notes,'存货','parent')['rows']==[]
    changed=copy.deepcopy(notes)
    for n in changed:n['text']=n['text'].replace('<td>25</td>','<td>26</td>')
    assert notes_matrix(notes+changed,'存货')['rows'][0]['cells'][0]['conflict'] is True
    assert notes_matrix(notes+changed,'存货')['rows'][0]['cells'][0]['value'] is None


def test_audit_matrix_uses_explicit_disclosure_and_does_not_claim_halfyear_audited():
    from leasedd.financial_notes import notes_matrix
    notes=index_notes('## 一、审计报告\n<table><tr><td>审计意见类型</td><td>标准的无保留意见</td></tr><tr><td>审计报告签署日期</td><td>2026年04月23日</td></tr></table>','doc','conversion')
    for n in notes:n['report_end']='2025-12-31'
    result=notes_matrix(notes,'审计报告')
    assert result['rows'][0]['cells'][0]['value']=='2026-04-23'
    assert result['rows'][1]['cells'][0]['value']=='标准无保留'
    for n in notes:n['report_end']='2026-06-30'
    assert notes_matrix(notes,'审计报告')['rows']==[]


def test_note_matrix_api_keeps_entities_separate_and_supplement_sources_read_only(env):
    app,c,pid,login=env
    for number,entity in enumerate(['甲公司','乙公司']):
        doc=upload(c,pid,entity+'.pdf')
        cid,_,_=seed_finance(app,pid,doc,'writer')
        markdown=f'''{entity} 2026年半年度报告
编制单位：{entity}
<table><tr><td></td><td>本报告期</td><td>上年同期</td></tr><tr><td>加权平均净资产收益率</td><td>10%</td><td>8%</td></tr></table>
## 合并资产负债表
## 七、合并财务报表项目注释
## 1、货币资金
单位：元
<table><tr><td>项目</td><td>期末余额</td><td>期初余额</td></tr><tr><td>库存现金</td><td>{100+number}</td><td>80</td></tr></table>
'''
        with app.state.db.begin() as db:
            conversion=db.get(DocumentConversion,cid)
            (app.state.root/conversion.markdown_path).write_text(markdown)
            conversion.markdown_sha256=hashlib.sha256(markdown.encode()).hexdigest()
    root=f'/api/projects/{pid}'
    result=c.get(root+'/financial-notes-matrix',params={'category':'货币资金','entity':'甲公司'}).json()
    assert set(result['entities'])=={'甲公司','乙公司'}
    assert result['rows'][0]['cells'][0]['value']=='100'
    assert result['rows'][0]['cells'][0]['conflict'] is False
    result=c.get(root+'/financial-notes-matrix',params={'category':'货币资金','entity':'乙公司'}).json()
    assert result['rows'][0]['cells'][0]['value']=='101'
    items=[i for s in c.get(root+'/financial-statements').json() for i in s['items'] if i.get('supplemental')]
    assert items
    iid=items[0]['id']
    assert c.get(root+'/financial-items/'+iid+'/source').status_code==200
    assert c.post(root+'/financial-items/'+iid+'/confirm',json={'decision':'confirm','reason':'不允许伪造持久化确认'}).status_code==404
    login('outsider','long-password-123')
    assert c.get(root+'/financial-items/'+iid+'/source').status_code==403
    assert c.get(root+'/financial-notes-matrix',params={'category':'货币资金'}).status_code==403
