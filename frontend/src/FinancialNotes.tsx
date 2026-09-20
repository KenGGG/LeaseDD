import React,{useEffect,useRef,useState} from 'react';
import {api,friendly} from './api';
import type {Doc} from './api';
import {formatAmount,toCsv,unitPowers} from './financial-view';
import {noteParent,noteLabel} from './reference-finance';
type Note={id:string;title:string;section:string;scope:string;document_id:string;markdown_sha256:string;start_line:number;end_line:number;categories:string[];report_end:string|null};
type Cell={text:string;colspan:number;rowspan:number};
type Detail=Note&{blocks:({type:'text';text:string}|{type:'table';rows:Cell[][]})[];lines:string[]};
type Value={value:string|null;note_ids:string[];conflict:boolean};
type Matrix={layout?:'records';columns?:{label:string;unit:string}[];records?:{key:string;period:string;cells:Value[]}[];entities?:string[];entity?:string;periods:string[];rows:{key:string;label:string;section:string;unit?:string;cells:Value[]}[]};
const periodLabel=(p:string)=>p.slice(0,4)+'年'+(p.endsWith('12-31')?'年报':p.endsWith('06-30')?'中报':'季报');
export default function FinancialNotes({pid,docs,category}:{pid:string;docs:Doc[];category:string}){
 const [notes,setNotes]=useState<Note[]>([]),[matrix,setMatrix]=useState<Matrix|null>(null),[error,setError]=useState('');
 const [entity,setEntity]=useState('');
 const [doc,setDoc]=useState(''),[scope,setScope]=useState('consolidated'),[unit,setUnit]=useState('自动'),[hide,setHide]=useState(false);
 const [ids,setIds]=useState<string[]>([]),[selected,setSelected]=useState('');
 useEffect(()=>{let active=true;setMatrix(null);setError('');setIds([]);Promise.all([api<{notes:Note[]}>('/projects/'+pid+'/financial-notes'),api<Matrix>('/projects/'+pid+'/financial-notes-matrix?category='+encodeURIComponent(category)+'&scope='+scope+'&document_id='+doc+'&entity='+encodeURIComponent(entity))]).then(([n,m])=>{if(active){setNotes(n.notes);setMatrix(m)}}).catch(e=>{if(active)setError(friendly(e.message))});return()=>{active=false}},[pid,docs,category,scope,doc,entity]);
 const available=notes.filter(n=>n.categories.includes(noteParent(category))&&(!doc||n.document_id===doc));
 const periodIndexes=matrix?.periods.map((p,i)=>({p,i})).filter(({p},i)=>i===0||p.endsWith('12-31')).map(x=>x.i)||[];
 const periods=periodIndexes.map(i=>matrix!.periods[i]);
 const rows=matrix?.rows.map(r=>({...r,cells:periodIndexes.map(i=>r.cells[i])})).filter(r=>!hide||r.cells.some(c=>c.value!==null))||[];
 const records=matrix?.records?.filter(r=>periods.includes(r.period))||[];
 const display=(v:string|null,valueUnit='元')=>{
  if(v===null)return '—';if(valueUnit==='text')return v;if(valueUnit==='%')return formatAmount(v,'元',2)+'%';if(!/^-?\d+(\.\d+)?$/.test(v))return v;
  if(unit!=='自动')return formatAmount(v,unit,2);
  const abs=v.replace('-','').split('.')[0].replace(/^0+/, '');const u=abs.length>8?'亿元':abs.length>4?'万元':'元';
  return formatAmount(v,u,2)+(u==='亿元'?'亿':u==='万元'?'万':'元');
 };
 function exportCsv(){const content=matrix?.layout==='records'?[['报告期',...matrix.columns!.map(c=>c.label)],...records.map(r=>[periodLabel(r.period),...r.cells.map((c,i)=>display(c.value,matrix.columns![i].unit))])]:[['项目名称',...(periods.map(periodLabel)||[])],...rows.map(r=>[r.label,...r.cells.map(c=>display(c.value,r.unit))])];const url=URL.createObjectURL(new Blob([toCsv(content)],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=category+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 return <>
  <div className="finance-heading"><h2>{noteLabel(category)}</h2><button className="button secondary" disabled={!rows.length&&!records.length} onClick={exportCsv}>导出 CSV</button></div>
  <div className="finance-filters reference-filters">{!!matrix?.entities&&matrix.entities.length>1&&<label>主体<select aria-label="附注主体" value={matrix.entity} onChange={e=>setEntity(e.target.value)}>{matrix.entities.map(e=><option key={e}>{e}</option>)}</select></label>}<label>报告期<select aria-label="附注报告文件" value={doc} onChange={e=>setDoc(e.target.value)}><option value="">最新、年报</option>{docs.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>{category!=='审计报告'&&<><label>报表类型<select aria-label="附注范围" value={scope} onChange={e=>setScope(e.target.value)}><option value="consolidated">合并期末</option><option value="parent">母公司期末</option></select></label><label>单位<select aria-label="附注单位" value={unit} onChange={e=>setUnit(e.target.value)}><option>自动</option>{Object.keys(unitPowers).map(u=><option key={u}>{u}</option>)}</select></label></>}<label><input type="checkbox" checked={hide} onChange={e=>setHide(e.target.checked)}/>隐藏空行</label></div>
  {error?<p role="alert">{error}</p>:!matrix?<p role="status">加载中…</p>:matrix.layout==='records'&&records.length?<div className="finance-table-scroll" aria-label="财务附注明细表"><table className="finance-matrix reference-matrix"><thead><tr>{matrix.columns!.map(c=><th key={c.label}>{c.label}</th>)}</tr></thead><tbody>{records.map((r,i)=><React.Fragment key={r.key}>{(i===0||records[i-1].period!==r.period)&&<tr className="finance-section"><th colSpan={matrix.columns!.length}>{periodLabel(r.period)}</th></tr>}<tr>{r.cells.map((c,j)=>j===0?<th key={j}>{c.value}</th>:<td key={j}><button className="finance-number" disabled={!c.note_ids.length} title={c.conflict?'来源存在差异':''} onClick={()=>{setIds(c.note_ids);setSelected(c.note_ids[0])}}>{display(c.value,matrix.columns![j].unit)}</button></td>)}</tr></React.Fragment>)}</tbody></table></div>:rows.length?<div className="finance-table-scroll" aria-label="财务附注对比表"><table className="finance-matrix reference-matrix"><thead><tr><th>项目名称</th>{periods.map(p=><th key={p}>{periodLabel(p)}</th>)}</tr></thead><tbody>{rows.map((r,i)=><React.Fragment key={r.key}>{r.section&&(i===0||rows[i-1].section!==r.section)&&<tr className="finance-section"><th>{r.section}</th>{periods.map(p=><td key={p}/>)}</tr>}<tr><th>{r.label}</th>{r.cells.map((c,j)=><td key={j}><button className="finance-number" disabled={!c.note_ids.length} title={c.conflict?'来源存在差异':''} onClick={()=>{setIds(c.note_ids);setSelected(c.note_ids[0])}}>{display(c.value,r.unit)}</button></td>)}</tr></React.Fragment>)}</tbody></table></div>:<div className="finance-empty">暂无数据</div>}
  {!!available.length&&<details className="finance-legacy"><summary>查看原文</summary><div className="finance-notes-index">{available.map(n=><button key={n.id} onClick={()=>{setIds([n.id]);setSelected(n.id)}}>{n.title}<small>{docs.find(d=>d.id===n.document_id)?.name}</small></button>)}</div></details>}
  {!!ids.length&&<NoteDialog key={ids.join(',')} pid={pid} ids={ids} selected={selected} setSelected={setSelected} docs={docs} notes={notes} close={()=>setIds([])}/>}
 </>
}
function NoteDialog({pid,ids,selected,setSelected,docs,notes,close}:{pid:string;ids:string[];selected:string;setSelected:(id:string)=>void;docs:Doc[];notes:Note[];close:()=>void}){
 const ref=useRef<HTMLDialogElement>(null),[detail,setDetail]=useState<Detail|null>(null),[error,setError]=useState('');
 useEffect(()=>{ref.current?.showModal()},[]);
 useEffect(()=>{let active=true;setDetail(null);setError('');api<Detail>('/projects/'+pid+'/financial-notes/'+selected).then(x=>{if(active)setDetail(x)}).catch(e=>{if(active)setError(friendly(e.message))});return()=>{active=false}},[pid,selected]);
 return <dialog className="finance-evidence" ref={ref} onCancel={close} onClose={close} aria-label="附注正文"><div className="finance-heading"><h3>{detail?.title||'来源原文'}</h3><button className="button secondary" onClick={close}>关闭</button></div><div className="finance-evidence-body">
  {ids.length>1&&<select aria-label="附注来源" value={selected} onChange={e=>setSelected(e.target.value)}>{ids.map(id=><option key={id} value={id}>{docs.find(d=>d.id===notes.find(n=>n.id===id)?.document_id)?.name||id}</option>)}</select>}
  {error?<p role="alert">{error}</p>:!detail?<p>加载中…</p>:<><a className="button secondary" href={'/api/projects/'+pid+'/documents/'+detail.document_id+'/download'}>下载原报告</a>{detail.blocks.map((block,i)=>block.type==='text'?<div className="finance-note-text" key={i}>{block.text}</div>:<div className="finance-table-scroll" key={i}><table className="finance-note-table"><tbody>{block.rows.map((row,j)=><tr key={j}>{row.map((cell,k)=><td key={k} colSpan={cell.colspan} rowSpan={cell.rowspan}>{cell.text||'—'}</td>)}</tr>)}</tbody></table></div>)}<details><summary>原文位置</summary><p>第 {detail.start_line}–{detail.end_line} 行</p><p className="finance-hash">SHA-256：{detail.markdown_sha256}</p><pre>{detail.lines.join('\n')}</pre></details></>}
 </div></dialog>
}
