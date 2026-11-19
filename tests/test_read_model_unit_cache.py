"""Lossless cache conversion, bounded expansion and unpublished-copy compaction."""
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zlib

from read_model.projector import compact_if_wasteful
from read_model.storage import IntegrityFailure, encoded
from read_model.unit_cache import pack, unpack


class UnitCacheTests(unittest.TestCase):
    def fixture(self):
        return {'references': [{'id':'saved-'+str(i),'version':'1.0.0','source':'immutable'} for i in range(300)],
                'metrics':{'number':1.25,'integer':12345678901234567890,'missing':None,'passed':True},
                'label':'Currency € — research'}

    def test_large_values_are_smaller_and_restore_exact_fields(self):
        original=self.fixture();saved=pack(original)
        self.assertLess(len(saved),len(encoded(original))//2)
        self.assertEqual(unpack(saved),original)

    def test_legacy_json_small_values_and_json_strings_remain_readable(self):
        for value in (self.fixture(), {'id':'saved'}, ['one',None,False], 'zlib1:looks-like-a-prefix'):
            self.assertEqual(unpack(encoded(value)),value)
            self.assertEqual(unpack(pack(value)),value)

    def test_corrupt_digest_base64_length_and_stream_fail_closed(self):
        saved=pack(self.fixture());prefix,size,sha,payload=saved.split(':',3)
        compressed=base64.b64decode(payload)
        invalid=[f'{prefix}:{size}:{"0"*64}:{payload}',
                 f'{prefix}:{int(size)-1}:{sha}:{payload}',
                 f'{prefix}:{size}:{sha}:invalid?',
                 f'{prefix}:{size}:{sha}:'+base64.b64encode(compressed[:-2]).decode(),
                 f'{prefix}:{size}:{sha}:'+base64.b64encode(compressed+b'trailing').decode()]
        for value in invalid:
            with self.subTest(value=value[:90]),self.assertRaises(IntegrityFailure):unpack(value)

    def test_declared_size_and_underreported_expansion_are_bounded(self):
        saved=pack(self.fixture())
        with patch('read_model.unit_cache.MAX_VALUE_BYTES',16):
            with self.assertRaises(ValueError):pack(self.fixture())
            with self.assertRaises(IntegrityFailure):unpack(saved)
            with self.assertRaises(IntegrityFailure):unpack(encoded(self.fixture()))
        raw=b'x'*1000000
        bomb='zlib1:10:'+hashlib.sha256(raw).hexdigest()+':'+base64.b64encode(zlib.compress(raw)).decode()
        with self.assertRaises(IntegrityFailure):unpack(bomb)

    def test_compaction_reclaims_only_empty_pages_and_preserves_source_baselines(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'unpublished.sqlite';db=sqlite3.connect(path)
            db.execute('CREATE TABLE sources(path TEXT,signature TEXT,sha256 TEXT)')
            db.execute('INSERT INTO sources VALUES(?,?,?)',('original.json','original-signature','a'*64))
            db.execute('CREATE TABLE padding(value BLOB)')
            db.execute('INSERT INTO padding VALUES(zeroblob(524288))');db.commit()
            db.execute('DELETE FROM padding');db.commit()
            original=db.execute('SELECT * FROM sources').fetchall();before=path.stat().st_size
            with patch('read_model.projector.MAX_DATABASE_BYTES',256*1024):compact_if_wasteful(db)
            self.assertLess(path.stat().st_size,before)
            self.assertEqual(db.execute('SELECT * FROM sources').fetchall(),original)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            statements=[];db.set_trace_callback(statements.append);compact_if_wasteful(db)
            self.assertNotIn('VACUUM',statements);db.close()
