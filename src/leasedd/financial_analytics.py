"""Deterministic, read-only analytics over source-verified statement candidates.

Formula policy v2: original currency, no annualization, explicit reported ROE,
absolute-base growth and 30/360 turnover days. Beginning balances must match
the exact period start. These results do not approve facts or reports.
"""
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json

from .statement_tables import concept_for, ALIASES

VERSION = 'statement-analytics-v2'
BS, IS, CF = 'balance_sheet', 'income_statement', 'cash_flow_statement'
LABELS = {value:key for key,value in ALIASES.items()}
LABELS['net_profit_excluding_nonrecurring'] = '扣非后归母净利润'
for _label in ('基本每股收益','稀释每股收益'):
    LABELS[concept_for(_label,IS)] = _label
for _label,_table in [('营业总收入',IS),('归属于母公司所有者权益合计',BS)]:
    LABELS[concept_for(_label,_table)] = _label
CATEGORY_ORDER = ['利润表','资产负债表','每股指标','盈利能力','偿债能力','营运能力','成长能力','现金流量','杜邦分析','勾稽检查']


class Unavailable(Exception):
    pass


def financial_analytics(statements):
    groups = {}
    for s in statements:
        key = (s['entity'], s['scope'], s['currency'], s['document_id'] if s['scope'] == 'unknown' else '')
        groups.setdefault(key, []).append(s)
    result = []
    for key, source in groups.items():
        flows = {(s['period_normalized'], s['period_kind']) for s in source if s['statement_type'] != BS and s.get('period_normalized') and '/' in s['period_normalized']}
        ends = {p.split('/')[-1] for p, _ in flows}
        periods = flows | {(s['period_normalized'], 'instant') for s in source if s['statement_type'] == BS and s.get('period_normalized') and s['period_normalized'] not in ends}
        columns = []
        for period, kind in sorted(periods, key=lambda p: (p[0].split('/')[-1], p[0], p[1] or ''), reverse=True):
            start, end = (period.split('/') if '/' in period else (None, period))
            cells = []

            def add(code, label, category, unit, formula, specs, operation, policy=None):
                inputs = []
                def resolve(spec):
                    concept, table, offset = spec
                    target = end if table == BS else period
                    if table != BS and not start:
                        raise Unavailable('缺少该期间的累计报表')
                    if offset == 'opening':
                        if not start:
                            raise Unavailable('缺少明确的期间起点')
                        target = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
                    elif offset == 'previous':
                        target = '/'.join(date.fromisoformat(d).replace(year=int(d[:4])-1).isoformat() for d in target.split('/'))
                    elif offset == 'previous_quarter':
                        d=date.fromisoformat(end)
                        months=d.year*12+d.month-1-3
                        year,month=divmod(months,12);month+=1
                        target=date(year,month,monthrange(year,month)[1]).isoformat()
                    candidates = []
                    for s in source:
                        if s['statement_type'] != table or s.get('period_normalized') != target:
                            continue
                        if table != BS and s.get('period_kind') != kind:
                            continue
                        for item in s['items']:
                            if item['concept'] == concept and item['status'] != 'human_rejected':
                                candidates.append((s, item))
                    if not candidates:
                        raise Unavailable('缺少输入：'+LABELS.get(concept,'该科目')+'（'+target+'）')
                    for s, item in candidates:
                        inputs.append({'item_id':item['id'], 'document_id':s['document_id'], 'label':item['source_name'], 'period':target, 'value':item['normalized_value'], 'unit':item['raw_unit'] if item['raw_unit'] in ('元/股','股','%') else '元', 'status':item['status'], 'start_line':item['source_start_line'], 'end_line':item['source_end_line']})
                    if key[1] == 'unknown' or not key[0] or key[2] in ('', 'unknown', None) or any(s['issues'] or s['state'] != 'extracted' or not s.get('unit_scale') or not s.get('period_kind') for s, _ in candidates):
                        raise Unavailable('主体、范围、期间或单位口径待确认')
                    if any(i['status'] not in ('source_verified', 'human_confirmed') or i['normalized_value'] is None for _, i in candidates):
                        raise Unavailable('来源数值尚未通过校验')
                    special={'ordinary_share_count':'股','reported_roe':'%','reported_ex_roe':'%','reported_ex_basic_eps':'元/股','reported_ex_diluted_eps':'元/股'}
                    expected=special.get(concept,'元/股' if concept in (concept_for('基本每股收益',IS),concept_for('稀释每股收益',IS)) else '元')
                    units={i['raw_unit'] if i['raw_unit'] in ('元/股','股','%') else '元' for _,i in candidates}
                    if units!={expected}:
                        raise Unavailable('输入单位不一致')
                    values = {Decimal(i['normalized_value']) for _, i in candidates}
                    if len(values) != 1:
                        raise Unavailable('同一科目存在冲突，请先核对候选')
                    value = next(iter(values))
                    if not value.is_finite():
                        raise Unavailable('输入不是有效数值')
                    return value
                value, reason = None, None
                try:
                    if policy:
                        raise Unavailable(policy)
                    with localcontext() as ctx:
                        ctx.prec = 38
                        value = format(operation(*[resolve(spec) for spec in specs]), 'f')
                except (Unavailable, ValueError, InvalidOperation) as exc:
                    reason = str(exc) or '期间或数值无效'
                cell = {'code':code, 'label':label, 'category':category, 'unit':unit, 'formula':formula, 'formula_version':VERSION, 'value':value, 'reason':reason, 'inputs':inputs, 'status':'unavailable' if value is None else 'confirmed_inputs' if inputs and all(i['status']=='human_confirmed' for i in inputs) else 'pending_review'}
                cells.append(cell)

            def spec(concept, table=IS, offset='current'):
                return (concept, table, offset)

            def ratio(a, b):
                if b == 0:
                    raise Unavailable('分母为零')
                if b < 0:
                    raise Unavailable('分母为负，不适用常规比率解释')
                return a / b

            direct = [
                ('revenue','营业收入',IS,'利润表'),('total_profit','利润总额',IS,'利润表'),('net_profit','净利润',IS,'利润表'),
                ('net_profit_attributable_to_parent','归母净利润',IS,'利润表'),('net_profit_excluding_nonrecurring','扣非后归母净利润',IS,'利润表'),
                ('asset_impairment_loss','资产减值损失',IS,'利润表'),('credit_impairment_loss','信用减值损失',IS,'利润表'),
                ('total_assets','总资产',BS,'资产负债表'),('total_liabilities','总负债',BS,'资产负债表'),('total_equity','净资产',BS,'资产负债表'),
                ('net_operating_cash_flow','经营现金流量净额',CF,'现金流量'),('net_investing_cash_flow','投资现金流量净额',CF,'现金流量'),
                ('net_financing_cash_flow','筹资现金流量净额',CF,'现金流量'),('net_increase_in_cash','现金及现金等价物净增加额',CF,'现金流量'),('ending_cash_balance','期末现金及现金等价物余额',CF,'现金流量'),
            ]
            for concept, label, table, category in direct:
                add(concept,label,category,'元','损失按正数列示，原利润表损益符号取反' if concept in ('asset_impairment_loss','credit_impairment_loss') else '原报表披露值',[spec(concept,table)],(lambda x:-x) if concept in ('asset_impairment_loss','credit_impairment_loss') else (lambda x:x))
            for label, table, category in [('营业总收入',IS,'利润表'),('归属于母公司所有者权益合计',BS,'资产负债表')]:
                concept=concept_for(label,table)
                add(concept,label,category,'元','原报表披露值',[spec(concept,table)],lambda x:x)
            for label in ('基本每股收益','稀释每股收益'):
                concept = concept_for(label,IS)
                add(concept,label,'每股指标','元/股','原报告披露值，不以股本金额代替股数',[spec(concept)],lambda x:x)
            add('gross_margin','销售毛利率','盈利能力','%','(营业收入 − 营业成本) / 营业收入 × 100',[spec('revenue'),spec('cost')],lambda a,b:ratio(a-b,a)*100)
            for code,label,num in [('net_margin','销售净利率','net_profit'),('operating_margin','营业利润率','operating_profit')]:
                add(code,label,'盈利能力','%',label+' = '+('净利润' if num=='net_profit' else '营业利润')+' / 营业收入 × 100',[spec(num),spec('revenue')],lambda a,b:ratio(a,b)*100)
            for code,label,concept in [('roa','总资产收益率（期间）','total_assets'),('roe_total','净资产收益率（全体股东）','total_equity')]:
                add(code,label,'盈利能力','%','净利润 / ((期初余额 + 期末余额) / 2) × 100；不年化、非加权口径',[spec('net_profit'),spec(concept,BS,'opening'),spec(concept,BS)],lambda n,b,e:ratio(n,(b+e)/2)*100)
            add('debt_ratio','资产负债率','偿债能力','%','总负债 / 总资产 × 100',[spec('total_liabilities',BS),spec('total_assets',BS)],lambda a,b:ratio(a,b)*100)
            add('current_ratio','流动比率','偿债能力','%','流动资产 / 流动负债 × 100',[spec('total_current_assets',BS),spec('total_current_liabilities',BS)],lambda a,b:ratio(a,b)*100)
            add('quick_ratio','速动比率','偿债能力','%','(流动资产 − 存货) / 流动负债 × 100',[spec('total_current_assets',BS),spec('inventory',BS),spec('total_current_liabilities',BS)],lambda a,b,c:ratio(a-b,c)*100)
            add('cash_ratio','货币资金比率','偿债能力','%','货币资金 / 流动负债 × 100；未剔除受限资金',[spec('cash',BS),spec('total_current_liabilities',BS)],lambda a,b:ratio(a,b)*100)
            for code,label,numerator,denominator in [('asset_turnover','总资产周转率','revenue','total_assets'),('receivable_turnover','应收账款周转率','revenue','accounts_receivable'),('inventory_turnover','存货周转率','cost','inventory')]:
                inputs=[spec(numerator),spec(denominator,BS,'opening'),spec(denominator,BS)]
                add(code,label+'（期间）','营运能力','次',('营业成本' if numerator=='cost' else '营业收入')+' / 期初期末平均余额；不年化',inputs,lambda n,b,e:ratio(n,(b+e)/2))
                if code!='asset_turnover':
                    def days(n,b,e):
                        begin,finish=date.fromisoformat(start),date.fromisoformat(end)
                        if begin.day!=1 or finish.day!=monthrange(finish.year,finish.month)[1]:raise Unavailable('不足整月，30/360口径不适用')
                        elapsed=Decimal(((finish.year-begin.year)*12+finish.month-begin.month+1)*30)
                        return ratio(elapsed,ratio(n,(b+e)/2))
                    add(code+'_days',label.replace('周转率','周转天数'),'营运能力','天','期间月数 × 30 / 期间周转率（30/360口径）',inputs,days)
            for concept,label,table in [('revenue','营业收入',IS),('net_profit','净利润',IS),('net_profit_attributable_to_parent','归母净利润',IS),('total_assets','总资产',BS),('total_equity','净资产',BS)]:
                add(concept+'_growth',label+'同比','成长能力','%','(本期 − 上年同口径同期) / |上年同期| × 100',[spec(concept,table),spec(concept,table,'previous')],lambda a,b:ratio(a-b,abs(b))*100)
            add('cash_revenue','销售收现比','现金流量','%','销售商品、提供劳务收到的现金 / 营业收入 × 100（现金包含税额影响）',[spec('cash_received_from_sales',CF),spec('revenue')],lambda a,b:ratio(a,b)*100)
            add('cash_profit','净利润现金含量','现金流量','%','经营现金流量净额 / 净利润 × 100；净利润须为正',[spec('net_operating_cash_flow',CF),spec('net_profit')],lambda a,b:ratio(a,b)*100)
            add('equity_multiplier','权益乘数（平均余额）','杜邦分析','倍','平均总资产 / 平均归母净资产',[spec('total_assets',BS,'opening'),spec('total_assets',BS),spec(concept_for('归属于母公司所有者权益合计',BS),BS,'opening'),spec(concept_for('归属于母公司所有者权益合计',BS),BS)],lambda a,b,c,d:ratio(a+b,c+d))
            add('balance_difference','资产负债表平衡差额','勾稽检查','元','总资产 − 总负债 − 净资产',[spec('total_assets',BS),spec('total_liabilities',BS),spec('total_equity',BS)],lambda a,b,c:a-b-c)
            parent_equity=concept_for('归属于母公司所有者权益合计',BS)
            interest=concept_for('利息费用',IS)
            for concept,label,table in [('total_liabilities','总负债',BS),(parent_equity,'归母净资产',BS),(concept_for('营业总收入',IS),'营业总收入',IS)]:
                add(concept+'_growth',label+'同比','成长能力','%','(本期 − 上年同期) / |上年同期| × 100',[spec(concept,table),spec(concept,table,'previous')],lambda a,b:ratio(a-b,abs(b))*100)
            for concept,label in [('total_assets','总资产'),('total_liabilities','总负债'),('total_equity','净资产'),(parent_equity,'归母净资产')]:
                add(concept+'_quarter_growth',label+'环比','成长能力','%','(本期末 − 上季末) / |上季末| × 100',[spec(concept,BS),spec(concept,BS,'previous_quarter')],lambda a,b:ratio(a-b,abs(b))*100)
            add('roe','净资产收益率(ROE)','盈利能力','%','报告披露的加权平均净资产收益率',[spec('reported_roe')],lambda x:x)
            for c,label,unit,category in [('reported_ex_roe','扣非后加权净资产收益率(ROE)','%','盈利能力'),('reported_ex_basic_eps','扣非后基本每股收益','元/股','每股指标'),('reported_ex_diluted_eps','扣非后稀释每股收益','元/股','每股指标')]:
                add(c,label,category,unit,'报告补充资料披露值',[spec(c)],lambda x:x)
            for code,label,num,avg in [('roe_average','平均净资产收益率(ROE)','net_profit_attributable_to_parent',True),('roe_diluted','摊薄净资产收益率(ROE)','net_profit_attributable_to_parent',False),('roe_ex_average','扣非后平均净资产收益率(ROE)','net_profit_excluding_nonrecurring',True),('roe_ex_diluted','扣非后摊薄净资产收益率(ROE)','net_profit_excluding_nonrecurring',False)]:
                inputs=[spec(num),spec(parent_equity,BS)]+([spec(parent_equity,BS,'opening')] if avg else [])
                add(code,label,'盈利能力','%','归母口径利润 / '+('期初期末平均归母净资产' if avg else '期末归母净资产')+' × 100',inputs,(lambda n,e,b:ratio(n,(e+b)/2)*100) if avg else (lambda n,e:ratio(n,e)*100))
            for code,label,concept,table in [('diluted_eps','摊薄每股收益','net_profit_attributable_to_parent',IS),('net_assets_per_share','每股净资产',parent_equity,BS),('cash_per_share','每股经营现金流','net_operating_cash_flow',CF),('revenue_per_share','每股营业收入','revenue',IS),('operating_per_share','每股营业利润','operating_profit',IS),('cash_change_per_share','每股现金流','net_increase_in_cash',CF),('capital_reserve_per_share','每股资本公积金',concept_for('资本公积',BS),BS),('surplus_per_share','每股盈余公积金',concept_for('盈余公积',BS),BS),('retained_per_share','每股未分配利润',concept_for('未分配利润',BS),BS)]:
                add(code,label,'每股指标','元/股',label.replace('每股','')+' / 期末普通股股份总数',[spec(concept,table),spec('ordinary_share_count',BS)],ratio)
            depreciation=[spec(c,CF) for c in ['fixed_depreciation','rou_depreciation','intangible_amortization','deferred_amortization']]
            ebit=[spec('total_profit'),spec(interest)]
            add('ebit','EBIT','偿债能力','元','利润总额 + 利息费用',ebit,lambda *v:sum(v))
            add('ebitda','EBITDA','偿债能力','元','利润总额 + 利息费用 + 固定资产折旧 + 使用权资产折旧 + 无形资产摊销 + 长期待摊费用摊销',ebit+depreciation,lambda *v:sum(v))
            add('ebit_cover','EBIT保障倍数','偿债能力','倍','(利润总额 + 利息费用) / 利息费用',ebit,lambda p,i:ratio(p+i,i))
            add('ebitda_cover','EBITDA保障倍数','偿债能力','倍','EBITDA / 利息费用',ebit+depreciation,lambda p,i,*d:ratio(p+i+sum(d),i))
            add('short_debt','短期债务','偿债能力','元','短期借款 + 一年内到期的非流动负债',[spec('short_term_borrowings',BS),spec('current_portion_noncurrent_liabilities',BS)],lambda a,b:a+b)
            long=[spec('long_term_borrowings',BS),spec('lease_liabilities',BS),spec(concept_for('长期应付款',BS),BS)]
            # Defined financing balance, no missing term is replaced by zero.
            add('long_debt','长期债务','偿债能力','元','长期借款 + 租赁负债 + 长期应付款（此口径不含应付债券）',long,lambda *v:sum(v))
            debt=[spec('short_term_borrowings',BS),spec('current_portion_noncurrent_liabilities',BS)]+long
            add('interest_debt','有息债务','偿债能力','元','短期债务 + 长期债务（此口径不含应付债券及应付票据）',debt,lambda *v:sum(v))
            add('debt_ebitda','有息债务/EBITDA','偿债能力','倍','上述有息债务 / EBITDA；未年化',debt+ebit+depreciation,lambda *v:ratio(sum(v[:5]),sum(v[5:])))
            for code,label,num in [('cost_rate','营业成本率','cost'),('selling_rate','营业费用率','selling_expenses'),('admin_rate','管理费用率','administrative_expenses'),('research_rate','研发费用率','research_and_development_expenses'),('finance_rate','财务费用率','finance_expenses')]:
                add(code,label,'盈利能力','%',label.replace('率','')+' / 营业收入 × 100',[spec(num),spec('revenue')],lambda a,b:ratio(a,b)*100)
            expense=[spec(c) for c in ['selling_expenses','administrative_expenses','research_and_development_expenses','finance_expenses']]
            add('expense_rate','期间费用率','盈利能力','%','销售、管理、研发、财务费用合计 / 营业收入 × 100',expense+[spec('revenue')],lambda a,b,c,d,r:ratio(a+b+c+d,r)*100)
            add('ebit_margin','息税前利润率','盈利能力','%','EBIT / 营业收入 × 100',ebit+[spec('revenue')],lambda p,i,r:ratio(p+i,r)*100)
            add('ebitda_margin','息税折旧摊销前利润率','盈利能力','%','EBITDA / 营业收入 × 100',ebit+depreciation+[spec('revenue')],lambda *v:ratio(sum(v[:-1]),v[-1])*100)
            add('asset_reward','总资产报酬率','盈利能力','%','EBIT / 平均总资产 × 100',ebit+[spec('total_assets',BS,'opening'),spec('total_assets',BS)],lambda p,i,b,e:ratio(p+i,(b+e)/2)*100)
            add('total_cost_rate','营业总成本/营业总收入','盈利能力','%','营业总成本 / 营业总收入 × 100',[spec(concept_for('营业总成本',IS)),spec(concept_for('营业总收入',IS))],lambda a,b:ratio(a,b)*100)
            for code,label,concept in [('current_asset_share','流动资产/总资产','total_current_assets'),('current_liability_share','流动负债/总负债','total_current_liabilities')]:
                denominator='total_assets' if concept=='total_current_assets' else 'total_liabilities'
                add(code,label,'偿债能力','%',label+' × 100',[spec(concept,BS),spec(denominator,BS)],lambda a,b:ratio(a,b)*100)
                add('non_'+code,'非'+label,'偿债能力','%','(总额 − 流动部分) / 总额 × 100',[spec(concept,BS),spec(denominator,BS)],lambda a,b:ratio(b-a,b)*100)
            add('equity_multiplier_end','权益乘数','偿债能力','倍','总资产 / 净资产',[spec('total_assets',BS),spec('total_equity',BS)],ratio)
            add('working_capital','营运资金','偿债能力','元','流动资产 − 流动负债',[spec('total_current_assets',BS),spec('total_current_liabilities',BS)],lambda a,b:a-b)
            add('conservative_quick','保守速动比率','偿债能力','%','(货币资金 + 应收票据 + 应收账款) / 流动负债 × 100',[spec('cash',BS),spec('notes_receivable',BS),spec('accounts_receivable',BS),spec('total_current_liabilities',BS)],lambda a,b,c,d:ratio(a+b+c,d)*100)
            for code,label,inputs in [('cash_current_debt','现金流动负债比率',[spec('total_current_liabilities',BS)]),('cash_short_debt','经营现金流量短期债务比',debt[:2]),('cash_total_debt','经营活动净现金/总负债',[spec('total_liabilities',BS)]),('cash_interest_debt','经营活动净现金/有息债务',debt),('cash_interest_cover','现金流量利息保障倍数',[spec(interest)])]:
                add(code,label,'偿债能力','倍','经营活动净现金流 / 分母项目合计',[spec('net_operating_cash_flow',CF)]+inputs,lambda cf,*v:ratio(cf,sum(v)))
            add('cash_noncurrent_debt','经营活动净现金/非流动负债','偿债能力','倍','经营活动净现金流 / (总负债 − 流动负债)',[spec('net_operating_cash_flow',CF),spec('total_liabilities',BS),spec('total_current_liabilities',BS)],lambda c,a,b:ratio(c,a-b))
            add('cash_net_debt','经营活动净现金/净债务','偿债能力','倍','经营活动净现金流 / (有息债务 − 货币资金)',[spec('net_operating_cash_flow',CF)]+debt+[spec('cash',BS)],lambda cf,*v:ratio(cf,sum(v[:-1])-v[-1]))
            add('ebitda_debt','EBITDA/有息债务','偿债能力','倍','EBITDA / 有息债务',ebit+depreciation+debt,lambda *v:ratio(sum(v[:6]),sum(v[6:])))
            add('parent_capital_share','归母净资产/投入资本','偿债能力','%','归母净资产 / (归母净资产 + 有息债务) × 100',[spec(parent_equity,BS)]+debt,lambda e,*d:ratio(e,e+sum(d))*100)
            add('debt_capital_share','有息债务/投入资本','偿债能力','%','有息债务 / (归母净资产 + 有息债务) × 100',[spec(parent_equity,BS)]+debt,lambda e,*d:ratio(sum(d),e+sum(d))*100)
            for code,label,c in [('current_asset_turnover','流动资产周转率','total_current_assets'),('fixed_asset_turnover','固定资产周转率','fixed_assets')]:
                add(code,label,'营运能力','次','营业收入 / 期初期末平均余额',[spec('revenue'),spec(c,BS,'opening'),spec(c,BS)],lambda r,b,e:ratio(r,(b+e)/2))
            for c,label in [('total_assets','总资产'),('total_liabilities','总负债'),(parent_equity,'归母净资产')]:
                add(c+'_opening_growth',label,'成长能力','%','(期末 − 年初) / |年初| × 100',[spec(c,BS),spec(c,BS,'opening')],lambda e,b:ratio(e-b,abs(b))*100)
            for c,label in [('total_profit','利润总额'),('operating_profit','营业利润'),('net_operating_cash_flow','经营活动净现金')]:
                table=CF if c=='net_operating_cash_flow' else IS
                add(c+'_growth',label,'成长能力','%','(本期 − 上年同期) / |上年同期| × 100',[spec(c,table),spec(c,table,'previous')],lambda a,b:ratio(a-b,abs(b))*100)
            for label in ['基本每股收益','稀释每股收益']:
                c=concept_for(label,IS)
                add(c+'_growth',label,'成长能力','%','(本期 − 上年同期) / |上年同期| × 100',[spec(c),spec(c,IS,'previous')],lambda a,b:ratio(a-b,abs(b))*100)
            add('cash_sales_multiple','销售收现比','现金流量','倍','销售商品、提供劳务收到的现金 / 营业收入',[spec('cash_received_from_sales',CF),spec('revenue')],ratio)
            add('cash_profit_multiple','净现比','现金流量','倍','经营活动净现金流 / 净利润；净利润为正时适用',[spec('net_operating_cash_flow',CF),spec('net_profit')],ratio)
            add('cash_revenue_multiple','经营活动净现金/营业收入','现金流量','倍','经营活动净现金流 / 营业收入',[spec('net_operating_cash_flow',CF),spec('revenue')],ratio)
            add('net_assets_per_share_growth','每股净资产','成长能力','%','(期末每股归母净资产 − 年初每股归母净资产) / |年初每股归母净资产| × 100',[spec(parent_equity,BS),spec('ordinary_share_count',BS),spec(parent_equity,BS,'opening'),spec('ordinary_share_count',BS,'opening')],lambda e,s,b,t:ratio(ratio(e,s)-ratio(b,t),abs(ratio(b,t)))*100)
            cycle=[spec('revenue'),spec('cost'),spec('inventory',BS,'opening'),spec('inventory',BS),spec('accounts_receivable',BS,'opening'),spec('accounts_receivable',BS)]
            payable=[spec('cost'),spec('inventory',BS,'opening'),spec('inventory',BS),spec('accounts_payable',BS,'opening'),spec('accounts_payable',BS)]
            def period_days():
                if not start:raise Unavailable('缺少期间起点')
                b,e=date.fromisoformat(start),date.fromisoformat(end)
                if b.day!=1 or e.day!=monthrange(e.year,e.month)[1]:raise Unavailable('不足整月，30/360口径不适用')
                return Decimal(((e.year-b.year)*12+e.month-b.month+1)*30)
            def operating_cycle(r,c,ib,ie,ab,ae):
                return period_days()*(ratio((ib+ie)/2,c)+ratio((ab+ae)/2,r))
            def payable_turnover(c,ib,ie,pb,pe):return ratio(c+ie-ib,(pb+pe)/2)
            add('operating_cycle','营业周期','营运能力','天','存货周转天数 + 应收账款周转天数；30/360口径',cycle,operating_cycle)
            add('payable_turnover','应付账款周转率','营运能力','次','(营业成本 + 期末存货 − 期初存货) / 平均应付账款',payable,payable_turnover)
            add('payable_days','应付账款周转天数','营运能力','天','期间月数 × 30 / 应付账款周转率',payable,lambda *v:ratio(period_days(),payable_turnover(*v)))
            add('cash_cycle','现金周期','营运能力','天','营业周期 − 应付账款周转天数；30/360口径',cycle+payable,lambda *v:operating_cycle(*v[:6])-ratio(period_days(),payable_turnover(*v[6:])))
            cells.sort(key=lambda cell:CATEGORY_ORDER.index(cell['category']))
            columns.append({'key':period+'|'+str(kind),'period':period,'kind':kind,'end':end,'metrics':cells})
        result.append({'id':json.dumps(key,ensure_ascii=False),'entity':key[0],'scope':key[1],'currency':key[2],'periods':columns})
    digest=hashlib.sha256(json.dumps(statements,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'formula_version':VERSION,'input_hash':digest,'groups':result}
