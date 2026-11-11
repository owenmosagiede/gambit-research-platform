"""Freeze and submit the registered per-pair equivalents of the 53 momentum recipes."""

import argparse
from hashlib import sha256
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from data.fx_pipeline import list_instruments
from data.reusable_features import legacy_bindings_for_recipe, load_reusable_recipe
from data.scopes import PAIR_IDS
from data.transformations.identity import reference
from research.contracts import ResearchBlocked, canonical, digest, ref
from research.schedule import load_schedule
from research.store import install_bytes, lock, read_json
from runtime.experiment_identity import freeze
from runtime.research_jobs import ResearchJobs, implementation


def formula(recipe):
    body = recipe['body']
    return digest({name: body[name] for name in ('steps', 'output_contract', 'output_node',
                                                 'history_policy', 'execution_policy')})


def build(root, source):
    raw = source.read_bytes()
    previous = read_json(source)
    if previous['program_id'] != 'GAMBIT_CS_MOMENTUM_20261025_V1' or len(previous['recipes']) != 53:
        raise ValueError('Expected the frozen 53-recipe momentum program')
    schedule = load_schedule(root)
    if schedule is None:
        raise ValueError('The prospective research schedule must be active')
    registered = {}
    for path in sorted((root / 'definitions/feature_recipes').glob('*/*.json')):
        item = read_json(path)
        if item['body'].get('input_contract', {}).get('source_profile') != 'fx_price.1.0.0':
            continue
        item = load_reusable_recipe(root, item['id'], item['version'])
        key = formula(item)
        if key in registered:
            raise ValueError('More than one registered pair recipe matches a momentum formula')
        registered[key] = item
    prices = {item['instrument_id']: item['price_coverage']['start'] for item in list_instruments(root)}
    if set(prices) != set(PAIR_IDS):
        raise ValueError('The registered time-series universe differs from the approved 43 pairs')
    # EURUSD with the first frozen recipe is the first ordinary production request.
    symbols = ['EURUSD', *sorted(set(PAIR_IDS) - {'EURUSD'})]
    entries, unresolved = [], []
    source_sha = sha256(raw).hexdigest()
    matched = set()
    for row in previous['recipes']:
        original = row['reference']
        currency = load_reusable_recipe(root, original['id'], original['version'])
        if reference(currency) != original:
            raise ValueError('A source momentum formula differs from the frozen program')
        recipe = registered[formula(currency)]
        if recipe['id'] in matched:
            raise ValueError('Momentum formulas do not map one-to-one to pair recipes')
        matched.add(recipe['id'])
        bound = {row['instrument_id'] for row in legacy_bindings_for_recipe(
            root, reference(recipe), verify_features=False)}
        for symbol in symbols:
            if symbol not in bound:
                unresolved.append({'recipe': recipe['id'], 'scope': symbol, 'reason': 'FEATURE_BINDING_MISSING'})
                continue
            request = {'feature': {'id': recipe['id'], 'version': recipe['version']},
                       'target_family': 'price_return', 'scope': {'id': symbol, 'version': '1.0.0'},
                       'expected_direction': 'POSITIVE'}
            request['request_id'] = str(uuid5(NAMESPACE_URL, digest([source_sha, ref(schedule), request])))
            entries.append(request)
    if len(entries) + len(unresolved) != 43 * 53:
        raise ValueError('The candidate roster does not reconcile to the TS momentum grid')
    return {'program': 'GAMBIT_TS_MOMENTUM_20261111', 'schedule': ref(schedule),
            'source_program_sha256': source_sha, 'entries': entries, 'unresolved': unresolved}


def verify(root, path):
    manifest = read_json(path)
    schedule = load_schedule(root)
    if schedule is None or manifest['schedule'] != ref(schedule):
        raise ValueError('The intake manifest does not use the installed research schedule')
    entries = manifest['entries']
    if manifest['program'] != 'GAMBIT_TS_MOMENTUM_20261111' or len(entries) != len({r['request_id'] for r in entries}):
        raise ValueError('The intake manifest identity or request roster differs')
    return manifest


def launch(root, manifest_path, checkpoint_path, *, count=None):
    with lock(root, 'ts-momentum-intake', nonblocking=True) as acquired:
        if not acquired:
            raise ValueError('The time-series momentum intake is already running')
        return submit_manifest(root, manifest_path, checkpoint_path, count=count)


def submit_manifest(root, manifest_path, checkpoint_path, *, count):
    manifest = verify(root, manifest_path)
    manifest_sha = sha256(manifest_path.read_bytes()).hexdigest()
    state = read_json(checkpoint_path) if checkpoint_path.exists() else {
        'manifest_sha256': manifest_sha, 'next_index': 0, 'created': 0, 'existing': 0, 'blocked': [],
    }
    if state['manifest_sha256'] != manifest_sha:
        raise ValueError('The checkpoint belongs to a different intake manifest')
    entries = manifest['entries']
    start = state['next_index']
    if not 0 <= start <= len(entries):
        raise ValueError('The intake checkpoint is outside the frozen roster')
    end = len(entries) if count is None else min(len(entries), start + count)
    jobs = ResearchJobs(root)
    try:
        for index in range(start, end):
            request = entries[index]
            try:
                _, created = jobs.submit(request)
            except ResearchBlocked as error:
                state['blocked'].append({'request_id': request['request_id'], 'blockers': error.blockers})
            else:
                state['created' if created else 'existing'] += 1
            state['next_index'] = index + 1
            install_bytes(checkpoint_path, canonical(state) + b'\n', mutable=True)
            if index == start or state['next_index'] % 25 == 0 or index + 1 == end:
                print(f'Processed {index + 1}/{len(entries)} requests. '
                      f'{state["created"]} created, {state["existing"]} existing, '
                      f'{len(state["blocked"])} blocked.', flush=True)
    finally:
        jobs.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--manifest', type=Path, required=True)
    actions = parser.add_subparsers(dest='action', required=True)
    prepare = actions.add_parser('prepare')
    prepare.add_argument('source', type=Path)
    actions.add_parser('verify-first')
    submit = actions.add_parser('submit')
    submit.add_argument('checkpoint', type=Path)
    submit.add_argument('--count', type=int)
    args = parser.parse_args()
    if args.action == 'prepare':
        manifest = build(args.root, args.source)
        install_bytes(args.manifest, canonical(manifest) + b'\n')
        print(f'{len(manifest["entries"])} registered requests; {len(manifest["unresolved"])} missing bindings.')
    elif args.action == 'verify-first':
        manifest = verify(args.root, args.manifest)
        intent = {key: value for key, value in manifest['entries'][0].items() if key != 'request_id'}
        jobs = ResearchJobs(args.root)
        try:
            plan = freeze(jobs, intent, implementation())['frozen_plan']
            print(canonical({k: plan[k] for k in ('horizons', 'periods', 'horizon_periods')}).decode())
        finally:
            jobs.close()
    else:
        if args.count is not None and args.count < 1:
            parser.error('--count must be positive')
        launch(args.root, args.manifest, args.checkpoint, count=args.count)


if __name__ == '__main__':
    main()
