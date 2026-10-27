#!/usr/bin/env python3
"""Offline fresh Feature proof with a closed, explicitly derived provenance map.

The fixture replaces source admission only. Both releases publish new Features
and independently replay them. No production path is accepted. Changed producer
code blobs may change identity; no scientific fields or arbitrary IDs are erased.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def reference(record):
    value = deepcopy(record); value.pop('display_name', None)
    if value.get('record_type') == 'snapshot_manifest': value.pop('members', None)
    if value.get('record_type') == 'materialization_manifest': value.pop('partitions', None)
    return {'id': record['id'], 'version': record['version'], 'content_sha256': digest(value)}


def require(condition, message):
    if not condition: raise ValueError('Fresh Feature proof: ' + message)


def identified(record, prefix):
    value = deepcopy(record); value.pop('id', None)
    return dict(value, id=prefix + digest(value))


def compare_reports(before, after):
    require(before['schema'] == after['schema'] == 'fresh_feature_evidence_v1', 'schema differs')
    for report in (before, after):
        actual = report['source_implementation']; files = actual['files']
        require(isinstance(files, dict) and bool(files) and
                all(isinstance(k, str) and isinstance(v, str) and len(v) == 64 and
                    all(c in '0123456789abcdef' for c in v) for k, v in files.items()) and
                actual['fingerprint'] == digest(files), 'actual source implementation fingerprint differs')
    require(before['fixture'] == after['fixture'], 'source, recipe or phase fixture differs')
    require(before['lineage_storage_mode'] == after['lineage_storage_mode'], 'physical mode differs')
    require(set(before['phases']) == set(after['phases']) == {'P1', 'P2'}, 'both fresh phases required')
    mapped_materializations = {}; proof = []
    for phase in ('P1', 'P2'):
        old, new = before['phases'][phase], after['phases'][phase]
        old_impl, new_impl = old['implementation'], new['implementation']
        for report, item in ((before, old), (after, new)):
            impl = item['implementation']
            require(identified(impl, 'IMPLEMENTATION_') == impl, 'producer implementation identity differs')
            require(set(item['code_sources']) == {m['role'] for m in impl['code_artifacts']}, 'code closure differs')
            for member in impl['code_artifacts']:
                source = item['code_sources'][member['role']]
                require(member['format'] == 'txt' and member['blob_sha256'] == source['sha256'] and
                        member['byte_count'] == source['bytes'] and
                        source['path'].replace('/', '_') == member['role'], 'code leaf does not match source bytes')
                path = Path(source['path'])
                if (len(path.parts) > 2 and path.parts[0] == 'src' and
                        path.parts[1] in {'data', 'research', 'runtime', 'contracts'} and path.suffix == '.py'):
                    require(report['source_implementation']['files'].get(str(path.relative_to('src'))) ==
                            source['sha256'], 'producer code leaf differs from actual source implementation')
            manifest = item['verified']['manifest']; rows = item['verified']['observations']
            require(manifest['input_key']['implementation'] == reference(impl), 'manifest producer differs')
            require(manifest['id'] == 'MATERIALIZATION_' + digest({
                'identity_profile': manifest['identity_profile'], 'input_key': manifest['input_key']}), 'materialization ID differs')
            require(manifest['semantic_content_sha256'] == digest(rows), 'observation digest differs')
            require(len(manifest['partitions']) == 1, 'unexpected Feature partition structure')
            raw = b''.join(canonical(row) + b'\n' for row in rows)
            member = manifest['partitions'][0]
            require(member['format'] == 'jsonl' and member['blob_sha256'] == sha256(raw).hexdigest() and
                    member['byte_count'] == len(raw) and member['row_count'] == len(rows), 'partition bytes differ')
            require(item['publication']['reused'] is False, 'fresh publication was not exercised')
            require(item['publication']['materialization'] == reference(manifest), 'published manifest differs')
            require(item['publication']['entry'] == reference(item['entry']) and
                    identified(item['entry'], 'LIBRARYENTRY_') == item['entry'], 'published library entry differs')
        require([m['role'] for m in old_impl['code_artifacts']] ==
                [m['role'] for m in new_impl['code_artifacts']], 'producer code roles changed')
        changed = []
        for left, right in zip(old_impl['code_artifacts'], new_impl['code_artifacts']):
            require({k:v for k,v in left.items() if k not in ('blob_sha256','byte_count')} ==
                    {k:v for k,v in right.items() if k not in ('blob_sha256','byte_count')}, 'unexpected code leaf change')
            left_path = old['code_sources'][left['role']]['path']
            require(left_path == new['code_sources'][right['role']]['path'], 'producer code path changed')
            if left != right:
                path = Path(left_path)
                require(len(path.parts) > 2 and path.parts[0] == 'src' and
                        path.parts[1] in {'data', 'research', 'runtime', 'contracts'} and path.suffix == '.py',
                        'producer leaf outside the implementation fingerprint changed')
                changed.append(left_path)
        normalized_impl = deepcopy(new_impl); normalized_impl['code_artifacts'] = deepcopy(old_impl['code_artifacts'])
        require(identified(normalized_impl, 'IMPLEMENTATION_') == old_impl, 'non-code implementation field changed')
        normalized = deepcopy(new['verified'])
        manifest = normalized['manifest']; manifest['input_key']['implementation'] = reference(old_impl)
        manifest['id'] = 'MATERIALIZATION_' + digest({'identity_profile': manifest['identity_profile'],
                                                   'input_key': manifest['input_key']})
        lineage_map = {}
        require(len(old['lineages']) == len(new['lineages']), 'lineage count changed')
        for left, right in zip(old['lineages'], new['lineages']):
            require(identified(right, 'LINEAGE_') == right and identified(left, 'LINEAGE_') == left,
                    'row lineage identity differs')
            require(right['body']['implementation'] == reference(new_impl), 'lineage producer differs')
            translated = deepcopy(right); translated['body']['implementation'] = reference(old_impl)
            translated = identified(translated, 'LINEAGE_')
            require(translated == left, 'lineage fields changed beyond producer reference')
            lineage_map[digest(reference(right))] = reference(left)
        def translate_lineage(binding):
            require(digest(binding) in lineage_map, 'unproven row lineage reference')
            return deepcopy(lineage_map[digest(binding)])
        manifest['lineage'] = [translate_lineage(r) for r in manifest['lineage']]
        for row in normalized['observations']:
            require(row['materialization_id'] == new['verified']['manifest']['id'], 'foreign row materialization')
            row['materialization_id'] = manifest['id']; row['lineage'] = translate_lineage(row['lineage'])
        rows = normalized['observations']; raw = b''.join(canonical(row) + b'\n' for row in rows)
        manifest['semantic_content_sha256'] = digest(rows)
        manifest['partitions'][0].update(blob_sha256=sha256(raw).hexdigest(), byte_count=len(raw))
        require(normalized == old['verified'], 'verified values, statuses, operands or manifest fields changed')
        mapped_materializations[digest(reference(new['verified']['manifest']))] = reference(manifest)
        entry = deepcopy(new['entry'])
        require(all(digest(r) in mapped_materializations for r in entry['feature_materializations']), 'unproven library materialization')
        entry['feature_materializations'] = sorted(
            (mapped_materializations[digest(r)] for r in entry['feature_materializations']), key=lambda r:r['id'])
        entry = identified(entry, 'LIBRARYENTRY_')
        require(entry == old['entry'], 'library entry changed beyond proven materializations')
        publication = deepcopy(new['publication'])
        publication.update(materialization=reference(manifest), entry=reference(entry))
        require(publication == old['publication'], 'publication result changed')
        proof.append({'phase':phase, 'changed_producer_code_paths':changed,
            'producer_reference':{'baseline':reference(old_impl),'optimized':reference(new_impl)},
            'materialization_reference':{'baseline':reference(manifest),'optimized':reference(new['verified']['manifest'])},
            'mapped_lineages':len(lineage_map), 'exact_scientific_equality':True})
    return {'schema':'fresh_feature_comparison_v1','exact_scientific_equality':True,'phases':proof,
            'production_data_used':False,'mapping_rule':'validated producer code leaves and only recomputed transitive references'}


def helper():
    spec=importlib.util.spec_from_file_location('input_benchmark', ROOT/'tools/benchmark_research_inputs.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(source, output):
    benchmark=helper();performance=benchmark.load_source(source)
    from test_fx_feature_store import FXFeatureStoreTests
    from data.verified_inputs import execution_inputs, phase_inputs
    from data.fx_feature_store import read_fx_materialization
    from runtime.research_jobs import implementation
    from datetime import date,timedelta
    fixture=FXFeatureStoreTests('runTest');fixture.setUp()
    try:
        # Exercise a positive-input failure as well as the fixture's missing day.
        fixture.prices[25]['value']='0'
        fixture.prices[25]['id']='FXPRICE_'+digest({k:v for k,v in fixture.prices[25].items() if k!='id'})
        periods={name:{'start_inclusive':fixture.days[a],
            'end_exclusive':(date.fromisoformat(fixture.days[b])+timedelta(days=1)).isoformat()}
            for name,a,b in [('P1',0,39),('P2',40,79)]}
        pinned={'feature':fixture.feature,'snapshot':fixture.snapshot_record,'prices':fixture.prices,
                'batch_policy':fixture.batch,'periods':periods,'cutoff':'2024-05-02'}
        plan={'plan_id':'FRESH_FEATURE_'+digest(pinned),'periods':periods}
        report={'schema':'fresh_feature_evidence_v1','fixture':pinned,'phases':{},
            'lineage_storage_mode':os.environ.get('GAMBIT_FX_LINEAGE_STORAGE','loose'),
            'source_implementation':implementation(),'environment':benchmark.locked_environment(source),
            'source_boundary':'Synthetic source admission; real fresh publication and independent numerical replay.',
            'phase_boundary':'P1/P2-shaped direct Feature intervals; admission is tested by the runtime suite.'}
        code_paths={str(p.relative_to(source)).replace('/','_'):p for top in ('src','specs')
                    for p in (source/top).rglob('*') if p.is_file()}
        with execution_inputs(fixture.root,implementation()):
            for phase in ('P1','P2'):
                period=periods[phase]
                with performance.profiling() as measurement,phase_inputs(fixture.root,plan,phase):
                    saved=fixture.prepare(start=period['start_inclusive'],
                        end=(date.fromisoformat(period['end_exclusive'])-timedelta(days=1)).isoformat())
                    verified=read_fx_materialization(fixture.root,saved['materialization']['id'])
                impl=fixture.store.resolve(verified['manifest']['input_key']['implementation'])
                sources={}
                for member in impl['code_artifacts']:
                    path=code_paths[member['role']];data=path.read_bytes()
                    require(fixture.store.payload(member)==data,'installed producer blob differs from source file')
                    sources[member['role']]={'path':str(path.relative_to(source)),
                        'sha256':sha256(data).hexdigest(),'bytes':len(data)}
                entries=[json.loads(p.read_text()) for p in
                    (fixture.root/'storage/catalog/signal_library/entries'/saved['signal_id']).glob('*.json')]
                entry=next(v for v in entries if reference(v)==saved['entry'])
                report['phases'][phase]={'publication':saved,'verified':verified,'implementation':impl,
                    'lineages':[fixture.store.resolve(r) for r in verified['manifest']['lineage']],
                    'entry':entry,'code_sources':sources,'performance':measurement.report()}
        output.write_text(json.dumps(report,indent=2)+'\n')
    finally:fixture.tearDown()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--lineage',choices=('loose','packed_v1'),default='packed_v1')
    parser.add_argument('--timing-context',required=True)
    parser.add_argument('--child',action='store_true');parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.child:run(args.source,args.output);return
    if not args.baseline:parser.error('--baseline is required')
    benchmark=helper();benchmark.locked_environment(ROOT)
    commit=subprocess.check_output(['git','-C',str(args.baseline),'rev-parse','HEAD'],text=True).strip()
    require(commit==benchmark.BASELINE_COMMIT,'baseline commit differs')
    args.output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='gambit-fresh-feature-proof-') as tmp:
        tmp=Path(tmp);sources={'baseline':tmp/'baseline','optimized':tmp/'optimized'}
        benchmark.source_copy(args.baseline,sources['baseline'],benchmark.BASELINE_COMMIT)
        benchmark.source_copy(ROOT,sources['optimized'])
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GAMBIT_FX_LINEAGE_STORAGE=args.lineage)
        reports={}
        for name,source in sources.items():
            path=args.output/(name+'.json')
            subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child','--source',str(source),
                '--output',str(path),'--timing-context',args.timing_context],env=env,check=True)
            reports[name]=json.loads(path.read_text())
        result=compare_reports(reports['baseline'],reports['optimized'])
        result.update(baseline_commit=commit,timing_context=args.timing_context,
            source_snapshot_sha256={name:benchmark.tree_identity(source)['sha256'] for name,source in sources.items()},
            timings={name:{phase:value['performance'] for phase,value in report['phases'].items()}
                     for name,report in reports.items()})
        (args.output/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
