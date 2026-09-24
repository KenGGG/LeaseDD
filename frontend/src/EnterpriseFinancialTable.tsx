import React,{useEffect,useId,useState} from 'react';
import {createPortal} from 'react-dom';
import {enterpriseCellUnit,enterpriseColumnKind,enterpriseCurrencyVariants,selectEnterpriseCurrencyVariant,enterpriseToolbarOptions,enterpriseReportOptions,enterpriseNotePrecisionState} from './enterprise-financial-view';
import type {EnterpriseModuleData} from './api';
import {buildEnterpriseModuleView,filterEnterpriseMatrix,filterEnterpriseRecords,enterpriseHasPeriodControls,groupEnterpriseRecordTables,enterpriseDisplayValue,enterpriseDisplayRecordValue,selectEnterpriseModule,collapseEnterpriseRows,enterpriseSourceLink,enterpriseExportUrl} from './enterprise-financial-view';
import {unitPowers} from './financial-view';
import type {EnterpriseMatrixRow} from './enterprise-financial-view';
import EnterpriseIndicatorTrend from './EnterpriseIndicatorTrend';
import EnterpriseStatementTrend from './EnterpriseStatementTrend';

function IndicatorHelp({row}:{row:EnterpriseMatrixRow}){
 const id=useId(),[anchor,setAnchor]=useState<{left:number;top:number}|null>(null);
 useEffect(()=>{
  if(!anchor)return;
  const close=()=>setAnchor(null);
  window.addEventListener('scroll',close,true);window.addEventListener('resize',close);
  return ()=>{window.removeEventListener('scroll',close,true);window.removeEventListener('resize',close)};
 },[anchor]);
 if(!row.description&&!row.formula)return null;
 const show=(element:HTMLButtonElement)=>{const rect=element.getBoundingClientRect();setAnchor({left:Math.max(8,Math.min(rect.left,window.innerWidth-348)),top:rect.bottom+6})};
 return <><button className="enterprise-indicator-help" aria-label={'指标说明 - '+row.label} aria-describedby={anchor?id:undefined}
  onMouseEnter={event=>show(event.currentTarget)} onMouseLeave={()=>setAnchor(null)} onFocus={event=>show(event.currentTarget)} onBlur={()=>setAnchor(null)}
  onClick={event=>show(event.currentTarget)} onKeyDown={event=>{if(event.key==='Escape')setAnchor(null)}}>?</button>
  {anchor&&createPortal(<div id={id} role="tooltip" className="enterprise-indicator-tooltip" style={anchor}>
   <strong>指标说明 - {row.label}</strong>{row.description&&<p>{row.description}</p>}{row.formula&&<p>公式：<br/>{row.formula}</p>}{row.definitionUnit&&<p>单位：{row.definitionUnit}</p>}
  </div>,document.body)}</>;
}

const reportOptions=[['all','全部'],['latest','最新'],['annual','年报'],['q3','三季报'],['half','中报'],['q1','一季报']];
const sourceNoSortNotes=new Set(['audit_report','receivables_aging','other_receivables_aging','prepayments_aging','cash_notes','inventory_notes','finance_costs','nonrecurring_gains_losses']);
function ReportSelect({value,onChange,label='报告期',options=reportOptions}:{value:string;onChange:(value:string)=>void;label?:string;options?:string[][]}){
 const selected=value.split(',');
 const labels=options.filter(([key])=>selected.includes(key)).map(([,label])=>label);
 return <div className="reference-report"><span>{label}</span><details className="reference-select">
  <summary aria-label={label+'筛选'}>{labels.join(',')||'请选择'} <span>▾</span></summary>
  <div className="reference-select-options">{options.map(([key,label])=><label key={key}><input type="checkbox" checked={selected.includes(key)} onChange={event=>{
   if(key==='all'){onChange(event.target.checked?'all':'');return}
   const next=new Set(selected.filter(item=>item&&item!=='all'));event.target.checked?next.add(key):next.delete(key);onChange([...next].join(','));
  }}/>{label}</label>)}<button onClick={event=>{const details=event.currentTarget.closest('details');if(details)details.open=false}}>确定</button></div>
 </details></div>;
}

export default function EnterpriseFinancialTable({modules,activeName,projectId}:{modules:EnterpriseModuleData[];activeName?:string;projectId:string}){
 const sourceModule=selectEnterpriseModule(modules,activeName);
 const [currency,setCurrency]=useState('O'),[rate,setRate]=useState('1');
 const module=selectEnterpriseCurrencyVariant(sourceModule,currency,rate);
 const variants=enterpriseCurrencyVariants(sourceModule);
 const currencyNames:Record<string,string>={O:'披露币种',CNY:'人民币',USD:'美元',JPY:'日元',HKD:'港元',GBP:'英镑',EUR:'欧元',CAD:'加拿大元',AUD:'澳大利亚元'};
 const currencyOptions=[...new Set(variants.map(v=>String((v.request_params as Record<string,unknown>)?.displayCurrency)))];
 const rateOptions=[...new Set(variants.filter(v=>(v.request_params as Record<string,unknown>)?.displayCurrency===currency).map(v=>String((v.request_params as Record<string,unknown>)?.rateType)))];
 const [report,setReport]=useState(sourceModule?.category==='notes'||sourceModule?.category==='analysis'?'latest,annual':'latest,annual,q3');
 const [start,setStart]=useState(''),[end,setEnd]=useState(''),[unit,setUnit]=useState('万元');
 const [decimals,setDecimals]=useState(module?.module_key==='per_share'?4:2);
 const defaults=sourceModule?enterpriseToolbarOptions(sourceModule):undefined;
 const [windowYears,setWindowYears]=useState(defaults?.defaultYears||0);
 const [scopes,setScopes]=useState(defaults?.defaultScope||'all'),[dataKinds,setDataKinds]=useState(defaults?.defaultKind||'all');
 const [descending,setDescending]=useState(true),[hideEmpty,setHideEmpty]=useState(true),[filtersHidden,setFiltersHidden]=useState(false);
 const [collapsedRows,setCollapsedRows]=useState<Set<string>>(new Set());
 const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState('');
 const [trendKey,setTrendKey]=useState('');
 if(!module)return <p className="finance-empty">{activeName||'当前栏目'}尚未导入。</p>;
 const original=buildEnterpriseModuleView(module);
 const periodControls=enterpriseHasPeriodControls(original,module);
 const view=original.kind==='matrix'?filterEnterpriseMatrix(original,{report,start,end,descending,hideEmpty,scopes,dataKinds,windowYears}):original.kind==='records'&&periodControls?filterEnterpriseRecords(original,{report,start,end,descending,hideEmpty,windowYears}):original;
 const visibleRows=view.kind==='matrix'?collapseEnterpriseRows(view.rows,collapsedRows):[];
 const years=original.kind==='matrix'?[...new Set(original.periods.map(p=>p.slice(0,4)))].sort().reverse():original.kind==='records'?[...new Set(original.tables.map(table=>table.title.slice(0,4)).filter(value=>/^\d{4}$/.test(value)))].sort().reverse():[];
 const text=(value:unknown)=>value==null?'':String(value);
 const metadata=(key:string)=>original.kind==='matrix'?[...new Set(original.rows.find(row=>row.key===key)?.values.map(text).filter(Boolean)||[])]:[];
 const main=module.category==='statements'||module.category==='indicators';
 const toolbar=enterpriseToolbarOptions(module);
 const precisionState=enterpriseNotePrecisionState(module),preciseRecord=precisionState==='precise';
 const columnKinds=(metadata('dataType').length?metadata('dataType'):metadata('reportRange')).map(enterpriseColumnKind);
 const scopeOptions=[['all','全部'],...[...new Set(columnKinds.map(item=>item.scope).filter(Boolean))].map(value=>[value,value])];
 const kindOptions=[['all','全部'],...[...new Set(columnKinds.map(item=>item.kind))].map(value=>[value,value])];
 const sources=view.kind==='matrix'?view.rows.find(row=>row.key==='dataSource')?.values||[]:[];
 const sortLabel='报告期'+(module.category==='analysis'?(descending?'降序':'正序'):(descending?'倒序':'正序'));
 async function exportExcel(){
  if(!module)return;
  setExporting(true);setExportError('');
  try{
   const response=await fetch(enterpriseExportUrl(projectId,module.module_key,{report:periodControls?report:'all',start,end,descending,hideEmpty:periodControls?hideEmpty:false,scopes,dataKinds,currency,rate,windowYears},unit,decimals,module.response_sha256),{credentials:'same-origin'});
   if(!response.ok)throw new Error(response.status===409?'来源批次已变化，请刷新页面后再导出。':'Excel 导出失败，请重试。');
   if(!response.headers.get('content-type')?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))throw new Error('返回内容不是 Excel 文件，请刷新后重试。');
   const url=URL.createObjectURL(await response.blob());
   const link=document.createElement('a');link.href=url;link.download=(module.module_name||module.module_key)+'.xlsx';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(error){setExportError(error instanceof Error?error.message:'Excel 导出失败，请重试。')}finally{setExporting(false)}
 }
 function toggleRow(key:string){setCollapsedRows(previous=>{const next=new Set(previous);next.has(key)?next.delete(key):next.add(key);return next})}
 return <div className={'enterprise-financial-view enterprise-reference enterprise-reference-'+module.category}>
  <div className="finance-heading"><h2>{module.module_name}</h2>{periodControls&&<button className="reference-link" onClick={()=>setFiltersHidden(!filtersHidden)}>{filtersHidden?'展开筛选':'收起筛选'}</button>}</div>
  {precisionState==='legacy_summary'&&<p role="alert" className="finance-pending">该栏目当前仍为旧摘要批次：金额经原站压缩显示，并非原站财务表的精确值；请由管理员重新导入。</p>}
  <div className="enterprise-reference-toolbar">
  {!filtersHidden&&periodControls&&<div className="enterprise-reference-filters">
   <ReportSelect value={report} onChange={setReport} options={enterpriseReportOptions(module)}/>
   {(toolbar.yearsAndUnit||original.kind==='records')&&<>
    <div className="reference-years"><span>年度</span>{[3,5,10].map(n=><button key={n} aria-pressed={windowYears===n} onClick={()=>{setWindowYears(n);setStart('');setEnd('')}}>{n}Y</button>)}<select aria-label="起始年度" value={start} onChange={e=>{setWindowYears(0);setStart(e.target.value)}}><option value="">起始</option>{years.map(y=><option key={y}>{y}</option>)}</select><span>至</span><select aria-label="结束年度" value={end} onChange={e=>{setWindowYears(0);setEnd(e.target.value)}}><option value="">结束</option>{years.map(y=><option key={y}>{y}</option>)}</select><button onClick={()=>{setWindowYears(0);setStart('');setEnd('')}}>全部</button></div>
    {(main||module.category==='analysis')&&scopeOptions.length>1&&<ReportSelect label={main?'报表类型':'合并类型'} value={scopes} onChange={setScopes} options={scopeOptions}/>}
    {toolbar.dataKinds&&kindOptions.length>1&&<ReportSelect label="数据类型" value={dataKinds} onChange={setDataKinds} options={kindOptions}/>}
    {(toolbar.yearsAndUnit||preciseRecord)&&<><label>单位<select aria-label="显示单位" value={unit} onChange={e=>setUnit(e.target.value)}>{Object.keys(unitPowers).map(v=><option key={v}>{v}</option>)}</select></label>
    <div className="reference-years"><button aria-label="减少小数位" disabled={decimals===0} onClick={()=>setDecimals(decimals-1)}>.00 ←</button><button aria-label="增加小数位" disabled={decimals===6} onClick={()=>setDecimals(decimals+1)}>→ .00</button></div></>}
    {toolbar.currency&&<><label>币种<select aria-label="币种" value={currency} disabled={!variants.length} onChange={e=>{setCurrency(e.target.value);setRate('1')}}>{(currencyOptions.length?currencyOptions:['O']).map(v=><option key={v} value={v}>{currencyNames[v]||v}</option>)}</select></label><label>汇率<select aria-label="汇率" value={rate} disabled={!variants.length} onChange={e=>setRate(e.target.value)}>{(rateOptions.length?rateOptions:['1']).map(v=><option key={v} value={v}>{v==='1'?'期末汇率':v==='2'?'最新汇率':v}</option>)}</select></label></>}
   </>}
  </div>}
  <div className="enterprise-reference-tools">{periodControls&&<>{!sourceNoSortNotes.has(module.module_key)&&<button onClick={()=>setDescending(!descending)}>{sortLabel}<svg className="reference-sort-icon" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true"><path d="M3 10V2m0 0L1.5 3.5M3 2l1.5 1.5M9 2v8m0 0L7.5 8.5M9 10l1.5-1.5"/></svg></button>}{original.kind==='matrix'&&module.category!=='analysis'&&<label><input type="checkbox" checked={hideEmpty} onChange={e=>setHideEmpty(e.target.checked)}/>隐藏空行</label>}</>}<button className="reference-export" disabled={view.kind==='empty'||exporting} onClick={exportExcel}>{exporting?'正在导出…':'导出Excel'}</button></div>
  </div>
  {exportError&&<p role="alert" className="finance-pending">{exportError}</p>}
  {view.kind==='matrix'?<div className="finance-table-scroll enterprise-source-table" tabIndex={0} aria-label={module.module_name+'原始数据表'}>
   <table className="finance-matrix"><thead><tr><th>{view.firstColumnLabel||(module.category==='notes'?'项目名称':module.category==='analysis'?'指标名称':'报告期')}</th>{view.periods.map((period,index)=>{const source=enterpriseSourceLink(sources[index]);return <th key={period+index}>{period}{source&&<a className="enterprise-pdf-link" href={source.href} target="_blank" rel="noopener noreferrer" aria-label={'查看'+period+'原始报告'}>PDF</a>}</th>})}</tr></thead><tbody>
    {visibleRows.map((row,index)=><tr key={row.uiKey??row.key+'-'+index} className={row.section?'enterprise-section-row':row.bold?'finance-total':''}>
     <th style={{paddingLeft:12+row.depth*14}} title={[row.description,row.formula].filter(Boolean).join('\n')}>
      {row.hasChildren&&<button className="enterprise-row-toggle" aria-label={(collapsedRows.has(row.uiKey??row.key)?'展开':'收起')+row.label} aria-expanded={!collapsedRows.has(row.uiKey??row.key)} onClick={()=>toggleRow(row.uiKey??row.key)}>{collapsedRows.has(row.uiKey??row.key)?'+':'−'}</button>}
      {row.label}{row.unit&&!(row.unit in unitPowers)&&!row.label.includes(row.unit)&&!(row.unit==='元/股'&&/[（(]元[）)]/.test(row.label))&&`(${row.unit})`}
      {module.module_key==='main_indicators'&&!row.section&&/^\d+(?:_\d+)?$/.test(row.key)&&<button className="enterprise-trend-trigger" aria-label={row.label+'指标趋势图'} onClick={()=>setTrendKey(row.key)}><svg width="15" height="15" viewBox="0 0 15 15" aria-hidden="true"><path d="M2 13h12M4 10V7M8 10V4M12 10V1" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg></button>}
      {module.category==='statements'&&!row.section&&/^\d+$/.test(row.key)&&original.kind==='matrix'&&original.rows.filter(item=>item.key===row.key).length===1&&row.values.some(value=>value!==null&&value!==undefined&&value!=='')&&<button className="enterprise-trend-trigger" aria-label={row.label+'指标趋势图'} onClick={()=>setTrendKey(row.key)}><svg width="15" height="15" viewBox="0 0 15 15" aria-hidden="true"><path d="M2 13h12M4 10V7M8 10V4M12 10V1" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg></button>}
      <IndicatorHelp row={row}/>
     </th>
     {row.values.map((value,column)=>{const source=enterpriseSourceLink(value),cellUnit=enterpriseCellUnit(view.rows,row,column);return <td key={column} className={/^-/ .test(String(value))?'reference-negative':''} title={value==null?'原文空值':'原值：'+String(value)+' '+cellUnit}>{source?<a href={source.href} target="_blank" rel="noopener noreferrer">{source.label}</a>:enterpriseDisplayValue(value,cellUnit,unit,decimals)||(row.section?'':'-')}</td>})}
    </tr>)}
   </tbody></table>
   {!view.periods.length&&<p className="finance-empty">当前筛选无已导入期间。</p>}
  </div>:view.kind==='records'?<div className="finance-table-scroll enterprise-record-table">
   {groupEnterpriseRecordTables(view.tables).map((group,index)=><table key={group[0].title+index} className="finance-matrix"><thead><tr>{group[0].headers.map((header,i)=><th key={i}>{header}</th>)}</tr></thead><tbody>
    {group.map((table,section)=><React.Fragment key={table.title+section}>
     {/^\d{4}年/.test(table.title)&&<tr className="enterprise-section-row"><th colSpan={table.headers.length}>{table.title}</th></tr>}
     {table.rows.map((row,i)=><tr key={i} className={row[0]==='合计'?'finance-total':''}>{row.map((value,j)=>j===0?<th key={j}>{text(value)}</th>:<td key={j} title={preciseRecord&&value!=null?'原值：'+text(value)+' '+(/[％%]/.test(table.headers[j])?'%':String(module.request_params?.unit||'')):undefined}>{enterpriseDisplayRecordValue(value,table.headers[j]||'',String(module.request_params?.unit||''),unit,decimals,preciseRecord)||'-'}</td>)}</tr>)}
    </React.Fragment>)}
   </tbody></table>)}
   {!view.tables.length&&<p className="finance-empty">当前筛选无已导入期间。</p>}
  </div>:<p className="finance-empty">{view.unavailable?'企业预警通原站当前禁用此栏目，未计入数据采集成功项。':view.confirmed?'企业预警通该栏目暂无数据':'当前栏目数据尚待核对'}</p>}
  <details className="enterprise-source-details"><summary>数据来源与采集口径</summary><p>{module.module_name} · {module.endpoint_path}</p><p>报告期、报表类型及币种范围以当前已导入数据为准。筛选和显示换算不修改来源原值。</p><p className="finance-hash">{module.response_sha256}</p></details>
  {trendKey&&original.kind==='matrix'&&(module.module_key==='main_indicators'?<EnterpriseIndicatorTrend view={original} rowKey={trendKey} module={module} projectId={projectId} filter={{start,end,windowYears,currency,rate}} onClose={()=>setTrendKey('')}/>:module.category==='statements'?<EnterpriseStatementTrend view={original} rowKey={trendKey} module={module} projectId={projectId} filter={{start,end,windowYears,currency,rate}} displayUnit={unit} onClose={()=>setTrendKey('')}/>:null)}
 </div>;
}
