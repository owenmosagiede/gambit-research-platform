"""Offline PIT store tests; all writes occur in isolated temporary platforms.

The bounded integration fixture generates fictional inputs in a temporary directory
and runs the real importer and PIT writer. It never copies the retired real pilot,
consults legacy stores, calls a provider or writes the real platform.
"""

import copy
from contextlib import closing
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from alfred_synthetic_fixture import make_bounded_fixture, SYNTHETIC_EVENT_COUNT

try:
    from data import alfred_pit as pit
except ImportError as exc:
    pit = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = ''

REAL_ROOT = Path(__file__).resolve().parents[1]
RAW_REF = {'id': 'SNAPSHOT_' + 'a'*64, 'version': '1.0.0', 'content_sha256': 'b'*64}
VIEW_REF = {'id': 'SYNTHETIC_VIEW', 'version': '1.0.0', 'content_sha256': 'c'*64}
BLOB_HASH = 'd'*64


def synthetic_payload():
    return {'output_type': 3, 'units': 'lin', 'offset': 0, 'count': 1, 'observations': [{
        'date': '2018-01-01',
        'CES0500000003_20180202': '26.740',
        'CES0500000003_20180309': '26.710',
        'CES0500000003_20180406': '26.710',
        'CES0500000003_20180504': '.',
    }]}


@unittest.skipUnless(pit, 'ALFRED PIT module or its optional dependency unavailable: ' + IMPORT_ERROR)
class AlfredPitUnitTests(unittest.TestCase):
    def test_revision_boundaries_and_before_first_release(self):
        rows = pit.normalize(synthetic_payload(), RAW_REF, VIEW_REF, BLOB_HASH)
        self.assertEqual(pit.select_rows(rows, '2018-02-01', '2018-01-01'), [])
        self.assertEqual(pit.select_rows(rows, '2018-02-02', '2018-01-01')[0]['value'], '26.74')
        self.assertEqual(pit.select_rows(rows, '2018-03-08', '2018-01-01')[0]['value'], '26.74')
        revised = pit.select_rows(rows, '2018-03-09', '2018-01-01')
        self.assertEqual(len(revised), 1)
        self.assertEqual(revised[0]['value'], '26.71')
        self.assertNotIn('next_vintage_date', revised[0])
        self.assertNotIn('available_at', revised[0])
        self.assertEqual(revised[0]['raw_snapshot'], RAW_REF)

    def test_same_value_change_event_and_missing_state_are_preserved(self):
        rows = pit.normalize(synthetic_payload(), RAW_REF, VIEW_REF, BLOB_HASH)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1]['value'], rows[2]['value'])
        self.assertEqual(rows[1]['next_vintage_date'], '2018-04-06')
        self.assertEqual(rows[2]['source_field'], 'CES0500000003_20180406')
        self.assertEqual(pit.select_rows(rows, '2018-04-06')[0]['vintage_date'], '2018-04-06')
        missing = pit.select_rows(rows, '2018-05-04')[0]
        self.assertEqual(missing['status'], 'missing')
        self.assertIsNone(missing['value'])
        self.assertEqual(missing['source_raw_blob_sha256'], BLOB_HASH)
        self.assertIsNone(rows[-1]['next_vintage_date'])

    def test_date_only_rejects_invalid_dates_and_intraday_inputs(self):
        self.assertEqual(pit.date_only('2020-02-29'), '2020-02-29')
        for value in ('2018-02-29', '2018-13-01', '2018-2-02', '2018-02-02T00:00:00Z', None, 20180202):
            with self.subTest(value=value), self.assertRaises(ValueError):
                pit.date_only(value)


@unittest.skipUnless(pit, 'ALFRED PIT module or its optional dependency unavailable: ' + IMPORT_ERROR)
class AlfredPitStoreIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixed_paths = [
            'specs/schemas/platform.schema.json', 'specs/schemas/onboarding.schema.json',
            'specs/schemas/alfred_pit_rows.schema.json',
            'src/data/alfred_pit.py', 'src/data/alfred_onboarding.py', 'src/data/pit_selection.py',
            'tools/materialize_alfred_pit.py', 'tools/onboard_alfred.py',
        ]
        cls.fixture_dir = tempfile.TemporaryDirectory(prefix='alfred_pit_fixture_', dir='/private/tmp')
        cls.addClassCleanup(cls.fixture_dir.cleanup)
        cls.fixture_root = Path(cls.fixture_dir.name) / 'research_platform'
        cls.fixture_root.mkdir()
        for relative in fixed_paths:
            destination = cls.fixture_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REAL_ROOT/relative, destination)
        fixture_run = make_bounded_fixture(cls.fixture_root, Path(cls.fixture_dir.name))
        cls.run_patch = patch.object(pit, 'RUN', fixture_run)
        cls.run_patch.start()
        cls.addClassCleanup(cls.run_patch.stop)
        # Materialization and every subsequent mutation affect only this temporary
        # platform. Per-test copies contain these generated fixture artifacts.
        cls.completion = pit.materialize(cls.fixture_root)
        cls.snapshot_id = cls.completion['pit_snapshot']['id']

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory(prefix='alfred_pit_case_', dir='/private/tmp')
        self.addCleanup(self.test_dir.cleanup)
        self.root = Path(self.test_dir.name) / 'research_platform'
        shutil.copytree(self.fixture_root, self.root)
        self.assertNotEqual(self.root.resolve(), REAL_ROOT.resolve())

    def selected(self):
        return pit.query(self.root, self.snapshot_id, '2018-03-09', '2018-01-01')

    def immutable_storage_files(self):
        result = {}
        for path in (self.root / 'storage').rglob('*'):
            if path.is_file():
                relative = path.relative_to(self.root).as_posix()
                if relative == pit.INDEX or relative.startswith('storage/temporary/'):
                    continue
                result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def test_complete_synthetic_events_12_periods_and_known_historical_revisions(self):
        snapshot, rows = pit.read_pit(self.root, self.snapshot_id)
        self.assertEqual(len(rows), SYNTHETIC_EVENT_COUNT)
        self.assertEqual(snapshot['record_count'], SYNTHETIC_EVENT_COUNT)
        self.assertEqual({row['observation_date'] for row in rows}, {f'2018-{month:02d}-01' for month in range(1, 13)})
        self.assertEqual(pit.query(self.root, self.snapshot_id, '2018-02-01', '2018-01-01')['observations'], [])
        self.assertEqual(pit.query(self.root, self.snapshot_id, '2018-02-02', '2018-01-01')['observations'][0]['value'], '26.74')
        self.assertEqual(self.selected()['observations'][0]['value'], '26.71')
        self.assertTrue(all('next_vintage_date' not in row for row in self.selected()['observations']))

    def test_query_rejects_future_invalid_and_uncovered_dates(self):
        snapshot, _ = pit.read_pit(self.root, self.snapshot_id)
        future = (dt.date.fromisoformat(snapshot['information_cutoff'][:10]) + dt.timedelta(days=1)).isoformat()
        for as_of, observation in ((future, '2018-01-01'), ('2018-02-30', '2018-01-01'),
                                   ('2018-03-09T00:00:00Z', None), ('2018-03-09', '2017-12-01'),
                                   ('2018-03-09', '2018-01-02')):
            with self.subTest(as_of=as_of, observation=observation), self.assertRaises(ValueError):
                pit.query(self.root, self.snapshot_id, as_of, observation)

    def test_corrupted_canonical_payload_fails_closed(self):
        payload = self.root / self.completion['payload_path']
        payload.write_bytes(payload.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.selected()

    def test_corrupted_index_reference_fails_closed(self):
        with closing(sqlite3.connect(self.root / pit.INDEX)) as connection, connection:
            connection.execute('UPDATE snapshots SET content_sha256=? WHERE snapshot_id=?', ('0'*64, self.snapshot_id))
        with self.assertRaisesRegex(ValueError, 'Stale PIT index'):
            self.selected()

    def test_corrupted_index_table_row_fails_closed(self):
        with closing(sqlite3.connect(self.root / pit.INDEX)) as connection, connection:
            connection.execute('UPDATE observations SET row_json=? WHERE snapshot_id=? AND observation_date=? AND vintage_date=?',
                               ('{}', self.snapshot_id, '2018-01-01', '2018-02-02'))
        with self.assertRaisesRegex(ValueError, 'index differs'):
            self.selected()

    def test_deleted_index_rebuild_preserves_query_results(self):
        expected = self.selected()
        (self.root / pit.INDEX).unlink()
        with self.assertRaisesRegex(ValueError, 'index missing'):
            self.selected()
        rebuilt = pit.rebuild_index(self.root)
        self.assertEqual(rebuilt['vintage_rows'], SYNTHETIC_EVENT_COUNT)
        self.assertEqual(self.selected(), expected)

    def test_repeated_materialization_adds_no_immutable_files(self):
        before = self.immutable_storage_files()
        repeated = pit.materialize(self.root)
        self.assertEqual(repeated['pit_snapshot'], self.completion['pit_snapshot'])
        self.assertEqual(self.immutable_storage_files(), before)

    def test_reads_use_pinned_row_schema_after_working_schema_changes(self):
        expected = self.selected()
        current_schema = self.root / 'specs/schemas/alfred_pit_rows.schema.json'
        current_schema.write_text('{"not": {}}\n')
        self.assertEqual(self.selected(), expected)
        self.assertEqual(len(pit.read_pit(self.root, self.snapshot_id)[1]), SYNTHETIC_EVENT_COUNT)

    def test_missing_pinned_schema_evidence_fails_closed(self):
        evidence_id = self.completion['row_schema']['id']
        (self.root / f'storage/catalog/onboarding/evidence/{evidence_id}.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.selected()


if __name__ == '__main__':
    unittest.main()
