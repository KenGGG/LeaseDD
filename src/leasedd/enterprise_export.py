"""Excel presentation of a saved enterprise module; no collection or mutation."""
from __future__ import annotations

from decimal import Decimal, localcontext
from io import BytesIO
import re

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .finance_extract import UNIT_SCALES


def _blank(value):
    return value is None or str(value).strip() in {'', '-', '--', '—'}


def _period(value):
    value = str(value)
    match = re.fullmatch(r'(\d{4})(0331|0630|0930|1231)', value)
    return match[1]+'年'+{'0331':'一季报','0630':'中报','0930':'三季报','1231':'年报'}[match[2]] if match else value


def _kind(period):
    for key, pattern in [('annual',r'年报|1231|12-31'),('half',r'中报|半年|0630|06-30'),('q3',r'三季报|0930|09-30'),('q1',r'一季报|0331|03-31')]:
        if re.search(pattern,period):return key
    return ''


def _order(period):
    year=re.match(r'\d{4}',period)
    return int(year[0])*10+{'annual':4,'q3':3,'half':2,'q1':1}.get(_kind(period),0) if year else 0


def _amount(value, source_unit, target_unit, decimals):
    if value is None:return ''
    text=str(value)
    if source_unit not in UNIT_SCALES and source_unit not in {'%','倍','天','元/股'}:return text
    if not re.fullmatch(r'-?\d+(?:\.\d+)?',text):return text
    with localcontext() as context:
        context.prec=max(50,len(text)+20)
        number=Decimal(text)
        if source_unit in UNIT_SCALES:number=number*UNIT_SCALES[source_unit]/UNIT_SCALES[target_unit]
        if number==0:number=abs(number)
        return number


def _flatten(rows, source_rows):
    for row in rows:
        key=row.get('key',row.get('value'))
        values=row.get('values')
        if values is None:values=[source.get(key) for source in source_rows]
        yield {**row,'values':values}
        yield from _flatten(row.get('children') or [],source_rows)


def select_currency_variant(module,currency='',rate=''):
    from types import SimpleNamespace
    if not currency and not rate:return module
    currency=currency or 'O';rate=rate or '1'
    variants=(module.parsed_payload or {}).get('variants') or []
    if not variants:
        if currency=='O' and rate=='1':return module
        raise ValueError('currency_variant_unavailable')
    for index,variant in enumerate(variants):
        params=variant['request_params']
        if params.get('displayCurrency')==currency and str(params.get('rateType'))==rate:
            responses=(module.raw_payload or {}).get('responses') or []
            if index>=len(responses):raise ValueError('currency_variant_unavailable')
            return SimpleNamespace(module_name=module.module_name,module_key=module.module_key,category=module.category,
                request_params={**module.request_params,**params},raw_payload=responses[index]['payload'],
                parsed_payload=variant['parsed'],response_sha256=module.response_sha256)
    raise ValueError('currency_variant_unavailable')


def _column_selected(value,scopes,data_kinds):
    text=str(value or '');match=re.match(r'^(合并|母公司)期[初末]',text)
    scope=match[0] if match else text;suffix=text[len(scope):]
    kind={'较年初比(%)':'较年初增长率','同比(%)':'同比增长率','销售比(%)':'销售百分比','资产比(%)':'资产百分比','环比(%)':'环比增长率'}.get(suffix,suffix or '原始报表')
    if text in {'原始报表','同比','占收入比'}:scope,kind='',text
    return (not scopes or scopes=='all' or scope in scopes.split(',')) and (not data_kinds or data_kinds=='all' or kind in data_kinds.split(','))


def export_enterprise_workbook(module, *, report='all', start='', end='', descending=True, hide_empty=True, unit='万元', decimals=2, scopes='', data_kinds='', window_years=0, trend_key=''):
    if window_years not in (0,3,5,10):raise ValueError('invalid_export_options')
    if unit not in UNIT_SCALES or not 0<=decimals<=6:raise ValueError('invalid_export_options')
    if any(value and not re.fullmatch(r'\d{4}',value) for value in (start,end)):raise ValueError('invalid_export_options')
    if start and end and start>end:raise ValueError('invalid_export_options')
    parsed=module.parsed_payload or {};metadata=parsed.get('metadata') or {}
    if metadata.get('unavailable') is True:raise ValueError('source_module_unavailable')
    periods=[_period(value) for value in parsed.get('periods') or []]
    rows=parsed.get('rows') or [];heads=parsed.get('head') or []
    if trend_key:
        if (getattr(module,'module_key','')!='main_indicators' or not re.fullmatch(r'\d+(?:_\d+)?',trend_key)
                or scopes not in {'合并期末','母公司期末'} or report not in {'annual','half','q1','q3'}
                or not any(isinstance(row,dict) and row.get('key')==trend_key for row in rows)):
            raise ValueError('invalid_trend_options')
        hide_empty=False
    output=[]
    if heads and isinstance(heads[0],list):
        reports=metadata.get('report') or [];previous_header=None
        for index,head in enumerate(heads):
            columns=rows[index] if index<len(rows) else []
            header=[head[0],*[column[0] for column in columns]]
            if header!=previous_header:output.append(header);previous_header=header
            output.append([_period(reports[index]) if index<len(reports) else str(index+1)])
            output.extend([[name,*[column[i+1] if i+1<len(column) else None for column in columns]] for i,name in enumerate(head[1:])])
    else:
        if heads and rows and all(isinstance(row,list) and re.fullmatch(r'\d{8}',str(row[0])) for row in rows):
            periods=[_period(row[0]) for row in rows]
            rows=[{'name':name,'values':[row[i+1] if i+1<len(row) else None for row in rows]} for i,name in enumerate(heads[1:])]
        if periods:
            reports=set(report.split(','));latest=max(map(_order,periods))
            column_types=next((row.get('values') or [] for row in rows if isinstance(row,dict) and row.get('key') in {'dataType','reportRange'}),[])
            indices=[i for i,p in enumerate(periods) if (not start or p[:4]>=start) and (not end or p[:4]<=end) and (
                'all' in reports or _kind(p) in reports or 'latest' in reports and _order(p)==latest or 'quarter' in reports and _kind(p) in {'q1','q3'})]
            indices.sort(key=lambda i:_order(periods[i]),reverse=descending)
            if window_years:
                quarter=lambda p:(_order(p)//10)*4+_order(p)%10
                cutoff=max(map(quarter,periods))-window_years*4
                indices=[i for i in indices if quarter(periods[i])>cutoff]
            indices=[i for i in indices if _column_selected(column_types[i] if i<len(column_types) else '',scopes,data_kinds)]
            output=[['报告期',*[periods[i] for i in indices]]]
            raw_data=(getattr(module,'raw_payload',{}) or {}).get('data') or {}
            export_headers=metadata.get('headExport') or []
            column_types=next((row.get('values') or [] for row in rows if isinstance(row,dict) and row.get('key')=='dataType'),[])
            for index,row in enumerate(_flatten(rows,raw_data.get('dataList') or [])):
                if trend_key and row.get('key') not in {trend_key,trend_key+'_2'}:continue
                source_unit=row.get('unit') or ''
                if not source_unit and getattr(module,'module_key','')=='main_business':
                    if re.search(r'[（(]%[）)]$',str(row.get('name',''))):source_unit='%'
                    elif re.match(r'^(120050|120062|900144|incomePrefix_|costPrefix_)',str(row.get('key',''))):
                        source_unit={'0':'元','3':'千元','4':'万元','6':'百万元','8':'亿元','9':'十亿元'}.get(str(module.request_params.get('unitCode')),'')
                if index+1<len(export_headers):
                    match=re.search(r'[（(]([^（）()]+)[）)]$',str(export_headers[index+1]))
                    if match:source_unit=match[1]
                name=str(row.get('name',row.get('label','')))
                if '每股' in name and source_unit=='元':source_unit='元/股'
                values=[row['values'][i] if i<len(row['values']) else None for i in indices]
                section=row.get('highlight') or row.get('level') in (0,'0')
                if hide_empty and not section and all(_blank(value) for value in values):continue
                label=name
                if source_unit:
                    display_unit=unit if source_unit in UNIT_SCALES else source_unit
                    suffix=re.search(r'[（(]([^（）()]+)[）)]$',label)
                    if suffix and suffix[1] in {*UNIT_SCALES,'%','倍','天','元/股'}:
                        label=label[:suffix.start()]+'（'+display_unit+'）'
                    else:label+='（'+display_unit+'）'
                output.append([label,*[_amount(value,'%' if source_unit in UNIT_SCALES and i<len(column_types) and (re.search(r'[%％]',str(column_types[i])) or column_types[i] in {'同比','占收入比'}) else source_unit,unit,decimals) for value,i in zip(values,indices)]])
        elif heads:output=[heads,*rows]
        else:output=[['企业预警通该栏目暂无数据' if metadata.get('empty') else '当前栏目数据尚待核对']]
    if trend_key:
        currency_values=next((row.get('values') or [] for row in rows if isinstance(row,dict) and row.get('key')=='displayCurrency'),[])
        currencies=[str(currency_values[i]) if i<len(currency_values) and not _blank(currency_values[i]) else '' for i in indices]
        unique_currencies=set(currencies)
        if len(unique_currencies)==1 and currencies[0]:
            for row in output[1:]:
                if row[0].endswith('（'+unit+'）'):
                    row[0]=row[0][:-1]+currencies[0]+'）'
        output=[['序号','报告期',*[row[0] for row in output[1:]]],
                *[[i,period,*[row[i] for row in output[1:]]] for i,period in enumerate(output[0][1:],1)]]
        if len(unique_currencies)>1:
            output[0].append('币种')
            for row,currency in zip(output[1:],currencies):row.append(currency)
    source_style=not trend_key and module.category in {'indicators','statements'} and bool(periods)
    if source_style:
        output=[['数据来源：企业预警通'],['序号','指标名称',*output[0][1:]],*[[index,*row] for index,row in enumerate(output[1:],1)]]
    book=Workbook();sheet=book.active
    sheet.title=re.sub(r'[\\/*?:\[\]]','',module.module_name or '财务数据')[:31] or '财务数据'
    sheet.freeze_panes='C3' if source_style else 'B2'
    for row_index,row in enumerate(output,1):
        for column,value in enumerate(row,1):
            cell=sheet.cell(row_index,column)
            if isinstance(value,Decimal) and len(''.join(map(str,value.as_tuple().digits)).rstrip('0'))<=15:
                cell.value=value;cell.number_format='#,##0'+('.'+'0'*decimals if decimals else '')
            elif source_style and column==1 and row_index>2:
                cell.value=value;cell.number_format='0'
            else:
                # Unsafe formula-like labels stay text. Amounts beyond Excel's
                # numeric precision stay exact strings, never rounded to floats.
                cell.value=format(value,f',.{max(decimals,-value.as_tuple().exponent)}f') if isinstance(value,Decimal) else '' if value is None else str(value)
                cell.data_type='s'
            cell.font=Font(name='Microsoft YaHei',size=10,bold=row_index<=(2 if source_style else 1),color='FF4545' if str(value).startswith('-') else '20252C')
            if row_index==1 or row_index%2==0:cell.fill=PatternFill('solid',fgColor='F7FAFF')
    for column in range(1,sheet.max_column+1):sheet.column_dimensions[get_column_letter(column)].width=20
    sheet.column_dimensions['B' if source_style else 'A'].width=34
    if source_style:
        sheet.column_dimensions['A'].width=8
        sheet.merge_cells(start_row=1,start_column=1,end_row=1,end_column=sheet.max_column)
    content=BytesIO();book.save(content);book.close()
    return content.getvalue()
