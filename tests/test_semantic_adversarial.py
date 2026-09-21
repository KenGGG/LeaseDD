"""Adversarial evidence checks: exact numbers are insufficient without metadata."""
from copy import deepcopy
import pytest

from leasedd.document_structure import build_document_map
from leasedd.financial_semantics import TableUnderstanding, _merge_statement_fragments, normalized_period, validate_table


def fixture(header='2025-12-31', prefix=None):
    prefix = prefix or '# 示例有限公司\n合并报表，币种：人民币，单位：万元\n'
    table = '<table><tr><td>项目</td><td>' + header + '</td><td>2024-12-31</td></tr><tr><td>货币资金</td><td>10</td><td>9</td></tr><tr><td>资产总计</td><td>200</td><td>150</td></tr><tr><td>负债合计</td><td>80</td><td>50</td></tr><tr><td>所有者权益合计</td><td>120</td><td>100</td></tr></table>'
    document = build_document_map(prefix + table)
    block = [b for b in document['blocks'] if b['kind'] == 'table'][-1]
    bid = block['id']
    proof = lambda quote, line=2: {'start_line': line, 'end_line': line, 'quote': quote}
    metadata = {'statement_type': 'balance_sheet', 'entity': '示例有限公司', 'scope': 'consolidated', 'currency': 'CNY', 'raw_unit': '万元', 'evidence': {'entity': proof('示例有限公司', 1), 'scope': proof('合并报表'), 'currency': proof('人民币'), 'unit': proof('单位：万元'), 'statement_type': proof('合并报表')}, 'columns': [{'block_id': bid, 'column': column, 'label_column': 1, 'header_rows': [1], 'raw_header': label, 'period': period, 'evidence': {'period': proof(label, block['start_line'])}} for column, period, label in [(2, '2025-12-31', header), (3, '2024-12-31', '2024-12-31')]]}
    rows = []
    for row, (name, concept, values) in enumerate([('货币资金', 'cash', ['10', '9']), ('资产总计', 'total_assets', ['200', '150']), ('负债合计', 'total_liabilities', ['80', '50']), ('所有者权益合计', 'total_equity', ['120', '100'])], 2):
        rows.append({'block_id': bid, 'row': row, 'source_name': name, 'concept': concept, 'values': [{'column': column, 'raw_value': value} for column, value in zip([2, 3], values)]})
    return document, [bid], metadata, {'rows': rows}


def test_smaller_unit_cannot_match_inside_larger_source_unit():
    document, ids, metadata, rows = fixture()
    metadata['raw_unit'] = '元'
    result = validate_table(document, ids, metadata, rows)
    assert all(item['status'] != 'source_verified' for statement in result['statements'] for item in statement['items'])


def test_qualified_full_date_header_cannot_pass_another_date_in_same_year():
    document, ids, metadata, rows = fixture(header='2025-06-30期末余额')
    result = validate_table(document, ids, metadata, rows)
    assert all(item['status'] != 'source_verified' for item in result['statements'][0]['items'])


def test_adjacent_table_scope_evidence_cannot_override_current_table_scope():
    prefix = '# 示例有限公司\n合并报表，币种：人民币，单位：万元\n<table><tr><td>其他表</td><td>1</td></tr></table>\n母公司报表，币种：人民币，单位：万元\n'
    document, ids, metadata, rows = fixture(prefix=prefix)
    result = validate_table(document, ids, metadata, rows)
    assert all(item['status'] != 'source_verified' for statement in result['statements'] for item in statement['items'])


def test_repeated_quote_does_not_authorize_wrong_source_line_for_unit():
    prefix = '# 示例有限公司\n合并报表，币种：人民币，单位：元\n<table><tr><td>其他表</td><td>1</td></tr></table>\n合并报表，币种：人民币，单位：万元\n'
    document, ids, metadata, rows = fixture(prefix=prefix)
    metadata['raw_unit'] = '元'
    metadata['evidence']['unit'] = {'start_line': 2, 'end_line': 2, 'quote': '元'}
    result = validate_table(document, ids, metadata, rows)
    assert all(item['status'] != 'source_verified' for statement in result['statements'] for item in statement['items'])


def test_missing_entire_numeric_column_is_not_complete_coverage():
    document, ids, metadata, rows = fixture()
    metadata['columns'] = metadata['columns'][:1]
    result = validate_table(document, ids, metadata, rows)
    assert result['coverage']['status'] == 'partial'
    assert result['coverage']['numeric_cells'] == 8


def test_model_cannot_hide_numeric_data_row_by_declaring_it_a_header():
    document, ids, metadata, rows = fixture()
    for column in metadata['columns']:
        column['header_rows'] = [1, 2]
    result = validate_table(document, ids, metadata, rows)
    assert result['coverage']['status'] == 'partial'


def test_duplicate_metadata_column_is_not_a_second_independent_verified_statement():
    document, ids, metadata, rows = fixture()
    metadata['columns'].append(deepcopy(metadata['columns'][0]))
    result = validate_table(document, ids, metadata, rows)
    assert result['coverage']['status'] == 'partial'
    # Every source numeric cell is counted once, even if the model repeats it.
    assert result['coverage']['numeric_cells'] == 8


def test_unselected_source_name_column_cannot_substitute_for_wrong_row_concept():
    # This test is deliberately limited: semantic concept selection still needs
    # an independent benchmark; source matching alone cannot validate semantics.
    document, ids, metadata, rows = fixture()
    metadata['columns'][0]['label_column'] = 3
    rows['rows'][0]['source_name'] = '9'
    rows['rows'][0]['concept'] = 'cash'
    result = validate_table(document, ids, metadata, rows)
    assert result['statements'][0]['items'][0]['status'] != 'source_verified'


@pytest.mark.parametrize('kind', ['instant', 'year', 'quarter'])
def test_explicit_half_year_duration_cannot_be_labeled_incompatible_period_kind(kind):
    with pytest.raises(ValueError):
        normalized_period('2025-01-01/2025-06-30', kind, 'income_statement')


def test_out_of_bounds_model_row_is_not_silently_accepted_as_complete():
    document, ids, metadata, rows = fixture()
    extra = deepcopy(rows['rows'][0])
    extra['row'] = 500
    rows['rows'].append(extra)
    result = validate_table(document, ids, metadata, rows)
    assert result['coverage']['status'] == 'partial'


def test_table_contract_preserves_raw_headers_and_declares_non_amount_columns():
    _, _, metadata, _ = fixture()
    for column in metadata['columns']:
        column['raw_header'] = column['period']
    metadata['non_amount_columns'] = [{
        'block_id': metadata['columns'][0]['block_id'],
        'column': 4,
        'header_rows': [1],
        'raw_header': '附注',
        'kind': 'note_reference',
        'evidence': {'start_line': 3, 'end_line': 3, 'quote': '附注'},
    }]
    parsed = TableUnderstanding.model_validate(metadata)
    assert parsed.columns[0].raw_header == '2025-12-31'
    assert parsed.non_amount_columns[0].kind == 'note_reference'


def test_validated_note_column_is_not_missing_amount_but_real_amount_still_is():
    markdown = '# 示例有限公司\n合并资产负债表，币种：人民币，单位：万元\n<table><tr><td>项目</td><td>附注</td><td>2025-12-31</td><td>2024-12-31</td></tr><tr><td>资产总计</td><td>六、1</td><td>200</td><td>150</td></tr></table>'
    document = build_document_map(markdown)
    block = next(b for b in document['blocks'] if b['kind'] == 'table')
    proof = lambda quote, line=2: {'start_line': line, 'end_line': line, 'quote': quote}
    metadata = {
        'statement_type': 'balance_sheet', 'entity': '示例有限公司',
        'scope': 'consolidated', 'currency': 'CNY', 'raw_unit': '万元',
        'evidence': {'entity': proof('示例有限公司', 1), 'scope': proof('合并资产负债表'),
                     'currency': proof('人民币'), 'unit': proof('单位：万元'),
                     'statement_type': proof('合并资产负债表')},
        'columns': [{'block_id': block['id'], 'column': 3, 'label_column': 1,
                     'header_rows': [1], 'raw_header': '2025-12-31',
                     'period': '2025-12-31',
                     'evidence': {'period': proof('2025-12-31', block['start_line'])}}],
        'non_amount_columns': [{'block_id': block['id'], 'column': 2,
                                'header_rows': [1], 'raw_header': '附注',
                                'kind': 'note_reference',
                                'evidence': proof('附注', block['start_line'])}],
    }
    rows = {'rows': [{'block_id': block['id'], 'row': 2, 'source_name': '资产总计',
                      'concept': 'total_assets', 'values': [{'column': 3, 'raw_value': '200'}]}]}
    result = validate_table(document, [block['id']], metadata, rows)
    assert 'non_amount_column_overlap' not in result['issues']
    assert 'unmapped_numeric_column' in result['issues']  # column 4 remains a real omitted amount


def test_non_amount_column_cannot_overlap_label_or_amount_column():
    document, ids, metadata, rows = fixture()
    for column in metadata['columns']:
        column['raw_header'] = column['period']
    metadata['non_amount_columns'] = [{
        'block_id': ids[0], 'column': 2, 'header_rows': [1],
        'raw_header': '2025-12-31', 'kind': 'other',
        'evidence': {'start_line': document['blocks'][-1]['start_line'],
                     'end_line': document['blocks'][-1]['start_line'], 'quote': '2025-12-31'},
    }]
    result = validate_table(document, ids, metadata, rows)
    assert 'non_amount_column_overlap' in result['issues']
    assert all(statement['source_status'] == 'needs_review' for statement in result['statements'])
    assert all('non_amount_column_overlap' in statement['source_issues'] for statement in result['statements'])


def test_adjusted_opening_and_closing_columns_never_merge_by_normalized_date():
    def fragment(period, raw_header, value):
        return {'statement_type': 'balance_sheet', 'entity': '示例有限公司',
                'scope': 'consolidated', 'currency': 'CNY', 'period_kind': 'instant',
                'raw_unit': '万元', 'period': period, 'period_normalized': '2024-12-31',
                'raw_header': raw_header, 'issues': [], 'source_start_line': 1,
                'source_end_line': 1,
                'items': [{'normalized_value': value,
                           'evidence': {'cell': {'block_id': raw_header}}}]}
    result = _merge_statement_fragments([
        fragment('2025年1月1日（调整前）', '2025年1月1日（调整前）', '100'),
        fragment('2024年12月31日（调整后）', '2024年12月31日（调整后）', '101'),
    ])
    assert len(result) == 2
