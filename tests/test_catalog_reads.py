"""Isolated cache invalidation, reader boundaries, and concurrent publication."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from api.catalog_cache import CatalogCache
from data.alfred_onboarding import stable_read
from data.catalog_reads import CatalogChanged, catalog_glob, catalog_reads, memo
from data.transformations.registry import _read as registry_read
from research.store import read_json


class CatalogReadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'record.json'
        self.path.write_text('{"value":1}')
        self.now = [0]
        self.cache = CatalogCache(clock=lambda: self.now[0])
        self.calls = 0

    def read(self):
        self.calls += 1
        return {'items': [json.loads(stable_read(self.path))], 'issues': []}

    def get(self, reader=None, key='catalog'):
        return self.cache.get_verified(key, self.root, reader or self.read)

    def test_unchanged_catalog_survives_old_ttl_but_reverifies_at_max_age(self):
        first = self.get()
        self.now[0] = 10
        second = self.get()
        self.assertEqual(self.calls, 1)
        first['items'].clear()
        self.assertEqual(second['items'], [{'value': 1}])
        self.now[0] = 300
        self.assertEqual(self.get(), second)
        self.assertEqual(self.calls, 2)

    def test_same_size_edit_and_restored_mtime_invalidates_immediately(self):
        self.get()
        before = self.path.stat()
        self.path.write_text('{"value":2}')
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.get()['items'], [{'value': 2}])
        self.assertEqual(self.calls, 2)

    def test_atomic_replacement_deletion_and_repair_never_return_stale_success(self):
        self.get()
        temporary = self.root / 'temporary'
        temporary.write_text('{"value":3}')
        temporary.replace(self.path)
        self.assertEqual(self.get()['items'], [{'value': 3}])
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.get()
        self.assertFalse(self.cache.verified_entries)
        self.assertFalse(self.cache.pending)
        self.path.write_text('{"value":4}')
        self.assertEqual(self.get()['items'], [{'value': 4}])

    def test_symlink_target_change_is_not_hidden_by_an_unchanged_link(self):
        folder = self.root / 'source'
        folder.mkdir()
        original = self.path
        original.rename(folder / 'record.json')
        alias = self.root / 'alias'
        alias.symlink_to(folder, target_is_directory=True)
        self.path = alias / 'record.json'
        self.get()
        other = self.root / 'other'
        other.mkdir()
        (other / 'record.json').write_text('{"value":2}')
        alias.unlink()
        alias.symlink_to(other, target_is_directory=True)
        self.assertEqual(self.get()['items'], [{'value': 2}])

    def test_new_nested_files_and_removal_invalidate_directory_membership(self):
        def read():
            self.calls += 1
            return {'items': [str(p.relative_to(self.root)) for p in catalog_glob(self.root, '*/*.json')]}
        self.assertEqual(self.get(read)['items'], [])
        folder = self.root / 'new'
        folder.mkdir()
        path = folder / 'record.json'
        path.write_text('{}')
        self.assertEqual(self.get(read)['items'], ['new/record.json'])
        (folder / 'second.json').write_text('{}')
        self.assertEqual(len(self.get(read)['items']), 2)
        path.unlink()
        self.assertEqual(self.get(read)['items'], ['new/second.json'])
        self.assertEqual(self.calls, 4)

    def test_redirected_catalog_directory_invalidates_resolved_file_reads(self):
        first=self.root/'first';second=self.root/'second'
        first.mkdir();second.mkdir()
        (first/'entry.json').write_text('{"value":1}')
        (second/'entry.json').write_text('{"value":2}')
        alias=self.root/'catalog';alias.symlink_to(first,target_is_directory=True)
        def read():
            return {'items':[read_json(path.resolve()) for path in catalog_glob(alias,'*.json')]}
        self.assertEqual(self.get(read)['items'],[{'value':1}])
        alias.unlink();alias.symlink_to(second,target_is_directory=True)
        self.assertEqual(self.get(read)['items'],[{'value':2}])

    def test_registry_research_and_stable_read_all_record_dependencies(self):
        for reader in (registry_read, read_json, lambda p: json.loads(stable_read(p))):
            with self.subTest(reader=reader):
                cache = CatalogCache()
                self.path.write_text('{"value":1}')
                get = lambda: cache.get_verified('reader', self.root, lambda: {'value': reader(self.path)})
                self.assertEqual(get()['value']['value'], 1)
                self.path.write_text('{"value":2}')
                self.assertEqual(get()['value']['value'], 2)

    def test_partial_and_failed_reads_are_not_retained(self):
        for issues in ([{'code': 'UNAVAILABLE_SIGNAL'}], [{'code': 'RESEARCH_STATUS_UNAVAILABLE'}]):
            self.get(lambda: {'items': [], 'issues': issues})
            self.assertFalse(self.cache.verified_entries)
        with self.assertRaises(ValueError):
            self.get(lambda: (_ for _ in ()).throw(ValueError('bad')))
        self.assertFalse(self.cache.pending)
        self.assertEqual(self.get()['items'], [{'value': 1}])

    def test_concurrent_reads_share_verification(self):
        started, release = threading.Event(), threading.Event()
        def read():
            result = self.read()
            started.set()
            self.assertTrue(release.wait(3))
            return result
        with ThreadPoolExecutor(max_workers=4) as pool:
            first = pool.submit(self.get, read)
            self.assertTrue(started.wait(1))
            rest = [pool.submit(self.get, read) for _ in range(3)]
            release.set()
            values = [first.result()] + [f.result() for f in rest]
        self.assertEqual(self.calls, 1)
        values[0]['items'].clear()
        self.assertEqual(values[1]['items'], [{'value': 1}])

    def test_publication_during_build_retries_without_caching_a_mixed_view(self):
        started, release = threading.Event(), threading.Event()
        def read():
            result = self.read()
            if self.calls == 1:
                started.set()
                self.assertTrue(release.wait(3))
            return result
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.get, read)
            self.assertTrue(started.wait(1))
            self.path.write_text('{"value":2}')
            release.set()
            self.assertEqual(future.result()['items'], [{'value': 2}])
        self.assertEqual(self.calls, 2)

    def test_continuous_changes_fail_boundedly_without_stale_fallback(self):
        def read():
            result = self.read()
            self.path.write_text(json.dumps({'value': self.calls + 1}))
            return result
        with self.assertRaises(CatalogChanged):
            self.get(read)
        self.assertEqual(self.calls, 2)
        self.assertFalse(self.cache.verified_entries)
        self.assertFalse(self.cache.pending)

    def test_request_memo_does_not_escape_request_root_or_thread(self):
        calls = []
        def read():
            calls.append(1)
            return object()
        with catalog_reads(self.root) as context:
            first = memo(self.root, 'registry', read)
            self.assertIs(memo(self.root, 'registry', read), first)
            self.assertIsNot(memo(self.root / 'other', 'registry', read), first)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertIsNot(pool.submit(memo, self.root, 'registry', read).result(), first)
        self.assertFalse(context.values)
        self.assertIsNot(memo(self.root, 'registry', read), first)
        self.assertEqual(len(calls), 4)

    def test_cache_is_bounded_and_separates_workspace_roots(self):
        self.cache.limit = 2
        self.get(key='one')
        self.get(key='two')
        self.get(key='three')
        self.assertEqual(len(self.cache.verified_entries), 2)
        other = self.root / 'other'
        self.assertEqual(self.cache.get_verified('three', other, lambda: {'value': 99}), {'value': 99})
        self.assertEqual(self.get(key='three')['items'], [{'value': 1}])

    def test_other_catalog_eviction_during_validation_does_not_fail(self):
        self.cache.limit = 1
        original = self.get()
        dependencies = next(iter(self.cache.verified_entries.values()))[2]
        def validate():
            self.get(key='other')
            return True
        with patch.object(dependencies, 'unchanged', side_effect=validate):
            self.assertEqual(self.get(), original)
        self.assertEqual(len(self.cache.verified_entries), 1)
