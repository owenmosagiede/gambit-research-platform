"""Exact CS funding-release metadata, separate from the canonical TS bindings."""
from pathlib import Path

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore
from data.fx_funded_scopes import SCOPE_IDS, members
from data.targets.fx_total import policy
from data.transformations.fx_currency import REFERENCES
from data.transformations.contracts import normalize_reference
from data.transformations.identity import reference

CONFIG = 'config/fx_total_return_cs.json'
SCHEMA = 'fx_total_return_cs_release_v1'
HORIZONS = (1, 7, 21, 63)


def load_release(root, *, required=True):
    path = Path(root) / CONFIG
    if not path.is_file() and not required:
        return None
    value = strict_json(stable_read(path))
    fields = {'schema', 'currency_release', 'price_catalog', 'funding_model',
              'funding_snapshot', 'scope_specification', 'scopes', 'materializations'}
    if set(value) != fields or value['schema'] != SCHEMA:
        raise ValueError('Invalid currency-universe total-return release')
    for key in ('currency_release', 'price_catalog', 'funding_model', 'funding_snapshot', 'scope_specification'):
        normalize_reference(value[key])
    if value['funding_model'] != reference(policy()):
        raise ValueError('Currency-universe benchmark funding model differs')
    store = FeatureStore(root)
    release = store.resolve(value['currency_release'])
    if (release.get('body', {}).get('kind') != 'fx_currency_release'
            or release['body']['price_catalog'] != value['price_catalog']):
        raise ValueError('Currency funding release and declared oriented price catalog differ')
    from data.fx_funding import validate_record
    validate_record(store.resolve(value['funding_snapshot']))
    if set(value['scopes']) != set(SCOPE_IDS):
        raise ValueError('Exactly seven financed currency Scopes are required')
    for identifier, binding in value['scopes'].items():
        normalize_reference(binding)
        if binding['id'] != identifier or binding['version'] != '1.0.0':
            raise ValueError('Financed currency Scope binding differs')
    expected = {symbol for quote in REFERENCES for symbol in members(quote)}
    if set(value['materializations']) != expected:
        raise ValueError('All 119 fixed funded currency exposures are required')
    for horizons in value['materializations'].values():
        if set(horizons) != {str(h) for h in HORIZONS}:
            raise ValueError('All four financed currency Target horizons are required')
        for binding in horizons.values():
            if set(binding) != {'definition', 'materialization'}:
                raise ValueError('Exact financed currency Target bindings are required')
            for item in binding.values():
                normalize_reference(item)
    return value
