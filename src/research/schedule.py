"""Pin the prospective experiment schedule without changing historical plans."""

from copy import deepcopy
from datetime import date
from pathlib import Path

from research.contracts import HORIZONS, ResearchError, canonical, exact_selection, ref


ACTIVE = (1, 7, 21, 63)
CONFIG = 'config/research_schedule.json'


def load_schedule(root):
    from research.store import inside, read_json
    pointer = Path(root) / CONFIG
    if not pointer.is_file():
        return None
    binding = read_json(pointer)
    if set(binding) != {'id', 'version', 'content_sha256'}:
        raise ResearchError('Research schedule requires an exact reference')
    exact_selection({k: binding[k] for k in ('id', 'version')})
    path = inside(root, f"definitions/research_specs/{binding['id']}/{binding['version']}.json")
    schedule = read_json(path)
    if ref(schedule) != binding or path.read_bytes() != canonical(schedule) + b'\n':
        raise ResearchError('Installed research schedule content differs')
    if (schedule.get('kind') != 'prospective_research_schedule_v1'
            or schedule.get('approval_state') != 'approved'
            or schedule.get('horizons') != list(ACTIVE)):
        raise ResearchError('Installed research schedule is not approved or supported')
    policy = schedule['price_time_series']
    check_periods(policy['default'], automatic=True)
    check_periods(policy['63'], automatic=True)
    if policy['default']['P2']['end_exclusive'] != policy['63']['P2']['end_exclusive']:
        raise ResearchError('TS schedules must reserve the same historical test start')
    return schedule


def check_periods(periods, *, automatic):
    if set(periods) != {'P1', 'P2'}:
        raise ResearchError('Both research stages must have fixed periods')
    for phase, period in periods.items():
        if set(period) != {'start_inclusive', 'end_exclusive'}:
            raise ResearchError('Invalid research period fields')
        start, end = period['start_inclusive'], period['end_exclusive']
        for label in (end,) if phase == 'P1' and automatic and start is None else (start, end):
            if type(label) is not str or date.fromisoformat(label).isoformat() != label:
                raise ResearchError('Research period requires exact ISO dates')
        if start is not None and start >= end:
            raise ResearchError('Research period must increase')
    if periods['P1']['end_exclusive'] > periods['P2']['start_inclusive']:
        raise ResearchError('Discovery and validation periods must be disjoint and ordered')


def apply_schedule(profile, schedule, *, price_time_series):
    if profile is None or schedule is None:
        return profile
    value = deepcopy(profile)
    value['parent_research_spec'] = ref(profile)
    value['id'] = profile['id'] + '_PROSPECTIVE'
    value['version'] = schedule['version']
    value['research_schedule'] = ref(schedule)
    value['horizons'] = list(ACTIVE)
    if price_time_series:
        windows = schedule['price_time_series']
        value['periods'] = deepcopy(windows['default'])
        value['horizon_periods'] = {'63': deepcopy(windows['63'])}
        value['period_labels'] = {'P1': 'Pair history through 2021, or through 2016 for 63D',
                                  'P2': '2022–2024, or 2017–2024 for 63D'}
        value['exposure_classification']['interpretation'] = (
            'TS hypotheses use prespecified periods on prices previously used in related FX research. '
            'The 2025-01-01 through 2026-08-31 strategy test is retrospective.')
    return value


def validate_profile_schedule(profile):
    if 'research_schedule' not in profile:
        if 'horizons' in profile or 'horizon_periods' in profile:
            raise ResearchError('Custom horizons require a pinned research schedule')
        return
    binding = profile['research_schedule']
    if set(binding) != {'id', 'version', 'content_sha256'} or profile.get('horizons') != list(ACTIVE):
        raise ResearchError('The frozen horizon schedule differs from its approved form')
    overrides = profile.get('horizon_periods', {})
    if set(overrides) - {'63'}:
        raise ResearchError('Only 63D has a separate approved schedule')
    automatic = profile.get('discovery_start_rule') == 'scope_structural_start_v1'
    for periods in (profile['periods'], *overrides.values()):
        check_periods(periods, automatic=automatic)
        if max(period['end_exclusive'] for period in periods.values()) > profile['target_selection']['knowledge_cutoff']:
            raise ResearchError('Research window exceeds the pinned data cutoff')


def resolved_periods(profile, structural_start):
    """Return the historical plan fields plus exact prospective overrides, if present."""
    validate_profile_schedule(profile)
    periods = deepcopy(profile['periods'])
    automatic = profile.get('discovery_start_rule') == 'scope_structural_start_v1'
    if automatic and periods['P1']['start_inclusive'] is None:
        periods['P1']['start_inclusive'] = structural_start
    result = {'periods': periods, 'horizons': list(profile.get('horizons', HORIZONS))}
    if 'research_schedule' not in profile:
        return result
    overrides, excluded = {}, {}
    for horizon, windows in profile.get('horizon_periods', {}).items():
        windows = deepcopy(windows)
        discovery = windows['P1']
        if automatic and discovery['start_inclusive'] is None:
            discovery['start_inclusive'] = structural_start
        if discovery['start_inclusive'] >= discovery['end_exclusive']:
            result['horizons'].remove(int(horizon))
            excluded[horizon] = 'NO_STRUCTURAL_DISCOVERY_HISTORY'
        else:
            overrides[horizon] = windows
    if overrides:
        result['horizon_periods'] = overrides
    if excluded:
        result['excluded_horizons'] = excluded
    return result


def period_for(plan, phase, horizon=None):
    return plan.get('horizon_periods', {}).get(str(horizon), plan['periods'])[phase]
