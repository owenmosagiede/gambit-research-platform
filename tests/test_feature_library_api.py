"""Registered Feature selection is a read-only operation separate from preparation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api import application as server,feature_library
from test_signal_library_api import running,request,inventory
from test_feature_store import persistence_fixture
from data.feature_store import publish_feature,FeatureStore
from data.transformations.identity import reference

RID='FEATURE_RECIPE_'+'a'*64
QUERY='?feature_id='+RID+'&feature_version=1.0.0&scope_id=FTMO_UNIVERSE&scope_version=1.0.0'

class FeatureSelectionApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()

    def test_registered_listing_and_scope_resolution_are_read_only_gets(self):
        result={'schema_version':'1.0.0','feature_count':180,'features':[],'issues':[]}
        resolution={'selection_read_only':True,'recipe':{'reference':{'id':RID}}}
        before=inventory(self.root)
        with patch.object(server,'list_feature_library',return_value=result) as listing,patch.object(server,'get_feature_resolution',return_value=resolution) as resolve:
            with running(self.root) as address:
                status,headers,data=request(address,'/api/feature-library')
                self.assertEqual(status,200);self.assertEqual(json.loads(data),result);self.assertEqual(headers['Cache-Control'],'no-store')
                status,_,data=request(address,'/api/feature-resolution'+QUERY)
                self.assertEqual(status,200);self.assertEqual(json.loads(data),resolution)
                resolve.assert_called_with(self.root,RID,'1.0.0','FTMO_UNIVERSE','1.0.0')
                self.assertEqual(request(address,'/api/feature-library','HEAD')[0],200)
                self.assertEqual(request(address,'/api/feature-resolution'+QUERY,'HEAD')[2],b'')
                for method in ('POST','PUT','PATCH','DELETE'):
                    self.assertEqual(request(address,'/api/feature-resolution'+QUERY,method)[0],405)
        self.assertEqual(inventory(self.root),before)

    def test_query_errors_are_distinct_from_integrity_and_absence(self):
        with patch.object(server,'get_feature_resolution') as resolve,running(self.root) as address:
            for q in ('','?feature_id=x',QUERY+'&scope_id=AUDUSD',QUERY+'&prepare=true',QUERY.replace('scope_version=1.0.0','scope_version=')):
                self.assertEqual(request(address,'/api/feature-resolution'+q)[0],400)
            resolve.assert_not_called()
            resolve.side_effect=ValueError('PRIVATE_RECORD_LOCATION')
            status,_,body=request(address,'/api/feature-resolution'+QUERY)
            self.assertEqual(status,503);self.assertNotIn(b'PRIVATE_RECORD_LOCATION',body)
            resolve.side_effect=feature_library.FeatureNotFound('absent')
            self.assertEqual(request(address,'/api/feature-resolution'+QUERY)[0],404)
            resolve.side_effect=feature_library.InvalidFeatureQuery('invalid')
            self.assertEqual(request(address,'/api/feature-resolution'+QUERY)[0],400)
            self.assertEqual(request(address,'/api/feature-library?prepare=true')[0],400)

    def test_identity_validation_before_resolution(self):
        for identifier,version,scope,scope_version in [('OTHER','1.0.0','AUDUSD','1.0.0'),(RID,None,'AUDUSD','1.0.0'),(RID,'1.0.0','../','1.0.0'),(RID,'1.0.0','AUDUSD','latest')]:
            with self.assertRaises(feature_library.InvalidFeatureQuery):feature_library.get_feature_resolution(self.root,identifier,version,scope,scope_version)

    def test_non_fx_definitions_remain_selectable_without_materialization(self):
        args=persistence_fixture(self.root);store=FeatureStore(self.root);feature=args['feature']
        # Fixture installs dependencies; registration can be independent of output.
        store.install_record(feature)
        with patch('data.reusable_features.list_reusable_fx_recipes',return_value=[]):
            catalog=feature_library.list_feature_library(self.root)
        self.assertEqual(catalog['feature_count'],1);row=catalog['features'][0]
        self.assertEqual(row['id'],feature['id']);self.assertEqual(row['registration_state'],'registered')
        self.assertEqual(row['kind'],'stored_feature')
        self.assertFalse(list((self.root/'storage/catalog/feature_store').glob('*/manifest.json')))

    def test_non_fx_source_coverage_is_not_broadcast_as_fx_outputs(self):
        args=persistence_fixture(self.root);saved=publish_feature(self.root,**args);feature=FeatureStore(self.root).resolve(saved['feature'])
        scope={'id':'FTMO_UNIVERSE','version':'1.0.0','reference':{'id':'FTMO_UNIVERSE'},
               'display_name':'FTMO Universe','membership_snapshot':{'id':'SNAPSHOT_FIXTURE'},'members':['AUDUSD','EURUSD']}
        before=inventory(self.root)
        with patch('data.scopes.resolve_scope',return_value=scope):
            result=feature_library.get_feature_resolution(self.root,feature['id'],'1.0.0','FTMO_UNIVERSE','1.0.0')
        self.assertEqual(result['summary'],{'materialized_member_count':0,'missing_member_count':0,'blocked_member_count':2})
        self.assertEqual(len(result['source_materializations']),1)
        self.assertTrue(all(not row['materializations'] for row in result['members']))
        self.assertEqual(inventory(self.root),before)

if __name__=='__main__':unittest.main()
