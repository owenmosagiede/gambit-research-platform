"""Read-only experiment views, independent of intake's research-writer lock.

Commands retain the runtime's recovery path. A page read only verifies published
envelopes, intake journals and one snapshot of append-only execution events. An
interrupted publication remains an explicit issue until the writer repairs it.
"""
from copy import deepcopy

from research.contracts import ResearchError, digest, request_id
from research.store import inside, read_json
from runtime.experiment_identity import IdentityIndex, checked
from runtime.research_jobs import ACTIVE


class ExperimentView:
    def __init__(self, jobs):
        self.jobs = jobs
        self.index = IdentityIndex(jobs)
        self.events = jobs._event_snapshot()
        self.worker = jobs.health()

    def get(self, rid):
        rid = request_id(rid)
        journal = self.index.journal(rid)
        canonical_id = journal['canonical_request_id'] if journal else rid
        original = self.jobs._submission(canonical_id)
        if journal:
            if (original['intent'] != journal['intent'] or
                    self.index.entry(original, self.events)['scientific_identity'] != journal['scientific_identity']):
                raise ResearchError('Intake journal differs from the canonical experiment')
        incident_path = self.jobs._incident_path(self.jobs._submission_path(canonical_id))
        if incident_path.exists():
            incident = read_json(incident_path)
            if incident['request_id'] != canonical_id:
                raise ResearchError('Incident identity differs from the experiment')
            return self.jobs._incident_job(incident), None
        job = self.jobs._read_job(canonical_id, self.events)
        if job is None:
            raise ResearchError('Submission publication is incomplete; no recorded event')
        if job['request_id'] != canonical_id:
            raise ResearchError('Execution event belongs to another experiment')
        value = self.jobs.public(job)
        value['runtime'] = deepcopy(self.worker)
        if journal:
            receipt = {key: journal[key] for key in ('request_id', 'canonical_request_id', 'scientific_identity')}
            receipt['journal_sha256'] = journal['sha256']
            path = self.index.base / 'receipts' / (rid + '.json')
            if path.exists():
                if checked(path) != dict(receipt, sha256=digest(receipt)):
                    raise ResearchError('Receipt differs from the authoritative intake journal')
                value['submission_receipt'] = receipt
            else:
                value['submission_receipt_pending'] = True
            value['intake_action'] = ('view_results' if job['status'] == 'succeeded' else
                                      'view_existing' if job['status'] in ACTIVE else 'recover_existing')
        return value, deepcopy(original['intent'])

    def list(self):
        paths = set()
        for relative in ('storage/catalog/submissions', 'storage/catalog/operations/jobs'):
            paths.update(p.stem for p in inside(self.jobs.root, relative).glob('*.json'))
        issues = []
        # Journal-only reservations are visible as pending/unverifiable evidence;
        # aliases are not additional experiments. Never publish envelopes here.
        for path in sorted((self.index.base / 'requests').glob('*.json')):
            try:
                journal = self.index.journal(path.stem)
                paths.add(journal['canonical_request_id'])
                if journal['request_id'] != journal['canonical_request_id']:
                    self.get(journal['request_id'])  # verify alias binding, not another queue item
            except Exception:
                issues.append({'request_id': path.stem, 'message': 'Intake record could not be verified.'})
        items = []
        for rid in sorted(paths):
            try:
                job, intent = self.get(rid)
                items.append({'job': job, 'intent': intent})
            except Exception:
                issues.append({'request_id': rid,
                               'message': 'Queue record is incomplete or could not be verified. No repair was attempted.'})
        items.sort(key=lambda item: (0 if item['job']['status'] in ACTIVE else 1,
                                    self.jobs.queue_key(item['job'])))
        waiting = 0
        for item in items:
            if item['job']['status'] == 'queued':
                waiting += 1
                item['queue_position'] = waiting
            else:
                item['queue_position'] = None
        return {'items': items, 'issues': issues, 'worker': deepcopy(self.worker),
                'execution': 'sequential', 'ordering': 'queued_at_then_request_id'}


def list_experiments(jobs):
    return ExperimentView(jobs).list()


def get_experiment(jobs, rid):
    return ExperimentView(jobs).get(rid)[0]
