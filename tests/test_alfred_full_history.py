"""Offline full-history integration checks; writes only isolated temporary copies."""
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from data import alfred_full_history as full
from data import alfred_pit as pilot
from data.alfred_onboarding import canonical, sha

ROOT=Path(__file__).resolve().parents[1]


def copy_file(source,root,relative):
    target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/relative,target)


def restore_acquisition(destination):
    """Use immutable published evidence when available, otherwise explicit staging."""
    completions=sorted((ROOT/'storage/catalog/pit_store/full_history/completions').glob('*.json'))
    if not completions:
        source=Path(os.environ.get('ALFRED_FULL_ACQUISITION','/private/tmp/alfred_full_work/acquisition'))
        if not (source/'bundle.json').exists():raise unittest.SkipTest('Full acquisition fixture unavailable')
        shutil.copytree(source,destination);return
    complete=json.loads(completions[-1].read_text());run=json.loads((ROOT/complete['run_path']).read_text())
    evidence=json.loads((ROOT/f"storage/catalog/onboarding/evidence/{run['acquisition_evidence']['id']}.json").read_text())
    payload=evidence['body']['payload'];data=json.loads((ROOT/f"storage/payloads/sha256/{payload['sha256'][:2]}/{payload['sha256']}.json").read_text())
    destination.mkdir();(destination/'bundle.json').write_bytes(canonical(data['bundle_index'])+b'\n')
    for name,receipt in data['saved_receipts'].items():
        target=destination/receipt['payload_path'];target.parent.mkdir(parents=True,exist_ok=True)
        digest=receipt['sha256'];target.write_bytes((ROOT/f'storage/payloads/sha256/{digest[:2]}/{digest}.json').read_bytes())
        (destination/(name+'.receipt.json')).write_bytes(canonical(receipt)+b'\n')


class FullHistoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='alfred_full_fixture_',dir='/private/tmp');cls.addClassCleanup(cls.temp.cleanup)
        cls.acquisition=Path(cls.temp.name)/'acquisition';restore_acquisition(cls.acquisition)
        cls.root=Path(cls.temp.name)/'research_platform';cls.root.mkdir()
        completion_path=next((ROOT/'storage/catalog/pit_store/full_history/completions').glob('SNAPSHOT_*.json'))
        published=json.loads(completion_path.read_text())
        run=json.loads((ROOT/published['run_path']).read_text())
        paths=run['record_paths']+run['payload_paths']+[published['run_path'],str(completion_path.relative_to(ROOT))]
        paths+=['specs/schemas/platform.schema.json','specs/schemas/onboarding.schema.json','specs/schemas/alfred_pit_rows.schema.json']
        paths+=['src/data/'+n for n in ['alfred_onboarding.py','alfred_pit.py','alfred_full_acquisition.py','alfred_full_history.py','pit_selection.py']]
        paths+=['tools/onboard_alfred_full_history.py','tools/materialize_alfred_pit.py']
        for relative in paths:copy_file(ROOT,cls.root,relative)
        if (cls.root/pilot.RUN).exists():raise AssertionError('Standalone fixture unexpectedly contains retired pilot')
        cls.complete=full.materialize(cls.root,cls.acquisition);cls.sid=cls.complete['pit_snapshot']['id']
        if cls.sid!=published['pit_snapshot']['id']:raise AssertionError('Repeat build changed existing full-history identity')

    def setUp(self):
        self.temp_case=tempfile.TemporaryDirectory(prefix='alfred_full_case_',dir='/private/tmp');self.addCleanup(self.temp_case.cleanup)
        self.root=Path(self.temp_case.name)/'research_platform';shutil.copytree(type(self).root,self.root)

    def test_full_coverage_preserves_periods_outside_pilot_and_original_cells(self):
        snapshot,rows,run=full.read_pit(self.root,self.sid)
        periods=sorted({r['observation_date'] for r in rows})
        self.assertLess(periods[0],'2018-01-01');self.assertGreater(periods[-1],'2018-12-01')
        self.assertEqual(len(periods),run['counts']['reference_months'])
        start=dt.date.fromisoformat(periods[0]);end=dt.date.fromisoformat(periods[-1])
        self.assertEqual(len(periods),(end.year-start.year)*12+end.month-start.month+1)
        raw=json.loads((self.root/full.snapshot_path(run['raw_snapshot']['id'])).read_text())
        self.assertEqual(len(raw['members']),2)
        self.assertEqual(len(periods),247)
        self.assertEqual(len(rows),1587)
        self.assertEqual({r['source_raw_blob_sha256'] for r in rows},{m['blob_sha256'] for m in raw['members']})
        for day,value in [('2018-02-02','26.74'),('2018-03-09','26.71')]:
            result=full.query(self.root,self.sid,day,'2018-01-01')
            self.assertEqual(result['observations'][0]['value'],value)
            self.assertNotIn('next_vintage_date',result['observations'][0])

    def test_before_archive_coverage_is_explicitly_unavailable(self):
        _,rows,_=full.read_pit(self.root,self.sid)
        earliest=min(r['vintage_date'] for r in rows);before=(dt.date.fromisoformat(earliest)-dt.timedelta(days=1)).isoformat()
        result=full.query(self.root,self.sid,before)
        self.assertEqual(result['archive_coverage_status'],'before_archive_coverage')
        self.assertEqual(result['observations'],[])
        first=full.query(self.root,self.sid,earliest)
        self.assertGreater(first['selected_count'],0)
        self.assertEqual(first['archive_coverage_status'],'within_captured_archive')

    def test_future_and_uncovered_observation_dates_rejected(self):
        _,_,run=full.read_pit(self.root,self.sid)
        future=(dt.date.fromisoformat(run['as_of_date'])+dt.timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):full.query(self.root,self.sid,future)
        with self.assertRaises(ValueError):full.query(self.root,self.sid,run['as_of_date'],'1900-01-01')

    def test_index_tampering_fails_then_rebuild_recovers(self):
        _,_,run=full.read_pit(self.root,self.sid);before=full.query(self.root,self.sid,run['as_of_date'])
        with closing(sqlite3.connect(self.root/full.INDEX)) as conn:
            conn.execute('UPDATE observations SET vintage_date=? WHERE rowid=(SELECT min(rowid) FROM observations)',('1700-01-01',));conn.commit()
        with self.assertRaises(ValueError):full.query(self.root,self.sid,run['as_of_date'])
        full.rebuild_index(self.root)
        self.assertEqual(full.query(self.root,self.sid,run['as_of_date']),before)

    def test_missing_raw_page_cannot_pass_as_complete(self):
        _,_,run=full.read_pit(self.root,self.sid)
        raw=json.loads((self.root/full.snapshot_path(run['raw_snapshot']['id'])).read_text());m=raw['members'][-1]
        (self.root/f"storage/payloads/sha256/{m['blob_sha256'][:2]}/{m['blob_sha256']}.json").unlink()
        with self.assertRaises((ValueError,OSError)):full.read_pit(self.root,self.sid)

    def test_repeat_build_preserves_all_immutable_files(self):
        def inventory():
            return {str(p.relative_to(self.root)):sha(p.read_bytes()) for base in ['definitions','storage'] for p in (self.root/base).rglob('*') if p.is_file() and p.suffix!='.sqlite' and 'temporary' not in p.parts}
        before=inventory();again=full.materialize(self.root,self.acquisition)
        self.assertEqual(again['pit_snapshot'],self.complete['pit_snapshot']);self.assertEqual(inventory(),before)

    def test_standalone_package_queries_and_rebuilds_without_retired_pilot(self):
        self.assertFalse((self.root/pilot.RUN).exists())
        self.assertFalse((self.root/pilot.INDEX).exists())
        self.assertEqual(list((self.root/'storage/catalog/pit_store/completions').glob('*.json')),[])
        before=full.query(self.root,self.sid,'2018-03-09','2018-01-01')
        (self.root/full.INDEX).unlink()
        full.rebuild_index(self.root)
        self.assertEqual(full.query(self.root,self.sid,'2018-03-09','2018-01-01'),before)
        self.assertEqual(before['observations'][0]['value'],'26.71')

    def test_repeat_build_rejects_mismatched_completion_without_changes(self):
        completion_path=next((self.root/'storage/catalog/pit_store/full_history/completions').glob('*.json'))
        completion=json.loads(completion_path.read_text())
        completion['run_sha256']='0'*64
        completion_path.write_bytes(canonical(completion)+b'\n')
        before={str(p.relative_to(self.root)):sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError,'completion does not match'):
            full.materialize(self.root,self.acquisition)
        self.assertEqual({str(p.relative_to(self.root)):sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()},before)

    def test_unpublished_bundle_cannot_recreate_retired_bootstrap_sample(self):
        acquisition=Path(self.temp_case.name)/'changed_acquisition'
        shutil.copytree(self.acquisition,acquisition)
        bundle=json.loads((acquisition/'bundle.json').read_text())
        member=bundle['request_manifest'][0]
        receipt_path=acquisition/(member['name']+'.receipt.json')
        receipt=json.loads(receipt_path.read_text())
        receipt['headers']['etag']='"synthetic-different-capture"'
        receipt_path.write_bytes(canonical(receipt)+b'\n')
        member['receipt_sha256']=sha(canonical(receipt))
        (acquisition/'bundle.json').write_bytes(canonical(bundle)+b'\n')
        before={str(p.relative_to(self.root)):sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError,'new versioned refresh'):
            full.materialize(self.root,acquisition)
        self.assertFalse((self.root/pilot.RUN).exists())
        self.assertEqual({str(p.relative_to(self.root)):sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()},before)

    def test_working_row_schema_does_not_redefine_published_history(self):
        expected=full.read_pit(self.root,self.sid)[1]
        (self.root/'specs/schemas/alfred_pit_rows.schema.json').write_text('{"not":{}}')
        self.assertEqual(full.read_pit(self.root,self.sid)[1],expected)


if __name__=='__main__':unittest.main()
