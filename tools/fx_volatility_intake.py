#!/usr/bin/env python3
"""Stage standalone volatility registration and the request inputs for a small TS pilot."""

import argparse
from hashlib import sha256
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from data.reusable_features import build_volatility_registration
from data.transformations.identity import reference
from research.contracts import canonical, digest, load_profile, ref
from research.schedule import load_schedule
from research.store import install_bytes


PILOT_PAIRS = ('EURUSD', 'AUDUSD', 'USDJPY')
DIRECTIONS = ('POSITIVE', 'NEGATIVE')


def build(root):
    schedule = load_schedule(root)
    if schedule is None:
        raise ValueError('The prospective research schedule must be active')
    catalog = build_volatility_registration(root)
    recipe, = [value for value in catalog['recipes']
               if value['body']['steps'][-1]['operator']['id'] == 'TR_BASE_vol_diff_sd'
               and [(p['name'], p['value']['value']) for p in value['body']['steps'][-1]['parameters']]
               == [('w', '21')]]
    entries = []
    for pair in PILOT_PAIRS:
        for direction in DIRECTIONS:
            request = {'feature': {'id': recipe['id'], 'version': recipe['version']},
                       'scope': {'id': pair, 'version': '1.0.0'}, 'target_family': 'price_return',
                       'expected_direction': direction}
            request['request_id'] = str(uuid5(NAMESPACE_URL, digest([ref(schedule), reference(recipe), request])))
            entries.append(request)
    return {'program': 'GAMBIT_TS_VOLATILITY_PILOT_V1', 'schedule': ref(schedule),
            'base_research_spec': ref(load_profile(root)), 'pilot_recipe': reference(recipe),
            'entries': entries, **catalog}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    if args.bundle.resolve().is_relative_to(args.root.resolve()):
        parser.error('Use a staging location outside the research store')
    result = build(args.root)
    install_bytes(args.bundle, canonical(result) + b'\n')
    print(canonical({'recipe_count': len(result['recipes']),
                     'pair_bindings': len(result['features']), 'pilot_entries': result['entries'],
                     'bundle_sha256': sha256(args.bundle.read_bytes()).hexdigest()}).decode())


if __name__ == '__main__':
    main()
