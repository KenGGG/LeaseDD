import type {EnterpriseModuleData} from './api';
import {formatAmount,unitPowers} from './financial-view.ts';

export type EnterpriseMatrixRow={key:string;uiKey?:string;label:string;unit:string;definitionUnit?:string;depth:number;section:boolean;bold?:boolean;hasChildren?:boolean;values:unknown[];description?:string|null;formula?:string|null};
export type EnterpriseRecordTable={title:string;headers:string[];rows:unknown[][]};
export type EnterpriseModuleView=
 | {kind:'matrix';periods:string[];rows:EnterpriseMatrixRow[]}
 | {kind:'records';tables:EnterpriseRecordTable[]}
 | {kind:'empty';confirmed:boolean;unavailable?:boolean};
// The verified nested customer/supplier record pages expose only Excel export;
// their year headings are data groups, not a period toolbar.
export function enterpriseHasPeriodControls(view:EnterpriseModuleView){return view.kind==='matrix'}
export function groupEnterpriseRecordTables(tables:EnterpriseRecordTable[]){
 const groups:EnterpriseRecordTable[][]=[];
 for(const table of tables){
  const current=groups[groups.length-1],head=current?.[0]?.headers;
  if(head&&head.length===table.headers.length&&head.every((value,index)=>value===table.headers[index]))current.push(table);
  else groups.push([table]);
 }
 return groups;
}

const object=(value:unknown):Record<string,unknown>=>value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
const strings=(value:unknown):string[]=>Array.isArray(value)?value.map(item=>item==null?'':String(item)):[];
const rowArray=(value:unknown):unknown[][]=>Array.isArray(value)?value.filter(Array.isArray) as unknown[][]:[];
export type EnterpriseModuleCache={pid:string;importId:string|null;modules:EnterpriseModuleData[]};
export function mergeEnterpriseModule(cache:EnterpriseModuleCache,pid:string,importId:string,moduleKey:string,result:{import_id:string|null;modules:EnterpriseModuleData[]}):EnterpriseModuleCache{
 if(cache.pid!==pid||cache.importId!==importId||result.import_id!==importId||result.modules.length!==1||result.modules[0].module_key!==moduleKey)return cache;
 return {...cache,modules:cache.modules.map(module=>module.module_key===moduleKey?{...module,...result.modules[0]}:module)};
}
export function selectEnterpriseModule(modules:EnterpriseModuleData[],activeName?:string){
 return activeName?modules.find(item=>(item.module_name||item.module_key)===activeName):modules[0];
}
export function enterpriseToolbarOptions(module:Pick<EnterpriseModuleData,'module_key'|'category'>){
 const business=module.module_key==='main_business',restricted=module.module_key==='restricted_assets';
 return {yearsAndUnit:module.category!=='notes'||business||restricted,
  currency:module.category==='indicators'||module.category==='statements'||business,
  dataKinds:module.category==='statements'||business,halfAnnualOnly:business||restricted,
  defaultScope:module.category==='indicators'||module.category==='statements'||module.category==='analysis'&&module.module_key!=='per_share'?'合并期末':'all',
  defaultKind:module.category==='statements'||business?'原始报表':'all',
  defaultYears:module.category==='statements'||module.category==='indicators'?3:module.category==='analysis'||business||restricted?5:0};
}
export function enterpriseCurrencyVariants(module?:EnterpriseModuleData){
 const variants=module?.parsed_payload?.variants;
 return Array.isArray(variants)?variants.map(object):[];
}
export function selectEnterpriseCurrencyVariant(module:EnterpriseModuleData|undefined,currency='O',rate='1'):EnterpriseModuleData|undefined{
 if(!module)return undefined;
 const variants=enterpriseCurrencyVariants(module);
 if(!variants.length)return currency==='O'&&rate==='1'?module:undefined;
 const index=variants.findIndex(variant=>{const params=object(variant.request_params);return params.displayCurrency===currency&&String(params.rateType)===rate});
 if(index<0)return undefined;
 const responses=module.raw_payload?.responses;
 if(!Array.isArray(responses)||!responses[index])return undefined;
 return {...module,request_params:{...module.request_params,...object(variants[index].request_params)},parsed_payload:object(variants[index].parsed),raw_payload:object(object(responses[index]).payload)};
}
export function enterpriseModuleGroups(modules:EnterpriseModuleData[]){
 const groups:{name:string;nested:boolean;children:EnterpriseModuleData[]}[]=[];
 for(const module of modules){
  const parent=String(module.request_params?.menu_parent||''),name=parent||module.module_name||module.module_key;
  const existing=parent?groups.find(group=>group.nested&&group.name===parent):undefined;
  if(existing)existing.children.push(module);else groups.push({name,nested:!!parent,children:[module]});
 }
 return groups;
}
export function collapseEnterpriseRows(rows:EnterpriseMatrixRow[],collapsed:Set<string>){
 let hiddenBelow:number|null=null;
 return rows.filter(row=>{
  if(hiddenBelow!==null&&row.depth>hiddenBelow)return false;
  hiddenBelow=collapsed.has(row.uiKey??row.key)?row.depth:null;
  return true;
 });
}
export function enterpriseSourceLink(value:unknown){
 if(typeof value!=='string')return null;
 const separator=value.indexOf('__');
 if(separator<0)return null;
 try{
  const url=new URL(value.slice(separator+2));
  return ['http:','https:'].includes(url.protocol)?{label:value.slice(0,separator)||'查看',href:url.href}:null;
 }catch{return null}
}
export function enterprisePeriodLabel(value:unknown):string{
 const text=String(value??''),match=text.match(/^(\d{4})-?(0331|0630|0930|1231)$/);
 if(!match)return text;
 return match[1]+'年'+({'0331':'一季报','0630':'中报','0930':'三季报','1231':'年报'}[match[2]]||match[2]);
}

function flatten(rows:unknown[],depth=0,parentPath=''):EnterpriseMatrixRow[]{
 return rows.flatMap((input,index)=>{
  const row=object(input),children=Array.isArray(row.children)?row.children:[];
  const uiKey=parentPath+'/'+index;
  const current:EnterpriseMatrixRow={
   uiKey,
   definitionUnit:String(row.definitionUnit??row.unit??''),
   key:String(row.key??row.value??`${depth}-${index}`),label:String(row.name??row.label??''),unit:row.unit==='元'&&String(row.name).includes('每股')?'元/股':String(row.unit??''),depth:depth||Number(row.depth)||Number(row.indent)||0,
   section:Boolean(row.highlight),bold:Boolean(row.bold),hasChildren:children.length>0,values:Array.isArray(row.values)?row.values:[],
   description:row.description==null?null:String(row.description),formula:row.formula==null?null:String(row.formula),
  };
  return [current,...flatten(children,depth+1,uiKey)];
 });
}

function hydrate(rows:unknown[],sourceRows:Record<string,unknown>[]):unknown[]{
 return rows.map(input=>{
  const row=object(input),key=String(row.key??row.value??''),children=Array.isArray(row.children)?row.children:[];
  return {...row,
   ...(!Array.isArray(row.values)?{values:sourceRows.map(source=>source[key]??null)}:{}),
   ...(children.length?{children:hydrate(children,sourceRows)}:{}),
  };
 });
}

export function buildEnterpriseModuleView(module:EnterpriseModuleData):EnterpriseModuleView{
 const parsed=object(module.parsed_payload),periods=strings(parsed.periods),rows=Array.isArray(parsed.rows)?parsed.rows:[];
 const metadata=object(parsed.metadata),exportHeaders=strings(metadata.headExport);
 if(metadata.unavailable===true)return {kind:'empty',confirmed:false,unavailable:true};
 if(periods.length&&rows.some(row=>!Array.isArray(row))){
  const rawData=object(object(module.raw_payload).data),sourceRows=(Array.isArray(rawData.dataList)?rawData.dataList:[]).map(object);
  const displayRows=hydrate(rows,sourceRows).map((input,index)=>{
   const row=object(input),match=exportHeaders[index+1]?.match(/[（(]([^（()]+)[）)]\s*$/);
   const black=Array.isArray(metadata.black)?metadata.black[index+1]:null;
   const formula=row.formula??(Array.isArray(metadata.formula)?metadata.formula[index+1]:null);
   const indent=Array.isArray(metadata.blankNum)?metadata.blankNum[index+1]:row.indent??row.level;
   const businessUnit=module.module_key==='main_business'&&!row.unit
    ?(/[（(]%[）)]$/.test(String(row.name))?'%':/^(120050|120062|900144|incomePrefix_|costPrefix_)/.test(String(row.key))?({'0':'元','3':'千元','4':'万元','6':'百万元','8':'亿元','9':'十亿元'} as Record<string,string>)[String(module.request_params?.unitCode)]:'') : '';
   return {...row,formula,definitionUnit:row.unit,...(businessUnit?{unit:businessUnit}:{}),...(match?{unit:match[1]}:{}),highlight:row.highlight||(row.level!==undefined&&Number(row.level)===0&&black===1),bold:row.bold||black===1,depth:Number(indent)||0};
  });
  const flat=flatten(displayRows);
  return {kind:'matrix',periods,rows:flat.map((row,index)=>({...row,hasChildren:row.hasChildren||(!row.section&&(flat[index+1]?.depth??0)>row.depth)}))};
 }
 const heads=Array.isArray(parsed.head)?parsed.head:[];
 if(heads.length&&Array.isArray(heads[0])){
  const reports=strings(metadata.report);
  return {kind:'records',tables:heads.map((head,index)=>{
   const labels=strings(head),columns=rowArray(rows[index]);
   return {title:enterprisePeriodLabel(reports[index]||String(index+1)),
    headers:[labels[0],...columns.map(column=>String(column[0]??''))],
    rows:labels.slice(1).map((label,i)=>[label,...columns.map(column=>column[i+1])]),
   };
  })};
 }
 if(heads.length&&rows.length){
  const cells=rowArray(rows);
  if(module.category==='notes'&&cells.every(row=>/^\d{8}$/.test(String(row[0])))){
   return {kind:'matrix',periods:cells.map(row=>enterprisePeriodLabel(row[0])),rows:strings(heads).slice(1).map((label,i)=>({
    key:'note-'+i,label,unit:'',depth:0,section:false,bold:label==='合计',values:cells.map(row=>row[i+1]),
   }))};
  }
  return {kind:'records',tables:[{title:module.module_name||module.module_key,headers:strings(heads),rows:rowArray(rows)}]};
 }
 return {kind:'empty',confirmed:Boolean(metadata.empty)};
}

export function enterpriseColumnKind(value:unknown){
 if(['原始报表','同比','占收入比'].includes(String(value)))return {scope:'',kind:String(value)};
 const text=String(value??''),scope=text.match(/^(合并|母公司)期[初末]/)?.[0]||text;
 const suffix=text.slice(scope.length);
 const kinds:Record<string,string>={'较年初比(%)':'较年初增长率','同比(%)':'同比增长率','销售比(%)':'销售百分比','资产比(%)':'资产百分比','环比(%)':'环比增长率'};
 return {scope,kind:suffix?(kinds[suffix]||suffix):'原始报表'};
}
export type EnterpriseFilter={report:string;start:string;end:string;descending:boolean;hideEmpty:boolean;scopes?:string;dataKinds?:string;currency?:string;rate?:string;windowYears?:number};
export function enterpriseExportUrl(projectId:string,moduleKey:string,filter:EnterpriseFilter,unit:string,decimals:number,expectedHash=''){
 const params=new URLSearchParams({module_key:moduleKey,export_format:'xlsx',report:filter.report,start:filter.start,end:filter.end,descending:String(filter.descending),hide_empty:String(filter.hideEmpty),unit,decimals:String(decimals),expected_hash:expectedHash});
 if(filter.scopes!==undefined)params.set('scopes',filter.scopes||'none');
 if(filter.dataKinds!==undefined)params.set('data_kinds',filter.dataKinds||'none');
 if(filter.currency)params.set('currency',filter.currency);
 if(filter.rate)params.set('rate',filter.rate);
 if(filter.windowYears)params.set('window_years',String(filter.windowYears));
 return '/api/projects/'+encodeURIComponent(projectId)+'/enterprise/data?'+params;
}
function periodKind(period:string){
 if(/年报|1231|12-31/.test(period))return 'annual';
 if(/中报|半年|0630|06-30/.test(period))return 'half';
 if(/三季报|0930|09-30/.test(period))return 'q3';
 if(/一季报|0331|03-31/.test(period))return 'q1';
 return '';
}
function periodOrder(period:string){const ranks:Record<string,number>={annual:4,half:2,q3:3,q1:1};return Number(period.slice(0,4))*10+(ranks[periodKind(period)]??0)}
function periodQuarter(period:string){const order=periodOrder(period);return Math.floor(order/10)*4+order%10}
export const enterpriseIsBlank=(value:unknown)=>value==null||['','-','—','--'].includes(String(value).trim());
export function filterEnterpriseMatrix(view:Extract<EnterpriseModuleView,{kind:'matrix'}>,filter:EnterpriseFilter){
 const reports=filter.report.split(','),latest=Math.max(...view.periods.map(periodOrder));
 const latestQuarter=Math.max(...view.periods.map(periodQuarter));
 const types=view.rows.find(row=>row.key==='dataType'||row.key==='reportRange')?.values||[];
 const indices=view.periods.map((period,index)=>({period,index})).filter(({period,index})=>{
  const {scope,kind}=enterpriseColumnKind(types[index]);
  if(filter.windowYears&&periodQuarter(period)<=latestQuarter-filter.windowYears*4)return false;
  if(filter.scopes!==undefined&&filter.scopes!=='all'&&(!filter.scopes||!filter.scopes.split(',').includes(scope)))return false;
  if(filter.dataKinds!==undefined&&filter.dataKinds!=='all'&&(!filter.dataKinds||!filter.dataKinds.split(',').includes(kind)))return false;
  const year=period.match(/^\d{4}/)?.[0]||'';
  return (!filter.start||year>=filter.start)&&(!filter.end||year<=filter.end)&&
   (reports.includes('all')||reports.includes(periodKind(period))||reports.includes('latest')&&periodOrder(period)===latest||reports.includes('quarter')&&['q1','q3'].includes(periodKind(period)));
 });
 indices.sort((a,b)=>(periodOrder(b.period)-periodOrder(a.period))*(filter.descending?1:-1));
 const rows=view.rows.map(row=>({...row,values:indices.map(({index})=>row.values[index])}));
 return {...view,periods:indices.map(({period})=>period),rows:rows.filter(row=>!filter.hideEmpty||row.section||row.values.some(value=>!enterpriseIsBlank(value)))};
}

export function enterpriseDisplayValue(value:unknown,sourceUnit:string,targetUnit:string,decimals:number){
 if(value===null||value===undefined||value==='')return '';
 const source=String(value),scientific=source.match(/^(-?)(\d+)(?:\.(\d+))?[eE]([+-]?\d{1,3})$/);
 const raw=scientific?(()=>{
  const digits=scientific[2]+(scientific[3]||''),point=scientific[2].length+Number(scientific[4]);
  return scientific[1]+(point<=0?'0.'+'0'.repeat(-point)+digits:point>=digits.length?digits+'0'.repeat(point-digits.length):digits.slice(0,point)+'.'+digits.slice(point));
 })():source;
 if(!/^-?\d+(\.\d+)?$/.test(raw))return raw;
 if(!(sourceUnit in unitPowers)&&!['%','倍','天','元/股'].includes(sourceUnit))return raw;
 const power=sourceUnit in unitPowers?unitPowers[sourceUnit]:0;
 const negative=raw.startsWith('-'),[whole,fraction='']=raw.replace(/^-/,'').split('.');
 const digits=(whole+fraction).padEnd(whole.length+power,'0');
 const position=whole.length+power;
 const base=(negative?'-':'')+digits.slice(0,position)+(position<digits.length?'.'+digits.slice(position):'');
 return formatAmount(base,sourceUnit in unitPowers?targetUnit:'元',decimals);
}

export function enterpriseCellUnit(rows:EnterpriseMatrixRow[],row:EnterpriseMatrixRow,column:number){
 const type=rows.find(item=>item.key==='dataType')?.values[column];
 return row.unit in unitPowers&&(/[%％]/.test(String(type??''))||['同比','占收入比'].includes(String(type)))?'%':row.unit;
}

export function enterpriseIndicatorTrend(view:Extract<EnterpriseModuleView,{kind:'matrix'}>,key:string,filter:Pick<EnterpriseFilter,'report'|'start'|'end'|'scopes'|'windowYears'>){
 if(!/^\d+(?:_\d+)?$/.test(key)||!view.rows.some(row=>row.key===key)||!['annual','half','q1','q3'].includes(filter.report)||!['合并期末','母公司期末'].includes(filter.scopes||''))return null;
 const selected=filterEnterpriseMatrix(view,{...filter,descending:true,hideEmpty:false,dataKinds:'原始报表'});
 return {periods:selected.periods,rows:selected.rows.filter(row=>row.key===key||row.key===key+'_2'),currencies:selected.rows.find(row=>row.key==='displayCurrency')?.values||[]};
}

export function enterpriseStatementTrend(view:Extract<EnterpriseModuleView,{kind:'matrix'}>,key:string,statementType:string,filter:Pick<EnterpriseFilter,'report'|'start'|'end'|'scopes'|'windowYears'>){
 if(!/^\d+$/.test(key)||!['annual','half','q1','q3'].includes(filter.report)||!['合并期末','母公司期末'].includes(filter.scopes||''))return null;
 const matches=view.rows.filter(item=>item.key===key);
 if(matches.length!==1||matches[0].section)return null;
 const row=matches[0];
 const suffixes=statementType==='balance_sheet'?[['较年初比(%)','', '%'],['同比(%)','同比增长率','%'],['销售比(%)','销售百分比','%'],['资产比(%)','资产百分比','%'],['环比(%)','环比增长率','%']]:
  statementType==='income_statement'?[['','',row.unit],['同比(%)','同比增长率','%'],['销售比(%)','销售百分比','%']]:
  statementType==='cash_flow_statement'?[['','',row.unit],['同比(%)','同比增长率','%']]:null;
 if(!suffixes)return null;
 const selected=filterEnterpriseMatrix(view,{...filter,descending:true,hideEmpty:false,scopes:'all',dataKinds:'all'});
 const periods=[...new Set(selected.periods)],types=selected.rows.find(item=>item.key==='dataType')?.values||[];
 const values=selected.rows.find(item=>item.key===key)?.values||[];
 const currencies=selected.rows.find(item=>item.key==='displayCurrency')?.values||[];
 const positions=suffixes.map(([suffix])=>periods.map(period=>selected.periods.findIndex((candidate,index)=>candidate===period&&String(types[index])===(filter.scopes||'')+suffix)));
 return {periods,row,series:suffixes.map(([suffix,label,unit],seriesIndex)=>({key:key+suffix,label:label||row.label,unit,
  values:positions[seriesIndex].map(index=>index<0?null:values[index])})),
  currencies:positions[0].map(index=>index<0?'':currencies[index]??'')};
}

export function enterpriseTrendAxis(input:(number|null)[],unit:string,currency:string,includeZero:boolean){
 const finite=input.map(value=>value!==null&&Number.isFinite(value)?value:null);
 const monetary=unit in unitPowers,basePower=monetary?unitPowers[unit]:0;
 const largest=Math.max(0,...finite.map(value=>Math.abs(value??0)))*10**basePower;
 const power=monetary?([12,9,6,3,0].find(value=>largest>=10**value)??0):0;
 const values=finite.map(value=>value===null?null:value*10**(basePower-power));
 const present=values.filter((value):value is number=>value!==null);
 if(includeZero||!present.length)present.push(0);
 const min=Math.floor(Math.min(...present)),maxValue=Math.ceil(Math.max(...present)),max=maxValue===min?min+1:maxValue;
 const magnitude:Record<number,string>={0:'元',3:'千',6:'百万',9:'十亿',12:'万亿'};
 return {values,min,max,interval:(max-min)/5,name:monetary?magnitude[power]+(currency?'·'+currency:''):unit};
}
