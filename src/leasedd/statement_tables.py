"""Read explicit, column-labelled primary statements from converted HTML tables.

Only source cells are read. Unknown disclosed rows get stable local identifiers;
they are not model-created standard concepts and do not enter formula inputs.
"""
import hashlib
import re
from datetime import date
from html.parser import HTMLParser

from .finance_extract import normalize_source_number, validate_extracted_statement

TITLES={'资产负债表':'balance_sheet','利润表':'income_statement','现金流量表':'cash_flow_statement'}
HEADING=re.compile(r'^\s*#{1,6}\s*([^\n]+)',re.M)
PRIMARY=re.compile(r'^(?:[0-9一二三四五六七八九十]+[、.．]\s*)?(合并|母公司)(资产负债表|利润表|现金流量表)\s*$')
TABLE=re.compile(r'<table\b[^>]*>.*?</table\s*>',re.S|re.I)
ROW=re.compile(r'<tr\b[^>]*>.*?</tr\s*>',re.S|re.I)
ALIASES={
 '货币资金':'cash','交易性金融资产':'trading_financial_assets','应收票据':'notes_receivable','应收账款':'accounts_receivable',
 '应收款项融资':'receivables_financing','预付款项':'prepayments','预付账款':'prepayments','其他应收款':'other_receivables','存货':'inventory','合同资产':'contract_assets','流动资产合计':'total_current_assets',
 '固定资产':'fixed_assets','在建工程':'construction_in_progress','使用权资产':'right_of_use_assets','无形资产':'intangible_assets','非流动资产合计':'total_noncurrent_assets','资产总计':'total_assets',
 '短期借款':'short_term_borrowings','应付票据':'notes_payable','应付账款':'accounts_payable','合同负债':'contract_liabilities','其他应付款':'other_payables','一年内到期的非流动负债':'current_portion_noncurrent_liabilities','流动负债合计':'total_current_liabilities',
 '长期借款':'long_term_borrowings','应付债券':'bonds_payable','租赁负债':'lease_liabilities','非流动负债合计':'total_noncurrent_liabilities','负债合计':'total_liabilities','所有者权益合计':'total_equity','所有者权益(或股东权益)合计':'total_equity',
 '营业收入':'revenue','营业成本':'cost','税金及附加':'taxes_and_surcharges','销售费用':'selling_expenses','管理费用':'administrative_expenses','研发费用':'research_and_development_expenses','财务费用':'finance_expenses',
 '其他收益':'other_income','投资收益':'investment_income','信用减值损失':'credit_impairment_loss','资产减值损失':'asset_impairment_loss','营业利润':'operating_profit','利润总额':'total_profit','所得税费用':'income_tax_expense','净利润':'net_profit','归属于母公司股东的净利润':'net_profit_attributable_to_parent',
 '营业外收入':'nonoperating_income','营业外支出':'nonoperating_expense',
 '销售商品、提供劳务收到的现金':'cash_received_from_sales','经营活动现金流入小计':'operating_cash_inflows','经营活动现金流出小计':'operating_cash_outflows','经营活动产生的现金流量净额':'net_operating_cash_flow','投资活动产生的现金流量净额':'net_investing_cash_flow','筹资活动产生的现金流量净额':'net_financing_cash_flow','汇率变动对现金及现金等价物的影响':'exchange_rate_effect','现金及现金等价物净增加额':'net_increase_in_cash','期初现金及现金等价物余额':'beginning_cash_balance','期末现金及现金等价物余额':'ending_cash_balance',
}


class RowCells(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells=[];self.active=None;self.merged=False

    def handle_starttag(self,tag,attrs):
        if tag in ('td','th'):
            self.active=[]
            self.merged |= any(k in ('rowspan','colspan') and v not in (None,'1') for k,v in attrs)
        elif tag=='br' and self.active is not None:self.active.append(' ')

    def handle_data(self,data):
        if self.active is not None:self.active.append(data)

    def handle_endtag(self,tag):
        if tag in ('td','th') and self.active is not None:
            self.cells.append(''.join(self.active).strip());self.active=None


def clean_label(label):
    label=re.sub(r'\s+','',label).replace('（','(').replace('）',')').replace('：',':')
    label=re.sub(r'^(?:[一二三四五六七八九十]+、|\d+[.．]|\([一二三四五六七八九十0-9]+\))','',label)
    label=re.sub(r'^(?:其中|加|减):','',label)
    # OCR may truncate the explanatory parenthesis, but never the account name.
    label=re.split(r'\((?:净亏损|亏损|损失|亏损总额)',label)[0]
    return label


def concept_for(label,statement_type):
    normalized=clean_label(label)
    return ALIASES.get(normalized) or 'disclosed_'+hashlib.sha256((statement_type+':'+normalized).encode()).hexdigest()[:32]


def report_end(markdown):
    match=re.search(r'(20\d{2})\s*年\s*(半年度|年度|第一季度|第三季度)报告',markdown[:6000])
    if not match:return None
    year,kind=match.groups()
    return year+{'半年度':'-06-30','年度':'-12-31','第一季度':'-03-31','第三季度':'-09-30'}[kind]


def column_period(text,kind,end):
    text=re.sub(r'\s+','',text)
    if kind=='balance_sheet':
        explicit=re.fullmatch(r'(20\d{2})年(\d{1,2})月(\d{1,2})日',text)
        if explicit:
            try:return date(*map(int,explicit.groups())).isoformat()
            except ValueError:return None
        if re.fullmatch(r'20\d{2}-\d{2}-\d{2}',text):
            try:return date.fromisoformat(text).isoformat()
            except ValueError:return None
        if end and text in ('期末余额','本期期末余额','期末数'):return end
        if end and text in ('期初余额','年初余额','期初数'):return str(int(end[:4])-1)+'-12-31'
    else:
        match=re.fullmatch(r'(20\d{2})年(?:半年度|1[-—至]6月)',text)
        if match:return match[1]+'H1'
        match=re.fullmatch(r'(20\d{2})年度?',text)
        if match:return match[1]+'年度'
    return None


def extract_statement_tables(markdown):
    headings=list(HEADING.finditer(markdown));results=[];end=report_end(markdown)
    entity_matches=re.findall(r'编制单位\s*[:：]\s*([^\n<]+)',markdown)
    # Shared metadata is safe only if all explicit preparer names agree.
    entities={re.sub(r'\s+','',e).strip() for e in entity_matches}
    entity=next(iter(entities)) if len(entities)==1 else None
    coverage={'method':'source_table_cells_v1','tables_found':0,'tables_parsed':0,'numeric_cells':0,'extracted_cells':0,'blank_cells':0,'unreadable_cells':0,'status':'complete'}
    for index,heading in enumerate(headings):
        title=PRIMARY.fullmatch(heading[1].strip())
        if not title:continue
        section_end=headings[index+1].start() if index+1<len(headings) else len(markdown)
        section=markdown[heading.end():section_end]
        scope='consolidated' if title[1]=='合并' else 'parent';kind=TITLES[title[2]]
        section_entity=re.search(r'编制单位\s*[:：]\s*([^\n<]+)',section)
        current_entity=re.sub(r'\s+','',section_entity[1]) if section_entity else entity
        preceding=markdown[:heading.start()].rstrip().split('\n')[-1]
        metadata=section+'\n'+(preceding if re.fullmatch(r'\s*单位\s*[:：]\s*(?:人民币)?\s*(?:百万元|千元|万元|亿元|元)\s*',preceding) else '')
        unit=re.search(r'单位\s*[:：]\s*(?:人民币)?\s*(百万元|千元|万元|亿元|元)',metadata)
        currency_unsupported=bool(re.search(r'单位[^\n<]{0,25}(美元|港元|欧元|日元)',section))
        explicit_end=re.search(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',section[:section.find('<table')])
        current_end=end
        if explicit_end:
            try:current_end=date(*map(int,explicit_end.groups())).isoformat()
            except ValueError:current_end=None
        by_period={}
        for table in TABLE.finditer(section):
            coverage['tables_found']+=1
            parsed=[]
            for row in ROW.finditer(table[0]):
                parser=RowCells();parser.feed(row[0])
                parsed.append((row,parser))
            if not parsed or not current_entity or not unit or currency_unsupported or any(p.merged for _,p in parsed):continue
            header=parsed[0][1].cells
            if not header or header[0].strip() not in ('项目','科目'):continue
            columns={i:column_period(value,kind,current_end) for i,value in enumerate(header) if i>0}
            columns={i:p for i,p in columns.items() if p}
            if not columns:continue
            coverage['tables_parsed']+=1
            for row,parser in parsed[1:]:
                cells=parser.cells
                if len(cells)!=len(header):
                    coverage['unreadable_cells']+=len(columns);continue
                label=cells[0]
                if not label:continue
                source_offset=heading.end()+table.start()+row.start()
                start_line=markdown.count('\n',0,source_offset)+1
                end_line=start_line+row[0].count('\n')
                concept=concept_for(label,kind)
                for col,period in columns.items():
                    value=cells[col].strip()
                    if value in ('','-','—','–','－','不适用'):
                        coverage['blank_cells']+=1;continue
                    try:normalize_source_number(value)
                    except ValueError:
                        coverage['unreadable_cells']+=1;continue
                    coverage['numeric_cells']+=1
                    by_period.setdefault(period,[]).append({'concept':concept,'source_name':label,'raw_value':value,'source_text':row[0],'source_start_line':start_line,'source_end_line':end_line})
        for period,items in by_period.items():
            payload={'statement_type':kind,'entity':current_entity,'scope':scope,'period':period,'currency':'CNY','raw_unit':unit[1],'items':items}
            extra={i['concept'] for i in items if i['concept'].startswith('disclosed_')}
            result=validate_extracted_statement(payload,section,extra_concepts=extra)
            result.update(source_start_line=markdown.count('\n',0,heading.start())+1,source_end_line=markdown.count('\n',0,section_end)+1)
            for item,original in zip(result['items'],items):
                item.update(source_start_line=original['source_start_line'],source_end_line=original['source_end_line'])
                if '每股收益' in item['source_name']:
                    item['raw_unit']='元/股';item['normalized_value']=format(normalize_source_number(item['raw_value']),'f')
            coverage['extracted_cells']+=len(result['items'])
            results.append(result)
    if coverage['tables_found']!=coverage['tables_parsed'] or coverage['unreadable_cells']:coverage['status']='partial'
    for result in results:result['coverage']=coverage
    return results
