"""Human labels derived from immutable metadata; never scientific identities."""


def recipe_label(record):
    body = record['body']
    recipe = body.get('recipe', body)
    steps = recipe.get('steps', [])
    if not steps:
        return record.get('display_name', record['id'])
    final = steps[-1]
    operator = final['operator']['id']
    params = {p['name']: p['value']['value'] for p in final['parameters']}
    log = steps[0]['operator']['id'] == 'TR_BASE_level_log'
    # The approved FX chains use the daily grid. Other definitions retain their
    # own display names rather than acquiring an inferred daily interpretation.
    if not log or not recipe.get('input_contract', {}).get('source_profile', '').startswith('fx_'):
        return record.get('display_name', record['id'])
    labels = {
        'TR_BASE_change_diff': lambda: f"{params['k']}-day log momentum",
        'TR_BASE_momentum_skip_diff': lambda: f"{params['k']}-day log momentum, skip {params['s']} days",
        'TR_BASE_smooth_ew_change': lambda: f"Smoothed log momentum, {params['h']}-day half-life",
        'TR_BASE_trend_ema_distance': lambda: f"Log-price EMA distance, {params['h']}-day half-life",
        'TR_BASE_trend_ma_distance': lambda: f"{params['w']}-day log-price moving-average distance",
        'TR_BASE_trend_slope': lambda: f"{params['w']}-day log-price trend slope",
        'TR_BASE_trend_slope_tstat': lambda: f"{params['w']}-day log-price trend t-statistic",
        'TR_BASE_volscale_diff': lambda: f"{params['k']}-day volatility-scaled momentum, {params['w']}-day volatility",
        'TR_BASE_volscale_trend': lambda: f"{params['w']}-day volatility-scaled trend, {params['v']}-day volatility",
    }
    return labels[operator]() if operator in labels else record.get('display_name', record['id'])


def scope_label(record):
    body=record.get('body',{})
    # Read only the definition's frozen member identities. Currency Scopes use
    # one common quote; their display name need not leak the registry ID.
    members=body.get('entity_ids',[])
    if body.get('kind')=='universe' and members:
        parts=[value.split('_') for value in members]
        if all(len(value)==3 and value[0]=='FX' and len(value[1])==len(value[2])==3 for value in parts):
            quotes={value[2] for value in parts}
            if len(quotes)==1 and record['id']=='FX_CCY_VS_'+next(iter(quotes)):
                return next(iter(quotes))+' pairs'
    return record.get('display_name', record['id'])
