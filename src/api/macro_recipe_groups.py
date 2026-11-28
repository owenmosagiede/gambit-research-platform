"""Display-only macro families over exact, immutable pair Feature records.

The group identifier is a navigation key, never a registered scientific Feature
reference. Pair Features, source snapshots and research references stay intact.
"""
from collections import Counter, defaultdict
from copy import deepcopy

from data.transformations.identity import digest, reference


def descriptor(root, store, feature):
    if feature.get('schema_version') != '0.11.0':
        return None
    p = feature['body']['projection']
    if p['package'] != 'macro' or p['selector'].get('table') != 'pair_features_data':
        return None
    from data import panel_import as panels
    panels.resolved(root, feature, verify_database=False, store=store)
    pair = p['pair']
    if not pair or not p['name'].startswith(pair + ' '):
        raise ValueError('Macro pair projection lacks its exact display binding')
    recipe = feature['body']['recipe']
    # Field and source identities establish equivalence; cosmetic names do not.
    # Freeze/layer and policy distinctions remain visible as separate versions.
    key = {'kind': 'macro_library_group_v1', 'snapshot': feature['body']['snapshot'],
           'selector': {k: v for k, v in p['selector'].items() if k not in ('base_id', 'quote_id')},
           'field': p['field'], 'layer': p['layer'], 'panels': p['panel_ids'],
           'unit': p['unit'], 'frequency': p['frequency'],
           'sources': recipe['sources'],
           'policies': {k: recipe[k] for k in ('history_mode', 'history_policy', 'execution_policy', 'evaluation_policy')}}
    return {'id': 'MACRO_FEATURE_' + digest(key),
            'name': p['name'][len(pair) + 1:] + ' [' + p['layer'] + ']',
            'pair': pair, 'feature': reference(feature), 'source_layer': p['layer']}


def presentation(members):
    """Collect verified pair entries without rewriting any branch's recipe."""
    first = members[0]['entry']['macro_group']
    by_pair = defaultdict(list)
    inputs = defaultdict(dict)
    for member in members:
        group = member['entry']['macro_group']
        if group['id'] != first['id'] or group['name'] != first['name']:
            raise ValueError('Conflicting macro recipe presentation')
        rows = [v['row'] for v in member['values']]
        for row in rows:
            pair = row['scope'].get('id')
            if pair not in (group['pair'], group['pair'][3:] + group['pair'][:3]):
                raise ValueError('Macro pair research differs from its stored input')
            by_pair[pair].append(row)
            inputs[pair][group['feature']['id']] = {'feature': deepcopy(group['feature']), 'source_pair': group['pair']}
    pairs = []
    for pair, rows in sorted(by_pair.items()):
        pairs.append({'pair': pair, 'inputs': [inputs[pair][key] for key in sorted(inputs[pair])],
                      'relationship_count': len({r['relationship']['id'] for r in rows}),
                      'p1_counts': dict(Counter(r['p1_status'] for r in rows)),
                      'p2_counts': dict(Counter(r['p2_status'] for r in rows)),
                      'research_stage_pass_count': len({r['relationship']['id'] for r in rows if r['research_stage_pass']})})
    return {'id': first['id'], 'kind': 'macro_recipe_group', 'name': first['name'],
            'pair_count': len({p['pair'] for p in pairs}), 'pairs': pairs,
            'source_layer': first['source_layer'], 'observation_count': None}
