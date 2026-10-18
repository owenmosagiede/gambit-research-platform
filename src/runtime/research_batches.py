"""Durable, explicitly approved batches around the ordinary research queue.

Preview resolves existing contracts only. Dispatch uses the same frozen submission
and execution path as Submit. No kernels, materializers, or additional workers here.
"""
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path
import shutil
import uuid

from research.contracts import (canonical, digest, normalize_submission, request_id,
    load_profile, profile_blockers, ResearchError, ResearchConflict, ResearchBlocked, HORIZONS)
from research.store import inside, install_bytes, read_json, lock
from runtime.research_jobs import implementation, now, ACTIVE

MAX_EXPERIMENTS = 5000
MAX_BODY = 262144
BASE = 'storage/catalog/operations/research_batches'


def checked(path):
    value = read_json(path)
    if value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'}):
        raise ResearchError('Batch evidence checksum mismatch: ' + path.name)
    return value


def save(path, value, *, mutable=False):
    value = {k: v for k, v in value.items() if k != 'sha256'}
    value['sha256'] = digest(value)
    install_bytes(path, canonical(value) + b'\n', mutable=mutable)
    return value


def semantic_key(packet):
    """Existing output windows are reusable caches, not a different hypothesis."""
    plan = deepcopy(packet['frozen_plan'])
    plan.pop('plan_id', None)
    for member in plan['members']:
        member.pop('feature_materializations', None)
    return digest({'intent': packet['intent'], 'research_spec': packet['research_spec'],
                   'implementation': packet['implementation'], 'plan': plan})


def weekdays(period):
    a, b = (date.fromisoformat(period[k]) for k in ('start_inclusive', 'end_exclusive'))
    n = (b - a).days
    return n // 7 * 5 + sum((a.weekday() + i) % 7 < 5 for i in range(n % 7))


class ResearchBatches:
    def __init__(self, jobs):
        self.jobs, self.root = jobs, jobs.root
        self.base = inside(self.root, BASE)

    def directory(self, bid):
        return self.base / request_id(bid)

    def create(self, value):
        required = {'batch_id', 'name', 'features', 'scopes', 'target_family', 'expected_direction', 'duplicate_policy'}
        if type(value) is not dict or set(value) - (required | {'estimate_basis'}) or not required <= set(value):
            raise ResearchError('Batch requires exact Features, Scopes, Target, Direction and duplicate policy')
        bid = request_id(value['batch_id'])
        if type(value['name']) is not str or not 1 <= len(value['name']) <= 120:
            raise ResearchError('Batch name must contain 1–120 characters')
        if value['duplicate_policy'] not in ('reuse_exact', 'reject'):
            raise ResearchError('Use reuse_exact or reject')
        fs, ss = value['features'], value['scopes']
        if (type(fs) is not list or type(ss) is not list or not fs or not ss
                or len(fs) * len(ss) > MAX_EXPERIMENTS):
            raise ResearchError('Batch must contain 1–5000 Feature × Scope combinations')
        intents = {}; requested = len(fs) * len(ss)
        for f in fs:
            for s in ss:
                intent = normalize_submission({'request_id': bid, 'feature': f, 'scope': s,
                    'target_family': value['target_family'], 'expected_direction': value['expected_direction']})
                intent.pop('request_id'); intents.setdefault(digest(intent), intent)
        basis = value.get('estimate_basis')
        if basis is not None:
            if type(basis) is not dict or set(basis) != {'description', 'seconds_per_experiment', 'bytes_per_experiment'}:
                raise ResearchError('Estimates need a description and seconds/bytes ranges per five-horizon experiment')
            if type(basis['description']) is not str or not 1 <= len(basis['description']) <= 500:
                raise ResearchError('Explain the estimate basis')
            for k in ('seconds_per_experiment', 'bytes_per_experiment'):
                v = basis[k]
                if type(v) is not list or len(v) != 2 or any(type(n) is not int or not 0 <= n <= 10**15 for n in v) or v[1] < v[0]:
                    raise ResearchError('Estimate bounds must be ordered nonnegative integers')
        d = self.directory(bid)
        with lock(self.root, 'batch-writer'):
            if (d / 'manifest.json').exists():
                original = checked(d / 'manifest.json')
                if original['request'] != value: raise ResearchConflict('Batch ID already belongs to another manifest')
            else:
                save(d / 'manifest.json', {'schema': 'research_batch_v1', 'batch_id': bid, 'request': value,
                    'created_at': now(), 'implementation': implementation(), 'intents': list(intents.values()),
                    'requested_combinations': requested, 'input_duplicates': requested - len(intents)})
        self.jobs.wake.set()
        return self.status(bid)

    def _state(self, d, state, **kwargs):
        return save(d / 'state.json', {'state': state, 'updated_at': now(), **kwargs}, mutable=True)

    def _packet(self, intent, impl):
        from research import inputs, external_features, feature_applications
        profile = load_profile(self.root)
        if self.jobs.adapter is None:
            _, contract = feature_applications.binding_for(self.root, intent['feature'])
            if contract['kind'] == feature_applications.SINGLE_SERIES:
                profile = external_features.load_profile(self.root)
        blockers = profile_blockers(profile)
        if blockers: raise ResearchBlocked(blockers)
        adapter = self.jobs.adapter or inputs
        plan = adapter.resolve_plan(self.root, intent, profile)
        return {'intent': intent, 'research_spec': profile, 'implementation': impl, 'frozen_plan': plan,
                **({'feature_application': plan['feature_application']} if 'feature_application' in plan else {})}

    def _duplicates(self, packet):
        matches = []; ambiguous = []
        snapshot = self.jobs._event_snapshot()
        for p in sorted(inside(self.root, 'storage/catalog/submissions').glob('*.json')):
            # Corruption must be explicit; never turn unverifiable history into a fresh run.
            original = self.jobs._submission(p.stem)
            if original['intent'] != packet['intent']: continue
            if original['research_spec'] != packet['research_spec'] or original['implementation'] != packet['implementation']: continue
            job = self.jobs._read_job(p.stem, snapshot)
            plan = original.get('frozen_plan')
            if plan is None and job and job.get('plan'):
                plan = self.jobs.store.resolve('plan', job['plan'])['body']
            if plan is None:
                ambiguous.append(p.stem); continue
            if semantic_key(dict(original, frozen_plan=plan)) == semantic_key(packet):
                matches.append((p.stem, job))
        return matches, ambiguous

    def _preview_row(self, d, manifest, index):
        intent = manifest['intents'][index]
        row = {'index': index, 'intent': intent, 'request_id': str(uuid.uuid5(uuid.UUID(manifest['batch_id']), digest(intent))),
               'checked_at': now()}
        try:
            packet = self._packet(intent, manifest['implementation'])
            packet_hash = digest(packet)
            save(d / 'packets' / (packet_hash + '.json'), packet)
            row.update(packet_sha256=packet_hash, disposition='new', mode=packet['frozen_plan']['mode'],
                research_spec={k: packet['research_spec'][k] for k in ('id', 'version')},
                research_spec_sha256=digest(packet['research_spec']), periods=packet['frozen_plan']['periods'],
                scope_members=[m['instrument_id'] for m in packet['frozen_plan']['members']],
                members=len(packet['frozen_plan']['members']), scheduled_member_rows={phase:
                weekdays(period) * len(packet['frozen_plan']['members']) for phase, period in packet['frozen_plan']['periods'].items()})
            with lock(self.root, 'research-writer'):
                matches, ambiguous = self._duplicates(packet)
            if ambiguous:
                raise ResearchBlocked([{'code': 'DUPLICATE_UNRESOLVED', 'message': 'Matching submissions have not resolved their exact inputs: ' + ', '.join(ambiguous)}])
            reusable = [(rid, j) for rid, j in matches if j and j['status'] in ACTIVE | {'succeeded'}]
            if reusable and manifest['request']['duplicate_policy'] == 'reuse_exact':
                rid, j = sorted(reusable, key=lambda x: (x[1]['status'] != 'succeeded', x[0]))[0]
                row.update(disposition='reuse', existing_request_id=rid, existing_status=j['status'])
            elif matches:
                raise ResearchBlocked([{'code': 'DUPLICATE_REQUIRES_REVIEW', 'message': 'Exact matching history exists; inspect it instead of automatically rerunning: ' + ', '.join(r for r, _ in matches)}])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            row.update(disposition='blocked', blockers=getattr(exc, 'blockers', [{'code': 'PREVIEW_BLOCKED', 'message': str(exc)[:800]}]))
        save(d / 'rows' / (str(index) + '.json'), row)

    def _rows(self, d):
        return sorted((checked(p) for p in (d / 'rows').glob('*.json')), key=lambda r: r['index'])

    def _preview(self, d, manifest):
        rows = self._rows(d); counts = dict(Counter(r['disposition'] for r in rows))
        new = counts.get('new', 0); basis = manifest['request'].get('estimate_basis')
        estimates = {'new_submissions': new, 'p1_horizon_evaluations': new * 5,
            'p2_horizon_evaluations_upper_bound': new * 5,
            'scheduled_member_rows_upper_bound': {phase: sum(r.get('scheduled_member_rows', {}).get(phase, 0)
                for r in rows if r['disposition'] == 'new') for phase in ('P1', 'P2')},
            'sequential_seconds_range': [new * n for n in basis['seconds_per_experiment']] if basis else None,
            'additional_bytes_range': [new * n for n in basis['bytes_per_experiment']] if basis else None,
            'basis': basis, 'execution': 'existing sequential worker',
            'limitations': ['Scheduled rows are workload bounds, not usable samples or independent observations.',
                'P2 depends on P1 admission. Reuse and coverage can reduce work.',
                'Time/storage are unknown unless an explicit calibration is supplied; estimates are not reservations.',
                'No extra workers or cloud capacity are provisioned.']}
        return {'batch_id': manifest['batch_id'], 'manifest_sha256': manifest['sha256'],
                'rows': [r['sha256'] for r in rows], 'counts': counts, 'estimates': estimates}

    def approve(self, bid, value):
        if type(value) is not dict or set(value) != {'preview_sha256', 'exclude_blocked'} or type(value['exclude_blocked']) is not bool:
            raise ResearchError('Approval requires the reviewed preview hash and explicit exclude_blocked choice')
        d = self.directory(bid)
        with lock(self.root, 'batch-writer'):
            m = checked(d / 'manifest.json'); preview = self._preview(d, m)
            if len(preview['rows']) != len(m['intents']) or digest(preview) != value['preview_sha256']:
                raise ResearchConflict('Preview is incomplete or differs from the approved preview')
            if preview['counts'].get('blocked') and not value['exclude_blocked']:
                raise ResearchConflict('Blocked items require explicit exclusion or a new corrected batch')
            if implementation() != m['implementation']: raise ResearchConflict('Implementation changed; create a new preview')
            approval = d / 'approval.json'
            if approval.exists():
                if checked(approval)['approval'] != value: raise ResearchConflict('Approval is immutable')
            else:
                save(approval, {'approval': value, 'approved_at': now(), 'manifest_sha256': m['sha256']})
                self._state(d, 'approved')
        self.jobs.wake.set()
        return self.status(bid)

    def control(self, bid, action):
        d = self.directory(bid)
        with lock(self.root, 'batch-writer'):
            m = checked(d / 'manifest.json')
            if action not in ('pause', 'resume'): raise ResearchError('Unknown batch action')
            if action == 'resume' and implementation() != m['implementation']:
                raise ResearchConflict('Implementation changed; preserve this batch and create a new preview')
            self._state(d, 'paused' if action == 'pause' else ('approved' if (d / 'approval.json').exists() else 'previewing'))
        self.jobs.wake.set()
        return self.status(bid)

    def advance(self):
        """One bounded intake step under the existing executor, after queued research.

        Crash after Submit but before the receipt is safe: the deterministic ID
        recovers the same durable submission, never a replacement experiment.
        """
        with lock(self.root, 'batch-writer', nonblocking=True) as claimed:
            if not claimed: return
            for path in sorted(self.base.glob('*/manifest.json'), key=lambda p: p.stat().st_mtime_ns):
                d = path.parent
                try:
                    m = checked(path)
                    state = checked(d / 'state.json')['state'] if (d / 'state.json').exists() else 'previewing'
                    if state in ('paused', 'completed', 'needs_attention'): continue
                    # Approval is authority; a crash can leave its state projection
                    # at ready after the immutable approval was already committed.
                    if state == 'ready' and not (d / 'approval.json').exists(): continue
                    if implementation() != m['implementation']: raise ResearchConflict('Implementation changed; create a new preview')
                    rows = self._rows(d)
                    if len(rows) < len(m['intents']):
                        self._preview_row(d, m, len(rows))
                        self._state(d, 'previewing', previewed=len(rows) + 1)
                        if len(rows) + 1 == len(m['intents']): self._state(d, 'ready')
                        return
                    if not (d / 'approval.json').exists(): self._state(d, 'ready'); continue
                    approval = checked(d / 'approval.json')
                    if approval['manifest_sha256'] != m['sha256'] or approval['approval']['preview_sha256'] != digest(self._preview(d, m)):
                        raise ResearchConflict('Approved preview changed')
                    for row in rows:
                        receipt_path = d / 'dispatch' / (str(row['index']) + '.json')
                        if receipt_path.exists(): continue
                        if row['disposition'] == 'blocked':
                            if not approval['approval']['exclude_blocked']: raise ResearchConflict('Blocked item was not excluded')
                            save(receipt_path, {'index': row['index'], 'state': 'excluded', 'at': now()}); return
                        packet = checked(d / 'packets' / (row['packet_sha256'] + '.json'))
                        packet.pop('sha256')
                        if digest(packet) != row['packet_sha256']: raise ResearchError('Packet identity differs')
                        # Shared intake holds the ordinary writer lock across dedup and publication.
                        job, created = self.jobs.submit(dict(row['intent'], request_id=row['request_id']),
                            _batch_packet=packet, _batch_duplicate_policy=m['request']['duplicate_policy'],
                            _batch_reuse_id=row.get('existing_request_id'))
                        save(receipt_path, {'index': row['index'], 'state': 'submitted' if created else 'linked',
                            'request_id': job['request_id'], 'at': now()})
                        self._state(d, 'dispatching'); return
                    states = []
                    with lock(self.root, 'research-writer'):
                        snapshot = self.jobs._event_snapshot()
                    for p in (d / 'dispatch').glob('*.json'):
                        r = checked(p)
                        if r.get('request_id'): states.append(self.jobs.get(r['request_id'], _snapshot=snapshot)['status'])
                    if any(s in ACTIVE for s in states): return
                    self._state(d, 'needs_attention' if any(s != 'succeeded' for s in states) else 'completed')
                except Exception as exc:
                    self._state(d, 'needs_attention', error=type(exc).__name__ + ': ' + str(exc)[:800])
                return

    def status(self, bid):
        d = self.directory(bid); m = checked(d / 'manifest.json'); rows = self._rows(d)
        state = checked(d / 'state.json') if (d / 'state.json').exists() else {'state': 'previewing'}
        preview = self._preview(d, m); dispatch = {r['index']: r for r in (checked(p) for p in (d / 'dispatch').glob('*.json'))}
        counts = Counter(); items = []
        with lock(self.root, 'research-writer'):
            snapshot = self.jobs._event_snapshot() if any(r.get('request_id') for r in dispatch.values()) else {}
        for row in rows:
            r = dispatch.get(row['index']); item = {k: v for k, v in row.items() if k not in ('sha256', 'packet_sha256')}
            if r:
                item['dispatch'] = r
                if r.get('request_id'):
                    job = self.jobs.get(r['request_id'], _snapshot=snapshot)
                    item['job'] = {k: job.get(k) for k in ('request_id', 'status', 'stage', 'progress', 'horizons', 'updated_at', 'preparation_progress', 'message')}
                    counts[job['status']] += 1
                else: counts['excluded'] += 1
            items.append(item)
        free = shutil.disk_usage(self.root).free
        return {'batch_id': bid, 'name': m['request']['name'], 'state': state,
            'created_at': m['created_at'], 'requested_combinations': m['requested_combinations'],
            'unique_experiments': len(m['intents']), 'input_duplicates': m['input_duplicates'],
            'previewed': len(rows), 'preview_complete': len(rows) == len(m['intents']),
            'preview_sha256': digest(preview), 'preview_counts': preview['counts'], 'estimates': preview['estimates'],
            'free_bytes_on_workspace_filesystem': free, 'job_counts': dict(counts), 'items': items,
            'implementation_fingerprint': m['implementation']['fingerprint'],
            'approved': (d / 'approval.json').exists(), 'research_results': 'Each job retains its own Scope, Target, direction and horizon outcomes.'}
