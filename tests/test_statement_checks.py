from copy import deepcopy

from leasedd.statement_checks import evaluate_statement_checks


EXPECTED = {
    'assets_equal_liabilities_equity',
    'current_plus_noncurrent_assets_equal_assets',
    'current_plus_noncurrent_liabilities_equal_liabilities',
    'profit_less_tax_equals_net_profit',
    'operating_plus_nonoperating_equals_total_profit',
    'cash_flows_plus_fx_equal_net_increase',
    'opening_cash_plus_change_equals_ending_cash',
}


def item(concept, value, raw=None, status='source_verified', mapping='mapped', increment='1', unit='元'):
    return {'id': concept, 'concept': concept, 'raw_value': raw or value,
            'normalized_value': value, 'raw_unit': unit, 'status': status,
            'evidence': {'mapping_state': mapping, 'verification_state': 'VERIFIED',
                         'source_increment': increment,
                         'cell': {'block_id': 'b', 'row': len(concept), 'column': 2}}}


def statement(statement_type, items):
    return {'statement_type': statement_type, 'entity': '示例公司',
            'scope': 'consolidated', 'period_normalized': '2025-12-31',
            'currency': 'CNY', 'raw_unit': '元', 'unit_scale': '1', 'items': items}


def test_registry_contains_exactly_seven_fixed_equations():
    rows = [
        item('total_assets', '300'), item('total_liabilities', '100'), item('total_equity', '200'),
        item('total_current_assets', '120'), item('total_noncurrent_assets', '180'),
        item('total_current_liabilities', '40'), item('total_noncurrent_liabilities', '60'),
    ]
    income = [item('total_profit', '80'), item('income_tax_expense', '20'), item('net_profit', '60'),
              item('operating_profit', '75'), item('nonoperating_income', '10'), item('nonoperating_expense', '5')]
    cash = [item('net_operating_cash_flow', '100'), item('net_investing_cash_flow', '-40'),
            item('net_financing_cash_flow', '-20'), item('exchange_rate_effect', '5'),
            item('net_increase_in_cash', '45'), item('beginning_cash_balance', '20'),
            item('ending_cash_balance', '65')]
    checks = (evaluate_statement_checks(statement('balance_sheet', rows)) +
              evaluate_statement_checks(statement('income_statement', income)) +
              evaluate_statement_checks(statement('cash_flow_statement', cash)))
    assert {check['code'] for check in checks} == EXPECTED
    assert all(check['status'] == 'passed' for check in checks)


def test_missing_and_unverified_inputs_are_distinct_and_never_assumed_zero():
    rows = [item('total_assets', '300'), item('total_liabilities', '100')]
    check = evaluate_statement_checks(statement('balance_sheet', rows))[0]
    assert check['status'] == 'not_checked_missing_disclosure'
    assert check['missing_concepts'] == ['total_equity']
    rows.append(item('total_equity', '200', status='pending_confirmation'))
    check = evaluate_statement_checks(statement('balance_sheet', rows))[0]
    assert check['status'] == 'not_checked_unverified_source'
    assert check['missing_concepts'] == []


def test_duplicate_or_unmapped_candidates_are_not_arbitrarily_selected():
    base = [item('total_assets', '300'), item('total_liabilities', '100'), item('total_equity', '200')]
    duplicate = deepcopy(base) + [item('total_assets', '300')]
    assert evaluate_statement_checks(statement('balance_sheet', duplicate))[0]['status'] == 'not_checked_unverified_source'
    unmapped = deepcopy(base)
    unmapped[0]['evidence']['mapping_state'] = 'unmapped'
    assert evaluate_statement_checks(statement('balance_sheet', unmapped))[0]['status'] == 'not_checked_unverified_source'


def test_tolerance_sums_half_of_every_disclosed_increment_after_unit_scaling():
    rows = [item('total_profit', '30000', '3', increment='1', unit='万元'),
            item('income_tax_expense', '12000', '1.2', increment='0.1', unit='万元'),
            item('net_profit', '23400', '2.34', increment='0.01', unit='万元')]
    # (0.5 + 0.05 + 0.005) 万元 = 5550 yuan.
    check = evaluate_statement_checks(statement('income_statement', rows))[0]
    assert check['tolerance'] == '5550.00'
    assert check['difference'] == '-5400'
    assert check['status'] == 'passed'
    rows[0]['normalized_value'] = '29850'
    check = evaluate_statement_checks(statement('income_statement', rows))[0]
    assert check['difference'] == '-5550'
    assert check['status'] == 'passed'
    rows[0]['normalized_value'] = '29849'
    assert evaluate_statement_checks(statement('income_statement', rows))[0]['status'] == 'conflict'


def test_formula_conflict_never_mutates_source_values_or_states():
    rows = [item('total_assets', '302'), item('total_liabilities', '100'), item('total_equity', '200')]
    before = deepcopy(rows)
    check = evaluate_statement_checks(statement('balance_sheet', rows))[0]
    assert check['status'] == 'conflict'
    assert check['involved_concepts'] == ['total_assets', 'total_liabilities', 'total_equity']
    assert rows == before
