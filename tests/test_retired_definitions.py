"""Synthetic retirement evidence only; no stored research or production access."""
from contextlib import ExitStack
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
sys.path.insert(0, str(PROJECT / 'deploy'))
import retired_definitions as retired
from release_bundle import canonical, sha


def archive_bytes(files, commit):
    manifest = {'schema': 'gambit_code_release_v1', 'repository': 'owenmosagiede/gambit-research-platform',
        'commit': commit, 'files': [{'path': p, 'sha256': sha(b), 'bytes': len(b)}
                                 for p, b in sorted(files.items())]}
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w:gz') as archive:
        for name, data in dict(files, **{'release-manifest.json': canonical(manifest)}).items():
            info = tarfile.TarInfo(name); info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return out.getvalue(), manifest


class SyntheticRetirement:
    """Reusable fixture: replace reviewed anchors and root ownership only in tests.

    The production ownership reader is independently tested below. All parsing,
    archive verification, planner matching and revalidation use the real helper.
    """
    def __init__(self, case, count=3):
        self.temp = tempfile.TemporaryDirectory(); case.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.root = self.base / 'application'
        self.root.mkdir(); self.stack = ExitStack(); case.addCleanup(self.stack.close)
        self.names = [retired.PREFIXES[i % 3] + f'RETIRED_{i:05d}/1.0.0.json' for i in range(count)]
        self.source_files = {name: canonical({'synthetic_retired_definition': i})
                             for i, name in enumerate(self.names)}
        self.source_files.update({'src/runtime/example.py': b'old executor\n',
                                  'config/unchanged.json': b'unchanged policy'})
        self.target_files = dict(self.source_files, **{'src/runtime/example.py': b'new executor\n'})
        for name in ('src/runtime/example.py', 'config/unchanged.json'):
            p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(self.source_files[name])
        self.source, self.source_manifest = archive_bytes(self.source_files, 'a' * 40)
        self.target, self.target_manifest = archive_bytes(self.target_files, 'b' * 40)
        self.source_path = self.base / 'source.tar.gz'; self.source_path.write_bytes(self.source)
        self.target_path = self.base / 'target.tar.gz'; self.target_path.write_bytes(self.target)
        self.source_sha = sha(self.source); self.target_sha = sha(self.target)
        self.omissions = {name: sha(self.source_files[name]) for name in self.names}
        self.reset = {'schema': 'gambit_clean_momentum_reset_v1', 'moves': {
            name.rsplit('/', 1)[0]: {'kind': 'directory', 'files': {
                '1.0.0.json': {'sha256': sha(self.source_files[name]), 'bytes': len(self.source_files[name])}}}
            for name in self.names}}
        self.reset['sha256'] = sha(canonical(self.reset))
        self.status = {'phase': 'complete', 'plan_sha256': self.reset['sha256'], 'verification': {'verified': True}}
        self.receipt = {'schema': 'gambit_code_deployment_plan_v1', 'status': 'succeeded',
            'data_touched': False, 'commit': 'a'*40, 'release_id': 'a'*40+'-synthetic', 'blockers': [],
            'post_reset_review': {'archive_sha256': self.source_sha,
                'manifest_sha256': sha(canonical(self.source_manifest)),
                'reset_plan_sha256': self.reset['sha256'], 'reset_plan_file_sha256': sha(canonical(self.reset)),
                'reset_status_file_sha256': sha(canonical(self.status)),
                'omissions_sha256': sha(canonical(self.omissions)), 'acknowledged_omissions': self.omissions,
                'action': 'acknowledged_absent_no_registry_writes'}}
        self.evidence = {key: self.base / name for key, name in retired.SAVED_NAMES.items()}
        self.pins = {}
        self.write_evidence()
        for key, value in {'SOURCE_COMMIT': 'a'*40, 'SOURCE_SHA256': self.source_sha,
            'PRIOR_RELEASE_ID': 'a'*40+'-synthetic', 'RESET_SHA256': self.reset['sha256'],
            'EVIDENCE_SHA256': self.pins, 'OMISSIONS_SHA256': sha(canonical(self.omissions)),
            'OMISSIONS_COUNT': count}.items():
            self.stack.enter_context(patch.object(retired, key, value))
        self.stack.enter_context(patch.object(retired, '_protected_bytes', side_effect=self.read_fixture))
        self.stack.enter_context(patch.object(retired, '_protected_directory', side_effect=self.protected_directory))
        self.context = self.load()

    def protected_directory(self, path):
        for p in (Path(path), *Path(path).parents):
            if p.is_relative_to(self.base) and (p.is_symlink() or not p.is_dir() or p.stat().st_mode & 0o022):
                raise RuntimeError('Unprotected synthetic evidence destination')

    def read_fixture(self, path, expected=None):
        p = Path(path)
        for parent in (p, *p.parents):
            if parent.is_relative_to(self.base) and (parent.is_symlink() or parent.stat().st_mode & 0o022):
                raise RuntimeError('Unprotected synthetic evidence')
        raw = p.read_bytes()
        if expected is not None and sha(raw) != expected:
            raise RuntimeError('Retirement evidence checksum differs')
        return raw

    def write_evidence(self):
        for key, value in [('plan', self.reset), ('status', self.status), ('receipt', self.receipt)]:
            raw = canonical(value); self.evidence[key].write_bytes(raw); self.pins[key] = sha(raw)

    def load(self):
        return retired.load_context(self.evidence, self.source_path, self.source_sha,
                                    self.target_path, self.target_sha)

    def plan(self, source=False):
        context = self.context
        return context.code_plan(self.root, context.source_manifest if source else context.target_manifest,
            context.source_files if source else context.target_files,
            context.source_sha256 if source else context.target_sha256)


class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.f = SyntheticRetirement(self)

    def test_both_plans_acknowledge_only_exact_absences_and_preserve_ordinary_planner(self):
        ordinary = retired.release.plan(self.f.root, self.f.source_manifest, self.f.source_files)
        self.assertEqual(len(ordinary['blockers']), 3)
        self.assertEqual(self.f.plan(True)['changes'], [])
        self.assertEqual(self.f.plan()['blockers'], [])
        self.assertEqual([v['path'] for v in self.f.plan()['changes']], ['src/runtime/example.py'])
        self.assertEqual(self.f.context.revalidate(self.f.root), self.f.context.binding)
        self.assertEqual(retired.release.plan(self.f.root, self.f.source_manifest, self.f.source_files), ordinary)
        self.assertTrue(all(not (self.f.root / name).exists() for name in self.f.names))

    def test_all_5717_synthetic_omissions_are_handled(self):
        f = SyntheticRetirement(self, count=5717)
        self.assertEqual(len(f.plan()['retirement_acknowledgement']['acknowledged_omissions']), 5717)
        self.assertEqual(f.plan(True)['changes'], [])
        self.assertEqual(len(retired.release.plan(f.root, f.source_manifest, f.source_files)['blockers']), 5717)

    def test_receipt_status_identity_map_and_evidence_are_required(self):
        for change in [lambda r: r.update(status='failed'), lambda r: r.update(release_id='wrong'),
                       lambda r: r['post_reset_review']['acknowledged_omissions'].pop(self.f.names[0]),
                       lambda r: r['post_reset_review'].update(action='restore_definitions')]:
            original = deepcopy(self.f.receipt)
            change(self.f.receipt); self.f.write_evidence()
            with self.assertRaises(RuntimeError): self.f.load()
            self.f.receipt = original; self.f.write_evidence()

    def test_reset_status_plan_identity_and_raw_hash_change_are_rejected(self):
        self.f.status['phase'] = 'incomplete'; self.f.write_evidence()
        with self.assertRaisesRegex(RuntimeError, 'completed retirement'): self.f.load()
        self.f.status['phase'] = 'complete'; self.f.write_evidence()
        self.f.evidence['plan'].write_bytes(self.f.evidence['plan'].read_bytes() + b' ')
        with self.assertRaisesRegex(RuntimeError, 'checksum'): self.f.context.revalidate(self.f.root)

    def test_missing_extra_or_changed_inventory_cannot_be_acknowledged(self):
        for mutation in [lambda m: m.pop(self.f.names[0].rsplit('/',1)[0]),
                         lambda m: m.update({'definitions/features/EXTRA': {'files': {'1.0.0.json': {'sha256':'1'*64,'bytes':2}}}}),
                         lambda m: next(iter(m.values()))['files']['1.0.0.json'].update(sha256='0'*64)]:
            original = deepcopy(self.f.reset)
            mutation(self.f.reset['moves']); self.f.write_evidence()
            with self.assertRaises(RuntimeError): self.f.load()
            self.f.reset = original; self.f.write_evidence()

    def test_reappeared_file_directory_and_redirected_ancestor_are_rejected(self):
        path = self.f.root / self.f.names[0]
        path.parent.mkdir(parents=True)
        for make in (lambda: path.write_bytes(self.f.source_files[self.f.names[0]]), lambda: path.mkdir()):
            make()
            with self.assertRaisesRegex(RuntimeError, 'reappeared'): self.f.plan()
            path.rmdir() if path.is_dir() else path.unlink()
        path.symlink_to(self.f.base / 'nonexistent')
        with self.assertRaisesRegex(RuntimeError, 'redirected'): self.f.context.revalidate(self.f.root)
        path.unlink(); path.parent.rmdir(); path.parent.symlink_to(self.f.base)
        with self.assertRaisesRegex(RuntimeError, 'redirected'): self.f.plan()

    def test_changed_missing_or_substituted_archive_and_payload_are_rejected(self):
        for files in [dict(self.f.target_files, **{self.f.names[0]: b'changed'}),
                      {k:v for k,v in self.f.target_files.items() if k != self.f.names[0]}]:
            raw, _ = archive_bytes(files, 'b'*40); self.f.target_path.write_bytes(raw)
            with self.assertRaises(RuntimeError):
                retired.load_context(self.f.evidence, self.f.source_path, self.f.source_sha, self.f.target_path, sha(raw))
        self.f.target_path.write_bytes(self.f.target)
        bad = dict(self.f.target_files, **{'src/runtime/example.py': b'changed'})
        with self.assertRaisesRegex(RuntimeError, 'Planner archive'):
            self.f.context.code_plan(self.f.root, self.f.target_manifest, bad, self.f.target_sha)
        with self.assertRaisesRegex(RuntimeError, 'Planner archive'):
            self.f.context.code_plan(self.f.root, self.f.target_manifest, self.f.target_files, '0'*64)
        self.f.source_path.write_bytes(self.f.target)
        with self.assertRaisesRegex(RuntimeError, 'checksum'): self.f.plan()

    def test_all_unrelated_registry_removal_runtime_and_reader_blockers_remain(self):
        extra = [{'path':'definitions/scopes/extra.json','reason':retired.REGISTRY_BLOCKER},
                 {'path':'config/policy.json','reason':retired.REGISTRY_BLOCKER},
                 {'path':'requirements-cloud.lock','reason':retired.REGISTRY_BLOCKER},
                 {'path':'deploy/gambit-worker.service','reason':retired.REGISTRY_BLOCKER},
                 {'path':'src/old.py','reason':'Removal requires a separately reviewed migration'},
                 {'path':'storage/catalog/lineage_packs','reason':'Reader unavailable'}]
        ordinary = retired.release.plan(self.f.root, self.f.target_manifest, self.f.target_files)
        with patch.object(retired.release, 'plan', return_value=dict(ordinary, blockers=ordinary['blockers']+extra)):
            self.assertEqual(self.f.plan()['blockers'], extra)
        (self.f.root/'config/unchanged.json').write_bytes(b'policy changed')
        self.assertEqual(self.f.plan()['blockers'][0]['path'], 'config/unchanged.json')

    def test_duplicate_missing_or_wrong_reason_blocker_and_definition_write_fail(self):
        ordinary = retired.release.plan(self.f.root, self.f.target_manifest, self.f.target_files)
        candidates = [dict(ordinary, blockers=ordinary['blockers'][:-1]),
            dict(ordinary, blockers=ordinary['blockers']+[ordinary['blockers'][0]]),
            dict(ordinary, blockers=[dict(b, reason='different') for b in ordinary['blockers']]),
            dict(ordinary, changes=ordinary['changes']+[{'path':self.f.names[0]}])]
        for candidate in candidates:
            with patch.object(retired.release, 'plan', return_value=candidate):
                with self.assertRaises(RuntimeError): self.f.plan()

    def test_durable_copy_loads_without_original_staging_and_detects_tampering(self):
        folder = self.f.base/'saved'
        saved = self.f.context.persist(folder)
        self.assertEqual(saved.binding, self.f.context.binding)
        for path in list(self.f.evidence.values())+[self.f.source_path,self.f.target_path]: path.unlink()
        self.assertEqual(retired.load_saved(folder).revalidate(self.f.root), saved.binding)
        self.assertEqual(saved.code_plan(self.f.root,saved.target_manifest,saved.target_files,saved.target_sha256)['blockers'], [])
        (folder/'context.json').write_bytes(canonical(dict(saved.binding, action='restore')))
        with self.assertRaisesRegex(RuntimeError, 'Saved retirement context'): retired.load_saved(folder)

    def test_unprotected_destination_is_rejected_before_any_copy(self):
        destination = self.f.base/'unprotected'; destination.mkdir(); destination.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError, 'destination'):
            self.f.context.persist(destination/'evidence')
        self.assertFalse((destination/'evidence').exists())
        destination.chmod(0o700)
        alias = self.f.base/'alias'; alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'destination'):
            self.f.context.persist(alias/'evidence')
        self.assertFalse((destination/'evidence').exists())

    def test_saved_source_evidence_cannot_change_silently(self):
        saved = self.f.context.persist(self.f.base/'saved')
        (self.f.base/'saved/receipt.json').write_bytes(b'{}')
        with self.assertRaisesRegex(RuntimeError, 'checksum'): saved.revalidate(self.f.root)

    def test_unprotected_or_redirected_evidence_is_refused_by_fixture_reader(self):
        p = self.f.evidence['status']; raw = p.read_bytes(); p.chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, 'Unprotected'): self.f.load()
        p.chmod(0o600); p.unlink(); target = self.f.base/'alias'; target.write_bytes(raw); p.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, 'Unprotected'): self.f.load()

    def test_strict_json_and_canonical_relative_paths(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":{"x":1,"x":2}}', b'{"a":NaN}']:
            with self.assertRaises(RuntimeError): retired._json(raw)
        for path in ['', '.', '..', '../a', '/a', 'a/../b', 'a//b', 'a\\b', './a']:
            with self.assertRaises(RuntimeError): retired._relative(path)
        self.assertEqual(retired._relative('definitions/features/a/1.0.0.json'), 'definitions/features/a/1.0.0.json')


class ProtectedReaderTests(unittest.TestCase):
    def test_actual_fd_read_and_checksum_with_protected_stat_metadata(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve()/'evidence.json'; path.write_bytes(b'protected evidence')
            real_lstat = Path.lstat; real_fstat = os.fstat
            def protected_info(info):
                fields = ('st_mode','st_uid','st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
                return SimpleNamespace(**dict({k:getattr(info,k) for k in fields},
                    st_uid=0, st_mode=info.st_mode & ~0o022))
            def protected_lstat(value): return protected_info(real_lstat(value))
            def protected_fstat(fd): return protected_info(real_fstat(fd))
            with patch.object(Path,'lstat',protected_lstat), patch.object(os,'fstat',protected_fstat):
                self.assertEqual(retired._protected_bytes(path,sha(b'protected evidence')),b'protected evidence')
                with self.assertRaisesRegex(RuntimeError,'checksum'):
                    retired._protected_bytes(path,'0'*64)
            calls = 0
            def changed_fstat(fd):
                nonlocal calls
                result=protected_fstat(fd);calls += 1
                if calls == 2: result.st_mtime_ns += 1
                return result
            with patch.object(Path,'lstat',protected_lstat), patch.object(os,'fstat',changed_fstat):
                with self.assertRaisesRegex(RuntimeError,'changed while reading'):
                    retired._protected_bytes(path)

    def test_destination_protection_checks_all_ancestors(self):
        good=type('Stat', (), {'st_mode':stat.S_IFDIR|0o700,'st_uid':0})()
        for mode, uid in [(stat.S_IFDIR|0o777,0),(stat.S_IFLNK|0o777,0),
                          (stat.S_IFDIR|0o700,501),(stat.S_IFREG|0o600,0)]:
            bad=type('Stat', (), {'st_mode':mode,'st_uid':uid})()
            with patch.object(Path,'lstat',side_effect=[good,bad]):
                with self.assertRaisesRegex(RuntimeError,'destination'):
                    retired._protected_directory('/protected/parent')
        with patch.object(Path,'lstat',return_value=good):
            retired._protected_directory('/protected/parent')


    def test_non_root_owned_file_or_writable_redirected_ancestor_fails_before_open(self):
        for mode, uid in [(stat.S_IFREG|0o644, 501), (stat.S_IFREG|0o666, 0),
                          (stat.S_IFLNK|0o777,0), (stat.S_IFIFO|0o600,0)]:
            fake = type('Stat', (), {'st_mode':mode,'st_uid':uid})()
            with patch.object(Path, 'lstat', return_value=fake), patch.object(os,'open') as opened:
                with self.assertRaises(RuntimeError): retired._protected_bytes('/protected/evidence.json')
                opened.assert_not_called()
        for path in ('relative/path', '/protected/../elsewhere'):
            with self.assertRaises(RuntimeError): retired._protected_bytes(path)

    def test_writable_ancestor_is_rejected_even_when_file_is_protected(self):
        fileinfo=type('Stat', (), {'st_mode':stat.S_IFREG|0o600,'st_uid':0})()
        badparent=type('Stat', (), {'st_mode':stat.S_IFDIR|0o777,'st_uid':0})()
        with patch.object(Path, 'lstat', side_effect=[fileinfo,badparent]), patch.object(os,'open') as opened:
            with self.assertRaises(RuntimeError): retired._protected_bytes('/protected/evidence.json')
            opened.assert_not_called()


if __name__ == '__main__': unittest.main()


class SuccessorRetirementTests(unittest.TestCase):
    def setUp(self):
        self.f = SyntheticRetirement(self)
        self.current = self.f.target_path
        self.current_files = self.f.target_files
        self.next_files = dict(self.current_files, **{'src/runtime/example.py': b'third executor\n'})
        raw, self.next_manifest = archive_bytes(self.next_files, 'c'*40)
        self.next = self.f.base/'next.tar.gz'; self.next.write_bytes(raw); self.next_sha = sha(raw)
        (self.f.root/'src/runtime/example.py').write_bytes(b'new executor\n')

    def load(self, **changes):
        args = dict(retirement_archive=self.f.source_path)
        args.update(changes)
        return retired.load_context(self.f.evidence, self.current, self.f.target_sha,
                                    self.next, self.next_sha, **args)

    def test_later_release_uses_same_exact_retirement_evidence_and_preserves_absence(self):
        context = self.load()
        self.assertEqual(context.binding['schema'], 'gambit_retired_definitions_v2')
        self.assertEqual(context.binding['acknowledged_omissions'], self.f.omissions)
        self.assertEqual(context.binding['retirement_source_archive_sha256'], self.f.source_sha)
        self.assertEqual(context.code_plan(self.f.root, context.source_manifest, context.source_files,
                                          context.source_sha256)['changes'], [])
        plan = context.code_plan(self.f.root, context.target_manifest, context.target_files, context.target_sha256)
        self.assertEqual(plan['blockers'], [])
        self.assertEqual([r['path'] for r in plan['changes']], ['src/runtime/example.py'])
        saved = context.persist(self.f.base/'saved-successor')
        for path in [*self.f.evidence.values(), self.f.source_path, self.current, self.next]: path.unlink()
        self.assertEqual(retired.load_saved(self.f.base/'saved-successor').revalidate(self.f.root), saved.binding)
        self.assertTrue(all(not (self.f.root/name).exists() for name in self.f.names))

    def test_successor_cannot_omit_or_replace_anchor_or_change_either_definition_inventory(self):
        with self.assertRaises(RuntimeError): self.load(retirement_archive=None)
        with self.assertRaises(RuntimeError): self.load(retirement_archive=self.current)
        for target in ('current', 'next'):
            files = dict(self.current_files if target == 'current' else self.next_files)
            files[self.f.names[0]] = b'changed retired definition'
            raw, _ = archive_bytes(files, 'd'*40)
            path = self.current if target == 'current' else self.next
            original = path.read_bytes(); path.write_bytes(raw)
            source_sha = sha(raw) if target == 'current' else self.f.target_sha
            target_sha = sha(raw) if target == 'next' else self.next_sha
            with self.assertRaisesRegex(RuntimeError, 'Retired definition differs'):
                retired.load_context(self.f.evidence, self.current, source_sha, self.next, target_sha,
                                     retirement_archive=self.f.source_path)
            path.write_bytes(original)
