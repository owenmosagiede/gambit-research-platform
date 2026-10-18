"""Real immutable publication/read/restore with bounded synthetic prices only."""
from copy import deepcopy
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from data.feature_store import FeatureStore, PublicationError, record_path
from data.fx_feature_store import read_fx_materialization
from data.lineage_packs import CATALOG, INDEX, PackedLineage, install_records, storage_mode
from data.transformations.identity import reference, canonical_bytes
from data.catalog_reads import catalog_reads
import test_fx_feature_store as fixture


class LineagePackTests(unittest.TestCase):
    setUp = fixture.FXFeatureStoreTests.setUp
    tearDown = fixture.FXFeatureStoreTests.tearDown
    install = fixture.FXFeatureStoreTests.install
    load_price = fixture.FXFeatureStoreTests.load_price
    build_recipe = fixture.FXFeatureStoreTests.build_recipe
    prepare = fixture.FXFeatureStoreTests.prepare

    def packed(self, **kwargs):
        with patch.dict(os.environ, GAMBIT_FX_LINEAGE_STORAGE='packed_v1'):
            return self.prepare(**kwargs)

    def item(self, saved):
        return read_fx_materialization(self.root, saved['materialization']['id'])

    def rows(self, saved):
        store = FeatureStore(self.root)
        return [store.resolve(r) for r in self.item(saved)['manifest']['lineage']]

    def test_loose_packed_identical_ids_bytes_and_numerical_replay(self):
        # Clone before publication, so both stores compute the same scientific
        # records independently with only the physical write mode different.
        clone = self.root / 'clone'
        shutil.copytree(self.root, clone, ignore=shutil.ignore_patterns('clone'))
        loose = self.prepare()
        expected = self.item(loose)
        original = self.root
        try:
            self.root = clone
            packed = self.packed()
            actual = self.item(packed)
            self.assertEqual(packed['materialization'], loose['materialization'])
            self.assertEqual(actual, expected)
            self.assertEqual(len(list(clone.glob(CATALOG+'/*.json'))), 1)
            self.assertEqual(len(list(clone.glob('storage/catalog/lineage/*/manifest.json'))), 1)
            self.assertTrue(self.packed()['reused'])
        finally:
            self.root = original

    def test_all_53_momentum_configurations_replay_identically(self):
        import math
        from data.fx_feature_recipes import configurations, build_fx_feature
        from data.fx_feature_store import _dates
        from data.transformations.registry import Registry
        from data.transformations.identity import digest
        from test_feature_store import _copy_metadata_closure
        names = ('change_diff','momentum_skip_diff','smooth_ew_change','trend_ema_distance',
                 'trend_ma_distance','trend_slope','trend_slope_tstat','volscale_diff','volscale_trend')
        registry = Registry(fixture.PROJECT)
        _copy_metadata_closure(self.root,[registry.operator('TR_BASE_'+n) for n in names])
        variants = [v for v in configurations(registry) if v['operator']['id'] in {'TR_BASE_'+n for n in names}]
        self.assertEqual(len(variants),53)
        self.days = list(_dates('2022-01-03','2024-04-30'))
        template = deepcopy(self.prices[0]); self.prices=[]
        for i, day in enumerate(self.days):
            if i == len(self.days)-7: continue
            row = dict(template,reference_time=day,value=str(100+i*.1+3*math.sin(i*.3)))
            row.pop('id'); row['id']='FXPRICE_'+digest(row);self.prices.append(row)
        local = Registry(self.root)
        features=[]
        for v in variants:
            feature=build_fx_feature(self.root,{'instrument_id':'EURUSD','price_snapshot':self.snapshot},v,registry=local)
            self.store.install_record(feature);features.append(feature)
        with tempfile.TemporaryDirectory() as folder:
            clone=Path(folder)/'packed';shutil.copytree(self.root,clone)
            original=self.root
            for feature in features:
                with self.subTest(operator=feature['body']['recipe']['steps'][-1]['operator']['id'],feature=feature['id']):
                    loose=self.prepare(feature,start=self.days[-12])
                    expected=self.item(loose)
                    try:
                        self.root=clone
                        packed=self.packed(feature=feature,start=self.days[-12])
                        self.assertEqual(packed['materialization'],loose['materialization'])
                        self.assertEqual(self.item(packed),expected)
                    finally: self.root=original

    def test_materialization_catalog_reads_do_not_retain_row_lineage_arrays(self):
        saved=self.packed();store=FeatureStore(self.root)
        binding=saved['materialization'];first=store.resolve(binding)
        self.assertTrue(first['lineage'])
        self.assertFalse(any(k[0].startswith('MATERIALIZATION_') for k in store._resolved))
        first['lineage'].clear()
        self.assertTrue(store.resolve(binding)['lineage'])
        path=store.path(record_path(store.resolve(binding)))
        value=json.loads(path.read_text());value['semantic_content_sha256']='0'*64
        path.write_text(json.dumps(value))
        with self.assertRaises(PublicationError):store.resolve(binding)

    def test_resumption_inventory_keeps_locators_and_checks_scope_boundaries(self):
        spec=importlib.util.spec_from_file_location('momentum_operator',fixture.PROJECT/'tools/prepare_momentum_population.py')
        operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
        saved=self.packed();manifest=self.item(saved)['manifest'];fid=self.feature['id']
        selected={fid:{'historical_feature':reference(self.feature),'instrument_id':'EURUSD','source_snapshot':self.snapshot}}
        kwargs=dict(root=self.root,selected=selected,batch=manifest['input_key']['batch_policy'],
            cutoff=manifest['input_key']['knowledge_cutoff'],starts={'EURUSD':self.days[0]},end='2024-05-01',boundaries={'EURUSD':[]})
        self.assertEqual(operator.inventory_candidates(**kwargs),{fid:[manifest['id']]})
        kwargs['boundaries']={'EURUSD':[self.days[20]]}
        self.assertEqual(operator.inventory_candidates(**kwargs),{})
        path=self.store.path(record_path(manifest));path.parent.rename(path.parent.with_name('MATERIALIZATION_'+'0'*64))
        with self.assertRaisesRegex(RuntimeError,'path differs'):operator.inventory_candidates(**kwargs)

    def test_missing_corrupt_and_incomplete_indexes_recover(self):
        saved = self.packed(start=self.days[40])
        expected = self.item(saved)
        index = self.root/INDEX
        for damage in ('delete', 'garbage', 'missing_row'):
            with self.subTest(damage=damage):
                if damage == 'delete': index.unlink()
                elif damage == 'garbage': index.write_bytes(b'not sqlite')
                else:
                    with closing(sqlite3.connect(index)) as db: db.execute('DELETE FROM records'); db.commit()
                self.assertEqual(self.item(saved), expected)

    def test_interrupted_publication_retries_and_never_exposes_partial_output(self):
        for point in ('pack_payload', 'pack_catalog', 'pack_index', 'payloads'):
            with self.subTest(point=point):
                start = self.days[40 + ('pack_payload','pack_catalog','pack_index','payloads').index(point)]
                before = set(self.root.glob('storage/catalog/feature_store/*/manifest.json'))
                with self.assertRaisesRegex(PublicationError, 'interruption'):
                    self.packed(start=start, fail_at=point)
                self.assertEqual(set(self.root.glob('storage/catalog/feature_store/*/manifest.json')), before)
                self.assertFalse(self.packed(start=start)['reused'])
                self.assertTrue(self.packed(start=start)['reused'])

    def test_new_pack_after_catalog_only_crash_keeps_previous_records(self):
        with self.assertRaisesRegex(PublicationError, 'interruption'):
            self.packed(start=self.days[40], fail_at='pack_catalog')
        orphan = json.loads(next(self.root.glob(CATALOG+'/*.json')).read_text())
        self.packed(start=self.days[50])
        for binding in orphan['references']:
            self.assertEqual(reference(FeatureStore(self.root).resolve(binding)), binding)

    def test_payload_catalog_and_locator_tampering_fail_closed(self):
        saved = self.packed(start=self.days[40]); self.item(saved)
        catalog_path = next(self.root.glob(CATALOG+'/*.json'))
        catalog_bytes = catalog_path.read_bytes(); catalog = json.loads(catalog_bytes)
        member = catalog['payload']
        payload = self.root/f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.bin"
        original = payload.read_bytes()
        payload.write_bytes(bytes([original[0] ^ 1])+original[1:])
        with self.assertRaises(ValueError): self.item(saved)
        payload.write_bytes(original)
        catalog['raw_bytes'] += 1; catalog_path.write_text(json.dumps(catalog))
        with self.assertRaises(ValueError): self.item(saved)
        catalog_path.write_bytes(catalog_bytes)
        with closing(sqlite3.connect(self.root/INDEX)) as db:
            db.execute("UPDATE records SET hash=?", ('0'*64,)); db.commit()
        with self.assertRaisesRegex(PublicationError, 'conflicts'): self.item(saved)

    def test_loose_conflict_not_hidden_by_packed_record(self):
        saved = self.packed(start=self.days[40]); row = self.rows(saved)[0]
        bad = deepcopy(row); bad['body']['prefix_count'] += 1
        path = self.root/record_path(row); path.parent.mkdir(parents=True)
        path.write_bytes(canonical_bytes(bad)+b'\n')
        with self.assertRaisesRegex(PublicationError, 'Conflicting'): FeatureStore(self.root).resolve(reference(row))

    def test_copy_restore_without_index_preserves_all_lineage_and_observations(self):
        saved = self.packed(start=self.days[40]); expected = self.item(saved)
        spec = importlib.util.spec_from_file_location('packed_backup', Path(__file__).resolve().parents[1]/'deploy/backup_cloud.py')
        backup = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup)
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp)/'restored'
            backup.copy_tree(self.root, clone)
            # A missing derived index is sufficient for independent recovery.
            (clone/INDEX).unlink(missing_ok=True)
            backup.seal(clone); backup.verify(clone)
            original = self.root
            try:
                self.root = clone
                self.assertEqual(self.item(saved), expected)
            finally: self.root = original

    def test_ui_cache_tracks_packs_and_detects_mutation(self):
        saved = self.packed(start=self.days[40]); refs = self.item(saved)['manifest']['lineage']
        with catalog_reads(self.root) as deps:
            reader = PackedLineage(FeatureStore(self.root))
            reader.resolve(refs[0]); reader.resolve(refs[1])
        self.assertTrue(deps.unchanged())
        catalog = next(self.root.glob(CATALOG+'/*.json'))
        catalog.write_bytes(catalog.read_bytes()+b' ')
        self.assertFalse(deps.unchanged())

    def test_concurrent_index_recovery_and_new_publication(self):
        saved = self.packed(start=self.days[40]); refs = self.item(saved)['manifest']['lineage']
        (self.root/INDEX).unlink()
        def read(binding): return reference(FeatureStore(self.root).resolve(binding))
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(read, refs[:8])), refs[:8])

    def test_competing_publishers_and_exact_duplicates_are_idempotent(self):
        saved=self.prepare(start=self.days[40]);records=self.rows(saved)
        def publish(_):
            store=FeatureStore(self.root)
            with store.writer(): return install_records(store,records)
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(publish,range(2)))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(len(list(self.root.glob(CATALOG+'/*.json'))),1)
        for row in records:
            self.assertEqual(FeatureStore(self.root).resolve(reference(row)),row)

    def test_truncated_and_oversized_decompression_are_rejected(self):
        import gzip,hashlib
        from data.lineage_packs import _records,MAX_BYTES
        from data.transformations.identity import digest
        saved=self.packed(start=self.days[40]);self.item(saved)
        catalog=json.loads(next(self.root.glob(CATALOG+'/*.json')).read_text())
        member=catalog['payload']
        original=(self.root/f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.bin").read_bytes()
        for data in (original[:-5],gzip.compress(b'x'*(MAX_BYTES+1),mtime=0)):
            bad=deepcopy(catalog)
            bad['payload']=self.store.io.blob(data,'bin','fx_row_lineage_pack',len(bad['references']))
            key=digest(bad);self.store.io.install(f'{CATALOG}/{key}.json',canonical_bytes(bad)+b'\n')
            with self.assertRaisesRegex(PublicationError,'uncompressed'):_records(self.store,key)

    def test_unknown_mode_fails_and_default_is_loose(self):
        with patch.dict(os.environ, {}, clear=True): self.assertEqual(storage_mode(), 'loose')
        with patch.dict(os.environ, GAMBIT_FX_LINEAGE_STORAGE='typo'):
            with self.assertRaisesRegex(PublicationError, 'unknown'): self.prepare()

    def test_bounded_publication_rejects_wrong_record_and_oversized_batch(self):
        with self.assertRaises(ValueError): install_records(self.store,[self.feature])
        with self.assertRaisesRegex(PublicationError, 'batch size'): install_records(self.store,[{}]*1025)
