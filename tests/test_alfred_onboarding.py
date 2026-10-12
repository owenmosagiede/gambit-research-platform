"""Meaningful boundary checks for the bounded raw onboarding implementation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from data.alfred_onboarding import (SERIES, Store, as_of, canonical, fetch_evidence,
    parse_vintages, ref, sha, stable_read, strict_json)


def example():
    return {'output_type':3,'units':'lin','offset':0,'count':1,'observations':[
        {'date':'2018-01-01',SERIES+'_20180202':'26.74',SERIES+'_20180309':'26.71'}]}

class AlfredOnboardingTests(unittest.TestCase):
    def test_historical_cutoff_does_not_leak_later_revision(self):
        rows=parse_vintages(example())
        self.assertEqual(as_of(rows,'2018-02-01'),[])
        self.assertEqual(as_of(rows,'2018-02-02')[0]['value'],'26.74')
        self.assertEqual(as_of(rows,'2018-03-08')[0]['value'],'26.74')
        self.assertEqual(as_of(rows,'2018-03-09')[0]['value'],'26.71')

    def test_withdrawn_value_stays_missing_instead_of_reusing_old_value(self):
        d=example();d['observations'][0][SERIES+'_20180309']='.'
        row=as_of(parse_vintages(d),'2018-03-09')[0]
        self.assertEqual(row['status'],'missing');self.assertIsNone(row['value'])

    def test_truncated_or_noninitial_page_cannot_pass_as_complete(self):
        for field,value in [('count',2),('offset',1),('count',True)]:
            with self.subTest(field=field,value=value):
                d=example();d[field]=value
                with self.assertRaises(ValueError): parse_vintages(d)

    def test_duplicate_period_wrong_series_and_invalid_date_rejected(self):
        d=example();d['observations']*=2;d['count']=2
        with self.assertRaises(ValueError): parse_vintages(d)
        d=example();d['observations'][0]['OTHER_20180309']='1'
        with self.assertRaises(ValueError): parse_vintages(d)
        d=example();d['observations'][0][SERIES+'_20180230']='1'
        with self.assertRaises(ValueError): parse_vintages(d)

    def test_numeric_missingness_and_strict_json_are_not_coerced(self):
        for value in ['NaN','Infinity',2.5]:
            d=example();d['observations'][0][SERIES+'_20180202']=value
            with self.assertRaises(ValueError): parse_vintages(d)
        for text in ['{"x":1,"x":2}','{"x":NaN}']:
            with self.assertRaises(ValueError): strict_json(text)

    def test_archive_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'raw.json';p.write_bytes(b'changed')
            with self.assertRaises(ValueError): stable_read(p,sha(b'original'))

    def test_immutable_publication_reuses_exact_bytes_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            store.install('catalog/a.json',b'original')
            store.install('catalog/a.json',b'original')
            with self.assertRaises(ValueError): store.install('catalog/a.json',b'changed')
            self.assertEqual((Path(directory)/'catalog/a.json').read_bytes(),b'original')
            with self.assertRaises(ValueError): store.install('../escape',b'bad')

    def test_corrupted_published_blob_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);store.blob(b'original')
            path=next(iter(store.blobs));(Path(directory)/path).write_bytes(b'changed')
            with self.assertRaises(ValueError): store.verify_closure()

    def test_wrong_payload_format_cannot_resolve_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);member=store.blob(b'{}')
            member['format']='parquet'
            record={'record_type':'test','id':'test','version':'1.0.0','members':[member]}
            store.records[('test','1.0.0')]=record;store.paths[('test','1.0.0')]='record.json'
            store.install('record.json',canonical(record)+b'\n')
            with self.assertRaises(ValueError): store.verify_closure()

    def test_request_failure_records_do_not_disclose_credential_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);secret='a'*32
            creds=root/'credential';creds.write_text('FRED_API_KEY='+secret+'\n')
            error=urllib.error.URLError('https://api.stlouisfed.org/?api_key='+secret)
            with patch('data.alfred_onboarding.urllib.request.urlopen',side_effect=error):
                fetch_evidence(root/'requests',creds)
            receipts=list((root/'requests').glob('*.receipt.json'))
            self.assertEqual(len(receipts),5)
            for path in receipts:
                text=path.read_text();self.assertNotIn(secret,text)
                record=json.loads(text)
                self.assertIsNotNone(record['error']);self.assertIsNone(record['payload_path'])
                self.assertNotIn('api_key',record['parameters'])

if __name__=='__main__': unittest.main()
