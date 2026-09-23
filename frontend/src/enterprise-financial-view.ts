import type {EnterpriseModuleData} from './api';

export type EnterpriseMatrixRow={key:string;label:string;unit:string;depth:number;section:boolean;values:unknown[];description?:string|null;formula?:string|null};
export type EnterpriseRecordTable={title:string;headers:string[];rows:unknown[][]};
export type EnterpriseModuleView=
 | {kind:'matrix';periods:string[];rows:EnterpriseMatrixRow[]}
 | {kind:'records';tables:EnterpriseRecordTable[]}
 | {kind:'empty';confirmed:boolean};

const object=(value:unknown):Record<string,unknown>=>value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
const strings=(value:unknown):string[]=>Array.isArray(value)?value.map(item=>item==null?'':String(item)):[];
const rowArray=(value:unknown):unknown[][]=>Array.isArray(value)?value.filter(Array.isArray) as unknown[][]:[];

function flatten(rows:unknown[],depth=0):EnterpriseMatrixRow[]{
 return rows.flatMap((input,index)=>{
  const row=object(input),children=Array.isArray(row.children)?row.children:[];
  const current:EnterpriseMatrixRow={
   key:String(row.key??row.value??`${depth}-${index}`),label:String(row.name??row.label??''),unit:String(row.unit??''),depth,
   section:Boolean(row.highlight||row.bold||children.length),values:Array.isArray(row.values)?row.values:[],
   description:row.description==null?null:String(row.description),formula:row.formula==null?null:String(row.formula),
  };
  return [current,...flatten(children,depth+1)];
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
 if(periods.length&&rows.some(row=>!Array.isArray(row))){
  const rawData=object(object(module.raw_payload).data),sourceRows=(Array.isArray(rawData.dataList)?rawData.dataList:[]).map(object);
  const displayRows=hydrate(rows,sourceRows).map((input,index)=>{
   const row=object(input),match=exportHeaders[index+1]?.match(/[（(]([^（()]+)[）)]\s*$/);
   return match?{...row,unit:match[1]}:row;
  });
  return {kind:'matrix',periods,rows:flatten(displayRows)};
 }
 const heads=Array.isArray(parsed.head)?parsed.head:[];
 if(heads.length&&Array.isArray(heads[0])){
  const reports=strings(metadata.report);
  return {kind:'records',tables:heads.map((head,index)=>({
   title:reports[index]||String(index+1),headers:strings(head),rows:rowArray(rows[index]),
  }))};
 }
 if(heads.length&&rows.length){
  return {kind:'records',tables:[{title:module.module_name||module.module_key,headers:strings(heads),rows:rowArray(rows)}]};
 }
 return {kind:'empty',confirmed:Boolean(metadata.empty)};
}
