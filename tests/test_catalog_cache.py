import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from api.catalog_cache import CatalogCache

class CatalogCacheTests(unittest.TestCase):
    def test_overlapping_reads_share_work_and_results_are_isolated(self):
        cache=CatalogCache(); started=threading.Event(); release=threading.Event(); calls=[]
        def read():
            calls.append(1);started.set();release.wait(3);return {'items':[1]}
        with ThreadPoolExecutor(max_workers=4) as pool:
            first=pool.submit(cache.get,'pit',read);self.assertTrue(started.wait(1))
            rest=[pool.submit(cache.get,'pit',read) for _ in range(3)]
            release.set();values=[first.result()]+[f.result() for f in rest]
        self.assertEqual(len(calls),1);values[0]['items'].append(2)
        self.assertEqual(cache.get('pit',read),{'items':[1]})
    def test_expiry_failures_and_bounded_size(self):
        now=[0];cache=CatalogCache(ttl=5,limit=2,clock=lambda:now[0]);calls=[]
        def read():calls.append(1);return len(calls)
        self.assertEqual(cache.get('a',read),1);now[0]=5
        self.assertEqual(cache.get('a',read),2)
        with self.assertRaises(ValueError):cache.get('b',lambda:(_ for _ in ()).throw(ValueError('bad')))
        self.assertEqual(cache.get('b',read),3);cache.get('c',read)
        self.assertEqual(len(cache.entries),2);self.assertFalse(cache.pending)
