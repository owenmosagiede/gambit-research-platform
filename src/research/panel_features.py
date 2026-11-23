"""Explicit UTC alignment for imported frozen panel fields, TS only.

This policy does not change the older date-only stored-series policy. Archive
dates and assumed retrospective publication lags remain uncertified evidence.
"""
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from data import panel_import as panels
from data.transformations.identity import reference, digest
from research.contracts import canonical, ref, profile_blockers
from research.store import inside, read_json, install_bytes

POLICY_ID = 'POL_FROZEN_PANEL_UTC_STATE'


def policy():
    return {'id':POLICY_ID,'version':'1.0.0','approval_state':'approved',
        'sampling_mode':'DAILY_STATE',
        'eligibility_rule':'original_UTC_strictly_before_anchor_00UTC',
        'availability_precision_rule':'preserve_package_UTC_and_original_precision_warning',
        'freshness_rule':{'mode':'PACKAGE_INTERVAL_AND_REFERENCE_AGE',
            'age_basis':'reference_end','unit':'calendar_days','precedence':'select_newest_then_age'},
        'invalid_update_rule':'newest_supersedes_including_null',
        'collision_rule':'reject_duplicate_UTC_effective_instants',
        'missing_anchor_rule':'preserve_scheduled_grid',
        'phase_context_rule':'one_prevailing_preperiod_state',
        'ceiling_rule':'no_target_anchor_after_package_capture',
        'capture_rule':'context_at_capture_only_no_historical_TS',
        'pair_rule':'same_pair_only_negate_if_target_quotation_reversed',
        'common_rule':'one_source_series_TS_only_no_currency_mapping_or_CS_broadcast'}


def validate_policy(value):
    if value != policy(): panels.fail('unimplemented panel alignment policy')
    return deepcopy(value)


def install_profile(root):
    from research.contracts import load_profile as base_profile
    base = base_profile(root)
    p = policy()
    profile = dict(base,id='RSPEC_FROZEN_PANEL_TS',version='1.0.0',
        application_class='external_stored_feature_to_individual_ts',
        external_alignment_policy=ref(p),inherited_research_spec=ref(base))
    for folder, value in [('alignment_policies',p),('research_specs',profile)]:
        install_bytes(inside(root,f"definitions/{folder}/{value['id']}/{value['version']}.json"),canonical(value)+b'\n')
    install_bytes(inside(root,'config/frozen_panel_alignment.json'),canonical({'research_spec':ref(profile)})+b'\n')
    return {'alignment_policy':ref(p),'research_spec':ref(profile)}


def load_profile(root):
    binding = read_json(inside(root,'config/frozen_panel_alignment.json'))['research_spec']
    p = inside(root,f"definitions/research_specs/{binding['id']}/{binding['version']}.json")
    value = read_json(p)
    if ref(value) != binding or p.read_bytes() != canonical(value)+b'\n' or profile_blockers(value):
        panels.fail('panel Research Spec identity/approval differs')
    from research.external_features import load_policy
    validate_policy(load_policy(root,value['external_alignment_policy']))
    return value


def resolve_source(root, feature, profile, target_pair=None, *, verify_database=True):
    from research.external_features import load_policy, next_weekday
    p = load_policy(root,profile['external_alignment_policy']); validate_policy(p)
    store,snapshot,manifest,view,dataset = panels.resolved(root,feature,verify_database=verify_database)
    projection = feature['body']['projection']; summary = projection['summary']
    if projection['layer'] == 'capture':
        panels.fail('capture-only context has no historical TS training eligibility; retain until refreshed')
    canonical_pair = projection['pair']; multiplier = 1
    if canonical_pair and target_pair:
        if target_pair == canonical_pair: pass
        elif target_pair == canonical_pair[3:]+canonical_pair[:3]: multiplier = -1
        else: panels.fail('pair macro field belongs to another currency pair')
    recipe = feature['body']['recipe']
    return {'feature':reference(feature),'materialization':reference(manifest),
        'metadata':{'selection':recipe['selection'],'source_view':reference(view),'dataset':reference(dataset),
            'unit':projection['unit'],'unit_label':projection['unit_label'],'temporal_precision':'UTC',
            'availability_semantics':'package_'+projection['layer']+'_not_intraday_certified',
            'history_mode':'emitted_history','history_policy':recipe['history_policy']},
        'source_snapshots':[reference(snapshot)],'alignment_policy':profile['external_alignment_policy'],
        'policy':p,'first_eligible_anchor':next_weekday(summary['first_valid'][:10]),
        'row_count':summary['row_count'],
        'status_counts':{'valid':summary['valid_count'],'missing':summary['row_count']-summary['valid_count'],'invalid':0},
        'coverage':{'reference_start':None,'reference_end':None,'cutoff_start':summary['cutoff_start'],
                    'cutoff_end':summary['cutoff_end']},
        'native_panel_profile':'frozen_panel_v1','frozen_max_asof':snapshot['body']['frozen_max_asof'],
        'source_layer':projection['layer'],'pair_orientation_multiplier':multiplier,
        'target_pair':target_pair,'source_pair':canonical_pair}


def phase_rows(root, source, period):
    from data.feature_store import FeatureStore
    store = FeatureStore(root); feature = store.resolve(source['feature'])
    _,snapshot,manifest,_,_ = panels.resolved(root,feature,verify_database=False)
    if reference(manifest) != source['materialization'] or [reference(snapshot)] != source['source_snapshots']:
        panels.fail('frozen source references differ')
    expected=resolve_source(root,feature,{'external_alignment_policy':source['alignment_policy']},
        source['target_pair'],verify_database=False)
    if expected != source: panels.fail('frozen panel alignment semantics differ')
    start = period['start_inclusive']+'T00:00:00Z'
    # No decoding of validation/future values: last included UTC instant is
    # strictly earlier than the phase's exclusive upper bound.
    from datetime import datetime, timezone
    bound = datetime.fromisoformat(period['end_exclusive']).replace(tzinfo=timezone.utc)-timedelta(seconds=1)
    end = min(bound.strftime('%Y-%m-%dT%H:%M:%SZ'),snapshot['body']['frozen_max_asof'])
    if start > end: return []
    return panels.read(root,feature,start=start,end=end)['observations']


def state_at(rows, anchor, value):
    validate_policy(value)
    instant = anchor+'T00:00:00Z'
    eligible = [r for r in rows if r['available_at'] < instant and r['evaluation_cutoff'] < instant]
    if not eligible: return None,None,'FEATURE_NOT_AVAILABLE'
    keys = [r['available_at'] for r in eligible]
    if len(set(keys)) != len(keys): panels.fail('duplicate eligible UTC states')
    row = max(eligible,key=lambda r:r['available_at'])
    age = (date.fromisoformat(anchor)-date.fromisoformat(row['reference_end'])).days if row['reference_end'] else None
    if instant > row['frozen_max_asof']: return row,age,'FROZEN_SOURCE_REFRESH_REQUIRED'
    if row['vintage_id'] == 'capture': return row,age,'CAPTURE_ONLY_CONTEXT'
    if row['available_until'] and instant >= row['available_until']: return row,age,'SOURCE_INTERVAL_EXPIRED'
    if row['status'] != 'valid': return row,age,row['reason_code']
    # Macro has a fully materialized daily grid with its own cadence-specific
    # staleness decisions; sparse market vectors require query-time age checks.
    table = row['lineage']['source_table']
    if table == 'feature_vectors' or (table == 'feature_states' and 'current_observation_id' in row['lineage'].get('source_lineage',{})):
        maximum = 14 if row['frequency']=='D' else 150
        if age is None or age < 0 or age > maximum: return row,age,'FEATURE_STALE'
    return row,age,None
