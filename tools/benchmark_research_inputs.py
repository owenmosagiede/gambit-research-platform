#!/usr/bin/env python3
"""Reproducible isolated stored-input comparison; never accepts a production store.

Both versions run copies of one baseline-built synthetic store. Source admission
and registry discovery are synthetic fixture boundaries; Feature verification,
Target reconstruction, phase isolation, kernels, artifacts and the request worker
are real. This is not a production-scale forecast or a provider I/O benchmark.
"""
import argparse
import ast
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import io
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = '9654b7de0b90d7f9a85718638effc271f6d6c6e1'
CASES = ('diff1_positive', 'diff5_positive', 'diff5_negative', 'diff63_positive', 'ew21_positive')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def locked_environment(source):
    data = (source / 'requirements-cloud.lock').read_bytes()
    versions = {name: {'required': version, 'installed': importlib.metadata.version(name)}
                for name, version in re.findall(r'^([A-Za-z0-9_.-]+)==([^\s]+)', data.decode(), re.M)}
    if not versions or any(v['required'] != v['installed'] for v in versions.values()):
        raise ValueError('Benchmark requires every exact locked dependency version')
    return {'lockfile_sha256': sha(data), 'packages': versions,
            'python': sys.version, 'platform': platform.platform(), 'cpu_count': os.cpu_count()}


def compare_saved_closures(old, new):
    if 'research.contracts' not in sys.modules:
        sys.path.insert(0, str(ROOT / 'src'))
    spec = importlib.util.spec_from_file_location('research_benchmark_closure', ROOT / 'tools/research_benchmark_closure.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.compare_closures(old, new)


def compare_reports(old, new):
    fields = ('case', 'loaded_inputs_sha256', 'complete_calculation_sha256', 'phase_access', 'horizons')
    if not old['loaded_inputs_sha256'] or not old['complete_calculation_sha256']:
        raise ValueError('Empty evidence cannot prove scientific equivalence')
    differences = [key for key in fields if old[key] != new[key]]
    if 'saved_scientific_closure' not in old or 'saved_scientific_closure' not in new:
        raise ValueError('Saved authoritative result closure is required')
    saved = compare_saved_closures(old['saved_scientific_closure'], new['saved_scientific_closure'])
    if not saved['exact_saved_scientific_equality']: differences.append('saved_scientific_closure')
    return {'case': old['case'], 'exact_scientific_equality': not differences,
            'differing_evidence': differences, 'saved_closure_comparison': saved,
            'baseline_wall_seconds': old['end_to_end']['wall_seconds'],
            'optimized_wall_seconds': new['end_to_end']['wall_seconds']}


def fixture_builder_identity(source_text):
    names = {'build', 'fixture_boundary', 'load_source', 'source_copy', 'copy_store', 'canonical', 'sha'}
    functions = [node for node in ast.parse(source_text).body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in functions} != names: raise ValueError('Fixture builder source is incomplete')
    return sha(ast.dump(ast.Module(body=functions, type_ignores=[]), include_attributes=False).encode())


def tree_identity(root):
    names = {str(p.relative_to(root)): sha(p.read_bytes()) for p in root.rglob('*')
             if p.is_file() and p.suffix not in ('.pyc', '.lock') and '__pycache__' not in p.parts}
    return {'sha256': sha(canonical(names)), 'files': len(names)}


def copy_store(source, target, *, merge=False):
    if sys.platform == 'darwin':
        # APFS clone files share immutable payload extents until changed.
        subprocess.run(['cp', '-cR', str(source) + ('/.' if merge else ''), str(target)], check=True)
    else:
        shutil.copytree(source, target, dirs_exist_ok=merge)


def source_copy(source, target, revision=None):
    if (source / 'storage').exists():
        raise ValueError('Only source-only checkouts are accepted; storage is forbidden')
    if revision:
        data = subprocess.check_output(['git', '-C', str(source), 'archive', '--format=tar', revision])
        target.mkdir()
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(target, filter='data')
    else:
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(
            '.git', '__pycache__', '.venv*', 'node_modules', 'outputs', 'dist', '*.log', '*.tar.gz', 'release-checks.json'))
    fixture = target / 'tests/fixtures/registry_support'
    for row in json.loads((fixture / 'manifest.json').read_text())['files']:
        rel = Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Unsafe fixture path')
        data = (fixture / rel).read_bytes()
        if sha(data) != row['sha256'] or len(data) != row['bytes']:
            raise ValueError('Approved policy fixture checksum mismatch')
        dest = target / rel; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)


def load_source(source):
    sys.path[:0] = [str(source / 'src'), str(source / 'tests')]
    # The baseline remains unmodified. Measurement is an external observational
    # wrapper, loaded from this tool's release when the old module is absent.
    try:
        from research import performance
    except ImportError:
        spec = importlib.util.spec_from_file_location('research.performance', ROOT / 'src/research/performance.py')
        performance = importlib.util.module_from_spec(spec)
        sys.modules['research.performance'] = performance; spec.loader.exec_module(performance)
    return performance


@contextmanager
def fixture_boundary(root, fixture):
    """Replace only approved-source admission with frozen synthetic observations."""
    from data.transformations.identity import reference
    def prices(store, binding, policy, verify_rows=True):
        snapshot, values = fixture['states'][binding['id']]
        if store.resolve(binding) != snapshot or reference(snapshot) != binding:
            raise AssertionError('Synthetic source binding changed')
        return deepcopy(snapshot), deepcopy(values) if verify_rows else None
    with ExitStack() as stack:
        for module in ('research.inputs', 'data.fx_feature_store', 'data.targets.fx'):
            stack.enter_context(patch(module + '._price_snapshot', side_effect=prices))
        yield


def build(source, destination, *, member_count=5, cases=CASES, scheduled_dates=None, production_shape=False, resume_checkpoint=None):
    load_source(source)
    from data.feature_store import FeatureStore
    from data.fx_feature_recipes import build_fx_feature, get_fx_policy, _typed_parameters
    from data.reusable_features import _definition, _project_legacy
    from data.transformations.registry import Registry
    from data.transformations.identity import reference, digest
    from research import inputs
    from research.p1_discovery import run_p1
    from research.feature_applications import install_binding, PER_MEMBER, CURRENCY_QUOTE
    from data.verified_inputs import execution_inputs
    from runtime.research_jobs import implementation
    from test_feature_store import _copy_metadata_closure
    from test_research_end_to_end import StoredResearchEndToEndTests
    from test_research_policy_inputs import scheduled_profile
    f = StoredResearchEndToEndTests(methodName='runTest'); f.setUp()
    try:
        if resume_checkpoint:
            metadata = json.loads((resume_checkpoint / 'metadata.json').read_text())
            if (metadata['schema'] != 'isolated_momentum_fixture_checkpoint_v1'
                    or metadata['baseline_commit'] != BASELINE_COMMIT
                    or metadata['production_shape'] != production_shape or metadata['members'] != member_count
                    or metadata['lineage'] != os.environ.get('GAMBIT_FX_LINEAGE_STORAGE', 'loose')):
                raise ValueError('Checkpoint build provenance differs')
            checkpoint = resume_checkpoint / 'store'
            actual = {str(p.relative_to(checkpoint)): sha(p.read_bytes()) for p in checkpoint.rglob('*')
                      if p.is_file() and p.suffix not in ('.pyc', '.lock') and '__pycache__' not in p.parts}
            if actual != metadata['files']: raise ValueError('Checkpoint files changed')
            copy_store(checkpoint, f.root, merge=True)
            print('Resumed exact baseline fixture checkpoint', len(actual), 'files', flush=True)
        # The legacy five-member fixture remains a regression control. The
        # larger fixture uses 18 synthetic preoriented USD sources, and the real
        # currency application/Feature/Target paths. Provider traversal is excluded.
        import math
        cutoff = '2026-09-07' if production_shape else '2024-05-02'
        captured_at = '2026-09-06T12:00:00.000000Z' if production_shape else '2024-05-01T12:00:00.000000Z'
        if production_shape:
            if member_count != 18 or scheduled_dates is not None:
                raise ValueError('Production-shape fixture requires 18 currencies and no alternate date count')
            from data.fx_feature_store import _dates
            f.days = list(_dates('1979-12-24', '2026-09-04'))
            f.profile['periods'] = {'P1': {'start_inclusive': '2020-04-14', 'end_exclusive': '2022-01-01'},
                'P2': {'start_inclusive': '2022-01-01', 'end_exclusive': '2026-09-01'}}
            f.profile['target_selection']['knowledge_cutoff'] = cutoff
            (f.root / 'config/fx_retrospective_completion.json').write_text(json.dumps({
                'return_policy': f.fx.batch, 'knowledge_cutoff': cutoff}))
            structural_patch = patch('research.inputs._structural_start',
                side_effect=lambda store, snapshot: snapshot['body'].get('valid_coverage', snapshot['body']['coverage'])['start'])
            structural_patch.start(); f.addCleanup(structural_patch.stop)
        if scheduled_dates is not None:
            if member_count != 18: raise ValueError('Long-history fixture requires currency application')
            from datetime import date, timedelta
            last = date(2022, 5, 31); days = []
            while len(days) < scheduled_dates:
                if last.weekday() < 5: days.append(last.isoformat())
                last -= timedelta(days=1)
            f.days = sorted(days)
            split = f.days[int(scheduled_dates * .77)]
            f.profile['periods'] = {'P1': {'start_inclusive': f.days[0], 'end_exclusive': split},
                'P2': {'start_inclusive': split, 'end_exclusive': '2022-06-01'}}
        from decimal import Decimal
        from data.fx_records import make_record
        from data.transformations.contracts import decimal_text
        from data.transformations.fx_currency import CURRENCIES
        from data.targets.fx import materialize
        desired = ['AUDUSD', 'EURUSD', 'GBPUSD', 'NZDUSD', 'CADUSD']
        desired += sorted(c + 'USD' for c in CURRENCIES if c != 'USD' and c + 'USD' not in desired)
        desired = list(f.symbols) if member_count == 5 else sorted(desired[:member_count])
        oriented = member_count == 18
        price_profile = 'fx_currency_price.1.0.0' if oriented else 'fx_price.1.0.0'
        existing = {} if oriented else {r['instrument_id']: r for r in f.current}
        for index, symbol in enumerate(desired):
            if symbol in existing: continue
            meta = dict(f.fx.meta, base_currency=symbol[:3], quote_currency='USD', unit='USD_per_' + symbol[:3])
            dataset = f.store.install_record(make_record('dataset_definition', {
                'kind': 'fx_constructed_dataset', 'profile': price_profile, 'instrument_id': symbol,
                'source_metadata': meta}, 'ISOLATED synthetic ' + symbol))
            view = f.store.install_record(make_record('source_view_definition', {
                'kind': 'fx_constructed_view', 'profile': price_profile, 'dataset': dataset, 'source_metadata': meta}))
            construction = f.store.install_record(make_record('transformation_definition', {
                'kind': 'ISOLATED_SYNTHETIC_PRICE_ADMISSION', 'instrument_id': symbol}))
            snapshot = make_record('snapshot_manifest', {'kind': 'fx_constructed_prices', 'profile': price_profile,
                'instrument_id': symbol, 'economic_id': 'FX_' + symbol[:3] + '_USD', 'definition': view,
                'recipe': construction, 'source_metadata': meta, 'coverage': {'start': f.days[0], 'end': f.days[-1]},
                'valid_coverage': {'start': '2020-04-14' if production_shape and symbol == 'CNHUSD' else f.days[0],
                                   'end': f.days[-1]}})
            binding = f.store.install_record(snapshot); prices = []
            for t, day in enumerate(f.days):
                level = 100 * math.exp(.0008 * (index + 1) * t + .011 * math.sin(t * .11 + index * .9)
                                       + .003 * math.sin(t * .67 + index * .7))
                row = {'reference_time': day, 'value': decimal_text(Decimal(str(level))), 'status': 'valid',
                       'reason_code': None, 'available_at': None, 'original_ingested_at': captured_at,
                       'input_dependencies': [{'original_ingested_at': captured_at}]}
                if production_shape and symbol == 'CNHUSD' and day < '2020-04-14':
                    row.update(value=None, status='missing', reason_code='missing_source_value')
                row['id'] = 'FXPRICE_' + digest(row); prices.append(row)
            f.states[binding['id']] = (snapshot, prices)
            existing[symbol] = {'instrument_id': symbol, 'price_snapshot': binding}
            saved_targets = []
            if resume_checkpoint:
                for path in (f.root / 'storage/catalog/target_store').glob('*/manifest.json'):
                    row = json.loads(path.read_text())
                    if row.get('price_snapshot') == binding and row['input_key']['knowledge_cutoff'] == cutoff:
                        saved_targets.append(row)
            if len(saved_targets) != 5:
                materialize(f.root, binding, f.fx.batch, knowledge_cutoff=cutoff)
        f.symbols[:] = desired; f.current[:] = [existing[s] for s in desired]
        registry_source = Registry(source)
        _copy_metadata_closure(f.root, [registry_source.operator('TR_BASE_smooth_ew_change')])
        registry, policy = Registry(f.root), get_fx_policy(f.root)
        if oriented:
            policy = deepcopy(policy)
            policy.update(id='POL_TRANSFORM_EVALUATION_FX_CURRENCY_SNAPSHOT', version='2.0.0')
            f.store.install_record(policy)
            catalog = make_record('onboarding_evidence', {'kind': 'ISOLATED_CURRENCY_PRICE_CATALOG',
                'return_policy': f.fx.batch, 'members': desired})
            catalog_ref = f.store.install_record(catalog)
            f.scope.update(reference_currency='USD', research_basis='currency_against_quote_reference',
                           price_catalog=catalog_ref)
            catalog_patch = patch('data.fx_currency_catalog.resolve_prices',
                return_value=(catalog, {r['instrument_id']: r for r in f.current}))
            catalog_patch.start(); f.addCleanup(catalog_patch.stop)
        profile = scheduled_profile(f.profile)
        profile['id'] = 'RSPEC_ISOLATED_PERFORMANCE'
        targets = {s: {} for s in f.symbols}
        target_store = inputs.TargetStore(f.root)
        for path in (f.root / 'storage/catalog/target_store').glob('*/manifest.json'):
            m = json.loads(path.read_text()); definition = target_store.resolve(m['definition'])
            symbol = target_store.resolve(m['price_snapshot'])['body']['instrument_id']
            if symbol in targets and m['price_snapshot'] == existing[symbol]['price_snapshot']:
                targets[symbol][str(definition['body']['horizon']['amount'])] = reference(m)
        profile['target_selection'].update(selection_scope='registered_fx_registry',
            source_snapshots={r['instrument_id']: r['price_snapshot'] for r in f.current}, materializations=targets)
        if oriented:
            profile['target_selection'].update(selection_scope='currency_price_catalog', price_catalog=catalog_ref)
        from research.contracts import canonical as rc, ref
        pp = f.root / 'definitions/research_specs' / profile['id'] / (profile['version'] + '.json')
        pp.parent.mkdir(parents=True, exist_ok=True)
        if pp.exists() and pp.read_bytes() != rc(profile) + b'\n':
            raise ValueError('Checkpoint research profile differs')
        pp.write_bytes(rc(profile) + b'\n')
        (f.root / 'config/research_execution.json').write_bytes(rc({'research_spec': ref(profile)}) + b'\n')
        plans = {}; expected_p2 = {}
        for label, operator, parameters in (
                ('diff1', 'TR_BASE_change_diff', {'k': 1}),
                ('diff5', 'TR_BASE_change_diff', {'k': 5}),
                ('diff63', 'TR_BASE_change_diff', {'k': 63}),
                ('ew21', 'TR_BASE_smooth_ew_change', {'h': 21})):
            if not any(case.startswith(label + '_') for case in cases): continue
            print('Building isolated fixture:', member_count, label, flush=True)
            op = registry.operator(operator)
            variant = {'operator': reference(op), 'parameters': _typed_parameters(op, parameters),
                       'grid_policy': op['body']['execution_contract']['grid_profile'],
                       'mode': 'log_first', 'parameter_frequency': 'daily'}
            recipe = _definition(registry, policy, variant)
            if oriented:
                from data.reusable_feature_contracts import CURRENCY_INPUT_CONTRACT, RECIPE_KIND, make_record as reusable_record
                body = deepcopy(recipe['body']); body['input_contract'] = deepcopy(CURRENCY_INPUT_CONTRACT)
                recipe = reusable_record(RECIPE_KIND, body, 'Currency / quote: ' + recipe['display_name'])
            f.store.install_record(recipe)
            install_binding(f.root, recipe, CURRENCY_QUOTE if oriented else PER_MEMBER)
            bindings = []
            for current in f.current:
                feature = build_fx_feature(f.root, current, variant, registry=registry, evaluation_policy=policy)
                f.store.install_record(feature)
                bindings.append({'instrument_id': current['instrument_id'], 'feature': reference(feature),
                                 'source_view': feature['body']['recipe']['sources'][0]['source_view'],
                                 'price_snapshot': current['price_snapshot']})
            intent = {'feature': {'id': recipe['id'], 'version': recipe['version']},
                      'scope': {'id': f.scope['id'], 'version': f.scope['version']},
                      'target_family': 'price_return', 'expected_direction': 'POSITIVE'}
            with ExitStack() as stack:
                stack.enter_context(patch('research.inputs.load_reusable_recipe', return_value=recipe))
                stack.enter_context(patch('research.inputs.legacy_bindings_for_recipe', return_value=bindings))
                def projector(root, selected_recipe):
                    def project(feature):
                        if not oriented:
                            return _project_legacy(FeatureStore(root), feature, Registry(root), get_fx_policy(root),
                                                   {selected_recipe['id']: selected_recipe})
                        binding = next(b for b in bindings if b['feature'] == reference(feature))
                        expected = build_fx_feature(root, binding, variant, registry=Registry(root), evaluation_policy=policy)
                        if feature != expected: raise AssertionError('Synthetic currency Feature semantics changed')
                        return deepcopy(selected_recipe)
                    return project
                stack.enter_context(patch('research.inputs.legacy_recipe_projector', side_effect=projector))
                try:
                    plan = inputs.resolve_plan(f.root, intent, profile)
                except inputs.InputsBlocked as exc:
                    raise AssertionError(getattr(exc, 'reasons', str(exc))) from exc
                with execution_inputs(f.root, implementation()):
                    prepared = inputs.prepare_phase(f.root, plan, 'P1'); admitted = []
                    for horizon in plan['horizons']:
                        loaded = inputs.load_phase(f.root, plan, prepared, 'P1', horizon)
                        kp = dict(profile['kernel'], structural_common_start=plan['structural_common_start'],
                                  window_start=plan['periods']['P1']['start_inclusive'],
                                  window_end_exclusive=plan['periods']['P1']['end_exclusive'])
                        result = run_p1(loaded['rows'], mode='CS', horizon=horizon, members=f.symbols,
                                        expected_direction='POSITIVE', profile=kp)
                        if result['admission'] == 'admitted' and (result['metrics']['primary_effect'] or 0) > 0:
                            admitted.append(horizon)
                    if admitted and label + '_positive' in cases:
                        token = {'plan_id': plan['plan_id'], 'direction': 'POSITIVE', 'admitted_horizons': admitted}
                        inputs.prepare_phase(f.root, plan, 'P2', admission=token)
                plans[label + '_positive'] = inputs.resolve_plan(f.root, intent, profile)
                expected_p2[label + '_positive'] = admitted
                if label == 'diff5':
                    negative = dict(intent, expected_direction='NEGATIVE')
                    plans['diff5_negative'] = inputs.resolve_plan(f.root, negative, profile)
                    expected_p2['diff5_negative'] = []
        if 'diff5_positive' in expected_p2 and not expected_p2['diff5_positive']:
            raise AssertionError('Fixture must exercise real admitted P2')
        fixture = {'schema': 'isolated_momentum_performance_fixture_v1', 'profile': profile,
                   'plans': plans, 'states': f.states, 'expected_p2': expected_p2,
                   'horizons': [1, 7, 21, 63, 252], 'members': f.symbols, 'currency_application': oriented,
                   'scheduled_source_dates': len(f.days), 'production_shaped_dimensions': production_shape, 'source_date_range': [f.days[0], f.days[-1]],
                   'source_admission': 'synthetic exact pinned source fixture; real source provider traversal excluded',
                   'fixture_population': 'three recipes and opposite-direction control, not the production population'}
        (f.root / 'benchmark-fixture.json').write_bytes(canonical(fixture) + b'\n')
        copy_store(f.root, destination)
    finally:
        f.doCleanups()
    return {**tree_identity(destination), 'members': fixture['members'],
            'scheduled_source_dates': fixture['scheduled_source_dates'],
            'source_date_range': fixture['source_date_range'], 'periods': fixture['profile']['periods'],
            'expected_p2_horizons': fixture['expected_p2'],
            'currency_application': fixture['currency_application'],
            'plan_ids': {k: v['plan_id'] for k, v in fixture['plans'].items()}}


@contextmanager
def operational_wrappers(performance):
    """Same outer observational hooks around unmodified and optimized code."""
    from research import inputs
    from research.store import ResearchStore
    from runtime.research_jobs import ResearchJobs
    def wrap(function, name):
        def measured(*args, **kwargs):
            with performance.measure('benchmark.' + name):
                return function(*args, **kwargs)
        return measured
    with ExitStack() as stack:
        for owner, name, label in (
                (inputs, 'prepare_phase', 'feature.prepare'), (inputs, 'load_phase', 'inputs.load'),
                (inputs, '_verified_feature', 'feature.verify'), (inputs, '_load_target', 'target.verify'),
                (inputs, '_phase_target_rows', 'target.decode'), (inputs, 'construct_rows', 'target.reconstruct'),
                (ResearchStore, 'artifact', 'publication.artifacts'),
                (ResearchJobs, '_event_snapshot', 'events.replay')):
            stack.enter_context(patch.object(owner, name, wrap(getattr(owner, name), label)))
        yield


def run(source, fixture_root, case, output, *, warm=False):
    performance = load_source(source)
    from data.verified_inputs import execution_inputs
    from research import inputs
    from research.p1_discovery import run_p1
    from research.p2_validation import run_p2
    from runtime.research_jobs import ResearchJobs, implementation
    fixture_path = fixture_root / 'benchmark-fixture.json'
    fixture = json.loads(fixture_path.read_text())
    fixture_holder = {'serialized_bytes': fixture_path.stat().st_size,
        'source_rows': sum(len(value[1]) for value in fixture['states'].values()),
        'rss_high_water_before_worker_bytes': performance.peak_rss_bytes(),
        'note': 'Source states stay in memory as a synthetic admission fixture; process RSS includes this holder and startup. RSS deltas are not cache-size estimates.'}
    plan = fixture['plans'][case]; captured = {}; calculations = {}; access = []
    def identity(value):
        with performance.measure('benchmark.equivalence_capture'):
            return sha(canonical(value))
    class Adapter:
        def resolve_plan(self, root, intent, profile):
            if intent != plan['intent'] or profile != fixture['profile']:
                raise AssertionError('Frozen synthetic inputs changed')
            return deepcopy(plan)
        def prepare_phase(self, *args, **kwargs): return inputs.prepare_phase(*args, **kwargs)
        def load_phase(self, root, p, prepared, phase, horizon, **kwargs):
            result = inputs.load_phase(root, p, prepared, phase, horizon, **kwargs)
            key = phase + '.' + str(horizon); captured[key] = identity(result); access.append(key)
            return result
    class Kernels:
        def run_p1(self, rows, **kwargs):
            with performance.measure('benchmark.kernel.P1'): result = run_p1(rows, **kwargs)
            calculations['P1.' + str(kwargs['horizon'])] = identity(result); return result
        def run_p2(self, rows, **kwargs):
            with performance.measure('benchmark.kernel.P2'): result = run_p2(rows, **kwargs)
            calculations['P2.' + str(kwargs['horizon'])] = identity(result); return result
    with fixture_boundary(fixture_root, fixture), operational_wrappers(performance):
        jobs = ResearchJobs(fixture_root, adapter=Adapter(), kernels=Kernels())
        try:
            request = dict(plan['intent'], request_id='9b8b174a-d240-4450-84d3-d19f7df3fbf7')
            with performance.profiling() as profile:
                jobs.submit(request); jobs.run_pending_once(); job = jobs.get(request['request_id'])
            print('Execution finished:', case, round(profile.report()['wall_seconds'], 3), flush=True)
            if job['status'] != 'succeeded': raise AssertionError(job)
            p2 = sorted(int(v.split('.')[1]) for v in access if v.startswith('P2.'))
            if p2 != fixture['expected_p2'][case]: raise AssertionError(('Unexpected P2 access', case, p2))
            runtime = profile.report()
            from research_benchmark_closure import capture_closure
            saved_closure = capture_closure(jobs.store, job, expected_implementation=implementation())
            before = tree_identity(fixture_root)
            again, created = jobs.submit(request)
            if created or again['results'] != job['results'] or len(calculations) != len(access):
                raise AssertionError('Committed trial reuse failed')
            if before != tree_identity(fixture_root): raise AssertionError('Exact retry altered store')
            input_runs = []
            if warm:
                with execution_inputs(fixture_root, implementation()) as context:
                    for temperature in ('cold', 'warm'):
                        with performance.profiling() as detail:
                            prepared = inputs.prepare_phase(fixture_root, plan, 'P1')
                            actual = {f'P1.{h}': identity(inputs.load_phase(fixture_root, plan, prepared, 'P1', h))
                                      for h in plan['horizons']}
                        if actual != {k: v for k, v in captured.items() if k.startswith('P1.')}:
                            raise AssertionError('Warm inputs differ from exact cold inputs')
                        input_runs.append({'temperature': temperature, 'performance': detail.report(),
                                           'cache_counts_cumulative': dict(context.counts),
                                           'cache_seconds_cumulative': dict(context.seconds),
                                           'cache_retained_bytes': context.bytes, 'cache_limit_bytes': context.max_bytes})
            report = {'schema': 'isolated_research_benchmark_v1', 'case': case,
                      'source_implementation': implementation(), 'end_to_end': runtime,
                      'input_temperature_runs': input_runs, 'loaded_inputs_sha256': captured,
                      'complete_calculation_sha256': calculations, 'phase_access': access,
                      'horizons': job['horizons'], 'committed_retry_unchanged': True,
                      'saved_scientific_closure': saved_closure,
                      'process_environment': locked_environment(source),
                      'source_admission_boundary': fixture['source_admission'], 'fixture_holder': fixture_holder,
                      'lineage_storage_mode': os.environ.get('GAMBIT_FX_LINEAGE_STORAGE', 'loose')}
            output.write_text(json.dumps(report, indent=2) + '\n')
        finally:
            jobs.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    p.add_argument('--warm', action='store_true', help='Also compare repeated cold/warm P1 input passes')
    p.add_argument('--members', type=int, choices=(5, 18), default=5, help='5-member legacy control or 18-member common-USD currency application')
    p.add_argument('--production-shape', action='store_true',
                   help='12185 synthetic source dates, 449 P1 weekdays and 1216 P2 weekdays; no production observations')
    p.add_argument('--scheduled-dates', type=int, choices=(2600,), help='Long-history currency fixture')
    p.add_argument('--resume-checkpoint', type=Path, help='Resume an exact checksummed isolated baseline fixture checkpoint')
    p.add_argument('--fixture-cache', type=Path, help='Optional local synthetic fixture cache, checksummed before reuse')
    p.add_argument('--lineage', choices=('loose', 'packed_v1'), default='loose',
                   help='Physical lineage mode; identical for baseline and optimized')
    p.add_argument('--order', choices=('baseline-first', 'optimized-first'), default='baseline-first')
    p.add_argument('--parallel', type=int, choices=(1, 2), default=1,
                   help='Offline independent-store subprocess experiment only; not a production coordinator')
    p.add_argument('--child', choices=('build', 'run'))
    p.add_argument('--source', type=Path)
    p.add_argument('--fixture', type=Path)
    p.add_argument('--case', choices=CASES)
    a = p.parse_args()
    if a.child == 'build':
        a.output.write_text(json.dumps(build(a.source, a.fixture, member_count=a.members, cases=a.cases, scheduled_dates=a.scheduled_dates, production_shape=a.production_shape, resume_checkpoint=a.resume_checkpoint), indent=2) + '\n'); return
    if a.child == 'run':
        run(a.source, a.fixture, a.case, a.output, warm=a.warm); return
    if not a.baseline: p.error('--baseline is required')
    locked_environment(ROOT)
    baseline = a.baseline.resolve()
    actual = subprocess.check_output(['git', '-C', str(baseline), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(baseline), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    if actual != BASELINE_COMMIT or dirty:
        raise ValueError('Baseline must be clean unmodified ' + BASELINE_COMMIT)
    a.output.mkdir(parents=True, exist_ok=False)
    # No existing store path can be supplied by the user. All source/fixture/store
    # copies live under a fresh temporary directory and are removed on completion.
    with tempfile.TemporaryDirectory(prefix='gambit-offline-research-performance-') as tmp:
        tmp = Path(tmp); base = tmp / 'baseline-source'; optimized = tmp / 'optimized-source'
        source_copy(baseline, base, BASELINE_COMMIT); source_copy(ROOT, optimized)
        fixture = tmp / 'seed'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', GAMBIT_ISOLATED_TEST='1', GAMBIT_FX_LINEAGE_STORAGE=a.lineage)
        command = [sys.executable, str(optimized / 'tools/benchmark_research_inputs.py')]
        cache_key = {'baseline_commit': BASELINE_COMMIT, 'members': a.members, 'cases': a.cases,
                     'scheduled_dates': a.scheduled_dates, 'production_shape': a.production_shape, 'lineage': a.lineage,
                     'fixture_builder_sha256': fixture_builder_identity(Path(__file__).read_text()), 'environment': locked_environment(base)}
        if a.fixture_cache and a.fixture_cache.exists():
            metadata = json.loads((a.fixture_cache / 'metadata.json').read_text())
            prior_key = dict(metadata['key'])
            if 'tool_sha256' in prior_key:
                builder_source = (a.fixture_cache / 'builder_source.py').read_bytes()
                if sha(builder_source) != prior_key.pop('tool_sha256'):
                    raise ValueError('Original fixture builder source checksum differs')
                prior_key['fixture_builder_sha256'] = fixture_builder_identity(builder_source.decode())
            if prior_key != cache_key or tree_identity(a.fixture_cache / 'store') != metadata['fixture']:
                raise ValueError('Synthetic fixture cache differs from exact build configuration')
            copy_store(a.fixture_cache / 'store', fixture)
            (a.output / 'fixture.json').write_text(json.dumps(metadata['fixture_summary'], indent=2) + '\n')
        else:
            subprocess.run(command + ['--child', 'build', '--source', str(base), '--fixture', str(fixture),
                           '--output', str(a.output / 'fixture.json'), '--members', str(a.members), '--cases', *a.cases]
                           + (['--scheduled-dates', str(a.scheduled_dates)] if a.scheduled_dates else [])
                           + (['--production-shape'] if a.production_shape else [])
                           + (['--resume-checkpoint', str(a.resume_checkpoint.resolve())] if a.resume_checkpoint else []), env=env, check=True)
            if a.fixture_cache:
                a.fixture_cache.mkdir(parents=True, exist_ok=False)
                shutil.copy2(Path(__file__), a.fixture_cache / 'builder_source.py')
                copy_store(fixture, a.fixture_cache / 'store')
                (a.fixture_cache / 'metadata.json').write_text(json.dumps({'key': cache_key,
                    'fixture': tree_identity(fixture),
                    'fixture_summary': json.loads((a.output / 'fixture.json').read_text())}, indent=2) + '\n')
        versions = {}
        execution_order = [('baseline', base), ('optimized', optimized)]
        if a.order == 'optimized-first': execution_order.reverse()
        for version, source in execution_order:
            stores = []
            for case in a.cases:
                store = tmp / (version + '-' + case); copy_store(fixture, store); stores.append(store)
            started = time.perf_counter(); version_reports = []; active = []
            for number, case in enumerate(a.cases):
                store = stores[number]
                report = a.output / (version + '-' + case + '.json')
                child = command + ['--child', 'run', '--source', str(source), '--fixture', str(store),
                                   '--case', case, '--output', str(report)] + (['--warm'] if a.warm else [])
                active.append((subprocess.Popen(child, env=env), report))
                if len(active) == a.parallel or number == len(a.cases) - 1:
                    for process, result_path in active:
                        if process.wait() != 0: raise RuntimeError('Benchmark child failed: ' + str(result_path))
                        version_reports.append(json.loads(result_path.read_text()))
                    active = []
            elapsed = time.perf_counter() - started
            for store in stores: shutil.rmtree(store)
            versions[version] = {'observed_batch_wall_seconds': elapsed,
                                 'reports': version_reports}
        comparisons = []
        for old, new in zip(versions['baseline']['reports'], versions['optimized']['reports']):
            comparisons.append(compare_reports(old, new))
        summary = {'schema': 'research_performance_comparison_v1', 'baseline_commit': actual,
                   'fixture': json.loads((a.output / 'fixture.json').read_text()), 'parallel_processes': a.parallel, 'execution_order': [v for v, _ in execution_order],
                   'synthetic_member_count': a.members, 'lineage_storage_mode': a.lineage,
                   'scheduled_source_dates': 12185 if a.production_shape else a.scheduled_dates or 'original E2E interval',
                   'all_exact': all(c['exact_scientific_equality'] for c in comparisons), 'cases': comparisons,
                   'baseline_batch_wall_seconds': versions['baseline']['observed_batch_wall_seconds'],
                   'optimized_batch_wall_seconds': versions['optimized']['observed_batch_wall_seconds'],
                   'production_data_used': False,
                   'checkpoint_metadata_sha256': sha((a.resume_checkpoint / 'metadata.json').read_bytes()) if a.resume_checkpoint else None, 'production_coordinator_implemented': False,
                   'limitations': ['Synthetic source admission/catalog discovery; real stored Feature/Target and runtime paths.',
                                  'Warm means repeated P1 input access in one context; normal requests start fresh.',
                                  'Process RSS is lifetime maximum, not incremental cache memory.',
                                  'Batch wall includes process startup; excludes fixture construction/store cloning.',
                                  'Offline parallel workers use independent stores; no shared-writer safety claim.',
                                  'No full-program completion forecast.']}
        (a.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary), flush=True)
        if not summary['all_exact']: raise SystemExit('Exact scientific comparison failed')


if __name__ == '__main__': main()
