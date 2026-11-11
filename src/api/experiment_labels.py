"""Read-only experiment captions from the submission's exact frozen references."""
from copy import deepcopy

from api.research_labels import recipe_label, scope_label
from data.feature_store import FeatureStore


def with_experiment_labels(root, jobs, value):
    """A missing label never hides a job or falls back to today's dropdowns.

    Resolving definitions reads metadata only. This adapter neither resolves new
    input plans nor opens prices, observations or numerical research artifacts.
    """
    result = deepcopy(value)
    store = FeatureStore(root)
    for item in result['items']:
        item['presentation'] = {
            'state': 'unavailable',
            'message': 'Saved input labels could not be verified. Exact selections are retained below.',
        }
        if not item.get('intent') or item['job'].get('operational_failure'):
            continue
        try:
            original = jobs._submission(item['job']['request_id'])
            intent = item['intent']
            if original['intent'] != intent:
                raise ValueError('Submission selection differs')
            plan = original['frozen_plan']
            recipe_ref, frozen_scope = plan['recipe'], plan['scope']
            scope_ref = frozen_scope['reference']
            for reference, selection in ((recipe_ref, intent['feature']), (scope_ref, intent['scope'])):
                if {key: reference[key] for key in ('id', 'version')} != selection:
                    raise ValueError('Frozen definition differs from intent')
            mode = plan['mode']
            if mode not in ('TS', 'CS') or frozen_scope['kind'] != ('instrument' if mode == 'TS' else 'universe'):
                raise ValueError('Frozen Scope kind differs from mode')
            members = frozen_scope['members']
            if not isinstance(members, list) or not members or any(not isinstance(m, str) for m in members) or len(set(members)) != len(members):
                raise ValueError('Invalid frozen membership')
            feature = store.resolve(recipe_ref)
            scope = store.resolve(scope_ref)
            feature_name, scope_name = recipe_label(feature), scope_label(scope)
            direction = {'POSITIVE': 'Positive hypothesis', 'NEGATIVE': 'Negative hypothesis'}[intent['expected_direction']]
            mode_name = 'Cross-sectional' if mode == 'CS' else 'Time-series'
            members_name = ('currencies' if frozen_scope.get('reference_currency') else 'instruments') if mode == 'CS' else 'instrument'
            target_label = 'Forward price return · five forecast horizons'
            if plan.get('profile', {}).get('research_schedule'):
                target_label = 'Forward price return · ' + ', '.join(f'{h}D' for h in plan['horizons'])
            item['presentation'] = {
                'state': 'verified',
                'feature_label': feature_name, 'scope_label': scope_name,
                'title': f'{feature_name} · {scope_name}',
                'subtitle': f'{mode_name} · {len(members)} {members_name} · {direction}',
                'target_label': target_label,
                'schedule_note': 'Lookbacks and forecast horizons use scheduled weekdays.',
                'feature_reference': deepcopy(recipe_ref), 'scope_reference': deepcopy(scope_ref),
                'membership_snapshot': deepcopy(frozen_scope['membership_snapshot']),
                'member_count': len(members), 'mode': mode,
            }
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            # The original queue/result remains visible; never guess its inputs.
            continue
    return result
