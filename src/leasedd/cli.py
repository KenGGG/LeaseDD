import argparse,json,os
from pathlib import Path
from .app import create_app
from . import contracts

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['bootstrap','schema','doctor']);args=parser.parse_args()
    if args.command=='bootstrap':
        app=create_app(initialize=False)
        app.state.bootstrap(os.environ['LEASEDD_ADMIN_USER'],os.environ['LEASEDD_ADMIN_PASSWORD'])
        print('Administrator initialized (existing accounts are never replaced).')
    elif args.command=='schema':
        directory=Path('contracts');directory.mkdir(exist_ok=True)
        for name in ['SourceDocument','EvidenceSpan','Fact','MetricResult','SectionContract','SectionDraft','RunManifest']:
            (directory/(name+'.schema.json')).write_text(json.dumps(getattr(contracts,name).model_json_schema(),ensure_ascii=False,indent=2))
        try:
            from .financial_semantics import SEMANTIC_CONTRACTS
            for name,contract in SEMANTIC_CONTRACTS.items():
                (directory/(name+'.schema.json')).write_text(json.dumps(contract.model_json_schema(),ensure_ascii=False,indent=2))
        except ImportError:
            pass
    else:
        print(json.dumps({'execution_state':'completed','quality_state':'not_checked','review_state':'pending','production_template_status':'missing','agnes_credential_configured':bool(os.getenv('AGNES_API_KEY'))}))

if __name__=='__main__':main()
