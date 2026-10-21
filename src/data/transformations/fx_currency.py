"""Frozen currency-versus-reference close prices; legacy instrument IDs are unchanged."""
from . import fx
from .contracts import ContractError
from .identity import digest

PROFILE = 'fx_currency_price.1.0.0'
REFERENCES = ('USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD')
CURRENCIES = tuple(sorted({'USD', *fx.SOURCE_BY_CURRENCY}))
SCOPE_IDS = tuple('FX_CCY_VS_' + currency for currency in REFERENCES)


def members(reference_currency):
    if reference_currency not in REFERENCES:
        raise ContractError('Unsupported currency reference')
    return [currency + reference_currency for currency in CURRENCIES if currency != reference_currency]


def instrument_spec(instrument_id):
    if not isinstance(instrument_id, str) or len(instrument_id) != 6:
        raise ContractError('An explicit currency/reference pair is required')
    base, quote = instrument_id[:3], instrument_id[3:]
    if quote not in REFERENCES or base not in CURRENCIES or base == quote:
        raise ContractError('Currency exposure is outside the frozen seven-reference inventory')
    sources = sorted({fx.SOURCE_BY_CURRENCY[c] for c in (base, quote) if c != 'USD'})
    method = ('direct' if sources == [base + '/' + quote] else
              'inverse' if sources == [quote + '/' + base] else 'usd_triangulation')
    return {'instrument_id': instrument_id, 'economic_id': 'FX_' + base + '_' + quote,
            'base_currency': base, 'quote_currency': quote, 'unit': quote + '_per_' + base,
            'method': method, 'source_symbols': sources}


def recipe(instrument_id, source_metadata, alignment_policy):
    spec = instrument_spec(instrument_id)
    metadata = {s: fx.normalize_metadata(s, source_metadata[s]) for s in spec['source_symbols']}
    alignment = fx.normalize_alignment_policy(alignment_policy)
    if alignment['mode'] == 'single_source_observation' and spec['method'] == 'usd_triangulation':
        raise ContractError('A cross requires explicit alignment approval')
    body = {'kind': 'currency_reference_fx_price', 'version': '1.0.0', **spec,
            'formula': 'P_C_R=U_C/U_R; U_C=USD per C; U_USD=1',
            'arithmetic': 'decimal_50_then_binary64_guard', 'sources': metadata,
            'normalization': {s: 'reciprocal' if s.startswith('USD/') else 'identity' for s in metadata},
            'direct_source_retention': spec['method'] == 'direct', 'fallback': 'none',
            'missing': 'retain_null', 'nonpositive': 'retain_null', 'alignment_policy': alignment}
    return {'id': 'FXRECIPE_' + digest(body), 'version': '1.0.0', 'body': body}


def construct_prices(instrument_id, sources, *, alignment_policy, source_metadata):
    spec = instrument_spec(instrument_id)
    bound = recipe(instrument_id, source_metadata, alignment_policy)
    if type(sources) is not dict or set(sources) - set(fx.SOURCE_SYMBOLS):
        raise ContractError('Unexpected source outside the frozen currency inventory')
    selected = {s: sources.get(s, []) for s in spec['source_symbols']}
    prepared = fx._prepare(selected, source_metadata)
    return fx._construct(instrument_id, prepared, source_metadata, bound['body']['alignment_policy'],
                         fx._normalize_prepared(prepared), specification=spec, bound_recipe=bound)
