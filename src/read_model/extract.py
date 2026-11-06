"""Incremental, metadata-only extraction using the existing authority validators.

No discovery/evaluation kernel, payload verifier, repair path, or scientific lock
is used. Units retain transitive file dependencies; unchanged units are reused
only after checking those dependencies against the captured source inventory.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import time

from api.experiment_views import ExperimentView, _metadata_cache
from api.experiment_labels import with_experiment_labels
from api.signal_summaries import _verified_branch, _registered_entry
from data.catalog_reads import catalog_reads
from data.feature_store import FeatureStore
from research.contracts import digest, ref, request_id
from research.store import ResearchStore, read_json
from runtime.experiment_identity import IdentityIndex
from runtime.research_jobs import ResearchJobs
from read_model.storage import encoded, signature, IntegrityFailure

MAX_FILES = 200000
MAX_RECORD_BYTES = 64 * 1024 * 1024
REVERIFY_SECONDS = 3600


def compact(value):
    result = encoded(value)
    if len(result.encode()) > 256 * 1024:
        raise ValueError('Display row exceeds its metadata bound')
    return result


class ReadJobs(ResearchJobs):
    def __init__(self, root):
        super().__init__(root, start_worker=False)
        self.snapshot = {}

    def _event_snapshot(self):
        return self.snapshot

    def health(self):
        # Historical observation only: do not acquire the service lock or claim
        # a live process based on an old heartbeat. The UI labels this explicitly.
        return {'healthy': False, 'state': 'not_live_checked', 'worker_alive': None,
                'supervisor_alive': None, 'execution_process': 'separate'}

    def public(self, job):
        # Projection is not a command; do not call recovery/compatibility checks.
        return {k: deepcopy(v) for k, v in job.items() if k != 'cancel_requested'}


class Extractor:
    def __init__(self, root, db, *, now=None, deadline=None):
        self.root = Path(root).resolve(); self.db = db
        self.now = time.time() if now is None else now
        self.deadline = deadline or time.monotonic() + 600
        self.seen = {}; self.used = set(); self.live_units = set(); self.issues = []
        self.rebuilt = Counter(); self.reused = Counter()
        self.jobs = ReadJobs(self.root)
        # Each extraction must record its own dependencies, not inherit a cache
        # whose verification happened outside this generation's capture.
        _metadata_cache.cache_clear()

    def budget(self):
        if len(self.seen) > MAX_FILES or time.monotonic() > self.deadline:
            raise TimeoutError('Metadata projection budget exhausted')

    def path(self, relative):
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root) or path.resolve() != path.absolute():
            raise IntegrityFailure('Source path or parent is a symlink')
        if relative.startswith(('storage/payloads/', 'storage/catalog/lineage/', 'storage/catalog/trial_artifacts/')):
            raise IntegrityFailure('Numerical payload or lineage traversal is outside metadata projection')
        return path

    def source(self, relative):
        self.budget()
        if relative in self.seen: return self.seen[relative]
        path = self.path(relative)
        old = self.db.execute('SELECT * FROM sources WHERE path=?', (relative,)).fetchone()
        try: sig = signature(path)
        except FileNotFoundError:
            if old: raise IntegrityFailure('Previously verified immutable source disappeared: ' + relative)
            self.seen[relative] = None
            return None
        if sig[2] > MAX_RECORD_BYTES: raise IntegrityFailure('Metadata record exceeds the configured bound')
        if old and json.loads(old['signature']) == sig and self.now - old['checked'] < REVERIFY_SECONDS:
            value = {'signature': sig, 'sha256': old['sha256']}
        else:
            raw = path.read_bytes()
            if signature(path) != sig: raise IntegrityFailure('Source changed during verification')
            sha = hashlib.sha256(raw).hexdigest()
            if old and old['sha256'] != sha:
                raise IntegrityFailure('Previously verified immutable source changed: ' + relative)
            value = {'signature': sig, 'sha256': sha}
            self.db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?)', (relative, encoded(sig), sha, self.now))
        self.seen[relative] = value
        return value

    def files(self, pattern):
        paths = sorted(self.root.glob(pattern))
        if len(paths) > MAX_FILES: raise IntegrityFailure('Metadata discovery bound exceeded')
        return [p.relative_to(self.root).as_posix() for p in paths if p.is_file() or p.is_symlink()]

    def unit(self, kind, identity, explicit, loader):
        self.live_units.add((kind, identity))
        old = self.db.execute('SELECT * FROM units WHERE kind=? AND id=?', (kind, identity)).fetchone()
        dependencies = {p: self.source(p) for p in explicit}
        if old:
            previous = json.loads(old['dependencies'])
            dependencies.update({p: self.source(p) for p in previous if p not in dependencies})
            if dependencies == previous:
                self.reused[kind] += 1
                return json.loads(old['value'])
        with catalog_reads(self.root) as capture:
            value = loader()
            if not capture.unchanged(): raise IntegrityFailure('Metadata changed while extracting a unit')
            for path in capture.files:
                relative = path.relative_to(self.root).as_posix()
                dependencies[relative] = self.source(relative)
                if dependencies[relative] is None: raise IntegrityFailure('Read source disappeared')
            # Readers used here must not discover broad, uncaptured collections.
            # Event discovery and aliases are explicitly captured outside loaders.
            if capture.listings: raise IntegrityFailure('Unexpected uncaptured catalog scan')
        self.db.execute('INSERT OR REPLACE INTO units VALUES(?,?,?,?)',
                        (kind, identity, encoded(dependencies), encoded(value)))
        self.rebuilt[kind] += 1
        return value

    def issue(self, kind, identity):
        self.issues.append({'code': 'UNAVAILABLE_' + kind.upper(), 'record_id': identity,
                            'message': 'Stored metadata is incomplete or could not be verified; no repair was attempted.'})
        # A failed unit must never be resurrected from its previously verified cache.
        self.db.execute('DELETE FROM units WHERE kind=? AND id=?', (kind, identity))

    def try_unit(self, kind, identity, paths, loader):
        try: return self.unit(kind, identity, paths, loader)
        except IntegrityFailure: raise
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            self.issue(kind, identity)
            return None

    def experiment(self, rid):
        view = ExperimentView(self.jobs)
        job, intent = view.get(rid)
        item = with_experiment_labels(self.root, view, {'items': [{'job': job, 'intent': intent}]})['items'][0]
        if not job.get('operational_failure'):
            original = self.jobs._submission(job['request_id'])
            # These are immutable references, not rewritten execution bindings.
            item['provenance'] = {k: original[k] for k in ('record_sha256', 'scientific_identity',
                'implementation', 'execution_compatibility', 'feature_application', 'research_spec') if k in original}
            plan = original.get('frozen_plan', {})
            item['provenance']['frozen_plan_id'] = plan.get('plan_id')
            item['provenance']['frozen_scope'] = plan.get('scope')
            item['provenance']['frozen_recipe'] = plan.get('recipe')
        compact(item)
        return item

    def branch(self, path):
        store = ResearchStore(self.root); link = store.get('link', Path(path).stem)
        if link['scientific_key'] != link['body']: raise ValueError('Link identity differs')
        relation, trials, admissions, validations = _verified_branch(store, link)
        body = relation['body']; recipe_id = body['recipe']['id']
        row = {'signal_id': 'SIGNAL_' + recipe_id.removeprefix('FEATURE_RECIPE_').removeprefix('FEATURE_'),
            'projection': ref(link), 'relationship': ref(relation), 'attempt_ids': [], 'recipe': body['recipe'],
            **{k: link['body'][k] for k in ('trial_results', 'admission_results', 'validation_results')},
            **{k: body[k] for k in ('scope', 'mode', 'horizon', 'target_family', 'expected_direction')},
            'p1_status': admissions[0]['body']['decision'],
            'p2_status': validations[0]['body']['decision'] if validations else 'not_run'}
        stages = {t['body']['stage']: t for t in trials}; p1 = stages['P1']; p2 = stages.get('P2')
        row['research_stage_pass'] = False
        if row['p2_status'] == 'VALIDATED':
            try:
                effect = Decimal(str(p1['body']['metrics']['primary_effect']))
                orientation = {'POSITIVE': 1, 'NEGATIVE': -1}[body['expected_direction'].upper()]
                valid = (row['p1_status'] == 'admitted' and effect.is_finite() and effect * orientation > 0
                    and p1['body']['execution_status'] == 'completed' and p2 is not None
                    and p2['body']['execution_status'] == 'completed' and p2['body']['decision'] == 'VALIDATED'
                    and p2['body']['sample']['validation_data_accessed'] is True)
            except (KeyError, InvalidOperation): valid = False
            if not valid: raise ValueError('Validated branch lacks authoritative evaluation evidence')
            row['research_stage_pass'] = True
        row['p2_evaluation_ran'] = p2 is not None and p2['body'].get('execution_status') == 'completed'
        row['p2_reason_codes'] = validations[0]['body'].get('reason_codes', []) if validations else []
        compact(row)
        return {'row': row, 'relationship': relation, 'trials': trials, 'decisions': admissions + validations}

    def run(self):
        # Recheck every previously observed source, including deletions and
        # same-mtime replacements; immutable evidence never silently changes.
        for row in self.db.execute('SELECT path FROM sources').fetchall(): self.source(row['path'])
        event_paths = defaultdict(list)
        for path in self.files('storage/catalog/attempts/*/events/RESEVENT_*.json'):
            event = self.try_unit('event', path, [path], lambda p=path: read_json(self.path(p)))
            if event is None:
                self.jobs.snapshot.setdefault(None, []).append(path)
                continue
            try:
                rid = request_id(event['request_id'])
                if Path(path).stem != 'RESEVENT_' + digest(event): raise ValueError('Event hash differs')
                self.jobs.snapshot.setdefault(rid, []).append((Path(path).stem, event))
                event_paths[rid].append(path)
            except (KeyError, ValueError):
                self.jobs.snapshot.setdefault(None, []).append(path)
        index = IdentityIndex(self.jobs)
        requests = {Path(p).stem for p in self.files('storage/catalog/submissions/*.json')}
        aliases = []
        for path in self.files('storage/catalog/operations/experiment_intake/requests/*.json'):
            rid = Path(path).stem
            journal = self.try_unit('journal', rid, [path], lambda r=rid: {k:v for k,v in index.journal(r).items() if k in ('request_id','canonical_request_id','scientific_identity','sha256')})
            if journal:
                requests.add(journal['canonical_request_id']); aliases.append(journal)
        # The journal loader verifies the full envelope; only a compact value is
        # retained in aliases below. Unit journal data is compacted by its loader.
        for table in ('branches', 'recipes', 'experiments', 'aliases', 'trials', 'decisions', 'relationships', 'issues'):
            self.db.execute('DELETE FROM ' + table)
        for rid in sorted(requests):
            paths = event_paths[rid] + self.jobs.snapshot.get(None, []) + [f'storage/catalog/submissions/{rid}.json',
                f'storage/catalog/operations/experiment_intake/requests/{rid}.json',
                f'storage/catalog/operations/experiment_intake/receipts/{rid}.json',
                str(self.jobs._incident_path(self.jobs._submission_path(rid)).relative_to(self.root))]
            item = self.try_unit('experiment', rid, paths, lambda r=rid: self.experiment(r))
            if not item: continue
            job = item['job']; intent = item.get('intent') or {}
            self.db.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?)',
                (rid, job['status'], self.jobs.queue_key(job)[1], job['updated_at'],
                 intent.get('feature', {}).get('id'), intent.get('scope', {}).get('id'),
                 intent.get('expected_direction'), encoded([rid, intent, item.get('presentation')]).casefold(), encoded(item)))
        for journal in aliases:
            rid = journal['request_id']; canonical_id = journal['canonical_request_id']
            if rid != canonical_id:
                paths = event_paths[canonical_id] + self.jobs.snapshot.get(None, []) + [f'storage/catalog/operations/experiment_intake/requests/{rid}.json',
                    f'storage/catalog/operations/experiment_intake/receipts/{rid}.json',
                    f'storage/catalog/submissions/{canonical_id}.json',
                    f'storage/catalog/operations/experiment_intake/requests/{canonical_id}.json',
                    f'storage/catalog/operations/experiment_intake/receipts/{canonical_id}.json']
                checked = self.try_unit('alias', rid, paths, lambda r=rid: ExperimentView(self.jobs).get(r)[0]['submission_receipt'])
                if checked: self.db.execute('INSERT INTO aliases VALUES(?,?,?)', (rid, canonical_id, encoded(checked)))
        # Preserve metadata for completed/partial records even before their link
        # is published. Only verified complete branches contribute library cards.
        from research.store import FOLDERS, PREFIX
        store = ResearchStore(self.root)
        for kind, table in (('trial','trials'), ('admission','decisions'), ('validation','decisions')):
            for path in self.files('storage/catalog/' + FOLDERS[kind] + '/' + PREFIX[kind] + '_*.json'):
                identifier = Path(path).stem
                record = self.try_unit(kind, identifier, [path], lambda k=kind,i=identifier: store.get(k,i))
                if record: self.db.execute('INSERT OR IGNORE INTO ' + table + ' VALUES(?,?)', (identifier, encoded(record)))
        grouped = defaultdict(list)
        for path in self.files('storage/catalog/signal_library/research_links/RESEARCHLINK_*.json'):
            value = self.try_unit('branch', Path(path).stem, [path], lambda p=path: self.branch(p))
            if value: grouped[encoded(value['row']['relationship'])].append(value)
        selected = []
        for values in grouped.values():
            evidence = lambda v: frozenset(encoded(r) for k in ('trial_results','admission_results','validation_results') for r in v['row'][k])
            seen = set()
            for value in values:
                key = evidence(value)
                if key in seen or any(key < evidence(other) for other in values): continue
                seen.add(key); selected.append(value)
        by_recipe = defaultdict(list)
        for value in selected: by_recipe[value['row']['recipe']['id']].append(value)
        for rid, values in sorted(by_recipe.items()):
            bindings = {encoded(v['row']['recipe']) for v in values}
            if len(bindings) != 1:
                self.issue('recipe', rid); continue
            def load_recipe():
                store = FeatureStore(self.root)
                entry = _registered_entry(store, store.resolve(values[0]['row']['recipe']))
                compact(entry)
                return entry
            entry = self.try_unit('recipe', rid, [], load_recipe)
            if not entry: continue
            rows = [v['row'] for v in values]
            entry['research'] = {'state': 'results_linked', 'label': 'Research results recorded',
                'relationship_count': len({encoded(r['relationship']) for r in rows}),
                'branch_count': len(rows), 'p1_counts': dict(Counter(r['p1_status'] for r in rows)),
                'p2_counts': dict(Counter(r['p2_status'] for r in rows)),
                'research_stage_pass_count': len({encoded(r['relationship']) for r in rows if r['research_stage_pass']}),
                'description': 'Each result belongs to its exact hypothesis and period; no recipe-wide validation is implied.'}
            self.db.execute('INSERT INTO recipes VALUES(?,?,?,?)', (rid, entry['name'].casefold(), encoded(entry).casefold(), encoded(entry)))
            for value in values:
                row = value['row']
                self.db.execute('INSERT OR IGNORE INTO relationships VALUES(?,?)', (row['relationship']['id'], encoded(value['relationship'])))
                for table in ('trials', 'decisions'):
                    for record in value[table]: self.db.execute('INSERT OR IGNORE INTO ' + table + ' VALUES(?,?)', (record['id'], encoded(record)))
                self.db.execute('INSERT INTO branches VALUES(?,?,?,?,?,?,?,?)', (row['projection']['id'], rid, row['relationship']['id'],
                    row['scope'].get('id', row['scope'].get('reference', {}).get('id')), row['expected_direction'], row['horizon'], row['p2_status'], encoded(row)))
        for issue in self.issues: self.db.execute('INSERT INTO issues(value) VALUES(?)', (encoded(issue),))
        for unit in self.db.execute('SELECT kind,id FROM units').fetchall():
            if tuple(unit) not in self.live_units: self.db.execute('DELETE FROM units WHERE kind=? AND id=?', tuple(unit))
        # Ensure captured references still name the bytes actually verified. New
        # append-only publications are left for the next cycle; no global restart.
        for path, state in self.seen.items():
            if state is not None and signature(self.path(path)) != state['signature']:
                raise IntegrityFailure('Captured source changed before publication')
        return {'issues': self.issues, 'rebuilt': dict(self.rebuilt), 'reused': dict(self.reused),
                'source_count': len(self.seen), 'inventory_sha256': digest(self.seen)}
