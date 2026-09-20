"""Read explicit summary disclosures and cash-flow notes with source locators.

Never fetch financial values from a reference website. Supplement IDs depend on
conversion, concept, period and the exact source row; existing facts stay intact.
"""
import hashlib
import re
from datetime import date
from .statement_tables import TABLE, ROW, RowCells, HEADING, report_end
from .finance_extract import normalize_source_number

SUMMARY={
 '归属于上市公司股东的扣除非经常性损益的净利润(元)':('net_profit_excluding_nonrecurring','元'),
 '加权平均净资产收益率':('reported_roe','%'),
}
DEPRECIATION={
 '固定资产折旧、油气资产折耗、生产性生物资产折旧':'fixed_depreciation',
 '使用权资产折旧':'rou_depreciation','无形资产摊销':'intangible_amortization','长期待摊费用摊销':'deferred_amortization',
}

def supplementary_statements(markdown, document_id, conversion_id, statements):
    end=report_end(markdown)
    contexts=[s for s in statements if s['scope']=='consolidated' and s['document_id']==document_id]
    if not end or not contexts or len({s['entity'] for s in contexts})!=1:return []
    template=contexts[0]
    flow=f'{end[:4]}-01-01/{end}'
    kind='year' if end.endswith('12-31') else 'half_year' if end.endswith('06-30') else 'year_to_date'
    groups={}
    def add(concept,label,raw,unit,period,table,row,offset):
        try:value=normalize_source_number(raw.rstrip('%％'))
        except ValueError:return
        identity=hashlib.sha256(f'{conversion_id}:{concept}:{period}:{offset}:{row}'.encode()).hexdigest()[:28]
        key=(table,period)
        s=groups.setdefault(key,{**{k:v for k,v in template.items() if k!='items'},'id':'supplement_'+identity,'statement_type':table,'period':period,'period_normalized':period,'period_kind':'instant' if table=='balance_sheet' else kind,'raw_unit':'元','unit_scale':'1','state':'extracted','issues':[],'items':[]})
        s['conversion_id']=conversion_id
        line=markdown.count('\n',0,offset)+1
        s['items'].append({'id':'sup_'+identity,'concept':concept,'source_name':label,'raw_value':raw,'raw_unit':unit,'normalized_value':format(value,'f'),'source_text':row,'source_start_line':line,'source_end_line':line+row.count('\n'),'status':'source_verified','confirmation_reason':None,'supplemental':True})
    primary=re.search(r'#{1,6}\s*(?:[0-9一二三四五六七八九十]+[、.．]\s*)?合并资产负债表',markdown)
    summary_end=primary.start() if primary else 0
    for table in TABLE.finditer(markdown):
        rows=[]
        for row in ROW.finditer(table[0]):
            parser=RowCells();parser.feed(row[0]);rows.append((row,parser.cells))
        if not rows:continue
        header=rows[0][1]
        if header[:2]==['报告期利润','加权平均净资产收益率']:
            for row,cells in rows:
                if len(cells)==4 and cells[0]=='扣除非经常性损益后归属于公司普通股股东的净利润':
                    for col,concept,unit in [(1,'reported_ex_roe','%'),(2,'reported_ex_basic_eps','元/股'),(3,'reported_ex_diluted_eps','元/股')]:
                        add(concept,{'reported_ex_roe':'扣非后加权净资产收益率','reported_ex_basic_eps':'扣非后基本每股收益','reported_ex_diluted_eps':'扣非后稀释每股收益'}[concept],cells[col],unit,flow,'income_statement',row[0],table.start()+row.start())
        summary_columns=[]
        if '本报告期' in header and '上年同期' in header:
            summary_columns=[(header.index('本报告期'),flow),(header.index('上年同期'),'/'.join(str(int(d[:4])-1)+d[4:] for d in flow.split('/')))]
        elif kind=='year':
            for col,title in enumerate(header):
                year=re.fullmatch(r'(20\d{2})年?',re.sub(r'\s+','',title))
                if year and any((s.get('period_normalized') or '').startswith(year[1]) for s in contexts):
                    summary_columns.append((col,f'{year[1]}-01-01/{year[1]}-12-31'))
        if table.start()<summary_end and summary_columns:
            for row,cells in rows[1:]:
                if not cells:continue
                label=re.sub(r'\s+','',cells[0]).replace('（','(').replace('）',')')
                if label not in SUMMARY:continue
                concept,unit=SUMMARY[label]
                for col,period in summary_columns:
                    if col<len(cells):add(concept,cells[0],cells[col],unit,period,'income_statement',row[0],table.start()+row.start())
        # Quantity disclosure under share-change tables, never the capital amount.
        if table.start()<summary_end and '本次变动前' in ''.join(header) and '本次变动后' in ''.join(header):
            for row,cells in rows:
                if cells and '股份总数' in cells[0] and len(cells)>=5 and cells[-1].endswith('%') and not cells[-2].endswith('%'):
                    add('ordinary_share_count','期末股份总数',cells[-2],'股',end,'balance_sheet',row[0],table.start()+row.start())
                    if cells[2].endswith('%'):
                        add('ordinary_share_count','期初股份总数',cells[1],'股',str(int(end[:4])-1)+'-12-31','balance_sheet',row[0],table.start()+row.start())
        if header[:3]==['补充资料','本期金额','上期金额']:
            before=markdown[:table.start()]
            majors=[h[1] for h in HEADING.finditer(before) if re.match(r'^[一二三四五六七八九十]+、',h[1])]
            if not majors or '合并财务报表项目注释' not in majors[-1]:continue
            for row,cells in rows[1:]:
                if not cells or cells[0] not in DEPRECIATION:continue
                for col,period in [(1,flow),(2,'/'.join(str(int(d[:4])-1)+d[4:] for d in flow.split('/')))]:
                    if col<len(cells):add(DEPRECIATION[cells[0]],cells[0],cells[col],'元',period,'cash_flow_statement',row[0],table.start()+row.start())
    return list(groups.values())
