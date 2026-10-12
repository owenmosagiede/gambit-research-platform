"""Install the approved external stored Feature research policy; execute no research."""
from pathlib import Path
from research.contracts import load_profile, canonical, ref
from research.store import install_bytes, inside
from research.external_features import validate_policy


def install(root):
    policy = validate_policy({'id': 'POL_EXTERNAL_STORED_DAILY_STATE', 'version': '1.0.0',
        'approval_state': 'approved', 'sampling_mode': 'DAILY_STATE',
        'eligibility_rule': 'availability_and_evaluation_strictly_before_anchor',
        'availability_precision_rule': 'date_only_next_scheduled_weekday',
        'freshness_rule': {'mode': 'UNTIL_SUPERSEDED', 'age_basis': 'evaluation_cutoff',
                          'unit': 'calendar_days', 'precedence': 'select_newest_then_age'},
        'invalid_update_rule': 'newest_supersedes_including_null',
        'collision_rule': 'reject_duplicate_effective_dates',
        'missing_anchor_rule': 'preserve_scheduled_grid',
        'phase_context_rule': 'one_prevailing_preperiod_state'})
    base = load_profile(root)
    profile = dict(base, id='RSPEC_EXTERNAL_STORED_TS', version='1.0.0',
        application_class='external_stored_feature_to_individual_ts',
        external_alignment_policy=ref(policy), inherited_research_spec=ref(base))
    for folder, value in [('alignment_policies', policy), ('research_specs', profile)]:
        install_bytes(inside(root, f"definitions/{folder}/{value['id']}/{value['version']}.json"), canonical(value)+b'\n')
    install_bytes(inside(root, 'config/external_feature_alignment.json'), canonical({'research_spec': ref(profile)})+b'\n')
    return {'alignment_policy': ref(policy), 'research_spec': ref(profile)}


if __name__ == '__main__':
    import json
    print(json.dumps(install(Path(__file__).resolve().parents[1]), indent=2))
