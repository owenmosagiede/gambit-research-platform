#!/usr/bin/env python3
"""Offline fresh, multi-member P1 preparation against the deployed baseline.

No production store argument exists. Two independent source processes use copies
of one baseline-built synthetic seed, with no prepublished selected Features.
Source admission is synthetic; publication, packed lineage, independent replay,
five Target alignments and P1 decisions are real. This is not a production ETA.
"""
import argparse
from copy import deepcopy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '992ced766dd76b7a311a8bddf4dfaa05d9077679'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


benchmark = module('stored_benchmark', ROOT/'tools/benchmark_research_inputs.py')
proof = module('fresh_proof', ROOT/'tools/benchmark_fresh_features.py')


def write(path, value):
    with gzip.open(path, 'wt') as out:
        json.dump(value, out, sort_keys=True, separators=(',', ':'), allow_nan=False)


def read(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def isolated_child(source, fixture):
    source, fixture = source.resolve(), fixture.resolve()
    parent = source.parent
    if (not parent.name.startswith('gambit-fresh-preparation-') or
            source.name not in ('baseline', 'candidate') or
            not fixture.is_relative_to(parent)):
        raise ValueError('Benchmark child accepts only its isolated temporary workspace')
    # source_copy seeds exactly six approved policy-support files for tests.
    expected = {row['path']:(row['bytes'], row['sha256']) for row in
                json.loads((source/'tests/fixtures/registry_support/manifest.json').read_text())['files']}
    actual = {str(path.relative_to(source)):(path.stat().st_size, proof.sha256(path.read_bytes()).hexdigest())
              for path in (source/'storage').rglob('*') if path.is_file()}
    if actual != expected:
        raise ValueError('Benchmark source contains storage beyond approved policy fixtures')


def run(source, root, output):
    performance = benchmark.load_source(source)
    from data.verified_inputs import execution_inputs, fresh_inputs
    from data.feature_store import FeatureStore
    from data.fx_feature_store import read_fx_materialization
    from runtime.research_jobs import implementation
    from research import inputs
    from research.p1_discovery import run_p1
    fixture = json.loads((root/'benchmark-fixture.json').read_text())
    plan = fixture['plans']['diff63_positive']
    if any(m['feature_materializations'] for m in plan['members']):
        raise ValueError('Selected Feature fixture must be fresh')
    saved = []; original = inputs.prepare_fx_feature
    def publish(*args, **kwargs):
        value = original(*args, **kwargs)
        if value['reused']: raise ValueError('Expected fresh publication')
        saved.append(value)
        return value
    report = {'schema':'fresh_feature_evidence_v1', 'fixture':proof.digest(fixture), 'phases':{},
              'lineage_storage_mode':os.environ['GAMBIT_FX_LINEAGE_STORAGE'],
              'source_implementation':implementation(), 'environment':benchmark.locked_environment(source)}
    with benchmark.fixture_boundary(root, fixture), patch.object(inputs, 'prepare_fx_feature', publish):
        with performance.profiling() as measurement, execution_inputs(root, implementation()) as cache:
            prepared = inputs.prepare_phase(root, plan, 'P1')
            loaded = [inputs.load_phase(root, plan, prepared, 'P1', h) for h in plan['horizons']]
            period = plan['periods']['P1']
            kernel = dict(fixture['profile']['kernel'], structural_common_start=plan['structural_common_start'],
                          window_start=period['start_inclusive'], window_end_exclusive=period['end_exclusive'])
            decisions = [run_p1(item['rows'], mode='CS', horizon=h, members=plan['scope']['members'],
                                expected_direction='POSITIVE', profile=kernel)
                         for h,item in zip(plan['horizons'], loaded)]
            report['cache_high_water_bytes'] = cache.high_water_bytes
        report.update(performance=measurement.report(), prepared=prepared, loaded=loaded, decisions=decisions,
                      dimensions={'members':len(plan['members']), 'source_dates':fixture['scheduled_source_dates'],
                                  'P1_weekdays':sum(1 for _ in inputs._period_days(period)), 'publications':len(saved)},
                      source_admission_boundary=fixture['source_admission'])
        print('Measured fresh preparation:', source.name, json.dumps({
            'seconds':report['performance']['wall_seconds'], 'dimensions':report['dimensions'],
            'price_verifications':cache.counts['prices.loads'],
            'feature_lookup_invalidations':cache.counts['feature_lookup.invalidations']}), flush=True)
        # Independent inspection is outside timing and cannot inherit a cache.
        store = FeatureStore(root)
        code_paths = {str(p.relative_to(source)).replace('/','_'):p for top in ('src','specs')
                      for p in (source/top).rglob('*') if p.is_file()}
        with fresh_inputs():
            for index, publication in enumerate(saved):
                verified = read_fx_materialization(root, publication['materialization']['id'])
                # Operand content has no producer-code-derived references. Bind
                # its entire exact value without repeating the large history in reports.
                verified['operands_sha256'] = proof.digest(verified.pop('operands'))
                impl = store.resolve(verified['manifest']['input_key']['implementation'])
                sources = {}
                for member in impl['code_artifacts']:
                    path = code_paths[member['role']]; data = path.read_bytes()
                    proof.require(store.payload(member) == data, 'producer payload differs')
                    sources[member['role']] = {'path':str(path.relative_to(source)),
                        'sha256':proof.sha256(data).hexdigest(), 'bytes':len(data)}
                entries = [json.loads(p.read_text()) for p in
                    (root/'storage/catalog/signal_library/entries'/publication['signal_id']).glob('*.json')]
                entry = next(v for v in entries if proof.reference(v) == publication['entry'])
                report['phases'][str(index)] = {'publication':publication, 'verified':verified,
                    'implementation':impl, 'lineages':[store.resolve(r) for r in verified['manifest']['lineage']],
                    'entry':entry, 'code_sources':sources}
    write(output, report)
    print('Finished isolated fresh preparation:', source.name, round(report['performance']['wall_seconds'], 3), flush=True)


def compare(before, after):
    keys = [str(i) for i in range(len(before['phases']))]
    checked = proof.compare_reports(before, after, publication_keys=keys)
    references = {}; materializations = {}
    for key in keys:
        old, new = before['phases'][key], after['phases'][key]
        for left,right in [(old['verified']['manifest'], new['verified']['manifest']),
                           *zip(old['lineages'], new['lineages'])]:
            references[proof.digest(proof.reference(right))] = proof.reference(left)
        materializations[new['verified']['manifest']['id']] = old['verified']['manifest']['id']
    def translate(value):
        if isinstance(value, dict):
            if set(value) == {'id','version','content_sha256'}:
                return deepcopy(references.get(proof.digest(value), value))
            return {k:translate(v) for k,v in value.items()}
        if isinstance(value, list): return [translate(v) for v in value]
        return materializations.get(value, value) if isinstance(value, str) else value
    prepared = translate(after['prepared']); prepared.pop('prepared_id')
    for member in prepared['members']:
        member['materializations'].sort(key=lambda r:r['id'])
    prepared['prepared_id'] = 'PREPARED_' + proof.digest(prepared)
    proof.require(prepared == before['prepared'], 'prepared phase changed beyond proven references')
    loaded = translate(after['loaded'])
    for item in loaded:
        proof.require(item['lineage']['prepared_id'] == after['prepared']['prepared_id'], 'unknown prepared identity')
        item['lineage']['prepared_id'] = prepared['prepared_id']
    proof.require(loaded == before['loaded'], 'aligned values, missingness, Target lineage or phase changed')
    # P1 artifacts embed the aligned sample and its exact producer lineage.
    # Translate only the references already proven above, never metric fields.
    proof.require(translate(after['decisions']) == before['decisions'], 'P1 scientific decisions changed')
    proof.require(before['dimensions'] == after['dimensions'], 'fixture dimensions changed')
    proof.require(after['cache_high_water_bytes'] <= 128*1024*1024, 'retained cache exceeded budget')
    return {'exact_scientific_equality':True, 'publications_verified':len(checked['phases']),
            'five_horizons_equal':True, 'P1_decisions_equal':True, 'dimensions':before['dimensions'],
            'source_admission_boundary':before['source_admission_boundary'],
            'baseline':before['performance'], 'candidate':after['performance'],
            'candidate_cache_high_water_bytes':after['cache_high_water_bytes'], 'production_data_used':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=2, choices=(1,2,3))
    parser.add_argument('--production-shape', action='store_true')
    parser.add_argument('--child', choices=('build','run'))
    parser.add_argument('--source', type=Path); parser.add_argument('--fixture', type=Path)
    args = parser.parse_args()
    if args.child:
        if args.source is None or args.fixture is None:
            parser.error('internal child needs source and fixture')
        isolated_child(args.source, args.fixture)
    if args.child == 'build':
        result = benchmark.build(args.source, args.fixture, member_count=18, cases=('diff63_positive',),
                                 production_shape=args.production_shape, fresh_features=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n'); return
    if args.child == 'run': run(args.source, args.fixture, args.output); return
    benchmark.locked_environment(ROOT)
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='gambit-fresh-preparation-') as tmp:
        tmp = Path(tmp); sources = {'baseline':tmp/'baseline', 'candidate':tmp/'candidate'}
        benchmark.source_copy(ROOT, sources['baseline'], BASELINE)
        benchmark.source_copy(ROOT, sources['candidate'])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', GAMBIT_ISOLATED_TEST='1', GAMBIT_FX_LINEAGE_STORAGE='packed_v1')
        command = [sys.executable, '-B', str(Path(__file__).resolve())]
        seed = tmp/'seed'
        subprocess.run(command+['--child','build','--source',str(sources['baseline']), '--fixture',str(seed),
            '--output',str(args.output/'fixture.json')]+(['--production-shape'] if args.production_shape else []), env=env, check=True)
        comparisons = []
        for repeat in range(args.repeats):
            reports = {}
            # Reverse order on the second repeat to expose warm machine effects.
            order = ('baseline','candidate') if repeat % 2 == 0 else ('candidate','baseline')
            for name in order:
                with tempfile.TemporaryDirectory(dir=tmp, prefix='run-') as folder:
                    root = Path(folder)/'store'; benchmark.copy_store(seed, root)
                    output = args.output/(str(repeat)+'-'+name+'.json.gz')
                    subprocess.run(command+['--child','run','--source',str(sources[name]),'--fixture',str(root),
                        '--output',str(output)], env=env, check=True)
                    reports[name] = output
            comparisons.append(compare(read(reports['baseline']), read(reports['candidate'])))
        result = {'baseline_commit':BASELINE, 'source_trees':{name:benchmark.tree_identity(path) for name,path in sources.items()},
                  'repeats':comparisons, 'production_data_used':False,
                  'scope':'Fresh P1 preparation, all five horizon reads and P1 evaluation. P2/recovery covered separately by regression tests.'}
        (args.output/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
