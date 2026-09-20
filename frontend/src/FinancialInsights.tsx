import React,{useEffect,useRef,useState} from 'react';
import {api,friendly} from './api';
import type {FinancialStatement} from './api';
import {formatAmount,scopeLabels,toCsv,unitPowers} from './financial-view';
import {mainRows} from './reference-finance';
import referenceAnalysis from './reference-analysis.json';
import type {ReferenceRow} from './reference-finance';

type Input={item_id:string;document_id:string;label:string;period:string;value:string|null;unit:string;status:string;start_line:number;end_line:number};
type Measure={code:string;label:string;category:string;unit:string;formula:string;formula_version:string;value:string|null;reason:string|null;inputs:Input[];status:string};
type Period={key:string;period:string;kind:string;end:string;metrics:Measure[]};
type Group={id:string;entity:string;scope:string;currency:string;periods:Period[]};
type Analytics={formula_version:string;input_hash:string;groups:Group[]};
const kindLabel:Record<string,string>={instant:'期末',year:'年报',annual:'年报',half_year:'中报',quarter:'季报',year_to_date:'三季报'};
const label=(p:Period)=>p.end.slice(0,4)+'年'+(kindLabel[p.kind]||'报告');
export default function FinancialInsights({pid,statements,mode,category,onEvidence,children}:{pid:string;statements:FinancialStatement[];mode:'metrics'|'analysis';category:string;onEvidence:(ids:string[],title:string)=>void;children:React.ReactNode}){
 const [data,setData]=useState<Analytics|null>(null),[error,setError]=useState('');
 const [groupId,setGroup]=useState(''),[unit,setUnit]=useState('万元'),[kind,setKind]=useState('latest_annual');
 const [start,setStart]=useState(''),[end,setEnd]=useState(''),[descending,setDescending]=useState(true),[hide,setHide]=useState(false);
 const [selected,setSelected]=useState<{metric:Measure;period:Period}|null>(null);
 useEffect(()=>{let active=true;setData(null);setError('');api<Analytics>('/projects/'+pid+'/financial-analytics').then(x=>{if(active)setData(x)}).catch(e=>{if(active)setError(friendly(e.message))});return()=>{active=false}},[pid,statements]);
 useEffect(()=>setSelected(null),[data,groupId,category,kind,mode]);
 const group=data?.groups.find(g=>g.id===groupId)||data?.groups[0];
 const latest=group?.periods[0]?.end;
 const years=[...new Set(group?.periods.map(p=>p.end.slice(0,4)))].sort().reverse();
 const periods=(group?.periods.filter(p=>(kind==='all'||kind==='latest_annual'&&(p.end===latest||['year','annual'].includes(p.kind))||p.kind===kind)&&(!start||p.end.slice(0,4)>=start)&&(!end||p.end.slice(0,4)<=end))||[]).sort((a,b)=>(a.end.localeCompare(b.end)||a.key.localeCompare(b.key))*(descending?-1:1));
 const resolve=(row:ReferenceRow,p:Period)=>p.metrics.find(m=>m.code===row.key)||p.metrics.find(m=>!!row.match&&m.label===row.match&&(mode==='metrics'||m.category===category));
 const analysisRows:ReferenceRow[]=(referenceAnalysis as Record<string,ReferenceRow[]>)[category]||[];
 const rows=(mode==='metrics'?mainRows:analysisRows).filter(r=>!hide||periods.some(p=>resolve(r,p)?.value!=null));
 const display=(m?:Measure)=>m?formatAmount(m.value,m.unit==='元'?unit:'元',m.unit==='元/股'?4:2):'—';
 function select(row:ReferenceRow,p:Period){const m=resolve(row,p);setSelected({metric:m||{code:row.key,label:row.label,category:row.section,unit:'',formula:'',formula_version:data?.formula_version||'',value:null,reason:'当前报告缺少可核实的数据',inputs:[],status:'unavailable'},period:p})}
 function exportCsv(){const matrix=[['项目名称',...periods.map(label)],['报表类型',...periods.map(()=>scopeLabels[group?.scope||'']||'')],['单位',unit],...rows.map(r=>[r.label,...periods.map(p=>display(resolve(r,p)))])];const url=URL.createObjectURL(new Blob([toCsv(matrix)],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=(mode==='metrics'?'主要财务指标':category)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 return <>
  <div className="finance-heading"><h2>{mode==='metrics'?'主要财务指标':category}</h2><button className="button secondary" disabled={!rows.length} onClick={exportCsv}>导出 CSV</button></div>
  {error?<p role="alert">{error}</p>:!data?<p role="status">加载中…</p>:!group?<div className="finance-empty">暂无财务数据</div>:<>
   <div className="finance-filters reference-filters"><label>报告期<select aria-label="指标报告期类型" value={kind} onChange={e=>setKind(e.target.value)}><option value="latest_annual">最新、年报</option><option value="all">全部</option><option value="year">年报</option><option value="half_year">中报</option><option value="quarter">季报</option></select></label><label>年度<div className="finance-presets">{[3,5,10].map(n=><button key={n} onClick={()=>{setStart(String(Number(years[0])-n+1));setEnd(years[0])}}>{n}Y</button>)}</div></label><label>起始<select aria-label="指标起始年度" value={start} onChange={e=>setStart(e.target.value)}><option value="">不限</option>{years.map(y=><option key={y}>{y}</option>)}</select></label><label>结束<select aria-label="指标结束年度" value={end} onChange={e=>setEnd(e.target.value)}><option value="">不限</option>{years.map(y=><option key={y}>{y}</option>)}</select></label><label>报表类型<select aria-label="指标主体口径" value={group.id} onChange={e=>setGroup(e.target.value)}>{data.groups.map(g=><option key={g.id} value={g.id}>{g.scope==='consolidated'?'合并期末':scopeLabels[g.scope]||g.scope}{data.groups.some(x=>x.entity!==g.entity)?' · '+g.entity:''}{g.currency!=='CNY'?' · '+g.currency:''}</option>)}</select></label><label>单位<select aria-label="指标金额单位" value={unit} onChange={e=>setUnit(e.target.value)}>{Object.keys(unitPowers).map(u=><option key={u}>{u}</option>)}</select></label><label><input type="checkbox" checked={descending} onChange={e=>setDescending(e.target.checked)}/>报告期倒序</label><label><input type="checkbox" checked={hide} onChange={e=>setHide(e.target.checked)}/>隐藏空行</label></div>
   <div className="finance-table-scroll" tabIndex={0} aria-label="财务指标对比表"><table className="finance-matrix reference-matrix"><thead><tr><th>{mode==='metrics'?'报告期':'指标名称'}</th>{periods.map(p=><th key={p.key}>{label(p)}</th>)}</tr></thead><tbody><tr className="finance-scope-row"><th>报表类型</th>{periods.map(p=><td key={p.key}>{group.scope==='consolidated'?'合并期末':scopeLabels[group.scope]}</td>)}</tr>{mode==='metrics'&&<tr className="finance-scope-row"><th>截止日期</th>{periods.map(p=><td key={p.key}>{p.end}</td>)}</tr>}{rows.map((r,i)=><React.Fragment key={r.key}>{(i===0||rows[i-1].section!==r.section)&&<tr className="finance-section"><th>{r.section}</th>{periods.map(p=><td key={p.key}/>)}</tr>}<tr><th>{r.label}</th>{periods.map(p=><td key={p.key}><button className="finance-number" aria-label={r.label+' '+label(p)+' '+display(resolve(r,p))} onClick={()=>select(r,p)}>{display(resolve(r,p))}</button></td>)}</tr></React.Fragment>)}{!rows.length&&<tr><td colSpan={periods.length+1}>暂无数据</td></tr>}</tbody></table></div>
  </>}
  {selected&&<Calculation selected={selected} display={display} onEvidence={onEvidence} close={()=>setSelected(null)}/>}
  {mode==='metrics'&&<details className="finance-legacy"><summary>更多操作</summary>{children}</details>}
 </>
}
function Calculation({selected,display,onEvidence,close}:{selected:{metric:Measure;period:Period};display:(m:Measure)=>string;onEvidence:(ids:string[],title:string)=>void;close:()=>void}){
 const ref=useRef<HTMLDialogElement>(null);useEffect(()=>{ref.current?.showModal()},[]);const m=selected.metric;
 return <dialog ref={ref} className="finance-evidence" onCancel={close} onClose={close} aria-label="指标计算依据"><div className="finance-heading"><h3>{m.label} · {label(selected.period)}</h3><button className="button secondary" onClick={close}>关闭</button></div><div className="finance-evidence-body"><strong>{display(m)} {m.unit}</strong><p>{m.formula}</p>{m.reason&&<p>{m.reason}</p>}<p className="finance-note">{m.formula_version} · {m.status==='confirmed_inputs'?'输入已核对':'待复核'}</p>{m.inputs.map((input,i)=><p key={input.item_id+i}><button className="button secondary" onClick={()=>onEvidence([input.item_id],input.label+' · '+input.period)}>{input.label}：{input.value} {input.unit} · {input.period}</button></p>)}</div></dialog>
}
