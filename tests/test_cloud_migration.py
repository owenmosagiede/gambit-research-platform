import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from cloud_migration import inventory, export, verify
from research.store import lock

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'source';self.root.mkdir()
        (self.root/'config').mkdir();(self.root/'config/research_execution.json').write_text('{"approved":true}')
        (self.root/'config/storage.local.json').write_text('{"local":"must not ship"}')
        (self.root/'src').mkdir();(self.root/'src/example.py').write_text('pass\n')
    def test_inventory_does_not_change_source_and_excludes_local_config(self):
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=inventory(self.root)
        self.assertEqual(result['status'],'inventory_only_not_a_consistent_backup')
        self.assertNotIn('config/storage.local.json',[e['path'] for e in result['entries']])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_export_refuses_live_worker_without_interruption(self):
        with lock(self.root,'research-worker-service'):
            with self.assertRaisesRegex(ValueError,'owned'):export(self.root,self.base/'export')
        self.assertFalse((self.base/'export').exists())
    def test_export_preserves_bytes_detects_corruption(self):
        result=export(self.root,self.base/'export');self.assertEqual(verify(self.base/'export',result),result['file_count'])
        (self.base/'export/src/example.py').write_text('altered')
        with self.assertRaisesRegex(ValueError,'mismatch'):verify(self.base/'export',result)
    def test_path_escape_symlinks_and_duplicates_rejected(self):
        (self.root/'src/escape').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError,'Symlink'):inventory(self.root)
        for path in ('../escape','/etc/passwd'):
            with self.assertRaisesRegex(ValueError,'Unsafe'):verify(self.root,{'entries':[{'path':path}]})
    def test_external_exact_bytes_relocated_without_changing_manifest(self):
        import hashlib
        data=b'legacy-evidence';sha=hashlib.sha256(data).hexdigest()
        folder=self.root/'storage/catalog/snapshots';folder.mkdir(parents=True)
        manifest=json.dumps({'members':[{'blob_sha256':sha,'format':'csv','byte_count':len(data)}]}).encode()
        (folder/'manifest.json').write_bytes(manifest)
        with patch('cloud_migration.FeatureStore.payload',return_value=data):
            result=export(self.root,self.base/'export')
        self.assertEqual(len(result['external_payloads']),1)
        self.assertEqual((self.base/'export/storage/catalog/snapshots/manifest.json').read_bytes(),manifest)
        self.assertEqual((self.base/f'export/storage/payloads/sha256/{sha[:2]}/{sha}.csv').read_bytes(),data)
        self.assertFalse((self.root/f'storage/payloads/sha256/{sha[:2]}/{sha}.csv').exists())
