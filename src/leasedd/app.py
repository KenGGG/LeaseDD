import hashlib, os, secrets, time, re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, delete
from .db import Base, database, User, LoginSession, Project, Member, Document, DocumentConversion, ExtractionRun, FinancialStatement, FinancialItem, FactBatch, Task, Export, Audit, Setting, SectionRevision, EnterpriseBinding, EnterpriseImport, EnterpriseFinancialData, uid
from .security import password_hash, verify_password, token_hash
from .contracts import Login, CreateUser, CreateProject, FactImport, CreateTask, BatchRecognition, SectionEdit, AgnesSettings, FinancialItemDecision, EnterpriseImportRequest
from .domain import facts_snapshot, snapshot_hash, calculate, validate_draft, metric_display

MAX_FILE=20*1024*1024

def create_app(database_url=None, data_dir=None, secure_cookie=True, initialize=True):
    engine, factory=database(database_url or os.getenv('LEASEDD_DATABASE_URL','sqlite:///runtime/dev.sqlite'))
    root=Path(data_dir or os.getenv('LEASEDD_DATA_DIR','runtime/files')).resolve()
    root.mkdir(parents=True,exist_ok=True)
    if initialize: Base.metadata.create_all(engine)
    app=FastAPI(title='LeaseDD',version='0.1.0')
    app.state.engine=engine;app.state.db=factory;app.state.root=root

    def bootstrap(username,password):
        if len(password)<12: raise ValueError('bootstrap_password_too_short')
        with factory.begin() as db:
            if db.scalar(select(User.id).limit(1)): return
            db.add(User(username=username,password_hash=password_hash(password),admin=True))
    app.state.bootstrap=bootstrap

    def session():
        with factory() as db:
            yield db

    def current(request:Request,db=Depends(session)):
        token=request.cookies.get('leasedd_session','')
        sess=db.get(LoginSession,token_hash(token)) if token else None
        if not sess or sess.expires<time.time(): raise HTTPException(401,'authentication_required')
        user=db.get(User,sess.user_id)
        if not user or not user.active: raise HTTPException(401,'authentication_required')
        if request.method not in ('GET','HEAD','OPTIONS') and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),sess.csrf):
            raise HTTPException(403,'csrf_failed')
        return user

    def admin(user=Depends(current)):
        if not user.admin: raise HTTPException(403,'admin_required')
        return user

    def project(db,project_id,user,write=False,lock=False):
        p=db.scalar(select(Project).where(Project.id==project_id).with_for_update()) if lock else db.get(Project,project_id)
        if not p: raise HTTPException(404,'project_not_found')
        member=db.scalar(select(Member).where(Member.project_id==project_id,Member.user_id==user.id))
        if not member: raise HTTPException(403,'project_membership_required')
        if write and member.role!='writer': raise HTTPException(403,'writer_required')
        return p

    def audit(db,user,action,pid=None,details=None):
        db.add(Audit(user_id=user.id,project_id=pid,action=action,details=details or {},created_at=time.time()))

    def state(p):
        quality='not_checked' if p.metrics_revision!=p.revision else ('passed_with_gaps' if any(m['value'] is None for m in p.metrics.values()) else 'passed')
        return {'execution_state':'completed','quality_state':quality,'review_state':'pending','export_eligibility':'review_only'}

    def project_view(p):
        return {'id':p.id,'name':p.name,'revision':p.revision,'metrics':p.metrics,'metrics_current':p.metrics_revision==p.revision,'section_current':p.section_revision==p.revision and bool(p.section),'production_template_status':p.production_template_status,'synthetic':True,**state(p)}

    def doc_view(d):
        return {'id':d.id,'name':d.name,'sha256':d.sha256,'model_allowed':d.model_allowed,'parse_state':d.parse_state}

    def task_view(t):
        return {'id':t.id,'kind':t.kind,'mode':t.mode,'state':t.state,'attempts':t.attempts,'reason':t.reason,'result':t.result,'execution_state':t.state,'quality_state':t.result.get('quality_state','not_checked'),'review_state':'pending'}

    @app.middleware('http')
    async def boundaries(request,call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            allowed=os.getenv('LEASEDD_PUBLIC_ORIGIN')
            if origin and origin!=(allowed or str(request.base_url).rstrip('/')):
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'origin_not_allowed'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Cache-Control']='no-store'
        return response

    @app.get('/api/health')
    def health():
        return {'status':'ok','version':'0.1.0','production_ready':False}

    @app.post('/api/login')
    def login(payload:Login,request:Request,db=Depends(session)):
        # Limit password guesses per username using an atomic database row lock.
        key='login:'+hashlib.sha256(payload.username.encode()).hexdigest()[:24]
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert=pg_insert if engine.dialect.name=='postgresql' else sqlite_insert
        # Upsert obtains a row lock even on the first concurrent attempts.
        statement=insert(Setting).values(key=key,value={'count':0,'window':0,'until':0})
        db.execute(statement.on_conflict_do_update(index_elements=['key'],set_={'key':key}))
        limiter=db.scalar(select(Setting).where(Setting.key==key).with_for_update())
        now=time.time()
        if limiter and limiter.value.get('until',0)>now: raise HTTPException(429,'login_rate_limited')
        user=db.scalar(select(User).where(User.username==payload.username,User.active==True))
        valid=verify_password(payload.password,user.password_hash if user else app.state.dummy_hash)
        if not user or not valid:
            old=limiter.value if limiter else {}
            count=old.get('count',0)+1 if old.get('window',0)>now-300 else 1
            val={'count':count,'window':old.get('window',now) if count>1 else now,'until':now+300 if count>=5 else 0}
            if limiter: limiter.value=val
            else: db.add(Setting(key=key,value=val))
            db.commit();raise HTTPException(401,'invalid_credentials')
        if limiter: db.delete(limiter)
        token=secrets.token_urlsafe(32);csrf=secrets.token_hex(32)
        db.add(LoginSession(token_hash=token_hash(token),user_id=user.id,csrf=csrf,expires=now+28800))
        audit(db,user,'login');db.commit()
        from fastapi.responses import JSONResponse
        response=JSONResponse({'id':user.id,'username':user.username,'admin':user.admin,'csrf_token':csrf})
        response.set_cookie('leasedd_session',token,httponly=True,secure=secure_cookie,samesite='strict',max_age=28800)
        return response

    app.state.dummy_hash=password_hash(secrets.token_urlsafe(32))

    @app.get('/api/me')
    def me(request:Request,user=Depends(current),db=Depends(session)):
        sess=db.get(LoginSession,token_hash(request.cookies['leasedd_session']))
        return {'id':user.id,'username':user.username,'admin':user.admin,'csrf_token':sess.csrf}

    @app.post('/api/logout')
    def logout(request:Request,user=Depends(current),db=Depends(session)):
        db.execute(delete(LoginSession).where(LoginSession.token_hash==token_hash(request.cookies['leasedd_session'])));db.commit()
        from fastapi.responses import JSONResponse
        r=JSONResponse({'ok':True});r.delete_cookie('leasedd_session');return r

    @app.get('/api/users')
    def users(user=Depends(admin),db=Depends(session)):
        return [{'id':u.id,'username':u.username,'admin':u.admin} for u in db.scalars(select(User).order_by(User.username))]

    @app.post('/api/users')
    def add_user(payload:CreateUser,user=Depends(admin),db=Depends(session)):
        if db.scalar(select(User.id).where(User.username==payload.username)):raise HTTPException(409,'username_exists')
        u=User(username=payload.username,password_hash=password_hash(payload.password),admin=payload.admin);db.add(u);db.flush()
        audit(db,user,'create_user',details={'user_id':u.id});db.commit()
        return {'id':u.id,'username':u.username}

    @app.get('/api/settings/agnes')
    def agnes_get(user=Depends(admin),db=Depends(session)):
        s=db.get(Setting,'agnes')
        return {**(s.value if s else {'base_url':'','model':''}),'credential_configured':bool(os.getenv('AGNES_API_KEY'))}

    @app.put('/api/settings/agnes')
    def agnes_put(payload:AgnesSettings,user=Depends(admin),db=Depends(session)):
        s=db.get(Setting,'agnes')
        if s:s.value=payload.model_dump()
        else:db.add(Setting(key='agnes',value=payload.model_dump()))
        audit(db,user,'configure_agnes');db.commit()
        return {'saved':True,'credential_configured':bool(os.getenv('AGNES_API_KEY'))}

    @app.get('/api/projects')
    def projects(user=Depends(current),db=Depends(session)):
        return [project_view(p) for p in db.scalars(select(Project).join(Member).where(Member.user_id==user.id).order_by(Project.name))]

    @app.post('/api/projects')
    def add_project(payload:CreateProject,user=Depends(admin),db=Depends(session)):
        if payload.writer_id==payload.reviewer_id:raise HTTPException(422,'independent_reviewer_required')
        if not all(db.get(User,i) for i in [payload.writer_id,payload.reviewer_id]):raise HTTPException(422,'unknown_member')
        p=Project(name=payload.name);db.add(p);db.flush()
        db.add_all([Member(project_id=p.id,user_id=payload.writer_id,role='writer'),Member(project_id=p.id,user_id=payload.reviewer_id,role='reviewer')])
        audit(db,user,'create_project',p.id);db.commit();return project_view(p)

    @app.get('/api/projects/{pid}')
    def get_project(pid:str,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user); members=db.scalars(select(Member).where(Member.project_id==pid)).all()
        return {**project_view(p),'members':[{'user_id':m.user_id,'username':db.get(User,m.user_id).username,'role':m.role} for m in members]}

    @app.get('/api/projects/{pid}/documents')
    def documents(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        return [doc_view(d) for d in db.scalars(select(Document).where(Document.project_id==pid))]

    @app.post('/api/projects/{pid}/documents')
    def upload(pid:str,file:UploadFile=File(),model_allowed:bool=Form(False),user=Depends(current),db=Depends(session)):
        p=project(db,pid,user,write=True,lock=True)
        name=file.filename or ''
        if not name or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or len(name)>255:raise HTTPException(422,'unsafe_filename')
        doc_id=uid();directory=root/pid/'raw';directory.mkdir(parents=True,exist_ok=True)
        path=directory/doc_id;temp=directory/(doc_id+'.tmp');total=0;sha=hashlib.sha256()
        try:
            with temp.open('xb') as f:
                while chunk:=file.file.read(65536):
                    total+=len(chunk)
                    if total>MAX_FILE:raise HTTPException(413,'file_too_large')
                    sha.update(chunk);f.write(chunk)
                f.flush();os.fsync(f.fileno())
            temp.replace(path);path.chmod(0o440)
        finally:temp.unlink(missing_ok=True)
        parse_state='unsupported_pending'
        if name.lower().endswith(('.txt','.md','.csv')):
            try:path.read_text(encoding='utf-8');parse_state='text_available' if total else 'empty'
            except UnicodeError:parse_state='encoding_pending'
        d=Document(id=doc_id,project_id=pid,name=name,sha256=sha.hexdigest(),path=str(path.relative_to(root)),model_allowed=False,parse_state=parse_state,created_by=user.id)
        db.add(d);p.revision+=1;db.flush()
        # Upload is deliberately passive: the writer chooses when a batch of
        # materials may start conversion and optional model processing.
        audit(db,user,'upload_document',pid,{'document_id':doc_id,'sha256':d.sha256});db.commit()
        return doc_view(d)

    @app.post('/api/projects/{pid}/documents/recognize')
    def recognize_documents(pid:str,payload:BatchRecognition,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user,write=True,lock=True)
        requested=list(dict.fromkeys(payload.document_ids))
        documents={d.id:d for d in db.scalars(select(Document).where(Document.project_id==pid,Document.id.in_(requested)))}
        if len(documents)!=len(requested):raise HTTPException(404,'document_not_found')
        tasks=db.scalars(select(Task).where(Task.project_id==pid,Task.kind=='extract_finance')).all()
        queued=[];skipped=0
        for did in requested:
            d=documents[did]
            previous=[t for t in tasks if t.result.get('document_id')==did]
            if any(t.state in ('queued','running') for t in previous) or (not payload.reprocess and any(t.state=='completed' and t.result.get('statement_count',0)>0 for t in previous)):
                skipped+=1;continue
            d.model_allowed=payload.model_allowed
            task=Task(project_id=pid,kind='extract_finance',mode='auto',input_revision=p.revision,input_hash=d.sha256,result={'document_id':did,'model_allowed':payload.model_allowed},created_by=user.id,created_at=time.time())
            db.add(task);queued.append(task)
        db.flush()
        audit(db,user,'batch_recognize_documents',pid,{'document_ids':requested,'queued_task_ids':[t.id for t in queued],'model_allowed':payload.model_allowed,'reprocess':payload.reprocess})
        db.commit()
        return {'queued':len(queued),'skipped':skipped,'task_ids':[t.id for t in queued]}

    def get_doc(db,pid,did,user):
        project(db,pid,user);d=db.get(Document,did)
        if not d or d.project_id!=pid:raise HTTPException(404,'document_not_found')
        path=(root/d.path).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise HTTPException(409,'source_missing')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=d.sha256:raise HTTPException(409,'source_hash_mismatch')
        return d,path

    @app.get('/api/projects/{pid}/documents/{did}/download')
    def download_doc(pid:str,did:str,user=Depends(current),db=Depends(session)):
        d,path=get_doc(db,pid,did,user);return FileResponse(path,filename=d.name,media_type='application/octet-stream')

    @app.get('/api/projects/{pid}/documents/{did}/evidence')
    def evidence(pid:str,did:str,user=Depends(current),db=Depends(session)):
        d,path=get_doc(db,pid,did,user)
        if d.parse_state!='text_available':raise HTTPException(409,'text_locator_not_supported')
        return {'document_id':did,'sha256':d.sha256,'lines':path.read_text(encoding='utf-8').splitlines()[:10000]}

    def latest_conversion(db,pid,did):
        return db.scalar(select(DocumentConversion).where(DocumentConversion.project_id==pid,DocumentConversion.document_id==did).order_by(DocumentConversion.created_at.desc()))

    @app.get('/api/projects/{pid}/documents/{did}/conversion')
    def conversion_status(pid:str,did:str,user=Depends(current),db=Depends(session)):
        get_doc(db,pid,did,user)
        conversion=latest_conversion(db,pid,did)
        if conversion:
            return {'id':conversion.id,'state':conversion.state,'tool':conversion.tool,'tool_version':conversion.tool_version,'original_sha256':conversion.original_sha256,'markdown_sha256':conversion.markdown_sha256,'error':conversion.error}
        tasks=db.scalars(select(Task).where(Task.project_id==pid,Task.kind=='extract_finance',Task.state.in_(['queued','running'])).order_by(Task.created_at.desc())).all()
        task=next((candidate for candidate in tasks if candidate.result.get('document_id')==did),None)
        return {'id':None,'state':task.state if task else 'not_started','tool':None,'tool_version':None,'original_sha256':None,'markdown_sha256':None,'error':None}

    def conversion_markdown(conversion):
        if not conversion or conversion.state!='completed' or not conversion.markdown_path:raise HTTPException(409,'markdown_not_ready')
        path=(root/conversion.markdown_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise HTTPException(409,'markdown_missing')
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=conversion.markdown_sha256:raise HTTPException(409,'markdown_hash_mismatch')
        return content.decode('utf-8')

    @app.get('/api/projects/{pid}/documents/{did}/markdown')
    def document_markdown(pid:str,did:str,user=Depends(current),db=Depends(session)):
        get_doc(db,pid,did,user);conversion=latest_conversion(db,pid,did);markdown=conversion_markdown(conversion)
        return {'document_id':did,'conversion_id':conversion.id,'markdown_sha256':conversion.markdown_sha256,'markdown':markdown}

    def financial_item_view(item):
        return {'id':item.id,'concept':item.concept,'source_name':item.source_name,'raw_value':item.raw_value,'raw_unit':item.raw_unit,'normalized_value':item.normalized_value,'source_text':item.source_text,'source_start_line':item.source_start_line,'source_end_line':item.source_end_line,'status':item.status,'evidence':item.evidence or {},'confirmed_by':item.confirmed_by,'confirmed_at':item.confirmed_at,'confirmation_reason':item.confirmation_reason}

    def latest_enterprise_import(db,pid,readable=False):
        query=select(EnterpriseImport).where(EnterpriseImport.project_id==pid)
        if not readable:
            return db.scalar(query.join(Task,Task.id==EnterpriseImport.task_id).order_by(Task.created_at.desc()))
        if readable:
            query=query.where(EnterpriseImport.state.in_(['completed','partial']))
            query=query.order_by((EnterpriseImport.state=='completed').desc())
        binding=db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id==pid))
        for record in db.scalars(query.order_by(EnterpriseImport.completed_at.desc(),EnterpriseImport.started_at.desc())):
            if not binding:return record
            task=db.get(Task,record.task_id)
            code=(task.result or {}).get('company_code') if task else None
            if code is None:
                # Legacy imports retain the immutable company code in their
                # captured financial request, never in the mutable binding.
                codes=set()
                for params in db.scalars(select(EnterpriseFinancialData.request_params).where(EnterpriseFinancialData.import_id==record.id)):
                    value=(params or {}).get('code')
                    if isinstance(value,list):value=value[0] if len(value)==1 else None
                    if value:codes.add(str(value))
                code=next(iter(codes)) if len(codes)==1 else None
            if code==binding.company_code:return record
        return None

    def enterprise_status_view(db,pid):
        binding=db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id==pid))
        record=latest_enterprise_import(db,pid)
        return {'source_type':'enterprise_warning' if binding else None,
                'binding':None if not binding else {'company_code':binding.company_code,'company_name':binding.company_name,'identity':binding.identity},
                'import':None if not record else {'id':record.id,'state':record.state,'quality_state':record.quality_state,
                    'module_status':record.module_status,'content_sha256':record.content_sha256,'started_at':record.started_at,'completed_at':record.completed_at}}

    @app.get('/api/projects/{pid}/enterprise')
    def enterprise_status(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        return enterprise_status_view(db,pid)

    @app.post('/api/projects/{pid}/enterprise/import')
    def enterprise_import(pid:str,payload:EnterpriseImportRequest,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user,lock=True)
        binding=db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id==pid))
        if not payload.company_code:
            admin(user);project(db,pid,user,write=True)
            collector=getattr(app.state,'enterprise_collector',None)
            if collector is None:
                from .enterprise_warning import QyjCollector
                collector=QyjCollector();app.state.enterprise_collector=collector
            candidates=collector.search(payload.query or p.name)
            return {'candidates':[{'code':item.code,'name':item.name,'identity':item.identity} for item in candidates]}
        rebinding=not binding or (binding.company_code,binding.company_name)!=(payload.company_code,payload.company_name)
        if rebinding:
            admin(user);project(db,pid,user,write=True)
        active=db.scalar(select(Task).where(Task.project_id==pid,Task.kind=='enterprise_import',Task.state.in_(['queued','running'])))
        if active and binding and binding.company_code!=payload.company_code:
            raise HTTPException(409,'enterprise_import_in_progress')
        if not binding:
            binding=EnterpriseBinding(project_id=pid,company_code=payload.company_code,company_name=payload.company_name,
                                      identity={},created_by=user.id,created_at=time.time());db.add(binding);db.flush()
        elif rebinding:
            binding.company_code=payload.company_code;binding.company_name=payload.company_name
        if rebinding:audit(db,user,'bind_enterprise',pid,{'company_code':payload.company_code})
        from .enterprise_import import enqueue_enterprise_import
        task,_=enqueue_enterprise_import(db,p,binding,user)
        audit(db,user,'enqueue_enterprise_import',pid,{'task_id':task.id});db.commit()
        return task_view(task)

    @app.post('/api/projects/{pid}/enterprise/retry')
    def enterprise_retry(pid:str,user=Depends(admin),db=Depends(session)):
        admin(user);p=project(db,pid,user,write=True,lock=True)
        binding=db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id==pid))
        record=latest_enterprise_import(db,pid)
        if not binding or not record:raise HTTPException(409,'enterprise_import_missing')
        failed=[key for key,value in (record.module_status or {}).items() if value.get('state')=='failed']
        if not failed:
            previous=db.get(Task,record.task_id)
            failed=list((previous.result or {}).get('failed_modules',[])) if previous else []
        if not failed:raise HTTPException(409,'enterprise_import_has_no_failures')
        from .enterprise_import import enqueue_enterprise_import
        task,_=enqueue_enterprise_import(db,p,binding,user,failed_modules=failed)
        audit(db,user,'retry_enterprise_import',pid,{'task_id':task.id,'modules':failed});db.commit()
        return task_view(task)

    @app.get('/api/projects/{pid}/enterprise/data')
    def enterprise_data(pid:str,category:str|None=None,module_key:str|None=None,export_format:str|None=None,
                        summary_only:bool=False,import_id:str='',window_years:int=0,trend_key:str='',
                        report:str='all',start:str='',end:str='',descending:bool=True,hide_empty:bool=True,
                        unit:str='万元',decimals:int=2,expected_hash:str='',scopes:str='',data_kinds:str='',currency:str='',rate:str='',user=Depends(current),db=Depends(session)):
        project(db,pid,user);record=latest_enterprise_import(db,pid,readable=True)
        if import_id and (not record or import_id!=record.id):raise HTTPException(409,'enterprise_source_changed')
        if not record:
            if export_format is not None:raise HTTPException(404,'enterprise_data_not_found')
            return {'import_id':None,'modules':[]}
        query=select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id==record.id)
        if category:query=query.where(EnterpriseFinancialData.category==category)
        if module_key:query=query.where(EnterpriseFinancialData.module_key==module_key)
        if summary_only and export_format is None:
            fields=('category','module_key','module_name','module_order','endpoint_path','request_params',
                    'response_sha256','state','error','collected_at')
            summaries=db.execute(query.with_only_columns(*(getattr(EnterpriseFinancialData,key) for key in fields))
                                 .order_by(EnterpriseFinancialData.module_order)).mappings().all()
            return {'import_id':record.id,'modules':[dict(row) for row in summaries]}
        rows=db.scalars(query.order_by(EnterpriseFinancialData.module_order)).all()
        if expected_hash and (len(rows)!=1 or expected_hash!=rows[0].response_sha256):raise HTTPException(409,'enterprise_source_changed')
        if export_format is not None:
            if export_format!='xlsx' or not module_key or len(rows)!=1:raise HTTPException(400,'invalid_export_options')
            from .enterprise_export import export_enterprise_workbook,select_currency_variant
            from urllib.parse import quote
            try:
                selected=select_currency_variant(rows[0],currency,rate)
                content=export_enterprise_workbook(selected,report=report,start=start,end=end,descending=descending,hide_empty=hide_empty,unit=unit,decimals=decimals,scopes=scopes,data_kinds=data_kinds,window_years=window_years,trend_key=trend_key)
            except ValueError as error:
                raise HTTPException(400,'invalid_export_options') from error
            filename=re.sub(r'[\\/:*?"<>|\r\n]','_',rows[0].module_name or module_key)+'.xlsx'
            return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename),'Cache-Control':'private, no-store'})
        return {'import_id':record.id,'modules':[{'category':row.category,'module_key':row.module_key,'module_name':row.module_name,
            'module_order':row.module_order,'endpoint_path':row.endpoint_path,'request_params':row.request_params,
            'raw_payload':row.raw_payload,'parsed_payload':row.parsed_payload,'response_sha256':row.response_sha256,
            'state':row.state,'error':row.error,'collected_at':row.collected_at} for row in rows]}

    @app.get('/api/projects/{pid}/financial-statements')
    def financial_statements(pid:str,run_id:str='',user=Depends(current),db=Depends(session)):
        from .financial_presentation import source_layout, align_balance_period
        project(db,pid,user)
        if not run_id:
            binding=db.scalar(select(EnterpriseBinding).where(EnterpriseBinding.project_id==pid))
            record=latest_enterprise_import(db,pid,readable=True) if binding else None
            if record:
                from .enterprise_views import enterprise_statement_views
                rows=db.scalars(select(EnterpriseFinancialData).where(EnterpriseFinancialData.import_id==record.id,EnterpriseFinancialData.category=='statements').order_by(EnterpriseFinancialData.module_order)).all()
                return enterprise_statement_views(record,rows)
        if run_id:
            run=db.get(ExtractionRun,run_id)
            if not run or run.project_id!=pid:raise HTTPException(404,'financial_extraction_not_found')
            statements=db.scalars(select(FinancialStatement).where(FinancialStatement.project_id==pid,FinancialStatement.run_id==run_id).order_by(FinancialStatement.entity,FinancialStatement.statement_type,FinancialStatement.period)).all()
            active_runs={run.document_id:run}
        else:
            runs=db.scalars(select(ExtractionRun).where(ExtractionRun.project_id==pid,ExtractionRun.state=='completed').order_by(ExtractionRun.created_at.desc())).all()
            active_runs={}
            for run in runs:
                if run.document_id not in active_runs and db.scalar(select(FinancialStatement.id).where(FinancialStatement.run_id==run.id).limit(1)):
                    active_runs[run.document_id]=run
            run_ids=[run.id for run in active_runs.values()]
            conditions=[FinancialStatement.run_id.in_(run_ids)] if run_ids else []
            legacy_docs=set(db.scalars(select(FinancialStatement.document_id).where(FinancialStatement.project_id==pid,FinancialStatement.run_id==None)))
            legacy_docs-=set(active_runs)
            if legacy_docs:conditions.append((FinancialStatement.run_id==None)&FinancialStatement.document_id.in_(legacy_docs))
            from sqlalchemy import or_
            statements=db.scalars(select(FinancialStatement).where(FinancialStatement.project_id==pid,or_(*conditions)).order_by(FinancialStatement.entity,FinancialStatement.statement_type,FinancialStatement.period)).all() if conditions else []
        diagnostic_indexes={}
        for run in active_runs.values():
            index={}
            for table in (run.manifest or {}).get('tables',[]):
                for diagnostic in table.get('statement_diagnostics',[]):
                    if diagnostic.get('statement_key'):index[diagnostic['statement_key']]=diagnostic
            diagnostic_indexes[run.id]=index
        layouts={};result=[]
        for s in statements:
            if s.conversion_id not in layouts:
                layouts[s.conversion_id]=source_layout(conversion_markdown(db.get(DocumentConversion,s.conversion_id)))
            items=[]
            for item in db.scalars(select(FinancialItem).where(FinancialItem.statement_id==s.id).order_by(FinancialItem.concept)):
                value=financial_item_view(item)
                matches=[entry for entry in layouts[s.conversion_id].get(item.source_text,[]) if entry['source_start_line']==item.source_start_line]
                if len(matches)==1:
                    value.update({k:v for k,v in matches[0].items() if k!='source_start_line'})
                items.append(value)
            key=next((item.get('evidence',{}).get('statement_key') for item in items if item.get('evidence',{}).get('statement_key')),None)
            diagnostic=diagnostic_indexes.get(s.run_id,{}).get(key,{})
            checks=[]
            for raw in diagnostic.get('checks',[]):
                check=dict(raw)
                involved=set(check.get('involved_concepts',[]))
                check['item_ids']=[item['id'] for item in items if item['concept'] in involved]
                checks.append(check)
            result.append({'id':s.id,'run_id':s.run_id,'document_id':s.document_id,'conversion_id':s.conversion_id,'statement_type':s.statement_type,'entity':s.entity,'scope':s.scope,'period':s.period,'period_normalized':s.period_normalized,'period_kind':s.period_kind,'currency':s.currency,'raw_unit':s.raw_unit,'unit_scale':s.unit_scale,'state':s.state,'issues':s.issues,'items':items,
                'source_status':diagnostic.get('source_status','not_available'),'source_issues':diagnostic.get('source_issues',[]),
                'formula_status':diagnostic.get('formula_status','not_checked'),'checks':checks,
                'semantic_review_count':diagnostic.get('semantic_review_count',0),'manual_review_required':diagnostic.get('manual_review_required',False)})
        result=[align_balance_period(s) for s in result]
        from .financial_supplements import supplementary_statements
        for cid in layouts:
            conversion=db.get(DocumentConversion,cid)
            active=active_runs.get(conversion.document_id)
            if not active or active.pipeline_version!='agnes-semantic-v1':result.extend(supplementary_statements(conversion_markdown(conversion),conversion.document_id,cid,result))
        return result

    @app.get('/api/projects/{pid}/financial-extractions')
    def financial_extractions(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        runs=db.scalars(select(ExtractionRun).where(ExtractionRun.project_id==pid).order_by(ExtractionRun.created_at.desc())).all()
        return [{'id':r.id,'task_id':r.task_id,'document_id':r.document_id,'conversion_id':r.conversion_id,'pipeline_version':r.pipeline_version,'state':r.state,'manifest':r.manifest,'created_at':r.created_at} for r in runs]

    @app.get('/api/projects/{pid}/financial-extractions/runs/{rid}')
    def financial_extraction(pid:str,rid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user);run=db.get(ExtractionRun,rid)
        if not run or run.project_id!=pid:raise HTTPException(404,'financial_extraction_not_found')
        return {'id':run.id,'task_id':run.task_id,'document_id':run.document_id,'conversion_id':run.conversion_id,'pipeline_version':run.pipeline_version,'state':run.state,'manifest':run.manifest,'created_at':run.created_at}

    @app.get('/api/projects/{pid}/financial-analytics')
    def analytics(pid:str,user=Depends(current),db=Depends(session)):
        from .financial_analytics import financial_analytics
        return financial_analytics(financial_statements(pid,user=user,db=db))

    def project_notes(pid,user,db):
        from .financial_notes import index_notes
        from .statement_tables import report_end
        project(db,pid,user)
        conversions=db.scalars(select(DocumentConversion).where(DocumentConversion.project_id==pid).order_by(DocumentConversion.created_at.desc())).all()
        seen=set();notes=[]
        for conversion in conversions:
            if conversion.document_id in seen:continue
            seen.add(conversion.document_id)
            if conversion.state!='completed':continue
            markdown=conversion_markdown(conversion)
            entities={re.sub(r'\s+','',name) for name in re.findall(r'编制单位\s*[:：]\s*([^\n<]+)',markdown)}
            entity=next(iter(entities)) if len(entities)==1 else '未明确主体 · '+conversion.document_id[:8]
            for note in index_notes(markdown,conversion.document_id,conversion.id):
                note['markdown_sha256']=conversion.markdown_sha256
                note['report_end']=report_end(markdown)
                note['entity']=entity
                notes.append(note)
        return notes

    @app.get('/api/projects/{pid}/financial-notes')
    def financial_notes(pid:str,q:str='',user=Depends(current),db=Depends(session)):
        from .financial_notes import CATEGORIES
        notes=project_notes(pid,user,db)
        return {'categories':list(CATEGORIES),'notes':[{k:v for k,v in note.items() if k!='text'} for note in notes if q.casefold() in note['text'].casefold()]}

    @app.get('/api/projects/{pid}/financial-notes-matrix')
    def financial_notes_matrix(pid:str,category:str,scope:str='consolidated',document_id:str='',entity:str='',user=Depends(current),db=Depends(session)):
        from .financial_notes import notes_matrix
        notes=project_notes(pid,user,db)
        if document_id:notes=[n for n in notes if n['document_id']==document_id]
        entities=sorted({n['entity'] for n in notes})
        selected=entity if entity in entities else entities[0] if entities else ''
        return {**notes_matrix([n for n in notes if n['entity']==selected],category,scope),'entities':entities,'entity':selected}

    @app.get('/api/projects/{pid}/financial-notes/{nid}')
    def financial_note(pid:str,nid:str,user=Depends(current),db=Depends(session)):
        from .financial_notes import note_blocks
        note=next((n for n in project_notes(pid,user,db) if n['id']==nid),None)
        if not note:raise HTTPException(404,'financial_note_not_found')
        return {**{k:v for k,v in note.items() if k!='text'},'blocks':note_blocks(note['text']),'lines':note['text'].splitlines()}

    def get_financial_item(db,pid,iid,user,write=False):
        project(db,pid,user,write=write)
        item=db.get(FinancialItem,iid)
        statement=db.get(FinancialStatement,item.statement_id) if item else None
        if not item or not statement or statement.project_id!=pid:raise HTTPException(404,'financial_item_not_found')
        return item,statement

    @app.get('/api/projects/{pid}/financial-items/{iid}/source')
    def financial_item_source(pid:str,iid:str,user=Depends(current),db=Depends(session)):
        if iid.startswith('sup_'):
            for statement in financial_statements(pid,user=user,db=db):
                item=next((i for i in statement['items'] if i['id']==iid),None)
                if item:
                    lines=conversion_markdown(db.get(DocumentConversion,statement['conversion_id'])).splitlines()
                    start,end=item['source_start_line'],item['source_end_line']
                    return {'item_id':iid,'document_id':statement['document_id'],'conversion_id':statement['conversion_id'],'start_line':start,'end_line':end,'lines':lines[start-1:end]}
            raise HTTPException(404,'financial_item_not_found')
        item,statement=get_financial_item(db,pid,iid,user)
        conversion=db.get(DocumentConversion,statement.conversion_id);lines=conversion_markdown(conversion).splitlines()
        start=max(1,item.source_start_line);end=min(len(lines),item.source_end_line)
        return {'item_id':item.id,'document_id':statement.document_id,'conversion_id':conversion.id,'start_line':start,'end_line':end,'lines':lines[start-1:end]}

    @app.post('/api/projects/{pid}/financial-items/{iid}/confirm')
    def confirm_financial_item(pid:str,iid:str,payload:FinancialItemDecision,user=Depends(current),db=Depends(session)):
        item,_=get_financial_item(db,pid,iid,user,write=True)
        if payload.decision=='confirm' and item.status=='source_value_not_found':raise HTTPException(409,'source_value_not_found')
        item.status='human_confirmed' if payload.decision=='confirm' else 'human_rejected'
        item.confirmed_by=user.id;item.confirmed_at=time.time();item.confirmation_reason=payload.reason
        audit(db,user,'confirm_financial_item',pid,{'item_id':item.id,'decision':payload.decision});db.commit()
        return financial_item_view(item)

    @app.get('/api/projects/{pid}/facts')
    def get_facts(pid:str,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user)
        return {'facts':facts_snapshot(db,p),'history':[{'id':b.id,'revision':b.revision,'reason':b.payload.get('reason'),'created_by':b.created_by} for b in db.scalars(select(FactBatch).where(FactBatch.project_id==pid).order_by(FactBatch.revision))]}

    @app.post('/api/projects/{pid}/facts')
    def import_facts(pid:str,payload:FactImport,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user,write=True,lock=True)
        if payload.expected_revision!=p.revision:raise HTTPException(409,'fact_version_conflict')
        d,path=get_doc(db,pid,payload.document_id,user)
        if d.sha256!=payload.sha256 or d.parse_state!='text_available':raise HTTPException(422,'source_hash_or_format_invalid')
        lines=path.read_text(encoding='utf-8').splitlines()
        for f in payload.facts:
            if f.line>len(lines) or f.quote!=lines[f.line-1] or not re.fullmatch(re.escape(f.concept)+r'\s*[:：]\s*'+re.escape(f.value)+r'\s*',f.quote):
                raise HTTPException(422,'invalid_evidence_locator_or_value')
        p.revision+=1
        b=FactBatch(project_id=pid,document_id=d.id,payload=payload.model_dump(mode='json'),revision=p.revision,created_by=user.id,created_at=time.time())
        db.add(b);audit(db,user,'import_facts',pid,{'revision':p.revision,'reason':payload.reason});db.commit()
        return {'revision':p.revision,'count':len(payload.facts),**state(p)}

    @app.post('/api/projects/{pid}/calculate')
    def compute(pid:str,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user,write=True,lock=True)
        # Source hashes are rechecked before using selected facts.
        for f in facts_snapshot(db,p):get_doc(db,pid,f['document_id'],user)
        p.metrics=calculate(facts_snapshot(db,p))
        for key,m in p.metrics.items():m['display_value']=metric_display(key,m)
        p.metrics_revision=p.revision
        audit(db,user,'calculate',pid,{'revision':p.revision});db.commit()
        return {'metrics':p.metrics,**state(p)}

    @app.get('/api/projects/{pid}/section')
    def section(pid:str,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user)
        return {'version':p.section_version,'draft':p.section,'current':p.section_revision==p.revision,'input_hash':snapshot_hash(db,p)}

    @app.get('/api/projects/{pid}/section/history')
    def section_history(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        return [{'version':s.version,'input_revision':s.input_revision,'draft':s.draft,'created_by':s.created_by,'created_at':s.created_at} for s in db.scalars(select(SectionRevision).where(SectionRevision.project_id==pid).order_by(SectionRevision.version))]

    @app.put('/api/projects/{pid}/section')
    def edit_section(pid:str,payload:SectionEdit,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user,write=True,lock=True)
        if payload.version!=p.section_version:raise HTTPException(409,'section_version_conflict')
        if p.section_revision!=p.revision:raise HTTPException(409,'section_stale')
        try:draft=validate_draft(payload.draft.model_dump(exclude_none=True),p.section['input_hash'],p.metrics)
        except ValueError as e:raise HTTPException(422,str(e))
        p.section=draft;p.section_version+=1
        db.add(SectionRevision(project_id=pid,version=p.section_version,input_revision=p.revision,draft=draft,created_by=user.id,created_at=time.time()))
        audit(db,user,'edit_section',pid,{'version':p.section_version});db.commit()
        return {'version':p.section_version,'draft':p.section}

    @app.get('/api/projects/{pid}/tasks')
    def tasks(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        return [task_view(t) for t in db.scalars(select(Task).where(Task.project_id==pid).order_by(Task.created_at.desc()).limit(50))]

    @app.post('/api/projects/{pid}/tasks')
    def enqueue(pid:str,payload:CreateTask,user=Depends(current),db=Depends(session)):
        p=project(db,pid,user,write=True,lock=True)
        if payload.kind=='extract_finance':
            if payload.mode!='auto':raise HTTPException(422,'extract_mode_invalid')
        elif p.metrics_revision!=p.revision or not p.metrics:raise HTTPException(409,'calculate_current_facts_first')
        if payload.kind=='render' and (not p.section or p.section_revision!=p.revision):raise HTTPException(409,'section_missing_or_stale')
        if payload.kind=='render' and payload.mode!='synthetic':raise HTTPException(422,'render_mode_invalid')
        if payload.mode=='agnes':
            settings=db.get(Setting,'agnes')
            if not settings or not os.getenv('AGNES_API_KEY'):raise HTTPException(409,'agnes_not_configured')
            docs={d.id:d for d in db.scalars(select(Document).where(Document.project_id==pid))}
            if any(not docs[f['document_id']].model_allowed for f in facts_snapshot(db,p)):
                raise HTTPException(403,'model_data_not_authorized')
        h=snapshot_hash(db,p)
        existing=db.scalar(select(Task).where(Task.project_id==pid,Task.kind==payload.kind,Task.mode==payload.mode,Task.input_hash==h,Task.state.in_(['queued','running','completed'])))
        if existing:return task_view(existing)
        t=Task(project_id=pid,kind=payload.kind,mode=payload.mode,input_revision=p.revision,input_hash=h,created_by=user.id,created_at=time.time())
        db.add(t);db.flush();audit(db,user,'enqueue_task',pid,{'task_id':t.id,'kind':t.kind});db.commit()
        return task_view(t)

    @app.get('/api/projects/{pid}/tasks/{tid}')
    def get_task(pid:str,tid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user);t=db.get(Task,tid)
        if not t or t.project_id!=pid:raise HTTPException(404,'task_not_found')
        return task_view(t)

    @app.get('/api/projects/{pid}/exports')
    def exports(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        return [{'id':e.id,'sha256':e.sha256,'manifest':e.manifest} for e in db.scalars(select(Export).where(Export.project_id==pid))]

    @app.get('/api/projects/{pid}/exports/{eid}')
    def download_export(pid:str,eid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user);e=db.get(Export,eid)
        if not e or e.project_id!=pid:raise HTTPException(404,'export_not_found')
        path=(root/e.path).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=e.sha256:raise HTTPException(409,'export_integrity_failed')
        return FileResponse(path,filename='LeaseDD_合成测试_待复核.docx')

    @app.get('/api/projects/{pid}/audit')
    def get_audit(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        return [{'action':a.action,'user_id':a.user_id,'details':a.details,'created_at':a.created_at} for a in db.scalars(select(Audit).where(Audit.project_id==pid).order_by(Audit.created_at.desc()).limit(100))]

    @app.post('/api/projects/{pid}/publish-reviewed')
    def publish(pid:str,user=Depends(current),db=Depends(session)):
        project(db,pid,user)
        raise HTTPException(409,'formal_publication_disabled_M1')

    return app
