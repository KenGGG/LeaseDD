import React,{useEffect,useId,useRef,useState} from 'react';
import type {EnterpriseModuleData} from './api';
import {enterpriseDisplayValue,enterpriseExportUrl,enterpriseStatementTrend,enterpriseTrendAxis} from './enterprise-financial-view';
import type {EnterpriseFilter,EnterpriseModuleView} from './enterprise-financial-view';
import {unitPowers} from './financial-view';

type Props={view:Extract<EnterpriseModuleView,{kind:'matrix'}>;rowKey:string;module:EnterpriseModuleData;projectId:string;
 filter:Pick<EnterpriseFilter,'start'|'end'|'windowYears'|'currency'|'rate'>;displayUnit:string;onClose:()=>void};

export default function EnterpriseStatementTrend({view,rowKey,module,projectId,filter,displayUnit,onClose}:Props){
 const [report,setReport]=useState('annual'),[scope,setScope]=useState('合并期末');
 const [error,setError]=useState(''),[exporting,setExporting]=useState(false);
 const [hidden,setHidden]=useState<Set<number>>(new Set());
 const dialog=useRef<HTMLDialogElement>(null),id=useId();
 useEffect(()=>{dialog.current?.showModal()},[]);
 const data=enterpriseStatementTrend(view,rowKey,module.module_key,{...filter,report,scopes:scope});
 if(!data)return null;
 const primary=data.series[0],monetary=primary.unit in unitPowers;
 const currencies=[...new Set(data.currencies.map(String).filter(Boolean))],currency=currencies.length===1?currencies[0]:'';
 const unit=monetary?displayUnit:primary.unit;
 const primaryLabel=primary.label+'('+unit+(monetary?currency:'')+')';
 const labels=data.series.map((series,index)=>index===0?primaryLabel:series.label+'(%)');
 const show=(value:unknown,sourceUnit:string)=>enterpriseDisplayValue(value,sourceUnit,monetary&&sourceUnit in unitPowers?unit:'万元',2)||'-';
 const chronological=data.periods.map((period,index)=>({period,index})).reverse();
 const number=(value:unknown,scale=0)=>value!==null&&value!==undefined&&/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3})?$/.test(String(value))?Number(value)*10**scale:null;
 const left=enterpriseTrendAxis(chronological.map(({index})=>number(primary.values[index],monetary?unitPowers[primary.unit]-unitPowers[unit]:0)),unit,currency,true);
 const secondary=data.series.slice(1).flatMap(series=>chronological.map(({index})=>number(series.values[index])));
 const right=enterpriseTrendAxis(secondary,'%','',false);
 const y=(value:number,min:number,max:number)=>215-(value-min)/(max-min||1)*150;
 const x=(index:number)=>70+(index+.5)*680/Math.max(1,chronological.length);
 const colors=['#3986fe','#12b9be','#ff7043','#42a5f5','#b0c4ef'];
 async function download(){
  setExporting(true);setError('');
  try{
   const path=enterpriseExportUrl(projectId,module.module_key,{...filter,report,scopes:scope,descending:true,hideEmpty:false,dataKinds:'all'},monetary?unit:'万元',2,module.response_sha256)+'&trend_key='+encodeURIComponent(rowKey);
   const response=await fetch(path,{credentials:'same-origin'});
   if(!response.ok)throw new Error(response.status===409?'来源批次已变化，请刷新后重试。':'趋势图 Excel 导出失败，请重试。');
   if(!response.headers.get('content-type')?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))throw new Error('返回内容不是 Excel 文件。');
   const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=primary.label+'趋势图.xlsx';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){setError(e instanceof Error?e.message:'趋势图 Excel 导出失败。')}finally{setExporting(false)}
 }
 return <dialog ref={dialog} className="enterprise-trend" aria-labelledby={id} onCancel={onClose}>
  <header><h3 id={id}>{data.row.label}——指标趋势图</h3><button aria-label="关闭趋势图" onClick={onClose}>×</button></header>
  <div className="enterprise-trend-controls"><label>报告期<select aria-label="趋势报告期" value={report} onChange={event=>setReport(event.target.value)}>{[['annual','年报'],['half','中报'],['q1','一季报'],['q3','三季报']].map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
   <label>报表类型<select aria-label="趋势报表类型" value={scope} onChange={event=>setScope(event.target.value)}><option>合并期末</option><option>母公司期末</option></select></label>
   <button className="reference-export" disabled={exporting} onClick={download}>{exporting?'正在导出…':'导出Excel'}</button></div>
  {error&&<p role="alert">{error}</p>}
  {currencies.length>1?<p>所选期间披露币种不同，保留明细，不混合绘图。</p>:<svg className="enterprise-trend-chart" viewBox="0 0 840 252" role="img" aria-label={data.row.label+'历史趋势'}>
   <text x="420" y="24" textAnchor="middle" className="trend-title">{data.row.label}历史趋势</text><text x="70" y="48">{left.name}</text>{data.series.length>1&&<text x="765" y="48">%</text>}
   {[0,.2,.4,.6,.8,1].map(t=><g key={t}><line x1="70" x2="750" y1={215-150*t} y2={215-150*t} stroke="#efefef" strokeDasharray="4 3"/><text x="60" y={219-150*t} textAnchor="end">{(left.min+(left.max-left.min)*t).toFixed(2)}</text><text x="760" y={219-150*t}>{(right.min+(right.max-right.min)*t).toFixed(2)}</text></g>)}
   {chronological.map(({period,index},position)=><g key={period+index}><text x={x(position)} y="239" textAnchor="middle">{period.slice(0,4)}</text>{!hidden.has(0)&&left.values[position]!==null&&<rect x={x(position)-7} width="14" y={Math.min(y(left.values[position]!,left.min,left.max),y(0,left.min,left.max))} height={Math.max(1,Math.abs(y(left.values[position]!,left.min,left.max)-y(0,left.min,left.max)))} fill={colors[0]}><title>{period} {primaryLabel}：{show(primary.values[index],primary.unit)}</title></rect>}
    {data.series.slice(1).map((series,seriesIndex)=>{const value=number(series.values[index]);if(hidden.has(seriesIndex+1)||value===null)return null;const previous=position>0?number(series.values[chronological[position-1].index]):null;return <g key={series.key}>{previous!==null&&<line x1={x(position-1)} y1={y(previous,right.min,right.max)} x2={x(position)} y2={y(value,right.min,right.max)} stroke={colors[(seriesIndex+1)%colors.length]} strokeWidth="2"/>}<circle cx={x(position)} cy={y(value,right.min,right.max)} r="3" fill="white" stroke={colors[(seriesIndex+1)%colors.length]}><title>{period} {series.label}：{show(series.values[index],series.unit)}%</title></circle></g>})}
   </g>)}
  </svg>}
  <div className="enterprise-trend-legend">{labels.map((label,index)=><button key={label+index} aria-pressed={!hidden.has(index)} onClick={()=>setHidden(previous=>{const next=new Set(previous);next.has(index)?next.delete(index):next.add(index);return next})}><i style={{background:colors[index%colors.length]}}/>{label}{index===0?'(左)':'(右)'}</button>)}</div>
  <div className="enterprise-trend-table"><table className="finance-matrix"><thead><tr><th>序号</th><th>报告期</th>{labels.map((label,index)=><th key={label+index}>{label}</th>)}{currencies.length>1&&<th>币种</th>}</tr></thead><tbody>{data.periods.map((period,index)=><tr key={period+index}><td>{index+1}</td><td>{period}</td>{data.series.map((series,seriesIndex)=><td key={series.key} className={String(series.values[index]).startsWith('-')?'reference-negative':''}>{show(series.values[index],series.unit)}</td>)}{currencies.length>1&&<td>{String(data.currencies[index]??'')}</td>}</tr>)}</tbody></table>{!data.periods.length&&<p>当前口径无已导入期间。</p>}</div>
 </dialog>;
}
