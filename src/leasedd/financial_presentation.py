"""Read presentation hints from unchanged, hash-verified source Markdown."""
from .statement_tables import HEADING, PRIMARY, TABLE, ROW, RowCells, clean_label


def align_balance_period(statement):
    """Group opening balances with prior closing balances without losing evidence.

    Values remain separate candidates: a restatement still produces a conflict.
    This also repairs presentation of historical rows without rewriting their audit.
    """
    from .finance_extract import normalize_period
    period = statement.get('period_normalized') or statement.get('period', '')
    if statement.get('statement_type') != 'balance_sheet' or not period.endswith('-01-01') or '/' in period:
        return statement
    normalized = normalize_period(period, 'balance_sheet')
    if not normalized:
        return statement
    return {**statement, 'period_normalized': normalized[0], 'period_kind': normalized[1], 'period_basis': 'opening_balance'}


def source_layout(markdown):
    result={}
    headings=list(HEADING.finditer(markdown))
    for index,heading in enumerate(headings):
        title=PRIMARY.fullmatch(heading[1].strip())
        if not title:continue
        end=headings[index+1].start() if index+1<len(headings) else len(markdown)
        section_text=markdown[heading.end():end]
        section=title[2]
        for table in TABLE.finditer(section_text):
            headers=[]
            for row in ROW.finditer(table[0]):
                parser=RowCells();parser.feed(row[0])
                cells=parser.cells
                if not cells or parser.merged:continue
                if cells[0] in ('项目','科目'):headers=cells
                label=clean_label(cells[0]).rstrip(':')
                if all(c.strip() in ('','-','—') for c in cells[1:]):
                    if label in ('流动资产','非流动资产','流动负债','非流动负债','所有者权益','所有者权益(或股东权益)'):
                        section=label
                    elif label in ('经营活动产生的现金流量','投资活动产生的现金流量','筹资活动产生的现金流量','每股收益'):
                        section=label
                offset=heading.end()+table.start()+row.start()
                result.setdefault(row[0],[]).append({'source_order':offset,'source_section':section,'source_label':label,'source_cells':cells,'source_headers':headers,'source_start_line':markdown.count('\n',0,offset)+1})
    return result
