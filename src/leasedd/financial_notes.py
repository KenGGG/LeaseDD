"""Index and safely present original financial notes; never infer absent notes."""
import hashlib
import re
from html import unescape
from html.parser import HTMLParser
from .statement_tables import TABLE, ROW

CATEGORIES = {
    '审计报告':['审计报告','审计意见','聘任、解聘会计师事务所'], '主营构成':['营业收入','营业成本','主营业务','分行业','分产品'],
    '主要销售客户':['主要客户','前五名客户','前5名客户','销售客户'], '主要供应商':['主要供应商','前五名供应商','前5名供应商','前五大供应商'],
    '应收账款':['应收账款'], '预付款项':['预付款'], '其他应收款':['其他应收款'],
    '应付账款':['应付账款'], '预收款项':['预收款'], '其他应付款':['其他应付款'],
    '货币资金':['货币资金'], '存货':['存货'], '投资性房地产':['投资性房地产'],
    '受限资产':['受限','受到限制','所有权或使用权'], '财务费用':['财务费用'],
    '非经常性损益':['非经常性损益'],
    '长期应收款':['长期应收款'],
}
MAJOR = re.compile(r'^[一二三四五六七八九十百]+[、．.]')
TOPIC = re.compile(r'^\d+[、．.]\s*[^\d]')
HEADING = re.compile(r'^\s*#{1,6}\s+(.+?)\s*$')


def section_number(title):
    token=re.split('[、．.]',title,1)[0]
    digits={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    if '十' in token:
        tens,ones=token.split('十',1)
        return digits.get(tens,1)*10+digits.get(ones,0)
    return digits.get(token,0)


def plain(text):
    return re.sub(r'(?m)^\s*#{1,6}\s+', '', unescape(re.sub(r'<[^>]*>', ' ', text))).strip()


def index_notes(markdown, document_id, conversion_id):
    lines = markdown.splitlines()
    declared_units=re.findall(r'财务附注中报表的单位为\s*[:：]\s*(百万元|千元|万元|亿元|元)',markdown)
    note_unit=declared_units[0] if len(set(declared_units))==1 else None
    headers = []
    active, section, scope = False, '', 'report'
    topic_categories=[]
    for number, line in enumerate(lines,1):
        match=HEADING.match(line)
        if not match:
            continue
        title=match[1]
        if re.match(r'^第[一二三四五六七八九十0-9]+节',title):
            active=False
            section=title
            scope='report'
            topic_categories=[]
        major=bool(MAJOR.match(title))
        # Flattened PDF headings can contain table subgroups such as 二、联营企业
        # inside 七、合并财务报表项目注释. They do not end the enclosing scope.
        main_major=major and not (scope in ('consolidated','parent') and section_number(title)<=section_number(section))
        if main_major:
            topic_categories=[]
            section=title
            if any(x in title for x in ('财务报表项目注释','财务报表主要项目注释','重要会计政策','财务报表的编制基础','公司基本情况')):
                active=True
            if title.startswith('第'):
                active=False
            scope='parent' if '母公司' in title else 'consolidated' if '合并' in title else 'report'
        categories=[name for name, keywords in CATEGORIES.items() if any(word in title for word in keywords)]
        if TOPIC.match(title) or (scope=='report' and re.match(r'^[（(]\d+[）)]',title)):
            topic_categories=categories
        elif not major:
            categories=list(dict.fromkeys(topic_categories+categories))
        # Only Arabic top-level topics, not nested (1), 1), age buckets, etc.
        if major or TOPIC.match(title) or categories:
            headers.append({'title':title,'start_line':number,'section':section,'scope':scope,'major':major,'include':active or bool(categories),'categories':categories})
    notes=[]
    for n,header in enumerate(headers):
        if not header['include']:
            continue
        end=headers[n+1]['start_line']-1 if n+1<len(headers) else len(lines)
        if header['title']=='一、审计报告':
            boundary=next((h['start_line']-1 for h in headers[n+1:] if h['title']=='二、财务报表'),None)
            if boundary:end=boundary
        text='\n'.join(lines[header['start_line']-1:end])
        if not text.strip():
            continue
        # Classification uses explicit heading words; searching also covers body.
        note={k:v for k,v in header.items() if k not in ('major','include')}
        note.update(id=hashlib.sha256(f'{conversion_id}:{header["start_line"]}:{end}'.encode()).hexdigest()[:32], document_id=document_id,conversion_id=conversion_id,end_line=end,text=text,summary=plain(text)[:180],declared_unit=note_unit)
        notes.append(note)
    return notes


def note_blocks(text):
    """Return text and literal cells, never executable source HTML."""
    blocks=[]
    cursor=0
    for table in TABLE.finditer(text):
        if table.start()>cursor:
            blocks.append({'type':'text','text':plain(text[cursor:table.start()])})
        rows=[]
        for row in ROW.finditer(table[0]):
            parser=NoteCells();parser.feed(row[0]);rows.append(parser.cells)
        blocks.append({'type':'table','rows':rows})
        cursor=table.end()
    if cursor<len(text):
        blocks.append({'type':'text','text':plain(text[cursor:])})
    return blocks


class NoteCells(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells=[]
        self.active=None

    def handle_starttag(self,tag,attrs):
        if tag in ('td','th'):
            attributes=dict(attrs)
            def span(name):
                value=attributes.get(name,'1') or '1'
                return min(max(int(value),1),1000) if value.isdigit() else 1
            self.active={'text':'','rowspan':span('rowspan'),'colspan':span('colspan')}
        elif tag=='br' and self.active is not None:
            self.active['text']+='\n'

    def handle_data(self,data):
        if self.active is not None:self.active['text']+=data

    def handle_endtag(self,tag):
        if tag in ('td','th') and self.active is not None:
            self.active['text']=self.active['text'].strip()
            self.cells.append(self.active);self.active=None


def table_grid(table):
    """Expand merged headers to explicit positions without discarding columns."""
    occupied={};height=0;width=0
    for y,row in enumerate(ROW.finditer(table)):
        parser=NoteCells();parser.feed(row[0]);x=0;height=y+1
        for cell in parser.cells:
            while (y,x) in occupied:x+=1
            for dy in range(cell['rowspan']):
                for dx in range(cell['colspan']):occupied[y+dy,x+dx]=cell['text']
            width=max(width,x+cell['colspan']);x+=cell['colspan']
    grid=[[occupied.get((y,x),'') for x in range(width)] for y in range(height)]
    return join_wrapped_rows(grid)


def join_wrapped_rows(grid):
    """Rejoin PDF continuation rows only when numeric fragments prove continuity.

    For example ``509,352,8`` + ``17.46`` or ``30,000,514.4`` + ``6``.
    A nameless row containing independent complete amounts is never added/merged.
    Raw note blocks and original line locators remain unchanged.
    """
    result=[]
    money=re.compile(r'^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?$')
    for row in grid:
        if result and not row[0] and result[-1][0]:
            previous=result[-1];continuations=[];valid=True
            for i,cell in enumerate(row[1:],1):
                if not cell:continue
                a=re.sub(r'\s+','',previous[i]);b=re.sub(r'\s+','',cell)
                if re.fullmatch(r'[\d,.]+',b):
                    fragmented=not money.fullmatch(a) or bool(re.search(r'\.\d$',a) and re.fullmatch(r'\d',b))
                    if fragmented and money.fullmatch(a+b):continuations.append(i)
                    else:valid=False
            if valid and continuations:
                result[-1]=[a+b for a,b in zip(previous,row)]
                continue
        result.append(row)
    return result


def notes_matrix(notes,category,scope='consolidated'):
    from decimal import Decimal
    from .finance_extract import normalize_source_number,UNIT_SCALES
    if category=='审计报告':return audit_matrix(notes)
    from .note_tables import specialized_matrix
    specialized=specialized_matrix(notes,category,scope)
    if specialized is not None:return specialized
    values={};periods=set();order=[]
    for note in notes:
        end=note.get('report_end')
        business=category=='主营构成' and scope=='consolidated'
        if not end or category not in note['categories']:continue
        if business:
            if '非主营' in note['title']:continue
        elif note['scope']!=scope or '财务报表' not in note['section'] or '注释' not in note['section']:continue
        for table in TABLE.finditer(note['text']):
            rows=table_grid(table[0])
            if not rows or not rows[0] or rows[0][0] not in (('','项目') if business else ('项目','账龄','类别')):continue
            unit=re.findall(r'单位\s*[:：]\s*(?:人民币)?\s*(亿元|万元|千元|百万元|元)',note['text'][:table.start()])
            if not unit:continue
            scale=UNIT_SCALES[unit[-1]]
            header=rows[0];header_count=2 if len(rows)>1 and rows[1][0]==header[0] else 1
            cols={}
            for col,name in enumerate(header[1:],1):
                if name in ('期末余额','期末数','期末账面余额','本期发生额','本期金额'):period=end
                elif name in ('期初余额','期初数','上年年末余额'):period=str(int(end[:4])-1)+'-12-31'
                elif name in ('上期发生额','上期金额'):period=str(int(end[:4])-1)+end[4:]
                elif business and name=='本报告期':period=end
                elif business and name=='上年同期':period=str(int(end[:4])-1)+end[4:]
                elif business and re.fullmatch(r'20\d{2}年',name):period=name[:4]+'-12-31'
                elif business and name in ('营业收入','营业成本'):period=end
                else:continue
                field=rows[1][col] if header_count==2 else ''
                if '%' in field or '比例' in field:continue
                if business:
                    if header_count==2 and field!='金额':continue
                    if header_count==1 and name not in ('营业收入','营业成本'):continue
                    field=name if name in ('营业收入','营业成本') else '营业收入'
                cols[col]=(period,field)
            if not cols:continue
            if category=='存货' and not any(field=='账面价值' for _,field in cols.values()):continue
            # Money-fund restrictions are a separate note, not part of its balance.
            if category=='货币资金' and not any(r[0]=='库存现金' for r in rows):continue
            table_values={}
            dimension='合计'
            for row in rows[header_count:]:
                name=row[0]
                if not name:continue
                if business and name.startswith('分'):
                    dimension=name[1:];continue
                name={'在产品':'在产品及半成品','半成品':'在产品及半成品','库存商品':'产成品及库存商品'}.get(name,name) if category=='存货' else name
                for col,(period,field) in cols.items():
                    if col>=len(row):continue
                    try:value=normalize_source_number(row[col])*scale
                    except ValueError:continue
                    if category=='存货':
                        sub='账面价值' if field=='账面价值' else '跌价准备' if '准备' in field else '期末余额'
                        label=(sub+'合计') if name=='合计' else name if sub=='账面价值' else sub
                        key=name+'|'+sub
                    elif business:
                        name={'营业收入合计':'营业收入','境内销售':'国内','境外销售':'国外'}.get(name,name)
                        if name=='营业收入' and field=='营业成本':name='营业成本'
                        key=field+'|'+dimension+'|'+name;label=name
                    else:
                        key=name+'|'+field;label=name+(' · '+field if field else '')
                    entry=table_values.setdefault((key,period),{'key':key,'label':label,'section':category,'value':Decimal(0),'note_ids':[note['id']]})
                    entry['value']+=value
            for (key,period),entry in table_values.items():
                if key not in order:order.append(key)
                periods.add(period)
                value={**entry,'value':format(entry['value'],'f')}
                values.setdefault((key,period),[]).append(value)
    if category=='存货':
        names=list(dict.fromkeys(k.split('|')[0] for k in order))
        order=[n+'|'+field for n in names for field in ['账面价值','期末余额','跌价准备'] if n+'|'+field in order]
    if category=='主营构成':
        dimension_order={'合计':0,'产品':1,'行业':2,'地区':3,'销售模式':4}
        order.sort(key=lambda k:(0 if k.split('|')[0]=='营业收入' else 1,dimension_order.get(k.split('|')[1],5)))
    periods=sorted(periods,reverse=True)
    rows=[]
    for key in order:
        example=next(v[0] for (k,_),v in values.items() if k==key)
        cells=[]
        for period in periods:
            candidates=values.get((key,period),[])
            distinct={Decimal(c['value']) for c in candidates}
            cells.append({'value':candidates[0]['value'] if len(distinct)==1 else None,'note_ids':list(dict.fromkeys(n for c in candidates for n in c['note_ids'])),'conflict':len(distinct)>1})
        rows.append({'key':key,'label':example['label'],'section':key.split('|')[0]+' · '+key.split('|')[1] if category=='主营构成' else '', 'cells':cells})
    return {'periods':periods,'rows':rows}


def audit_matrix(notes):
    from .note_tables import number
    fields={'审计报告签署日期':'审计日期','审计意见类型':'审计意见','审计机构名称':'境内会计事务所','注册会计师姓名':'签字注册会计师'}
    records={}
    for note in notes:
        end=note.get('report_end','') or ''
        if not end.endswith('12-31'):continue
        if '聘任、解聘会计师事务所' in note['title']:
            for table in TABLE.finditer(note['text']):
                for row in table_grid(table[0]):
                    if len(row)==2 and re.fullmatch(r'境内会计师事务所报酬[（(]万元[）)]',row[0]):
                        amount=number(row[1])
                        if amount is not None:
                            records.setdefault(('境内',end),[]).append({'value':str(amount*10000),'note_id':note['id']})
            continue
        if note['title']!='一、审计报告':continue
        records.setdefault(('审计报告正文',end),[]).append({'value':'查看','note_id':note['id']})
        for table in TABLE.finditer(note['text']):
            for row in table_grid(table[0]):
                if len(row)==2 and row[0] in fields:
                    value=row[1]
                    if row[0]=='审计意见类型' and value in ('标准的无保留意见','标准无保留意见'):value='标准无保留'
                    if row[0]=='审计机构名称':value=re.sub(r'[（(].*?[）)]','',value)
                    if row[0]=='审计报告签署日期':value=re.sub(r'(\d{4})年(\d{2})月(\d{2})日',r'\1-\2-\3',value)
                    records.setdefault((fields[row[0]],end),[]).append({'value':value,'note_id':note['id']})
    periods=sorted({p for _,p in records},reverse=True)
    rows=[]
    for label in [*fields.values(),'境内','审计报告正文']:
        cells=[]
        for period in periods:
            values=records.get((label,period),[]);distinct={v['value'] for v in values}
            cells.append({'value':values[0]['value'] if len(distinct)==1 else None,'note_ids':[v['note_id'] for v in values],'conflict':len(distinct)>1})
        rows.append({'key':label,'label':label,'section':'','cells':cells})
    return {'periods':periods,'rows':rows if periods else []}
