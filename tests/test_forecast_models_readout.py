"""Read-only forecast evidence: support, scope, and signed error."""

import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_forecast_models_readout import (
    SOURCE_POLICY, SCHEMA, build, calibration_bins, checksum, diagnostics, evaluation_rows,
)


class ForecastReadoutTests(unittest.TestCase):
    def rows(self):
        task = {'targets':dict.fromkeys(('AUDCAD','NZDCAD','USDCAD')),'horizon':1}
        forecasts = {('2026-09-01','AUDCAD'):0, ('2026-09-01','NZDCAD'):-1, ('2026-09-01','USDCAD'):1,
                     ('2026-09-02','AUDCAD'):0, ('2026-09-02','NZDCAD'):-1, ('2026-09-02','USDCAD'):1,
                     ('2026-09-03','AUDCAD'):0, ('2026-09-03','NZDCAD'):-1, ('2026-09-03','USDCAD'):1,
                     ('2026-09-04','AUDCAD'):0}
        return list(evaluation_rows(task,forecasts,[
            '2026-09-01','2026-09-02','2026-09-04','2026-09-03'],
            lambda date,_: {'AUDCAD':0.5,'NZDCAD':-1.5,'USDCAD':1} if date=='2026-09-01' else None,
            '2026-09-04'))

    def test_only_complete_matured_target_sections_enter_any_metric(self):
        rows = self.rows()
        result = diagnostics(rows,'CS')
        self.assertEqual(result['counts'], {'missing_outcome':6,'pending_outcome':1,'unavailable_forecast':2,'matched':3})
        self.assertEqual(result['dates'],1)
        self.assertEqual(result['quality_dates'],1)
        self.assertEqual(result['metric_values'][0]['value'],1)
        self.assertAlmostEqual(result['metric_values'][1]['value'],(0.5/3)**0.5)
        zero = next(row for row in rows if row['status']=='matched' and row['instrument']=='AUDCAD')
        self.assertEqual(zero['forecast_bps'],0)
        self.assertEqual(zero['error_bps'],0.5)
        self.assertEqual(sum(bin['count'] for bin in result['histogram']),3)
        self.assertFalse(result['rolling']['points'])

    def test_incomplete_cross_section_is_excluded(self):
        task = {'targets':dict.fromkeys(('AUDCAD','NZDCAD')),'horizon':1}
        rows = list(evaluation_rows(task,{('2026-09-01','AUDCAD'):0},['2026-09-01'],
                                    lambda *_: self.fail('Incomplete group requested targets'),'2026-09-02'))
        self.assertEqual([r['status'] for r in rows],['excluded_incomplete_scope','unavailable_forecast'])
        self.assertTrue(all(metric['value'] is None for metric in diagnostics(rows,'CS')['metric_values']))

    def test_forecast_view_and_ties_are_preserved(self):
        rows = [{'status':'matched','instrument':'CADUSD','origin':str(i),'forecast_bps':2,
                 'realized_bps':i,'error_bps':i-2} for i in range(8)]
        ts = diagnostics(rows,'TS')
        self.assertEqual(ts['metric_values'][0]['label'],'Forecast correlation')
        self.assertIsNone(ts['metric_values'][0]['value'])
        self.assertIsNone(ts['metric_values'][-1]['value'])
        self.assertFalse(ts['calibration'])
        for i,r in enumerate(rows):
            r['forecast_bps'] = i//3
        bins = calibration_bins(rows)
        self.assertEqual([b['count'] for b in bins],[3,3,2])
        self.assertEqual(diagnostics(rows,'COMBINED')['metric_values'][0]['value'],None)

    def export_fixture(self, directory, *, incompatible=False, corrupt=False):
        task_id = 'P3GROUP_'+'e'*64
        model_id = 'P3MODEL_'+'9'*64
        scope = {'id':'FX_CCY_VS_CAD','reference_currency':'CAD','members':['AUDCAD','NZDCAD']}
        targets = {'AUDCAD':{'id':'TARGET_example_a'},'NZDCAD':{'id':'TARGET_example_b'}}
        relation = {'id':'RELATIONSHIP_sample'}
        constituent = dict(relationship=relation,targets=targets,scope=scope,recipe={'id':'RECIPE_sample'},
                           trial={},validation={},features={},alignment_policy=None,mapping={})
        model = dict(group_id=task_id,id=model_id,horizon=1,method='equal_weight',mode='CS',scope=scope,
                     basis='relative_to_scope_mean',targets=targets,relationships=[relation],
                     combination={'weights':['1'],'intercept':'0','status':'fitted'})
        roster = [model]
        if incompatible:
            roster.append(dict(model,id='P3MODEL_'+'8'*64,method='error_weight',
                               targets=dict(targets,AUDCAD={'id':'different target'})))
        fit = dict(schema_version='p3_fit/2.0.0',policy=SOURCE_POLICY,id='P3FIT_fixture',
                   fit_period={'start_inclusive':'2022-01-01','end_exclusive':'2026-09-01'},
                   weight_training={},constituents=[constituent],models_by_horizon={'1':roster})
        target = directory/'fit.json'
        target.write_text(json.dumps(fit))
        panel=directory/'p4-inputs.json'
        panel.write_text(json.dumps({
            'fit_id':fit['id'],'fit_sha256':checksum(target.read_bytes()),'extension':{'id':'snapshot'},
            'kind':'p4_frozen_fx_inputs','market_dates':['2026-09-01','2026-09-02'],
            'score_dates':['2026-09-01','2026-09-02'],'price_lineage':{},
            'pair_closes':{'AUDCAD':['1','1.01'],'NZDCAD':['1','1.00']},
        }))
        forecasts=directory/'p4-forecasts.csv.gz'
        with gzip.open(forecasts,'wt') as stream:
            stream.write('model_id,horizon,scope,method,forecast_date,pair,expected_relative_return\n')
            for day in ('2026-09-01','2026-09-02'):
                stream.write(f'{model_id},1,FX_CCY_VS_CAD,equal_weight,{day},AUDCAD,0.001\n')
                stream.write(f'{model_id},1,FX_CCY_VS_CAD,equal_weight,{day},NZDCAD,-0.001\n')
        manifest=directory/'p4-run-manifest.json'
        manifest.write_text(json.dumps({'fit':fit['id'],'fit_sha256':checksum(target.read_bytes()),
            'input_sha256':checksum(panel.read_bytes()),'files':{'p4-forecasts.csv.gz':checksum(forecasts.read_bytes())},
            'period':['2026-09-01','2026-09-02'],'price_snapshot':{'id':'snapshot'},'feature_replay_script_sha256':'fixture'}))
        if corrupt:
            panel.write_text('{}')
        output=directory/'readout'
        result=build(target,directory,checksum(manifest.read_bytes()),output)
        return result,output,task_id,model_id

    def test_full_readout_preserves_saved_ids_and_applies_declared_centering(self):
        with tempfile.TemporaryDirectory() as path:
            result,output,task_id,model_id=self.export_fixture(Path(path))
            catalog=json.loads((output/'index.json').read_bytes())
            self.assertEqual(catalog['schema'],SCHEMA)
            self.assertEqual(result,{'tasks':1,'candidates':1,'evaluation_models':1})
            self.assertEqual(catalog['tasks'][0]['id'],task_id)
            saved=(output/(model_id+'.json')).read_bytes()
            self.assertEqual(catalog['model_hashes'][model_id],checksum(saved))
            detail=json.loads(saved)
            self.assertEqual(detail['model_id'],model_id)
            diagnostics_result=detail['evaluation']['diagnostics']
            self.assertEqual(diagnostics_result['counts'],{'matched':2,'pending_outcome':2})
            matched=next(row for row in detail['evaluation']['rows'] if row['status']=='matched')
            self.assertAlmostEqual(matched['realized_bps'],50)
            self.assertAlmostEqual(matched['error_bps'],40)
            self.assertIsNone(detail['model_version'])

    def test_mixed_target_or_changed_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaisesRegex(ValueError,'Incompatible'):
                self.export_fixture(Path(path),incompatible=True)
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaisesRegex(ValueError,'Source hash'):
                self.export_fixture(Path(path),corrupt=True)


if __name__=='__main__':
    unittest.main()
