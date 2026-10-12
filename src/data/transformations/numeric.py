"""Provider-independent causal arithmetic for one ordered numeric series.

Adapted mathematical definitions: legacy Data transformation_catalog.py (0.1.0)
49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b.
The platform contract deliberately versions explicit failure propagation and zero
*descriptive* deviation separately from the old implementation. Nothing imports
legacy code, reads data, selects vintages or interprets provider identity here.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from datetime import datetime
import math
from statistics import mean, median

class ParameterError(ValueError):
    """Invalid operator, domain, parameter, or numeric input contract."""

class ExecutionFailure(RuntimeError):
    """Unexpected implementation error; never a scientific null result."""

FAILURE_CODES = frozenset({
    'NON_NUMERIC_INPUT', 'INSUFFICIENT_HISTORY', 'MISSING_REQUIRED_OBSERVATION',
    'NONPOSITIVE_LOG_INPUT', 'NONPOSITIVE_INPUT', 'ZERO_DENOMINATOR',
    'ZERO_VARIANCE', 'ZERO_MAD', 'ZERO_RANGE', 'ZERO_PATH_LENGTH',
    'UNDEFINED_SEASONAL_BUCKET', 'INSUFFICIENT_SEASONAL_HISTORY',
    'NUMERICAL_FAILURE', 'NONFINITE_OUTPUT', 'SOURCE_MISSING', 'SOURCE_INVALID',
    'MISSING_PERIOD', 'UNSUPPORTED_DOMAIN', 'UNSUPPORTED_CADENCE', 'INAPPLICABLE', 'UNDECLARED_HISTORY_MODE',
})

class _PointFailure(ArithmeticError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

# Parameter names are separate from optional, explicitly requested finite grids.
PARAMETERS = {
    'level.raw': (), 'level.log': (),
    'change.diff': ('k',), 'change.pct': ('k',), 'change.log': ('k',),
    'standard.zscore': ('w',), 'standard.robust_z': ('w',),
    'standard.rank_centered': ('w',), 'standard.ew_zscore': ('h',),
    'smooth.sma': ('w',), 'smooth.median': ('w',), 'smooth.ema': ('h',),
    'smooth.ew_change': ('h',),
    'trend.ma_distance': ('w',), 'trend.ma_relative': ('w',),
    'trend.ema_distance': ('h',), 'trend.ema_relative': ('h',),
    'trend.ma_crossover': ('fast','slow'), 'trend.ema_crossover': ('fast','slow'),
    'trend.slope': ('w',), 'trend.slope_tstat': ('w',),
    'trend.efficiency_ratio': ('w',), 'trend.breakout_position': ('w',),
    'momentum.skip_diff': ('k','s'), 'momentum.skip_return': ('k','s'),
    'momentum.sign_balance': ('w',),
    'shock.standardized_change': ('k','w'), 'shock.change_zscore': ('k','w'),
    'shock.change_percentile': ('k','w'),
    'accel.second_diff': ('k',), 'accel.pct_change': ('k',),
    'accel.log_change': ('k',), 'accel.slope_change': ('w','k'),
    'vol.diff_sd': ('w',), 'vol.pct_sd': ('w',), 'vol.log_sd': ('w',),
    'vol.ewma': ('basis','h'), 'vol.abs_change': ('basis','w'),
    'vol.change': ('basis','w','k'), 'vol.ratio': ('basis','fast','slow'),
    'vol.downside': ('basis','w'), 'vol.upside': ('basis','w'),
    'vol.asymmetry': ('basis','w'), 'volscale.diff': ('k','w'),
    'volscale.trend': ('w','v'),
    'distribution.skew': ('w',), 'distribution.kurtosis': ('w',),
    'distribution.iqr': ('w',), 'distribution.quantile_range': ('w','low','high'),
    'distribution.quantile_skew': ('w',),
    'extreme.range': ('w',), 'extreme.new_high': ('w',), 'extreme.new_low': ('w',),
    'extreme.time_since_high': ('w',), 'extreme.time_since_low': ('w',),
    'extreme.max_drawdown': ('w',),
    'persistence.diff_autocorr': ('a','w'), 'persistence.sign': ('w',),
    'persistence.sign_streak': ('w',), 'persistence.variance_ratio': ('k','w'),
    'threshold.positive_level': (), 'threshold.positive_change': ('k',),
    'threshold.above_mean': ('w',), 'threshold.above_median': ('w',),
    'threshold.above_quantile': ('w','q'), 'threshold.below_quantile': ('w','q'),
    'seasonal.bucket_deviation': ('history_years',),
    'seasonal.bucket_zscore': ('history_years',),
    'price.vol_normalized_log_return': ('k','w'),
    'price.log_return_shape': ('short','long'), 'price.oriented_new_low': ('w',),
    'core.lag': ('k',), 'core.rolling_sum': ('w',), 'core.sample_sd': ('w',),
    'input_distribution.skew': ('w',), 'input_distribution.kurtosis': ('w',),
    'input_distribution.iqr': ('w',),
    'input_distribution.quantile_range': ('w','low','high'),
    'input_distribution.quantile_skew': ('w',),
}
OPERATIONS = frozenset(PARAMETERS)
FREQUENCIES = frozenset({'tick','intraday','daily','weekly','monthly','quarterly','semiannual','annual','irregular','event'})
SEASONAL_FREQUENCIES = FREQUENCIES - {'annual','irregular','event'}

def parameter_requirements(operation):
    """Factual mathematical domains for registration metadata (not grids)."""
    if not isinstance(operation,str) or (operation not in OPERATIONS and operation!='release.shock_change_zscore'):
        raise ParameterError('unknown operation')
    minima = {}
    if operation in {'standard.zscore','vol.diff_sd','vol.pct_sd','vol.log_sd','vol.change','volscale.diff','core.sample_sd','price.vol_normalized_log_return','shock.standardized_change','shock.change_zscore','release.shock_change_zscore'}: minima['w']=2
    if operation == 'volscale.trend': minima['v']=2
    if operation == 'vol.ratio': minima.update(fast=2,slow=2)
    if operation in {'trend.slope','trend.slope_tstat','accel.slope_change','distribution.skew','input_distribution.skew'}: minima['w']=3
    if operation in {'distribution.kurtosis','input_distribution.kurtosis'}: minima['w']=4
    relations=[]
    names=PARAMETERS.get(operation,('k','w','basis'))
    if 'low' in names:relations.append('0 <= low < high <= 1')
    if 'q' in names:relations.append('0 <= q <= 1')
    if 'fast' in names:relations.append('fast < slow')
    if 'short' in names:relations.append('short < long')
    if 's' in names:relations.append('s < k')
    if operation.startswith('shock.') or operation=='release.shock_change_zscore':relations.append('k < w')
    if operation=='persistence.diff_autocorr':relations.append('w >= 4*a')
    if operation=='persistence.variance_ratio':relations.append('w >= 4*k')
    for name in names:
        if name not in {'q','low','high','basis'}:minima.setdefault(name,1)
    return {'minima':minima,'constraints':relations,
            'supported_frequencies':sorted(SEASONAL_FREQUENCIES if operation.startswith('seasonal.') else FREQUENCIES)}

def validate_parameters(operation, parameters, frequency='irregular'):
    """Validate the mathematical domain, independently of approved grid profiles."""
    if not isinstance(operation, str): raise ParameterError('operation must be text')
    names = PARAMETERS.get(operation)
    if operation == 'release.shock_change_zscore': names = ('k','w','basis')
    if names is None: raise ParameterError('unknown operation: '+operation)
    if not isinstance(parameters, Mapping) or set(parameters) != set(names):
        raise ParameterError('exact parameters required: '+', '.join(names))
    if not isinstance(frequency,str) or frequency not in FREQUENCIES: raise ParameterError('unsupported frequency')
    p = dict(parameters)
    for name, value in p.items():
        if name == 'basis':
            if value not in ('diff','pct','log'): raise ParameterError('basis must be diff, pct or log')
        elif name in {'q','low','high'}:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=1 or not math.isfinite(value):
                raise ParameterError(name+' must be a probability in [0,1]')
        elif type(value) is not int or value<1:
            raise ParameterError(name+' must be a positive integer')
    if 'low' in p and p['low']>=p['high']: raise ParameterError('low must be less than high')
    if 'fast' in p and p['fast']>=p['slow']: raise ParameterError('fast must be less than slow')
    if 'short' in p and p['short']>=p['long']: raise ParameterError('short must be less than long')
    if 's' in p and p['s']>=p['k']: raise ParameterError('s must be less than k')
    if (operation.startswith('shock.') or operation=='release.shock_change_zscore') and p['k']>=p['w']: raise ParameterError('shock requires k < w')
    minima = parameter_requirements(operation)['minima']
    for name, minimum in minima.items():
        if p[name]<minimum: raise ParameterError(f'{name} must be at least {minimum}')
    if operation=='persistence.diff_autocorr' and p['w']<4*p['a']: raise ParameterError('w must be at least 4*a')
    if operation=='persistence.variance_ratio' and p['w']<4*p['k']: raise ParameterError('w must be at least 4*k')
    if operation.startswith('seasonal.') and frequency not in SEASONAL_FREQUENCIES:
        raise ParameterError('unsupported seasonal frequency')
    return p

def required_history(operation, parameters):
    """Minimum total input count; seasonal also needs two eligible prior buckets.

    Release shock counts emitted events here; each event additionally needs its
    declared k-lag resolved state. EW counts consecutive valid observations.
    """
    p=validate_parameters(operation,parameters,'monthly' if str(operation).startswith('seasonal.') else 'irregular')
    if operation.startswith('seasonal.'): return 3
    if operation=='release.shock_change_zscore': return p['w']+1
    if operation in {'level.raw','level.log','threshold.positive_level'}: return 1
    if operation.startswith('change.') or operation in {'core.lag','threshold.positive_change'}: return p['k']+1
    if operation in {'standard.zscore','standard.robust_z','standard.rank_centered','trend.breakout_position','extreme.new_high','extreme.new_low','threshold.above_mean','threshold.above_median','threshold.above_quantile','threshold.below_quantile','price.oriented_new_low','trend.efficiency_ratio','momentum.sign_balance'}: return p['w']+1
    if operation=='standard.ew_zscore': return p['h']+1
    if operation in {'smooth.ema','trend.ema_distance','trend.ema_relative'}: return p['h']
    if operation in {'smooth.ew_change','vol.ewma'}: return p['h']+1
    if operation in {'trend.ma_crossover','trend.ema_crossover'}: return p['slow']
    if operation=='vol.ratio': return p['slow']+1
    if operation.startswith('momentum.skip_'): return p['k']+1
    if operation.startswith('shock.'): return p['k']+p['w']+1
    if operation=='accel.slope_change': return p['w']+p['k']
    if operation.startswith('accel.'): return 2*p['k']+1
    if operation=='vol.change': return p['w']+p['k']+1
    if operation.startswith('vol.') or operation.startswith('distribution.'): return p['w']+1
    if operation in {'volscale.diff','price.vol_normalized_log_return'}: return max(p['k'],p['w'])+1
    if operation=='volscale.trend': return max(p['w'],p['v']+1)
    if operation=='persistence.diff_autocorr': return p['w']+p['a']+1
    if operation=='persistence.sign': return p['w']+2
    if operation=='persistence.sign_streak': return 2
    if operation=='persistence.variance_ratio': return p['w']+1
    if operation=='price.log_return_shape': return p['long']+1
    return p['w']

def _finite(value):
    if not math.isfinite(value): raise _PointFailure('NONFINITE_OUTPUT')
    return float(value)

def _divide(numerator, denominator, reason='ZERO_DENOMINATOR'):
    _finite(numerator); _finite(denominator)
    if denominator==0: raise _PointFailure(reason)
    return numerator/denominator

def _sd(values, denominator=False):
    if len(values)<2: raise _PointFailure('INSUFFICIENT_HISTORY')
    center=mean(values)
    deviation=math.sqrt(sum((v-center)**2 for v in values)/(len(values)-1))
    if denominator and deviation==0: raise _PointFailure('ZERO_VARIANCE')
    return _finite(deviation)

def _quantile(values,q):
    ordered=sorted(values); position=(len(ordered)-1)*q
    lo=math.floor(position);hi=math.ceil(position)
    if lo==hi:return ordered[lo]
    weight=position-lo
    return ordered[lo]*(1-weight)+ordered[hi]*weight

def _rank(value,history):
    return (sum(v<value for v in history)+.5*sum(v==value for v in history))/len(history)

def _sign(value): return int(value>0)-int(value<0)

def _ols(values):
    n=len(values);xc=(n-1)/2;yc=mean(values)
    sxx=sum((i-xc)**2 for i in range(n))
    slope=sum((i-xc)*(v-yc) for i,v in enumerate(values))/sxx
    intercept=yc-slope*xc
    error=math.sqrt(sum((v-(intercept+slope*i))**2 for i,v in enumerate(values))/(n-2)/sxx)
    return _finite(slope),_finite(error)

def _distribution(values,kind,p):
    n=len(values)
    if kind in {'skew','kurtosis'}:
        center=mean(values);scale=_sd(values,True)
        if kind=='skew': return n/((n-1)*(n-2))*sum(((v-center)/scale)**3 for v in values)
        return n*(n+1)/((n-1)*(n-2)*(n-3))*sum(((v-center)/scale)**4 for v in values)-3*(n-1)**2/((n-2)*(n-3))
    if kind=='quantile_range': return _quantile(values,p['high'])-_quantile(values,p['low'])
    q25,q75=_quantile(values,.25),_quantile(values,.75)
    if kind=='iqr':return q75-q25
    return _divide(q75+q25-2*_quantile(values,.5),q75-q25,'ZERO_RANGE')

def _bucket(dt,frequency):
    if frequency in {'tick','intraday'}:return dt.weekday(),dt.hour,dt.minute,dt.second
    if frequency=='daily':return (dt.weekday(),)
    if frequency=='weekly':return (dt.isocalendar().week,)
    if frequency=='monthly':return (dt.month,)
    if frequency=='quarterly':return ((dt.month-1)//3+1,)
    if frequency=='semiannual':return (1 if dt.month<=6 else 2,)
    raise ParameterError('unsupported seasonal frequency')

def calculate(operation, values, parameters, *, reference_times=None, frequency='irregular', input_reasons=None):
    """Return causal ordered {value, reason} points; no imputation or data access.

    Missing/arithmetic failures propagate from precisely the required operands.
    EW state resets on failure; a failing point retains its reason, followed by
    fresh warmup. Zero descriptive SD is valid; zero denominator SD is undefined.
    """
    p=validate_parameters(operation,parameters,frequency)
    if operation not in OPERATIONS:raise ParameterError('temporal operator requires the recipe engine')
    if isinstance(values,(str,bytes)) or not isinstance(values,Sequence):raise ParameterError('values must be an ordered sequence')
    x=[]
    for value in values:
        if value is None:x.append(None);continue
        if isinstance(value,bool) or not isinstance(value,(int,float)):raise ParameterError('NON_NUMERIC_INPUT')
        try: converted=float(value)
        except OverflowError:raise ParameterError('nonfinite input') from None
        if not math.isfinite(converted):raise ParameterError('nonfinite input')
        x.append(converted)
    n=len(x)
    reasons=list(input_reasons) if input_reasons is not None else [None if v is not None else 'MISSING_REQUIRED_OBSERVATION' for v in x]
    if len(reasons)!=n:raise ParameterError('input reason length mismatch')
    for value,reason in zip(x,reasons):
        if value is None and reason not in FAILURE_CODES:raise ParameterError('null input requires a controlled reason')
        if value is not None and reason is not None:raise ParameterError('valid input cannot carry a failure reason')
    dates=None
    if reference_times is not None:
        if not isinstance(reference_times,Sequence) or isinstance(reference_times,(str,bytes)) or len(reference_times)!=n:raise ParameterError('reference time length mismatch')
        try:dates=[datetime.fromisoformat(t.replace('Z','+00:00')) for t in reference_times]
        except (ValueError,TypeError,AttributeError):raise ParameterError('invalid reference timestamp') from None
        try:
            if any(a>=b for a,b in zip(dates,dates[1:])):raise ParameterError('reference timestamps must increase strictly')
        except TypeError:raise ParameterError('mixed timestamp precision or timezones') from None
    if operation.startswith('seasonal.') and dates is None:raise ParameterError('seasonal operation requires reference timestamps')
    def get(i):
        if i<0:raise _PointFailure('INSUFFICIENT_HISTORY')
        if x[i] is None:raise _PointFailure(reasons[i])
        return x[i]
    def window(i,w,exclusive=False):
        end=i if exclusive else i+1
        if end<w:raise _PointFailure('INSUFFICIENT_HISTORY')
        return [get(j) for j in range(end-w,end)]
    def change(i,k=1,basis='diff'):
        if i<k:raise _PointFailure('INSUFFICIENT_HISTORY')
        current,old=get(i),get(i-k)
        if basis=='diff':return _finite(current-old)
        if basis=='pct':return _finite(_divide(current,old)-1)
        if current<=0 or old<=0:raise _PointFailure('NONPOSITIVE_LOG_INPUT')
        return _finite(math.log(current)-math.log(old))
    def changes(i,w,basis='diff',lag=1):
        if i<w+lag-1:raise _PointFailure('INSUFFICIENT_HISTORY')
        return [change(j,lag,basis) for j in range(i-w+1,i+1)]
    def attempt(fn):
        try:return {'value':_finite(fn()),'reason':None}
        except _PointFailure as e:return {'value':None,'reason':e.reason}
        except OverflowError:return {'value':None,'reason':'NONFINITE_OUTPUT'}
        except Exception as e:raise ExecutionFailure('unexpected numeric execution failure in '+operation) from e
    def result_value(point):
        if point['reason'] is not None:raise _PointFailure(point['reason'])
        return point['value']
    ema_cache={}
    def ema(h,mode='level',basis='diff',zscore=False):
        key=(h,mode,basis,zscore)
        if key in ema_cache:return ema_cache[key]
        alpha=-math.expm1(math.log(.5)*(1/h))
        state=None;variance=0.0;run=0;out=[]
        for i in range(n):
            def source():
                if mode=='level':return get(i)
                value=change(i,1,basis)
                return _finite(value*value) if mode=='squared_change' else value
            point=attempt(source)
            if point['reason'] is not None:
                out.append(point);state=None;variance=0.0;run=0;continue
            value=point['value']
            if zscore:
                point=attempt(lambda:_divide(value-state,math.sqrt(variance),'ZERO_VARIANCE')) if run>=h else {'value':None,'reason':'INSUFFICIENT_HISTORY'}
            def advance():
                if state is None:return value,0.0
                new_variance=(1-alpha)*(variance+alpha*(value-state)**2) if zscore else 0.0
                return _finite(alpha*value+(1-alpha)*state),_finite(new_variance)
            try:newstate,newvariance=advance()
            except (OverflowError,_PointFailure):
                out.append({'value':None,'reason':'NONFINITE_OUTPUT'});state=None;variance=0.0;run=0;continue
            state,variance=newstate,newvariance;run+=1
            if not zscore:point={'value':state,'reason':None} if run>=h else {'value':None,'reason':'INSUFFICIENT_HISTORY'}
            out.append(point)
        ema_cache[key]=out
        return out
    def point(i):
        op=operation
        if op=='level.raw':return get(i)
        if op=='level.log':
            v=get(i)
            if v<=0:raise _PointFailure('NONPOSITIVE_LOG_INPUT')
            return math.log(v)
        if op=='core.lag':return get(i-p['k'])
        if op.startswith('change.'):return change(i,p['k'],op.split('.')[1])
        if op=='standard.ew_zscore':return result_value(ema(p['h'],zscore=True)[i])
        if op in {'standard.zscore','standard.robust_z','standard.rank_centered'}:
            history=window(i,p['w'],True);current=get(i)
            if op=='standard.zscore':return (current-mean(history))/_sd(history,True)
            if op=='standard.rank_centered':return 2*_rank(current,history)-1
            center=median(history);mad=median([abs(v-center) for v in history])
            return _divide(current-center,1.4826*mad,'ZERO_MAD')
        if op in {'smooth.sma','smooth.median','core.rolling_sum','core.sample_sd'}:
            w=window(i,p['w'])
            return {'smooth.sma':mean,'smooth.median':median,'core.rolling_sum':sum,'core.sample_sd':_sd}[op](w)
        if op in {'smooth.ema','smooth.ew_change'}:return result_value(ema(p['h'],'change' if op=='smooth.ew_change' else 'level')[i])
        if op in {'trend.ma_distance','trend.ma_relative','trend.ema_distance','trend.ema_relative'}:
            average=result_value(ema(p['h'])[i]) if '.ema_' in op else mean(window(i,p['w']))
            current=get(i)
            return _divide(current,average)-1 if op.endswith('relative') else current-average
        if op in {'trend.ma_crossover','trend.ema_crossover'}:
            if op=='trend.ma_crossover':fast,slow=mean(window(i,p['fast'])),mean(window(i,p['slow']))
            else:fast,slow=result_value(ema(p['fast'])[i]),result_value(ema(p['slow'])[i])
            return _divide(fast,slow)-1
        if op in {'trend.slope','trend.slope_tstat'}:
            slope,error=_ols(window(i,p['w']))
            return slope if op=='trend.slope' else _divide(slope,error)
        if op=='trend.efficiency_ratio':
            w=window(i,p['w']+1)
            return _divide(w[-1]-w[0],sum(abs(b-a) for a,b in zip(w,w[1:])),'ZERO_PATH_LENGTH')
        if op=='trend.breakout_position':
            w=window(i,p['w'],True)
            return _divide(get(i)-min(w),max(w)-min(w),'ZERO_RANGE')
        if op in {'momentum.skip_diff','momentum.skip_return'}:
            if i<p['k']:raise _PointFailure('INSUFFICIENT_HISTORY')
            recent,old=get(i-p['s']),get(i-p['k'])
            return recent-old if op.endswith('diff') else _divide(recent,old)-1
        if op=='momentum.sign_balance':return mean([_sign(v) for v in changes(i,p['w'])])
        if op.startswith('shock.'):
            if i<p['k']+p['w']:raise _PointFailure('INSUFFICIENT_HISTORY')
            current=change(i,p['k']);history=[change(j,p['k']) for j in range(i-p['w'],i)]
            if op=='shock.change_percentile':return 2*_rank(current,history)-1
            return (current-(mean(history) if op=='shock.change_zscore' else 0))/_sd(history,True)
        if op=='accel.slope_change':return _ols(window(i,p['w']))[0]-_ols(window(i-p['k'],p['w']))[0]
        if op.startswith('accel.'):
            basis={'accel.second_diff':'diff','accel.pct_change':'pct','accel.log_change':'log'}[op]
            return change(i,p['k'],basis)-change(i-p['k'],p['k'],basis)
        if op=='vol.ewma':return math.sqrt(result_value(ema(p['h'],'squared_change',p['basis'])[i]))
        if op in {'vol.diff_sd','vol.pct_sd','vol.log_sd'}:return _sd(changes(i,p['w'],op.split('.')[1].split('_')[0]))
        if op=='vol.change':return _sd(changes(i,p['w'],p['basis']))-_sd(changes(i-p['k'],p['w'],p['basis']))
        if op=='vol.ratio':return _divide(_sd(changes(i,p['fast'],p['basis'])),_sd(changes(i,p['slow'],p['basis'])))
        if op in {'vol.abs_change','vol.downside','vol.upside','vol.asymmetry'}:
            w=changes(i,p['w'],p['basis'])
            if op=='vol.abs_change':return mean([abs(v) for v in w])
            down=math.sqrt(mean([min(v,0)**2 for v in w]));up=math.sqrt(mean([max(v,0)**2 for v in w]))
            return down if op=='vol.downside' else up if op=='vol.upside' else _divide(down,up)
        if op=='volscale.diff':return change(i,p['k'])/_sd(changes(i,p['w']),True)
        if op=='volscale.trend':return (get(i)-mean(window(i,p['w'])))/_sd(changes(i,p['v']),True)
        if op.startswith(('distribution.','input_distribution.')):
            w=window(i,p['w']) if op.startswith('input_') else changes(i,p['w'])
            return _distribution(w,op.split('.')[1],p)
        if op.startswith('extreme.'):
            if op in {'extreme.new_high','extreme.new_low'}:
                w=window(i,p['w'],True);current=get(i)
                return int(current>max(w)) if op.endswith('high') else int(current<min(w))
            w=window(i,p['w'])
            if op=='extreme.range':return max(w)-min(w)
            if op in {'extreme.time_since_high','extreme.time_since_low'}:
                target=max(w) if op.endswith('high') else min(w)
                return len(w)-1-max(j for j,v in enumerate(w) if v==target)
            if any(v<=0 for v in w):raise _PointFailure('NONPOSITIVE_INPUT')
            peak=w[0];drawdown=0.0
            for v in w:peak=max(peak,v);drawdown=min(drawdown,v/peak-1)
            return drawdown
        if op=='persistence.diff_autocorr':
            w=changes(i,p['w']+p['a']);a,b=w[p['a']:],w[:-p['a']];ma,mb=mean(a),mean(b)
            numerator=sum((u-ma)*(v-mb) for u,v in zip(a,b))
            return _divide(numerator,math.sqrt(sum((v-ma)**2 for v in a)*sum((v-mb)**2 for v in b)),'ZERO_VARIANCE')
        if op=='persistence.sign':
            w=changes(i,p['w']+1)
            return mean([_sign(a)*_sign(b) for a,b in zip(w,w[1:])])
        if op=='persistence.sign_streak':
            sign=_sign(change(i));streak=1
            if sign==0:return 0
            for offset in range(1,p['w']):
                if i-offset<1 or _sign(change(i-offset))!=sign:break
                streak+=1
            return sign*streak
        if op=='persistence.variance_ratio':
            one=changes(i,p['w']);multi=[change(j,p['k']) for j in range(i-p['w']+p['k'],i+1)]
            return _sd(multi)**2/(p['k']*_sd(one,True)**2)
        if op=='threshold.positive_level':return int(get(i)>0)
        if op=='threshold.positive_change':return int(change(i,p['k'])>0)
        if op.startswith('threshold.'):
            w=window(i,p['w'],True);v=get(i)
            boundary=mean(w) if op.endswith('mean') else median(w) if op.endswith('median') else _quantile(w,p['q'])
            return int(v<boundary) if op=='threshold.below_quantile' else int(v>boundary)
        if op.startswith('seasonal.'):
            current=dates[i];bucket=_bucket(current,frequency)
            # Legacy seasonal exception: calendar-year lower bound, prior date
            # strictly earlier (intraday same-date points are excluded), skip nulls.
            history=[x[j] for j in range(i) if x[j] is not None and dates[j].year>=current.year-p['history_years'] and dates[j].date()<current.date() and _bucket(dates[j],frequency)==bucket]
            value=get(i)
            if len(history)<2:raise _PointFailure('INSUFFICIENT_SEASONAL_HISTORY')
            dev=value-mean(history)
            return dev if op.endswith('deviation') else dev/_sd(history,True)
        if op.startswith('price.'):
            current=get(i)
            if current<=0:raise _PointFailure('NONPOSITIVE_INPUT')
            if op=='price.oriented_new_low':
                w=window(i,p['w'],True)
                if any(v<=0 for v in w):raise _PointFailure('NONPOSITIVE_INPUT')
                return -int(current<min(w))
            if op=='price.log_return_shape':
                recent,old=get(i-p['short']),get(i-p['long'])
                if recent<=0 or old<=0:raise _PointFailure('NONPOSITIVE_INPUT')
                return (math.log(current)-math.log(recent))-(math.log(current)-math.log(old))
            w=window(i,p['w']+1);old=get(i-p['k'])
            if old<=0 or any(v<=0 for v in w):raise _PointFailure('NONPOSITIVE_INPUT')
            returns=[math.log(b)-math.log(a) for a,b in zip(w,w[1:])]
            return (math.log(current)-math.log(old))/_sd(returns,True)
        raise ExecutionFailure('registered operator has no implementation: '+op)
    return [attempt(lambda i=i:point(i)) for i in range(n)]
