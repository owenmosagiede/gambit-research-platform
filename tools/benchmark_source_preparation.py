#!/usr/bin/env python3
"""Offline preparation with real persisted provider-to-price verification.

All observations and approvals are synthetic. No production store argument is
accepted. Source admission, closure reads, normalized legs, oriented prices,
Feature publication/replay, five Target alignments and P1 are unmocked. Only
discovery of the isolated recipe/Scope bindings is supplied by the fixture.
"""
from contextlib import ExitStack
from copy import deepcopy
from datetime import date
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preparation_benchmark', ROOT/'tools/benchmark_preparation.py')
prep = importlib.util.module_from_spec(spec); spec.loader.exec_module(prep)
bench = prep.benchmark


def build(source, destination, *, long_history=False, p2_case=None):
    bench.load_source(source)
    from test_fx_onboarding import build_fixture
    from test_fx_targets import approve
    from test_feature_store import _copy_metadata_closure
    from test_research_inputs import approved_profile
    from test_research_policy_inputs import scheduled_profile
    from data.fx_onboarding import onboard
    from data.feature_store import FeatureStore
    from data.fx_currency_catalog import publish_prices, resolve_prices
    from data.fx_feature_store import _dates
    from data.fx_feature_recipes import _policy_records, _typed_parameters, build_fx_feature
    from data.reusable_features import _definition
    from data.reusable_feature_contracts import CURRENCY_INPUT_CONTRACT, RECIPE_KIND, make_record
    from data.transformations.registry import Registry
    from data.transformations.identity import reference
    from data.targets.fx import materialize
    from data.targets.store import TargetStore
    from research.feature_applications import install_binding, CURRENCY_QUOTE
    from research import inputs
    # The short-history control has the same 18-member, two-chunk P1 geometry.
    days = list(_dates('1979-12-24' if long_history else '2019-01-01',
                       '2026-09-04' if long_history or p2_case else '2022-12-30'))
    def price(number, day):
        t = (date.fromisoformat(day)-date(1979,12,24)).days / 7 * 5
        return 10 * math.exp(.00004*(number+1)*t + .011*math.sin(t*.11+number*.9)
                             + .003*math.sin(t*.67+number*.7))
    workspace = destination.parent/'provider-fixture'; workspace.mkdir()
    root, legacy, audit, _ = build_fixture(workspace, days=days,
        source_days={'USD/CNH':[d for d in days if d >= '2020-04-14']}, price_function=price)
    print('Admitting persisted synthetic provider sources', len(days), flush=True)
    sources = onboard(root, legacy, audit, migration_time='2026-10-09T10:00:00Z')['sources']
    store = FeatureStore(root)
    batch = approve(store, {'approval_state':'approved','representation':'simple','horizons':[1,7,21,63,252],
        'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
        'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
        'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
    print('Publishing real currency price catalog', flush=True)
    catalog = publish_prices(root, {s['symbol']:s['pit_snapshot'] for s in sources}, batch,
        'ISOLATED BENCHMARK ONLY: synthetic currency source approval')
    _, instruments = resolve_prices(root, reference(catalog))
    desired = sorted(s for s in instruments if s.endswith('CHF'))
    registry = Registry(source)
    operator, parameters = {'diff63':('TR_BASE_change_diff', {'k':63}),
                            'volscale5':('TR_BASE_volscale_diff', {'k':5,'w':21})}.get(p2_case, ('TR_BASE_change_diff', {'k':63}))
    _copy_metadata_closure(root, [registry.operator(n) for n in ('TR_BASE_level_log',operator)]+
        [registry.get_policy(n) for n in ('POL_TRANSFORM_EXECUTION','POL_TRANSFORM_HISTORY')])
    (root/'config/fx_retrospective_completion.json').write_text(json.dumps({'return_policy':batch,'knowledge_cutoff':'2026-10-09'}))
    policy, evidence, payload, _ = _policy_records(root,'ISOLATED BENCHMARK ONLY',{'fixture':True})
    store.io.blob(payload,'json','fixture_policy',None); store.install_record(evidence); store.install_record(policy)
    policy = deepcopy(policy); policy.update(id='POL_TRANSFORM_EVALUATION_FX_CURRENCY_SNAPSHOT',version='2.0.0')
    store.install_record(policy)
    registry = Registry(root); op = registry.operator(operator)
    variant = {'operator':reference(op),'parameters':_typed_parameters(op,parameters),
        'grid_policy':op['body']['execution_contract']['grid_profile'],'mode':'log_first','parameter_frequency':'daily'}
    recipe = _definition(registry,policy,variant); body = deepcopy(recipe['body'])
    body['input_contract'] = deepcopy(CURRENCY_INPUT_CONTRACT)
    recipe = make_record(RECIPE_KIND,body,'Currency / quote: '+recipe['display_name'])
    store.install_record(recipe); install_binding(root,recipe,CURRENCY_QUOTE)
    profile = approved_profile()
    profile.update(id='RSPEC_ISOLATED_FULL_SOURCE_PREPARATION',periods={
        'P1':{'start_inclusive':'2020-04-14','end_exclusive':'2022-01-01'},
        'P2':{'start_inclusive':'2022-01-01','end_exclusive':'2026-09-01' if long_history or p2_case else '2023-01-01'}})
    profile = scheduled_profile(profile)
    profile['target_selection'].update(knowledge_cutoff='2026-10-09',selection_scope='currency_price_catalog',
        price_catalog=reference(catalog),source_snapshots={s:instruments[s]['price_snapshot'] for s in desired}, materializations={})
    (root/'config/fx_retrospective_completion.json').write_text(json.dumps({'return_policy':batch,'knowledge_cutoff':'2026-10-09'}))
    bindings = []
    for symbol in desired:
        current = instruments[symbol]
        feature = build_fx_feature(root,current,variant,registry=registry,evaluation_policy=policy)
        store.install_record(feature)
        bindings.append({'instrument_id':symbol,'feature':reference(feature),'source_view':feature['body']['recipe']['sources'][0]['source_view'],
                         'price_snapshot':current['price_snapshot']})
        print('Publishing five frozen Targets:', symbol, flush=True)
        targets = materialize(root,current['price_snapshot'],batch,knowledge_cutoff='2026-10-09')
        target_store = TargetStore(root)
        profile['target_selection']['materializations'][symbol] = {
            str(target_store.resolve(target_store.resolve(t['materialization'])['definition'])['body']['horizon']['amount']):t['materialization'] for t in targets}
    scope = {'id':'FX_ISOLATED_CCY_VS_CHF','version':'1.0.0','kind':'universe','members':desired,
        'reference':{'id':'FX_ISOLATED_CCY_VS_CHF','version':'1.0.0','content_sha256':'a'*64},
        'membership_snapshot':{'id':'SNAPSHOT_'+'b'*64,'version':'1.0.0','content_sha256':'c'*64},
        'reference_currency':'CHF','research_basis':'currency_against_quote_reference','price_catalog':reference(catalog)}
    def project(feature):
        binding = next(b for b in bindings if b['feature'] == reference(feature))
        if feature != build_fx_feature(root,binding,variant,registry=registry,evaluation_policy=policy):
            raise ValueError('Fixture Feature recipe differs')
        return deepcopy(recipe)
    intent = {'feature':{k:recipe[k] for k in ('id','version')},'scope':{k:scope[k] for k in ('id','version')},
              'target_family':'price_return','expected_direction':'POSITIVE'}
    with ExitStack() as stack:
        for name,value in [('resolve_scope',scope),('load_reusable_recipe',recipe),
                           ('legacy_bindings_for_recipe',bindings),('legacy_recipe_projector',project)]:
            stack.enter_context(patch.object(inputs,name,return_value=value))
        plan = inputs.resolve_plan(root,intent,profile)
    inputs._validate_plan(plan)
    fixture = {'schema':'full_source_preparation_fixture_v1','profile':profile,'plans':{'diff63_positive':plan},
        'scheduled_source_dates':len(days),'source_admission':'real provider adapter, closure, normalized legs and oriented prices; synthetic observations only',
        'source_date_range':[days[0],days[-1]],'source_snapshots':{s['symbol']:s['pit_snapshot'] for s in sources}}
    (root/'benchmark-fixture.json').write_bytes(bench.canonical(fixture))
    bench.copy_store(root,destination)
    return {'fixture_sha256':prep.proof.digest(fixture),'source_dates':len(days),'members':len(desired),'periods':plan['periods']}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--long-history',action='store_true')
    parser.add_argument('--repeats',type=int,choices=(1,2,3),default=2)
    parser.add_argument('--child',choices=('build','run'))
    parser.add_argument('--source',type=Path); parser.add_argument('--fixture',type=Path)
    args = parser.parse_args()
    if args.child:
        prep.isolated_child(args.source,args.fixture)
        if args.child == 'build':
            args.output.write_text(json.dumps(build(args.source,args.fixture,long_history=args.long_history),indent=2)+'\n')
        else: prep.run(args.source,args.fixture,args.output)
        return
    bench.locked_environment(ROOT); args.output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='gambit-fresh-preparation-') as folder:
        tmp = Path(folder); sources = {'baseline':tmp/'baseline','candidate':tmp/'candidate'}
        bench.source_copy(ROOT,sources['baseline'],prep.BASELINE); bench.source_copy(ROOT,sources['candidate'])
        # Fixture construction uses the same approved source algorithms. The
        # extended provider fixture generator is test-only, shared by both runs.
        shutil.copyfile(ROOT/'tests/test_fx_onboarding.py',sources['baseline']/'tests/test_fx_onboarding.py')
        env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GAMBIT_ISOLATED_TEST='1',GAMBIT_FX_LINEAGE_STORAGE='packed_v1')
        cmd = [sys.executable,'-B',str(Path(__file__).resolve())]; seed = tmp/'seed'
        subprocess.run(cmd+['--child','build','--source',str(sources['baseline']),'--fixture',str(seed),
            '--output',str(args.output/'fixture.json')]+(['--long-history'] if args.long_history else []),env=env,check=True)
        comparisons = []
        for repeat in range(args.repeats):
            reports = {}
            for name in (('baseline','candidate') if repeat%2 == 0 else ('candidate','baseline')):
                with tempfile.TemporaryDirectory(dir=tmp,prefix='run-') as run:
                    root = Path(run)/'store'; bench.copy_store(seed,root)
                    output = args.output/f'{repeat}-{name}.json.gz'
                    subprocess.run(cmd+['--child','run','--source',str(sources[name]),'--fixture',str(root),
                        '--output',str(output)],env=env,check=True)
                    reports[name] = output
            comparisons.append(prep.compare(prep.read(reports['baseline']),prep.read(reports['candidate'])))
        gate = performance_gate(comparisons)
        (args.output/'comparison.json').write_text(json.dumps({'baseline_commit':prep.BASELINE,
            'source_trees':{n:bench.tree_identity(p) for n,p in sources.items()},'repeats':comparisons,
            'source_verification_mocked':False,'production_data_used':False,'performance_gate':gate},indent=2)+'\n')
        print(json.dumps(gate),flush=True)


def performance_gate(comparisons):
    results = []
    for row in comparisons:
        before,after = row['baseline_preparation'],row['candidate_preparation']
        old,new = (r['timings']['feature.preparation']['wall_seconds'] for r in (before,after))
        old_calls,new_calls = (r['timings']['source_prices.verify']['calls'] for r in (before,after))
        results.append({'preparation_reduction_percent':100*(1-new/old),
            'full_source_verifications_before':old_calls,'full_source_verifications_after':new_calls,
            'passed':row.get('source_verification_mocked') is False and row['exact_scientific_equality'] and new <= old*.9 and new_calls < old_calls
                and row['candidate']['wall_seconds'] < row['baseline']['wall_seconds']})
    return {'passed':len(results)>=2 and all(r['passed'] for r in results),
        'requirement':'At least two reversed-order runs; >=10% preparation reduction each, fewer full source replays, lower combined time and exact scientific equality',
        'repeats':results,'production_eta_claimed':False}


if __name__ == '__main__': main()
