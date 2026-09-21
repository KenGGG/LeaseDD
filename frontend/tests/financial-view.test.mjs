import test from 'node:test';
import assert from 'node:assert/strict';
import {buildMatrix, cellState, diagnosticSummary, formatAmount, formatCellAmount, groupKey, periodLabel, toCsv} from '../src/financial-view.ts';

const item=(id,value,status='source_verified')=>({id,concept:'cash',source_name:'货币资金',raw_value:value,raw_unit:'元',normalized_value:value,status});
const statement=(id,period,items,extra={})=>({id,document_id:id,statement_type:'balance_sheet',entity:'测试公司',scope:'consolidated',currency:'CNY',period,period_normalized:period,period_kind:'instant',raw_unit:'元',issues:[],items,...extra});
const a=statement('a','2025-12-31',[item('a1','1000000')]);
const b=statement('b','2024-12-31',[item('b1','800000')]);

test('aligns periods newest first and separates entity, scope and currency',()=>{
 const others=[{entity:'另一公司'},{scope:'parent'},{currency:'USD'}].map((x,i)=>statement('x'+i,'2025-12-31',[item('x','900')],x));
 const m=buildMatrix([b,a,...others],{group:groupKey(a),type:'balance_sheet',hideEmpty:true});
 assert.deepEqual(m.periods.map(p=>p.label),['2025年年报','2024年年报']);
 assert.equal(m.rows.length,1);
 assert.equal(m.rows[0].cells[0][0].item.normalized_value,'1000000');
 assert.equal(m.rows[0].cells[1][0].item.normalized_value,'800000');
});

test('missing cells stay empty; zero stays zero and survives hide-empty',()=>{
 const m=buildMatrix([a,statement('z','2023-12-31',[{...item('z','0'),concept:'inventory'}])],{group:groupKey(a),type:'balance_sheet',hideEmpty:true});
 const cash=m.rows.find(r=>r.concept==='cash');
 const inventory=m.rows.find(r=>r.concept==='inventory');
 assert.deepEqual(cash.cells[1],[]);
 assert.equal(cellState(inventory.cells[1]).value,'0');
 assert.equal(formatAmount('0','万元',2),'0.00');
 assert.equal(formatAmount(null,'万元',2),'—');
});

test('different candidates remain a conflict even when rounded amounts match',()=>{
 const copy=statement('c','2025-12-31',[item('c1','1000000.01','human_confirmed')]);
 const m=buildMatrix([a,copy],{group:groupKey(a),type:'balance_sheet',hideEmpty:true});
 assert.equal(cellState(m.rows[0].cells[0]).kind,'conflict');
 assert.equal(m.rows[0].cells[0].length,2);
 copy.items[0].status='human_rejected';
 assert.equal(cellState(buildMatrix([a,copy],{group:groupKey(a),type:'balance_sheet'}).rows.find(r=>r.concept==='cash').cells[0]).kind,'value');
});

test('equivalent decimals agree; invalid sources are never displayed as trusted amounts',()=>{
 const candidates=[{statement:a,item:item('1','100.00')},{statement:a,item:item('2','100')}];
 assert.equal(cellState(candidates).kind,'value');
 assert.equal(cellState([{statement:a,item:item('3','100','source_value_not_found')}]).kind,'unverified');
 assert.equal(cellState([{statement:a,item:item('4','100','pending_confirmation')}]).kind,'pending');
});

test('quarter and cumulative half-year are not merged, unknown scope remains document-specific',()=>{
 const half=statement('h','2025H1',[item('h1','100')],{statement_type:'income_statement',period_kind:'half_year',period_normalized:'2025-01-01/2025-06-30'});
 const quarter={...half,id:'q',period:'2025Q2',period_kind:'quarter',period_normalized:'2025-04-01/2025-06-30'};
 assert.equal(buildMatrix([half,quarter],{group:groupKey(half),type:'income_statement'}).periods.length,2);
 assert.notEqual(groupKey({...a,scope:'unknown'}),groupKey({...b,scope:'unknown'}));
 assert.equal(periodLabel(quarter),'2025年第二季度（单季）');
});

test('filters years and annual reports without inventing missing periods',()=>{
 const half=statement('h','2025-06-30',[item('h','4')]);
 const m=buildMatrix([a,b,half],{group:groupKey(a),type:'balance_sheet',report:'annual',startYear:'2025',endYear:'2025',descending:false});
 assert.equal(m.periods.length,1);
 assert.equal(m.periods[0].label,'2025年年报');
});

test('decimal display keeps large values exact and rounds half-up',()=>{
 assert.equal(formatAmount('900719925474099312345.67','元',2),'900,719,925,474,099,312,345.67');
 assert.equal(formatAmount('-123456789.005','元',2),'-123,456,789.01');
 assert.equal(formatAmount('123456789','万元',2),'12,345.68');
 assert.equal(formatAmount('-0.001','元',2),'0.00');
});

test('CSV escapes cells and neutralizes spreadsheet formulas',()=>{
 const csv=toCsv([['=HYPERLINK("x")','+formula','@x','safe,quoted','100.00']]);
 assert.ok(csv.startsWith('\ufeff'));
 assert.ok(csv.includes("'=HYPERLINK"));
 assert.ok(csv.includes("'+formula"));
 assert.ok(csv.includes('"safe,quoted"'));
});

test('per-share amounts keep their own units when monetary display switches',()=>{
 const eps=[{statement:a,item:{...item('eps','-0.0123'),raw_unit:'元/股'}}];
 assert.equal(formatCellAmount(eps,'万元',2),'-0.0123 元/股');
 assert.equal(formatCellAmount(eps,'亿元',0),'-0.0123 元/股');
});

test('source ordering places additional disclosed accounts inside their original sections',()=>{
 const data=statement('layout','2025-12-31',[
  {...item('cash','100'),source_order:20,source_section:'流动资产'},
  {...item('other','50'),concept:'disclosed_other',source_name:'其他流动资产',source_order:30,source_section:'流动资产'},
  {...item('total','150'),concept:'total_current_assets',source_name:'流动资产合计',source_order:40,source_section:'流动资产'},
 ]);
 const m=buildMatrix([data],{group:groupKey(data),type:'balance_sheet',hideEmpty:true,rowOrder:'source'});
 assert.deepEqual(m.rows.map(r=>r.concept),['cash','disclosed_other','total_current_assets']);
 assert.equal(m.rows[1].section,'流动资产');
 assert.equal(buildMatrix([data],{group:groupKey(data),type:'balance_sheet',hideEmpty:true,rowOrder:'standard'}).rows.at(-1).concept,'disclosed_other');
});

test('review filters count cells including source-verified candidates still awaiting human review',()=>{
 const data=statement('review','2025-12-31',[item('cash','100'),{...item('stock','0','human_confirmed'),concept:'inventory'}]);
 const base={group:groupKey(data),type:'balance_sheet',hideEmpty:true};
 assert.deepEqual(buildMatrix([data],{...base,review:'unreviewed'}).rows.map(r=>r.concept),['cash']);
 assert.deepEqual(buildMatrix([data],{...base,review:'confirmed'}).rows.map(r=>r.concept),['inventory']);
 assert.equal(buildMatrix([data],{...base,review:'conflict'}).rows.length,0);
 data.issues=['unit_unknown'];
 assert.equal(buildMatrix([data],{...base,review:'unreviewed'}).rows.length,2);
 assert.equal(buildMatrix([data],{...base,review:'confirmed'}).rows.length,0);
});

test('supplement-only periods do not create empty duplicate statement columns',()=>{
 const opening=statement('opening','2023-01-01',[item('opening','100')],{period_normalized:'2022-12-31'});
 const supplemental=statement('shares','2022-12-31',[{...item('shares','1000'),concept:'ordinary_share_count',supplemental:true}]);
 const onlyShares=statement('shares-only','2021-12-31',[{...item('shares-only','900'),supplemental:true}]);
 const m=buildMatrix([opening,supplemental,onlyShares],{group:groupKey(opening),type:'balance_sheet',hideEmpty:true});
 assert.deepEqual(m.periods.map(p=>p.label),['2022年年报']);
 assert.equal(m.rows[0].cells[0][0].statement.period,'2023-01-01');
 const restated=statement('closing','2022-12-31',[item('closing','101')]);
 assert.equal(cellState(buildMatrix([opening,restated],{group:groupKey(opening),type:'balance_sheet',hideEmpty:true}).rows[0].cells[0]).kind,'conflict');
});

test('source and formula diagnostics are separate and never suppress values',()=>{
 const conflict=statement('diag','2025-12-31',[item('cash','100')],{source_status:'consistent',source_issues:[],formula_status:'warning',checks:[{code:'assets_equal_liabilities_equity',status:'conflict',difference:'1',tolerance:'0',missing_concepts:[],involved_concepts:['total_assets'],item_ids:[]}],semantic_review_count:1,manual_review_required:true});
 assert.deepEqual(diagnosticSummary([conflict]),['资产负债表勾稽不一致']);
 assert.equal(cellState([{statement:conflict,item:conflict.items[0]}]).value,'100');
 const missing={...conflict,source_status:'needs_review',checks:[{...conflict.checks[0],status:'not_checked_missing_disclosure',missing_concepts:['total_equity']}]};
 assert.deepEqual(diagnosticSummary([missing]),['来源待核对','缺少披露项，未检查']);
});
