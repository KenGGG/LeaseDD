import React,{useEffect,useRef,useState} from 'react';
import {Download,Search,X,FileText} from 'lucide-react';
import {api,enterpriseCoverage,enterpriseStateLabel,failedEnterpriseModules,selectedEnterpriseCandidate,usesPdfEvidence} from './api';
import type {Doc,EnterpriseCandidate,EnterpriseModuleData,EnterpriseStatus,FinancialStatement,User} from './api';
import {buildMatrix,cellState,diagnosticSummary,formatCellAmount,groupKey,scopeLabels,statementLabels,statusLabels,toCsv,unitPowers} from './financial-view';
import type {Candidate} from './financial-view';
import './financial.css';
import FinancialInsights from './FinancialInsights';
import FinancialNotes from './FinancialNotes';
import {analysisCategories,noteCategories,noteGroups,noteParent,noteLabel} from './reference-finance';

type Props={statements:FinancialStatement[];docs:Doc[];pid:string;writer:boolean;busy:boolean;perform:(fn:()=>Promise<void>)=>void;refresh:()=>Promise<void>;children:React.ReactNode};
const stateText={empty:'—',rejected:'已拒绝',unverified:'来源待核对',conflict:'存在冲突',pending:'待核对',value:''};
export default function FinancialWorkspace({statements,docs,pid,writer,busy,perform,refresh,children}:Props){
 const [type,setType]=useState<FinancialStatement['statement_type']|'metrics'|'analysis'|'notes'>('balance_sheet');
 const [selectedGroup,setSelectedGroup]=useState(''),[unit,setUnit]=useState('万元'),[decimals,setDecimals]=useState(2);
 const [report,setReport]=useState('all'),[startYear,setStartYear]=useState(''),[endYear,setEndYear]=useState('');
 const [descending,setDescending]=useState(true),[hideEmpty,setHideEmpty]=useState(true),[query,setQuery]=useState('');
 const [analysisCategory,setAnalysisCategory]=useState('盈利能力'),[notesCategory,setNotesCategory]=useState('审计报告');
 const [insightSelection,setInsightSelection]=useState<{ids:string[];title:string}|null>(null);
 const [selection,setSelection]=useState<{concept:string;period:string}|null>(null);
 const [rowOrder,setRowOrder]=useState<'source'|'standard'>('source'),[review,setReview]=useState('all');
 const [enterprise,setEnterprise]=useState<EnterpriseStatus|null>(null),[canImport,setCanImport]=useState(false);
 const [enterpriseQuery,setEnterpriseQuery]=useState(''),[enterpriseCandidates,setEnterpriseCandidates]=useState<EnterpriseCandidate[]>([]),[selectedCompany,setSelectedCompany]=useState('');
 const [enterpriseModules,setEnterpriseModules]=useState<EnterpriseModuleData[]>([]),[enterpriseCoverageModules,setEnterpriseCoverageModules]=useState<EnterpriseModuleData[]>([]);
 const groups=[...new Map(statements.map(s=>[groupKey(s),s])).entries()];
 const group=groups.some(([key])=>key===selectedGroup)?selectedGroup:groups[0]?.[0]||'';
 const selected=groups.find(([key])=>key===group)?.[1];
 const matrix=buildMatrix(statements,{group,type:type==='metrics'||type==='analysis'||type==='notes'?'balance_sheet':type,hideEmpty,report,startYear,endYear,descending,query,rowOrder,review});
 const diagnosticStatements=statements.filter(s=>groupKey(s)===group&&s.statement_type===type);
 const diagnosticLabels=diagnosticSummary(diagnosticStatements);
 const years=[...new Set(statements.filter(s=>groupKey(s)===group).map(s=>(s.period_normalized||s.period).slice(0,4)).filter(y=>/^\d{4}$/.test(y)))].sort().reverse();
 const docName=(id:string)=>id?docs.find(d=>d.id===id)?.name||id:'企业预警通';
 const chosenRow=matrix.rows.find(r=>r.concept===selection?.concept);
 const periodIndex=matrix.periods.findIndex(p=>p.key===selection?.period);
 const candidates=chosenRow?.cells[periodIndex]||[];
 useEffect(()=>setSelection(null),[pid,group,type,report,startYear,endYear]);
 useEffect(()=>{let active=true;Promise.all([api<EnterpriseStatus>('/projects/'+pid+'/enterprise'),api<User>('/me')]).then(([status,user])=>{if(active){setEnterprise(status);setCanImport(user.admin)}});return()=>{active=false}},[pid]);
 useEffect(()=>{if(enterprise?.source_type!=='enterprise_warning'||!['metrics','analysis','notes'].includes(type)){setEnterpriseModules([]);return}let active=true;const category=type==='metrics'?'indicators':type;api<{modules:EnterpriseModuleData[]}>('/projects/'+pid+'/enterprise/data?category='+category).then(result=>{if(active)setEnterpriseModules(result.modules)});return()=>{active=false}},[pid,type,enterprise?.import?.id]);
 useEffect(()=>{if(enterprise?.source_type!=='enterprise_warning'){setEnterpriseCoverageModules([]);return}let active=true;api<{modules:EnterpriseModuleData[]}>('/projects/'+pid+'/enterprise/data').then(result=>{if(active)setEnterpriseCoverageModules(result.modules)});return()=>{active=false}},[pid,enterprise?.import?.id]);
 async function reloadEnterprise(){setEnterprise(await api<EnterpriseStatus>('/projects/'+pid+'/enterprise'));await refresh()}
 async function searchEnterprise(){const result=await api<{candidates:EnterpriseCandidate[]}>('/projects/'+pid+'/enterprise/import','POST',{query:enterpriseQuery});setEnterpriseCandidates(result.candidates);setSelectedCompany('')}
 async function importEnterprise(){const chosen=selectedEnterpriseCandidate(enterpriseCandidates,selectedCompany);if(!chosen)return;await api('/projects/'+pid+'/enterprise/import','POST',{company_code:chosen.code,company_name:chosen.name});await reloadEnterprise()}
 async function retryEnterprise(){await api('/projects/'+pid+'/enterprise/retry','POST');await reloadEnterprise()}
 function cellText(c:Candidate[]){const state=cellState(c);return state.value!==null?formatCellAmount(c,unit,decimals)+(state.kind==='pending'?'（待核对）':''):stateText[state.kind]}
 function exportCsv(){
  const metadata=[['LeaseDD 财务核对表（非审核定稿）'],['主体',selected?.entity||''],['报表口径',scopeLabels[selected?.scope||'']||selected?.scope||''],['币种',selected?.currency||''],['单位',unit],['报表',type==='metrics'?'主要财务指标':statementLabels[type as FinancialStatement['statement_type']]]];
  const values=[['科目',...matrix.periods.map(p=>p.label+' '+p.date)],...matrix.rows.map(r=>[r.label,...r.cells.map(cellText)])];
  const evidence=[[],['来源对照：科目','期间','原件','原科目','原值','原单位','折算值（原币元）','核对状态','Markdown 起始行','Markdown 结束行','候选 ID'],...matrix.rows.flatMap(r=>r.cells.flatMap((c,i)=>c.map(({item,statement})=>[r.label,matrix.periods[i].date,docName(statement.document_id),item.source_name,item.raw_value,item.raw_unit,item.normalized_value||'',statusLabels[item.status]||item.status,String(item.source_start_line),String(item.source_end_line),item.id])))];
  const url=URL.createObjectURL(new Blob([toCsv([...metadata,...values,...evidence])],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='LeaseDD_'+(type==='metrics'?'财务指标':statementLabels[type as FinancialStatement['statement_type']])+'_待核对.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 function selectTab(value:typeof type){setType(value);setQuery('');setInsightSelection(null)}
 return <div className="financial-workspace">
  <nav className="finance-nav" aria-label="财务数据栏目"><div className="finance-nav-title">财务数据</div>
   <button className={type==='metrics'?'active':''} onClick={()=>selectTab('metrics')}>主要财务指标</button>
   {Object.entries(statementLabels).map(([key,label])=><button key={key} className={type===key?'active':''} onClick={()=>selectTab(key as typeof type)}>{label}</button>)}
   <button className={type==='analysis'?'active':''} onClick={()=>selectTab('analysis')}>财务分析</button>
   {type==='analysis'&&analysisCategories.map(c=><button key={c} className={'finance-subnav '+(analysisCategory===c?'active':'')} onClick={()=>setAnalysisCategory(c)}>{c}</button>)}
   <button className={type==='notes'?'active':''} onClick={()=>selectTab('notes')}>财务附注</button>
   {type==='notes'&&noteCategories.map(c=><React.Fragment key={c}><button className={'finance-subnav '+(noteParent(notesCategory)===c?'active':'')} onClick={()=>setNotesCategory(noteGroups[c]?.[0]||c)}>{c}</button>{noteParent(notesCategory)===c&&noteGroups[c]?.map(child=><button key={child} className={'finance-subnav finance-leaf '+(notesCategory===child?'active':'')} onClick={()=>setNotesCategory(child)}>{noteLabel(child)}</button>)}</React.Fragment>)}
  </nav>
  <section className="finance-content">
   <EnterprisePanel status={enterprise} modules={enterpriseCoverageModules} admin={canImport} busy={busy} query={enterpriseQuery} setQuery={setEnterpriseQuery} candidates={enterpriseCandidates} selected={selectedCompany} setSelected={setSelectedCompany} perform={perform} search={searchEnterprise} start={importEnterprise} retry={retryEnterprise}/>
   {enterprise?.source_type==='enterprise_warning'&&['metrics','analysis','notes'].includes(type)?<EnterpriseRawModules modules={enterpriseModules}/>:type==='metrics'||type==='analysis'?<FinancialInsights pid={pid} statements={statements} mode={type} category={analysisCategory} onEvidence={(ids,title)=>setInsightSelection({ids,title})}>{children}</FinancialInsights>:type==='notes'?<FinancialNotes pid={pid} docs={docs} category={notesCategory}/>:<>
    <div className="finance-heading"><div><h2>{statementLabels[type as FinancialStatement['statement_type']]}</h2><p>{selected?.entity||'上传资料后查看财务数据'}{selected&&<span> · {scopeLabels[selected.scope]||selected.scope} · {selected.currency==='CNY'?'人民币':selected.currency}</span>}</p></div><button className="button secondary" disabled={!matrix.periods.length} onClick={exportCsv}><Download size={14}/>导出 CSV</button></div>
    {!!diagnosticLabels.length&&<details className="finance-diagnostics"><summary>{diagnosticLabels.join('；')}</summary>{diagnosticStatements.flatMap(s=>(s.checks||[]).filter(c=>c.status!=='passed').map(c=><div key={s.id+c.code}><strong>{c.status==='conflict'?'勾稽不一致':c.status==='not_checked_missing_disclosure'?'缺少披露项，未检查':'来源未核实，未检查'}</strong>{c.difference!==null&&<span>差额 {c.difference}；容差 {c.tolerance}</span>}{c.missing_concepts.length>0&&<span>缺少：{c.missing_concepts.join('、')}</span>}{!!c.item_ids?.length&&<button className="button secondary" onClick={()=>setInsightSelection({ids:c.item_ids||[],title:'勾稽检查相关来源'})}>查看相关来源</button>}</div>))}</details>}
    {statements.length===0?<div className="finance-empty"><FileText size={32}/><h3>还没有识别出的财务报表</h3><p>在“资料与证据”上传材料，勾选允许 Agnes 提取财务数据，再点击“批量识别”。处理完成后，各期数据会在这里横向对齐。</p></div>:<>
     <div className="finance-filters">
      <label className="finance-group">主体 / 口径 / 币种<select aria-label="财务主体口径" value={group} onChange={e=>{setSelectedGroup(e.target.value);setStartYear('');setEndYear('')}}>{groups.map(([key,s])=><option key={key} value={key}>{s.entity} · {scopeLabels[s.scope]||s.scope} · {s.currency}{s.scope==='unknown'?' · '+docName(s.document_id):''}</option>)}</select></label>
      <label>报告期<select aria-label="报告期类型" value={report} onChange={e=>setReport(e.target.value)}><option value="all">全部报告期</option><option value="annual">年报</option><option value="half">中报</option><option value="quarter">季度报告</option></select></label>
      <label>起始年度<select aria-label="起始年度" value={startYear} onChange={e=>setStartYear(e.target.value)}><option value="">不限</option>{years.map(y=><option key={y}>{y}</option>)}</select></label>
      <label>结束年度<select aria-label="结束年度" value={endYear} onChange={e=>setEndYear(e.target.value)}><option value="">不限</option>{years.map(y=><option key={y}>{y}</option>)}</select></label>
      <label>单位<select aria-label="显示单位" value={unit} onChange={e=>setUnit(e.target.value)}>{Object.keys(unitPowers).map(u=><option key={u}>{u}</option>)}</select></label>
      <label>精度<select aria-label="小数位数" value={decimals} onChange={e=>setDecimals(Number(e.target.value))}>{[0,2,4].map(n=><option key={n} value={n}>{n} 位小数</option>)}</select></label>
      <label>科目排列<select aria-label="科目排列" value={rowOrder} onChange={e=>setRowOrder(e.target.value as typeof rowOrder)}><option value="source">原表顺序</option><option value="standard">标准科目顺序</option></select></label>
     </div>
     <div className="finance-tools"><div className="finance-presets">年度{[3,5,10].map(n=><button key={n} disabled={!years.length} onClick={()=>{setStartYear(String(Number(years[0])-n+1));setEndYear(years[0])}}>近 {n} 年</button>)}<button onClick={()=>{setStartYear('');setEndYear('');setReport('all');setQuery('');setReview('all')}}>全部</button></div><label><input type="checkbox" checked={descending} onChange={e=>setDescending(e.target.checked)}/>报告期倒序</label><label><input type="checkbox" checked={hideEmpty} onChange={e=>setHideEmpty(e.target.checked)}/>隐藏空行</label><div className="finance-search"><Search size={14}/><input aria-label="搜索财务科目" placeholder="搜索科目" value={query} onChange={e=>setQuery(e.target.value)}/></div></div>
     <details className="finance-advanced"><summary>核对筛选</summary><div className="finance-review-filters" aria-label="财务核对状态">{[{id:'all',label:'全部数值'},{id:'unreviewed',label:'待人工核对',count:matrix.counts.unreviewed},{id:'conflict',label:'存在冲突',count:matrix.counts.conflict},{id:'confirmed',label:'已确认',count:matrix.counts.confirmed}].map(f=><button key={f.id} aria-pressed={review===f.id} onClick={()=>{setReview(f.id);setSelection(null)}}>{f.label}{f.count!==undefined&&<span>{f.count}</span>}</button>)}<small>按数值计数，筛选显示匹配科目的全部期间</small></div></details>
     {startYear&&endYear&&startYear>endYear?<div className="finance-empty">起始年度不能晚于结束年度，请调整筛选条件。</div>:matrix.periods.length===0?<div className="finance-empty">当前筛选下没有该类报表。请切换报表或调整报告期。</div>:<div className="finance-table-scroll" tabIndex={0} aria-label={statementLabels[type as FinancialStatement['statement_type']]+'横向对比表'}><table className="finance-matrix"><thead><tr><th scope="col">报告期</th>{matrix.periods.map(p=><th key={p.key} scope="col">{p.label}<small>{p.date}</small></th>)}</tr></thead><tbody>
      <tr className="finance-scope-row"><th scope="row">报表口径</th>{matrix.periods.map(p=><td key={p.key}>{scopeLabels[selected?.scope||'']||selected?.scope}</td>)}</tr>
      {matrix.rows.map((r,index)=><React.Fragment key={r.concept}>{(index===0||matrix.rows[index-1].section!==r.section)&&<tr className="finance-section"><th scope="row">{r.section}</th>{matrix.periods.map(p=><td key={p.key}/>)}</tr>}<tr className={r.total?'finance-total':''}><th scope="row">{r.label}</th>{r.cells.map((c,i)=>{const state=cellState(c);return <td key={matrix.periods[i].key}>{c.length?<button className={'finance-number '+state.kind+(state.confirmed?' confirmed':'')} title={c.length+' 个来源；点击查看原值与证据'} aria-label={r.label+' '+matrix.periods[i].label+' '+cellText(c)} onClick={()=>setSelection({concept:r.concept,period:matrix.periods[i].key})}>{state.value!==null?formatCellAmount(c,unit,decimals):stateText[state.kind]}</button>:<span className="finance-missing" title="原表未披露数值，或当前资料尚未提取此科目">—</span>}</td>})}</tr></React.Fragment>)}
      {matrix.rows.length===0&&<tr><td colSpan={matrix.periods.length+1}>当前筛选没有匹配科目，可切换“全部数值”、调整搜索或取消隐藏空行。</td></tr>}
     </tbody></table></div>}

    </>}
   </>}
  </section>
  {insightSelection&&<Evidence title={insightSelection.title} candidates={statements.flatMap(statement=>statement.items.filter(item=>insightSelection.ids.includes(item.id)).map(item=>({statement,item})))} docName={docName} pid={pid} writer={writer} busy={busy} perform={perform} refresh={refresh} close={()=>setInsightSelection(null)}/>}
  {selection&&chosenRow&&candidates.length>0&&<Evidence key={selection.concept+selection.period} title={chosenRow.label+' · '+matrix.periods[periodIndex].label} candidates={candidates} docName={docName} pid={pid} writer={writer} busy={busy} perform={perform} refresh={refresh} close={()=>setSelection(null)}/>}
 </div>
}

function EnterprisePanel({status,modules,admin,busy,query,setQuery,candidates,selected,setSelected,perform,search,start,retry}:{status:EnterpriseStatus|null;modules:EnterpriseModuleData[];admin:boolean;busy:boolean;query:string;setQuery:(value:string)=>void;candidates:EnterpriseCandidate[];selected:string;setSelected:(value:string)=>void;perform:Props['perform'];search:()=>Promise<void>;start:()=>Promise<void>;retry:()=>Promise<void>}){
 const failed=failedEnterpriseModules(status?.import?.module_status),coverage=enterpriseCoverage(modules);
 return <aside className="enterprise-panel"><div><strong>财务数据来源：{status?.binding?'企业预警通':'尚未绑定'}</strong><span className="badge subtle">{enterpriseStateLabel(status?.import?.state)}</span>{status?.binding&&<small>{status.binding.company_name} · {status.binding.company_code}</small>}{modules.length>0&&<small>报表/指标 {coverage.statements}/4 · 财务分析 {coverage.analysis}/7 · 财务附注 {coverage.notes}/6</small>}{failed.length>0&&<small>失败模块：{failed.join('、')}</small>}</div>{admin&&<div className="enterprise-actions"><input aria-label="搜索企业预警通企业" placeholder="输入企业名称" value={query} onChange={event=>setQuery(event.target.value)}/><button className="button secondary" disabled={busy||!query.trim()} onClick={()=>perform(search)}>搜索</button>{candidates.length>0&&<><select aria-label="企业预警通候选" value={selected} onChange={event=>setSelected(event.target.value)}><option value="">请选择匹配企业</option>{candidates.map(candidate=><option key={candidate.code} value={candidate.code}>{candidate.name} · {candidate.code}</option>)}</select><button className="button primary" disabled={busy||!selected} onClick={()=>perform(start)}>确认并导入</button></>}{failed.length>0&&<button className="button secondary" disabled={busy} onClick={()=>perform(retry)}>重试失败模块</button>}</div>}</aside>
}

function EnterpriseRawModules({modules}:{modules:EnterpriseModuleData[]}){
 if(!modules.length)return <div className="finance-empty">当前栏目暂无企业预警通数据。</div>;
 return <div><div className="finance-heading"><div><h2>企业预警通原始栏目</h2><p>保留来源层级、期间、单位与原值</p></div></div><div className="enterprise-modules">{modules.map(module=><details key={module.module_key}><summary>{module.module_name||module.module_key}<span className="badge subtle">{module.state||'completed'}</span></summary><p>{module.endpoint_path}</p><p className="finance-hash">响应 SHA-256：{module.response_sha256}</p><pre>{JSON.stringify(module.parsed_payload,null,2)}</pre></details>)}</div></div>
}

function Evidence({title,candidates,docName,pid,writer,busy,perform,refresh,close}:{title:string;candidates:Candidate[];docName:(id:string)=>string;pid:string;writer:boolean;busy:boolean;perform:Props['perform'];refresh:Props['refresh'];close:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),request=useRef(0);
 const [source,setSource]=useState<{id:string;lines:string[];start_line:number}|null>(null),[reason,setReason]=useState('');
 useEffect(()=>{dialog.current?.showModal();return()=>{request.current++}},[]);
 async function showSource(id:string){const token=++request.current;setSource(null);const result=await api<{lines:string[];start_line:number}>('/projects/'+pid+'/financial-items/'+id+'/source');if(request.current===token)setSource({...result,id})}
 async function decide(id:string,decision:string){if(!reason.trim())return;await api('/projects/'+pid+'/financial-items/'+id+'/confirm','POST',{decision,reason:reason.trim()});await refresh();setReason('')}
 return <dialog className="finance-evidence" ref={dialog} onCancel={close} onClose={close} aria-labelledby="finance-evidence-title"><div className="finance-heading"><div><h2 id="finance-evidence-title">{title}</h2><p>{candidates.length} 个来源候选 · 原件与 Markdown 定位</p></div><button className="iconbutton" aria-label="关闭财务来源" onClick={close}><X size={20}/></button></div><div className="finance-evidence-body">
  {candidates.map(({item,statement})=><section className="finance-candidate" key={item.id}><div className="finance-candidate-heading"><strong>{docName(statement.document_id)}</strong><span className="badge amber">{statusLabels[item.status]||item.status}</span></div><dl><dt>原科目</dt><dd>{item.source_name}</dd><dt>原始披露</dt><dd>{item.raw_value} {item.raw_unit} · {statement.currency}</dd><dt>折算值</dt><dd>{item.normalized_value??'无法换算'} {item.raw_unit==='元/股'?'元/股':'元'}</dd><dt>期间 / 口径</dt><dd>{statement.period_normalized||statement.period} · {scopeLabels[statement.scope]||statement.scope}</dd>{statement.source_type==='enterprise_warning'?<><dt>接口来源</dt><dd>{String(item.evidence?.module_key||'')} · 行 {String(item.evidence?.row??'')} · 期间列 {String(item.evidence?.period_column??'')}</dd><dt>响应摘要</dt><dd className="finance-hash">{String(item.evidence?.response_sha256||'')}</dd></>:<>{statement.statement_type==='balance_sheet'&&/^\d{4}-01-01$/.test(statement.period)&&statement.period!==statement.period_normalized&&<><dt>原表列日期</dt><dd>{statement.period}（年初余额，归入上年年末对比；原始来源保留）</dd></>}<dt>原文摘录</dt><dd className="finance-raw-row">{item.source_cells?<div className="finance-source-row"><table><caption>原表同一行（按原列序排列）</caption>{!!item.source_headers?.length&&<thead><tr>{item.source_headers.map((cell,n)=><th key={n}>{cell}</th>)}</tr></thead>}<tbody><tr>{item.source_cells.map((cell,n)=><td key={n} className={n>0&&cell===item.raw_value?'source-value-match':''}>{cell||'—'}</td>)}</tr></tbody></table></div>:<pre>{item.source_text}</pre>}<details><summary>查看原始文本</summary><pre>{item.source_text}</pre></details></dd><dt>原文位置</dt><dd>Markdown 第 {item.source_start_line}–{item.source_end_line} 行</dd></>}</dl>
   {statement.issues.length>0&&<p className="finance-pending">报表口径问题：{statement.issues.join('；')}</p>}
   {item.confirmation_reason&&<p>核对意见：{item.confirmation_reason}</p>}
   {usesPdfEvidence(statement.source_type)&&<div className="button-group"><button className="button secondary" disabled={busy} onClick={()=>perform(()=>showSource(item.id))}>查看来源原文</button><a className="button secondary" href={'/api/projects/'+pid+'/documents/'+statement.document_id+'/download'}>下载原件</a>{writer&&!item.supplemental&&!['human_confirmed','human_rejected'].includes(item.status)&&<><button className="button secondary" disabled={busy||!reason.trim()||item.status==='source_value_not_found'} onClick={()=>perform(()=>decide(item.id,'confirm'))}>确认此值</button><button className="button secondary" disabled={busy||!reason.trim()} onClick={()=>perform(()=>decide(item.id,'reject'))}>拒绝此值</button></>}</div>}
   {source?.id===item.id&&<div className="evidence-lines finance-source">{source.lines.map((line,i)=><div key={i}><span>{source.start_line+i}</span><code>{line}</code></div>)}</div>}
  </section>)}
  {writer&&candidates.some(candidate=>candidate.statement.source_type!=='enterprise_warning')&&<label className="finance-reason">核对理由（确认或拒绝前填写）<textarea aria-label="财务核对理由" value={reason} onChange={e=>setReason(e.target.value)} placeholder="请说明已核对的依据或拒绝原因"/></label>}
 </div></dialog>
}
