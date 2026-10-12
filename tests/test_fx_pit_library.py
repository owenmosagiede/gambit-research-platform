"""New source snapshots use the existing PIT metadata endpoint honestly."""
from pathlib import Path
import tempfile
import unittest

from api.pit_library import list_pit_library
from data.fx_onboarding import onboard
from data.feature_store import FeatureStore
from test_fx_onboarding import build_fixture,SOURCE_SYMBOLS


class FxPitLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fx_pit_library_')
        self.addCleanup(self.temp.cleanup)
        self.root,self.legacy,self.audit_path,_=build_fixture(Path(self.temp.name))
        self.imported=onboard(self.root,self.legacy,self.audit_path,migration_time='2026-10-09T10:00:00Z')

    def test_completed_sources_appear_with_unknown_vintages_not_alfred_claims(self):
        result=list_pit_library(self.root)
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['dataset_count'],18)
        self.assertEqual({item['series_id'] for item in result['datasets']},set(SOURCE_SYMBOLS))
        for dataset in result['datasets']:
            self.assertEqual(dataset['provider'],'Twelve Data')
            snapshot=dataset['snapshots'][0]
            self.assertEqual(snapshot['scope'],'retrospective_snapshot')
            self.assertEqual(snapshot['observation_count'],4)
            self.assertEqual(snapshot['vintage_count'],0)
            self.assertIsNone(snapshot['vintage_start']);self.assertIsNone(snapshot['vintage_end'])
            self.assertEqual(snapshot['readiness']['historical_replay'],'blocked')
            self.assertEqual(snapshot['captured_at'],'2026-09-06T21:03:46Z')
            self.assertEqual(snapshot['price_basis'],'unknown')

    def test_corrupt_source_payload_excluded_without_hiding_other_sources(self):
        store=FeatureStore(self.root)
        manifest=store.resolve(self.imported['sources'][0]['pit_snapshot'])
        member=manifest['body']['members'][0]
        path=self.root/f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.{member['format']}"
        path.write_bytes(path.read_bytes()+b'corrupt')
        result=list_pit_library(self.root)
        self.assertEqual(result['dataset_count'],17)
        self.assertEqual(len(result['issues']),1)
        self.assertNotIn(str(self.root),str(result['issues']))

    def test_reader_never_uses_alfred_adapters_for_fx_rows(self):
        from unittest.mock import patch
        with patch('api.pit_library.read_full',side_effect=AssertionError('Wrong source adapter')),patch('api.pit_library.read_pilot',side_effect=AssertionError('Wrong source adapter')):
            self.assertEqual(list_pit_library(self.root)['dataset_count'],18)


if __name__=='__main__':unittest.main()
