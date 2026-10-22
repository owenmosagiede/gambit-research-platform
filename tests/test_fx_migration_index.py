"""Planner equivalence and bounded inventory/serialization regression checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_fx_currency_migration as baseline
from data.fx_currency_migration import plan
from data.fx_migration_index import MigrationIndex,inventory
from data.fx_migration_manifest import chunks,manifest_digest,install_manifest
from data.transformations.identity import reference
from research.contracts import canonical,digest

path=Path(__file__).parent/'fixtures/migration_planner/legacy.py'
spec=importlib.util.spec_from_file_location('legacy_migration',path)
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)

class PlannerEquivalenceTests(baseline.CurrencyDeletionTests):
    # Every inherited ownership, corruption, drift and recovery test compares
    # the exact old/new manifests, including blockers, paths, hashes and bytes.
    def preview(self):
        expected=legacy.plan(self.root,reference(self.release))
        actual=plan(self.root,reference(self.release))
        self.assertEqual(expected,actual)
        return actual

class IndexTests(unittest.TestCase):
    def test_streaming_canonical_matches_scientific_contract(self):
        for value in [{'z':[1,2.5,None,True,'é'], 'a':{'nested':-0.0}}, {}, [], (1,'x')]:
            self.assertEqual(b''.join(chunks(value)),canonical(value))
            self.assertEqual(manifest_digest(value),digest(value))
        with self.assertRaises(ValueError):list(chunks(float('nan')))
        with self.assertRaises(ValueError):list(chunks({1:'bad'}))
    def test_inventory_never_parses_json_and_detects_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'definitions').mkdir()
            file=root/'definitions/a.json';file.write_bytes(b'{malformed')
            result=inventory(root)
            self.assertEqual(result['definitions/a.json']['sha256'],hashlib.sha256(file.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                with MigrationIndex(root):pass
            (root/'definitions/link').symlink_to(file)
            with self.assertRaisesRegex(ValueError,'symbolic'):inventory(root)
    def test_lazy_record_read_checks_frozen_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'definitions').mkdir();p=root/'definitions/a.json';p.write_text('{"id":"original"}')
            with MigrationIndex(root) as index:
                scratch=Path(index.temp.name)
                self.assertEqual(index.records['definitions/a.json']['id'],'original')
                p.write_text('{"id":"changed"}')
                with self.assertRaisesRegex(ValueError,'checksum'):index.records['definitions/a.json']
            self.assertFalse(scratch.exists())
    def test_atomic_manifest_is_identical_and_refuses_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'manifest.json';value={'sha256':'a'*64,'inventory':{'é':{'bytes':3}}}
            install_manifest(p,value);self.assertEqual(p.read_bytes(),canonical(value)+b'\n')
            install_manifest(p,value)
            with self.assertRaisesRegex(ValueError,'conflict'):install_manifest(p,{})
            self.assertEqual(p.read_bytes(),canonical(value)+b'\n')
