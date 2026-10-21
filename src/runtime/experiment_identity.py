"""Shared metadata-only intake identity and rebuildable lookup.

Caller holds research-writer. Immutable intake journals/submissions/events are
truth; the index and request receipts are projections. No observations are read.
"""
from copy import deepcopy
from pathlib import Path
from research.contracts import digest, canonical, request_id, ResearchConflict, ResearchError
from research.store import inside, read_json, install_bytes

BASE = 'storage/catalog/operations/experiment_intake'
# Reviewed exact implementation pairs only. Entries belong in a reviewed release,
# not a mutable server setting. Unknown changes are deliberately not compatible.
def release_reviews():
    # Kept outside fingerprinted Python modules to avoid a self-referential hash.
    path = Path(__file__).with_name('research_compatibility.json')
    record = read_json(path)
    if record.get('schema') != 'research_release_reviews_v1' or not isinstance(record.get('reviews'), list):
        raise ResearchError('Invalid release compatibility registry')
    reviews = record['reviews']
    pairs = set()
    for review in reviews:
        pair = (review['from'], review['to'])
        if pair in pairs or any(len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in pair):
            raise ResearchError('Ambiguous release compatibility review')
        pairs.add(pair)
    return reviews


def release_relation(old, new):
    if old == new:
        return 'equivalent'
    a, b = digest(old), digest(new)
    for review in release_reviews():
        if (review['from'], review['to']) == (a, b):
            if review['decision'] not in ('equivalent', 'different') or not review.get('evidence') or not review.get('tests'):
                raise ResearchError('Incomplete implementation compatibility review')
            return review['decision']
    return 'unreviewed'


def scientific_key(packet):
    plan = deepcopy(packet['frozen_plan'])
    plan.pop('plan_id', None)
    # Prepared output inventory is a cache, never an input selection policy.
    for member in plan['members']:
        member.pop('feature_materializations', None)
    return digest({'intent': packet['intent'], 'research_spec': packet['research_spec'], 'plan': plan})


def freeze(jobs, intent, impl):
    from research import inputs, external_features, feature_applications
    from research.contracts import load_profile, profile_blockers, ResearchBlocked
    from data.fx_currency_migration import check_intake
    check_intake(jobs.root,intent)
    profile = load_profile(jobs.root)
    if jobs.adapter is None:
        _, capability = feature_applications.binding_for(jobs.root, intent['feature'])
        if capability['kind'] == feature_applications.SINGLE_SERIES:
            profile = external_features.load_profile(jobs.root)
        elif capability['kind'] == feature_applications.CURRENCY_QUOTE:
            from data.fx_currency_release import load_profile as currency_profile
            profile=currency_profile(jobs.root)
    blockers = profile_blockers(profile)
    if blockers:
        raise ResearchBlocked(blockers)
    plan = (jobs.adapter or inputs).resolve_plan(jobs.root, intent, profile)
    return {'intent': deepcopy(intent), 'research_spec': profile, 'implementation': impl,
            'frozen_plan': plan,
            **({'feature_application': plan['feature_application']} if 'feature_application' in plan else {})}


def checked(path):
    value = read_json(path)
    if value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'}):
        raise ResearchError('Intake evidence checksum mismatch: ' + path.name)
    return value


def save(path, value, *, mutable=False):
    value = {k: v for k, v in value.items() if k != 'sha256'}
    value['sha256'] = digest(value)
    install_bytes(path, canonical(value) + b'\n', mutable=mutable)
    return value


class IdentityIndex:
    def __init__(self, jobs):
        self.jobs, self.root = jobs, jobs.root
        self.base = inside(self.root, BASE)
        self.path = self.base / 'index.json'

    def journal_path(self, rid):
        return self.base / 'requests' / (request_id(rid) + '.json')

    def journal(self, rid):
        path = self.journal_path(rid)
        if not path.exists():
            return None
        record = checked(path)
        if record['request_id'] != rid:
            raise ResearchError('Intake request identity mismatch')
        request_id(record['canonical_request_id'])
        if record.get('submission') is not None:
            s = record['submission']
            if s['request_id'] != record['canonical_request_id'] or s['intent'] != record['intent'] or scientific_key(s) != record['scientific_identity']:
                raise ResearchError('Intake frozen identity mismatch')
            if s['record_sha256'] != digest({k: v for k, v in s.items() if k != 'record_sha256'}):
                raise ResearchError('Intake submission checksum mismatch')
        return record

    def receipt(self, journal):
        receipt = {k: journal[k] for k in ('request_id', 'canonical_request_id', 'scientific_identity')}
        receipt['journal_sha256'] = journal['sha256']
        path = self.base / 'receipts' / (journal['request_id'] + '.json')
        if path.exists():
            if checked(path) != dict(receipt, sha256=digest(receipt)):
                raise ResearchError('Submission receipt differs from authoritative journal')
        else:
            save(path, receipt)
        return receipt

    def signature(self):
        result = []
        for path in (inside(self.root, 'storage/catalog/submissions'), self.base / 'requests'):
            s = path.stat() if path.exists() else None
            result.append([s.st_ino, s.st_mtime_ns, s.st_ctime_ns] if s else None)
        return result

    def invalidate(self):
        if self.path.exists():
            self.path.unlink()

    def entry(self, original, snapshot=None):
        plan = original.get('frozen_plan')
        if plan is None:
            job = self.jobs._read_job(original['request_id'], snapshot)
            if job and job.get('plan'):
                plan = self.jobs.store.resolve('plan', job['plan'])['body']
        return {'request_id': original['request_id'], 'intent_key': digest(original['intent']),
                'scientific_identity': scientific_key(dict(original, frozen_plan=plan)) if plan else None,
                'implementation_key': digest(original['implementation']), 'record_sha256': original['record_sha256']}

    def rebuild(self, *, persist=True):
        entries, issues, journals = {}, [], []
        snapshot = self.jobs._event_snapshot()
        # A committed journal reserves the experiment even if envelope publication
        # was interrupted. It is recovered only through normal intake, not here.
        for p in sorted((self.base / 'requests').glob('*.json')):
            try:
                j = self.journal(p.stem)
                journals.append(j)
                if j.get('submission'):
                    entries[j['canonical_request_id']] = self.entry(j['submission'], snapshot)
            except Exception as exc:
                issues.append({'path': p.relative_to(self.root).as_posix(), 'error': str(exc)[:300]})
        for p in sorted(inside(self.root, 'storage/catalog/submissions').glob('*.json')):
            try:
                original = self.jobs._submission(p.stem)
                self.verify_results(self.jobs._read_job(p.stem, snapshot))
                item = self.entry(original, snapshot)
                if p.stem in entries and entries[p.stem] != item:
                    raise ResearchError('Journal and submission differ')
                entries[p.stem] = item
            except Exception as exc:
                issues.append({'path': p.relative_to(self.root).as_posix(), 'error': str(exc)[:300]})
        # Orphan projections must not disappear from the history audit.
        for p in inside(self.root, 'storage/catalog/operations/jobs').glob('*.json'):
            if p.stem not in entries:
                issues.append({'path': p.relative_to(self.root).as_posix(), 'error': 'Job lacks verified submission'})
        for j in journals:
            if j['canonical_request_id'] not in entries:
                issues.append({'path': str(self.journal_path(j['request_id'])), 'error': 'Receipt canonical experiment missing'})
        pending = [rid for rid in entries if not self.jobs._submission_path(rid).exists()]
        index = {'schema': 'experiment_identity_v1', 'entries': entries, 'issues': issues, 'pending': pending}
        if persist:
            self.publish(index)
        return index

    def publish(self, index):
        index['signature'] = self.signature()
        save(self.path, index, mutable=True)

    def load(self):
        try:
            index = checked(self.path)
            if index['schema'] == 'experiment_identity_v1' and index['signature'] == self.signature():
                return index
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return self.rebuild()

    def verify_results(self, job):
        if job:
            try:
                for reference in job.get('results', []):
                    link = self.jobs.store.resolve('link', reference)
                    for trial_ref in link['body']['trial_results']:
                        trial = self.jobs.store.resolve('trial', trial_ref)
                        for artifact in trial['body']['artifact_manifests']:
                            self.jobs.store.verify_artifact(artifact)
                    for kind, field in (('admission', 'admission_results'), ('validation', 'validation_results')):
                        for ref in link['body'].get(field, []):
                            self.jobs.store.resolve(kind, ref)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise ResearchConflict('Saved results require reconciliation: ' + str(exc)) from exc

    def matches(self, packet, index=None):
        index = self.load() if index is None else index
        if index['issues']:
            raise ResearchConflict('History requires reconciliation: ' + index['issues'][0]['error'])
        key, intent_key = scientific_key(packet), digest(packet['intent'])
        matches, ambiguous = [], []
        for rid, item in index['entries'].items():
            if item['intent_key'] != intent_key:
                continue
            if item['scientific_identity'] is None:
                ambiguous.append(rid)
                continue
            if item['scientific_identity'] != key:
                continue
            published = self.jobs._submission_path(rid).exists()
            if published:
                original = self.jobs._submission(rid)
            else:
                journal = self.journal(rid)
                if not journal or not journal.get('submission'):
                    raise ResearchConflict('Indexed experiment evidence missing; reconciliation required')
                original = journal['submission']
            if original['record_sha256'] != item['record_sha256'] or digest(original['implementation']) != item['implementation_key']:
                raise ResearchConflict('Indexed submission changed; reconciliation required')
            relation = release_relation(original['implementation'], packet['implementation'])
            if relation == 'different':
                continue
            if relation != 'equivalent':
                ambiguous.append(rid)
                continue
            if published:
                job = self.jobs._read_job(rid)
                self.verify_results(job)
            else:
                j = self.journal(rid)
                if not j or not j.get('submission'):
                    raise ResearchConflict('Indexed experiment evidence missing; reconciliation required')
                job = None
            matches.append((rid, job))
        # Multiple historical authorities must be reconciled explicitly, even if
        # one completed and the others failed. Never hide exposure history.
        if len(matches) > 1:
            ambiguous.extend(rid for rid, _ in matches)
        return matches, ambiguous
