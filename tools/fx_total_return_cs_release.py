#!/usr/bin/env python3
"""Add matched currency CS funding Targets without replacing TS or old Scopes.

Run only through the reviewed data-release operator with code/backup controls.
The accepted queue must be empty and admissions remain closed. Config is last.
"""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from data import fx_funding, fx_funded_scopes
from data.feature_store import FeatureStore
from data.fx_currency_catalog import active_release
from data.fx_currency_release import profile_for
from data.fx_total_return_cs import CONFIG, SCHEMA, HORIZONS
from data.targets import fx_total
from data.targets.store import TargetStore
from data.transformations.contracts import normalize_reference
from data.transformations.fx_currency import REFERENCES
from data.transformations.identity import reference
from data.verified_inputs import execution_inputs, phase_inputs
from research.contracts import canonical, digest
from research.schedule import load_schedule
from research.store import read_json, lock, install_bytes
from fx_total_return_release import idle


def admissions_closed():
    return Path('/etc/gambit/research-admissions-closed').is_file()


def plan(root, request):
    root = Path(root).resolve()
    if set(request) != {'currency_release', 'funding_snapshot', 'funding_model', 'request_text'}:
        raise ValueError('Pin the exact currency release, funding snapshot/model and explicit request')
    for key in ('currency_release', 'funding_snapshot', 'funding_model'):
        normalize_reference(request[key])
    if not isinstance(request['request_text'], str) or not request['request_text'].strip():
        raise ValueError('Explicit matched currency-universe request evidence is required')
    idle(root)
    release = active_release(root)
    if release is None or reference(release) != request['currency_release']:
        raise ValueError('The reviewed currency release must remain active')
    ts = read_json(root / 'config/fx_total_return.json')
    if (ts.get('schema') != 'fx_total_return_release_v1'
            or ts['funding_snapshot'] != request['funding_snapshot']
            or ts['funding_model'] != request['funding_model']
            or request['funding_model'] != reference(fx_total.policy())):
        raise ValueError('Reuse the exact installed benchmark funding release')
    schedule = load_schedule(root)
    if schedule is None or schedule['horizons'] != list(HORIZONS):
        raise ValueError('The approved active horizon schedule differs')
    store = TargetStore(root)
    funding = store.resolve(request['funding_snapshot'])
    fx_funding.validate_record(funding)
    profile = profile_for(root, release)
    selection = profile['target_selection']
    if (selection['selection_scope'] != 'currency_price_catalog'
            or selection['price_catalog'] != release['body']['price_catalog']):
        raise ValueError('Currency Research Spec must pin this exact oriented price catalog')
    pairs = sorted({s for q in REFERENCES for s in fx_funded_scopes.members(q)})
    spots, definitions = {}, {}
    starts = [v['start'] for v in funding['body']['coverage'].values()]
    ends = [v['end'] for v in funding['body']['coverage'].values()]
    for pair in pairs:
        price = store.resolve(selection['source_snapshots'][pair])
        if price['body'].get('profile') != 'fx_currency_price.1.0.0' or price['body']['instrument_id'] != pair:
            raise ValueError('An exact correctly oriented currency price is required')
        starts.append(price['body']['coverage']['start'])
        ends.append(price['body']['coverage']['end'])
        spots[pair], definitions[pair] = {}, {}
        for horizon in HORIZONS:
            binding = selection['materializations'][pair][str(horizon)]
            manifest = store.resolve(binding)
            if (manifest['schema_version'] != '0.5.0'
                    or manifest['price_snapshot'] != selection['source_snapshots'][pair]):
                raise ValueError('Currency spot Target and frozen oriented price differ')
            definition = fx_total._definition(store.resolve(manifest['definition']), request['funding_model'])
            if (definition['body']['instrument_id'] != pair
                    or definition['body']['horizon']['amount'] != horizon):
                raise ValueError('Currency financing Target orientation or horizon differs')
            spots[pair][str(horizon)] = binding
            definitions[pair][str(horizon)] = reference(definition)
    # A full data-publication verification scope, covering every exact pinned
    # operand. It is not a P1/P2 evidence window and never creates an experiment.
    period = {'start_inclusive': min(starts),
              'end_exclusive': (date.fromisoformat(max(ends)) + timedelta(days=1)).isoformat()}
    date.fromisoformat(period['start_inclusive'])
    return {'operation': 'fx_currency_total_return_migration_v1', 'request': deepcopy(request),
        'price_catalog': selection['price_catalog'], 'horizons': list(HORIZONS),
        'scope_members': {identifier: fx_funded_scopes.members(q)
            for identifier, q in zip(fx_funded_scopes.SCOPE_IDS, REFERENCES)},
        'spot_materializations': spots, 'target_definitions': definitions,
        'verification_period': period, 'research_jobs_created': 0,
        'research_admissions_reopened': False}


def migrate(root, request, *, apply=False, expected_plan_sha256=None):
    root = Path(root).resolve()
    reviewed = plan(root, request)
    sha = digest(reviewed)
    if not apply:
        return dict(reviewed, plan_sha256=sha, apply=False)
    if expected_plan_sha256 != sha:
        raise ValueError('An exact reviewed CS data plan hash is required')
    if not admissions_closed():
        raise ValueError('Keep production research admissions closed during and after this migration')
    if (root / CONFIG).exists():
        raise ValueError('A CS funding release already exists; use an explicit versioned upgrade plan')
    with lock(root, 'research-executor', nonblocking=True) as available:
        if not available:
            raise ValueError('Research executor is active; no CS funding inputs installed')
        with lock(root, 'research-writer'):
            if plan(root, request) != reviewed:
                raise ValueError('The reviewed CS data plan changed')
            idle(root)
            feature_store = FeatureStore(root)
            feature_store.install_record(fx_total.policy())
            scopes = fx_funded_scopes.register(root, reviewed['price_catalog'], request['request_text'])
            scope = feature_store.resolve(next(iter(scopes.values())))
            specification = feature_store.resolve(scope['body']['eligibility_policy'])['body']['specification']
            store = TargetStore(root)
            # Freeze definition lookup directories before the bounded verified
            # read scope. Existing immutable records are only checked/reused.
            with store.writer():
                for horizons in reviewed['spot_materializations'].values():
                    for binding in horizons.values():
                        spot = store.resolve(binding)
                        store.install_record(fx_total._definition(store.resolve(spot['definition']), request['funding_model']))
            namespace = {'plan_id': 'DATA_RELEASE_' + sha}
            maps = {}
            with execution_inputs(root, {'release_plan': sha}, max_bytes=512 * 1024 * 1024):
                with phase_inputs(root, namespace, 'MATERIALIZATION', period=reviewed['verification_period']):
                    for pair, horizons in reviewed['spot_materializations'].items():
                        maps[pair] = {h: fx_total.materialize(root, binding, request['funding_snapshot'])
                                      for h, binding in horizons.items()}
            config = {'schema': SCHEMA, 'currency_release': request['currency_release'],
                'price_catalog': reviewed['price_catalog'], 'funding_model': request['funding_model'],
                'funding_snapshot': request['funding_snapshot'], 'scope_specification': specification,
                'scopes': scopes, 'materializations': maps}
            install_bytes(root / CONFIG, canonical(config) + b'\n')
    return {'status': 'installed', 'plan_sha256': sha, 'scopes': scopes,
        'materializations': maps, 'config_sha256': digest(config),
        'research_jobs_created': 0, 'research_admissions_reopened': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-plan-sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = migrate(args.root, read_json(args.request), apply=args.apply,
                    expected_plan_sha256=args.expected_plan_sha256)
    args.output.write_bytes(canonical(value) + b'\n')


if __name__ == '__main__':
    main()
