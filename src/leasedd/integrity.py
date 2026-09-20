"""Read-only verification of restored source and published artifact pointers."""
import hashlib,json,os
from pathlib import Path
from sqlalchemy import select
from .db import database,Document,Export

def verify_files(root,sources,exports):
    errors=[]
    for source in sources:
        path=(root/source['path']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
            errors.append('source_integrity_failed:'+source['path'])
    for artifact in exports:
        path=(root/artifact['path']).resolve()
        try:
            valid=path.is_relative_to(root.resolve()) and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==artifact['sha256'] and json.loads((path.parent/'artifact_manifest.json').read_text())==artifact['manifest']
        except (OSError,ValueError):valid=False
        if not valid:errors.append('export_integrity_failed:'+artifact['path'])
    return errors

def main():
    engine,factory=database(os.environ['LEASEDD_DATABASE_URL'])
    with factory() as db:
        sources=[{'path':d.path,'sha256':d.sha256} for d in db.scalars(select(Document))]
        exports=[{'path':e.path,'sha256':e.sha256,'manifest':e.manifest} for e in db.scalars(select(Export))]
    errors=verify_files(Path(os.environ['LEASEDD_DATA_DIR']),sources,exports)
    print(json.dumps({'execution_state':'completed','quality_state':'failed' if errors else 'passed','review_state':'pending','sources':len(sources),'exports':len(exports),'errors':errors},ensure_ascii=False))
    engine.dispose()
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
