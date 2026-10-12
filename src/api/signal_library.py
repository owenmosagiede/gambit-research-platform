"""Read-only, verified views over canonical stored Signal projections.

No research metric is inferred here. Descriptive summaries are transient API
views of one exact materialization, never independently editable records.
"""
from collections import Counter
from decimal import Decimal, localcontext
import math
import re

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, retrieve_signal
from data.feature_store_contracts import normalize_library_entry
from data.transformations.identity import digest, reference

SIGNAL_ID = re.compile(r'SIGNAL_[0-9a-f]{64}\Z', re.ASCII)
MATERIALIZATION_ID = re.compile(r'MATERIALIZATION_[0-9a-f]{64}\Z', re.ASCII)
ENTRIES = 'storage/catalog/signal_library/entries'


class SignalNotFound(ValueError):
    pass


def _coverage(rows):
    cutoffs = [row['evaluation_cutoff'] for row in rows]
    periods = [row['reference_time'] for row in rows if row['reference_time'] is not None]
    return {'cutoff_start': min(cutoffs) if cutoffs else None,
            'cutoff_end': max(cutoffs) if cutoffs else None,
            'reference_start': min(periods) if periods else None,
            'reference_end': max(periods) if periods else None}


def descriptive_statistics(rows, unit):
    """Summarize finite valid values without conflating nulls with zero."""
    counts = Counter(row['status'] for row in rows)
    reasons = Counter(row['reason_code'] for row in rows if row['reason_code'] is not None)
    values = sorted(Decimal(row['value']) for row in rows if row['status'] == 'valid')
    if any(not value.is_finite() for value in values):
        raise ValueError('Nonfinite stored value')
    result = {'kind': 'descriptive_observation_statistics', 'unit': unit,
              'row_count': len(rows), 'valid_count': counts['valid'],
              'missing_count': counts['missing'], 'invalid_count': counts['invalid'],
              'null_count': sum(row['value'] is None for row in rows),
              'reason_counts': dict(sorted(reasons.items())),
              'min': None, 'max': None, 'mean': None, 'median': None,
              'sample_standard_deviation': None, 'unavailable_statistics': []}
    if values:
        with localcontext() as context:
            context.prec = 50
            mean = sum(values) / len(values)
            middle = len(values) // 2
            median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
            stats = {'min': values[0], 'max': values[-1], 'mean': mean, 'median': median}
            if len(values) > 1:
                stats['sample_standard_deviation'] = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)).sqrt()
            for name, value in stats.items():
                number = float(value)
                if math.isfinite(number):
                    result[name] = number
                else:
                    result['unavailable_statistics'].append(name)
    return result


def _load_signal(root, identifier):
    """Verify every linked materialization; stale projections cannot duplicate rows."""
    if not SIGNAL_ID.fullmatch(identifier):
        raise SignalNotFound('Unknown Signal')
    store = FeatureStore(root)
    folder = store.path(ENTRIES + '/' + identifier)
    if not folder.is_dir():
        raise SignalNotFound('Unknown Signal')
    entries = []
    bindings = {}
    feature = None
    for path in sorted(folder.glob('*.json')):
        path = store.path(str(path.relative_to(store.root)))
        entry = normalize_library_entry(strict_json(stable_read(path)))
        if entry['signal_id'] != identifier or path.name != digest(entry) + '.json':
            raise ValueError('Signal entry identity mismatch')
        if feature is not None and entry['feature'] != feature:
            raise ValueError('Conflicting exact Feature references')
        feature = entry['feature']
        for binding in entry['feature_materializations']:
            if binding['id'] in bindings and binding != bindings[binding['id']]:
                raise ValueError('Conflicting exact materialization references')
            bindings[binding['id']] = binding
        entries.append(entry)
    if not entries:
        raise SignalNotFound('Unknown Signal')
    loaded = []
    for materialization_id in sorted(bindings):
        item = retrieve_signal(store.root, identifier, materialization_id)
        if reference(item['manifest']) != bindings[materialization_id] or reference(item['feature']) != feature:
            raise ValueError('Resolved Signal reference mismatch')
        loaded.append(item)
    if not loaded:
        raise ValueError('Signal has no complete materialization')
    # A deterministic default is a presentation preference, never a new identity.
    loaded.sort(key=lambda item: (_coverage(item['observations'])['cutoff_end'] or '', item['manifest']['id']), reverse=True)
    return store, loaded


def _source(store, item):
    dataset = item['metadata']['dataset']
    view = item['metadata']['source_view']
    if dataset['body'].get('kind') == 'fx_constructed_dataset':
        source_metadata = dataset['body']['source_metadata']
        # Constructed FX prices have registered source metadata rather than an
        # ALFRED-style provider contract. This is a display projection only.
        provider = {'body': {'provider': 'Twelve Data-derived',
                            'native_series_id': dataset['body']['instrument_id'],
                            'frequency': 'Scheduled weekdays',
                            'units': source_metadata['unit'],
                            'price_basis': source_metadata['price_basis'],
                            'timing': source_metadata['timing']}}
        return {'dataset': reference(dataset), 'name': dataset['display_name'],
                'series_id': dataset['body']['instrument_id'],
                'provider': provider['body']['provider'],
                'frequency': provider['body']['frequency'], 'units': provider['body']['units'],
                'source_view': reference(view)}, provider
    provider = store.resolve(dataset['body']['source_contract'])
    return {'dataset': reference(dataset), 'name': dataset['display_name'],
            'series_id': provider['body']['native_series_id'],
            'provider': provider['body']['provider'],
            'frequency': provider['body']['frequency'], 'units': provider['body']['units'],
            'source_view': reference(view)}, provider


def _summary(store, loaded):
    item = loaded[0]
    feature, manifest = item['feature'], item['manifest']
    source, _ = _source(store, item)
    transformations = []
    for step in feature['body']['recipe']['steps']:
        operator = store.resolve(step['operator'])
        transformations.append({'node': step['node'], 'operator': step['operator'],
                                'label': operator['display_name'], 'parameters': step['parameters']})
    latest = max(item['observations'], key=lambda row: (row['evaluation_cutoff'], row['reference_time'] or '', row['entity_id']))
    return {'signal_id': item['signal_id'], 'name': feature['display_name'],
            'feature': reference(feature), 'source': source, 'transformations': transformations,
            'materialization_state': item['materialization_state'], 'scientific_state': ('results_linked' if _authoritative_research(store.root, feature['id']) else item['scientific_state']),
            'materialization_count': len(loaded), 'default_materialization_id': manifest['id'],
            'row_count': manifest['row_count'], 'status_counts': manifest['status_counts'],
            'coverage': _coverage(item['observations']),
            'latest_observation': {key: latest[key] for key in ('evaluation_cutoff', 'reference_time', 'value', 'status', 'reason_code')},
            'unit': manifest['metadata']['unit'],
            'value_semantics': manifest['metadata']['value_semantics'],
            'availability_semantics': manifest['metadata']['availability_semantics'],
            'readiness_capabilities': manifest.get('readiness_capabilities', {})}


def list_signal_library(root):
    """List one selectable Feature per verified logical Signal, without writes."""
    store = FeatureStore(root)
    folder = store.path(ENTRIES)
    signals, issues = [], []
    for path in sorted(folder.iterdir()) if folder.exists() else []:
        if path.name.startswith('.'):
            continue
        identifier = path.name if SIGNAL_ID.fullmatch(path.name) else None
        try:
            if identifier is None or not path.is_dir():
                raise ValueError('Unsupported library location')
            loaded_store, loaded = _load_signal(store.root, identifier)
            signals.append(_summary(loaded_store, loaded))
        except Exception:
            issues.append({'code': 'UNAVAILABLE_SIGNAL', 'signal_id': identifier,
                           'message': 'A stored Signal could not be verified and was excluded.'})
    signals.sort(key=lambda item: (item['name'].casefold(), item['signal_id']))
    return {'schema_version': '1.0.0', 'signal_count': len(signals), 'signals': signals, 'issues': issues}


def get_signal_detail(root, identifier, materialization_id=None):
    if materialization_id is not None and not MATERIALIZATION_ID.fullmatch(materialization_id):
        raise SignalNotFound('Unknown materialization')
    store, loaded = _load_signal(root, identifier)
    return _detail(store, loaded, identifier, materialization_id,
                   research=_authoritative_research(root, loaded[0]['feature']['id']))


def _authoritative_research(root, feature_id):
    from research.store import ResearchStore
    results = ResearchStore(root).results_for_recipe(feature_id)
    if not results: return None
    return {'state':'results_linked', 'label':'Research results recorded',
        'relationship_count':len({r['relationship']['id'] for r in results}),
        'relationships':results, 'metrics':[],
        'description':'Each result belongs to its exact Scope, Target, horizon, direction, Research Spec and evaluation period. Stored preparation does not establish universal validation.'}


def _detail(store, loaded, identifier, materialization_id=None, *, research=None,
            output_prefix='/api/signal-library/'):
    """Present independently verified outputs; scientific results stay separate."""
    selected = next((item for item in loaded if item['manifest']['id'] == materialization_id), None) if materialization_id else loaded[0]
    if selected is None:
        raise SignalNotFound('Materialization is not linked to this Signal')
    manifest, feature = selected['manifest'], selected['feature']
    recipe = feature['body']['recipe']
    _, provider = _source(store, selected)
    evaluation = store.resolve(recipe['evaluation_policy']) if recipe.get('evaluation_policy') else None
    rules = {parameter['name']: parameter['value'].get('value') for parameter in evaluation['body']['parameters']} if evaluation else {}
    archive = rules.get('interpretation') == 'archive_date_replay'
    description = ('Archive date replay using the historical state permitted at each stored vintage date. '
                   'Date precision does not establish an exact release time or availability before a trading decision that day.'
                   if archive else 'Historical derived observations at the stored evaluation cutoffs; consult the pinned evaluation policy for its timing meaning.')
    retrospective = manifest['metadata']['availability_semantics'] in (
        'unknown_historical_availability', 'retrospective_snapshot_unknown')
    if retrospective:
        description = ('Retrospective calculation from the pinned FX price snapshot. '
                       'Reference dates label historical prices; the evaluation cutoff identifies the fixed snapshot selection. '
                       'Historical Feature availability is unknown and remains null. '
                       'These observations do not certify historical decision-time eligibility or live readiness.')
    materializations = []
    for item in loaded:
        saved = item['manifest']
        materializations.append({'id': saved['id'], 'reference': reference(saved),
                                 'row_count': saved['row_count'], 'status_counts': saved['status_counts'],
                                 'coverage': _coverage(item['observations']),
                                 'href': output_prefix + identifier + '?materialization_id=' + saved['id']})
    return {'schema_version': '1.0.0', 'signal': _summary(store, loaded),
            'selected_materialization_id': manifest['id'], 'materializations': materializations,
            'statistics': descriptive_statistics(selected['observations'], manifest['metadata']['unit']),
            'recipe': recipe,
            'source_metadata': dict(selected['metadata'], provider=provider),
            'timing': {'precision': manifest['metadata']['temporal_precision'],
                       'history_mode': manifest['metadata']['history_mode'],
                       'availability_semantics': manifest['metadata']['availability_semantics'],
                       'evaluation_policy': evaluation, 'description': description,
                       'retrospective_snapshot': retrospective,
                       'evaluation_label': 'Snapshot cutoff' if retrospective else 'Archive date',
                       'coverage_label': 'Snapshot cutoff' if retrospective else 'Archive coverage'},
            'provenance': {'feature': reference(feature), 'materialization': reference(manifest),
                           'implementation': manifest['input_key']['implementation'],
                           'source_snapshots': manifest['input_key']['source_snapshots'],
                           'policy_bindings': manifest['input_key']['policy_bindings']},
            'observations': selected['observations'],
            'research': research if research is not None else {'state': 'untested', 'relationship_count': 0, 'metrics': [],
                         'description': 'No target/horizon relationship has been tested. IC and other research metrics are not yet available.'},
            'issues': []}
