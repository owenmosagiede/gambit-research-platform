"""Provider-independent forward return constructor.

Prices are selected at the outcome knowledge cutoff, never at the prediction
anchor. Historical training eligibility is a separate label-availability check.
Source rows remain upstream; results carry exact references to every operand.
"""
from copy import deepcopy
from decimal import Decimal, DecimalException, localcontext
import math

from data.pit_selection import select_asof
from data.transformations.contracts import (
    ContractError, decimal_text, normalize_input, normalize_time, object_fields,
)
from data.transformations.identity import digest, reference
from .contracts import (
    SCHEMA_VERSION, DefinitionError, SourceIneligible, validate_definition,
    validate_policy, validate_observation,
)
from .scheduling import validate_schedule, resolve_intervals, temporal_eligible, add_duration


def _economic_eligibility(source, binding, basis, body, schedule, outcome):
    """Validate certified economic meaning before any numeric return is formed."""
    object_fields(source, {'series', 'economics', 'periods'}, path='Target canonical source')
    economic = validate_policy(source['economics'], kind='economic_source')
    econ = economic['body']
    if reference(economic) != binding['economic_policy']:
        raise SourceIneligible('Source economic policy is not the definition-pinned certification')
    series = normalize_input(source['series'])
    if series.get('execution') is not None:
        raise SourceIneligible('Target adapter accepts canonical upstream investment source data, not a Feature execution')
    if series['source_view'] != binding['source_view'] or econ['source_view'] != binding['source_view']:
        raise SourceIneligible('Canonical SourceView does not match definition and certification')
    if series['selection'] != binding['selection'] or econ['selection'] != binding['selection']:
        raise SourceIneligible('Canonical source partition differs from approved instrument/measure/dimensions')
    if series['selection']['entity_id'] != econ['instrument_id']:
        raise SourceIneligible('Canonical entity must identify the certified instrument')
    for field in ('unit', 'value_semantics', 'temporal_precision', 'cadence', 'history_policy'):
        if series[field] != econ[field]:
            raise SourceIneligible(f'Canonical {field} differs from economic certification')
    if econ['instrument_class'] in {'macro', 'yield', 'spread', 'rate', 'futures'}:
        raise SourceIneligible('Raw macro, rate, yield, spread and futures price ratios are outside investment return eligibility')
    if econ['instrument_class'] == 'certified_investment_series' and econ['input_kind'] == 'price':
        raise SourceIneligible('Specialized instruments require certified wealth or period returns')
    if econ['currency'] != body['currency'] or econ['economic_coverage'] != body['economic_coverage']:
        raise SourceIneligible('Return currency or economic coverage does not match Target')
    if econ['temporal_precision'] != schedule['temporal_precision'] or econ['observation_convention'] != schedule['observation_convention']:
        raise SourceIneligible('Source precision/observation convention incompatible with schedule')
    if any(econ[field] != schedule[field] for field in ('calendar_id', 'calendar_version', 'timezone')):
        raise SourceIneligible('Source certified calendar and timezone differ from scheduled economic intervals')
    if econ['instrument_class'] == 'spot_fx':
        if not econ['base_currency'] or not econ['quote_currency'] or econ['base_currency'] == econ['quote_currency']:
            raise SourceIneligible('FX requires distinct explicit base and quote currencies')
        if econ['quotation_direction'] not in {'quote_per_base', 'base_per_quote'}:
            raise SourceIneligible('FX quotation direction must be explicit')
        measured_currency = econ['quote_currency'] if econ['quotation_direction'] == 'quote_per_base' else econ['base_currency']
        if measured_currency != econ['currency']:
            raise SourceIneligible('FX return currency must match the currency of the quoted price')
    elif econ['quotation_direction'] != 'not_applicable' or econ['base_currency'] is not None or econ['quote_currency'] is not None:
        raise SourceIneligible('Non-FX source must not carry unresolved FX quotation conventions')
    kind = econ['input_kind']
    if basis == 'price':
        if kind != 'price' or econ['value_semantics'] != 'price' or econ['adjustment_convention'] not in {'unadjusted_price', 'certified_price_adjustments'}:
            raise SourceIneligible('Price return requires certified price semantics and explicit adjustment convention')
        if econ['includes_income'] or econ['period_representation'] is not None:
            raise SourceIneligible('Price-only construction cannot silently include income or period returns')
    else:
        if kind not in {'wealth_index', 'period_returns'} or not econ['includes_income'] or not econ['includes_corporate_actions']:
            raise SourceIneligible('Total return requires documented income and corporate action treatment')
        if kind == 'wealth_index':
            if econ['adjustment_convention'] != 'certified_total_return' or econ['value_semantics'] != 'numeric_level' or econ['period_representation'] is not None:
                raise SourceIneligible('Total wealth index certification is incomplete or ambiguous')
        else:
            if econ['adjustment_convention'] != 'certified_period_returns' or econ['period_representation'] not in {'simple', 'log'}:
                raise SourceIneligible('Period returns require explicit return and interval conventions')
            expected = 'fractional_change' if econ['period_representation'] == 'simple' else 'log_change'
            if econ['value_semantics'] != expected or econ['period_representation'] != body['construction']['representation']:
                raise SourceIneligible('Period representation must exactly match the requested return representation')
            required_unit = 'fraction' if econ['period_representation'] == 'simple' else 'natural_log'
            if econ['unit'] != required_unit:
                raise SourceIneligible('Canonical period inputs require fraction or natural_log units; percentages are not silently rescaled')
    if econ['availability_basis'] != outcome['availability_basis']:
        raise SourceIneligible('Published, archived and ingested availability bases cannot be substituted')
    known = econ['availability_basis'] != 'unknown' and econ['availability_evidence_complete']
    if not known and outcome['unknown_availability'] == 'reject':
        raise SourceIneligible('Source historical availability is uncertified')
    if outcome['selection'] == 'first_defensible':
        if not known or econ['vintage_capability'] != 'complete_history' or 'revision_history' not in series['capabilities']:
            raise SourceIneligible('First defensible observation requires complete certified vintage history')
    elif econ['vintage_capability'] == 'complete_history' and 'revision_history' not in series['capabilities']:
        raise SourceIneligible('Complete history certification conflicts with canonical history capabilities')
    if type(source['periods']) is not dict:
        raise SourceIneligible('Canonical period interval evidence must be a lineage-indexed object')
    periods = deepcopy(source['periods'])
    lineages = [row['lineage']['id'] for row in series['observations']]
    if len(set(lineages)) != len(lineages):
        raise SourceIneligible('Each canonical source observation requires distinct exact operand lineage')
    if kind != 'period_returns' and periods:
        raise SourceIneligible('Endpoint price/wealth inputs must not carry period return intervals')
    if kind == 'period_returns':
        if set(periods) != set(lineages):
            raise SourceIneligible('Every period return requires exactly one interval evidence binding')
        for row in series['observations']:
            interval = periods[row['lineage']['id']]
            object_fields(interval, {'interval_start', 'interval_end'}, path='canonical period interval')
            for field in interval: normalize_time(interval[field], series['temporal_precision'], field)
            if interval['interval_end'] != row['reference_time'] or interval['interval_start'] >= interval['interval_end']:
                raise SourceIneligible('Period intervals must be positive and indexed at their ending mark')
    return {'series':series, 'economics':economic, 'periods':periods, 'availability_known':known}


def preflight(definition, sources, schedule, anchors, knowledge_cutoff, *,
              outcome_policy, validity_policy, schedule_policy, calculation):
    """Resolve all scientific semantics and schedule endpoints before execution."""
    definition = validate_definition(definition)
    body = definition['body']
    policies = {'outcome_policy':(outcome_policy,'outcome_selection'),
                'validity_policy':(validity_policy,'mathematical_validity'),
                'schedule_policy':(schedule_policy,'target_schedule'),
                'calculation':(calculation,'return_calculation')}
    for field, (record, kind) in policies.items():
        validate_policy(record, kind=kind)
        if reference(record) != body[field]:
            raise DefinitionError(f'{field} is not the exact definition-pinned policy')
    schedule = validate_schedule(schedule)
    semantics = schedule_policy['body']
    if schedule['policy_id'] != schedule_policy['id'] or schedule['version'] != schedule_policy['version']:
        raise DefinitionError('Resolved market schedule is not bound to its semantic policy')
    for field in ('calendar_id', 'calendar_version', 'timezone', 'observation_convention', 'temporal_precision'):
        if schedule[field] != semantics[field]:
            raise DefinitionError(f'Resolved schedule changes pinned {field}')
    if anchors.get('mode') != body['anchor_policy']['mode']:
        raise DefinitionError('Requested prediction anchor mode differs from logical definition')
    if body['anchor_policy']['mode'] == 'explicit' and anchors.get('anchor_set_id') != body['anchor_policy']['anchor_set_id']:
        raise DefinitionError('Concrete canonical anchor-set identity differs from logical definition')
    precision = schedule['temporal_precision']
    normalize_time(knowledge_cutoff, precision, 'knowledge_cutoff')
    outcome = outcome_policy['body']
    required_precision = 'conservative_date_boundary' if precision == 'date' else 'exact_timestamp'
    if outcome['label_precision_policy'] != required_precision:
        raise DefinitionError('Outcome precision policy cannot invent intraday evidence')
    if precision == 'date' and outcome['finalization_wait']['unit'] != 'calendar_days':
        raise DefinitionError('Date-only outcomes cannot support elapsed finalization durations')
    intervals = resolve_intervals(schedule, anchors, body['entry'], body['horizon'], body['endpoint'])
    if type(sources) is not dict or set(sources) != {s['role'] for s in body['sources']}:
        raise SourceIneligible('Canonical source roles differ from definition')
    normalized = {}
    for binding in body['sources']:
        role = binding['role']
        basis = body['construction'][role + '_basis']
        normalized[role] = _economic_eligibility(sources[role], binding, basis, body, schedule, outcome)
    return {'definition':definition, 'sources':normalized, 'schedule':schedule,
            'anchors':deepcopy(anchors), 'intervals':intervals,
            'knowledge_cutoff':knowledge_cutoff, 'outcome_policy':deepcopy(outcome_policy),
            'validity_policy':deepcopy(validity_policy), 'schedule_policy':deepcopy(schedule_policy),
            'calculation':deepcopy(calculation), 'temporal_precision':precision}


def _state(source, cutoff, selection):
    rows = source['series']['observations']
    if selection == 'first_defensible':
        first = {}
        for row in rows:
            key = row['reference_time']
            if key not in first or row['available_at'] < first[key]['available_at']:
                first[key] = row
        rows = list(first.values())
    return select_asof(rows, cutoff)


def _operand(row, role, period=None):
    return {'role':role, 'reference_time':row['reference_time'], 'available_at':row['available_at'],
            'vintage_id':row['vintage_id'], 'lineage':row['lineage'],
            'interval_start':period['interval_start'] if period else None,
            'interval_end':period['interval_end'] if period else None}


def _row_failure(rows):
    for row in rows:
        if row['status'] != 'valid':
            return ('missing' if row['status'] == 'missing' else 'invalid',
                    'SOURCE_MISSING' if row['status'] == 'missing' else 'SOURCE_INVALID')
    return None


def _ratio(start, end, representation, zero_allowed):
    if start <= 0: return None, 'NONPOSITIVE_START'
    if end < 0: return None, 'NEGATIVE_END'
    if representation == 'log' and end == 0: return None, 'NONPOSITIVE_LOG_INPUT'
    if end == 0 and not zero_allowed: return None, 'ZERO_TERMINAL_NOT_CERTIFIED'
    ratio = end / start
    return (ratio - 1 if representation == 'simple' else ratio.ln()), None


def _calculate_source(source, interval, cutoff, outcome, representation):
    """Return (value, status, reason, selected operand evidence)."""
    entry, exit = interval['entry_time'], interval['exit_time']
    state = _state(source, cutoff, outcome['selection'])
    econ, operands = source['economics']['body'], []
    if econ['input_kind'] != 'period_returns':
        by_time = {row['reference_time']:row for row in state}
        selected = []
        for point, role in ((entry, 'entry'), (exit, 'exit')):
            row = by_time.get(point)
            if row is None:
                has_later = any(r['reference_time'] == point and r['available_at'] > cutoff for r in source['series']['observations'])
                return None, 'pending' if has_later else 'missing', 'ENDPOINT_NOT_AVAILABLE' if has_later else 'MISSING_ENDPOINT', operands
            selected.append(row); operands.append(_operand(row, role))
        failure = _row_failure(selected)
        if failure: return None, *failure, operands
        value, reason = _ratio(Decimal(selected[0]['value']), Decimal(selected[1]['value']), representation, econ['zero_terminal_allowed'])
        return value, 'invalid' if reason else 'valid', reason, operands
    selected = []
    for row in state:
        period = source['periods'][row['lineage']['id']]
        if period['interval_start'] < exit and period['interval_end'] > entry:
            selected.append((period['interval_start'], period['interval_end'], row, period))
    selected.sort(key=lambda v:(v[0],v[1],v[2]['lineage']['id']))
    operands = [_operand(row, 'period', period) for _,_,row,period in selected]
    def missing_component(start, end):
        for row in source['series']['observations']:
            period = source['periods'][row['lineage']['id']]
            if row['available_at'] > cutoff and period['interval_start'] < end and period['interval_end'] > start:
                return None, 'pending', 'ENDPOINT_NOT_AVAILABLE', operands
        return None, 'missing', 'PERIOD_GAP', operands
    position = entry
    for start,end,row,_ in selected:
        if start < entry or end > exit:
            return None, 'invalid', 'PERIOD_BOUNDARY_MISMATCH', operands
        if start < position:
            return None, 'invalid', 'PERIOD_OVERLAP', operands
        if start > position:
            return missing_component(position, start)
        position = end
    if position != exit:
        return missing_component(position, exit)
    failure = _row_failure([item[2] for item in selected])
    if failure: return None, *failure, operands
    value = Decimal(1) if representation == 'simple' else Decimal(0)
    for _,_,row,_ in selected:
        component = Decimal(row['value'])
        if representation == 'simple':
            if component < -1: return None, 'invalid', 'INVALID_PERIOD_RETURN', operands
            if component == -1 and not econ['zero_terminal_allowed']:
                return None, 'invalid', 'ZERO_TERMINAL_NOT_CERTIFIED', operands
            value *= 1 + component
        else:
            value += component
    return (value - 1 if representation == 'simple' else value), 'valid', None, operands


def construct(definition, sources, schedule, anchors, knowledge_cutoff, *,
              outcome_policy, validity_policy, schedule_policy, calculation):
    """Construct all requested rows, including explicit pending/missing/invalids."""
    context = preflight(definition, sources, schedule, anchors, knowledge_cutoff,
                        outcome_policy=outcome_policy, validity_policy=validity_policy,
                        schedule_policy=schedule_policy, calculation=calculation)
    definition = context['definition']; body = definition['body']
    outcome = context['outcome_policy']['body']; precision = context['temporal_precision']
    instrument = context['sources']['instrument']['economics']['body']
    observations = []
    for interval in context['intervals']:
        selected_sources, source_results, failures = [], {}, []
        pending_future = interval['exit_time'] > knowledge_cutoff
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            for role, source in sorted(context['sources'].items()):
                value, status, reason, operands = None, 'pending', 'FUTURE_ENDPOINT', []
                if not pending_future:
                    try:
                        value, status, reason, operands = _calculate_source(source, interval, knowledge_cutoff, outcome, body['construction']['representation'])
                        if value is not None and (not value.is_finite() or not math.isfinite(float(value))):
                            value, status, reason = None, 'invalid', 'NONFINITE_OUTPUT'
                    except (DecimalException, OverflowError):
                        # Pointwise numerical domain failure is controlled. All
                        # other exceptions propagate as unexpected execution errors.
                        value, status, reason, operands = None, 'invalid', 'NONFINITE_OUTPUT', []
                if status != 'valid': failures.append((status,reason))
                source_results[role] = value
                selected_sources.append({'role':role, 'source_view':source['series']['source_view'],
                    'source_snapshots':source['series']['source_snapshots'],
                    'economic_policy':reference(source['economics']), 'provenance':source['series']['provenance'],
                    'operands':operands})
            if failures:
                priority = {'invalid':0,'missing':1,'pending':2}
                status, reason = sorted(failures,key=lambda item:priority[item[0]])[0]
                value = None
            else:
                status, reason = 'valid', None
                value = source_results['instrument']
                if body['construction']['basis'] == 'benchmark_excess':
                    value -= source_results['benchmark']
                if not value.is_finite() or not math.isfinite(float(value)):
                    value, status, reason = None, 'invalid', 'NONFINITE_OUTPUT'
        availability = [operand['available_at'] for source in selected_sources for operand in source['operands']]
        availability_known = all(source['availability_known'] for source in context['sources'].values())
        source_available = max(availability) if availability and availability_known else None
        label_available = None
        if source_available is not None and status == 'valid':
            label_available = add_duration(max(interval['exit_time'], source_available),
                                           outcome['finalization_wait'], precision, schedule['timezone'])
            if label_available > knowledge_cutoff:
                value, status, reason = None, 'pending', 'FINALIZATION_PENDING'
        row = {'schema_version':SCHEMA_VERSION, 'record_type':'target_observation',
               'target':reference(definition), 'instrument_id':instrument['instrument_id'],
               'investment_series_id':instrument['investment_series_id'],
               'prediction_anchor':interval['prediction_anchor'], 'anchor_id':interval['anchor_id'],
               'temporal_precision':precision, 'entry_time':interval['entry_time'],
               'intended_end':interval['intended_end'], 'exit_time':interval['exit_time'],
               'horizon':body['horizon'], 'value':None if value is None else decimal_text(value),
               'unit':body['unit'], 'currency':body['currency'], 'status':status, 'reason_code':reason,
               'selected_sources':selected_sources, 'source_availability':source_available,
               'outcome_selection_cutoff':knowledge_cutoff, 'label_available_at':label_available,
               'historical_eligibility_certified':status == 'valid' and availability_known,
               'availability_basis':outcome['availability_basis'],
               'label_precision_policy':outcome['label_precision_policy'],
               'economic_coverage':body['economic_coverage']}
        row['id'] = 'TARGETOBS_' + digest(row)
        observations.append(validate_observation(row))
    return {'definition':reference(definition), 'temporal_precision':precision,
            'observations':observations, 'schedule_evidence':context['intervals']}


def historical_rows(observations, training_cutoff, *, cutoff_precision=None):
    """Return only certified labels usable at the caller's explicit training cutoff."""
    eligible = []
    for original in observations:
        row = validate_observation(original)
        precision = cutoff_precision or row['temporal_precision']
        normalize_time(training_cutoff, precision, 'training_cutoff')
        if row['status'] != 'valid' or not row['historical_eligibility_certified']:
            continue
        if temporal_eligible(row['label_available_at'], row['temporal_precision'], training_cutoff,
                             precision, policy='strict')['eligible']:
            eligible.append(row)
    return eligible
