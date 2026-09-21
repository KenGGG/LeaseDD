import type {FinancialItem, FinancialStatement} from './api';

export const statementLabels = {balance_sheet:'资产负债表',income_statement:'利润表',cash_flow_statement:'现金流量表'};
export function diagnosticSummary(statements:FinancialStatement[]){
 const labels:string[]=[];
 if(statements.some(s=>s.source_status==='needs_review'))labels.push('来源待核对');
 if(statements.some(s=>(s.checks||[]).some(c=>c.status==='conflict')))labels.push((statementLabels[statements[0]?.statement_type]||'报表')+'勾稽不一致');
 if(statements.some(s=>(s.checks||[]).some(c=>c.status==='not_checked_missing_disclosure')))labels.push('缺少披露项，未检查');
 return labels;
}
export const scopeLabels:Record<string,string> = {consolidated:'合并报表',parent:'母公司报表',standalone:'单体报表',unknown:'口径待核对'};
export const statusLabels:Record<string,string> = {source_verified:'来源已核验 · 待人审',pending_confirmation:'待核对',human_confirmed:'人工已确认',human_rejected:'已拒绝',source_value_not_found:'来源未验证'};
type CatalogRow={concept:string;label:string;section:string;total:boolean};
function rows(section:string, pairs:string):CatalogRow[]{
 return pairs.split('|').map(pair=>{const [concept,label]=pair.split(':');return {concept,label,section,total:/合计|总计|净额|净利润|利润总额/.test(label)}});
}
export const catalogs:Record<FinancialStatement['statement_type'],CatalogRow[]> = {
 balance_sheet:[
  ...rows('流动资产','cash:货币资金|trading_financial_assets:交易性金融资产|notes_receivable:应收票据|accounts_receivable:应收账款|receivables_financing:应收款项融资|prepayments:预付款项|other_receivables:其他应收款|inventory:存货|contract_assets:合同资产|total_current_assets:流动资产合计'),
  ...rows('非流动资产','fixed_assets:固定资产|construction_in_progress:在建工程|right_of_use_assets:使用权资产|intangible_assets:无形资产|total_assets:资产总计'),
  ...rows('流动负债','short_term_borrowings:短期借款|notes_payable:应付票据|accounts_payable:应付账款|contract_liabilities:合同负债|other_payables:其他应付款|current_portion_noncurrent_liabilities:一年内到期的非流动负债|total_current_liabilities:流动负债合计'),
  ...rows('非流动负债','long_term_borrowings:长期借款|bonds_payable:应付债券|lease_liabilities:租赁负债|total_liabilities:负债合计'),
  ...rows('所有者权益','total_equity:所有者权益合计'),
 ],
 income_statement:[
  ...rows('营业收支','revenue:营业收入|cost:营业成本|taxes_and_surcharges:税金及附加|selling_expenses:销售费用|administrative_expenses:管理费用|research_and_development_expenses:研发费用|finance_expenses:财务费用|other_income:其他收益|investment_income:投资收益|credit_impairment_loss:信用减值损失|asset_impairment_loss:资产减值损失'),
  ...rows('利润','operating_profit:营业利润|total_profit:利润总额|income_tax_expense:所得税费用|net_profit:净利润|net_profit_attributable_to_parent:归属于母公司股东的净利润|net_profit_excluding_nonrecurring:扣除非经常性损益后的净利润'),
 ],
 cash_flow_statement:[
  ...rows('经营活动','cash_received_from_sales:销售商品、提供劳务收到的现金|operating_cash_inflows:经营活动现金流入小计|operating_cash_outflows:经营活动现金流出小计|net_operating_cash_flow:经营活动产生的现金流量净额'),
  ...rows('投资活动','net_investing_cash_flow:投资活动产生的现金流量净额'),
  ...rows('筹资活动','net_financing_cash_flow:筹资活动产生的现金流量净额'),
  ...rows('现金及现金等价物','net_increase_in_cash:现金及现金等价物净增加额|ending_cash_balance:期末现金及现金等价物余额'),
 ],
};
export type Candidate={statement:FinancialStatement;item:FinancialItem};
export function groupKey(s:FinancialStatement){
 // Unresolved scopes/currencies cannot silently combine documents.
 return JSON.stringify([s.entity,s.scope,s.currency,(!s.entity||s.scope==='unknown'||!s.currency||s.currency==='unknown')?s.document_id:'']);
}
function periodKey(s:FinancialStatement){return JSON.stringify([s.period_normalized||s.period,s.period_kind||'',s.period_normalized&&s.period_kind?'':s.document_id])}
function periodEnd(s:FinancialStatement){return (s.period_normalized||s.period).split('/').at(-1)||s.period}
export function periodLabel(s:FinancialStatement){
 const end=periodEnd(s),year=end.slice(0,4);
 if(s.period_kind==='quarter')return `${year}年${['第一','第二','第三','第四'][Math.ceil(Number(end.slice(5,7))/3)-1]||''}季度（单季）`;
 if(s.period_kind==='year'||s.period_kind==='annual'||(s.period_kind==='instant'&&end.endsWith('-12-31')))return year+'年年报';
 if(s.period_kind==='half_year'||(s.period_kind==='instant'&&end.endsWith('-06-30')))return year+'年中报';
 if(s.period_kind==='instant'&&end.endsWith('-03-31'))return year+'年一季报';
 if(s.period_kind==='instant'&&end.endsWith('-09-30'))return year+'年三季报';
 return s.period_normalized||s.period||'期间待核对';
}
type Options={group:string;type:FinancialStatement['statement_type'];hideEmpty?:boolean;report?:string;startYear?:string;endYear?:string;descending?:boolean;query?:string;rowOrder?:'source'|'standard';review?:string};
export function buildMatrix(statements:FinancialStatement[],options:Options){
 let selected=statements.map(s=>({...s,items:s.items.filter(i=>!i.supplemental)})).filter(s=>s.items.length>0).filter(s=>{
  if(groupKey(s)!==options.group||s.statement_type!==options.type)return false;
  const year=periodEnd(s).slice(0,4),label=periodLabel(s);
  if(options.startYear&&(!/^\d{4}$/.test(year)||year<options.startYear))return false;
  if(options.endYear&&(!/^\d{4}$/.test(year)||year>options.endYear))return false;
  if(options.report==='annual'&&!label.endsWith('年报'))return false;
  if(options.report==='half'&&!label.endsWith('中报'))return false;
  if(options.report==='quarter'&&!label.includes('季'))return false;
  return true;
 });
 const periodMap=new Map<string,FinancialStatement>();
 selected.forEach(s=>periodMap.set(periodKey(s),s));
 const periods=[...periodMap].map(([key,s])=>({key,label:periodLabel(s),date:s.period_normalized||s.period,end:periodEnd(s)})).sort((a,b)=>(a.end.localeCompare(b.end)||a.key.localeCompare(b.key))*(options.descending===false?1:-1));
 selected=selected.map(s=>({...s,items:s.items.filter(i=>!i.supplemental)}));
 let catalog=[...catalogs[options.type]];
 selected.forEach(s=>s.items.forEach(i=>{if(!catalog.some(r=>r.concept===i.concept))catalog.push({concept:i.concept,label:i.source_label||i.source_name||i.concept,section:'其他披露科目',total:false})}));
 if(options.rowOrder!=='standard'){
  const ordered=new Map<string,CatalogRow>();
  const sources=[...selected].sort((a,b)=>periodEnd(b).localeCompare(periodEnd(a))||a.document_id.localeCompare(b.document_id)||a.id.localeCompare(b.id));
  for(const s of sources){
   const items=s.items.filter(i=>i.source_order!==undefined).sort((a,b)=>a.source_order!-b.source_order!);
   for(const item of items){
    if(ordered.has(item.concept))continue;
    const original=catalog.find(r=>r.concept===item.concept)!;
    ordered.set(item.concept,{...original,section:item.source_section||original.section,total:original.total||/合计|总计|小计|总额/.test(item.source_name)});
   }
  }
  if(ordered.size)catalog=[...ordered.values(),...catalog.filter(r=>!ordered.has(r.concept)).map(r=>({...r,section:'其他科目（未定位原表顺序）'}))];
 }
 const allRows=catalog.map(row=>({...row,cells:periods.map(p=>selected.filter(s=>periodKey(s)===p.key).flatMap(statement=>statement.items.filter(i=>i.concept===row.concept).map(item=>({statement,item}))))}));
 const counts={unreviewed:0,conflict:0,confirmed:0};
 const needsReview=(c:Candidate[])=>['pending','unverified','conflict'].includes(cellState(c).kind)||c.some(v=>!['human_confirmed','human_rejected'].includes(v.item.status));
 allRows.forEach(r=>r.cells.forEach(c=>{const state=cellState(c);if(state.kind==='conflict')counts.conflict++;if(state.kind==='value'&&state.confirmed)counts.confirmed++;if(needsReview(c))counts.unreviewed++}));
 const result=allRows.filter(row=>(!options.hideEmpty||row.cells.some(c=>c.length>0))&&(!options.query||row.label.includes(options.query)||row.cells.flat().some(c=>c.item.source_name.includes(options.query!)))&&(!options.review||options.review==='all'||row.cells.some(c=>{const state=cellState(c);return options.review==='conflict'?state.kind==='conflict':options.review==='confirmed'?state.kind==='value'&&state.confirmed:needsReview(c)})));
 return {periods,rows:result,statements:selected,counts};
}
function canonical(value:string){return value.replace(/^(-?)0+(?=\d)/,'$1').replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,'').replace(/^-0$/,'0')}
export function cellState(candidates:Candidate[]):{kind:'empty'|'rejected'|'unverified'|'conflict'|'pending'|'value';value:string|null;confirmed:boolean}{
 const active=candidates.filter(c=>c.item.status!=='human_rejected');
 if(!candidates.length)return {kind:'empty',value:null,confirmed:false};
 if(!active.length)return {kind:'rejected',value:null,confirmed:false};
 if(active.some(c=>c.item.normalized_value===null||! /^-?\d+(\.\d+)?$/.test(c.item.normalized_value)||c.item.status==='source_value_not_found'))return {kind:'unverified',value:null,confirmed:false};
 if(new Set(active.map(c=>canonical(c.item.normalized_value!))).size>1)return {kind:'conflict',value:null,confirmed:false};
 const pending=active.some(c=>!['source_verified','human_confirmed'].includes(c.item.status)||c.statement.issues.length>0);
 return {kind:pending?'pending':'value',value:active[0].item.normalized_value,confirmed:active.every(c=>c.item.status==='human_confirmed')};
}
export const unitPowers:Record<string,number>={'元':0,'千元':3,'万元':4,'百万元':6,'亿元':8};
export function formatAmount(value:string|null,unit:string,decimals:number):string{
 if(value===null||! /^-?\d+(\.\d+)?$/.test(value)||!(unit in unitPowers))return '—';
 const negative=value.startsWith('-'),[whole,fraction='']=value.replace(/^-/,'').split('.');
 const raw=BigInt(whole+fraction),shift=fraction.length+unitPowers[unit]-decimals;
 const divisor=10n**BigInt(Math.abs(shift));
 const rounded=shift>0?(raw+divisor/2n)/divisor:raw*divisor;
 const digits=rounded.toString().padStart(decimals+1,'0');
 const integer=(decimals?digits.slice(0,-decimals):digits).replace(/\B(?=(\d{3})+(?!\d))/g,',');
 return (negative&&rounded!==0n?'-':'')+integer+(decimals?'.'+digits.slice(-decimals):'');
}
export function formatCellAmount(candidates:Candidate[],unit:string,decimals:number){
 const state=cellState(candidates);
 const active=candidates.filter(c=>c.item.status!=='human_rejected');
 if(active.length&&active.every(c=>c.item.raw_unit==='元/股'))return formatAmount(state.value,'元',4)+' 元/股';
 return formatAmount(state.value,unit,decimals);
}
export function toCsv(rows:string[][]){
 return '\ufeff'+rows.map(row=>row.map(value=>{
  const safe=/^[\s]*[=+@-]/.test(value)&&! /^-?\d[\d,.]*$/.test(value)?"'"+value:value;
  return '"'+safe.replaceAll('"','""')+'"';
 }).join(',')).join('\r\n');
}
