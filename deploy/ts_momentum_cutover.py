"""Read-only capture of the accepted prefix of the paced TS momentum roster."""
import json
from pathlib import Path

from release_bundle import sha
from research.contracts import digest, normalize_submission, ref, scientific
from research.inputs import _validate_plan
from research.schedule import load_schedule, period_for
from research.store import read_json
from runtime.experiment_identity import IdentityIndex, scientific_key
from runtime.research_jobs import ACTIVE, ResearchJobs


PROGRAM = 'GAMBIT_TS_MOMENTUM_20261111'
INTAKE_UNIT = 'gambit-ts-momentum-paced-intake.service'
SCHEMA = 'ts_momentum_cutover_v1'


def bind_roster(roster_bytes, checkpoint, schedule):
    roster = json.loads(roster_bytes)
    entries = roster['entries']
    cursor = checkpoint.get('next_index')
    if (roster.get('program') != PROGRAM or roster.get('schedule') != ref(schedule)
            or roster.get('unresolved') != [] or len(entries) != 53 * 43
            or checkpoint.get('manifest_sha256') != sha(roster_bytes)
            or type(cursor) is not int or not 0 < cursor <= len(entries)
            or checkpoint.get('created') != cursor or checkpoint.get('existing') != 0
            or checkpoint.get('blocked') != []):
        raise RuntimeError('TS momentum roster or paced intake checkpoint differs')
    entries = [normalize_submission(row) for row in entries]
    ids = {row['request_id'] for row in entries}
    combinations = {(row['feature']['id'], row['scope']['id']) for row in entries}
    if (len(ids) != len(entries) or len(combinations) != len(entries)
            or len({feature for feature, _ in combinations}) != 53
            or len({scope for _, scope in combinations}) != 43
            or any(row['expected_direction'] != 'POSITIVE' for row in entries)):
        raise RuntimeError('TS momentum roster is not the exact positive pair/recipe grid')
    return entries, cursor


def capture(root, binding, *, roster_path, checkpoint_path, installed):
    """Verify both accepted work and the untouched staged suffix without intake."""
    from program_cutover import authority_inventory, verify_result_metadata, verify_trial_artifact_metadata

    root = Path(root)
    raw = roster_path.read_bytes()
    checkpoint_raw = checkpoint_path.read_bytes()
    if (set(binding) != {'schema', 'roster_sha256', 'checkpoint_sha256', 'global_pins'}
            or binding['schema'] != SCHEMA or binding['roster_sha256'] != sha(raw)
            or binding['checkpoint_sha256'] != sha(checkpoint_raw)):
        raise RuntimeError('TS cutover does not pin the current roster and checkpoint bytes')
    if binding['global_pins'] != {'implementation_digest': digest(installed),
                                   'implementation_fingerprint': installed['fingerprint']}:
        raise RuntimeError('TS cutover does not pin the original executor')
    schedule = load_schedule(root)
    if schedule is None:
        raise RuntimeError('Prospective research schedule is unavailable')
    entries, cursor = bind_roster(raw, read_json(checkpoint_path), schedule)
    jobs = ResearchJobs(root)
    index = IdentityIndex(jobs)
    events = jobs._event_snapshot()
    if events.get(None):
        raise RuntimeError('Unreadable research history during TS cutover')
    by_relationship = {}
    for path in (root/'storage/catalog/trial_ledger/records').glob('TRIAL_*.json'):
        trial = jobs.store.get('trial', path.stem)
        by_relationship.setdefault(trial['scientific_key']['relationship']['id'], []).append(trial)

    known, cohort, states = set(), [], {}
    for position, entry in enumerate(entries):
        rid = entry['request_id']
        journal = index.journal(rid)
        if position >= cursor:
            if journal or rid in events or jobs._submission_path(rid).exists() or jobs._job_path(rid).exists():
                raise RuntimeError('A staged TS request already has execution authority')
            continue
        if not journal or journal['canonical_request_id'] != rid:
            raise RuntimeError('Accepted TS request is missing its canonical journal')
        original = jobs._submission(rid)
        intent = {k:v for k,v in entry.items() if k != 'request_id'}
        identity = scientific_key(original)
        plan = original['frozen_plan']
        if (journal['intent'] != intent or original['intent'] != intent or journal['submission'] != original
                or journal['scientific_identity'] != identity or original['implementation'] != installed
                or plan['mode'] != 'TS' or plan['scope']['kind'] != 'instrument'
                or plan['scope']['id'] != entry['scope']['id'] or plan['recipe']['id'] != entry['feature']['id']
                or plan['profile'] != original['research_spec']
                or plan['profile'].get('research_schedule') != ref(schedule)):
            raise RuntimeError('Accepted TS request differs from its frozen inputs')
        _validate_plan(plan)
        job = jobs._read_job(rid, events)
        if job is None or job['status'] in ACTIVE - {'queued'}:
            raise RuntimeError('Drain active TS execution at a trial boundary')
        known.add(rid)
        refs = {}
        for horizon in plan['horizons']:
            relation = {'recipe': plan['recipe'], 'scope': plan['scope'], 'mode': 'TS',
                        'target_family': 'price_return', 'horizon': horizon, 'horizon_unit': 'scheduled_weekdays',
                        'members': [m['instrument_id'] for m in plan['members']],
                        'targets': [m['targets'][str(horizon)]['definition'] for m in plan['members']],
                        'expected_direction': intent['expected_direction']}
            if 'feature_application' in plan:
                relation['feature_application'] = plan['feature_application']
            for trial in by_relationship.get('RELATIONSHIP_' + digest(relation), []):
                key = trial['scientific_key']
                phase = key['stage']
                if (phase not in ('P1', 'P2') or key['horizon'] != horizon
                        or key['period'] != period_for(plan, phase, horizon)
                        or key['research_spec'] != ref(original['research_spec'])):
                    continue
                relationship = jobs.store.resolve('relationship', key['relationship'])
                targets = [{'instrument': m['instrument_id'], 'binding': m['targets'][str(horizon)]} for m in plan['members']]
                if relationship['body'] != scientific(relation) or key['targets'] != scientific(targets):
                    raise RuntimeError('Historical TS trial has different relationship or targets')
                if jobs.store.resolve('implementation', key['implementation'])['body'] != installed:
                    raise RuntimeError('Historical TS trial has an unexpected executor')
                verify_trial_artifact_metadata(jobs.store, trial)
                refs[trial['id']] = ref(trial)
        if job['status'] not in {'queued', 'succeeded'} or (job['status'] == 'queued' and refs):
            raise RuntimeError('TS request needs separate partial-result reconciliation')
        verify_result_metadata(jobs.store, job, refs)
        linked = {trial['id'] for link in job.get('results', [])
                  for trial in jobs.store.resolve('link', link)['body']['trial_results']}
        if linked != set(refs):
            raise RuntimeError('TS request has unlinked committed results')
        cohort.append({'request_id': rid, 'canonical_request_id': rid, 'intent_sha256': digest(intent),
                       'scientific_identity': identity, 'submission_sha256': original['record_sha256'],
                       'committed_trials': [refs[k] for k in sorted(refs)]})
        states[rid] = {'status': job['status'], 'sequence': job['sequence'], 'results': job.get('results', [])}

    names = {p.stem for p in (root/'storage/catalog/submissions').glob('*.json')}
    names.update(p.stem for p in (root/'storage/catalog/operations/jobs').glob('*.json'))
    names.update(events)
    for path in (index.base/'requests').glob('*.json'):
        journal = index.journal(path.stem)
        names.add(journal['canonical_request_id'])
    for rid in names:
        if (not jobs._submission_path(rid).is_file() or jobs._incident_path(jobs._submission_path(rid)).exists()
                or not (job := jobs._read_job(rid, events)) or (rid not in known and job['status'] in ACTIVE)):
            raise RuntimeError('Unresolved or unrelated active research authority')
    from data.legacy_batch_evidence import pending
    if pending(root):
        raise RuntimeError('Unapproved legacy batch remains pending')
    result = {'authority_scope': SCHEMA, 'cohort': cohort, 'states': states,
              'roster_sha256': sha(raw), 'checkpoint_sha256': sha(checkpoint_raw),
              'accepted': cursor, 'staged': len(entries) - cursor, 'authority': authority_inventory(root)}
    if roster_path.read_bytes() != raw or checkpoint_path.read_bytes() != checkpoint_raw:
        raise RuntimeError('The paced intake checkpoint changed during capture')
    result['snapshot_sha256'] = digest(result)
    return result


def checkpoint_binding(roster_path, checkpoint_path, installed):
    """Pin the inputs used for review without accepting or running a request."""
    return {'schema': SCHEMA, 'roster_sha256': sha(roster_path.read_bytes()),
            'checkpoint_sha256': sha(checkpoint_path.read_bytes()), 'global_pins': {
                'implementation_digest': digest(installed), 'implementation_fingerprint': installed['fingerprint']}}
