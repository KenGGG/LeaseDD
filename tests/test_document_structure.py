"""Physical structure and evidence only: no financial classification rules."""
import pytest

from leasedd.document_structure import build_document_map, get_cell


def tables(document):
    return [block for block in document['blocks'] if block['kind'] == 'table']


def test_html_merged_headers_preserve_unique_physical_cells_and_exact_lines():
    markdown = '# A report\n## Statement\nUnit: thousands\n<table>\n<tr><th rowspan="2">Item</th><th colspan="2">Period</th></tr>\n<tr><th>Current</th><th>Prior</th></tr>\n<tr><td>A &amp; B</td><td>12,300.00</td><td>12,300.00</td></tr>\n</table>\nEnd of table\n'
    document = build_document_map(markdown)
    block = tables(document)[0]
    assert (block['start_line'], block['end_line']) == (4, 8)
    assert [h['text'] for h in block['headings']] == ['A report', 'Statement']
    assert 'Unit: thousands' in block['before']
    assert 'End of table' in block['after']
    assert block['rows'] == [['Item', 'Period', 'Period'], ['Item', 'Current', 'Prior'], ['A & B', '12,300.00', '12,300.00']]
    assert len(block['cells']) == 7
    assert get_cell(document, block['id'], 1, 2)['id'] == get_cell(document, block['id'], 1, 3)['id']
    assert get_cell(document, block['id'], 2, 1)['row'] == 1
    current = get_cell(document, block['id'], 3, 2)
    prior = get_cell(document, block['id'], 3, 3)
    assert current['id'] != prior['id']
    assert current['start_line'] == current['end_line'] == 7
    assert current['raw'] == '<td>12,300.00</td>'
    assert markdown[current['start_offset']:current['end_offset']] == current['raw']
    assert current['block_id'] == block['id']
    assert block['header_rows'] == [1, 2]


def test_markdown_pipes_escaped_pipes_inline_code_and_alignment_are_physical():
    markdown = 'Title\n=====\nSome context\n| Name | This | Previous |\n| :--- | ---: | ---: |\n| a\\|b | 100 | 100 |\n| `x|y` | — | 0 |\n\nClosing words'
    document = build_document_map(markdown)
    block = tables(document)[0]
    assert block['format'] == 'markdown'
    assert block['rows'] == [['Name', 'This', 'Previous'], ['a|b', '100', '100'], ['`x|y`', '—', '0']]
    assert block['header_rows'] == [1]
    assert (block['start_line'], block['end_line']) == (4, 7)
    assert block['headings'][0]['text'] == 'Title'
    cell = get_cell(document, block['id'], 2, 1)
    assert cell['raw'] == ' a\\|b '
    assert cell['start_line'] == cell['end_line'] == 6
    assert cell['text'] == 'a|b'
    assert markdown[cell['start_offset']:cell['end_offset']] == cell['raw']
    assert not any('---' in cell['text'] for cell in block['cells'])


def test_cross_page_tables_stay_separate_and_repeated_values_have_unique_ids():
    table = '<table><tr><td>Category</td><td>Period</td></tr><tr><td>A</td><td>7</td></tr></table>'
    markdown = '## Unusual heading\n' + table + '\n\nPage 7\n' + table + '\n'
    document = build_document_map(markdown)
    first, second = tables(document)
    assert first['rows'] == second['rows']
    assert first['id'] != second['id']
    assert first['cells'][3]['id'] != second['cells'][3]['id']
    assert first['id'] == tables(build_document_map(markdown))[0]['id']
    assert 'Page 7' in second['before']
    assert not any('statement_type' in block for block in document['blocks'])
    assert not any('rows' in entry for entry in document['map'])


def test_plain_text_unstructured_ocr_and_code_fences_are_not_guessed_tables():
    markdown = '# Scanned note\nAmounts   2025   2024\nAlpha      12     10\n\n```example\n| A | B |\n| --- | --- |\n| 1 | 2 |\n<table><tr><td>9</td></tr></table>\n```\n'
    document = build_document_map(markdown)
    assert not tables(document)
    assert any('Alpha      12     10' in block['text'] for block in document['blocks'] if block['kind'] == 'text')
    assert ''.join(block['text'] for block in document['blocks']) == markdown


def test_multiline_cell_and_multiple_inline_tables_locate_exact_original_spans():
    markdown = 'before <table>\n<tr><td>long\nlabel<br>next</td><td><b>(18)</b></td></tr>\n</table> between <table><tr><td>2</td></tr></table> after'
    document = build_document_map(markdown)
    first, second = tables(document)
    cell = get_cell(document, first['id'], 1, 1)
    assert cell['text'] == 'long\nlabel\nnext'
    assert (cell['start_line'], cell['end_line']) == (2, 3)
    assert get_cell(document, first['id'], 1, 2)['text'] == '(18)'
    assert first['end_offset'] < second['start_offset']
    assert ''.join(block['text'] for block in document['blocks']) == markdown


def test_bad_coordinates_unknown_blocks_and_sparse_cells_do_not_guess_values():
    document = build_document_map('<table><tr><td>A</td><td>1</td></tr><tr><td>B</td></tr></table>')
    block = tables(document)[0]
    assert block['rows'][1] == ['B', '']
    assert block['grid'][1][1] is None
    for block_id, row, column in [(block['id'], 2, 2), (block['id'], 0, 1), (block['id'], 1, 3), ('other', 1, 1), (block['id'], True, 1)]:
        with pytest.raises(ValueError):
            get_cell(document, block_id, row, column)


def test_arbitrary_headings_and_empty_input_remain_structural():
    assert build_document_map('')['blocks'] == []
    document = build_document_map('# 第一层\n### Deep\ntext\n## Peer\n<table><tr><td></td></tr></table>')
    block = tables(document)[0]
    assert [h['text'] for h in block['headings']] == ['第一层', 'Peer']
    assert get_cell(document, block['id'], 1, 1)['text'] == ''


def test_truncated_html_is_flagged_and_preserved_without_synthetic_closing_tags():
    markdown = 'intro\n<table><tr><td>A</td><td>123'
    block = tables(build_document_map(markdown))[0]
    assert block['text'] == markdown[markdown.index('<table>'):]
    assert 'unclosed_table' in block['issues']
    assert 'unclosed_cell' in block['issues']
    assert block['cells'][-1]['raw'] == '<td>123'


def test_crlf_unicode_offsets_and_non_markup_heading_hashes_are_preserved():
    markdown = '# C#\r\n## 公司资料 ###\r\n| 项目 | 数值 |\r\n| --- | --- |\r\n| 甲 | （1,234） |\r\n'
    document = build_document_map(markdown)
    block = tables(document)[0]
    assert [heading['text'] for heading in block['headings']] == ['C#', '公司资料']
    cell = get_cell(document, block['id'], 2, 2)
    assert cell['text'] == '（1,234）'
    assert cell['raw'] == markdown[cell['start_offset']:cell['end_offset']]
    assert cell['start_line'] == cell['end_line'] == 5


def test_nested_or_overlapping_html_is_flagged_without_losing_original_source():
    raw = '<table><tr><td>outside<table><tr><td>inside</td></tr></table></td></tr></table>'
    document = build_document_map(raw)
    assert len(tables(document)) == 1
    block = tables(document)[0]
    assert block['issues'] == ['nested_table']
    assert block['text'] == raw
    # An inner value cannot be mistaken for a distinct, validated outer cell.
    assert block['rows'] == [['outside']]
    assert get_cell(document, block['id'], 1, 1)['raw'].endswith('</table></td>')
