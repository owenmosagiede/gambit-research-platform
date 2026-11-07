#!/usr/bin/env python3
"""Full P2 preparation/evaluation proof on isolated persisted synthetic sources.

No production path is accepted. Source provenance, Feature verification, Target
alignment, P1 admission and P2 evaluation are real. Only recipe/Scope discovery
is supplied by the fixture. Historical events are synthetic operational records.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import date
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '4eaba323d2de21034fb302edfddd61efcd9d2b80'
spec = importlib.util.spec_from_file_location('full_source', ROOT/'tools/benchmark_source_preparation.py')
full = importlib.util.module_from_spec(spec); spec.loader.exec_module(full)
prep, bench, proof = full.prep, full.prep.benchmark, full.prep.proof


def kernel(profile, plan, phase):
    return dict(profile['kernel'], structural_common_start=plan['structural_common_start'],
                window_start=plan['periods'][phase]['start_inclusive'],
                window_end_exclusive=plan['periods'][phase]['end_exclusive'])


def run(source, root, output, *, seed_stored=False):
    performance = bench.load_source(source)
    from data.verified_inputs import execution_inputs, fresh_inputs
    from data.feature_store import FeatureStore
    from data.fx_feature_store import read_fx_materialization
    from data.transformations.identity import reference
    from research import inputs
    from research.p1_discovery import run_p1
    from research.p2_validation import run_p2
    from runtime.research_jobs import ResearchJobs, implementation
    fixture = json.loads((root/'benchmark-fixture.json').read_text())
    plan = fixture['plans']['diff63_positive']; profile = fixture['profile']
    # An actual frozen submission provides the same cancellation checks called
    # by production preparation. No worker is started by this benchmark.
    class Adapter:
        def resolve_plan(self, unused_root, intent, selected):
            if intent != plan['intent'] or selected != profile: raise ValueError('Fixture binding changed')
            return deepcopy(plan)
    (root/'config/research_execution.json').write_text(json.dumps(profile))
    jobs = ResearchJobs(root, adapter=Adapter())
    request = dict(plan['intent'], request_id='65b555d5-6fb4-4da2-82ee-49e3197c9362')
    jobs.submit(request); rid = request['request_id']
    # Approximate the observed production event population, not its content.
    # Every event has a valid request ID and an independent immutable filename.
    template = jobs._read_job(rid)
    for n in range(500):
        other = str(uuid.UUID(int=n+1)); previous = None
        folder = root/'storage/catalog/attempts'/('benchmark-'+str(n))/'events'; folder.mkdir(parents=True)
        for seq in range(25):
            event = {'request_id':other,'sequence':seq,'previous':previous,
                     'job':dict(template,request_id=other,status='succeeded')}
            previous = proof.digest(event)
            (folder/('RESEVENT_'+previous+'.json')).write_bytes(bench.canonical(event)+b'\n')
    reports = {}; admitted = []; p1_decisions = {}
    saved = []; original = inputs.prepare_fx_feature
    def publish(*args, **kwargs):
        result = original(*args, **kwargs); saved.append(result); return result
    with patch.object(inputs, 'prepare_fx_feature', publish), execution_inputs(root, implementation()) as cache:
        for phase in ('P1','P2'):
            saved.clear()
            admission = None if phase == 'P1' else {'plan_id':plan['plan_id'],
                'direction':plan['intent']['expected_direction'], 'admitted_horizons':admitted}
            if phase == 'P2' and len(admitted) < 2:
                raise ValueError('Full P2 benchmark requires at least two actual admitted horizons: '+str(admitted))
            horizons = plan['horizons'] if phase == 'P1' else admitted
            print(source.name, phase, 'preparation started', flush=True)
            with performance.profiling() as measurement:
                prepared = inputs.prepare_phase(root,plan,phase,progress=lambda *a,**kw:jobs._check(rid),
                    cancelled=lambda:jobs._cancelled(rid),admission=admission)
                preparation = measurement.report()
                loaded = [inputs.load_phase(root,plan,prepared,phase,h,admission=admission) for h in horizons]
                decisions = []
                for h,item in zip(horizons,loaded):
                    arguments = dict(mode='CS',horizon=h,members=plan['scope']['members'],
                        expected_direction=plan['intent']['expected_direction'],profile=kernel(profile,plan,phase))
                    if phase == 'P1':
                        result = run_p1(item['rows'],**arguments); p1_decisions[h] = result
                        if result['admission'] == 'admitted' and (result['metrics']['primary_effect'] or 0)>0:
                            admitted.append(h)
                    else:
                        result = run_p2(item['rows'],discovery_effect=p1_decisions[h]['metrics']['primary_effect'],**arguments)
                    decisions.append(result)
            report = dict(schema='fresh_feature_evidence_v1',fixture=proof.digest(fixture),phases={},
                lineage_storage_mode=os.environ['GAMBIT_FX_LINEAGE_STORAGE'],source_verification_mocked=False,
                source_implementation=implementation(),environment=bench.locked_environment(source),
                prepared=prepared,loaded=loaded,decisions=decisions,cache_high_water_bytes=cache.high_water_bytes,
                preparation_performance=preparation,performance=measurement.report(),
                dimensions={'members':len(plan['members']),'source_dates':fixture['scheduled_source_dates'],
                    'phase':phase,'weekdays':len(list(inputs._period_days(plan['periods'][phase]))),'publications':len(saved)},
                source_admission_boundary=fixture['source_admission'],admitted_horizons=list(admitted))
            print(source.name, phase, 'measured', round(measurement.report()['wall_seconds'],2),
                  'preparation',round(preparation['wall_seconds'],2),'admitted',admitted,flush=True)
            print('Measured work',json.dumps({name:measurement.report()['timings'].get(name) for name in
                  ('events.replay','inputs.cache_witness','feature.verify','catalog.feature_resolution')}),flush=True)
            # Independent replay and complete provenance capture are not timed.
            store = FeatureStore(root)
            code_paths = {str(p.relative_to(source)).replace('/','_'):p for top in ('src','specs')
                          for p in (source/top).rglob('*') if p.is_file()}
            with fresh_inputs():
                for i,publication in enumerate(saved):
                    verified = read_fx_materialization(root,publication['materialization']['id'])
                    verified['operands_sha256'] = proof.digest(verified.pop('operands'))
                    impl = store.resolve(verified['manifest']['input_key']['implementation']); sources = {}
                    for member in impl['code_artifacts']:
                        path=code_paths[member['role']]; data=path.read_bytes()
                        proof.require(store.payload(member)==data,'producer payload differs')
                        sources[member['role']]={'path':str(path.relative_to(source)),
                            'sha256':proof.sha256(data).hexdigest(),'bytes':len(data)}
                    entries=[json.loads(p.read_text()) for p in
                        (root/'storage/catalog/signal_library/entries'/publication['signal_id']).glob('*.json')]
                    entry=next(e for e in entries if reference(e)==publication['entry'])
                    report['phases'][str(i)]={'publication':publication,'verified':verified,'implementation':impl,
                        'lineages':[store.resolve(r) for r in verified['manifest']['lineage']],
                        'entry':entry,'code_sources':sources}
            reports[phase]=report
    if seed_stored:
        # Freeze those exact baseline outputs for a separate stored-input case.
        for member in plan['members']:
            refs=[]
            for phase in ('P1','P2'):
                output_member=next(m for m in reports[phase]['prepared']['members'] if m['instrument_id']==member['instrument_id'])
                for binding in output_member['materializations']:
                    manifest=FeatureStore(root).resolve(binding)
                    refs.append({'reference':binding,'period':manifest['input_key']['period']})
            member['feature_materializations']=refs
        plan['plan_id']=inputs._plan_id(plan)
        (root/'benchmark-fixture.json').write_bytes(bench.canonical(fixture))
        # Fixture operational history is regenerated for each measured child.
        import shutil
        for name in ('submissions','attempts','operations','experiment_intake'):
            path=root/'storage/catalog'/name
            if path.exists():shutil.rmtree(path)
    prep.write(output,reports)


def compare(before,after):
    result={}
    for phase in ('P1','P2'):
        old,new=before[phase],after[phase]
        proof.require(old['source_verification_mocked'] is False and new['source_verification_mocked'] is False,
                      'full source verification required')
        if old['phases']:
            # P2 library entries also reference the P1 publications made by
            # this same experiment. Prove that complete closure before mapping
            # any entry; never discard an earlier dependency to make it match.
            closure = ('P1',) if phase == 'P1' else ('P1','P2')
            reports=[]
            for source,current in ((before,old),(after,new)):
                publications=[item for stage in closure for item in source[stage]['phases'].values()]
                reports.append(dict(current,phases={str(i):item for i,item in enumerate(publications)}))
            comparison=prep.compare(*reports)
        else:
            for field in ('fixture','prepared','loaded','decisions','dimensions','admitted_horizons'):
                proof.require(old[field]==new[field],'stored '+phase+' '+field+' changed')
            proof.require(not new['phases'],'stored run unexpectedly published')
            comparison={'exact_scientific_equality':True}
        proof.require(new['cache_high_water_bytes']<=128*1024*1024,'cache exceeded existing bound')
        result[phase]={'exact_scientific_equality':comparison['exact_scientific_equality'],
            'preparation_before':old['preparation_performance']['wall_seconds'],
            'preparation_after':new['preparation_performance']['wall_seconds'],
            'total_before':old['performance']['wall_seconds'],'total_after':new['performance']['wall_seconds'],
            'cache_high_water_bytes':new['cache_high_water_bytes'],'admitted_horizons':new['admitted_horizons']}
    result['passed']=(all(r['exact_scientific_equality'] for r in result.values())
        and result['P2']['preparation_after']<=result['P2']['preparation_before']*.7
        and result['P2']['total_after']<result['P2']['total_before']
        and result['P1']['total_after']<=result['P1']['total_before']*1.1)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',choices=('diff63','volscale5'),default='diff63')
    parser.add_argument('--repeats',type=int,choices=(1,2),default=2)
    parser.add_argument('--stored-first',action='store_true',help='Check stored-input regressions before fresh cases; all gates still apply')
    parser.add_argument('--child',choices=('build','run','seed-stored'))
    parser.add_argument('--source',type=Path);parser.add_argument('--fixture',type=Path)
    args=parser.parse_args()
    if args.child:
        prep.isolated_child(args.source,args.fixture)
        if args.child=='build':
            result=full.build(args.source,args.fixture,p2_case=args.case)
            args.output.write_text(json.dumps(result,indent=2)+'\n')
        else:run(args.source,args.fixture,args.output,seed_stored=args.child=='seed-stored')
        return
    bench.locked_environment(ROOT);args.output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='gambit-fresh-preparation-') as directory:
        tmp=Path(directory);sources={'baseline':tmp/'baseline','candidate':tmp/'candidate'}
        bench.source_copy(ROOT,sources['baseline'],BASELINE);bench.source_copy(ROOT,sources['candidate'])
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GAMBIT_ISOLATED_TEST='1',GAMBIT_FX_LINEAGE_STORAGE='packed_v1')
        cmd=[sys.executable,'-B',str(Path(__file__).resolve())];seed=tmp/'seed'
        def child(kind,source,fixture,output):
            subprocess.run(cmd+['--child',kind,'--source',str(source),'--fixture',str(fixture),
                '--output',str(output),'--case',args.case],env=env,check=True)
        child('build',sources['baseline'],seed,args.output/'fixture.json')
        comparisons=[]
        for state in (('stored','fresh') if args.stored_first else ('fresh','stored')):
            state_seed=seed
            if state=='stored':
                state_seed=tmp/'stored-seed';bench.copy_store(seed,state_seed)
                child('seed-stored',sources['baseline'],state_seed,args.output/'seed-stored.json.gz')
            for repeat in range(args.repeats):
                reports={}
                for name in (('baseline','candidate') if repeat%2==0 else ('candidate','baseline')):
                    with tempfile.TemporaryDirectory(dir=tmp,prefix='run-') as folder:
                        root=Path(folder)/'store';bench.copy_store(state_seed,root)
                        output=args.output/f'{state}-{repeat}-{name}.json.gz'
                        child('run',sources[name],root,output);reports[name]=prep.read(output)
                row=compare(reports['baseline'],reports['candidate']);row.update(state=state,repeat=repeat)
                comparisons.append(row)
                (args.output/'comparison.json').write_text(json.dumps({'baseline_commit':BASELINE,
                    'case':args.case,'repeats':comparisons,'passed':len(comparisons)==4 and all(r['passed'] for r in comparisons),
                    'source_trees':{n:bench.tree_identity(p) for n,p in sources.items()},'production_data_used':False,
                    'source_verification_mocked':False},indent=2)+'\n')
                print('Comparison',json.dumps(row),flush=True)
                if not row['passed']:
                    raise RuntimeError('Offline performance gate failed; retained evidence, no further repeats')


if __name__=='__main__':main()
