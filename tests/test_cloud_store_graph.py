import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from verify_cloud_store import graph, feature_reference


class CloudGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'definitions').mkdir(); (self.root / 'config').mkdir()
        self.data = b'exact archived source bytes'; sha = hashlib.sha256(self.data).hexdigest()
        self.payload = self.root / f'storage/payloads/sha256/{sha[:2]}/{sha}.bin'
        self.payload.parent.mkdir(parents=True); self.payload.write_bytes(self.data)
        self.record = {'schema_version': '0.2.0', 'record_type': 'snapshot_manifest', 'id': 'SNAPSHOT_fixture', 'version': '1.0.0',
                       'members': [{'blob_sha256': sha, 'format': 'bin', 'byte_count': len(self.data)}]}
        (self.root / 'definitions/snapshot.json').write_text(json.dumps(self.record))
        (self.root / 'config/reference.json').write_text(json.dumps({'source': feature_reference(self.record)}))

    def test_exact_references_and_local_payload_pass_without_writes(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = graph(self.root)
        self.assertEqual(result['status'], 'PASS'); self.assertEqual(result['verified_payloads'], 1)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_missing_payload_never_uses_legacy_fallback(self):
        self.payload.unlink(); result = graph(self.root)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['errors'][0]['kind'], 'missing_local_payload')
        self.assertFalse(result['legacy_fallback_used'])

    def test_changed_bytes_and_wrong_exact_reference_fail(self):
        self.payload.write_bytes(b'wrong'); result = graph(self.root)
        self.assertEqual(result['errors'][0]['kind'], 'payload_checksum_or_size_mismatch')
        ref = feature_reference(self.record); ref['content_sha256'] = 'f' * 64
        (self.root / 'config/reference.json').write_text(json.dumps(ref))
        self.assertIn('unresolved_reference', {e['kind'] for e in graph(self.root)['errors']})

    def test_symlink_cannot_substitute_external_payload(self):
        self.payload.unlink(); self.payload.symlink_to(self.root / 'definitions/snapshot.json')
        with self.assertRaisesRegex(ValueError, 'escapes'): graph(self.root)
