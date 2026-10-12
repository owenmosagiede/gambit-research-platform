"""Read-only grouped Signal mapping over real completed synthetic catalogs.

The shared fixture contains canonical metadata for 180 recipes and 43 source
bindings each. Legacy Features stay in memory: none are installed just to list
the mapping, and no source observations are copied or computed.
"""
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from data.alfred_onboarding import Store
from data.feature_store import FeatureStore, PublicationError
from data import reusable_features as reusable
from data.transformations.identity import make_feature_definition, reference
import test_reusable_feature_recipes as fixtures


class SignalRecipeMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ReusableFeatureRecipeTests.setUpClass.__func__(cls)
        store=FeatureStore(cls.template)
        for record in cls.definitions.values():store.install_record(record)
        store.install_record(reusable._registration(cls.definitions,cls.bindings,cls.catalogs))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='signal_recipe_mapping_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'platform';shutil.copytree(self.template,self.root)

    def feature(self,symbol='AUDUSD',configuration=None):
        if configuration is None:
            configuration=next(key for key,record in self.definitions.items()
                if record['body']['steps'][-1]['operator']['id']=='TR_BASE_momentum_skip_diff')
        binding=next(b for b in self.bindings.values()
                     if b['configuration_id']==configuration and b['instrument_id']==symbol)
        ref=binding['feature'];record=self.memory_records[(ref['id'],ref['version'],ref['content_sha256'])]
        return deepcopy(record)

    def test_complete_mapping_groups_instruments_and_separates_parameters(self):
        mapping,project=reusable.reusable_recipe_mapping_context(self.root)
        self.assertEqual(len(mapping),7740)
        self.assertEqual(len({entry['recipe']['id'] for entry in mapping.values()}),180)
        a=self.feature('AUDUSD');b=self.feature('EURUSD')
        self.assertNotEqual(a['id'],b['id'])
        self.assertEqual(reference(project(a)),reference(project(b)))
        self.assertEqual(reference(mapping[a['id']]['recipe']),reference(project(a)))
        self.assertEqual(mapping[a['id']]['feature'],reference(a))
        self.assertEqual(mapping[a['id']]['instrument_id'],'AUDUSD')
        self.assertEqual(mapping[a['id']]['source_view'],a['body']['recipe']['sources'][0]['source_view'])
        self.assertEqual(set(mapping[a['id']]),{'feature','recipe','instrument_id','source_view','price_snapshot'})
        first=project(a)
        other_configuration=next(key for key,record in self.definitions.items()
            if record['body']['steps'][-1]['operator']==first['body']['steps'][-1]['operator']
            and record['body']['steps'][-1]['parameters']!=first['body']['steps'][-1]['parameters'])
        other=self.feature('AUDUSD',other_configuration)
        self.assertNotEqual(project(other)['id'],first['id'])

    def test_mapping_does_not_open_any_legacy_features_snapshots_or_outputs(self):
        original=FeatureStore.resolve;opened=[]
        def metadata_only(store,binding):
            identifier=binding['id'];opened.append(identifier)
            if ((identifier.startswith('FEATURE_') and not identifier.startswith('FEATURE_RECIPE_'))
                    or identifier.startswith(('SNAPSHOT_','MATERIALIZATION_'))):
                raise AssertionError('Mapping attempted a historical Feature/source/output scan')
            return original(store,binding)
        with (patch.object(FeatureStore,'resolve',metadata_only),
              patch.object(FeatureStore,'payload',side_effect=AssertionError('Mapping read observations')),
              patch.object(reusable,'_price_snapshot',side_effect=AssertionError('Mapping checked source readiness'))):
            mapping=reusable.reusable_recipe_mapping(self.root)
        self.assertEqual(len(mapping),7740)
        self.assertEqual(len([identifier for identifier in opened if identifier.startswith('FEATURE_RECIPE_')]),180)

    def test_included_feature_projection_reuses_one_context_and_never_writes(self):
        before=fixtures.inventory(self.root)
        original=reusable._registered
        with (patch.object(reusable,'_registered',wraps=original) as registered,
              patch.object(Store,'install',side_effect=AssertionError('Mapping attempted installation')),
              patch.object(Store,'blob',side_effect=AssertionError('Mapping attempted payload creation')),
              patch.object(FeatureStore,'writer',side_effect=AssertionError('Mapping acquired a writer'))):
            mapping,project=reusable.reusable_recipe_mapping_context(self.root)
            for symbol in ('AUDUSD','EURUSD','USDJPY'):
                feature=self.feature(symbol)
                self.assertEqual(reference(project(feature)),reference(mapping[feature['id']]['recipe']))
            self.assertEqual(registered.call_count,1)
        self.assertEqual(before,fixtures.inventory(self.root))

    def test_mismatched_exact_reference_and_unmapped_features_are_rejected(self):
        _,project=reusable.reusable_recipe_mapping_context(self.root)
        feature=self.feature();altered=deepcopy(feature);altered['version']='1.0.1'
        with self.assertRaisesRegex(PublicationError,'exact completed legacy reference'):project(altered)
        altered=deepcopy(feature);altered['body']['recipe']['selection']['entity_id']='EURUSD'
        with self.assertRaisesRegex(PublicationError,'exact completed legacy reference'):project(altered)
        changed=deepcopy(feature['body']['recipe']);changed['selection']['entity_id']='UNKNOWN'
        with self.assertRaises(reusable.ReusableRecipeNotFound):project(make_feature_definition(changed,'Unmapped fixture'))
        renamed=deepcopy(feature);renamed['display_name']='A cosmetic historical label'
        self.assertEqual(reference(project(renamed)),reference(project(feature)))

    def test_mapping_mutation_cannot_change_projector_authority(self):
        mapping,project=reusable.reusable_recipe_mapping_context(self.root)
        feature=self.feature();expected=project(feature)
        entry=mapping[feature['id']];entry['feature']['version']='99.0.0'
        entry['instrument_id']='EURUSD';entry['source_view']['content_sha256']='f'*64
        entry['recipe']['body']['output_node']='altered'
        self.assertEqual(project(feature),expected)

    def test_projector_checks_instrument_and_source_against_completed_binding(self):
        context=reusable._registered(self.root);feature=self.feature()
        for field,value in [('instrument_id','EURUSD'),
                            ('source_view',self.feature('EURUSD')['body']['recipe']['sources'][0]['source_view'])]:
            changed=list(context);changed[-1]=deepcopy(context[-1]);changed[-1][feature['id']][field]=value
            with self.subTest(field=field),patch.object(reusable,'_registered',return_value=tuple(changed)):
                _,project=reusable.reusable_recipe_mapping_context(self.root)
                with self.assertRaisesRegex(PublicationError,'instrument or source'):project(feature)


if __name__=='__main__':unittest.main()
