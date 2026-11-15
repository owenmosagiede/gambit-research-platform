#!/usr/bin/env python3
"""Publish read-only diagnostics from verified frozen P3 and P4 archives."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
from decimal import Decimal, localcontext
from functools import lru_cache
import gzip
from hashlib import sha256
from itertools import groupby
import json
from math import ceil, isclose, isfinite, sqrt
from pathlib import Path
import re
from statistics import StatisticsError, correlation, mean


SCHEMA = 'gambit_forecast_models_readout_v1'
METHODS = {'equal_weight': 'Equal weight', 'error_weight': 'Error weight',
           'ridge_reg_weight': 'Ridge regression'}
SOURCE_POLICY = 'p3_p2_window_three_models_v2'
EVALUATED_HORIZONS = (1, 7, 21)
CALENDAR = 'Scheduled weekdays'
MODEL_ID = re.compile(r'P3MODEL_[0-9a-f]{64}')
TASK_ID = re.compile(r'P3GROUP_[0-9a-f]{64}')
MAX_FORECAST_ROWS = 100_000
PORTFOLIO_POLICY = 'P4-NET-BOOK-WITH-FIXED-DEAD-ZONE-v1'


def checksum(data):
    return sha256(data).hexdigest()


def number(value):
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError('Non-finite frozen forecast value')
    return parsed


def verified(path, expected, limit):
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError('Unsafe or oversized source: ' + path.name)
    data = path.read_bytes()
    if checksum(data) != expected:
        raise ValueError('Source hash mismatch: ' + path.name)
    return data


def scheduled_end(origin, horizon):
    day = date.fromisoformat(origin)
    if day.weekday() >= 5:
        raise ValueError('Forecast origin is outside the archived calendar')
    weeks, remainder = divmod(day.weekday() + horizon, 5)
    return (day + timedelta(days=7*weeks + remainder - day.weekday())).isoformat()


def archived_origins(first, last):
    day, end = date.fromisoformat(first), date.fromisoformat(last)
    if day > end or (end-day).days > 366:
        raise ValueError('Invalid archived evaluation period')
    return [(day+timedelta(days=i)).isoformat() for i in range((end-day).days+1)
            if (day+timedelta(days=i)).weekday() < 5]


def read_models(fit):
    if fit['schema_version'] != 'p3_fit/2.0.0' or fit['policy'] != SOURCE_POLICY:
        raise ValueError('Unsupported frozen P3 fit contract')
    models, tasks = {}, {}
    for horizon, roster in fit['models_by_horizon'].items():
        for model in roster:
            identity, task = model['id'], model['group_id']
            if (not MODEL_ID.fullmatch(identity) or identity in models or not TASK_ID.fullmatch(task)
                    or model['method'] not in METHODS or model['horizon'] != int(horizon)
                    or model['mode'] != 'CS' or model['basis'] != 'relative_to_scope_mean'
                    or len(model['targets']) < 2 or set(model['scope']['members']) != set(model['targets'])):
                raise ValueError('Unsupported or duplicate model identity in the archived fit')
            key = {field: model[field] for field in ('scope', 'targets', 'horizon', 'mode', 'basis')}
            if tasks.setdefault(task, key) != key:
                raise ValueError('Incompatible targets or membership share a task ID')
            models[identity] = model
    return models, tasks


def read_forecasts(path, models, origins):
    forecasts = defaultdict(dict)
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        rows = csv.DictReader(stream)
        expected = {'model_id', 'horizon', 'scope', 'method', 'forecast_date', 'pair', 'expected_relative_return'}
        if set(rows.fieldnames or []) != expected or len(rows.fieldnames) != len(expected):
            raise ValueError('Unsupported forecast ledger columns')
        for count, row in enumerate(rows, 1):
            model = models[row['model_id']]
            origin, instrument = row['forecast_date'], row['pair']
            key = (origin, instrument)
            model_rows = forecasts[model['id']]
            if (count > MAX_FORECAST_ROWS or int(row['horizon']) != model['horizon']
                    or model['horizon'] not in EVALUATED_HORIZONS or row['scope'] != model['scope']['id']
                    or row['method'] != model['method'] or origin not in origins
                    or instrument not in model['targets'] or key in model_rows):
                raise ValueError('Forecast has an incompatible origin, model, instrument or target horizon')
            model_rows[key] = number(row['expected_relative_return'])*10000
    return forecasts


def target_outcomes(task, panel, index, origin, endpoint):
    """Use the archived quote-oriented closes for the full saved membership."""
    if origin not in index or endpoint not in index:
        return None
    bounds = index[origin], index[endpoint]
    values = {}
    with localcontext() as context:
        context.prec = 50
        for instrument in task['targets']:
            closes = panel['pair_closes'][instrument]
            opening, closing = (closes[i] for i in bounds)
            if opening is None or closing is None:
                return None
            left, right = Decimal(opening), Decimal(closing)
            if not left.is_finite() or not right.is_finite() or min(left, right) <= 0:
                raise ValueError('Archived close is not a positive finite price')
            values[instrument] = float(right/left-1)
    average = mean(values.values())
    return {instrument: (value-average)*10000 for instrument, value in values.items()}


def evaluation_rows(task, forecasts, origins, closes, coverage_end):
    symbols = sorted(task['targets'])
    for origin in reversed(origins):
        endpoint = scheduled_end(origin, task['horizon'])
        observed = {symbol: forecasts.get((origin, symbol)) for symbol in symbols}
        complete = all(value is not None for value in observed.values())
        targets = closes(origin, endpoint) if endpoint <= coverage_end and complete else None
        if complete and abs(sum(observed.values())) > 1e-5:
            raise ValueError('Saved forecasts do not match the declared relative return basis')
        for symbol in symbols:
            forecast = observed[symbol]
            status = ('unavailable_forecast' if forecast is None else
                      'pending_outcome' if endpoint > coverage_end else
                      'excluded_incomplete_scope' if not complete else
                      'missing_outcome' if targets is None else 'matched')
            realized = targets[symbol] if status == 'matched' else None
            yield {'instrument': symbol, 'origin': origin, 'target_end': endpoint,
                   'forecast_bps': forecast, 'realized_bps': realized,
                   'error_bps': realized-forecast if realized is not None else None, 'status': status}


def ranks(values):
    ranked = [0.0] * len(values)
    order = sorted(range(len(values)), key=values.__getitem__)
    start = 1
    for _, tied in groupby(order, key=values.__getitem__):
        indices = list(tied)
        for index in indices:
            ranked[index] = start + (len(indices)-1)/2
        start += len(indices)
    return ranked


def correlate(left, right):
    try:
        return correlation(left, right)
    except StatisticsError:
        return None


def calibration_bins(rows):
    ordered = sorted(rows, key=lambda row: row['forecast_bps'])
    if len(ordered) < 6 or ordered[0]['forecast_bps'] == ordered[-1]['forecast_bps']:
        return []
    groups, current = [], []
    for _, tied in groupby(ordered, key=lambda row: row['forecast_bps']):
        current.extend(tied)
        if len(current) >= ceil(len(ordered)/6):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [{'forecast': mean(r['forecast_bps'] for r in group),
             'realized': mean(r['realized_bps'] for r in group), 'count': len(group)} for group in groups]


def histogram(errors):
    if not errors:
        return []
    extent = max(map(abs, errors))
    if extent == 0:
        return [dict(low=0, high=0, count=len(errors))]
    width = extent*2/9
    counts = [0]*9
    for error in errors:
        counts[min(8, int((error+extent)/width))] += 1
    return [dict(low=-extent+i*width, high=-extent+(i+1)*width, count=count) for i,count in enumerate(counts)]


def diagnostics(rows, view):
    matched = [row for row in rows if row['status'] == 'matched']
    by_date = defaultdict(list)
    for row in matched:
        by_date[row['origin']].append(row)
    errors = [row['error_bps'] for row in matched]
    x = [row['forecast_bps'] for row in matched]
    y = [row['realized_bps'] for row in matched]
    if view == 'CS':
        daily = [(origin, correlate(ranks([r['forecast_bps'] for r in day]),
                                    ranks([r['realized_bps'] for r in day])))
                 for origin, day in sorted(by_date.items())]
        quality = [item for item in daily if item[1] is not None]
        score = mean(v for _, v in quality) if quality else None
        score_name = 'Mean rank IC'
        score_reason = 'No completed date has enough distinct forecast and outcome ranks.'
        rolling_name = 'Rolling rank IC'
    elif view == 'TS' and len({row['instrument'] for row in rows}) == 1:
        score = correlate(x, y)
        quality = [(origin, mean(abs(r['error_bps']) for r in day)) for origin, day in sorted(by_date.items())]
        score_name, rolling_name = 'Forecast correlation', 'Rolling MAE'
        score_reason = 'No sufficiently varied paired forecasts and outcomes.'
    else:
        score, quality = None, []
        score_name, rolling_name = 'Forecast quality', 'Rolling forecast quality'
        score_reason = 'No diagnostic contract is available for this forecast view.'
    intercept_slope = None
    if len(x) >= 2 and min(x) != max(x):
        avg_x, avg_y = mean(x), mean(y)
        intercept_slope = sum((a-avg_x)*(b-avg_y) for a,b in zip(x,y,strict=True))/sum((a-avg_x)**2 for a in x)
    coverage = [len(day) for day in by_date.values()]
    return {
        'metric_values': [
            {'label': score_name, 'value': score, 'unit': None, 'note': score_reason if score is None else
             (f'Equal-weight mean of {len(quality)} valid date ranks' if view == 'CS' else 'Pearson correlation through time')},
            {'label':'RMSE','value':sqrt(mean(error**2 for error in errors)) if errors else None,
             'unit':'bps','note':'Root mean squared error across matched rows' if errors else 'No matched outcomes.'},
            {'label':'MAE','value':mean(map(abs,errors)) if errors else None,'unit':'bps',
             'note':'Mean absolute error across matched rows' if errors else 'No matched outcomes.'},
            {'label':'Calibration slope','value':intercept_slope,'unit':None,
             'note':'Realized return regressed on forecast, with an intercept' if intercept_slope is not None else
             'Requires at least two forecasts with distinct values.'},
        ],
        'counts': dict(Counter(row['status'] for row in rows)),
        'dates': len(by_date), 'quality_dates': len(quality),
        'breadth': [min(coverage),max(coverage)] if coverage else [],
        'mean_error': mean(errors) if errors else None,
        'rolling': {'label': rolling_name, 'window':21,
                    'points':[dict(origin=quality[i][0],value=mean(v for _,v in quality[i-20:i+1]))
                              for i in range(20,len(quality))]},
        'calibration': calibration_bins(matched),
        'histogram': histogram(errors),
    }


def resolve_labels(research_root):
    if research_root is None:
        return lambda ref: ref['id']
    from api.research_labels import recipe_label
    from data.feature_store import FeatureStore, PublicationError

    store = FeatureStore(research_root)

    @lru_cache(maxsize=512)
    def label(identifier, version, digest):
        binding = {'id':identifier,'version':version,'content_sha256':digest}
        try:
            return recipe_label(store.resolve(binding))
        except (OSError, KeyError, PublicationError):
            return identifier

    return lambda ref: label(ref['id'],ref['version'],ref['content_sha256'])


def model_inputs(model, constituents, describe):
    combination = model['combination']
    if combination['status'] not in ('fitted','unavailable'):
        raise ValueError('Invalid saved combination status')
    weights = combination.get('weights') if combination['status']=='fitted' else [None]*len(model['relationships'])
    rows = []
    for relationship, weight in zip(model['relationships'], weights, strict=True):
        signal = constituents[relationship['id']]
        if signal['relationship'] != relationship or signal['targets'] != model['targets'] or signal['scope'] != model['scope']:
            raise ValueError('Frozen constituent identity differs from the model')
        rows.append({
            'label':describe(signal['recipe']), 'recipe':signal['recipe'],
            'relationship':relationship,'validation':signal['validation'],'trial':signal['trial'],
            'feature_refs':signal['features'],'alignment_policy':signal['alignment_policy'],
            'calibration':signal['mapping'],'influence':number(weight) if weight is not None else None,
        })
    return rows


def dump(path, value):
    data = (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',',':'))+'\n').encode()
    path.write_bytes(data)
    return checksum(data)


def portfolio_performance(path, digest, manifest, models, forecasts, market_dates):
    if path is None and digest is None:
        return {}
    if path is None or not re.fullmatch(r'[a-f0-9]{64}', digest or ''):
        raise ValueError('A portfolio report and its verified SHA-256 are required together')
    report = json.loads(verified(path, digest, 512_000))
    if (report['fit'] != manifest['fit'] or report['period'] != manifest['period']
            or report['fx_snapshot'] != manifest['price_snapshot']['id']
            or report['close_panel_sha256'] != manifest['input_sha256']
            or report['forecast_sha256'] != manifest['files']['p4-forecasts.csv.gz']
            or report['market_dates'] != len(market_dates) or report['policy']['id'] != PORTFOLIO_POLICY
            or report['one_way_cost'] != 0.0001 or report['gross_cap'] != 2.0
            or report['broker_execution_verified'] is not False):
        raise ValueError('Portfolio report differs from the verified replay or portfolio benchmark')
    results = {}
    for row in report['models']:
        model_id = row['model_id']
        model = models.get(model_id)
        if (model_id not in forecasts or model_id in results or row['method'] != model['method']
                or row['horizon'] != model['horizon'] or row['reference'] != model['scope']['reference_currency']):
            raise ValueError('Portfolio report contains an incompatible or duplicate model')
        baseline = row['net']
        net, gross, turnover = (number(baseline[key]) for key in ('net_pnl','gross_pnl','total_turnover'))
        if (turnover < 0 or baseline['blocked_orders'] != 0
                or not isclose(net, gross - turnover * report['one_way_cost'], rel_tol=0, abs_tol=1e-12)):
            raise ValueError('Saved portfolio return does not reconcile with executed notional and costs')
        results[model_id] = {
            'net_return_fraction': net, 'period': report['period'], 'one_way_cost': report['one_way_cost'],
            'gross_cap': report['gross_cap'], 'report_policy': PORTFOLIO_POLICY, 'variant': 'net', 'report_sha256': digest,
        }
    if results.keys() != forecasts.keys():
        raise ValueError('Portfolio report and archived forecasts cover different models')
    return results


def build(fit_path, archive, manifest_hash, output, research_root=None, portfolio_report=None, portfolio_report_hash=None):
    manifest = json.loads(verified(archive/'p4-run-manifest.json',manifest_hash,64_000))
    fit = json.loads(verified(fit_path,manifest['fit_sha256'],10_000_000))
    panel = json.loads(verified(archive/'p4-inputs.json',manifest['input_sha256'],12_000_000))
    forecast_hash = manifest['files']['p4-forecasts.csv.gz']
    archive_forecasts = archive/'p4-forecasts.csv.gz'
    verified(archive_forecasts,forecast_hash,5_000_000)
    if (fit['id'] != manifest['fit'] or fit['id'] != panel['fit_id'] or panel['extension'] != manifest['price_snapshot']
            or panel['fit_sha256'] != manifest['fit_sha256'] or panel['kind'] != 'p4_frozen_fx_inputs'):
        raise ValueError('Archived forecasts and price inputs are from different fit or snapshot identities')
    first, last = manifest['period']
    origins = archived_origins(first,last)
    market_dates = panel['market_dates']
    if (panel['score_dates'] != origins or market_dates != sorted(set(market_dates))
            or market_dates[-1] != last or first < fit['fit_period']['end_exclusive']):
        raise ValueError('Forecast calendar or label availability differs from the archive')
    index = {origin: pos for pos,origin in enumerate(market_dates)}
    models,tasks = read_models(fit)
    forecasts = read_forecasts(archive_forecasts,models,set(origins))
    performance = portfolio_performance(portfolio_report, portfolio_report_hash, manifest, models, forecasts, origins)
    constituents = {row['relationship']['id']:row for row in fit['constituents']}
    if len(constituents) != len(fit['constituents']):
        raise ValueError('Duplicate saved relationships')
    describe = resolve_labels(research_root)

    output.mkdir(exist_ok=False)
    catalog = []
    digests = {}
    for task_id, task in sorted(tasks.items(),key=lambda pair:(pair[1]['horizon'],pair[1]['scope']['reference_currency'],pair[0])):
        quote = task['scope']['reference_currency']
        summary = {'id':task_id,'title':f"{quote} Universe · {task['horizon']}D",
                   'horizon':task['horizon'],'scope':task['scope'],'view':task['mode'],'calendar':CALENDAR,
                   'target_label':'Simple FX return relative to the saved universe mean','unit':'bps',
                   'instruments':len(task['targets']),'methods':[]}
        candidates = [model for model in models.values() if model['group_id']==task_id]
        if len({model['method'] for model in candidates}) != len(candidates):
            raise ValueError('The archived version contains ambiguous candidates for a method')
        @lru_cache(maxsize=366)
        def closes(origin, endpoint):
            return target_outcomes(task,panel,index,origin,endpoint)
        for model in sorted(candidates,key=lambda row:list(METHODS).index(row['method'])):
            model_id, method, fit_state = model['id'], model['method'], model['combination']
            summary['methods'].append({'id':model_id,'label':METHODS[method],'method':method,'status':fit_state['status'],
                                       'has_evaluation':model_id in forecasts})
            rows = list(evaluation_rows(task,forecasts[model_id],origins,closes,last)) if model_id in forecasts else []
            record = {
                'schema':SCHEMA,'task_id':task_id,'model_id':model_id,'method':method,
                'fit_id':fit['id'],'model_version':None,'saved_policy':fit['policy'],'fit_status':fit_state['status'],
                'fit_reason':fit_state.get('reason'),'intercept_bps':None if 'intercept' not in fit_state else number(fit_state['intercept'])*10000,
                'training':{'bounds':fit['fit_period'],'fit_evidence':{k:v for k,v in fit_state.items() if k not in ('weights','intercept')},
                            'availability':'Paired training predictions and outcomes were not retained in this fit archive.'},
                'evaluation':{'bounds':[first,last] if rows else None,'rows':rows,'diagnostics':diagnostics(rows,task['mode']),
                              'availability':None if rows else 'No saved evaluation forecasts for this model.',
                              'portfolio':performance.get(model_id)},
                'inputs':model_inputs(model,constituents,describe),
                'lineage':{'fit_sha256':manifest['fit_sha256'],'source_snapshot':manifest['price_snapshot'],
                           'forecast_stream_sha256':forecast_hash if rows else None,'evaluation_archive_sha256':manifest_hash if rows else None,
                           'archived_model_schema':fit['schema_version'],'weight_training':fit['weight_training'],
                           'targets_by_instrument':model['targets'],'market_price_references':{
                               symbol:panel['price_lineage'][symbol] for symbol in model['targets'] if symbol in panel['price_lineage']},
                           'model_version':None,'forecast_run_id':None,'per_forecast_available_at':None,
                           'saved_code_reference':manifest['feature_replay_script_sha256'] if rows else None},
            }
            digests[model_id] = dump(output/(model_id+'.json'),record)
        catalog.append(summary)
    dump(output/'index.json', {'schema':SCHEMA,'archived_through':last,'tasks':catalog,'model_hashes':digests})
    return {'tasks':len(catalog),'candidates':len(digests),'evaluation_models':len(forecasts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--research-root',type=Path)
    parser.add_argument('--portfolio-report',type=Path)
    parser.add_argument('--portfolio-report-sha256')
    args=parser.parse_args()
    print(json.dumps(build(args.fit,args.archive,args.manifest_sha256,args.output,args.research_root,
                           args.portfolio_report,args.portfolio_report_sha256)))


if __name__ == '__main__':
    main()
