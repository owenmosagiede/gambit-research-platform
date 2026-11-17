#!/usr/bin/env python3
"""Publish the approved two-recipe value program or submit its eligible pairs."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from data.feature_store import FeatureStore
from data.fx_value import COUNTRIES, FAMILIES, next_weekday, publish, recipe
from data.transformations.identity import canonical_bytes, digest, reference
from research.contracts import load_profile
from research.store import inside, install_bytes, read_json


def captures(root, weo_editions, reer_directory):
    store = FeatureStore(root)
    editions = []
    for edition in read_json(weo_editions)['editions']:
        available = next_weekday(edition.get('conservative_release_date', edition['published']))
        if available >= '2025-01-01':
            continue
        files = {kind: store.io.blob(Path(item['path']).read_bytes(), 'bin', 'original_IMF_WEO')
                 for kind, item in edition['files'].items()}
        editions.append({'id': edition['id'], 'published': edition['published'], 'available_on': available,
                         'files': files, 'source_urls': {kind: item['url'] for kind, item in edition['files'].items()}})
    weo = {'schema': 'fx_value_macro_capture_v1', 'family': 'weo_bilateral', 'editions': editions}
    currencies = {currency: store.io.blob(
        (reer_directory / ('RB' + country + 'BIS-all-vintages.zip')).read_bytes(), 'bin', 'original_ALFRED_BIS_REER')
        for currency, country in COUNTRIES.items()}
    reer = {'schema': 'fx_value_macro_capture_v1', 'family': 'reer_relative', 'currencies': currencies,
            'source_urls': {currency: 'https://alfred.stlouisfed.org/series?seid=RB' + country + 'BIS'
                            for currency, country in COUNTRIES.items()}, 'CNH_proxy': 'RBCNBIS'}
    return {family: store.io.blob(canonical_bytes(value), 'json', 'fx_value_macro_capture')
            for family, value in zip(FAMILIES, (weo, reer))}


def install_profile(root):
    original = load_profile(root)
    profile = deepcopy(original)
    profile.update(id='RSPEC_FX_VALUE_FIVE_YEAR', version='1.0.0', approval_state='approved',
                   value_recipes=[reference(recipe(family)) for family in FAMILIES],
                   parent_research_spec=reference(original))
    profile['exposure_classification'] = dict(profile['exposure_classification'],
        value_recipe_approval='User approved two fixed five-year recipes and China REER proxy for CNH',
        source_timing='Dated IMF and ALFRED macro observations. Spot history retains retrospective date labels.',
        untouched_holdout_claim=False)
    install_bytes(inside(root, 'definitions/research_specs/' + profile['id'] + '/1.0.0.json'),
                  canonical_bytes(profile) + b'\n')
    install_bytes(inside(root, 'config/fx_value_research.json'),
                  canonical_bytes({'research_spec': reference(profile)}) + b'\n')
    return profile


def prepare(args):
    sources = captures(args.root, args.weo_editions, args.reer_directory)
    profile = install_profile(args.root)
    pins = read_json(args.pair_pins)
    if args.pair:
        pins = {pair: pins[pair] for pair in args.pair}
    entries, excluded = [], []
    from data.verified_inputs import execution_inputs, phase_inputs
    from runtime.research_jobs import implementation
    publication = {'plan_id': 'VALUE_PUBLICATION_' + digest(sources),
                   'periods': {'PUBLICATION': {'start_inclusive': '2006-10-02', 'end_exclusive': '2025-01-01'}}}
    with execution_inputs(args.root, implementation()), phase_inputs(args.root, publication, 'PUBLICATION'):
        for family in FAMILIES:
            for pair, price_snapshot in sorted(pins.items()):
                try:
                    snapshot = publish(args.root, family, pair, price_snapshot, sources[family])
                except ValueError as exc:
                    # Missing five-year history is an explicit exclusion. Other
                    # publication/integrity failures abort the program immediately.
                    if str(exc) != 'Value feature has insufficient five-year history':
                        raise
                    excluded.append({'family': family, 'pair': pair, 'reason': 'NO_FIVE_YEAR_FEATURE_HISTORY'})
                    continue
                eligible = [int(h) for h, row in snapshot['body']['coverage'].items() if not row['exclusion']]
                if not eligible:
                    excluded.append({'family': family, 'pair': pair, 'reason': 'NO_ELIGIBLE_HORIZON',
                                     'coverage': snapshot['body']['coverage']})
                    continue
                identity = {'family': family, 'pair': pair, 'snapshot': reference(snapshot),
                            'research_spec': reference(profile)}
                request = str(uuid.uuid5(uuid.NAMESPACE_URL, 'gambit-value-five-year:' + digest(identity)))
                entries.append({**identity, 'horizons': eligible, 'coverage': snapshot['body']['coverage'],
                    'submission': {'request_id': request, 'feature': {key: recipe(family)[key] for key in ('id', 'version')},
                        'scope': {'id': pair, 'version': '1.0.0'}, 'target_family': 'price_return',
                        'expected_direction': 'DISCOVERY_SIGN_V1'}})
                print(json.dumps({'prepared': family, 'pair': pair, 'eligible_horizons': eligible}), flush=True)
    manifest = {'schema': 'fx_value_five_year_program_v1', 'research_spec': reference(profile),
                'source_captures': sources, 'entries': entries, 'excluded': excluded}
    manifest['sha256'] = digest(manifest)
    args.manifest.write_bytes(canonical_bytes(manifest) + b'\n')
    print(json.dumps({'manifest': str(args.manifest), 'requests': len(entries), 'excluded': len(excluded)}))


def queue(args):
    from runtime.research_jobs import ResearchJobs
    from runtime.experiment_identity import freeze
    from runtime.research_jobs import implementation
    manifest = read_json(args.manifest)
    if manifest.get('sha256') != digest({k: v for k, v in manifest.items() if k != 'sha256'}):
        raise ValueError('Value program manifest differs from its checksum')
    if manifest['research_spec'] != reference(install_profile(args.root)):
        raise ValueError('Installed value program differs from prepared program')
    jobs = ResearchJobs(args.root)
    packets = []
    # Resolve every candidate before accepting any request. A failed metadata
    # check cannot silently leave a partially validated batch in the queue.
    for entry in manifest['entries']:
        selection = entry['submission']
        intent = {key: value for key, value in selection.items() if key != 'request_id'}
        packet = freeze(jobs, intent, implementation())
        if sorted(packet['frozen_plan']['horizons']) != sorted(entry['horizons']):
            raise ValueError('Frozen horizon eligibility differs from preflight')
        if packet['frozen_plan']['value_source']['snapshot'] != entry['snapshot']:
            raise ValueError('Frozen value source differs from the reviewed program')
        packets.append(entry)
    if not args.apply:
        print(json.dumps({'verified_requests': len(packets), 'queue_mutated': False}))
        return
    for entry in packets:
        job, created = jobs.submit(entry['submission'])
        print(json.dumps({'request_id': job['request_id'], 'created': created, 'family': entry['family'],
                          'pair': entry['pair'], 'horizons': entry['horizons']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    actions = parser.add_subparsers(dest='action', required=True)
    prep = actions.add_parser('prepare')
    prep.add_argument('--weo-editions', type=Path, required=True)
    prep.add_argument('--reer-directory', type=Path, required=True)
    prep.add_argument('--pair-pins', type=Path, required=True)
    prep.add_argument('--pair', action='append')
    prep.add_argument('--manifest', type=Path, required=True)
    submit = actions.add_parser('queue')
    submit.add_argument('--manifest', type=Path, required=True)
    submit.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    prepare(args) if args.action == 'prepare' else queue(args)


if __name__ == '__main__':
    main()
