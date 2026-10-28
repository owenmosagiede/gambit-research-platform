#!/usr/bin/env python3
"""Staged, metadata-only status reader for an explicitly approved frozen program.

This command does not install approval, repair records, connect to a server,
write checkpoints, or change the active monitor. Run it from the reviewed
installed release only after separately approving reader activation. Existing
health/process monitoring and pass-identity checkpoint continuity must also be
retained by the activating wrapper. No numerical artifacts are opened here.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from api.signal_summaries import _verified_branch
from research.contracts import HORIZONS, canonical, digest, ref, request_id, scientific, ResearchConflict
from research.store import inside, read_json
from runtime import execution_compatibility as compatibility
from runtime.experiment_identity import scientific_key
from runtime.program_intake_compatibility import (load_operator, manifest_view,
    bridge_class, validate_entry_binding)


def require(condition, message):
    if not condition:
        raise ResearchConflict('Frozen program status: ' + message)


class MetadataVerifier:
    """Verify saved branches against exact program, approval and request authority.

    The caller must use a verified event snapshot for ``job`` and ``events``.
    ``read_status`` below supplies that boundary and runs the original operator's
    complete global metadata checks. This class never reads artifact manifests
    or payloads, and does not certify numerical recomputation/equivalence.
    """
    def __init__(self, store, *, manifest_bytes, operator_sha256, approval_reference,
                 actual_implementation, feature_catalog, target_metadata):
        self.store = store
        self.manifest_sha256 = sha256(manifest_bytes).hexdigest()
        self.approval = compatibility.for_program(store.root,
            manifest_sha256=self.manifest_sha256, operator_sha256=operator_sha256,
            actual_implementation=actual_implementation, binding=approval_reference)
        # Duplicate fields and nonfinite literals must not acquire a different
        # interpretation from the exact operator's strict JSON parser.
        def pairs(items):
            result = {}
            for name, value in items:
                require(name not in result, 'duplicate manifest field')
                result[name] = value
            return result
        self.manifest = json.loads(manifest_bytes, object_pairs_hook=pairs,
            parse_constant=lambda value: require(False, 'nonfinite manifest literal'))
        manifest_view(self.manifest, self.approval, actual_implementation)
        self.rows = {row['request_id']: row for row in self.manifest['entries']}
        self.catalog, self.targets = deepcopy(feature_catalog), deepcopy(target_metadata)
        previous = self.approval['proposal'].get('predecessor_approval')
        self.previous = (MetadataVerifier(store, manifest_bytes=manifest_bytes,
            operator_sha256=operator_sha256, approval_reference=ref(previous),
            actual_implementation=previous['proposal']['to_implementation'],
            feature_catalog=feature_catalog, target_metadata=target_metadata) if previous else None)
        self.historical_context = {}
        self.attempts = {}
        for path in sorted(inside(store.root, compatibility.BASE + '/attempts').glob('*.json')):
            value = read_json(path)
            compatibility._identity(value, 'EXECATTEMPT')
            require(set(value) == {'id', 'schema', 'version', 'request_id', 'attempt_id',
                'submission_sha256', 'approval', 'requested_implementation', 'executing_implementation'} and
                value['schema'] == 'frozen_program_execution_attempt_v1' and value['version'] == '1.0.0' and
                path.name == value['id'] + '.json' and path.read_bytes() == canonical(value) + b'\n',
                'execution attempt record differs')
            request_id(value['request_id']); request_id(value['attempt_id'])
            if value['approval'] == ref(self.approval):
                compatibility.row_for(self.approval, value['request_id'], canonical=True)
                self.attempts.setdefault(value['request_id'], []).append(value)

    def _execution_provenance(self, original, events):
        attempts = self.attempts.get(original['request_id'], [])
        observed = {event['job']['attempt_id'] for event in events
                    if event['request_id'] == original['request_id'] and
                    event['job']['request_id'] == original['request_id']}
        visible = []
        for value in attempts:
            require(value['submission_sha256'] == original['record_sha256'] and
                    value['requested_implementation'] == original['implementation'] and
                    value['executing_implementation'] == self.approval['proposal']['to_implementation'],
                    'execution attempt is not this frozen request')
            # The worker may start another attempt after our verified event
            # snapshot. Its later metadata is not evidence for that snapshot.
            if value['attempt_id'] in observed:
                visible.append(value)
        return visible

    def _history_context(self, original, events):
        """Recheck inherited intents and event provenance, not only new pins."""
        if self.previous is None:
            return
        self.previous._history_context(original, events)
        row = compatibility.row_for(self.previous.approval, original['request_id'], canonical=True)
        self.historical_context[original['request_id']] = (
            {r['id']: r for r in row['committed_trials']},
            {r['id']: r for r in compatibility._claimed_trials(self.store, self.previous.approval, original)},
            self.previous._execution_provenance(original, events))

    def _trial(self, trial, original, pinned, claimed, attempts, discovery=None):
        plan = original['frozen_plan']; key = trial['scientific_key']; body = trial['body']
        phase, horizon = key['stage'], key['horizon']
        require(phase in ('P1', 'P2') and horizon in HORIZONS and body['stage'] == phase,
                'trial phase/horizon differs')
        relation = self.store.resolve('relationship', key['relationship'])
        expected = {'recipe': plan['recipe'], 'scope': plan['scope'], 'mode': plan['mode'],
            'target_family': 'price_return', 'horizon': horizon, 'horizon_unit': 'scheduled_weekdays',
            'members': [m['instrument_id'] for m in plan['members']],
            'targets': [m['targets'][str(horizon)]['definition'] for m in plan['members']],
            'expected_direction': plan['intent']['expected_direction']}
        if 'feature_application' in plan:
            expected['feature_application'] = plan['feature_application']
        require(relation['body'] == scientific(expected) and relation['scientific_key'] == scientific(expected),
                'result differs from frozen relationship')
        require(key['period'] == plan['periods'][phase] and key['research_spec'] == ref(original['research_spec']) and
                body['expected_direction'] == plan['intent']['expected_direction'] == 'POSITIVE' and
                key['targets'] == [{'instrument': m['instrument_id'], 'binding': m['targets'][str(horizon)]}
                                   for m in plan['members']], 'trial scientific inputs differ')
        prepared = key['prepared']
        require(prepared['phase'] == phase and prepared['period'] == plan['periods'][phase] and
                [m['instrument_id'] for m in prepared['members']] == expected['members'],
                'trial prepared membership/period differs')
        if phase == 'P1':
            require(key['discovery_trial'] is None and key['discovery_effect'] is None,
                    'discovery trial has validation ancestry')
        else:
            require(discovery is not None and key['discovery_trial'] == ref(discovery) and
                    key['discovery_effect'] == discovery['body']['metrics']['primary_effect'] and
                    discovery['scientific_key']['horizon'] == horizon and
                    discovery['scientific_key']['relationship'] == key['relationship'],
                    'validation ancestry/effect differs')
        impl = self.store.resolve('implementation', key['implementation'])
        require(impl['scientific_key'] == impl['body'], 'implementation identity differs')
        if pinned.get(trial['id']) == ref(trial):
            require(compatibility.historical_executor_matches(self.approval, trial, impl, original=original),
                    'pinned historical trial executor differs')
            if self.previous is not None:
                require(original['request_id'] in self.historical_context, 'historical provenance context missing')
                old_pins, old_claimed, old_attempts = self.historical_context[original['request_id']]
                self.previous._trial(trial, original, old_pins, old_claimed, old_attempts, discovery=discovery)
            return 'approved_historical_reference'
        require(impl['body'] == self.approval['proposal']['to_implementation'] and
                claimed.get(trial['id']) == ref(trial) and bool(attempts),
                'new trial lacks exact approved executor, trial intent or execution attempt')
        return 'approved_new_executor'

    def verify_entry(self, rid, *, original, journal, receipt, job, events):
        row = self.rows[rid]
        pin = compatibility.validate_cohort_envelope(self.approval, rid, original)
        require(journal['schema'] == 'experiment_intake_v1' and journal['request_id'] == rid and
                journal['canonical_request_id'] == pin['canonical_request_id'] and
                journal['intent'] == original['intent'] == row['intent'] and
                journal['scientific_identity'] == scientific_key(original) and
                journal['sha256'] == digest({k: v for k, v in journal.items() if k != 'sha256'}) and
                journal['requested_implementation'] in compatibility.requested_implementations(self.approval),
                'accepted journal differs')
        require(journal.get('submission') == original or
                (rid != original['request_id'] and journal.get('submission') is None),
                'journal submission differs from frozen envelope')
        require(receipt['schema'] == 'gambit_finite_intake_receipt_v1' and
                receipt['manifest_sha256'] == self.manifest_sha256 and
                all(receipt[k] == journal[k] for k in ('request_id', 'canonical_request_id', 'scientific_identity')) and
                receipt['journal_sha256'] == journal['sha256'], 'program receipt differs')
        validate_entry_binding(self.manifest, row, original, feature_catalog=self.catalog,
                               target_metadata=self.targets)
        require(job is not None and job['request_id'] == original['request_id'], 'accepted event history is missing')
        historical = bool(row.get('expected_existing_request_id'))
        if historical:
            require(job['status'] == 'succeeded' and job['results'] == row['expected_existing_result_references'] and
                    journal['scientific_identity'] == row['expected_existing_scientific_identity'],
                    'historical alias result references differ')
        else:
            require(original['implementation'] in compatibility.requested_implementations(self.approval),
                    'request executor is outside exact approval')
        pinned = {r['id']: r for r in pin['committed_trials']}
        claimed = {r['id']: r for r in compatibility._claimed_trials(self.store, self.approval, original)}
        attempts = self._execution_provenance(original, events)
        self._history_context(original, events)
        # Include committed partial/orphan authority, not just currently linked
        # outcomes. An interrupted publication is never counted as a pass.
        closure = {**pinned, **(claimed if attempts else {})}
        for binding in closure.values():
            trial = self.store.resolve('trial', binding)
            p1 = (self.store.resolve('trial', trial['scientific_key']['discovery_trial'])
                  if trial['scientific_key']['stage'] == 'P2' else None)
            if p1 is not None:
                self._trial(p1, original, pinned, claimed, attempts)
            self._trial(trial, original, pinned, claimed, attempts, discovery=p1)
        outcomes = []; seen = set()
        recipe = next(r for r in self.manifest['recipes'] if r['reference'] == row['recipe_reference'])
        for link_ref in job.get('results', []):
            link = self.store.resolve('link', link_ref)
            require(link['scientific_key'] == link['body'], 'result link identity differs')
            relation, trials, admissions, validations = _verified_branch(self.store, link)
            h = relation['body']['horizon']
            require(h not in seen, 'duplicate horizon result'); seen.add(h)
            stages = {trial['body']['stage']: trial for trial in trials}; p1 = stages['P1']
            provenance = [self._trial(t, original, pinned, claimed, attempts,
                          discovery=p1 if t['body']['stage'] == 'P2' else None) for t in trials]
            admission = admissions[0]
            require(admission['scientific_key'] == {'trial': ref(p1)} and
                    admission['body'].get('evidence', {}) == p1['body'].get('evidence', {}) and
                    admission['body'].get('reason_codes', []) == p1['body'].get('reason_codes', []),
                    'admission evidence differs from saved discovery')
            decision1 = admission['body']['decision']
            validation = validations[0] if validations else None
            decision2 = validation['body']['decision'] if validation else ('pending' if decision1 == 'admitted' else 'not_admitted')
            passed = False
            if validation and validation['body']['evaluation_trial'] is None:
                require(validation['body']['period'] == original['frozen_plan']['periods']['P2'] and
                        validation['body']['research_spec'] == ref(original['research_spec']),
                        'validation precheck period/profile differs')
            if decision2 == 'VALIDATED':
                p2 = stages['P2']; effect = p1['body']['metrics']['primary_effect']
                require(type(effect) in (int, float, str) and Decimal(str(effect)).is_finite() and
                        Decimal(str(effect)) > 0 and decision1 == 'admitted' and
                        p1['body']['execution_status'] == p2['body']['execution_status'] == 'completed' and
                        p2['body']['decision'] == 'VALIDATED' and
                        p2['body']['sample']['validation_data_accessed'] is True,
                        'saved validation success does not satisfy stage gates')
                passed = True
            terminal = decision1 in ('rejected', 'unresolved') or decision2 in ('VALIDATED', 'FAILED', 'UNRESOLVED')
            outcomes.append({'horizon': h, 'relationship': ref(relation),
                'validation': ref(validation) if validation else None, 'p1': decision1, 'p2': decision2,
                'terminal': terminal, 'stage_gates_passed': passed, 'recipe': row['recipe_reference'],
                'recipe_name': recipe.get('display_name'), 'recipe_parameters': recipe.get('parameters'),
                'scope': row['scope_reference']['id'], 'historical_reuse': historical,
                'trial_execution_provenance': provenance})
        if job['status'] == 'succeeded':
            require(seen == set(HORIZONS) and all(r['terminal'] for r in outcomes),
                    'completed experiment has incomplete saved decisions')
        return outcomes


def read_status(root, manifest_path, operator_path, approval_reference):
    """Read installed authority once; no network, writes or service operations."""
    from runtime.research_jobs import implementation
    root = Path(root).resolve()
    require(root == Path(__file__).resolve().parents[1], 'run the exact installed reviewed reader')
    approval = compatibility.resolve(root, approval_reference)
    operator = load_operator(operator_path, approval['proposal']['operator_sha256'])
    with operator.read_only():
        raw = operator.stable_bytes(manifest_path)
        manifest = operator.validate_manifest(operator.strict_json(raw))
        sha = sha256(raw).hexdigest()
        compatibility.for_program(root, manifest_sha256=sha, operator_sha256=approval['proposal']['operator_sha256'],
            actual_implementation=implementation(), binding=approval_reference)
        bridge_type = bridge_class(operator, approval, manifest_sha256=sha,
            operator_sha256=approval['proposal']['operator_sha256'], frozen_manifest=manifest)
        bridge = bridge_type(root); bridge.check_context(submit=False)
        bridge.verify_global(manifest)  # Exact original metadata checks; verify_rows=False.
        # Snapshot events before resolving supporting append-only metadata, so
        # every trial linked in this view already has durable intent/attempts.
        snapshot = bridge.jobs._event_snapshot()
        verifier = MetadataVerifier(bridge.jobs.store, manifest_bytes=raw,
            operator_sha256=approval['proposal']['operator_sha256'], approval_reference=approval_reference,
            actual_implementation=implementation(), feature_catalog=bridge.catalog, target_metadata=bridge.target_metadata)
        rows = []; issues = []
        observed = datetime.now(timezone.utc).isoformat()
        allowed = set(verifier.rows) | {r.get('expected_existing_request_id', r['request_id']) for r in manifest['entries']}
        authority_ids = set(snapshot) - {None}
        for folder in ('storage/catalog/submissions', 'storage/catalog/operations/experiment_intake/requests',
                       'storage/catalog/operations/jobs'):
            authority_ids.update(p.stem for p in inside(root, folder).glob('*.json'))
        if snapshot.get(None) or authority_ids - allowed:
            issues.append({'unrelated_or_unreadable_authority': sorted(authority_ids - allowed),
                           'unreadable_events': snapshot.get(None, [])})
        for row in manifest['entries']:
            rid = row['request_id']; result = {'ordinal': row['ordinal'], 'request_id': rid,
                                              'scope': row['intent']['scope']['id']}
            try:
                journal = bridge.identity.journal(rid)
                require(journal is not None, 'complete accepted intake is required for this staged reader')
                cid = journal['canonical_request_id']; original = bridge.jobs._submission(cid)
                require(not bridge.jobs._incident_path(bridge.jobs._submission_path(cid)).exists(),
                        'submission integrity incident')
                receipt = read_json(inside(root, 'storage/catalog/operations/program_intake_receipts/' + sha + '/' + rid + '.json'))
                events = bridge.jobs._events(cid, snapshot); job = bridge.jobs._read_job(cid, snapshot)
                outcomes = verifier.verify_entry(rid, original=original, journal=journal, receipt=receipt, job=job, events=events)
                result.update(canonical_request_id=cid, scientific_identity=journal['scientific_identity'],
                    journal_sha256=journal['sha256'], receipt_verified=True, outcomes=outcomes,
                    historical_reuse=bool(row.get('expected_existing_request_id')), status=job['status'],
                    stage=job.get('stage'), updated_at=job.get('updated_at'), sequence=job.get('sequence'),
                    result_links=len(job.get('results', [])), progress=job.get('progress'), blockers=job.get('blockers', []))
            except Exception as exc:
                result.update(status='reconciliation_issue', error=str(exc))
                issues.append({'request_id': rid, 'error': str(exc)})
            rows.append(result)
        outcomes = [o for row in rows for o in row.get('outcomes', [])]
        passes = [o for o in outcomes if o['stage_gates_passed']]
        planned = len(manifest['entries']); receipts = sum(row.get('receipt_verified', False) for row in rows)
        return {'schema': 'momentum_program_heartbeat_approved_execution_v1', 'observed_at': observed,
            'manifest_sha256': sha, 'execution_compatibility': approval_reference, 'planned': planned,
            'verification': 'immutable metadata only; no artifact manifest/payload reads or numerical recomputation',
            'monitor_activation': 'staged candidate; active health/process/checkpoint wrapper must be retained',
            'verified_receipts': receipts, 'intake_complete': receipts == planned and not issues,
            'queue_counts': dict(Counter(row['status'] for row in rows)), 'issues': issues,
            'horizon_counts': {'p1': dict(Counter(o['p1'] for o in outcomes)), 'p2': dict(Counter(o['p2'] for o in outcomes))},
            'terminal_horizons': sum(o['terminal'] for o in outcomes), 'planned_horizons': planned * len(HORIZONS),
            'verified_passes': passes, 'historical_passes': sum(o['historical_reuse'] for o in passes),
            'new_research_passes': sum(not o['historical_reuse'] for o in passes),
            'program_complete': len(outcomes) == planned * len(HORIZONS) and
                all(row['status'] == 'succeeded' for row in rows) and all(o['terminal'] for o in outcomes) and not issues,
            'rows': rows}


def merge_checkpoint(current, previous=None):
    """Pure checkpoint merge; only a complete, issue-free read advances history.

    Program completion is not required: a healthy read of in-progress work can
    report new saved passes. Failed/incomplete reads preserve all previously
    known identities and the last successful observation time. The activation
    wrapper owns checkpoint IO and must keep its last successful file intact.
    """
    result = deepcopy(current)
    require(result.get('schema') == 'momentum_program_heartbeat_approved_execution_v1' and
            isinstance(result.get('manifest_sha256'), str) and
            re.fullmatch('[0-9a-f]{64}', result['manifest_sha256']), 'checkpoint program identity differs')
    known = set()
    last_success = None
    if previous is not None:
        require(previous.get('schema') in ('momentum_program_heartbeat_v1',
                'momentum_program_heartbeat_approved_execution_v1') and
                previous.get('manifest_sha256') == result['manifest_sha256'],
                'previous checkpoint belongs to another program')
        if previous.get('execution_compatibility'):
            require(previous['execution_compatibility'] == result.get('execution_compatibility'),
                    'previous checkpoint uses another execution approval')
        known.update(previous.get('verified_pass_identity_history', []))
        if previous.get('checkpoint_advanced', not previous.get('issues', [])):
            known.update(p['relationship']['id'] for p in previous.get('verified_passes', []))
            last_success = previous.get('last_successful_observed_at', previous.get('observed_at'))
        else:
            last_success = previous.get('last_successful_observed_at')
        result['previous_observed_at'] = previous.get('observed_at')
    require(all(isinstance(identity, str) and re.fullmatch('RELATIONSHIP_[0-9a-f]{64}', identity)
                for identity in known), 'previous pass identity is malformed')
    rows, passes = result.get('rows'), result.get('verified_passes')
    complete = (result.get('issues') == [] and result.get('intake_complete') is True and
        type(result.get('planned')) is int and result['planned'] > 0 and
        result.get('verified_receipts') == result['planned'] and type(rows) is list and
        len(rows) == result['planned'] and type(passes) is list and
        all(row.get('receipt_verified') is True and type(row.get('outcomes')) is list and
            row.get('status') != 'reconciliation_issue' for row in rows))
    if complete:
        derived = [p for row in rows for p in row['outcomes'] if p.get('stage_gates_passed') is True]
        require(passes == derived and len({p['relationship']['id'] for p in passes}) == len(passes),
                'checkpoint pass projection differs from verified rows')
        for item in passes:
            binding = item['relationship']
            require(set(binding) == {'id', 'version', 'content_sha256'} and
                    re.fullmatch('RELATIONSHIP_[0-9a-f]{64}', binding['id']) and binding['version'] == '1.0.0' and
                    re.fullmatch('[0-9a-f]{64}', binding['content_sha256']) and item['terminal'] is True,
                    'checkpoint contains an unverified pass identity')
        result['new_passes_since_previous'] = ([p for p in passes if p['relationship']['id'] not in known]
                                                if previous is not None else None)
        known.update(p['relationship']['id'] for p in passes)
        last_success = result['observed_at']
    else:
        result['new_passes_since_previous'] = [] if previous is not None else None
    result['checkpoint_advanced'] = complete
    result['last_successful_observed_at'] = last_success
    result['verified_pass_identity_history'] = sorted(known)
    if previous is None:
        result['baseline_checkpoint'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'manifest', 'operator', 'approval-reference'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(read_status(args.root, args.manifest, args.operator,
                                read_json(args.approval_reference)), indent=2))


if __name__ == '__main__':
    main()
