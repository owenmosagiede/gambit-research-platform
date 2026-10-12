"""Catalog reads do not scan observation bytes; exact data readers stay strict."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from api.pit_library import list_pit_library
from api.target_catalog import list_target_catalog
from data.feature_store import FeatureStore
import test_pit_library_api as pit_fixture
import test_fx_pit_library as fx_fixture
import test_fx_targets as target_fixture

class LibraryMetadataTests(unittest.TestCase):
    def test_alfred_metadata_is_pinned_and_payload_free(self):
        with TemporaryDirectory() as d:
            root=Path(d);marker=pit_fixture.collect_published_fixture(pit_fixture.ROOT,root)
            with patch.object(FeatureStore,'payload',side_effect=AssertionError('observation read')),patch('api.pit_library.read_full',side_effect=AssertionError('full replay')):
                result=list_pit_library(root,metadata_only=True)
            self.assertEqual(result['dataset_count'],1);self.assertEqual(result['issues'],[])
            item=result['datasets'][0]['snapshots'][0]
            self.assertEqual(item['observation_count'],247);self.assertEqual(item['verification_state'],'catalog_metadata_only')
            completion=root/pit_fixture.FULL_COMPLETIONS/(marker['pit_snapshot']['id']+'.json')
            corrupt=json.loads(completion.read_text());corrupt['counts']['reference_months']+=1;completion.write_text(json.dumps(corrupt))
            result=list_pit_library(root,metadata_only=True)
            self.assertEqual(result['dataset_count'],0);self.assertTrue(result['issues'])
    def test_fx_metadata_does_not_claim_payload_verification(self):
        fixture=fx_fixture.FxPitLibraryTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        with patch.object(FeatureStore,'payload',side_effect=AssertionError('payload read')):
            result=list_pit_library(fixture.root,metadata_only=True)
        self.assertEqual(result['dataset_count'],18);self.assertEqual(result['issues'],[])
        self.assertTrue(all(d['snapshots'][0]['verification_state']=='catalog_metadata_only' for d in result['datasets']))
    def test_target_catalog_uses_metadata_and_detail_still_rejects_corruption(self):
        fixture=target_fixture.FXTargetPersistenceTests();fixture.setUp();self.addCleanup(fixture.tearDown)
        outputs=fixture.build()
        with patch.object(FeatureStore,'payload',side_effect=AssertionError('payload read')):
            result=list_target_catalog(fixture.root)
        self.assertEqual(result['target_count'],2);self.assertEqual(result['issues'],[])
        self.assertTrue(all(t['verification_state']=='catalog_metadata_only' for t in result['targets']))
        output=outputs[0];from data.targets.service import read_materialization
        loaded=read_materialization(fixture.root,output['materialization']['id']);manifest=loaded['manifest']
        member=manifest['partitions'][0]
        path=fixture.root/f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.{member['format']}"
        path.write_bytes(path.read_bytes()+b'corruption')
        self.assertEqual(list_target_catalog(fixture.root)['target_count'],2)
        with self.assertRaises(Exception):read_materialization(fixture.root,manifest['id'])
