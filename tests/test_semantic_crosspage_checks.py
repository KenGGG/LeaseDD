from copy import deepcopy

from leasedd.document_structure import build_document_map
from leasedd.financial_semantics import validate_table


def fixture(groups, statement_type='balance_sheet', units=None, scopes=None):
    """Each group is a separate physical page table of one logical statement."""
    units = units or ['元'] * len(groups)
    scopes = scopes or ['consolidated'] * len(groups)
    period = '2025-12-31' if statement_type == 'balance_sheet' else '2025年度'
    markdown = '# 示例有限公司\n'
    for group, unit, scope in zip(groups, units, scopes):
        scope_name = '合并' if scope == 'consolidated' else '母公司'
        markdown += f'{scope_name}报表，币种：人民币，单位：{unit}\n'
        markdown += '<table><tr><td>项目</td><td>' + period + '</td></tr>'
        markdown += ''.join(f'<tr><td>{name}</td><td>{value}</td></tr>' for name, _, value in group)
        markdown += '</table>\n'
    document = build_document_map(markdown)
    blocks = [b for b in document['blocks'] if b['kind'] == 'table']
    proof = lambda quote, line: {'quote': quote, 'start_line': line, 'end_line': line}
    columns, rows = [], []
    for block, group, unit, scope in zip(blocks, groups, units, scopes):
        scope_name = '合并' if scope == 'consolidated' else '母公司'
        evidence = {'entity': proof('示例有限公司', 1), 'scope': proof(scope_name + '报表', block['start_line'] - 1), 'currency': proof('人民币', block['start_line'] - 1), 'unit': proof('单位：' + unit, block['start_line'] - 1), 'statement_type': proof(scope_name + '报表', block['start_line'] - 1), 'period': proof(period, block['start_line'])}
        columns.append({'block_id': block['id'], 'column': 2, 'label_column': 1, 'header_rows': [1], 'period': period, 'scope': scope, 'raw_unit': unit, 'evidence': evidence})
        for row, (name, concept, value) in enumerate(group, 2):
            rows.append({'block_id': block['id'], 'row': row, 'source_name': name, 'concept': concept, 'values': [{'column': 2, 'raw_value': value}]})
    meta = {'statement_type': statement_type, 'entity': '示例有限公司', 'scope': scopes[0], 'currency': 'CNY', 'raw_unit': units[0], 'evidence': {}, 'columns': columns}
    return document, [b['id'] for b in blocks], meta, {'rows': rows}


def test_crosspage_balance_merges_before_core_and_equation_checks():
    args = fixture([[('资产总计', 'total_assets', '200')], [('负债合计', 'total_liabilities', '80'), ('所有者权益合计', 'total_equity', '120')]])
    result = validate_table(*args)
    assert len(result['statements']) == 1
    statement = result['statements'][0]
    assert statement['source_start_line'] == 3
    assert statement['source_end_line'] == 5
    assert {i['evidence']['cell']['block_id'] for i in statement['items']} == set(args[1])
    assert result['coverage']['status'] == 'complete'
    assert result['checks'][0]['status'] == 'passed'
    assert not any(issue.startswith('missing_core:') for issue in result['issues'])


def test_crosspage_different_units_or_scopes_do_not_merge():
    groups = [[('资产总计', 'total_assets', '200')], [('负债合计', 'total_liabilities', '80'), ('所有者权益合计', 'total_equity', '120')]]
    for kwargs in [{'units': ['元', '万元']}, {'scopes': ['consolidated', 'parent']}]:
        result = validate_table(*fixture(groups, **kwargs))
        assert len(result['statements']) == 2
        assert result['coverage']['status'] == 'partial'
        assert not any(c['status'] == 'passed' for c in result['checks'])


def test_crosspage_balance_conflict_removes_all_involved_values():
    result = validate_table(*fixture([[('资产总计', 'total_assets', '201')], [('负债合计', 'total_liabilities', '80'), ('所有者权益合计', 'total_equity', '120')]]))
    assert len(result['statements']) == 1
    assert result['checks'][0]['status'] == 'conflict'
    assert all(i['normalized_value'] is None and i['evidence']['verification_state'] == 'CONFLICT' for i in result['statements'][0]['items'])


def test_income_total_profit_minus_tax_equals_net_profit():
    rows = [('营业收入', 'revenue', '500'), ('营业成本', 'cost', '300'), ('利润总额', 'total_profit', '100'), ('所得税费用', 'income_tax_expense', '20'), ('净利润', 'net_profit', '80')]
    result = validate_table(*fixture([rows[:3], rows[3:]], 'income_statement'))
    assert len(result['statements']) == 1
    assert result['coverage']['status'] == 'complete'
    check = next(c for c in result['checks'] if c['code'] == 'profit_less_tax_equals_net_profit')
    assert check['status'] == 'passed'
    rows[-1] = ('净利润', 'net_profit', '81')
    result = validate_table(*fixture([rows], 'income_statement'))
    items = {i['concept']: i for i in result['statements'][0]['items']}
    assert items['net_profit']['normalized_value'] is None
    assert items['total_profit']['normalized_value'] is None
    assert items['income_tax_expense']['normalized_value'] is None
    assert items['revenue']['status'] == 'source_verified'


def cash_rows():
    return [('经营现金流', 'net_operating_cash_flow', '100'), ('投资现金流', 'net_investing_cash_flow', '-40'), ('筹资现金流', 'net_financing_cash_flow', '-20'), ('汇率影响', 'exchange_rate_effect', '5'), ('现金净增加额', 'net_increase_in_cash', '45'), ('期初现金', 'beginning_cash_balance', '20'), ('期末现金', 'ending_cash_balance', '65')]


def test_cash_flow_equations_include_explicit_fx_and_beginning_balance():
    rows = cash_rows()
    result = validate_table(*fixture([rows[:3], rows[3:]], 'cash_flow_statement'))
    checks = {c['code']: c for c in result['checks']}
    assert checks['cash_flows_plus_fx_equal_net_increase']['status'] == 'passed'
    assert checks['opening_cash_plus_change_equals_ending_cash']['status'] == 'passed'
    assert result['coverage']['status'] == 'complete'
    assert all(i['status'] == 'source_verified' for i in result['statements'][0]['items'])


def test_missing_fx_does_not_assume_zero_even_when_three_flows_match_net_change():
    rows = cash_rows()
    rows = [r for r in rows if r[1] != 'exchange_rate_effect']
    rows = [(name, concept, '40' if concept == 'net_increase_in_cash' else '60' if concept == 'ending_cash_balance' else value) for name, concept, value in rows]
    result = validate_table(*fixture([rows], 'cash_flow_statement'))
    check = next(c for c in result['checks'] if c['code'] == 'cash_flows_plus_fx_equal_net_increase')
    assert check['status'] == 'gap'
    assert check['missing_concepts'] == ['exchange_rate_effect']
    assert result['coverage']['status'] == 'partial'


def test_cash_flow_conflict_clears_only_involved_evidence_values():
    rows = cash_rows()
    rows[4] = ('现金净增加额', 'net_increase_in_cash', '50')
    result = validate_table(*fixture([rows], 'cash_flow_statement'))
    check = next(c for c in result['checks'] if c['code'] == 'cash_flows_plus_fx_equal_net_increase')
    assert check['status'] == 'conflict'
    involved = {'net_operating_cash_flow', 'net_investing_cash_flow', 'net_financing_cash_flow', 'exchange_rate_effect', 'net_increase_in_cash'}
    assert all(i['normalized_value'] is None and i['status'] != 'source_verified' for i in result['statements'][0]['items'] if i['concept'] in involved)
