"""Read-only dashboard projections of authoritative research and evidence.

No statistics, decisions, identities or stored records are changed. Large samples
are fetched only for the selected trial; table pages retain exact stored rows.
"""
from copy import deepcopy
import hashlib
import json
import math
import re

from research.contracts import ResearchError, ref
from research.store import ResearchStore, inside
from data.feature_store import FeatureStore

RECIPE = re.compile(r'FEATURE_(?:RECIPE_)?[0-9a-f]{64}')
TRIAL = re.compile(r'TRIAL_[0-9a-f]{64}')
TABLE_ROLES = {'aligned_sample', 'observation_exclusions', 'cross_sectional_ic_history'}


def feature_research(root, recipe_id):
    if not RECIPE.fullmatch(recipe_id):
        raise ValueError('Use an exact Feature recipe ID')
    store = ResearchStore(root)
    # Reuse the existing reader's exact relationship, trial, admission and
    # validation linkage checks, including independent evidence branches.
    relationships = store.results_for_recipe(recipe_id)
    for relationship in relationships:
        # Cosmetic label only; never substitute today's scope or membership.
        try:
            scope = relationship['scope']
            relationship['scope_label'] = FeatureStore(root).resolve(scope.get('reference', scope))['display_name']
        except (ValueError, KeyError, OSError):
            relationship['scope_label'] = relationship['scope']['id']
        for result in relationship['results']:
            trial = store.resolve('trial', result['authority'])
            body = trial['body']
            result.update({key: deepcopy(body.get(key)) for key in (
                'evidence', 'reason_codes', 'confidence_flags', 'multiple_testing', 'fdr_diagnostics')})
            result['artifact_manifests'] = deepcopy(body['artifact_manifests'])
        relationship['validations'] = [dict(authority=value, **store.resolve('validation', value)['body'])
                                      for value in relationship['validation_results']]
    return {'schema_version': '1.0.0', 'recipe_id': recipe_id, 'relationships': relationships}


def _artifacts(store, trial, wanted):
    values = {}
    seen = set()
    for reference in trial['body']['artifact_manifests']:
        manifest = store.verify_artifact(reference)
        for member in manifest['members']:
            role = member['role']
            if role in seen:
                raise ResearchError('Ambiguous artifact role')
            seen.add(role)
            if role not in wanted:
                continue
            sha = member['blob_sha256']
            data = inside(store.root, f'storage/payloads/sha256/{sha[:2]}/{sha}.json').read_bytes()
            # Verify the same bytes used in the presentation, including a change
            # between manifest verification and reading this selected member.
            if hashlib.sha256(data).hexdigest() != sha or len(data) != member['byte_count']:
                raise ResearchError('Artifact changed during reading')
            values[role] = json.loads(data)
    return values


def _small(value):
    """Omit long HAC date arrays from the small chart/sidebar projection."""
    if isinstance(value, list):
        return [_small(row) for row in value]
    if isinstance(value, dict):
        return {key: _small(v) for key, v in value.items() if key not in ('usable_dates', 'lag_pair_counts')}
    return value


def trial_evidence(root, trial_id, role=None, offset=0):
    if not TRIAL.fullmatch(trial_id) or role is not None and role not in TABLE_ROLES:
        raise ValueError('Use an exact trial and supported evidence type')
    if not isinstance(offset, int) or offset < 0 or offset > 10000000:
        raise ValueError('Invalid evidence offset')
    store = ResearchStore(root)
    trial = store.get('trial', trial_id)
    is_cs = trial['body']['mode'] == 'CS'
    wanted = {role} if role is not None else {
        'stability', 'blocks', 'leaveouts', 'robustness_slices', 'scheduled_hac',
        'cross_sectional_ic_history' if is_cs else 'aligned_sample'}
    values = _artifacts(store, trial, wanted)
    base = {'schema_version': '1.0.0', 'authority': ref(trial),
            'artifact_manifests': trial['body']['artifact_manifests']}
    if role is not None:
        rows = values.get(role)
        if rows is not None and not isinstance(rows, list):
            raise ResearchError('Invalid table evidence')
        return dict(base, role=role, available=rows is not None, offset=offset,
                    total=len(rows) if rows is not None else None, limit=100,
                    rows=(rows or [])[offset:offset + 100])
    body = trial['body']
    source = values.get('cross_sectional_ic_history' if is_cs else 'aligned_sample')
    chart = {'kind': 'cumulative_rank_ic' if is_cs else 'scatter', 'points': [],
             'available': source is not None, 'total_count': 0, 'display_count': 0,
             'sampling': 'all observations'}
    points = []
    cumulative = 0.0
    for row in source or []:
        try:
            x = row.get('anchor_date', row.get('date')) if is_cs else float(row['feature'])
            y = float(row['rank_ic'] if is_cs else row['target'])
            if not math.isfinite(y) or (not is_cs and not math.isfinite(x)):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        if is_cs:
            cumulative += y
        points.append({'x': x, 'y': cumulative if is_cs else y,
                       'date': row.get('anchor_date', row.get('date'))})
    chart['total_count'] = len(points)
    # CS cumulative sums use every stored usable date. TS scatter rendering is
    # bounded; this changes display density only, never regression or evidence.
    if not is_cs and len(points) > 1200:
        points = [points[round(i * (len(points)-1) / 1199)] for i in range(1200)]
        chart['sampling'] = '1200 evenly spaced stored rows; statistics use the full sample'
    chart.update(points=points, display_count=len(points))
    return dict(base, chart=chart, artifacts={key: _small(values[key]) for key in
        ('stability', 'blocks', 'leaveouts', 'robustness_slices', 'scheduled_hac') if key in values})
