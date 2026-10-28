"""Review-scoped adapter around the exact original finite intake operator.

The original manifest, operator, UUIDs and receipts remain authoritative. Only
its old implementation gate is replaced, explicitly, with the separately
approved execution gate. All metadata/scientific/context/resource checks remain.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import ModuleType

from research.contracts import digest, ref, ResearchConflict
from runtime.execution_compatibility import (for_program, row_for,
    validate_cohort_packet, validate_cohort_envelope, requested_implementations)


def load_operator(path, expected_sha256):
    """Execute the same bytes that were hashed, with no import-time workspace IO."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ResearchConflict('Frozen intake operator bytes differ from approval')
    module = ModuleType('approved_frozen_intake_operator')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def manifest_view(manifest, approval, actual_implementation):
    """An ephemeral implementation-gate view, never serialized or re-identified."""
    proposal = approval['proposal']; pins = manifest['global_pins']
    old = proposal['from_implementation']
    if (pins['implementation_digest'] != digest(old) or
            pins['implementation_fingerprint'] != old['fingerprint'] or
            actual_implementation != proposal['to_implementation']):
        raise ResearchConflict('Frozen manifest/executor implementation pins differ')
    rows = {r['request_id']: r for r in manifest['entries']}
    if len(rows) != len(manifest['entries']) or set(rows) != {r['request_id'] for r in proposal['cohort']}:
        raise ResearchConflict('Approved cohort does not cover the exact frozen manifest')
    for rid, row in rows.items():
        pin = row_for(approval, rid)
        if (pin['canonical_request_id'] != row.get('expected_existing_request_id', rid) or
                pin['intent_sha256'] != digest(row['intent']) or
                (row.get('expected_existing_scientific_identity') is not None and
                 pin['scientific_identity'] != row['expected_existing_scientific_identity'])):
            raise ResearchConflict('Approved cohort differs from frozen program entry')
    view = deepcopy(manifest)
    view['global_pins']['implementation_digest'] = digest(actual_implementation)
    view['global_pins']['implementation_fingerprint'] = actual_implementation['fingerprint']
    return view


def validate_entry_binding(manifest, row, packet, *, feature_catalog, target_metadata):
    """Pure metadata validation shared by intake and cutover capture.

    Callers resolve exact immutable catalog/Target records once and pass them in;
    no observation payloads, materialization or job writes occur here.
    """
    from research.inputs import _validate_plan
    from research.contracts import HORIZONS
    from data.transformations.identity import reference
    def require(condition, message):
        if not condition: raise ResearchConflict('Frozen program binding: ' + message)
    plan = packet['frozen_plan']; _validate_plan(plan)
    pins = manifest['global_pins']
    scope = next(s for s in manifest['scopes'] if s['reference'] == row['scope_reference'])
    recipe = next(r for r in manifest['recipes'] if r['reference'] == row['recipe_reference'])
    profile = packet['research_spec']
    require(plan['intent'] == packet['intent'] == row['intent'] and plan['profile'] == profile and
            ref(profile) == pins['research_spec'] and
            digest(profile['target_selection']) == pins['source_and_target_pins_sha256'] and
            plan['recipe'] == row['recipe_reference'] and plan['periods'] == row['periods'] and
            plan['mode'] == 'CS' and plan['horizons'] == list(HORIZONS) and
            plan['scope']['reference'] == row['scope_reference'] and
            plan['scope']['membership_snapshot'] == row['membership_snapshot'] and
            plan['knowledge_cutoff'] == pins['knowledge_cutoff'], 'profile, recipe, Scope or period differs')
    for name in ('reference', 'membership_snapshot', 'members', 'reference_currency', 'price_catalog', 'research_basis'):
        require(plan['scope'][name] == scope[name], 'Scope ' + name + ' differs')
    require(plan['scope']['id'] == row['scope_reference']['id'] and
            plan['scope']['version'] == row['scope_reference']['version'] and
            plan['scope']['kind'] == 'universe', 'Scope identity differs')
    require([m['instrument_id'] for m in plan['members']] == scope['members'], 'ordered members differ')
    require(packet.get('feature_application') == plan.get('feature_application') and
            plan['feature_application']['binding'] == recipe['application_binding'], 'Feature application differs')
    require(reference(feature_catalog) == pins['feature_catalog'] and
            digest(feature_catalog['body']['bindings']) == pins['feature_bindings_sha256'], 'Feature catalog differs')
    configurations = {r['recipe']['id']: r['configuration'] for r in feature_catalog['body']['recipes']}
    require(configurations[recipe['reference']['id']] == recipe['configuration'], 'Feature configuration differs')
    bindings = {b['instrument_id']: b for b in feature_catalog['body']['bindings']
                if b['configuration_id'] == recipe['configuration']['id']}
    for member in plan['members']:
        binding = bindings[member['instrument_id']]
        for name in ('feature', 'price_snapshot', 'source_view'):
            require(member[name] == binding[name], 'member ' + name + ' differs')
        require(set(member['targets']) == {str(h) for h in HORIZONS}, 'Target horizons differ')
        for horizon, target in member['targets'].items():
            materialization = profile['target_selection']['materializations'][member['instrument_id']][horizon]
            record = target_metadata[member['instrument_id']][horizon]
            require(target['materialization'] == materialization and reference(record) == materialization and
                    target['definition'] == record['definition'] and record['price_snapshot'] == member['price_snapshot'],
                    'Target definition, source or materialization differs')
    from runtime.experiment_identity import scientific_key
    return scientific_key(packet)


def bridge_class(operator, approval, *, manifest_sha256, operator_sha256, frozen_manifest):
    """Retain original finite workflow; replace only reviewed identity gates."""
    require = operator.require
    binding = ref(approval)
    frozen_digest = digest(frozen_manifest)

    class ApprovedRuntimeBridge(operator.RuntimeBridge):
        def _approval(self, manifest):
            from runtime.research_jobs import implementation
            require(digest(manifest) == frozen_digest, 'Original frozen manifest changed')
            value = for_program(self.root, manifest_sha256=manifest_sha256,
                operator_sha256=operator_sha256, actual_implementation=implementation(), binding=binding)
            require(value == approval, 'Execution approval changed')
            return value

        def verify_global(self, manifest):
            from runtime.research_jobs import implementation
            reviewed = self._approval(manifest)
            # The old operator still checks every original scientific/global pin.
            # No replacement manifest is written, approved or used for receipts.
            return super().verify_global(manifest_view(manifest, reviewed, implementation()))

        def _envelope(self, row, original):
            return validate_cohort_envelope(approval, row['request_id'], original)

        def validate_packet(self, manifest, row, packet):
            # Replace the old global release-relation check for the one alias
            # with exact approved envelope/science pins, then run every original
            # frozen Scope/Feature/Target/member/period validation unchanged.
            validate_entry_binding(manifest, row, packet, feature_catalog=self.catalog,
                                   target_metadata=self.target_metadata)
            scientific_row = dict(row)
            scientific_row.pop('expected_existing_request_id', None)
            expected = super().validate_packet(manifest, scientific_row, packet)
            validate_cohort_packet(approval, row['request_id'], packet)
            if row.get('expected_existing_request_id'):
                old = self.jobs._submission(row['expected_existing_request_id'])
                self._envelope(row, old)
                job = self.jobs._read_job(old['request_id'])
                require(job and job['status'] == 'succeeded' and
                        job['results'] == row['expected_existing_result_references'],
                        'Exact historical alias result pins differ')
                self.identity.verify_results(job)
            return expected

        def verify_history(self, manifest):
            index = self.identity.rebuild(persist=False)
            require(not index['issues'], 'Existing research history needs reconciliation')
            rows = {r['request_id']: r for r in manifest['entries']}
            by_canonical = {}
            for row in rows.values():
                by_canonical.setdefault(row.get('expected_existing_request_id', row['request_id']), []).append(row)
            require(set(index['pending']) <= set(rows), 'Unrelated pending intake exists')
            for rid in index['entries']:
                require(rid in by_canonical, 'Unrelated research exists; review before program intake')
                if rid in index['pending']:
                    journal = self.identity.journal(rid)
                    require(journal and journal['intent'] == rows[rid]['intent'] and journal.get('submission'),
                            'Pending intake differs from program')
                    self._envelope(rows[rid], journal['submission'])
                    continue
                original = self.jobs._submission(rid)
                job = self.jobs._read_job(rid)
                require(job is not None and job['status'] not in operator.UNHEALTHY_RESULTS,
                        'Existing work needs explicit recovery')
                for row in by_canonical[rid]:
                    self._envelope(row, original)
                    self.validate_packet(manifest, row, original)
                require(not self.jobs._incident_path(self.jobs._submission_path(rid)).exists(),
                        'Research integrity incident')
                self.identity.verify_results(job)
                if job['status'] in operator.ACTIVE: self.own_active.add(rid)
            require(self.worker_state == 'idle' or bool(self.own_active), 'Worker must initially be idle')
            return {'verified': True, 'issues': [], 'saved_experiments': len(index['entries']),
                    'pending_same_program_intake': len(index['pending']), 'active_same_program': len(self.own_active)}

        def accepted_entry(self, manifest, row):
            rid = row['request_id']; journal = self.identity.journal(rid)
            if journal is None:
                # Original code detects all orphan journal/receipt/event evidence.
                return super().accepted_entry(manifest, row)
            require(journal.get('schema') == 'experiment_intake_v1' and journal['intent'] == row['intent'] and
                    journal['canonical_request_id'] == row.get('expected_existing_request_id', rid),
                    'Accepted journal differs from approved request')
            require(journal.get('requested_implementation') in
                    requested_implementations(approval),
                    'Accepted requested implementation is outside exact approval')
            canonical_id = journal['canonical_request_id']
            require(self.jobs._submission_path(canonical_id).is_file(),
                    'Incomplete accepted publication; explicit reconciliation required')
            original = self.jobs._submission(canonical_id); self._envelope(row, original)
            if canonical_id == rid:
                require(journal.get('submission') == original, 'Journal and canonical submission differ')
            else:
                require(journal.get('submission') is None or journal['submission'] == original,
                        'Historical alias submission differs')
            require(not self.jobs._incident_path(self.jobs._submission_path(canonical_id)).exists(),
                    'Accepted submission has an integrity incident')
            expected = self.validate_packet(manifest, row, original)
            require(expected == journal['scientific_identity'], 'Accepted scientific identity differs')
            job = self.jobs._read_job(canonical_id)
            require(job is not None and job['status'] in operator.ACTIVE | {'succeeded'},
                    'Accepted work requires explicit recovery')
            response = {'request_id': canonical_id, 'status': job['status'],
                        'intake_action': 'view_results' if job['status'] == 'succeeded' else 'view_existing'}
            authority = self.receipt_authority(row, response)
            response['submission_receipt'] = authority['receipt']
            return operator.verify_receipt(row, response, authority, expected)

        def receipt_authority(self, row, response):
            from runtime.experiment_identity import scientific_key
            journal = self.identity.journal(row['request_id'])
            require(journal is not None, 'Durable intake journal missing')
            rid = journal['canonical_request_id']; original = self.jobs._submission(rid)
            self._envelope(row, original)
            job = self.jobs._read_job(rid)
            require(job is not None and job['status'] not in operator.UNHEALTHY_RESULTS,
                    'Accepted work requires attention')
            self.identity.verify_results(job)
            require(scientific_key(original) == journal['scientific_identity'] and
                    original['intent'] == journal['intent'], 'Canonical research identity differs')
            receipt = {'request_id': journal['request_id'], 'canonical_request_id': rid,
                       'scientific_identity': journal['scientific_identity'], 'journal_sha256': journal['sha256']}
            return {'verified': True, 'receipt': receipt, 'intent': journal['intent'],
                    'result_references': job.get('results', [])}

    return ApprovedRuntimeBridge
