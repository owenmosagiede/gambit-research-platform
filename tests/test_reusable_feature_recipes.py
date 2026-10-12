"""Reusable identities and additive registration, using metadata-only fixtures.

The legacy catalog boundary is mocked with7740 valid synthetic metadata bindings;
no source observations, historical materializations or production files are used.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from data.feature_store import FeatureStore, PublicationError, record_path
from data import reusable_features as reusable
from data.reusable_feature_contracts import make_record, validate_record, RECIPE_KIND
from data.transformations.identity import reference, make_feature_definition, canonical_bytes
from data.fx_records import make_record as make_fx_record
from data.transformations.registry import Registry
import test_fx_feature_recipes as fx_fixtures


def inventory(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


class ReusableFeatureRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fx_fixtures.FxFeatureRecipeTests.setUpClass.__func__(cls)
        store=FeatureStore(cls.template)
        approval=make_fx_record('onboarding_evidence',{'kind':'synthetic_research_approval'})
        retrospective=make_fx_record('policy_definition',{'kind':'fx_retrospective_policy','approval':reference(approval),
            'mode':'retrospective_date_label','historical_replay':False,'live_use':False,
            'unknown_availability':'preserve_null','source_selection':'pinned_original_capture'})
        store.install_record(approval);store.install_record(retrospective)
        cls.policy=deepcopy(cls.policy)
        cls.policy['body']['parameters'].extend([
            {'name':'source_alignment_approval','unit':'evidence_reference','value':{'kind':'reference','value':reference(approval)}},
            {'name':'source_retrospective_policy','unit':'policy_reference','value':{'kind':'reference','value':reference(retrospective)}}])
        # Replace only this isolated synthetic fixture policy before deriving IDs.
        store.path(record_path(cls.policy)).write_bytes(canonical_bytes(cls.policy)+b'\n')
        registry,policy,variants=reusable._context(cls.template)
        cls.definitions={key:reusable._definition(registry,policy,v) for key,v in variants.items()}
        cls.memory_records={};cls.bindings={}
        store=FeatureStore(cls.template)
        for instrument in cls.instruments:
            snapshot=store.resolve(instrument['price_snapshot']);source=snapshot['body']['definition'];symbol=instrument['instrument_id']
            unit=snapshot['body']['source_metadata']['unit']
            for key,definition in cls.definitions.items():
                b=definition['body']
                recipe={'sources':[{'alias':'source','source_view':source}],
                    'selection':{'measure':'close','entity_id':symbol,'dimensions':[]},
                    'steps':deepcopy(b['steps']),'output_node':b['output_node'],
                    'output_unit':b['output_contract']['unit_template'].replace('quote_currency_per_base_currency',unit),
                    'calculation_scope_requirement':'none','scope_policy':None,
                    **{name:b[name] for name in ('history_mode','history_policy','execution_policy','evaluation_policy')}}
                feature=make_feature_definition(recipe,symbol+' - '+definition['display_name'])
                ref=reference(feature)
                cls.memory_records[(ref['id'],ref['version'],ref['content_sha256'])]=feature
                cls.bindings[feature['id']]={'configuration_id':key,'instrument_id':symbol,'feature':ref,
                    'price_snapshot':instrument['price_snapshot'],'source_view':source}
        catalog=make_fx_record('onboarding_evidence',{'kind':reusable.CATALOG_KIND,'profile':'fx_feature_recipes.1.0.0',
            'evaluation_policy':reference(policy),'configurations':list(variants.values()),'bindings':list(cls.bindings.values()),
            'configuration_count':180,'instrument_count':43,'binding_count':7740,
            'materialization_state':'registered_only','research_state':'not_executed'})
        store.install_record(catalog);cls.catalogs=[reference(catalog)]

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='reusable_feature_case_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()/'platform';shutil.copytree(self.template,self.root)
        self.store=FeatureStore(self.root);self.store._resolved=dict(self.memory_records)
        self.registry=Registry(self.root)
        self.expected={record['id']:record for record in self.definitions.values()}

    def context(self):
        return self.store,self.registry,self.policy,self.definitions,self.bindings,self.catalogs

    def fixture_feature(self,symbol='AUDUSD',operator='TR_BASE_momentum_skip_diff'):
        binding=next(b for b in self.bindings.values() if b['instrument_id']==symbol and self.definitions[b['configuration_id']]['body']['steps'][-1]['operator']['id']==operator)
        return self.store.resolve(binding['feature'])

    def test_180_unique_recipes_are_symbol_and_scope_independent(self):
        self.assertEqual(len(self.definitions),180)
        self.assertEqual(len(self.expected),180)
        forbidden={'instrument_id','source_view','selection','universe','scope','period','information_cutoff'}
        for record in self.definitions.values():
            validate_record(record)
            self.assertTrue(record['id'].startswith('FEATURE_RECIPE_'))
            self.assertFalse(forbidden & set(record['body']))
            self.assertFalse(forbidden & set(record['body']['input_contract']))
            self.assertEqual(record['body']['calculation_geometry'],'independent_per_instrument')
            self.assertNotIn('AUDUSD',record['display_name'])
            self.assertNotIn('FTMO_UNIVERSE',str(record))

    def test_same_operator_parameters_across_sources_map_to_one_reusable_identity(self):
        a=self.fixture_feature('AUDUSD');b=self.fixture_feature('EURUSD')
        self.assertNotEqual(a['id'],b['id'])
        pa=reusable._project_legacy(self.store,a,self.registry,self.policy,self.expected)
        pb=reusable._project_legacy(self.store,b,self.registry,self.policy,self.expected)
        self.assertEqual(reference(pa),reference(pb))
        self.assertEqual(pa['body']['output_contract']['unit_template'],'log_quote_currency_per_base_currency')
        self.assertEqual(a['body']['recipe']['calculation_scope_requirement'],'none')

    def test_display_labels_do_not_redefine_a_recipe_but_parameters_and_policies_do(self):
        record=deepcopy(next(iter(self.definitions.values())))
        renamed=deepcopy(record);renamed['display_name']='My display label'
        validate_record(renamed);self.assertEqual(reference(record),reference(renamed))
        changed=deepcopy(record['body']);changed['steps'][-1]['parameters'][0]['value']['value']='999'
        self.assertNotEqual(make_record(RECIPE_KIND,changed)['id'],record['id'])
        changed=deepcopy(record['body']);changed['execution_policy']['content_sha256']='f'*64
        self.assertNotEqual(make_record(RECIPE_KIND,changed)['id'],record['id'])
        changed=deepcopy(record['body']);changed['input_contract']['value_domain']='different_domain'
        self.assertNotEqual(make_record(RECIPE_KIND,changed)['id'],record['id'])
        with self.assertRaises(ValueError):validate_record(make_record(RECIPE_KIND,changed))
        changed=deepcopy(record['body']);changed['steps']=list(reversed(changed['steps']))
        self.assertNotEqual(make_record(RECIPE_KIND,changed)['id'],record['id'])
        with self.assertRaises(ValueError):validate_record(make_record(RECIPE_KIND,changed))
        changed=deepcopy(record['body']);changed['steps'][-1]['operator']['version']='2.0.1'
        self.assertNotEqual(make_record(RECIPE_KIND,changed)['id'],record['id'])
        changed=deepcopy(record['body']);changed['evaluation_policy']['version']='2.0.1'
        self.assertNotEqual(make_record(RECIPE_KIND,changed)['id'],record['id'])

    def test_scoped_or_source_mismatched_old_features_cannot_be_projected(self):
        feature=self.fixture_feature()
        for transform in ('entity','view','output'):
            recipe=deepcopy(feature['body']['recipe'])
            if transform=='entity':recipe['selection']['entity_id']='EURUSD'
            elif transform=='view':recipe['sources'][0]['source_view']=self.fixture_feature('EURUSD')['body']['recipe']['sources'][0]['source_view']
            else:recipe['output_unit']='dimensionless'
            altered=make_feature_definition(recipe,'Invalid binding')
            with self.subTest(transform=transform),self.assertRaises(PublicationError):
                reusable._project_legacy(self.store,altered,self.registry,self.policy,self.expected)

    def test_contract_rejects_instrument_or_universe_injection_and_double_log(self):
        record=next(iter(self.definitions.values()))
        for field,value in (('instrument_id','AUDUSD'),('scope','FTMO_UNIVERSE'),('period',{'start':'2024-01-01'})):
            body=deepcopy(record['body']);body[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_record(make_record(RECIPE_KIND,body))
        body=deepcopy(record['body']);body['steps'].insert(0,deepcopy(body['steps'][0]))
        with self.assertRaises(ValueError):validate_record(make_record(RECIPE_KIND,body))

    def test_legacy_parameters_and_existing_operator_definitions_remain_unchanged(self):
        before=inventory(self.root/'definitions/transformations')
        for identifier in ('TR_BASE_momentum_skip_diff','TR_BASE_vol_ewma','TR_BASE_distribution_skew'):
            old=self.fixture_feature(operator=identifier);recipe=reusable._project_legacy(self.store,old,self.registry,self.policy,self.expected)
            self.assertEqual(recipe['body']['steps'],old['body']['recipe']['steps'])
            for role in ('history_policy','execution_policy','evaluation_policy'):
                self.assertEqual(recipe['body'][role],old['body']['recipe'][role])
        self.assertEqual(before,inventory(self.root/'definitions/transformations'))

    def test_registration_reuses_all_records_without_observations_and_verifies_all_mappings(self):
        # A real pre-existing legacy file plus a historical payload sentinel must
        # remain byte-identical, even though the rest of the fixture is in memory.
        old=self.fixture_feature();self.store.install_record(old)
        sentinel=self.root/'storage/payloads/unchanged_historical_payload.bin'
        sentinel.parent.mkdir(parents=True,exist_ok=True);sentinel.write_bytes(b'Historical observations remain untouched.')
        before=inventory(self.root)
        with patch.object(reusable,'_legacy_context',side_effect=lambda root:self.context()), \
             patch.object(reusable,'FeatureStore',return_value=self.store), \
             patch.object(reusable,'_price_snapshot',side_effect=lambda store,binding,policy,verify_rows:(store.resolve(binding),None)):
            first=reusable.register_reusable_fx_recipes(self.root)
            after=inventory(self.root)
            second=reusable.register_reusable_fx_recipes(self.root)
            self.assertEqual(inventory(self.root),after)
            self.assertEqual((first['added_recipes'],first['reused_recipes']),(180,0))
            self.assertEqual((second['added_recipes'],second['reused_recipes']),(0,180))
            self.assertEqual(first['registration'],second['registration'])
            self.assertEqual((first['legacy_binding_count'],first['new_observations'],first['historical_records_rewritten']),(7740,0,0))
            listed=reusable.list_reusable_fx_recipes(self.root)
            self.assertEqual(len(listed),180)
            selected=next(r for r in listed if r['display_name']=='Log -> Skip-Recent Difference (k=63, s=5)')
            loaded=reusable.load_reusable_recipe(self.root,selected['id'])
            self.assertEqual(reference(selected),reference(loaded))
            mapped=reusable.legacy_bindings_for_recipe(self.root,reference(selected))
            self.assertEqual((len(mapped),len({b['instrument_id'] for b in mapped})),(43,43))
            blocked_id=mapped[0]['feature']['id'];original_resolve=self.store.resolve
            def one_bad_member(binding):
                if binding['id']==blocked_id:raise PublicationError('Isolated member corruption')
                return original_resolve(binding)
            with patch.object(self.store,'resolve',side_effect=one_bad_member):
                with self.assertRaises(PublicationError):reusable.legacy_bindings_for_recipe(self.root,reference(selected))
                deferred=reusable.legacy_bindings_for_recipe(self.root,reference(selected),verify_features=False)
                self.assertEqual(deferred,mapped)
            # An unavailable source prevents that member's strict readiness
            # check, but cannot erase its existing reusable recipe registration.
            blocked_snapshot=mapped[0]['price_snapshot']['id']
            def unavailable_source(binding):
                if binding['id']==blocked_snapshot:raise PublicationError('Historical source manifest unavailable')
                return original_resolve(binding)
            with patch.object(self.store,'resolve',side_effect=unavailable_source):
                self.assertEqual(len(reusable.list_reusable_fx_recipes(self.root)),180)
                self.assertEqual(reference(reusable.load_reusable_recipe(self.root,selected['id'])),reference(selected))
                self.assertEqual(reusable.legacy_bindings_for_recipe(self.root,reference(selected),verify_features=False),mapped)
                with self.assertRaisesRegex(PublicationError,'source manifest unavailable'):
                    reusable.legacy_bindings_for_recipe(self.root,reference(selected))
            # Registration is historical. Missing or changed current execution
            # config must affect readiness only, never these completed identities.
            current=self.root/'config/fx_retrospective_completion.json'
            current.unlink()
            self.assertEqual(len(reusable.list_reusable_fx_recipes(self.root)),180)
            self.assertEqual(reference(reusable.load_reusable_recipe(self.root,selected['id'])),reference(selected))
            self.assertEqual(len(reusable.legacy_bindings_for_recipe(self.root,reference(selected),verify_features=False)),43)
            current.write_text('{"return_policy":{"different_current_policy":true}}')
            self.assertEqual(len(reusable.list_reusable_fx_recipes(self.root)),180)
            self.assertEqual(reference(reusable.load_reusable_recipe(self.root,selected['id'])),reference(selected))
            self.assertEqual(len(reusable.legacy_bindings_for_recipe(self.root,reference(selected))),43)
            # A self-consistent altered definition still cannot enter the exact
            # approved registry just by recomputing its content address.
            changed=deepcopy(selected['body']);changed['steps'][-1]['parameters'][0]['value']['value']='999'
            wrong=make_record(RECIPE_KIND,changed,'Unsupported')
            self.store.install_record(wrong)
            with self.assertRaises(reusable.ReusableRecipeNotFound):reusable.load_reusable_recipe(self.root,wrong['id'])
        self.assertEqual({p:after[p] for p in before},before)
        created=set(after)-set(before)
        self.assertEqual(len(created),182)  #180definitions, one completion, writer lock
        self.assertTrue(all(p.startswith(('definitions/feature_recipes/','storage/catalog/feature_recipes/','storage/temporary/feature-store-publication.lock')) for p in created))

    def test_unknown_and_invalid_reusable_recipe_ids_fail_closed(self):
        for identifier in ('FEATURE_x','../secret','FEATURE_RECIPE_'+'A'*64):
            with self.subTest(identifier=identifier),self.assertRaises(reusable.ReusableRecipeNotFound):
                reusable.load_reusable_recipe(self.root,identifier)


if __name__=='__main__':unittest.main()
