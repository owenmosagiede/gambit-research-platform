from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import unittest
from api.application import ApplicationRoutes
from api.catalog_cache import CatalogCache
from read_model.projector import build
from read_model.storage import atomic


class ReadModelHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve(); self.root=self.base/'research';self.root.mkdir()
        self.output=self.base/'serving';build(self.root,self.output)

    def read(self,path,directory=True,head=False):
        route=ApplicationRoutes(self.root,None,CatalogCache(),'HEAD' if head else 'GET',path,read_model_dir=self.output if directory else None)
        with patch('api.experiment_views.ExperimentView',side_effect=AssertionError('request-time scan')),patch('api.signal_summaries.list_signal_summaries',side_effect=AssertionError('request-time scan')):
            route.read(head)
        return route.response[0],json.loads(route.response[1])

    def test_explicit_activation_and_no_fallback(self):
        self.assertEqual(self.read('/api/read-model/v1/recipes',False)[0],503)
        status,value=self.read('/api/read-model/v1/recipes')
        self.assertEqual(status,200);self.assertEqual(value['items'],[])
        atomic(self.output,'status.json',{'unavailable':True})
        self.assertEqual(self.read('/api/read-model/v1/recipes')[0],503)

    def test_queries_and_head(self):
        self.assertEqual(self.read('/api/read-model/v1/ledger',head=True)[0],200)
        for url in ('queue?limit=200','queue?limit=1&limit=2','queue?bad=1','ledger?from=bad','recipes?status=succeeded'):
            self.assertEqual(self.read('/api/read-model/v1/'+url)[0],400,url)
        self.assertEqual(self.read('/api/read-model/v1/missing')[0],404)
        self.assertEqual(self.read('/api/read-model/v1/trial/TRIAL_'+'0'*64)[0],404)

    def test_endpoints_cannot_submit_or_control_research(self):
        route=ApplicationRoutes(self.root,None,CatalogCache(),'POST','/api/read-model/v1/queue',read_model_dir=self.output)
        route.write(b'{}')
        self.assertIn(route.response[0],(404,405))
        self.assertFalse((self.root/'storage').exists())

    def test_activity_is_bounded_optional_and_read_only(self):
        code,value=self.read('/api/read-model/v1/activity')
        self.assertEqual(code,200);self.assertEqual(value['worker']['state'],'unknown')
        self.assertEqual(self.read('/api/read-model/v1/activity?scan=1')[0],400)
        self.assertEqual(self.read('/api/read-model/v1/evidence/TRIAL_'+'a'*64+'?role=aligned_sample')[0],400)
        self.assertFalse((self.root/'storage').exists())
