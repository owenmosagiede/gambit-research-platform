#!/usr/bin/env python3
"""Synthetic production-scale planner acceptance; never reads a live store.

Run separately from routine CI: creates hundreds of thousands of temporary files.
"""
import argparse,json,os,resource,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from test_scopes import fixture
from data.feature_store import FeatureStore
from data.fx_currency_catalog import add
from data.transformations.identity import reference
from data.fx_currency_migration import plan,apply
from data.fx_migration_manifest import install_manifest,manifest_digest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--records',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='gambit-synthetic-migration-scale-') as tmp:
        root=Path(tmp);fixture(root)
        release=add(FeatureStore(root),'onboarding_evidence',{'kind':'fx_currency_release'})
        # High-cardinality lineage-like records, each with many nested references.
        # The original planner retained the decoded objects AND every string set.
        for n in range(a.records):
            directory=root/'storage/catalog/lineage'/f'{n//1000:06d}';directory.mkdir(exist_ok=True,parents=True)
            record={'id':f'SYNTHETIC_LINEAGE_{n:09d}','schema_version':'0.8.0','record_type':'lineage',
                'body':{'kind':'synthetic_scale_only','operands':[{'id':f'SYNTHETIC_SOURCE_{n}_{i}',
                    'reference_time':f'2000-01-{i%28+1:02d}','value':str(n+i),'role':'input','unit':'price',
                    'evidence':{'content_sha256':f'{n*64+i:064x}','version':'1.0.0'}} for i in range(32)]}}
            (directory/f'{n:09d}.json').write_text(json.dumps(record,separators=(',',':')))
        print(json.dumps({'phase':'fixture_ready','records':a.records,'seconds':time.monotonic()-started}),flush=True)
        # Only scientific replay is mocked: this benchmark isolates the failed
        # planner/inventory path. Full release tests exercise real replay separately.
        with patch('data.fx_currency_release.validate_release',return_value=release):result=plan(root,reference(release))
        if result['blockers']:raise RuntimeError(result['blockers'])
        assert len(result['protected_ts'])==86
        assert not any(p.startswith('storage/catalog/lineage/') for p in result['delete'])
        install_manifest(root/'manifest.json',result)
        del result
        parsed=json.loads((root/'manifest.json').read_text())
        assert manifest_digest({k:v for k,v in parsed.items() if k!='sha256'})==parsed['sha256']
        with patch('data.fx_currency_release.validate_release',return_value=release):
            applied=apply(root,parsed,parsed['sha256'])
        assert applied['completed']
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform!='darwin':peak*=1024
        receipt={'records':a.records,'inventory_files':len(parsed['inventory']),'peak_rss_bytes':peak,
            'memory_budget_bytes':2*1024**3,'passed':peak<2*1024**3,'seconds':round(time.monotonic()-started,3),
            'scientific_replay':'covered separately; mocked only in this synthetic planner benchmark','production_data_used':False,'plan_apply_serialization_checked':True}
        a.output.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
        if not receipt['passed']:raise SystemExit(1)
if __name__=='__main__':main()
