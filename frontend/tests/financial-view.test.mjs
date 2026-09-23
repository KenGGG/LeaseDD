import test from 'node:test';
import assert from 'node:assert/strict';
import {enterpriseCellUnit,selectEnterpriseCurrencyVariant,enterpriseToolbarOptions,mergeEnterpriseModule,enterpriseIndicatorTrend,enterpriseTrendAxis} from '../src/enterprise-financial-view.ts';
import {buildMatrix, cellState, diagnosticSummary, formatAmount, formatCellAmount, groupKey, periodLabel, toCsv} from '../src/financial-view.ts';
import {enterpriseCoverage,enterpriseStateLabel,failedEnterpriseModules,selectedEnterpriseCandidate,taskDisplay,usesPdfEvidence} from '../src/api.ts';
import {buildEnterpriseModuleView,filterEnterpriseMatrix,enterpriseHasPeriodControls,groupEnterpriseRecordTables,enterpriseDisplayValue,selectEnterpriseModule,enterpriseModuleGroups,collapseEnterpriseRows,enterpriseSourceLink,enterpriseExportUrl} from '../src/enterprise-financial-view.ts';

const item=(id,value,status='source_verified')=>({id,concept:'cash',source_name:'货币资金',raw_value:value,raw_unit:'元',normalized_value:value,status});
const statement=(id,period,items,extra={})=>({id,document_id:id,statement_type:'balance_sheet',entity:'测试公司',scope:'consolidated',currency:'CNY',period,period_normalized:period,period_kind:'instant',raw_unit:'元',issues:[],items,...extra});
const a=statement('a','2025-12-31',[item('a1','1000000')]);
test('trend axes reproduce the observed billion magnitude and six ticks without changing table values',()=>{
 const values=[169.7250892423,null,76.1294121646,87.1649239191];
 const axis=enterpriseTrendAxis(values,'亿元','人民币',true);
 assert.equal(axis.name,'十亿·人民币');assert.equal(axis.min,0);assert.equal(axis.max,17);assert.equal(axis.interval,3.4);
 assert.equal(axis.values[0],16.97250892423);assert.equal(axis.values[1],null);
 assert.equal(values[0],169.7250892423);
 const ratio=enterpriseTrendAxis([-24.757502,-55.145457,14.495727],'%','',false);
 assert.equal(ratio.min,-56);assert.equal(ratio.max,15);assert.equal(ratio.interval,14.2);
});
test('indicator trend retains selected report scope and disclosed ratios without deriving missing data',()=>{
 const view={kind:'matrix',periods:['2025年年报','2025年年报','2024年年报'],rows:[
  {key:'dataType',values:['合并期末','母公司期末','合并期末']},
  {key:'displayCurrency',values:['人民币','人民币','人民币']},
  {key:'220006',label:'营业总收入',unit:'万元',values:['871649.239191','10000',null]},
  {key:'220006_2',label:'同比',unit:'%',values:['14.495727','2',null]}
 ]};
 const result=enterpriseIndicatorTrend(view,'220006',{report:'annual',start:'',end:'',scopes:'合并期末'});
 assert.deepEqual(result.periods,['2025年年报','2024年年报']);
 assert.deepEqual(result.rows.map(row=>row.values),[['871649.239191',null],['14.495727',null]]);
 assert.deepEqual(result.currencies,['人民币','人民币']);
 assert.equal(enterpriseIndicatorTrend(view,'missing',{report:'annual',start:'',end:'',scopes:'合并期末'}),null);
});
test('source indicator formula metadata stays aligned after the report header and is descriptive only',()=>{
 const module={parsed_payload:{periods:['2025年年报'],rows:[{key:'a',name:'扣非后归母净利润',values:[null]},{key:'b',name:'其他',formula:'行内说明',values:['2']}],metadata:{formula:['报告期','优先取披露数据，若无则取归母净利润-非经常性损益。','元数据说明']}}};
 const view=buildEnterpriseModuleView(module);
 assert.equal(view.rows[0].formula,'优先取披露数据，若无则取归母净利润-非经常性损益。');
 assert.equal(view.rows[1].formula,'行内说明');
 assert.deepEqual(view.rows[0].values,[null]);
 assert.equal(module.parsed_payload.rows[0].formula,undefined);
});
test('duplicate source group keys have independent collapse identities without changing source keys',()=>{
 const module={parsed_payload:{periods:['2025年年报'],rows:[
  {key:'0',name:'第一组',children:[{key:'a',name:'每股收益',values:['1']}]},
  {key:'0',name:'第二组',children:[{key:'b',name:'每股净资产',values:['2']}]}
 ]}};
 const view=buildEnterpriseModuleView(module);
 assert.notEqual(view.rows[0].uiKey,view.rows[2].uiKey);
 assert.deepEqual(collapseEnterpriseRows(view.rows,new Set([view.rows[0].uiKey])).map(row=>row.label),['第一组','第二组','每股净资产']);
 assert.equal(view.rows[0].key,'0');assert.equal(view.rows[2].key,'0');
 assert.equal(module.parsed_payload.rows[0].uiKey,undefined);
});
test('lazy module responses cannot overwrite another project, batch or module',()=>{
 const cache={pid:'project',importId:'batch',modules:[{module_key:'balance'},{module_key:'income'}]};
 const result={import_id:'batch',modules:[{module_key:'balance',parsed_payload:{rows:[{values:['10']}]}}]};
 assert.equal(mergeEnterpriseModule(cache,'other','batch','balance',result),cache);
 assert.equal(mergeEnterpriseModule(cache,'project','old','balance',result),cache);
 assert.equal(mergeEnterpriseModule(cache,'project','batch','income',result),cache);
 assert.equal(mergeEnterpriseModule(cache,'project','batch','balance',{...result,import_id:'old'}),cache);
 const merged=mergeEnterpriseModule(cache,'project','batch','balance',result);
 assert.deepEqual(merged.modules[0].parsed_payload.rows[0].values,['10']);
 assert.equal(merged.modules[1],cache.modules[1]);
 assert.equal(cache.modules[0].parsed_payload,undefined);
});
test('source disabled modules are not blank disclosures or imported-data coverage',()=>{
 const module={category:'notes',state:'unavailable',parsed_payload:{rows:[],metadata:{unavailable:true}}};
 assert.deepEqual(buildEnterpriseModuleView(module),{kind:'empty',confirmed:false,unavailable:true});
 assert.equal(enterpriseCoverage([module,{category:'notes',state:'completed'}]).notes,1);
});
test('initial financial scope matches source original consolidated view rather than every variant at once',()=>{
 assert.equal(enterpriseToolbarOptions({module_key:'balance_sheet',category:'statements'}).defaultScope,'合并期末');
 assert.equal(enterpriseToolbarOptions({module_key:'profitability',category:'analysis'}).defaultScope,'合并期末');
 assert.equal(enterpriseToolbarOptions({module_key:'per_share',category:'analysis'}).defaultScope,'all');
 assert.equal(enterpriseToolbarOptions({module_key:'main_business',category:'notes'}).defaultKind,'原始报表');
 assert.equal(enterpriseToolbarOptions({module_key:'balance_sheet',category:'statements'}).defaultYears,3);
 assert.equal(enterpriseToolbarOptions({module_key:'profitability',category:'analysis'}).defaultYears,5);
});
test('3Y is a rolling report-period window, retaining prior-year quarters after the cutoff',()=>{
 const view={kind:'matrix',periods:['2026年中报','2023年三季报','2023年中报'],rows:[{key:'amount',values:['1','2','3']}]};
 const filter={report:'all',start:'',end:'',descending:true,hideEmpty:false,windowYears:3};
 assert.deepEqual(filterEnterpriseMatrix(view,filter).rows[0].values,['1','2']);
 assert.equal(new URL(enterpriseExportUrl('p','balance',filter,'万元',2),'https://local').searchParams.get('window_years'),'3');
});
test('restricted assets uses its verified year/unit toolbar without invented currency or report scopes',()=>{
 const options=enterpriseToolbarOptions({module_key:'restricted_assets',category:'notes'});
 assert.equal(options.yearsAndUnit,true);
 assert.equal(options.currency,false);
 assert.equal(options.dataKinds,false);
 assert.equal(options.halfAnnualOnly,true);
 assert.equal(enterpriseToolbarOptions({module_key:'main_business',category:'notes'}).currency,true);
 assert.equal(enterpriseToolbarOptions({module_key:'cash_notes',category:'notes'}).yearsAndUnit,false);
});
test('business toolbar separates standalone data kinds and never scales ratios or exchange rates',()=>{
 const module={module_key:'main_business',category:'notes',request_params:{unitCode:'4'},parsed_payload:{periods:['2025年年报','2025年年报','2025年年报'],rows:[
  {key:'dataType',name:'数据类型',values:['原始报表','同比','占收入比']},
  {key:'120050',name:'营业收入',unit:'',values:['10000','12.5','100']},
  {key:'900042',name:'毛利率(%)',unit:'',values:['20','2','3']},
  {key:'conversionRate',name:'转换汇率',unit:'',values:['7','7','7']}
 ]}};
 const view=buildEnterpriseModuleView(module);
 assert.equal(view.rows[1].unit,'万元');assert.equal(view.rows[2].unit,'%');assert.equal(view.rows[3].unit,'');
 const filtered=filterEnterpriseMatrix(view,{report:'all',start:'',end:'',descending:true,hideEmpty:false,dataKinds:'同比',scopes:'all'});
 assert.deepEqual(filtered.rows[1].values,['12.5']);
 assert.equal(enterpriseCellUnit(filtered.rows,filtered.rows[1],0),'%');
 assert.equal(enterpriseDisplayValue('12.5',enterpriseCellUnit(filtered.rows,filtered.rows[1],0),'亿元',2),'12.50');
 assert.equal(module.parsed_payload.rows[1].unit,'');
});
test('currency selection reads the exact saved response and never falls back to another currency',()=>{
 const module={module_key:'balance',request_params:{unit:'万元'},response_sha256:'bundle',raw_payload:{responses:[{payload:{data:'USD-original'}}]},parsed_payload:{variants:[{request_params:{displayCurrency:'USD',rateType:'2'},parsed:{periods:['2025年年报'],rows:[{values:['14.25']}]}}]}};
 const selected=selectEnterpriseCurrencyVariant(module,'USD','2');
 assert.equal(selected.parsed_payload.rows[0].values[0],'14.25');
 assert.equal(selected.raw_payload.data,'USD-original');
 assert.equal(selected.response_sha256,'bundle');
 assert.equal(selectEnterpriseCurrencyVariant(module,'EUR','1'),undefined);
});
test('mixed scope percentage units survive column filtering and reordering',()=>{
 const amount={key:'assets',unit:'万元',values:['10000','12.5']};
 const rows=[{key:'dataType',values:['合并期末','合并期末同比(%)']},amount];
 assert.equal(enterpriseCellUnit(rows,amount,0),'万元');
 assert.equal(enterpriseCellUnit(rows,amount,1),'%');
 assert.equal(enterpriseDisplayValue('12.5',enterpriseCellUnit(rows,amount,1),'亿元',2),'12.50');
});
test('scope and data kind filters keep the matching source column, not just its year',()=>{
 const view={kind:'matrix',periods:['2025年年报','2025年年报','2025年年报'],rows:[{key:'dataType',values:['合并期末','母公司期末','母公司期末同比(%)']},{key:'assets',unit:'万元',values:['100','80','12.5']}]};
 const selected=filterEnterpriseMatrix(view,{report:'all',start:'',end:'',descending:true,hideEmpty:false,scopes:'母公司期末',dataKinds:'同比增长率'});
 assert.deepEqual(selected.rows[1].values,['12.5']);
 assert.equal(enterpriseCellUnit(selected.rows,selected.rows[1],0),'%');
 assert.deepEqual(view.rows[1].values,['100','80','12.5']);
 assert.equal(filterEnterpriseMatrix(view,{report:'all',start:'',end:'',descending:true,hideEmpty:false,scopes:''}).periods.length,0);
 const query=new URL(enterpriseExportUrl('p','balance',{report:'all',start:'',end:'',descending:true,hideEmpty:false,scopes:'母公司期末',dataKinds:'同比增长率'},'亿元',2),'http://local').searchParams;
 assert.equal(query.get('scopes'),'母公司期末');
 assert.equal(query.get('data_kinds'),'同比增长率');
});
test('analysis scope filtering reads the source reportRange metadata',()=>{
 const view={kind:'matrix',periods:['2025年年报','2025年年报'],rows:[{key:'reportRange',values:['合并期末','母公司期末']},{key:'ratio',unit:'%',values:['10','8']}]};
 const result=filterEnterpriseMatrix(view,{report:'all',start:'',end:'',descending:true,hideEmpty:false,scopes:'母公司期末'});
 assert.deepEqual(result.rows[1].values,['8']);
});
test('missing selected module must not silently display a different financial module',()=>{
 const modules=[{module_key:'balance_sheet',module_name:'资产负债表'}];
 assert.equal(selectEnterpriseModule(modules,'利润表'),undefined);
 assert.equal(selectEnterpriseModule(modules,'资产负债表'),modules[0]);
});
test('enterprise note navigation retains source parent groups without renaming leaves',()=>{
 const modules=[{module_key:'audit',module_name:'审计报告'},{module_key:'aging',module_name:'应收账款账龄分析',request_params:{menu_parent:'应收账款'}},{module_key:'top',module_name:'前五名应收账款',request_params:{menu_parent:'应收账款'}}];
 const groups=enterpriseModuleGroups(modules);
 assert.deepEqual(groups.map(g=>[g.name,g.children.map(m=>m.module_key)]),[['审计报告',['audit']],['应收账款',['aging','top']]]);
 assert.equal(groups[1].nested,true);
});
test('collapsing a financial parent hides descendants but preserves following siblings and raw data',()=>{
 const rows=[{key:'parent',depth:1},{key:'child',depth:2},{key:'grandchild',depth:3},{key:'next',depth:1}];
 assert.deepEqual(collapseEnterpriseRows(rows,new Set(['parent'])).map(r=>r.key),['parent','next']);
 assert.equal(rows.length,4);
});
test('source document references become safe short links rather than stretching period columns',()=>{
 assert.deepEqual(enterpriseSourceLink('年报__https://example.com/annual.pdf'),{label:'年报',href:'https://example.com/annual.pdf'});
 assert.equal(enterpriseSourceLink('查看__javascript:alert(1)'),null);
 assert.equal(enterpriseSourceLink('100.00'),null);
});
test('Excel download targets the existing data route with current view filters and source hash',()=>{
 const url=new URL(enterpriseExportUrl('project','cash_notes',{report:'latest,annual',start:'2020',end:'2026',descending:false,hideEmpty:true},'万元',4,'a'.repeat(64)),'https://app.test');
 assert.equal(url.pathname,'/api/projects/project/enterprise/data');
 assert.equal(url.searchParams.get('export_format'),'xlsx');
 assert.equal(url.searchParams.get('report'),'latest,annual');
 assert.equal(url.searchParams.get('descending'),'false');
 assert.equal(url.searchParams.get('expected_hash'),'a'.repeat(64));
 assert.equal(url.searchParams.get('decimals'),'4');
});
test('enterprise filters preserve period-cell alignment and retain disclosed zero',()=>{
 const view={kind:'matrix',periods:['2026年中报','2025年年报','2025年三季报','2024年年报'],rows:[{key:'x',label:'收入',unit:'万元',depth:1,section:false,values:['10','0','20','30']},{key:'empty',label:'空',unit:'万元',depth:1,section:false,values:[null,'',null,null]}]};
 const result=filterEnterpriseMatrix(view,{report:'annual',start:'2025',end:'2025',descending:true,hideEmpty:true});
 assert.deepEqual(result.periods,['2025年年报']);assert.deepEqual(result.rows.map(r=>r.values),[['0']]);
 assert.deepEqual(view.rows[0].values,['10','0','20','30']);
});
test('enterprise monetary display uses exact decimal shifts and leaves percentages unscaled',()=>{
 assert.equal(enterpriseDisplayValue('100000','万元','十亿元',2),'1.00');
 assert.equal(enterpriseDisplayValue('1039981.78','万元','亿元',2),'104.00');
 assert.equal(enterpriseDisplayValue('-116203.93','万元','万元',2),'-116,203.93');
 assert.equal(enterpriseDisplayValue('167.92','%','亿元',2),'167.92');
 assert.equal(enterpriseDisplayValue(null,'万元','元',2),'');
 assert.equal(enterpriseDisplayValue('合并期末','','万元',2),'合并期末');
});
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

test('enterprise helpers preserve candidates and require explicit selection',()=>{
 const candidates=[{code:'a',name:'甲公司',identity:{}},{code:'b',name:'甲科技',identity:{}}];
 assert.equal(selectedEnterpriseCandidate(candidates,''),null);
 assert.equal(selectedEnterpriseCandidate(candidates,'b')?.name,'甲科技');
 assert.equal(candidates.length,2);
});

test('enterprise coverage, partial state and task labels stay provider-specific',()=>{
 const modules=[...Array(4)].map((_,i)=>({category:i?'statements':'indicators',module_key:'s'+i})).concat(
  [...Array(7)].map((_,i)=>({category:'analysis',module_key:'a'+i})),
  [...Array(10)].map((_,i)=>({category:'notes',module_key:'n'+i})),
 );
 assert.deepEqual(enterpriseCoverage(modules),{statements:4,analysis:7,notes:10,total:21});
 assert.equal(enterpriseStateLabel('partial'),'导入不完整');
 assert.deepEqual(failedEnterpriseModules({x:{state:'failed',error:'empty_module'},y:{state:'completed',error:null}}),['x']);
 assert.deepEqual(taskDisplay({kind:'enterprise_import',mode:'qyyjt'}),{label:'企业预警通财务导入',mode:'结构化接口'});
 assert.equal(taskDisplay({kind:'enterprise_import',mode:'qyyjt'}).label.includes('Agnes'),false);
 assert.equal(usesPdfEvidence('enterprise_warning'),false);
 assert.equal(usesPdfEvidence(undefined),true);
});

test('enterprise indicator and analysis matrices preserve hierarchy, periods, units and blanks',()=>{
 const module={module_key:'per_share',module_name:'每股指标',category:'analysis',parsed_payload:{periods:['2026年中报','2025年年报'],rows:[
  {name:'上市公司披露',value:'group',highlight:true,unit:'',values:[null,null],children:[
   {name:'基本每股收益(元)',value:'eps',unit:'元',values:['0.42','0.38'],children:[]},
   {name:'稀释每股收益(元)',value:'diluted',unit:'元',values:[null,''] ,children:[]},
  ]},
 ]}};
 const view=buildEnterpriseModuleView(module);
 assert.equal(view.kind,'matrix');
 assert.deepEqual(view.periods,['2026年中报','2025年年报']);
 assert.deepEqual(view.rows.map(row=>[row.label,row.depth,row.unit,row.values]),[
  ['上市公司披露',0,'',[null,null]],
  ['基本每股收益(元)',1,'元/股',['0.42','0.38']],
  ['稀释每股收益(元)',1,'元/股',[null,'']],
 ]);
});

test('enterprise note records keep provider headers, period groups and raw formatted values',()=>{
 const module={module_key:'major_customers',module_name:'主要销售客户',category:'notes',parsed_payload:{
  head:[['客户名称','第一名','合计'],['客户名称','第一名','合计']],
  rows:[[['销售额','6.04亿','9.08亿'],['占比','31.30%','47.07%']], [['销售额','5.00亿','8.00亿']]],
  metadata:{report:['20251231','20241231']},
 }};
 const view=buildEnterpriseModuleView(module);
 assert.equal(view.kind,'records');
 assert.deepEqual(view.tables.map(table=>table.title),['2025年年报','2024年年报']);
 assert.deepEqual(view.tables[0].headers,['客户名称','销售额','占比']);
 assert.deepEqual(view.tables[0].rows[0],['第一名','6.04亿','31.30%']);
 assert.equal(view.tables[0].rows[0][1],'6.04亿');
});

test('source customer records have export only while period matrices have report controls',()=>{
 const records=buildEnterpriseModuleView({module_key:'major_customers',category:'notes',parsed_payload:{head:[['客户名称','第一名']],rows:[[ ['金额','1亿'] ]],metadata:{report:['20251231']}}});
 const matrix=buildEnterpriseModuleView({module_key:'cash_notes',category:'notes',parsed_payload:{head:['项目','现金'],rows:[['20251231','1亿']],metadata:{}}});
 assert.equal(enterpriseHasPeriodControls(records),false);
 assert.equal(enterpriseHasPeriodControls(matrix),true);
});

test('customer note repeats year groups under one matching header without merging changed layouts',()=>{
 const tables=[
  {title:'2025年年报',headers:['客户','金额'],rows:[['第一名','6亿']]},
  {title:'2024年年报',headers:['客户','金额'],rows:[['第一名','5亿']]},
  {title:'2023年年报',headers:['客户','金额','占比'],rows:[['第一名','4亿','30%']]},
 ];
 const groups=groupEnterpriseRecordTables(tables);
 assert.deepEqual(groups.map(group=>group.map(table=>table.title)),[['2025年年报','2024年年报'],['2023年年报']]);
 assert.equal(groups[0][0].rows[0][1],'6亿');
 assert.equal(groups[0][1].rows[0][1],'5亿');
});

test('enterprise flat notes transpose periods into columns without changing formatted values',()=>{
 const view=buildEnterpriseModuleView({module_key:'cash_notes',category:'notes',parsed_payload:{
  head:['项目名称','现金','银行存款','合计'],rows:[['20260630','2.87万','','32.29亿'],['20251231','1.83万','0','19.19亿']],metadata:{level:['0','1','1','1']},
 }});
 assert.equal(view.kind,'matrix');
 assert.deepEqual(view.periods,['2026年中报','2025年年报']);
 assert.deepEqual(view.rows.map(r=>r.values),[['2.87万','1.83万'],['','0'],['32.29亿','19.19亿']]);
 assert.equal(view.rows[2].bold,true);
 assert.equal(view.rows[2].section,false);
});

test('enterprise subtotal bold and expandable amount rows are not orange section headings',()=>{
 const view=buildEnterpriseModuleView({module_key:'solvency',category:'analysis',parsed_payload:{periods:['2025年年报'],rows:[
  {name:'合计',key:'total',bold:true,values:['30']},
  {name:'应收款项',key:'receivable',values:['10'],children:[{name:'应收账款',key:'accounts',values:['10']}]},
  {name:'上市公司披露',key:'section',highlight:true,values:[null]},
 ]}});
 assert.deepEqual(view.rows.map(r=>r.section),[false,false,false,true]);
 assert.equal(view.rows[0].bold,true);
 assert.equal(view.rows[1].hasChildren,true);
});

test('enterprise statement sections and child indent use original level and blankNum evidence',()=>{
 const view=buildEnterpriseModuleView({module_key:'balance_sheet',category:'statements',parsed_payload:{periods:['2025年年报'],rows:[
  {name:'流动资产',key:'group',level:0,values:['']},{name:'应收票据及应收账款',key:'receivable',level:1,values:['10']},{name:'应收账款',key:'accounts',level:1,values:['10']},{name:'流动资产合计',key:'total',level:1,values:['10']},
 ],metadata:{black:[0,1,0,0,1],blankNum:[0,0,2,3,1]}}});
 assert.deepEqual(view.rows.map(r=>[r.section,r.bold,r.depth]),[[true,true,0],[false,false,2],[false,false,3],[false,true,1]]);
 assert.equal(view.rows[1].hasChildren,true);
});

test('enterprise report multi-selection keeps latest plus annual and hides only blank placeholders',()=>{
 const view={kind:'matrix',periods:['2024年年报','2026年中报','2025年三季报','2025年年报'],rows:[
  {key:'zero',values:['0','','','0']},{key:'blank',values:['-','—','',null]},
 ]};
 const result=filterEnterpriseMatrix(view,{report:'latest,annual',start:'',end:'',descending:true,hideEmpty:true});
 assert.deepEqual(result.periods,['2026年中报','2025年年报','2024年年报']);
 assert.deepEqual(result.rows.map(r=>r.key),['zero']);
 assert.deepEqual(result.rows[0].values,['','0','0']);
});

test('enterprise confirmed empty modules remain explicit instead of becoming zero rows',()=>{
 const view=buildEnterpriseModuleView({module_key:'long_term_receivables',module_name:'长期应收款',category:'notes',parsed_payload:{head:[],rows:[],values:[],metadata:{empty:true}}});
 assert.deepEqual(view,{kind:'empty',confirmed:true});
});

test('enterprise matrix uses provider export header units instead of database units',()=>{
 const view=buildEnterpriseModuleView({module_key:'main_indicators',module_name:'主要财务指标',category:'indicators',parsed_payload:{
  periods:['2025年年报'],
  rows:[{name:'营业收入',key:'revenue',unit:'元',values:['95299.72']},{name:'同比',key:'growth',unit:'%',values:['44.35']}],
  metadata:{headExport:['指标名称','营业收入（万元）','同比（%）']},
 }});
 assert.deepEqual(view.rows.map(row=>[row.label,row.unit]),[['营业收入','万元'],['同比','%']]);
});

test('enterprise analysis view hydrates legacy child values from the saved raw response',()=>{
 const view=buildEnterpriseModuleView({module_key:'per_share',module_name:'每股指标',category:'analysis',
  parsed_payload:{periods:['2026年中报'],rows:[{name:'上市公司披露',value:'group',values:[null],children:[{name:'基本每股收益',value:'eps',unit:'元',children:[]}]}]},
  raw_payload:{data:{dataList:[{reportDate2:'2026年中报',eps:'0.42'}]}},
 });
 assert.equal(view.kind,'matrix');
 assert.deepEqual(view.rows[1].values,['0.42']);
});
