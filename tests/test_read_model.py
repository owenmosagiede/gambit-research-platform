"""Real immutable fixtures; source preservation, failure and query isolation."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from read_model.projector import build, source_read_only
from read_model.query import page, detail, InvalidQuery
from read_model.storage import Unavailable, CursorExpired, current, connect, freshness
from runtime.research_jobs import ResearchJobs
from research.store import lock
from test_research_runtime import Adapter, KernelSpy, intent, profile


class ReadModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve(); self.root=self.base/'research'; self.output=self.base/'serving'
        (self.root/'config').mkdir(parents=True)
        (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        self.jobs=ResearchJobs(self.root,adapter=Adapter(),kernels=KernelSpy())
        self.addCleanup(self.jobs.close)

    def submit(self, direction='POSITIVE'):
        request=intent(mode='TS'); request['expected_direction']=direction
        self.jobs.submit(request); return request['request_id']

    def files(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_backfill_matches_queue_and_preserves_every_source_byte(self):
        first=self.submit(); second=self.submit('NEGATIVE')
        from api.experiment_views import list_experiments
        expected=list_experiments(self.jobs)
        before=self.files()
        with lock(self.root,'research-writer'):
            result=build(self.root,self.output)
        self.assertEqual(before,self.files())
        value=page(self.output,'queue')
        self.assertEqual(result['issue_count'],0)
        self.assertEqual([r['job']['request_id'] for r in value['items']], [r['job']['request_id'] for r in expected['items']])
        self.assertEqual([r['queue_position'] for r in value['items']],[1,2])
        self.assertEqual(value['total'],2)
        self.assertEqual(detail(self.output,'experiment',second)['record']['intent']['expected_direction'],'NEGATIVE')

    def test_incremental_events_and_alias_without_duplicate_experiments(self):
        rid=self.submit(); first=build(self.root,self.output)
        second=build(self.root,self.output)
        self.assertEqual(second['extraction']['rebuilt'],{})
        self.jobs._update(rid,status='p1',stage='P1')
        third=build(self.root,self.output)
        self.assertEqual(third['extraction']['rebuilt']['experiment'],1)
        self.assertEqual(page(self.output,'queue')['items'][0]['job']['status'],'p1')
        import uuid
        alias=str(uuid.uuid4()); self.jobs.submit(dict(self.jobs._submission(rid)['intent'],request_id=alias))
        fourth=build(self.root,self.output)
        self.assertEqual(fourth['counts']['experiments'],1); self.assertEqual(fourth['counts']['aliases'],1)
        self.assertEqual(detail(self.output,'experiment',alias)['record']['job']['request_id'],rid)

    def test_pagination_pins_old_generation_during_new_publication(self):
        self.submit(); self.submit('NEGATIVE'); build(self.root,self.output)
        first=page(self.output,'queue',{'limit':'1'})
        rid=first['items'][0]['job']['request_id']; self.jobs._update(rid,status='p1',stage='P1')
        build(self.root,self.output)
        second=page(self.output,'queue',{'limit':'1','cursor':first['next_cursor']})
        self.assertEqual(first['freshness']['generation'],second['freshness']['generation'])
        self.assertNotEqual(rid,second['items'][0]['job']['request_id'])
        with self.assertRaises(InvalidQuery): page(self.output,'queue',{'limit':'2','cursor':first['next_cursor']})
        (self.output/('generation-'+first['freshness']['generation']+'.sqlite')).unlink()
        with self.assertRaises(CursorExpired): page(self.output,'queue',{'limit':'1','cursor':first['next_cursor']})

    def test_immutable_tamper_with_restored_mtime_revokes_old_pages(self):
        rid=self.submit(); build(self.root,self.output)
        path=self.jobs._submission_path(rid); stat=path.stat()
        data=path.read_bytes(); path.write_bytes(data.replace(b'POSITIVE',b'NEGATIVE'))
        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.assertRaises(Unavailable): build(self.root,self.output)
        with self.assertRaises(Unavailable): page(self.output,'queue')
        # A failed refresh cannot simply overwrite the original checksum baseline.
        with self.assertRaises(Unavailable): build(self.root,self.output)

    def test_failed_publish_keeps_previous_generation(self):
        self.submit(); first=build(self.root,self.output)
        for stage in ('database','manifest'):
            with self.assertRaises(RuntimeError): build(self.root,self.output,fail_at=stage)
            self.assertEqual(page(self.output,'queue')['freshness']['generation'],first['generation'])
        with self.assertRaises(OSError): build(self.root,self.output,max_bytes=1)
        self.assertEqual(page(self.output,'queue')['total'],1)

    def test_production_sized_generation_streams_hashes_and_preserves_sources(self):
        from read_model.extract import Extractor
        from read_model.storage import MAX_DATABASE_BYTES, MAX_DIRECTORY_BYTES
        self.submit(); before=self.files()
        extract=Extractor.run; read_bytes=Path.read_bytes
        def with_padding(extractor):
            result=extract(extractor)
            # SQLite's zero-blob writes a realistic-sized derived file without
            # manufacturing production research or a 300 MiB Python allocation.
            extractor.db.execute('CREATE TABLE IF NOT EXISTS capacity_fixture(value BLOB)')
            if not extractor.db.execute('SELECT 1 FROM capacity_fixture').fetchone():
                extractor.db.execute('INSERT INTO capacity_fixture VALUES(zeroblob(?))',(300*1024*1024,))
            return result
        def forbid_whole_database_read(path):
            if path.suffix=='.sqlite': raise AssertionError('Publisher loaded entire database into memory')
            return read_bytes(path)
        with patch.object(Extractor,'run',with_padding), patch.object(Path,'read_bytes',forbid_whole_database_read):
            first=build(self.root,self.output)
            second=build(self.root,self.output)
            self.assertGreater(first['database_bytes'],256*1024*1024)
            self.assertLess(second['database_bytes'],MAX_DATABASE_BYTES)
            self.assertEqual(first['projection_sha256'],second['projection_sha256'])
            self.assertEqual(second['extraction']['rebuilt'],{})
            self.assertEqual(page(self.output,'queue')['total'],1)
            with patch('read_model.projector.MAX_DATABASE_BYTES',256*1024*1024):
                with self.assertRaisesRegex(OSError,'database_limit=268435456'):
                    build(self.root,self.output)
            self.assertEqual(current(self.output)[1]['generation'],second['generation'])
        self.assertEqual(before,self.files())
        self.assertGreaterEqual(MAX_DIRECTORY_BYTES,3*MAX_DATABASE_BYTES)

    def test_large_provenance_pages_are_bounded_without_losing_rows(self):
        from read_model.extract import Extractor
        from read_model.storage import encoded
        from read_model.query import MAX_RESPONSE_BYTES, PAGE_PAYLOAD_BYTES
        self.submit();before=self.files();extract=Extractor.run
        def large_rows(extractor):
            result=extract(extractor)
            # Query fixture sized from the real 160 KB provenance record. The
            # authoritative experiment stays untouched; only derived rows vary.
            template=json.loads(extractor.db.execute('SELECT value FROM experiments LIMIT 1').fetchone()[0])
            extractor.db.execute('DELETE FROM experiments')
            for number in range(60):
                row=json.loads(encoded(template));rid='fixture-'+str(number).zfill(3)
                row['job'].update(request_id=rid,status='queued',created_at='2026-01-01T00:00:00Z',queued_at='2026-01-01T00:00:00Z')
                row['provenance']={'complete_fixture_metadata':'x'*(160*1024)}
                extractor.db.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?)',
                    (rid,'queued',row['job']['queued_at'],row['job']['created_at'],'recipe','scope','POSITIVE','fixture',encoded(row)))
            return result
        with patch.object(Extractor,'run',large_rows):build(self.root,self.output)
        found=[];positions=[];query={'limit':'50'};pages=0
        while True:
            statements=[]
            def traced(path):
                db=connect(path);db.set_trace_callback(statements.append);return db
            with patch('read_model.query.connect',traced):
                value=page(self.output,'queue',query)
            pages+=1
            self.assertLessEqual(len(encoded(value).encode()),MAX_RESPONSE_BYTES)
            self.assertTrue(value['items']);self.assertEqual(value['total'],60)
            self.assertLess(len(value['items']),50)
            self.assertLess(sum(len(encoded(r).encode()) for r in value['items']),PAGE_PAYLOAD_BYTES)
            # Provenance is fetched only for served rows and at most one row
            # that discovers the byte boundary, never for the full sorted set.
            payload_reads=[s for s in statements if s.startswith('SELECT value FROM experiments')]
            self.assertLessEqual(len(payload_reads),len(value['items'])+1)
            self.assertTrue(all(' WHERE id=' in s for s in payload_reads))
            self.assertFalse(any(s.startswith('SELECT value,') for s in statements))
            for row in value['items']:
                found.append(row['job']['request_id']);positions.append(row['queue_position'])
                self.assertEqual(row['provenance']['complete_fixture_metadata'],'x'*(160*1024))
            if value['next_cursor'] is None:break
            query={'limit':'50','cursor':value['next_cursor']}
            self.assertLess(pages,20,'Byte-limited cursor failed to advance')
        self.assertEqual(found,['fixture-'+str(n).zfill(3) for n in range(60)])
        self.assertEqual(positions,list(range(1,61)))
        self.assertEqual(before,self.files())

    def test_healthy_publication_handoff_keeps_the_verified_generation_readable(self):
        import read_model.storage as storage
        from read_model.query import snapshot
        self.submit();meta=build(self.root,self.output)
        original=storage.read_document;changed=[]
        def publishing(path,*args,**kwargs):
            if path.name.startswith('generation-') and not changed:
                changed.append(True);storage.atomic(self.output,'status.json',{'unavailable':False,'refresh':'healthy'})
            return original(path,*args,**kwargs)
        with patch.object(storage,'read_document',publishing):
            self.assertEqual(storage.current(self.output)[1]['generation'],meta['generation'])
        with snapshot(self.output) as (db,pinned):
            storage.atomic(self.output,'status.json',{'unavailable':False,'refresh':'another'})
            self.assertEqual(pinned['generation'],meta['generation'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM experiments').fetchone()[0],1)

    def test_publication_handoff_never_accepts_revocation_or_unstable_status(self):
        import read_model.storage as storage
        from read_model.query import snapshot
        self.submit();build(self.root,self.output)
        original=storage.read_document;changed=[]
        def revoking(path,*args,**kwargs):
            if path.name.startswith('generation-') and not changed:
                changed.append(True);storage.atomic(self.output,'status.json',{'unavailable':True})
            return original(path,*args,**kwargs)
        with patch.object(storage,'read_document',revoking):
            with self.assertRaisesRegex(Unavailable,'verification failed'):storage.current(self.output)
        storage.atomic(self.output,'status.json',{'unavailable':False})
        with self.assertRaisesRegex(Unavailable,'verification failed'):
            with snapshot(self.output):storage.atomic(self.output,'status.json',{'unavailable':True})
        with patch.object(storage,'read_document',side_effect=storage.DocumentChanged('atomic replacement')) as read:
            with self.assertRaisesRegex(Unavailable,'did not stabilize'):storage.verified_status(self.output)
            self.assertEqual(read.call_count,3)
        with patch.object(storage,'read_document',side_effect=[storage.DocumentChanged('atomic replacement'),{'unavailable':True}]) as read:
            with self.assertRaisesRegex(Unavailable,'verification failed'):storage.verified_status(self.output)
            self.assertEqual(read.call_count,2)
        with patch.object(storage,'read_document',side_effect=[storage.DocumentChanged('atomic replacement'),{'unavailable':False}]) as read:
            storage.verified_status(self.output);self.assertEqual(read.call_count,2)
        with patch.object(storage,'read_document',side_effect=[storage.DocumentChanged('atomic replacement'),{'generation':'new'}]) as read:
            self.assertEqual(storage.published_pointer(self.output),{'generation':'new'})
            self.assertEqual(read.call_count,2)
        with patch.object(storage,'read_document',side_effect=storage.DocumentChanged('atomic replacement')) as read:
            with self.assertRaisesRegex(Unavailable,'pointer did not stabilize'):storage.published_pointer(self.output)
            self.assertEqual(read.call_count,3)

    def test_source_guard_blocks_writes_locks_and_payloads(self):
        (self.root/'storage/payloads').mkdir(parents=True)
        payload=self.root/'storage/payloads/test'; payload.write_text('secret')
        with source_read_only(self.root):
            with self.assertRaises(PermissionError): (self.root/'oops').write_text('bad')
            with self.assertRaises(PermissionError): payload.read_bytes()
            with self.assertRaises(PermissionError):
                with lock(self.root,'research-writer'): pass
        self.assertFalse((self.root/'oops').exists())

    def test_query_does_not_open_research_or_rebuild_when_missing(self):
        self.submit(); build(self.root,self.output)
        original=Path.open
        def guarded(path,*args,**kwargs):
            if path.resolve().is_relative_to(self.root): raise AssertionError('HTTP read reached research storage')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',guarded), patch('read_model.projector.build',side_effect=AssertionError('HTTP rebuild')):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results=list(pool.map(lambda _:page(self.output,'queue'),range(100)))
            self.assertTrue(all(r['total']==1 for r in results))
        path,_=current(self.output); path.unlink()
        with self.assertRaises(Unavailable): page(self.output,'queue')

    def test_freshness_and_cursor_queries_fail_closed(self):
        self.submit(); meta=build(self.root,self.output)
        self.assertEqual(freshness(meta,now=meta['observed_epoch']+61)['state'],'delayed')
        self.assertEqual(freshness(meta,now=meta['observed_epoch']+301)['state'],'stale')
        self.assertEqual(freshness(meta,now=meta['observed_epoch']-20)['state'],'unknown')
        for q in ({'limit':'101'},{'cursor':'../../bad'},{'from':'nonsense'},{'search':'x'*300}):
            with self.assertRaises(InvalidQuery): page(self.output,'ledger',q)

    def test_read_only_sql_and_no_research_root_destination(self):
        self.submit(); build(self.root,self.output); path,_=current(self.output)
        db=connect(path)
        try:
            import sqlite3
            with self.assertRaises(sqlite3.OperationalError): db.execute('DELETE FROM experiments')
        finally: db.close()
        with self.assertRaises(ValueError): build(self.root,self.root/'serving')

    def test_event_gap_is_an_issue_not_success(self):
        rid=self.submit(); self.jobs._update(rid,status='p1')
        path=next(p for p in (self.root/'storage/catalog/attempts').glob('*/events/RESEVENT_*.json') if json.loads(p.read_text())['sequence']==0)
        path.unlink(); result=build(self.root,self.output)
        self.assertGreater(result['issue_count'],0)
        self.assertEqual(page(self.output,'queue')['total'],0)

    def test_new_unattributed_bad_event_invalidates_cached_experiments(self):
        self.submit();build(self.root,self.output)
        directory=self.root/'storage/catalog/attempts/invalid/events'
        directory.mkdir(parents=True)
        (directory/('RESEVENT_'+'0'*64+'.json')).write_text('{')
        value=build(self.root,self.output)
        self.assertGreater(value['issue_count'],0)
        self.assertEqual(page(self.output,'queue')['total'],0)

    def test_publication_files_are_readable_by_separate_serving_group(self):
        self.submit();value=build(self.root,self.output)
        import stat
        for name in ('current.json','status.json','generation-'+value['generation']+'.json'):
            self.assertEqual(stat.S_IMODE((self.output/name).stat().st_mode),0o640)
        path,_=current(self.output)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o440)

    def test_expensive_sql_is_interrupted_within_the_request_budget(self):
        import sqlite3
        from read_model.query import snapshot
        self.submit();build(self.root,self.output)
        with patch('read_model.query.time.monotonic',side_effect=[0,3]):
            with snapshot(self.output) as (db,_):
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT sum(x) FROM n').fetchone()

    def test_space_pressure_expires_old_cursor_but_preserves_current_and_previous(self):
        from read_model.projector import cleanup
        from read_model.storage import MAX_DATABASE_BYTES
        self.submit();generations=[build(self.root,self.output)['generation'] for _ in range(4)]
        cleanup(self.output,max_bytes=MAX_DATABASE_BYTES)
        self.assertTrue((self.output/('generation-'+generations[-1]+'.sqlite')).exists())
        self.assertTrue((self.output/('generation-'+generations[-2]+'.sqlite')).exists())
        with self.assertRaises(CursorExpired):current(self.output,generations[0])
        self.assertEqual(page(self.output,'queue')['total'],1)

    def test_completed_partial_and_queued_research_survive_projection_and_failure(self):
        completed=self.submit();self.jobs.run_pending_once()
        queued=self.submit('NEGATIVE')
        before=self.files();build(self.root,self.output)
        self.assertEqual(before,self.files())
        self.assertEqual(detail(self.output,'experiment',completed)['record']['job']['status'],'succeeded')
        self.assertEqual(detail(self.output,'experiment',queued)['record']['job']['status'],'queued')
        self.assertEqual(page(self.output,'ledger')['total'],1)
        with self.assertRaises(RuntimeError):build(self.root,self.output,fail_at='database')
        self.assertEqual(before,self.files())
        self.assertEqual(len(self.jobs._read_job(completed)['results']),5)

    def test_append_during_publication_does_not_restart_or_mix_event_prefix(self):
        rid=self.submit()
        from read_model.extract import Extractor
        original=Extractor.files
        advanced=[]
        def captured(extractor,pattern):
            paths=original(extractor,pattern)
            if 'events/RESEVENT_' in pattern and not advanced:
                # A genuinely separate writer remains free to append while the
                # reader verifies its captured, finite prefix.
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(self.jobs._update,rid,status='p1',stage='P1').result()
                advanced.append(True)
            return paths
        with patch.object(Extractor,'files',captured):build(self.root,self.output)
        self.assertEqual(page(self.output,'queue')['items'][0]['job']['status'],'queued')
        build(self.root,self.output)
        self.assertEqual(page(self.output,'queue')['items'][0]['job']['status'],'p1')

    def test_reader_pins_connection_across_pointer_swap(self):
        self.submit(); first=build(self.root,self.output)
        from read_model.query import snapshot
        with snapshot(self.output) as (db,manifest):
            second=build(self.root,self.output)
            self.assertEqual(manifest['generation'],first['generation'])
            self.assertEqual(json.loads(db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0]),first['generation'])
        self.assertEqual(page(self.output,'queue')['freshness']['generation'],second['generation'])

    def test_missing_receipt_and_new_receipt_refresh_without_repair(self):
        rid=self.submit();from runtime.experiment_identity import IdentityIndex
        index=IdentityIndex(self.jobs);path=index.base/'receipts'/ (rid+'.json');raw=path.read_bytes();path.unlink()
        before=self.files();build(self.root,self.output);self.assertEqual(before,self.files())
        self.assertTrue(page(self.output,'queue')['items'][0]['job']['submission_receipt_pending'])
        path.write_bytes(raw);build(self.root,self.output)
        self.assertIn('submission_receipt',page(self.output,'queue')['items'][0]['job'])

    def test_symlink_source_and_derived_tamper_fail_closed(self):
        rid=self.submit();build(self.root,self.output)
        source=self.jobs._submission_path(rid);other=self.base/'original';source.rename(other);source.symlink_to(other)
        with self.assertRaises(Unavailable):build(self.root,self.output)
        with self.assertRaises(Unavailable):page(self.output,'queue')

    def test_read_model_does_not_change_execution_fingerprint(self):
        import hashlib
        from runtime import research_jobs
        repo=Path(__file__).resolve().parents[1]
        # Check the current executor inventory, not one historical release's
        # fingerprint: an approved executor correction must change its identity.
        values={p.relative_to(repo/'src').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('research','runtime','data','contracts') for p in sorted((repo/'src'/folder).rglob('*.py'))}
        from research.contracts import digest
        actual=research_jobs.implementation()
        self.assertEqual(actual['files'],values)
        self.assertEqual(actual['fingerprint'],digest(values))
        # Exercise the real inventory function against an isolated source tree.
        # Serving changes are excluded; input preparation remains identity-bound.
        source=self.base/'code'/'src'
        for folder in ('research','runtime','data','contracts','read_model','api'):
            path=source/folder/'sample.py';path.parent.mkdir(parents=True)
            path.write_text('# original '+folder+'\n')
        with patch.object(research_jobs,'__file__',str(source/'runtime'/'sample.py')):
            before=research_jobs.implementation()
            for folder in ('read_model','api'):
                (source/folder/'sample.py').write_text('# serving update\n')
                self.assertEqual(research_jobs.implementation(),before)
            (source/'data'/'sample.py').write_text('# input preparation update\n')
            after=research_jobs.implementation()
            self.assertNotEqual(after['fingerprint'],before['fingerprint'])
            self.assertNotEqual(after['files']['data/sample.py'],before['files']['data/sample.py'])
