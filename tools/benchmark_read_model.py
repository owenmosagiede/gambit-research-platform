#!/usr/bin/env python3
"""Synthetic serving-query benchmark. Never accepts or opens a research root.

This measures query/serialization latency, not source verification, browser render,
HTTP transport/authentication, production resource use or research throughput.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from api.application import ApplicationRoutes
from read_model.storage import SCHEMA, atomic, encoded, initialize, signature


def fixture(directory, count):
    generation='a'*32; now=time.time(); date=datetime.now(timezone.utc).isoformat()
    path=directory/('generation-'+generation+'.sqlite')
    db=sqlite3.connect(path);initialize(db)
    db.execute('INSERT INTO metadata VALUES(?,?)',('schema_version',encoded(SCHEMA)))
    recipe='FEATURE_RECIPE_'+'a'*64
    for i in range(53):
        rid=recipe if i==0 else 'FEATURE_RECIPE_'+f'{i:064x}'
        entry={'id':rid,'name':'Synthetic momentum '+str(i),'research':{'relationship_count':count*5 if i==0 else 0,'research_stage_pass_count':0}}
        db.execute('INSERT INTO recipes VALUES(?,?,?,?)',(rid,entry['name'].casefold(),encoded(entry).casefold(),encoded(entry)))
    for i in range(count):
        rid=f'fixture-{i:08d}';status='succeeded' if i%2 else 'queued'
        job={'request_id':rid,'status':status,'queued_at':date,'created_at':date,'updated_at':date,'results':[],
             'horizons':[{'horizon':h,'p1_status':'rejected','p2_status':'not_run'} for h in (1,7,21,63,252)]}
        value={'job':job,'intent':{'expected_direction':'NEGATIVE','scope':{'id':'fixture-USD'}},'provenance':{'fixture_only':True}}
        db.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?)',(rid,status,date,date,recipe,'fixture-USD','NEGATIVE',encoded(value).casefold(),encoded(value)))
        for h in (1,7,21,63,252):
            relationship=f'fixture-relation-{i:08d}-{h}';trial=f'fixture-trial-{i:08d}-{h}'
            row={'fixture_only':True,'horizon':h,'recipe':{'id':recipe},'scope':{'id':'fixture-USD'},'expected_direction':'NEGATIVE',
                 'p1_status':'rejected','p2_status':'not_run','research_stage_pass':False,'trial_results':[{'id':trial}]}
            db.execute('INSERT INTO relationships VALUES(?,?)',(relationship,encoded({'fixture_only':True,'id':relationship})))
            db.execute('INSERT INTO trials VALUES(?,?)',(trial,encoded({'fixture_only':True,'id':trial,'metrics':{'primary_effect':0}})))
            db.execute('INSERT INTO branches VALUES(?,?,?,?,?,?,?,?)',(relationship,recipe,relationship,'fixture-USD','NEGATIVE',h,'not_run',encoded(row)))
    plans={
        'ledger':[r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT value FROM experiments WHERE status='succeeded' ORDER BY updated DESC,id LIMIT 51")],
        'branches':[r[3] for r in db.execute('EXPLAIN QUERY PLAN SELECT value FROM branches WHERE recipe=? ORDER BY id LIMIT 51',(recipe,))],
    }
    db.commit();db.close();os.chmod(path,0o440)
    manifest={'schema_version':SCHEMA,'generation':generation,'database_signature':signature(path),
              'database_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'observed_epoch':now,
              'observed_at':date,'published_at':date,'issue_count':0,'fixture_only':True}
    atomic(directory,'generation-'+generation+'.json',manifest)
    atomic(directory,'current.json',{'generation':generation});atomic(directory,'status.json',{'unavailable':False})
    return path.stat().st_size,plans,recipe


def run(sizes=(500,5000),requests=100,clients=(1,4,8)):
    results=[]
    with tempfile.TemporaryDirectory(prefix='gambit-serving-benchmark-') as tmp:
        for count in sizes:
            directory=Path(tmp).resolve()/str(count);directory.mkdir()
            size,plans,recipe=fixture(directory,count)
            endpoints=('ledger?limit=50','queue?limit=50','recipes?limit=50',f'recipes/{recipe}/branches?limit=50',
                       'trial/fixture-trial-00000000-1')
            for concurrency in clients:
                for endpoint in endpoints:
                    def request(_):
                        started=time.perf_counter()
                        route=ApplicationRoutes(Path(tmp)/'unused-source',None,None,'GET','/api/read-model/v1/'+endpoint,read_model_dir=directory)
                        route.read();status,body,_,_=route.response
                        if status!=200:raise RuntimeError(f'Synthetic query failed: {status}')
                        return (time.perf_counter()-started)*1000,len(body)
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        observations=list(pool.map(request,range(requests)))
                    times=sorted(v[0] for v in observations)
                    results.append({'experiments':count,'branches':count*5,'clients':concurrency,'endpoint':endpoint.split('?')[0],
                                    'requests':requests,'p50_ms':round(statistics.median(times),3),
                                    'p95_ms':round(times[min(len(times)-1,int(len(times)*.95))],3),
                                    'max_ms':round(max(times),3),'max_response_bytes':max(v[1] for v in observations),
                                    'database_bytes':size,'query_plans':plans})
    return {'schema':'synthetic_read_model_benchmark_v1','production_data_used':False,'measures':'fresh read-only SQLite connection and response serialization; OS caches uncontrolled',
            'does_not_measure':['projector throughput','browser rendering','HTTP authentication/transport','production research impact'],
            'results':results}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'scenarios':len(report['results']),'requests':sum(r['requests'] for r in report['results']),
                      'worst_p95_ms':max(r['p95_ms'] for r in report['results'])}))


if __name__=='__main__':main()
