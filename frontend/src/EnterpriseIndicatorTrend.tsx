import React,{useEffect,useId,useRef,useState} from 'react';
import type {EnterpriseModuleData} from './api';
import {enterpriseDisplayValue,enterpriseExportUrl,enterpriseIndicatorTrend,enterpriseTrendAxis} from './enterprise-financial-view';
import type {EnterpriseFilter,EnterpriseModuleView} from './enterprise-financial-view';
import {unitPowers} from './financial-view';

type Props={view:Extract<EnterpriseModuleView,{kind:'matrix'}>;rowKey:string;module:EnterpriseModuleData;projectId:string;filter:Pick<EnterpriseFilter,'start'|'end'|'windowYears'|'currency'|'rate'>;onClose:()=>void};
export default function EnterpriseIndicatorTrend({view,rowKey,module,projectId,filter,onClose}:Props){
 const [report,setReport]=useState('annual'),[scope,setScope]=useState('合并期末'),[error,setError]=useState(''),[exporting,setExporting]=useState(false);
 const [showAmount,setShowAmount]=useState(true),[showYoy,setShowYoy]=useState(true);
 const dialog=useRef<HTMLDialogElement>(null),id=useId();
 useEffect(()=>{dialog.current?.showModal()},[]);
 const data=enterpriseIndicatorTrend(view,rowKey,{...filter,report,scopes:scope});
 if(!data)return null;
 const row=data.rows[0],yoy=data.rows.find(item=>item.key===rowKey+'_2');
 const unit=row.unit in unitPowers?'亿元':row.unit;
 const currencies=[...new Set(data.currencies.map(String).filter(Boolean))];
 const currency=currencies.length===1?currencies[0]:'';
 const label=row.label+(unit?'('+unit+(row.unit in unitPowers?currency:'')+')':'');
 const show=(value:unknown,sourceUnit=row.unit)=>enterpriseDisplayValue(value,sourceUnit,unit,2)||'-';
 const chronological=data.periods.map((period,index)=>({period,index})).reverse();
 const number=(value:unknown,power=0)=>value!==null&&value!==undefined&&/^-?\d+(\.\d+)?$/.test(String(value))?Number(value)*10**power:null;
 const left=enterpriseTrendAxis(chronological.map(({index})=>number(row.values[index],row.unit in unitPowers?unitPowers[row.unit]-unitPowers[unit]:0)),unit,currency,true);
 const right=enterpriseTrendAxis(chronological.map(({index})=>number(yoy?.values[index])),'%','',false);
 const amounts=left.values,rates=right.values,{min,max}=left,lo=right.min,hi=right.max;
 const y=(value:number)=>220-(value-min)/(max-min||1)*155,yr=(value:number)=>220-(value-lo)/(hi-lo||1)*155;
 const x=(i:number)=>75+(i+.5)*680/Math.max(1,chronological.length);
 async function download(){
  setExporting(true);setError('');
  try{
   const path=enterpriseExportUrl(projectId,module.module_key,{...filter,report,scopes:scope,descending:true,hideEmpty:false,dataKinds:'原始报表'},row.unit in unitPowers?'亿元':'万元',2,module.response_sha256)+'&trend_key='+encodeURIComponent(rowKey);
   const response=await fetch(path,{credentials:'same-origin'});
   if(!response.ok)throw new Error(response.status===409?'来源批次已变化，请刷新后重试。':'趋势图 Excel 导出失败，请重试。');
   if(!response.headers.get('content-type')?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))throw new Error('返回内容不是 Excel 文件。');
   const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=row.label+'趋势图.xlsx';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){setError(e instanceof Error?e.message:'趋势图 Excel 导出失败。')}finally{setExporting(false)}
 }
 return <dialog ref={dialog} className="enterprise-trend" aria-labelledby={id} onCancel={onClose}>
  <header><h3 id={id}>{row.label}——指标趋势图</h3><button aria-label="关闭趋势图" onClick={onClose}>×</button></header>
  <div className="enterprise-trend-controls"><label>报告期<select aria-label="趋势报告期" value={report} onChange={e=>setReport(e.target.value)}>{[['annual','年报'],['half','中报'],['q1','一季报'],['q3','三季报']].map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
   <label>报表类型<select aria-label="趋势报表类型" value={scope} onChange={e=>setScope(e.target.value)}><option>合并期末</option><option>母公司期末</option></select></label>
   <button className="reference-export" disabled={exporting} onClick={download}>{exporting?'正在导出…':'导出Excel'}</button></div>
  {error&&<p role="alert">{error}</p>}
  {currencies.length>1?<p>所选期间披露币种不同，保留明细，不混合绘图。</p>:<><svg className="enterprise-trend-chart" viewBox="0 0 840 252" role="img" aria-label={row.label+'历史趋势'}>
   <text x="420" y="24" textAnchor="middle" className="trend-title">{row.label}历史趋势</text><text x="75" y="48">{left.name}</text>{yoy&&<text x="765" y="48">%</text>}
   {[0,.2,.4,.6,.8,1].map(t=><g key={t}><line x1="75" x2="755" y1={220-155*t} y2={220-155*t} stroke="#efefef" strokeDasharray="4 3"/><text x="65" y={224-155*t} textAnchor="end">{(min+(max-min)*t).toLocaleString('zh-CN',{maximumFractionDigits:2})}</text>{yoy&&<text x="765" y={224-155*t}>{(lo+(hi-lo)*t).toLocaleString('zh-CN',{maximumFractionDigits:2})}</text>}</g>)}
   {chronological.map(({period,index},i)=><g key={period+index}><text x={x(i)} y="239" textAnchor="middle">{period.slice(0,4)}</text>{showAmount&&amounts[i]!==null&&<rect data-series="primary" x={x(i)-7} width="14" y={Math.min(y(amounts[i]!),y(0))} height={Math.max(1,Math.abs(y(amounts[i]!)-y(0)))} fill="#3986fe"><title>{period} {label}：{show(row.values[index])}</title></rect>}
    {showYoy&&rates[i]!==null&&<>{i>0&&rates[i-1]!==null&&<line x1={x(i-1)} y1={yr(rates[i-1]!)} x2={x(i)} y2={yr(rates[i]!)} stroke="#EDB965" strokeWidth="2"/>}<circle cx={x(i)} cy={yr(rates[i]!)} r="2.5" fill="white" stroke="#EDB965"><title>{period} 同比：{show(yoy?.values[index],'%')}%</title></circle></>}
   </g>)}
  </svg><div className="enterprise-trend-legend"><button aria-pressed={showAmount} onClick={()=>setShowAmount(!showAmount)}><i/>{label}(左)</button>{yoy&&<button aria-pressed={showYoy} onClick={()=>setShowYoy(!showYoy)}><i className="trend-line-dot"/>同比(%)(右)</button>}</div></>}
  <div className="enterprise-trend-table"><table className="finance-matrix"><thead><tr><th>序号</th><th>报告期</th><th>{label}</th>{yoy&&<th>同比(%)</th>}{currencies.length>1&&<th>币种</th>}</tr></thead><tbody>{data.periods.map((period,index)=><tr key={period+index}><td>{index+1}</td><td>{period}</td><td className={String(row.values[index]).startsWith('-')?'reference-negative':''}>{show(row.values[index])}</td>{yoy&&<td className={String(yoy.values[index]).startsWith('-')?'reference-negative':''}>{show(yoy.values[index],'%')}</td>}{currencies.length>1&&<td>{String(data.currencies[index]??'')}</td>}</tr>)}</tbody></table>{!data.periods.length&&<p>当前口径无已导入期间。</p>}</div>
 </dialog>;
}
