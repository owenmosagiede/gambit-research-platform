"""Read-only experiment views, independent of intake's research-writer lock.

Commands retain the runtime's recovery path. A page read only verifies published
envelopes, intake journals and one snapshot of append-only execution events. An
interrupted publication remains an explicit issue until the writer repairs it.
"""
from copy import deepcopy
from functools import lru_cache

from api.catalog_cache import CatalogCache
from data.catalog_reads import reading
from research.contracts import ResearchError, digest, request_id
from research.store import inside, read_json
from runtime.experiment_identity import IdentityIndex, checked, scientific_key
from runtime.research_jobs import ACTIVE


@lru_cache(maxsize=4)
def _metadata_cache(root):
    # Compact verified metadata only; no frozen member plans or runtime state.
    # Each hit checks file inode/size/mtime/ctime, with full verification hourly.
    return CatalogCache(limit=1024)


class ExperimentView:
    def __init__(self, jobs):
        self.jobs = jobs
        self.index = IdentityIndex(jobs)
        self.events = jobs._event_snapshot()
        self.worker = jobs.health()
        self.cache = _metadata_cache(str(jobs.root.resolve()))
        self.originals = {}
        self.journals = {}
        self.scientific_keys = {}

    def _submission(self, rid):
        if rid not in self.originals:
            authority = self._journal(rid)
            binding = authority if authority and authority.get('submission') is not None else None
            def load():
                # Watch the unresolved address too: replacing a file or parent
                # symlink must invalidate the previously confined read.
                with reading(self.jobs.root / 'storage/catalog/submissions' / (rid + '.json')):
                    original = self.jobs._submission(rid)
                plan = original.get('frozen_plan')
                identity = None
                if binding:
                    if (original['intent'] != binding['intent'] or
                            original['record_sha256'] != binding['submission']['record_sha256']):
                        raise ResearchError('Journal and published submission differ')
                    # The journal verifier checked the complete embedded plan;
                    # equal verified envelope hashes bind its scientific key.
                    identity = binding['scientific_identity']
                elif plan:
                    identity = scientific_key(original)
                result = {key: original[key] for key in ('request_id', 'intent', 'record_sha256')}
                result['scientific_identity'] = identity
                if isinstance(plan, dict):
                    result['frozen_plan'] = {key: plan[key] for key in ('recipe', 'scope', 'mode') if key in plan}
                return result
            # A changed or newly published journal gets a different cache key;
            # its own dependency-verified read precedes this lookup.
            key = ('submission', rid, binding['sha256'] if binding else None)
            self.originals[rid] = self.cache.get_verified(key, self.jobs.root, load, max_age=3600)
        return self.originals[rid]

    def _journal(self, rid):
        if rid not in self.journals:
            # Absence is request-local only. A later publication must be seen by
            # the next page read without relying on a cached directory listing.
            if not self.index.journal_path(rid).exists():
                self.journals[rid] = None
            else:
                def load():
                    with reading(self.jobs.root / 'storage/catalog/operations/experiment_intake/requests' / (rid + '.json')):
                        journal = self.index.journal(rid)
                    if journal is None:
                        raise FileNotFoundError('Intake journal changed during reading')
                    result = {key: journal[key] for key in
                              ('request_id', 'canonical_request_id', 'intent', 'scientific_identity', 'sha256')}
                    submission = journal.get('submission')
                    result['submission'] = ({'record_sha256': submission['record_sha256']}
                                            if submission is not None else None)
                    return result
                self.journals[rid] = self.cache.get_verified(
                    ('journal', rid), self.jobs.root, load, max_age=3600)
        return self.journals[rid]

    def get(self, rid):
        rid = request_id(rid)
        journal = self._journal(rid)
        canonical_id = journal['canonical_request_id'] if journal else rid
        incident_path = self.jobs._incident_path(self.jobs._submission_path(canonical_id))
        if incident_path.exists():
            incident = read_json(incident_path)
            if incident['request_id'] != canonical_id:
                raise ResearchError('Incident identity differs from the experiment')
            return self.jobs._incident_job(incident), None
        original = self._submission(canonical_id)
        if journal:
            if original['intent'] != journal['intent']:
                raise ResearchError('Intake journal differs from the canonical experiment')
            if journal.get('submission') is not None:
                # journal() already verified this embedded envelope and its
                # scientific key. Equal verified hashes bind the same bytes.
                if journal['submission']['record_sha256'] != original['record_sha256']:
                    raise ResearchError('Journal and published submission differ')
                self.scientific_keys[canonical_id] = journal['scientific_identity']
            else:
                if canonical_id not in self.scientific_keys:
                    identity = original['scientific_identity']
                    if identity is None:
                        # Legacy envelopes can locate their plan through current
                        # event authority. Never persist that event-dependent key.
                        identity = self.index.entry(self.jobs._submission(canonical_id), self.events)['scientific_identity']
                    self.scientific_keys[canonical_id] = identity
                if self.scientific_keys[canonical_id] != journal['scientific_identity']:
                    raise ResearchError('Alias scientific identity differs from the experiment')
        # Use the runtime's chain verifier, with the envelope verified above.
        # Calling _read_job here would re-read/re-hash that same large envelope.
        events = self.jobs._events(canonical_id, self.events)
        if not events:
            raise ResearchError('Submission publication is incomplete; no recorded event')
        job = dict(events[-1]['job'], sequence=events[-1]['sequence'], event_sha256=digest(events[-1]))
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
                journal = self._journal(path.stem)
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
