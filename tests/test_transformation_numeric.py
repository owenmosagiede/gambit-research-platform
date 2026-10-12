"""Independent hand-calculated references; never generate answers with calculate.

Examples use triangular levels: their last four increments are exactly 6,7,8,9.
Fractional, OLS, quantile and moment references below derive from those explicit
operands. These are bounded certification fixtures, not exhaustive real domains.
"""
import math
import unittest
from unittest.mock import patch
from data.transformations.numeric import (calculate,validate_parameters,required_history,OPERATIONS,FAILURE_CODES,ParameterError,ExecutionFailure)

SQRT=math.sqrt
LOG=math.log
LEVELS=[1,2,4,7,11,16,22,29,37,46]
# Independent sample deviation of four explicitly supplied reference operands.
def reference_sd4(a,b,c,d):
    center=(a+b+c+d)/4
    return SQRT(((a-center)**2+(b-center)**2+(c-center)**2+(d-center)**2)/3)

def example(params,answer,values=None,**extra):
    return {'values':list(LEVELS if values is None else values),'parameters':params,'expected_last':answer,**extra}

NUMERICAL_EXAMPLES={
 'level.raw':example({},46),
 'level.log':example({},LOG(46)),
 'change.diff':example({'k':2},17),
 'change.pct':example({'k':2},17/29),
 'change.log':example({'k':2},LOG(46)-LOG(29)),
 'standard.zscore':example({'w':4},20/SQRT(82)),
 'standard.robust_z':example({'w':4},20.5/(1.4826*6.5)),
 'standard.rank_centered':example({'w':4},1),
 'standard.ew_zscore':example({'h':1},3,[1,3,5]),
 'smooth.sma':example({'w':4},33.5),
 'smooth.median':example({'w':4},33),
 'smooth.ema':example({'h':1},3.5,[1,3,5]),
 'smooth.ew_change':example({'h':1},1,[1,3,3]),
 'trend.ma_distance':example({'w':4},12.5),
 'trend.ma_relative':example({'w':4},46/33.5-1),
 'trend.ema_distance':example({'h':1},1.5,[1,3,5]),
 'trend.ema_relative':example({'h':1},5/3.5-1,[1,3,5]),
 'trend.ma_crossover':example({'fast':2,'slow':4},41.5/33.5-1),
 'trend.ema_crossover':example({'fast':1,'slow':2},3.5/(4-SQRT(2))-1,[1,3,5]),
 'trend.slope':example({'w':4},8),
 'trend.slope_tstat':example({'w':4},8*SQRT(10)),
 'trend.efficiency_ratio':example({'w':4},1),
 'trend.breakout_position':example({'w':4},10/7),
 'momentum.skip_diff':example({'k':4,'s':1},21),
 'momentum.skip_return':example({'k':4,'s':1},21/16),
 'momentum.sign_balance':example({'w':4},1),
 'shock.standardized_change':example({'k':1,'w':4},9/SQRT(5/3)),
 'shock.change_zscore':example({'k':1,'w':4},2.5/SQRT(5/3)),
 'shock.change_percentile':example({'k':1,'w':4},1),
 'accel.second_diff':example({'k':2},4),
 'accel.pct_change':example({'k':2},17/29-13/16),
 'accel.log_change':example({'k':2},LOG(46)-2*LOG(29)+LOG(16)),
 'accel.slope_change':example({'w':4,'k':2},2),
 'vol.diff_sd':example({'w':4},SQRT(5/3)),
 'vol.pct_sd':example({'w':4},reference_sd4(6/16,7/22,8/29,9/37)),
 'vol.log_sd':example({'w':4},reference_sd4(LOG(22/16),LOG(29/22),LOG(37/29),LOG(46/37))),
 'vol.ewma':example({'h':1,'basis':'diff'},SQRT(2.5),[1,3,2]),
 'vol.abs_change':example({'w':4,'basis':'diff'},7.5),
 'vol.change':example({'w':4,'k':2,'basis':'diff'},0),
 'vol.ratio':example({'fast':2,'slow':4,'basis':'diff'},SQRT(.3)),
 'vol.downside':example({'w':4,'basis':'diff'},SQRT(5),[10,8,11,7,9]),
 'vol.upside':example({'w':4,'basis':'diff'},SQRT(13/4),[10,8,11,7,9]),
 'vol.asymmetry':example({'w':4,'basis':'diff'},SQRT(20/13),[10,8,11,7,9]),
 'volscale.diff':example({'k':2,'w':4},17/SQRT(5/3)),
 'volscale.trend':example({'w':4,'v':4},12.5/SQRT(5/3)),
 'distribution.skew':example({'w':4},0),
 'distribution.kurtosis':example({'w':4},-1.2),
 'distribution.iqr':example({'w':4},1.5),
 'distribution.quantile_range':example({'w':4,'low':.1,'high':.9},2.4),
 'distribution.quantile_skew':example({'w':4},0),
 'extreme.range':example({'w':4},24),
 'extreme.new_high':example({'w':4},1),
 'extreme.new_low':example({'w':4},1,[4,3,2,1,0]),
 'extreme.time_since_high':example({'w':4},1,[5,4,5,3]),
 'extreme.time_since_low':example({'w':4},1,[1,2,1,3]),
 'extreme.max_drawdown':example({'w':4},-.5,[10,8,12,6]),
 'persistence.diff_autocorr':example({'w':4,'a':1},1),
 'persistence.sign':example({'w':4},1),
 'persistence.sign_streak':example({'w':4},4),
 'persistence.variance_ratio':example({'w':8,'k':2},14/9),
 'threshold.positive_level':example({},1),
 'threshold.positive_change':example({'k':2},1),
 'threshold.above_mean':example({'w':4},1),
 'threshold.above_median':example({'w':4},1),
 'threshold.above_quantile':example({'w':4,'q':.75},1),
 'threshold.below_quantile':example({'w':4,'q':.25},1,[1,2,3,4,0]),
 'seasonal.bucket_deviation':example({'history_years':3},5,[1,3,7],frequency='monthly',reference_times=['2020-01-01','2021-01-01','2022-01-01']),
 'seasonal.bucket_zscore':example({'history_years':3},5/SQRT(2),[1,3,7],frequency='monthly',reference_times=['2020-01-01','2021-01-01','2022-01-01']),
 'price.vol_normalized_log_return':example({'k':2,'w':4},LOG(46/29)/reference_sd4(LOG(22/16),LOG(29/22),LOG(37/29),LOG(46/37))),
 'price.log_return_shape':example({'short':1,'long':2},LOG(29/37)),
 'price.oriented_new_low':example({'w':3},-1,[4,3,2,1]),
 'core.lag':example({'k':2},29),
 'core.rolling_sum':example({'w':4},134),
 'core.sample_sd':example({'w':4},SQRT(107)),
 'input_distribution.skew':example({'w':4},(135/4)/(115/12)**1.5,[1,2,4,8]),
 'input_distribution.kurtosis':example({'w':4},(10/3)*(25141/64)/(115/12)**2-13.5,[1,2,4,8]),
 'input_distribution.iqr':example({'w':4},3.25,[1,2,4,8]),
 'input_distribution.quantile_range':example({'w':4,'low':.1,'high':.9},5.5,[1,2,4,8]),
 'input_distribution.quantile_skew':example({'w':4},3/13,[1,2,4,8]),
}

class NumericalAcceptanceTests(unittest.TestCase):
    def test_every_kernel_has_independent_defined_reference(self):
        self.assertEqual(set(NUMERICAL_EXAMPLES),OPERATIONS)
        self.assertEqual(len(OPERATIONS),79)
        for op,fixture in NUMERICAL_EXAMPLES.items():
            with self.subTest(operation=op):
                actual=calculate(op,fixture['values'],fixture['parameters'],frequency=fixture.get('frequency','irregular'),reference_times=fixture.get('reference_times'))
                self.assertIsNone(actual[-1]['reason'])
                self.assertAlmostEqual(actual[-1]['value'],fixture['expected_last'],places=11)
                self.assertEqual(len(actual),len(fixture['values']))
                for p in actual:
                    self.assertEqual(set(p),{'value','reason'})
                    self.assertEqual(p['value'] is None,p['reason'] is not None)
                    self.assertTrue(p['reason'] is None or p['reason'] in FAILURE_CODES)
                    self.assertTrue(p['value'] is None or math.isfinite(p['value']))
    def test_current_inclusive_and_exclusive_windows(self):
        self.assertEqual(calculate('smooth.sma',[1,2,9],{'w':2}),[{'value':None,'reason':'INSUFFICIENT_HISTORY'},{'value':1.5,'reason':None},{'value':5.5,'reason':None}])
        self.assertEqual(calculate('standard.zscore',[1,2,9],{'w':2})[-1]['value'],7.5/SQRT(.5))
        self.assertEqual(calculate('core.lag',[1,2,None],{'k':1})[-1],{'value':2.0,'reason':None})
        self.assertEqual(calculate('extreme.new_high',[1,2,2],{'w':2})[-1]['value'],0)
    def test_direct_distribution_does_not_difference(self):
        self.assertEqual(calculate('input_distribution.iqr',[1,2,4,8],{'w':4})[-1]['value'],3.25)
        self.assertEqual(calculate('distribution.iqr',[0,1,3,7,15],{'w':4})[-1]['value'],3.25)
        self.assertEqual(calculate('input_distribution.iqr',[0,1,3,7,15],{'w':4})[-1]['value'],6.5)
        self.assertEqual(calculate('core.sample_sd',[4,4,4],{'w':3})[-1]['value'],0)
    def test_zero_descriptive_sd_and_undefined_denominators(self):
        for op,params in [('vol.diff_sd',{'w':3}),('vol.pct_sd',{'w':3}),('vol.log_sd',{'w':3}),('core.sample_sd',{'w':3}),('vol.change',{'w':3,'k':1,'basis':'diff'})]:
            with self.subTest(op=op):self.assertEqual(calculate(op,[4]*10,params)[-1],{'value':0.0,'reason':None})
        for op,params,reason in [('standard.zscore',{'w':3},'ZERO_VARIANCE'),('standard.robust_z',{'w':3},'ZERO_MAD'),('trend.breakout_position',{'w':3},'ZERO_RANGE'),('trend.efficiency_ratio',{'w':3},'ZERO_PATH_LENGTH'),('volscale.diff',{'w':3,'k':1},'ZERO_VARIANCE'),('vol.ratio',{'fast':2,'slow':3,'basis':'diff'},'ZERO_DENOMINATOR'),('distribution.quantile_skew',{'w':3},'ZERO_RANGE')]:
            with self.subTest(op=op):self.assertEqual(calculate(op,[4]*10,params)[-1]['reason'],reason)
    def test_ties_and_zero_changes(self):
        self.assertEqual(calculate('standard.rank_centered',[2,2,2],{'w':2})[-1]['value'],0)
        self.assertEqual(calculate('extreme.new_low',[2,2,2],{'w':2})[-1]['value'],0)
        self.assertEqual(calculate('price.oriented_new_low',[2,2,2],{'w':2})[-1]['value'],0)
        self.assertEqual(calculate('persistence.sign_streak',[1,2,2],{'w':4})[-1]['value'],0)
        self.assertEqual(calculate('persistence.sign_streak',[1,2],{'w':100})[-1]['value'],1)
    def test_log_domains_and_zero_division(self):
        self.assertEqual(calculate('level.log',[0,-1],{}),[{'value':None,'reason':'NONPOSITIVE_LOG_INPUT'}]*2)
        self.assertEqual(calculate('change.pct',[0,2],{'k':1})[-1]['reason'],'ZERO_DENOMINATOR')
        self.assertEqual(calculate('change.pct',[-2,-1],{'k':1})[-1]['value'],-.5)
        self.assertEqual(calculate('price.oriented_new_low',[1,0,2],{'w':2})[-1]['reason'],'NONPOSITIVE_INPUT')
    def test_missing_complete_windows_and_reason_propagation(self):
        self.assertEqual(calculate('smooth.sma',[1,None,3,4],{'w':2})[2]['reason'],'MISSING_REQUIRED_OBSERVATION')
        self.assertEqual(calculate('smooth.sma',[1,None,3,4],{'w':2})[3]['value'],3.5)
        self.assertEqual(calculate('change.diff',[None,2],{'k':1},input_reasons=['ZERO_DENOMINATOR',None])[-1]['reason'],'ZERO_DENOMINATOR')
        self.assertEqual(calculate('smooth.sma',[None,2],{'w':2},input_reasons=['SOURCE_INVALID',None])[-1]['reason'],'SOURCE_INVALID')
    def test_ew_initialization_and_missing_reset(self):
        alpha=1-1/SQRT(2)
        r=calculate('smooth.ema',[1,3,None,5,7],{'h':2})
        self.assertEqual([x['reason'] for x in r],['INSUFFICIENT_HISTORY',None,'MISSING_REQUIRED_OBSERVATION','INSUFFICIENT_HISTORY',None])
        self.assertAlmostEqual(r[1]['value'],alpha*3+(1-alpha)*1)
        self.assertAlmostEqual(r[4]['value'],alpha*7+(1-alpha)*5)
        z=calculate('standard.ew_zscore',[1,3,None,5,7,9],{'h':1})
        self.assertEqual([v['reason'] for v in z],['INSUFFICIENT_HISTORY', 'ZERO_VARIANCE','MISSING_REQUIRED_OBSERVATION','INSUFFICIENT_HISTORY','ZERO_VARIANCE',None])
        self.assertAlmostEqual(z[-1]['value'],3)
    def test_ew_arithmetic_failure_not_warmup(self):
        r=calculate('vol.ewma',[0,2,4,8],{'h':1,'basis':'pct'})
        self.assertEqual([v['reason'] for v in r],['INSUFFICIENT_HISTORY','ZERO_DENOMINATOR',None,None])
        self.assertEqual(r[-1]['value'],1)
        r=calculate('smooth.ew_change',[1,1e308,-1e308,3,4],{'h':1})
        self.assertEqual(r[2]['reason'],'NONFINITE_OUTPUT')
        self.assertEqual(r[3]['value'],1e308)
        self.assertTrue(math.isfinite(r[-1]['value']))
    def test_seasonal_supported_buckets(self):
        buckets={
         'daily':['2020-01-06','2021-01-04','2022-01-03'],
         'weekly':['2020-01-01','2021-01-06','2022-01-05'],
         'monthly':['2020-01-01','2021-01-01','2022-01-01'],
         'quarterly':['2020-02-01','2021-01-01','2022-03-01'],
         'semiannual':['2020-01-01','2021-03-01','2022-05-01'],
         'intraday':['2020-01-06T12:00:00','2021-01-04T12:00:00','2022-01-03T12:00:00'],
         'tick':['2020-01-06T12:00:01','2021-01-04T12:00:01','2022-01-03T12:00:01'],
        }
        for freq,times in buckets.items():
            with self.subTest(frequency=freq):
                result=calculate('seasonal.bucket_deviation',[1,3,7],{'history_years':3},frequency=freq,reference_times=times)
                self.assertEqual(result[-1]['value'],5)
        for freq in ['annual','event','irregular']:
            with self.assertRaises(ParameterError):validate_parameters('seasonal.bucket_zscore',{'history_years':3},freq)
    def test_seasonal_history_boundary_and_missing_exception(self):
        times=['2018-01-01','2019-01-01','2020-01-01','2021-01-01','2022-01-01']
        out=calculate('seasonal.bucket_deviation',[100,1,None,3,7],{'history_years':3},frequency='monthly',reference_times=times)
        self.assertEqual(out[-1]['value'],5)
        self.assertEqual(out[2]['reason'],'MISSING_REQUIRED_OBSERVATION')
        with self.assertRaises(ParameterError):calculate('seasonal.bucket_deviation',[1,2,3],{'history_years':3},frequency='monthly')
        same_day=['2022-01-03T09:00:00','2022-01-03T10:00:00','2022-01-03T11:00:00']
        self.assertEqual(calculate('seasonal.bucket_deviation',[1,3,7],{'history_years':3},frequency='daily',reference_times=same_day)[-1]['reason'],'INSUFFICIENT_SEASONAL_HISTORY')
    def test_every_kernel_prefix_is_unchanged_by_future_observations(self):
        for op,f in NUMERICAL_EXAMPLES.items():
            with self.subTest(operation=op):
                dates=f.get('reference_times');later=dates+['2023-01-01'] if dates else None
                before=calculate(op,f['values'],f['parameters'],frequency=f.get('frequency','irregular'),reference_times=dates)
                after=calculate(op,f['values']+[900],f['parameters'],frequency=f.get('frequency','irregular'),reference_times=later)
                self.assertEqual(before,after[:-1])
    def test_extreme_finite_values_never_become_valid_nonfinite(self):
        for op,f in NUMERICAL_EXAMPLES.items():
            with self.subTest(operation=op):
                n=len(f['values']);values=[1e308 if i%2==0 else -1e308 for i in range(n)]
                result=calculate(op,values,f['parameters'],frequency=f.get('frequency','irregular'),reference_times=f.get('reference_times'))
                self.assertEqual(len(result),n)
                for value in result:self.assertTrue(value['value'] is None or math.isfinite(value['value']))
        self.assertEqual(calculate('change.diff',[1e308,-1e308],{'k':1})[-1]['reason'],'NONFINITE_OUTPUT')
    def test_parameter_domain_rejects_invalid_before_execution(self):
        for op,f in NUMERICAL_EXAMPLES.items():
            p=f['parameters'];freq=f.get('frequency','irregular')
            with self.subTest(operation=op):
                with self.assertRaises(ParameterError):validate_parameters(op,dict(p,unexpected=1),freq)
                for name,v in p.items():
                    if type(v) is int:
                        with self.assertRaises(ParameterError):validate_parameters(op,dict(p,**{name:0}),freq)
                        with self.assertRaises(ParameterError):validate_parameters(op,dict(p,**{name:True}),freq)
        for op,p in [('core.sample_sd',{'w':1}),('trend.slope',{'w':2}),('distribution.skew',{'w':2}),('distribution.kurtosis',{'w':3}),('trend.ma_crossover',{'fast':3,'slow':2}),('momentum.skip_diff',{'k':2,'s':2}),('shock.change_zscore',{'k':3,'w':3}),('release.shock_change_zscore',{'k':3,'w':3,'basis':'diff'}),('persistence.diff_autocorr',{'w':3,'a':1}),('persistence.variance_ratio',{'w':7,'k':2}),('distribution.quantile_range',{'w':4,'low':.9,'high':.1}),('vol.ewma',{'h':2,'basis':'invented'})]:
            with self.subTest(operation=op):
                with self.assertRaises(ParameterError):validate_parameters(op,p)
        with self.assertRaises(ParameterError):calculate('combine.difference',[1,2],{})
    def test_input_contract_rejections(self):
        for v in [[True],[float('nan')],[float('inf')],['2'],[10**500]]:
            with self.assertRaises(ParameterError):calculate('level.raw',v,{})
        with self.assertRaises(ParameterError):calculate('level.raw',[1],{},input_reasons=['SOURCE_INVALID'])
        with self.assertRaises(ParameterError):calculate('level.raw',[None],{},input_reasons=[None])
        with self.assertRaises(ParameterError):calculate('level.raw',[1,2],{},reference_times=['2020-01-02','2020-01-01'])
    def test_irregular_observations_count_positions_not_calendar_days(self):
        result=calculate('change.diff',[1,4,8],{'k':1},frequency='irregular',reference_times=['2020-01-01','2020-02-15','2022-01-01'])
        self.assertEqual([p['value'] for p in result],[None,3.0,4.0])
    def test_required_history_boundaries(self):
        cases={'core.lag':({'k':3},4),'core.sample_sd':({'w':2},2),'change.diff':({'k':3},4),'standard.zscore':({'w':4},5),'smooth.sma':({'w':4},4),'vol.diff_sd':({'w':4},5),'shock.change_zscore':({'k':2,'w':4},7),'accel.second_diff':({'k':3},7),'persistence.diff_autocorr':({'a':2,'w':8},11),'persistence.sign':({'w':4},6),'volscale.trend':({'w':4,'v':6},7),'release.shock_change_zscore':({'w':4,'k':1,'basis':'diff'},5)}
        for op,(p,expected) in cases.items():self.assertEqual(required_history(op,p),expected)
    def test_every_kernel_missing_required_values_are_explicit(self):
        for op,f in NUMERICAL_EXAMPLES.items():
            with self.subTest(operation=op):
                result=calculate(op,[None]*len(f['values']),f['parameters'],frequency=f.get('frequency','irregular'),reference_times=f.get('reference_times'))
                self.assertTrue(all(p['value'] is None for p in result))
                self.assertTrue(all(p['reason'] in FAILURE_CODES for p in result))
    def test_every_kernel_constant_level_boundary(self):
        zero_variance={'standard.zscore','standard.ew_zscore','shock.standardized_change','shock.change_zscore','volscale.diff','volscale.trend','distribution.skew','distribution.kurtosis','input_distribution.skew','input_distribution.kurtosis','persistence.diff_autocorr','persistence.variance_ratio','seasonal.bucket_zscore','price.vol_normalized_log_return'}
        special={'standard.robust_z':'ZERO_MAD','trend.breakout_position':'ZERO_RANGE','trend.efficiency_ratio':'ZERO_PATH_LENGTH','trend.slope_tstat':'ZERO_DENOMINATOR','vol.ratio':'ZERO_DENOMINATOR','vol.asymmetry':'ZERO_DENOMINATOR','distribution.quantile_skew':'ZERO_RANGE','input_distribution.quantile_skew':'ZERO_RANGE'}
        ones={'level.raw','smooth.sma','smooth.median','smooth.ema','core.lag','threshold.positive_level'}
        for op,f in NUMERICAL_EXAMPLES.items():
            with self.subTest(operation=op):
                # Adequate warmup for all finite windows in the defined fixtures.
                count=3 if op.startswith('seasonal.') else 40
                result=calculate(op,[1]*count,f['parameters'],frequency=f.get('frequency','irregular'),reference_times=f.get('reference_times'))[-1]
                expected_reason='ZERO_VARIANCE' if op in zero_variance else special.get(op)
                if expected_reason:self.assertEqual(result,{'value':None,'reason':expected_reason})
                else:
                    expected=f['parameters']['w'] if op=='core.rolling_sum' else 1 if op in ones else 0
                    self.assertIsNone(result['reason'])
                    self.assertAlmostEqual(result['value'],expected,places=12)
    def test_minimum_domain_boundaries_are_not_grid_membership(self):
        valid=[('core.sample_sd',{'w':2}),('trend.slope',{'w':3}),('distribution.skew',{'w':3}),('distribution.kurtosis',{'w':4}),('input_distribution.skew',{'w':3}),('input_distribution.kurtosis',{'w':4}),('persistence.diff_autocorr',{'w':4,'a':1}),('persistence.variance_ratio',{'w':4,'k':1}),('distribution.quantile_range',{'w':1,'low':0,'high':1}),('threshold.above_quantile',{'w':1,'q':0}),('threshold.below_quantile',{'w':1,'q':1})]
        for op,p in valid:
            with self.subTest(operation=op):self.assertEqual(validate_parameters(op,p),p)
    def test_quantiles_and_directional_semivariance_are_explicit(self):
        self.assertAlmostEqual(calculate('input_distribution.quantile_range',[1,2,4,8],{'w':4,'low':0,'high':1})[-1]['value'],7)
        self.assertEqual(calculate('vol.downside',[1,2,4],{'w':2,'basis':'diff'})[-1]['value'],0)
        self.assertEqual(calculate('vol.upside',[4,2,1],{'w':2,'basis':'diff'})[-1]['value'],0)
        self.assertEqual(calculate('vol.asymmetry',[4,2,1],{'w':2,'basis':'diff'})[-1]['reason'],'ZERO_DENOMINATOR')

    def test_ew_stable_moments_and_very_large_parameter(self):
        # The second raw moment minus squared mean loses this variance to
        # cancellation. Equivalent centered-moment recurrence retains it.
        result=calculate('standard.ew_zscore',[1e12,1e12+2,1e12+4],{'h':1})
        self.assertAlmostEqual(result[-1]['value'],3)
        self.assertTrue(all(p['reason']=='INSUFFICIENT_HISTORY' for p in calculate('smooth.ema',[1,2],{'h':10**500})))
        for q in [10**500,-10**500,float('inf'),float('nan')]:
            with self.assertRaises(ParameterError):validate_parameters('threshold.above_quantile',{'w':2,'q':q})
        with self.assertRaises(ParameterError):validate_parameters('level.raw',{},[])

    def test_zero_volatility_numerator_is_valid_when_denominator_is_positive(self):
        self.assertEqual(calculate('vol.ratio',[0,1,3,6,9],{'basis':'diff','fast':2,'slow':4})[-1],{'value':0.0,'reason':None})
        self.assertEqual(calculate('persistence.variance_ratio',[1,2,1,2,1,2,1,2,1],{'k':2,'w':8})[-1],{'value':0.0,'reason':None})

    def test_unexpected_errors_remain_execution_failures(self):
        for error in [RuntimeError('fixture defect'),ZeroDivisionError('fixture defect')]:
            with patch('data.transformations.numeric.mean',side_effect=error):
                with self.assertRaises(ExecutionFailure):calculate('smooth.sma',[1,2],{'w':2})

if __name__=='__main__':unittest.main()
