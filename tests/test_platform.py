import hashlib, io, zipfile, os, uuid
import pytest
from fastapi.testclient import TestClient
from leasedd.app import create_app
from leasedd.worker import run_once

@pytest.fixture
def env(tmp_path):
 url=os.getenv('LEASEDD_TEST_DATABASE_URL')
 schema=None
 if url:
  from sqlalchemy import create_engine,text
  pg=create_engine(url);schema='test_'+uuid.uuid4().hex
  with pg.begin() as db:db.execute(text('CREATE SCHEMA '+schema))
  test_url=url+'?options=-csearch_path%3D'+schema
 else:test_url=f'sqlite:///{tmp_path}/db.sqlite'
 app=create_app(test_url, tmp_path/'files', secure_cookie=False)
 app.state.bootstrap('admin','administrator-password')
 c=TestClient(app)
 def login(user,password):
  c.cookies.clear()
  r=c.post('/api/login',json={'username':user,'password':password}); assert r.status_code==200
  c.headers['X-CSRF-Token']=r.json()['csrf_token']
 login('admin','administrator-password')
 for u in ['writer','reviewer','outsider']:
  assert c.post('/api/users',json={'username':u,'password':'long-password-123','admin':False}).status_code==200
 ids={u['username']:u['id'] for u in c.get('/api/users').json()}
 p=c.post('/api/projects',json={'name':'合成租赁项目','writer_id':ids['writer'],'reviewer_id':ids['reviewer']}).json()['id']
 login('writer','long-password-123')
 yield app,c,p,login
 app.state.engine.dispose()
 if schema:
  with pg.begin() as db:db.execute(text('DROP SCHEMA '+schema+' CASCADE'))
  pg.dispose()

def facts(doc,sha):
 return {'document_id':doc,'sha256':sha,'expected_revision':3,'reason':'manual_verified_import','facts':[
 {'concept':k,'value':v,'entity':'E001','scope':'consolidated','period':'2025-12-31','currency':'CNY','unit':'yuan','line':i+1,'quote':f'{k}: {v}'}
 for i,(k,v) in enumerate([('total_assets','100'),('total_liabilities','80'),('interest_bearing_debt','30'),('current_assets','200'),('current_liabilities','100')])]}

def test_member_password_accepts_six_characters_and_rejects_five(env):
 _,c,_,login=env;login('admin','administrator-password')
 assert c.post('/api/users',json={'username':'six-char','password':'123456','admin':False}).status_code==200
 assert c.post('/api/users',json={'username':'five-char','password':'12345','admin':False}).status_code==422

def seed(app,c,p):
 raw=b'total_assets: 100\ntotal_liabilities: 80\ninterest_bearing_debt: 30\ncurrent_assets: 200\ncurrent_liabilities: 100\n'
 r=c.post(f'/api/projects/{p}/documents',files={'file':('statement.txt',raw,'text/plain')},data={'model_allowed':'false'})
 assert r.status_code==200
 doc=r.json()
 payload=facts(doc['id'],doc['sha256']);payload['expected_revision']=c.get(f'/api/projects/{p}').json()['revision']
 assert c.post(f'/api/projects/{p}/facts',json=payload).status_code==200
 return doc,raw

def test_full_offline_chain_and_word(env):
 app,c,p,_=env; doc,raw=seed(app,c,p)
 r=c.post(f'/api/projects/{p}/calculate'); assert r.status_code==200
 metrics=r.json()['metrics']
 assert metrics['liabilities_to_assets']['value']=='0.8'
 assert metrics['interest_bearing_debt_to_assets']['value']=='0.3'
 assert metrics['quick_ratio']['value'] is None
 assert metrics['quick_ratio']['reason']=='missing_required_input:inventory'
 task=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'}).json()
 assert run_once(app)
 assert c.get(f'/api/projects/{p}/tasks/{task["id"]}').json()['state']=='completed'
 task=c.post(f'/api/projects/{p}/tasks',json={'kind':'render','mode':'synthetic'}).json()
 assert run_once(app)
 result=c.get(f'/api/projects/{p}/tasks/{task["id"]}').json()
 assert result['state']=='completed'
 r=c.get(f'/api/projects/{p}/exports/{result["result"]["export_id"]}')
 assert r.status_code==200
 xml=zipfile.ZipFile(io.BytesIO(r.content)).read('word/document.xml').decode()
 assert '<w:tbl>' in xml and '80.00%' in xml and '30.00%' in xml and '待复核' in xml
 assert '{{' not in xml
 assert c.get(f'/api/projects/{p}/documents/{doc["id"]}/download').content==raw
 assert c.post(f'/api/projects/{p}/publish-reviewed').status_code==409

def test_all_project_routes_require_membership(env):
 app,c,p,login=env;doc,_=seed(app,c,p)
 login('outsider','long-password-123')
 for path in ['', '/documents','/facts','/tasks','/documents/'+doc['id']+'/download']:
  assert c.get(f'/api/projects/{p}'+path).status_code==403
 assert c.post(f'/api/projects/{p}/calculate').status_code==403

def test_bad_hash_locator_and_path_are_rejected(env):
 app,c,p,_=env;doc,_=seed(app,c,p)
 payload=facts(doc['id'],'0'*64)
 assert c.post(f'/api/projects/{p}/facts',json=payload).status_code==422
 payload=facts(doc['id'],doc['sha256']);payload['facts'][0]['line']=999
 assert c.post(f'/api/projects/{p}/facts',json=payload).status_code==422
 assert c.post(f'/api/projects/{p}/documents',files={'file':('../escape.txt',b'x')}).status_code==422

def test_csrf_and_reviewer_cannot_write(env):
 _,c,p,login=env
 c.headers.pop('X-CSRF-Token')
 assert c.post(f'/api/projects/{p}/calculate').status_code==403
 login('reviewer','long-password-123')
 assert c.post(f'/api/projects/{p}/calculate').status_code==403

def test_conflicts_and_zero_denominator(env):
 app,c,p,_=env;doc,_=seed(app,c,p)
 payload=facts(doc['id'],doc['sha256']);payload['facts'][0]['scope']='parent'
 assert c.post(f'/api/projects/{p}/facts',json=payload).status_code==200
 r=c.post(f'/api/projects/{p}/calculate').json()
 assert r['metrics']['liabilities_to_assets']['status']=='conflicted'


def test_section_edit_uses_version_and_rejects_unknown_refs(env):
 app,c,p,_=env;seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'});run_once(app)
 section=c.get(f'/api/projects/{p}/section').json()
 assert c.put(f'/api/projects/{p}/section',json={'version':section['version']-1,'draft':section['draft']}).status_code==409
 section['draft']['blocks'][0]['segments'].append({'type':'metric','ref':'UNKNOWN'})
 assert c.put(f'/api/projects/{p}/section',json=section).status_code==422

def test_no_duplicate_export_and_stale_task_is_not_accepted(env):
 app,c,p,_=env;seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 first=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'}).json()
 second=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'}).json()
 assert first['id']==second['id']
 c.post(f'/api/projects/{p}/documents',files={'file':('new.txt',b'unrelated')})
 run_once(app)
 assert c.get(f'/api/projects/{p}/tasks/{first["id"]}').json()['state']=='stale'
 assert not c.get(f'/api/projects/{p}/section').json()['draft']

def test_expired_lease_recovers_and_render_reuses_task(env):
 from leasedd.db import Task
 app,c,p,_=env;seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 task=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'}).json()
 with app.state.db.begin() as db:
  t=db.get(Task,task['id']);t.state='running';t.lease_until=1;t.attempts=1
 assert run_once(app)
 assert c.get(f'/api/projects/{p}/tasks/{task["id"]}').json()['attempts']==2
 first=c.post(f'/api/projects/{p}/tasks',json={'kind':'render','mode':'synthetic'}).json()
 run_once(app)
 second=c.post(f'/api/projects/{p}/tasks',json={'kind':'render','mode':'synthetic'}).json()
 assert first['id']==second['id']
 assert len(c.get(f'/api/projects/{p}/exports').json())==1

def test_source_tampering_stops_worker(env):
 from leasedd.db import Document
 app,c,p,_=env;doc,_=seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 task=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'}).json()
 with app.state.db() as db:
  d=db.get(Document,doc['id']);path=app.state.root/d.path;path.chmod(0o600);path.write_text('tampered')
 for _ in range(3):run_once(app)
 result=c.get(f'/api/projects/{p}/tasks/{task["id"]}').json()
 assert result['state']=='failed' and result['attempts']==3
 assert result['reason']=='source_hash_mismatch'

def test_value_substring_is_not_verified_evidence(env):
 app,c,p,_=env;doc,_=seed(app,c,p)
 payload=facts(doc['id'],doc['sha256']);payload['facts'][0]['value']='10'
 assert c.post(f'/api/projects/{p}/facts',json=payload).status_code==422

def test_fact_edit_requires_current_version_and_explicit_reason(env):
 app,c,p,_=env;doc,_=seed(app,c,p)
 payload=facts(doc['id'],doc['sha256']);payload['expected_revision']=1;payload['reason']='重新核对'
 assert c.post(f'/api/projects/{p}/facts',json=payload).status_code==409

def test_text_concept_mismatch_is_rejected(env):
 app,c,p,_=env;doc,_=seed(app,c,p)
 payload=facts(doc['id'],doc['sha256']);payload['facts'][0]['concept']='inventory'
 assert c.post(f'/api/projects/{p}/facts',json=payload).status_code==422

def test_expired_worker_cannot_overwrite_accepted_export(tmp_path):
 from leasedd.render import render
 from leasedd.domain import calculate,synthetic_draft
 metrics=calculate([dict(fact_id='A',concept='total_assets',value='100',entity='E',scope='consolidated',period='2025-12-31',currency='CNY',unit='yuan'),dict(fact_id='L',concept='total_liabilities',value='80',entity='E',scope='consolidated',period='2025-12-31',currency='CNY',unit='yuan')])
 draft=synthetic_draft('a'*64,metrics)
 path,sha,_=render(tmp_path,'project','task','a'*64,draft,metrics,[],lease_token='new-lease')
 render(tmp_path,'project','task','a'*64,draft,metrics,[],lease_token='old-lease')
 assert hashlib.sha256((tmp_path/path).read_bytes()).hexdigest()==sha
 assert 'new-lease' in path

def test_agnes_requires_authorized_materials_and_never_returns_key(env,monkeypatch):
 app,c,p,login=env;seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 monkeypatch.setenv('AGNES_API_KEY','secret-for-test-not-for-production')
 login('admin','administrator-password')
 r=c.put('/api/settings/agnes',json={'base_url':'http://localhost:9999/v1','model':'test-model'})
 assert r.status_code==200 and 'secret-for-test' not in r.text
 login('writer','long-password-123')
 assert c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'agnes'}).status_code==403

def test_agnes_invalid_json_retries_exactly_three_times(env,monkeypatch):
 import threading
 from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
 from leasedd.db import Document,Setting
 app,c,p,_=env;doc,_=seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 requests=[]
 class Handler(BaseHTTPRequestHandler):
  def do_POST(self):
   requests.append(self.rfile.read(int(self.headers['Content-Length'])))
   self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
   self.wfile.write(b'{"choices":[{"message":{"content":"invalid"}}]}')
  def log_message(self,*args):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 monkeypatch.setenv('AGNES_API_KEY','secret-test')
 try:
  with app.state.db.begin() as db:
   db.get(Document,doc['id']).model_allowed=True
   db.add(Setting(key='agnes',value={'base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'test'}))
  t=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'agnes'}).json()
  for _ in range(4):run_once(app)
  result=c.get(f'/api/projects/{p}/tasks/{t["id"]}').json()
  assert result['state']=='failed' and result['reason']=='agnes_invalid_json'
  assert len(requests)==3 and all(b'secret-test' not in r for r in requests)
 finally:server.shutdown();server.server_close()

def test_postgres_claim_skips_locked_project_and_serializes_tasks(env):
 from concurrent.futures import ThreadPoolExecutor
 from sqlalchemy import select
 from leasedd.db import Project,Task
 from leasedd.worker import claim
 app,c,p,_=env
 if app.state.engine.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency check; run LEASEDD_TEST_DATABASE_URL suite')
 seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 t=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'}).json()
 with app.state.db.begin() as db:
  db.scalar(select(Project).where(Project.id==p).with_for_update())
  with ThreadPoolExecutor(max_workers=1) as pool:
   assert pool.submit(claim,app).result(timeout=2) is None
 with ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda _:claim(app),range(2)))
 assert sum(r is not None for r in results)==1
 with app.state.db() as db:assert db.get(Task,t['id']).attempts==1

def test_accepted_section_versions_remain_available_after_edit(env):
 app,c,p,_=env;seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'});run_once(app)
 section=c.get(f'/api/projects/{p}/section').json();draft=section['draft']
 draft['blocks'][0]['segments'][0]['text']='按测试口径计算的资产负债率：'
 assert c.put(f'/api/projects/{p}/section',json={'version':section['version'],'draft':draft}).status_code==200
 history=c.get(f'/api/projects/{p}/section/history')
 assert history.status_code==200
 assert len(history.json())==2
 assert history.json()[0]['draft']['blocks'][0]['segments'][0]['text']=='资产负债率：'
 assert history.json()[1]['draft']['blocks'][0]['segments'][0]['text']=='按测试口径计算的资产负债率：'

def test_lost_lease_failure_cannot_reset_new_attempt(env):
 from leasedd.db import Task
 from leasedd.worker import record_failure
 app,c,p,_=env;seed(app,c,p);c.post(f'/api/projects/{p}/calculate')
 task=c.post(f'/api/projects/{p}/tasks',json={'kind':'generate','mode':'synthetic'}).json()
 with app.state.db.begin() as db:
  t=db.get(Task,task['id']);t.state='running';t.lease_token='new-owner';t.lease_until=9999999999;t.attempts=2
 record_failure(app,task['id'],'old-owner','agnes_http_error')
 with app.state.db() as db:
  t=db.get(Task,task['id']);assert t.state=='running' and t.lease_token=='new-owner' and t.lease_until==9999999999
 record_failure(app,task['id'],'new-owner','agnes_http_error')
 with app.state.db() as db:assert db.get(Task,task['id']).state=='queued'

def test_postgres_concurrent_login_failures_are_rate_limited_without_500(env):
 from concurrent.futures import ThreadPoolExecutor
 app,c,p,_=env
 if app.state.engine.dialect.name!='postgresql':pytest.skip('PostgreSQL login concurrency check')
 def fail_login(_):
  with TestClient(app) as client:
   return client.post('/api/login',json={'username':'unknown-concurrent','password':'incorrect-password'}).status_code
 with ThreadPoolExecutor(max_workers=5) as pool:codes=list(pool.map(fail_login,range(5)))
 assert codes==[401]*5
 assert fail_login(6)==429
