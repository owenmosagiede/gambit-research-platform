#!/usr/bin/env python3
"""Register five fixed retrospective carry features; never submit research here."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from data.fx_carry import FAMILIES, recipe, publish
from data.transformations.identity import canonical_bytes, digest, reference
from research.contracts import load_profile
from research.store import inside, install_bytes, read_json


def install_profile(root):
    original = load_profile(root); profile = deepcopy(original)
    profile.update(id='RSPEC_FX_CARRY_FIVE', version='1.0.0', approval_state='approved',
        carry_recipes=[reference(recipe(f)) for f in FAMILIES], parent_research_spec=reference(original))
    exposure = profile.get('exposure_classification')
    profile['exposure_classification'] = dict(exposure if isinstance(exposure, dict) else {},
        carry_recipe_approval='User authorized the five fixed carry recipes across 31 agreed G10 pairs on 2026-11-24',
        source_timing='Benchmark rate and spot reference dates are retrospective assumptions, not certified historical publication times. Inflation retains the existing first-published actual convention.',
        untouched_holdout_claim=False, historical_pit_certified=False, live_certified=False)
    install_bytes(inside(root, 'definitions/research_specs/' + profile['id'] + '/1.0.0.json'), canonical_bytes(profile)+b'\n')
    install_bytes(inside(root, 'config/fx_carry_research.json'), canonical_bytes({'research_spec': reference(profile)})+b'\n')
    return profile


def prepare(root, pairs, inflation_capture, manifest_path):
    from data.verified_inputs import execution_inputs, phase_inputs
    from runtime.research_jobs import implementation
    profile = install_profile(root)
    funding = read_json(inside(root, 'config/fx_total_return.json'))['funding_snapshot']
    publication = {'plan_id': 'CARRY_PUBLICATION_' + digest({'pairs': pairs, 'funding': funding, 'inflation': inflation_capture}),
        'periods': {'PUBLICATION': {'start_inclusive': '1900-01-01', 'end_exclusive': '2025-01-01'}}}
    entries, excluded = [], []
    with execution_inputs(root, implementation()), phase_inputs(root, publication, 'PUBLICATION'):
        for pair, price in sorted(pairs.items()):
            for family in FAMILIES:
                try:
                    snapshot = publish(root, family, pair, price, funding, inflation_capture if family == 'real_actual' else None)
                except ValueError as exc:
                    if str(exc) != 'Carry feature has no valid history': raise
                    excluded.append({'family': family, 'pair': pair, 'reason': str(exc)}); continue
                body = snapshot['body']; horizons = [int(h) for h, c in body['coverage'].items() if not c['exclusion']]
                entry = {'family': family, 'pair': pair, 'recipe': reference(recipe(family)),
                    'snapshot': reference(snapshot), 'horizons': sorted(horizons), 'coverage': body['coverage']}
                if horizons: entries.append(entry)
                else: excluded.append(dict(entry, reason='NO_ELIGIBLE_HORIZON'))
                print(json.dumps({'prepared': family, 'pair': pair, 'horizons': sorted(horizons)}), flush=True)
    manifest = {'schema': 'fx_carry_five_recipe_program_v1', 'research_spec': reference(profile),
        'funding_snapshot': funding, 'inflation_capture': inflation_capture, 'price_pins': pairs,
        'entries': entries, 'excluded': excluded, 'historical_pit_certified': False,
        'live_certified': False, 'research_submitted': False}
    manifest['sha256'] = digest(manifest)
    install_bytes(manifest_path, canonical_bytes(manifest)+b'\n')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True); p.add_argument('--pair-pins', type=Path, required=True)
    p.add_argument('--inflation-capture', type=Path, required=True); p.add_argument('--manifest', type=Path, required=True)
    a = p.parse_args(); manifest = prepare(a.root, read_json(a.pair_pins), read_json(a.inflation_capture), a.manifest)
    print(json.dumps({'prepared_candidates': len(manifest['entries']), 'excluded': len(manifest['excluded']), 'research_submitted': False}))

if __name__ == '__main__': main()
