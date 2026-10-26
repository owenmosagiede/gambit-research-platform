"""Synthetic archived batch files, built without the retired batch scheduler."""
from collections import Counter
from datetime import date
import shutil
import uuid
from unittest.mock import patch

from data.legacy_batch_evidence import BASE, checked, preview, rows
from research.contracts import canonical, digest, normalize_submission, request_id
from research.store import install_bytes
from runtime.experiment_identity import freeze
from runtime.research_jobs import implementation, now


def save(path, value, *, mutable=False):
    value = {key: value for key, value in value.items() if key != 'sha256'}
    value['sha256'] = digest(value)
    install_bytes(path, canonical(value) + b'\n', mutable=mutable)
    return value


def weekdays(period):
    start, end = (date.fromisoformat(period[key]) for key in ('start_inclusive', 'end_exclusive'))
    count = (end - start).days
    return count // 7 * 5 + sum((start.weekday() + i) % 7 < 5 for i in range(count % 7))


class ArchivedBatchFixture:
    def __init__(self, jobs):
        self.jobs, self.root = jobs, jobs.root

    def directory(self, bid):
        return self.root / BASE / request_id(bid)

    def install_completed(self, request):
        bid = request['batch_id']; directory = self.directory(bid); intents = {}
        for feature in request['features']:
            for scope in request['scopes']:
                intent = normalize_submission(dict(request_id=bid, feature=feature, scope=scope,
                    target_family=request['target_family'], expected_direction=request['expected_direction']))
                intent.pop('request_id'); intents.setdefault(digest(intent), intent)
        count = len(request['features']) * len(request['scopes'])
        manifest = save(directory / 'manifest.json', {'schema': 'research_batch_v1', 'batch_id': bid,
            'request': request, 'created_at': now(), 'implementation': implementation(),
            'intents': list(intents.values()), 'requested_combinations': count, 'input_duplicates': count-len(intents)})
        for index, intent in enumerate(manifest['intents']):
            rid = str(uuid.uuid5(uuid.UUID(bid), digest(intent)))
            packet = freeze(self.jobs, intent, manifest['implementation']); plan = packet['frozen_plan']
            packet_sha = digest(packet); save(directory / 'packets' / (packet_sha + '.json'), packet)
            save(directory / 'rows' / f'{index}.json', {'index': index, 'intent': intent, 'request_id': rid,
                'checked_at': now(), 'packet_sha256': packet_sha, 'disposition': 'new', 'mode': plan['mode'],
                'research_spec': {key: packet['research_spec'][key] for key in ('id', 'version')},
                'research_spec_sha256': digest(packet['research_spec']), 'periods': plan['periods'],
                'scope_members': [member['instrument_id'] for member in plan['members']], 'members': len(plan['members']),
                'scheduled_member_rows': {phase: weekdays(period)*len(plan['members']) for phase, period in plan['periods'].items()}})
            # Ordinary jobs produce real synthetic authority; the archived batch
            # files merely describe their provenance and never dispatch work.
            self.jobs.submit(dict(intent, request_id=rid))
            # These archived batches predate per-attempt profiling. Retain normal
            # queue selection, executor locks and research execution, without
            # inventing new request-linked diagnostics in historical fixtures.
            # Current worker profiling is exercised by its own runtime tests.
            with patch.object(self.jobs, '_run', self.jobs._execute):
                self.jobs.run_pending_once()
            if self.jobs._read_job(rid)['status'] != 'succeeded':
                raise AssertionError('Synthetic direct research did not complete')
            save(directory / 'dispatch' / f'{index}.json', {'index': index, 'state': 'submitted', 'request_id': rid, 'at': now()})
        save(directory / 'approval.json', {'approval': {'preview_sha256': digest(preview(directory, manifest)),
            'exclude_blocked': False}, 'approved_at': now(), 'manifest_sha256': manifest['sha256']})
        save(directory / 'state.json', {'state': 'completed', 'updated_at': now()})

    def _rows(self, directory):
        return rows(directory)

    def status(self, bid):
        directory = self.directory(bid); manifest = checked(directory / 'manifest.json'); records = rows(directory)
        frozen = preview(directory, manifest); counts = Counter(); items = []
        for row in records:
            dispatch = checked(directory / 'dispatch' / f"{row['index']}.json")
            job = self.jobs._read_job(dispatch['request_id'])
            item = {key: value for key, value in row.items() if key not in ('sha256', 'packet_sha256')}
            item.update(dispatch=dispatch, job={key: job.get(key) for key in ('request_id', 'status', 'stage',
                'progress', 'horizons', 'updated_at', 'preparation_progress', 'message')})
            counts[job['status']] += 1; items.append(item)
        historical = manifest['schema'] == 'research_batch_retained_ts_v1'
        return {'batch_id': bid, 'name': manifest['request']['name'], 'state': checked(directory / 'state.json'),
            'created_at': manifest['created_at'], 'requested_combinations': manifest['requested_combinations'],
            'unique_experiments': len(manifest['intents']), 'input_duplicates': manifest['input_duplicates'],
            'previewed': len(records), 'preview_complete': len(records)==len(manifest['intents']),
            'preview_sha256': digest(frozen), 'preview_counts': frozen['counts'], 'estimates': frozen['estimates'],
            'free_bytes_on_workspace_filesystem': shutil.disk_usage(self.root).free, 'job_counts': dict(counts), 'items': items,
            'implementation_fingerprint': manifest['implementation']['fingerprint'], 'approved': not historical,
            'read_only': historical, 'reconciliation': manifest.get('reconciliation'),
            'research_results': 'Each job retains its own Scope, Target, direction and horizon outcomes.'}
