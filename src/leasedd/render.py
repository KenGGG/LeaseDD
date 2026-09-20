import hashlib,json,os,zipfile
from pathlib import Path
from docx import Document
from docxtpl import DocxTemplate
from .domain import METRICS,metric_display,section_text,reason_text
from .contracts import RunManifest


def render(root,pid,task_id,input_hash,draft,metrics,facts,lease_token):
    directory=root/pid/'exports'/task_id/lease_token;directory.mkdir(parents=True,exist_ok=True)
    template=directory/'synthetic_template.docx'
    if not template.exists():
        import shutil
        shutil.copyfile(Path(__file__).parent/'assets'/'synthetic_template.docx',template)
        template.chmod(0o440)
    template_sha=hashlib.sha256(template.read_bytes()).hexdigest()
    rows=[{'label':label,'value':metric_display(key,metrics[key]),'reason':reason_text(metrics[key]['reason']) if metrics[key]['reason'] else '同主体、同范围、同一时点；测试口径'} for key,label in METRICS.items()]
    sources='\n'.join(f"{f['concept']} ← 文档 {f['document_id']} 第 {f['line']} 行；{f['entity']}／{f['scope']}／{f['period']}／{f['unit']}" for f in facts)
    tpl=DocxTemplate(template)
    tpl.render({'title':draft['title'],'paragraphs':'\n'.join(section_text(draft,metrics)),'rows':rows,'sources':sources},autoescape=True)
    temp=directory/'report.tmp.docx';output=directory/'report_review.docx'
    tpl.save(temp)
    with zipfile.ZipFile(temp) as z:
        xml=z.read('word/document.xml').decode()
        if '<w:tbl>' not in xml or '{{' in xml or '{%' in xml:raise ValueError('word_structure_invalid')
    if hashlib.sha256(template.read_bytes()).hexdigest()!=template_sha:raise ValueError('template_changed')
    sha=hashlib.sha256(temp.read_bytes()).hexdigest()
    manifest=RunManifest(run_id=task_id,project_id=pid,input_hash=input_hash,output_sha256=sha,execution_state='completed',quality_state='passed_with_gaps' if any(m['value'] is None for m in metrics.values()) else 'passed',template_sha256=template_sha).model_dump()
    with temp.open('rb') as f:os.fsync(f.fileno())
    temp.replace(output)
    manifest_temp=directory/'artifact_manifest.tmp.json'
    with manifest_temp.open('w') as f:
        json.dump(manifest,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    manifest_temp.replace(directory/'artifact_manifest.json')
    return str(output.relative_to(root)),sha,manifest
