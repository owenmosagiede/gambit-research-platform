"""Actual local storage tests for the exact-source FX snapshot adapter."""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from data.alfred_onboarding import canonical, sha
from data.fx_onboarding import (SOURCE_SYMBOLS, FXOnboardingError,
    InterruptedOnboarding, inspect_source, onboard, read_source)
from data.transformations.identity import digest

PROJECT = Path(__file__).resolve().parents[1]


def build_fixture(directory):
    root, legacy = directory / 'platform', directory / 'legacy'
    root.mkdir(); legacy.mkdir()
    shutil.copytree(PROJECT / 'specs', root / 'specs')
    (root / 'config').mkdir()
    (root / 'config/storage.local.json').write_bytes(canonical({'stores': {
        'LEGACY_TEST': {'path': str(legacy), 'read_only': True},
        'PLATFORM_LOCAL': {'path': str(root), 'read_only': False},
    }}))
    sources = []
    capture = '2026-09-06T21:03:46Z'
    for number, symbol in enumerate(SOURCE_SYMBOLS):
        base, quote = symbol.split('/')
        safe = symbol.replace('/', '_')
        dataset_id = 'DS_TWELVE_' + safe
        directory = legacy / 'production/twelve_data_fx' / ('symbol=' + safe) / 'page=0001'
        directory.mkdir(parents=True)
        rows = [{'datetime': day, 'open': str(number + 1), 'high': str(number + 2),
                 'low': str(number + 1), 'close': str(number + 1 + i / 10)}
                for i, day in enumerate(('2020-01-02', '2020-01-03', '2020-01-06', '2020-01-07'))]
        raw = {'meta': {'symbol': symbol, 'interval': '1day'}, 'values': rows}
        raw_bytes = canonical(raw)
        raw_hash = sha(raw_bytes)
        raw_relative = f'raw/v1/twelve_data_fx/{raw_hash[:2]}/{raw_hash}.json'
        raw_path = legacy / raw_relative
        raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_bytes(raw_bytes)
        ingestion_id = 'ING_TWELVE_DATA_FX_' + safe
        ingestion = {'ingestion_id': ingestion_id, 'retrieved_at': capture,
                     'raw_file_location': raw_relative,
                     'checksum': {'algorithm': 'sha256', 'value': raw_hash}}
        observations = []
        for row in rows:
            for field in ('open', 'high', 'low', 'close'):
                observations.append({'observation_date': row['datetime'],
                    'dataset_id': dataset_id, 'unit': f'{quote}_per_{base}',
                    'dimensions': {'price_field': field}, 'retrieved_at': capture,
                    'ingestion_id': ingestion_id, 'vintage_id': capture, 'revision_number': 0,
                    'quality_flags': ['vendor_history_snapshot'],
                    'source_record_id': symbol + ':' + row['datetime'] + ':' + field,
                    'value': float(row[field]), 'available_at': row['datetime'] + 'T00:00:00Z',
                    'original_release_at': row['datetime'] + 'T00:00:00Z', 'timestamp_precision': 'inferred'})
        obs_bytes = gzip.compress(b''.join(canonical(r) + b'\n' for r in observations), mtime=0)
        obs_path = directory / 'observations.jsonl.gz'; obs_path.write_bytes(obs_bytes)
        obs_relative = str(obs_path.relative_to(legacy))
        (directory / 'page-manifest.json').write_bytes(canonical({
            'observation_count': len(observations), 'observations_checksum_sha256': sha(obs_bytes)}))
        (directory / 'raw-ingestion-manifest.json').write_bytes(canonical({'ingestions': [ingestion]}))
        (directory / 'dataset-registry.json').write_bytes(canonical({'datasets': [{
            'dataset_id': dataset_id, 'source_dataset_id': symbol, 'unit': f'{quote}_per_{base}', 'frequency': 'daily'}]}))
        sources.append({'symbol': symbol, 'dataset_id': dataset_id, 'base_currency': base,
            'quote_currency': quote, 'units': [f'{quote}_per_{base}'],
            'pages': [{'directory': str(directory.relative_to(legacy)),
                'observation_path': obs_relative, 'observation_sha256': sha(obs_bytes),
                'raw_path': raw_relative, 'raw_sha256': raw_hash, 'retrieved_at': capture,
                'ingestion_id': ingestion_id, 'actual_ohlc_rows': 16, 'actual_close_rows': 4}],
            'actual_close_rows': 4, 'unique_close_dates': 4,
            'coverage_min': '2020-01-02', 'coverage_max': '2020-01-07',
            'all_raw_artifacts': [{'path': raw_relative, 'sha256': raw_hash,
                'known_ingestions': [ingestion], 'date_min': '2020-01-02', 'date_max': '2020-01-07'}],
            'raw_dates_absent_from_canonical': []})
    audit = {'sources': sources, 'legacy_root': str(legacy)}
    # The caller receives a stable fixture path outside the read-only source root.
    audit_path = root.parent / 'audit.json'
    audit_path.write_bytes(canonical(audit))
    return root, legacy, audit_path, audit


def rewrite_page(legacy, source, mutate):
    page = source['pages'][0]
    path = legacy / page['observation_path']
    records = [json.loads(x) for x in gzip.decompress(path.read_bytes()).splitlines()]
    mutate(records)
    encoded = gzip.compress(b''.join(canonical(r) + b'\n' for r in records), mtime=0)
    path.write_bytes(encoded); page['observation_sha256'] = sha(encoded)
    page['actual_ohlc_rows'] = len(records)
    page['actual_close_rows'] = sum(r['dimensions']['price_field'] == 'close' for r in records)
    (legacy / page['directory'] / 'page-manifest.json').write_bytes(canonical({
        'observation_count': len(records), 'observations_checksum_sha256': sha(encoded)}))


class FXOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root, self.legacy, self.audit_path, self.audit = build_fixture(Path(self.temp.name))

    def execute(self, **kwargs):
        return onboard(self.root, self.legacy, self.audit_path,
                       migration_time=kwargs.pop('migration_time', '2026-10-09T10:00:00Z'), **kwargs)

    def test_exact_requested_sources(self):
        self.assertEqual(len(SOURCE_SYMBOLS), 18)
        self.assertEqual(len(set(SOURCE_SYMBOLS)), 18)
        result = self.execute()
        self.assertEqual([s['symbol'] for s in result['sources']], list(SOURCE_SYMBOLS))
        self.assertEqual(result['row_count'], 72)
        self.assertEqual(len(list((self.root / 'definitions/datasets').glob('*'))), 18)

    def test_unknown_historical_availability_original_ingestion_preserved(self):
        source = self.execute()['sources'][0]
        stored = read_source(self.root, source['pit_snapshot'])
        self.assertEqual(len(stored['observations']), 4)
        for row in stored['observations']:
            self.assertIsNone(row['available_at'])
            self.assertIsNone(row['source_vintage_at'])
            self.assertEqual(row['original_ingested_at'], '2026-09-06T21:03:46Z')
            self.assertEqual(row['reference_time'], row['observation_date'])
        self.assertEqual(source['readiness']['historical_replay'], 'blocked')
        self.assertEqual(source['metadata']['timing']['synchronization'], 'unverified')
        self.assertEqual(source['metadata']['price_basis'], 'unknown')

    def test_all_native_dates_retained_without_calendar_inference(self):
        result = inspect_source(self.legacy, self.audit['sources'][0])
        self.assertEqual([r['reference_time'] for r in result['observations']],
                         ['2020-01-02', '2020-01-03', '2020-01-06', '2020-01-07'])
        self.assertIsNone(result['metadata']['source_calendar'])

    def test_raw_bytes_referenced_not_copied(self):
        result = self.execute()
        source = result['sources'][0]
        from data.feature_store import FeatureStore
        store = FeatureStore(self.root)
        raw = store.resolve(source['raw_snapshot'])
        for member in raw['body']['members']:
            self.assertFalse((self.root / 'storage/payloads/sha256' / member['blob_sha256'][:2] /
                              (member['blob_sha256'] + '.json')).exists())
            self.assertEqual(sha(store.payload(member)), member['blob_sha256'])

    def test_no_legacy_modification(self):
        before = {str(p.relative_to(self.legacy)): sha(p.read_bytes()) for p in self.legacy.rglob('*') if p.is_file()}
        self.execute()
        after = {str(p.relative_to(self.legacy)): sha(p.read_bytes()) for p in self.legacy.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_idempotent_despite_new_migration_clock(self):
        first = self.execute()
        before = {str(p.relative_to(self.root)): sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        second = self.execute(migration_time='2026-10-10T10:00:00Z')
        after = {str(p.relative_to(self.root)): sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        self.assertTrue(second['reused'])
        self.assertEqual(first['completion_path'], second['completion_path'])
        self.assertEqual(second['migration_time'], first['migration_time'])
        self.assertEqual(before, after)

    def test_interrupt_then_resume_no_partial_complete_run(self):
        with self.assertRaises(InterruptedOnboarding):
            self.execute(interrupt_after='payloads')
        self.assertFalse(list((self.root / 'storage/catalog/onboarding/runs').glob('*.json')))
        self.assertFalse(any(json.loads(p.read_text()).get('body', {}).get('kind') == 'fx_source_snapshot'
                             for p in (self.root / 'storage/catalog/snapshots').glob('*/manifest.json')))
        result = self.execute()
        self.assertEqual(result['row_count'], 72)
        self.assertEqual(len(result['sources']), 18)

    def test_final_run_seal_only_after_all_sources(self):
        with self.assertRaises(InterruptedOnboarding):
            self.execute(interrupt_after='sources')
        self.assertFalse(list((self.root / 'storage/catalog/onboarding/runs').glob('*.json')))
        self.assertTrue(self.execute()['reused'])

    def test_no_extra_source_accepted(self):
        self.audit['sources'][0]['symbol'] = 'CNY/USD'
        self.audit_path.write_bytes(canonical(self.audit))
        with self.assertRaisesRegex(FXOnboardingError, 'exactly'):
            self.execute()

    def test_cny_cannot_satisfy_cnh_dependency(self):
        source = deepcopy(self.audit['sources'][4])
        source['quote_currency'] = 'CNY'
        with self.assertRaisesRegex(FXOnboardingError, 'direction'):
            inspect_source(self.legacy, source)

    def test_nonpositive_close_rejected(self):
        source = self.audit['sources'][0]
        rewrite_page(self.legacy, source, lambda rows: rows[3].update(value=0))
        with self.assertRaisesRegex(FXOnboardingError, 'positive'):
            inspect_source(self.legacy, source)

    def test_conflicting_duplicate_close_rejected(self):
        source = self.audit['sources'][0]
        rewrite_page(self.legacy, source, lambda rows: rows.append(dict(rows[3], value=999)))
        with self.assertRaisesRegex(FXOnboardingError, 'Conflicting'):
            inspect_source(self.legacy, source)

    def test_exact_duplicate_close_rejected(self):
        source = self.audit['sources'][0]
        rewrite_page(self.legacy, source, lambda rows: rows.append(dict(rows[3])))
        with self.assertRaisesRegex(FXOnboardingError, 'Duplicate'):
            inspect_source(self.legacy, source)

    def test_missing_historical_page_rejected(self):
        source = self.audit['sources'][0]
        extra = self.legacy / source['pages'][0]['directory']
        other = extra.parent / 'page=0002'
        shutil.copytree(extra, other)
        with self.assertRaisesRegex(FXOnboardingError, 'every stored historical page'):
            inspect_source(self.legacy, source)

    def test_changed_raw_bytes_rejected(self):
        source = self.audit['sources'][0]
        path = self.legacy / source['pages'][0]['raw_path']
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            inspect_source(self.legacy, source)

    def test_same_date_at_capture_rejected(self):
        source = self.audit['sources'][0]
        rewrite_page(self.legacy, source, lambda rows: rows[3].update(observation_date='2026-09-06'))
        with self.assertRaisesRegex(FXOnboardingError, 'Incomplete'):
            inspect_source(self.legacy, source)

    def test_batched_lineage_and_compressed_storage(self):
        source = self.execute()['sources'][0]
        stored = read_source(self.root, source['pit_snapshot'])
        self.assertEqual(len(stored['lineage']), 4)
        self.assertEqual(len(stored['manifest']['body']['lineage_members']), 1)
        self.assertEqual(stored['manifest']['body']['members'][0]['codec'], 'gzip_jsonl')
        for row, lineage in zip(stored['observations'], stored['lineage']):
            self.assertEqual(row['lineage'], lineage['lineage'])
            self.assertEqual(row['lineage_key'], lineage['source_row_content_sha256'])
            self.assertEqual(lineage['raw_field'], 'close')
        self.assertFalse(list((self.root / 'storage/catalog/lineage').glob('FXSOURCE_*')))

    def test_fresh_process_reads_persisted_rows(self):
        source = self.execute()['sources'][0]
        program = ('import json,sys; from data.fx_onboarding import read_source; '
                   'r=read_source(sys.argv[1],json.loads(sys.argv[2])); '
                   'print(json.dumps({"rows":len(r["observations"]),"first":r["observations"][0]["value"]}))')
        env = dict(os.environ, PYTHONPATH=str(PROJECT / 'src'))
        output = subprocess.check_output([sys.executable, '-c', program, str(self.root), json.dumps(source['pit_snapshot'])], env=env)
        self.assertEqual(json.loads(output), {'rows': 4, 'first': '1'})

    def test_snapshot_lineage_payload_tampering_rejected(self):
        source = self.execute()['sources'][0]
        stored = read_source(self.root, source['pit_snapshot'])
        member = stored['manifest']['body']['lineage_members'][0]
        p = self.root / 'storage/payloads/sha256' / member['blob_sha256'][:2] / (member['blob_sha256'] + '.bin')
        p.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            read_source(self.root, source['pit_snapshot'])


@unittest.skipUnless(os.environ.get('FX_ACTUAL_AUDIT'), 'Actual legacy audit path supplied only for integration run')
class FXActualLegacyAuditTests(unittest.TestCase):
    def test_all_18_actual_source_histories_reconcile(self):
        audit = json.loads(Path(os.environ['FX_ACTUAL_AUDIT']).read_text())
        counts = [len(inspect_source(audit['legacy_root'], s)['observations']) for s in audit['sources']]
        self.assertEqual(len(counts), 18)
        self.assertEqual(sum(counts), 145236)


if __name__ == '__main__':
    unittest.main()
