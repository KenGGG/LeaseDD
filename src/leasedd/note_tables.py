"""Evidence-only adapters for the distinct financial-note table layouts.

Reference labels are presentation metadata. All amounts come from uploaded tables;
blank source cells remain unknown and conflicting disclosures remain candidates.
"""
import re
from decimal import Decimal
from .finance_extract import normalize_source_number, UNIT_SCALES

NOTE_GROUPS = {
 '应收账款':['应收账款账龄分析','前五名应收账款','计提坏账的重大应收账款'],
 '预付款项':['预付款项账龄分析','账龄超过1年的重要预付款','前五名预付款'],
 '其他应收款':['其他应收款按款项性质分类','其他应收款账龄分析','前五名其他应收款'],
 '应付账款':['应付账款账龄分析','账龄超过1年的重要应付账款','前五名应付款'],
 '预收款项':['预收款项账龄分析','账龄超过1年的重要预收款','前五名预收款'],
 '其他应付款':['其他应付款按款项性质分类','其他应付款账龄分析','账龄超过1年的重要其他应付款','前五名其他应付款'],
 '投资性房地产':['按成本计量','按公允价值计量'],
}
PARENT = {leaf:parent for parent,leaves in NOTE_GROUPS.items() for leaf in leaves}
AGE_LABELS=['1年内','1-2年','2-3年','3-4年','3年以上','4-5年','5年以上','合计']


def compact(s):return re.sub(r'\s+','',s).replace('（','(').replace('）',')').replace('：',':')


def number(s,scale=Decimal(1)):
    # A dangling comma is a truncated PDF cell, not a valid monetary amount.
    if not s.strip() or re.search(r'[,，]\s*$',s):return None
    numeric=re.sub(r'\s+','',s).replace('，',',').replace('%','')
    if ',' in numeric and not re.fullmatch(r'-?\d{1,3}(?:,\d{3})+(?:\.\d+)?',numeric):return None
    try:return normalize_source_number(s.replace('%',''))*scale
    except ValueError:return None


def age_label(s):
    s=compact(s)
    s=re.sub(r'\(.*?\)','',s)
    if s in ('1年以内','1年以下','一年以内'):return '1年内'
    s=re.sub(r'(\d)年?[至~—－-](\d)年',r'\1-\2年',s)
    return s


def source_tables(notes,category,scope):
    from .financial_notes import TABLE,table_grid
    parent=PARENT.get(category,category)
    for n in notes:
        if not n.get('report_end') or parent not in n['categories']:continue
        public=parent in ('主要销售客户','主要供应商','非经常性损益')
        if public:
            if scope!='consolidated':continue
        elif n['scope']!=scope or '注释' not in n['section']:continue
        for t in TABLE.finditer(n['text']):
            grid=table_grid(t[0])
            if not grid:continue
            units=re.findall(r'单位\s*[:：]\s*(?:人民币)?\s*(百万元|千元|万元|亿元|元)',n['text'][:t.start()])
            if units:scale=UNIT_SCALES[units[-1]]
            elif any('(元)' in compact(c) for c in grid[0]):scale=Decimal(1)
            elif n.get('declared_unit') and n['scope'] in ('consolidated','parent'):scale=UNIT_SCALES[n['declared_unit']]
            else:continue
            count=1
            while count<len(grid) and grid[count][0]==grid[0][0] and count<4:count+=1
            headers=['|'.join(dict.fromkeys(compact(grid[y][c]) for y in range(count))) for c in range(len(grid[0]))]
            yield n,headers,grid[count:],scale


def period_of(header,end):
    h=compact(header).split('|')[0]
    match=re.fullmatch(r'(20\d{2})年(?:金额)?',h)
    if match:return match[1]+'-12-31'
    if h in ('期初','期初余额','期初数','期初账面余额','年初余额','上年年末余额'):return str(int(end[:4])-1)+'-12-31'
    if h in ('上期发生额','上期金额','上年同期金额','上年同期'):return str(int(end[:4])-1)+end[4:]
    if h in ('期末','期末余额','期末数','期末账面余额','期末账面价值','本期发生额','本期金额','本报告期金额','本期','金额'):return end
    return None


class Matrix:
    def __init__(self):self.values={};self.order={}
    def add(self,key,label,period,value,n,unit='元'):
        if value is None:return
        self.order.setdefault(key,dict(key=key,label=label,section='',unit=unit))
        self.values.setdefault((key,period),[]).append(dict(value=format(value,'f') if isinstance(value,Decimal) else value,note_id=n['id']))
    def result(self,order=None):
        periods=sorted({p for _,p in self.values},reverse=True);rows=[]
        keys=[k for k in (order or self.order) if k in self.order]
        for key in keys:
            cells=[]
            for p in periods:
                vs=self.values.get((key,p),[]);distinct={v['value'] for v in vs}
                # Decimal equality tolerates harmless textual scale differences.
                try:distinct={Decimal(v) for v in distinct}
                except Exception:pass
                cells.append(dict(value=vs[0]['value'] if len(distinct)==1 else None,note_ids=list(dict.fromkeys(v['note_id'] for v in vs)),conflict=len(distinct)>1))
            rows.append({**self.order[key],'cells':cells})
        return dict(periods=periods,rows=rows)


def specialized_matrix(notes,category,scope):
    if category in ('主要销售客户','主要供应商') or category.startswith('前五名') or category=='计提坏账的重大应收账款' or category.startswith('账龄超过'):
        return records_table(notes,category,scope)
    if category in NOTE_GROUPS:category=NOTE_GROUPS[category][0]
    is_age='账龄分析' in category
    nature='按款项性质分类' in category
    if category not in ('货币资金','受限资产','财务费用','非经常性损益','长期应收款') and not is_age and not nature:return None
    m=Matrix()
    for n,headers,rows,scale in source_tables(notes,category,scope):
        if not rows:continue
        if is_age:
            if headers[0] not in ('账龄','项目') or not any(age_label(r[0]) in AGE_LABELS[:-1] for r in rows):continue
        elif nature:
            if headers[0]!='款项性质' and not ('按款项性质' in n['title'] and headers[0]=='项目'):continue
        elif category=='货币资金':
            if not any(compact(r[0])=='库存现金' for r in rows):continue
        elif category=='受限资产':
            if '所有权或使用权受到限制' not in n['title'] and '资产权利受限' not in n['title']:continue
        elif category=='财务费用':
            if not any('利息' in r[0] for r in rows):continue
        elif category=='非经常性损益':
            if headers[0]!='项目':continue
        for c,h in enumerate(headers[1:],1):
            period=period_of(h,n['report_end'])
            if not period or '比例' in h or '%' in h:continue
            if category=='受限资产' and '账面价值' not in h and '账面余额' in h:continue
            if category=='受限资产' and not ('账面价值' in h or h=='期末余额'):continue
            if is_age and len(h.split('|'))>1 and h.split('|')[-1] not in ('金额','账面余额','期末余额','期初余额'):continue
            for r in rows:
                if c>=len(r):continue
                label=compact(r[0]);value=number(r[c],scale)
                if not label or value is None:continue
                if is_age:
                    label=age_label(label)
                    if label not in AGE_LABELS:continue
                elif category=='货币资金':
                    label={'库存现金':'现金'}.get(label,label)
                    if label not in ('现金','银行存款','其他货币资金','合计'):continue
                elif category=='财务费用':
                    label={'利息费用':'利息支出','利息支出':'利息支出','减:利息收入':'减：利息收入','利息收入':'减：利息收入','汇兑损益':'汇兑损失','银行手续费及其他':'手续费支出','手续费':'手续费支出'}.get(label,label)
                    if '租赁负债' in label:continue
                    if label=='减：利息收入':value=-abs(value)
                elif category=='受限资产':label='受限资产合计' if label=='合计' else label
                elif category=='非经常性损益':
                    label=nonrecurring_label(label)
                    if label in ('所得税影响数','少数股东损益影响数'):value=-value
                m.add(label,label,period,value,n)
    result=m.result(AGE_LABELS if is_age else None)
    if is_age and PARENT.get(category) in ('应收账款','其他应收款'):
        # The reference displays the reported aging balance twice, followed by
        # allowance if separately disclosed. Do not invent allocation by aging.
        result['rows']=[entry for row in result['rows'] for entry in (row,{**row,'key':row['key']+'|balance','label':'期末余额'},{**row,'key':row['key']+'|allowance','label':'坏账准备','cells':[dict(value=None,note_ids=[],conflict=False) for _ in result['periods']]})]
    return result


def nonrecurring_label(label):
    for word,name in [('非流动','非流动资产处置损益'),('政府补助','政府补助'),('资金占用费','资金占用费'),('公允价值变动','投资收益'),('减值准备转回','已计提减值准备的转回'),('债务重组','债务重组损益'),('其他营业外','其他营业外收入和支出'),('所得税影响','所得税影响数'),('少数股东权益影响','少数股东损益影响数'),('其他符合','其他')]:
        if word in label:return name
    return label


def records_table(notes,category,scope):
    sales=category in ('主要销售客户','主要供应商');bad=category=='计提坏账的重大应收账款'
    important=category.startswith('账龄超过')
    labels=(['客户名称','销售额','占销售总额比例'] if category=='主要销售客户' else ['供应商名称','采购额','占采购总额比例']) if sales else ['单位名称','账面余额','坏账准备','账面价值'] if bad else ['单位名称','期末余额','未偿还或结转的原因'] if important else ['单位名称','期末余额','占总额比例(%)']
    units=['text','元','%'] if sales else ['text','元','元','元'] if bad else ['text','元','text'] if important else ['text','元','%']
    found={}
    for n,headers,rows,scale in source_tables(notes,category,scope):
        if sales:
            namecol=next((i for i,h in enumerate(headers) if h==labels[0]),None)
            amountcol=next((i for i,h in enumerate(headers) if ('销售额' if category=='主要销售客户' else '采购额') in h),None)
            ratecol=next((i for i,h in enumerate(headers) if '比例' in h),None)
            if namecol is None or amountcol is None:continue
        elif bad:
            if headers[0]!='名称' or not any('计提理由' in h for h in headers):continue
            namecol=0;amountcol=next((i for i,h in enumerate(headers) if '期末' in h and '账面余额' in h),None)
            allowance=next((i for i,h in enumerate(headers) if '期末' in h and '坏账准备' in h),None)
            if amountcol is None or allowance is None:continue
        else:
            if headers[0] not in ('单位名称','债权人名称','预付对象'):continue
            if important and not ('超过' in n['title'] or '逾期' in n['title']):continue
            if not important and not ('前五' in n['title'] or '前5' in n['title']):continue
            namecol=0
            amountcol=next((i for i,h in enumerate(headers) if h in ('应收账款期末余额','期末余额','账面余额')),None)
            ratecol=next((i for i,h in enumerate(headers) if '比例' in h),None)
            if amountcol is None:continue
        for r in rows:
            name=r[namecol].strip()
            if sales and r[0] in ('合计','小计'):name='合计'
            if name=='小计':name='合计'
            if not name:continue
            amount=number(r[amountcol],scale)
            if amount is None:continue
            if bad:
                provision=number(r[allowance],scale)
                vals=[name,amount,provision,amount-provision if provision is not None else None]
            elif important:
                reasoncol=next((i for i,h in enumerate(headers) if '原因' in h),None)
                vals=[name,amount,r[reasoncol] if reasoncol is not None else None]
            else:vals=[name,amount,number(r[ratecol]) if ratecol is not None else None]
            vals=[format(v,'f') if isinstance(v,Decimal) else v for v in vals]
            key=(n['report_end'],name)
            found.setdefault(key,[]).append((vals,n['id']))
    periods=sorted({p for p,_ in found},reverse=True);records=[]
    for (period,name),vs in sorted(found.items(),key=lambda kv:periods.index(kv[0][0])):
        cells=[]
        for i in range(len(labels)):
            distinct={v[0][i] for v in vs}
            cells.append(dict(value=vs[0][0][i] if len(distinct)==1 else None,note_ids=list(dict.fromkeys(v[1] for v in vs)),conflict=len(distinct)>1))
        records.append(dict(key=period+'|'+name,period=period,cells=cells))
    return dict(layout='records',periods=periods,rows=[],columns=[dict(label=l,unit=u) for l,u in zip(labels,units)],records=records)
