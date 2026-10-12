"""Executable Target 0.4 contracts; historical 0.2 drafts remain immutable.

The source certification is an independent registry policy, not a formula inferred
from a provider name or numeric values. Definitions pin that policy and exact
source selection. Actual observations, coverage and anchors belong to immutable
materializations, not logical identity.
"""
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from jsonschema import Draft202012Validator

from data.transformations.contracts import (
    ContractError, choice, object_fields, token, text, normalize_reference,
    normalize_references, normalize_selection, normalize_time, normalize_cadence,
    canonical_decimal, VALUE_SEMANTICS, VERSION,
)
from data.transformations.identity import digest, reference

SCHEMA_VERSION = '0.4.0'
IDENTITY_PROFILE = 'target_return.1.0.0'
CALCULATION_VERSION = '1.0.0'
AVAILABILITY_BASES = {'first_published', 'first_archived', 'first_ingested', 'unknown'}
REASONS = {
    'FUTURE_ENDPOINT', 'FINALIZATION_PENDING', 'MISSING_ENDPOINT',
    'ENDPOINT_NOT_AVAILABLE', 'SOURCE_MISSING', 'SOURCE_INVALID',
    'NONPOSITIVE_START', 'NEGATIVE_END', 'ZERO_TERMINAL_NOT_CERTIFIED',
    'NONPOSITIVE_LOG_INPUT', 'NONFINITE_OUTPUT', 'PERIOD_GAP', 'PERIOD_OVERLAP',
    'PERIOD_BOUNDARY_MISMATCH', 'INVALID_PERIOD_RETURN',
}


class DefinitionError(ContractError):
    """Invalid or unresolved scientific definition."""


class SourceIneligible(ContractError):
    """Canonical source lacks compatible certified economic semantics."""


@lru_cache(maxsize=1)
def _schema_validator():
    schema = Path(__file__).resolve().parents[3] / 'specs/schemas/target_store.schema.json'
    value = json.loads(schema.read_text())
    Draft202012Validator.check_schema(value)
    return Draft202012Validator(value)


def validate_schema(record):
    errors = sorted(_schema_validator().iter_errors(record), key=lambda error:str(error.path))
    if errors:
        raise ContractError('Target 0.4 structural schema: ' + errors[0].message)
    return record


def _boolean(value, field):
    if type(value) is not bool:
        raise ContractError(f'{field}: expected boolean')
    return value


def _nullable_token(value, field):
    return None if value is None else token(value, field)


def _wait(value):
    object_fields(value, {'amount', 'unit'}, path='finalization_wait')
    if type(value['amount']) is not int or value['amount'] < 0:
        raise DefinitionError('finalization_wait amount must be nonnegative integer')
    choice(value['unit'], {'calendar_days', 'elapsed_seconds'}, 'finalization_wait.unit')
    return dict(value)


def normalize_policy_body(body):
    if type(body) is not dict:
        raise ContractError('policy body must be an object')
    kind = body.get('kind')
    result = deepcopy(body)
    if kind == 'economic_source':
        fields = {'kind', 'source_view', 'selection', 'instrument_id', 'investment_series_id',
                  'instrument_class', 'input_kind', 'unit', 'value_semantics',
                  'temporal_precision', 'cadence', 'history_policy', 'currency',
                  'base_currency', 'quote_currency', 'quotation_direction',
                  'observation_convention', 'calendar_id', 'calendar_version', 'timezone', 'economic_coverage', 'adjustment_convention',
                  'includes_income', 'includes_corporate_actions', 'period_representation',
                  'availability_basis', 'vintage_capability', 'availability_evidence_complete',
                  'zero_terminal_allowed', 'evidence'}
        object_fields(body, fields, path='economic_source')
        result['source_view'] = normalize_reference(body['source_view'])
        result['selection'] = normalize_selection(body['selection'])
        result['history_policy'] = normalize_reference(body['history_policy'])
        result['cadence'] = normalize_cadence(body['cadence'])
        for field in ('instrument_id', 'investment_series_id', 'unit', 'currency',
                      'observation_convention', 'calendar_id', 'economic_coverage'):
            token(body[field], field)
        if not isinstance(body['calendar_version'], str) or not VERSION.fullmatch(body['calendar_version']):
            raise ContractError('calendar_version must be a semantic version')
        text(body['timezone'], 'timezone')
        # Ineligible classes can be represented as rejected source certifications;
        # publication of a Target rejects them before any arithmetic.
        choice(body['instrument_class'], {'spot_fx', 'equity', 'fund', 'index',
               'certified_investment_series', 'macro', 'yield', 'spread', 'rate', 'futures'}, 'instrument_class')
        choice(body['input_kind'], {'price', 'wealth_index', 'period_returns'}, 'input_kind')
        choice(body['value_semantics'], VALUE_SEMANTICS, 'value_semantics')
        choice(body['temporal_precision'], {'date', 'utc_timestamp'}, 'temporal_precision')
        for field in ('base_currency', 'quote_currency'):
            _nullable_token(body[field], field)
        choice(body['quotation_direction'], {'quote_per_base', 'base_per_quote', 'not_applicable'}, 'quotation_direction')
        choice(body['adjustment_convention'], {'unadjusted_price', 'certified_price_adjustments',
               'certified_total_return', 'certified_period_returns', 'ambiguous'}, 'adjustment_convention')
        for field in ('includes_income', 'includes_corporate_actions',
                      'availability_evidence_complete', 'zero_terminal_allowed'):
            _boolean(body[field], field)
        if body['period_representation'] is not None:
            choice(body['period_representation'], {'simple', 'log'}, 'period_representation')
        choice(body['availability_basis'], AVAILABILITY_BASES, 'availability_basis')
        choice(body['vintage_capability'], {'complete_history', 'pinned_state'}, 'vintage_capability')
        result['evidence'] = normalize_references(body['evidence'])
        if not result['evidence']:
            raise ContractError('economic_source requires documentary evidence references')
    elif kind == 'outcome_selection':
        object_fields(body, {'kind', 'selection', 'availability_basis', 'finalization_wait',
                            'label_precision_policy', 'unknown_availability'}, path=kind)
        choice(body['selection'], {'first_defensible', 'pinned_later'}, 'outcome_selection.selection')
        choice(body['availability_basis'], AVAILABILITY_BASES, 'availability_basis')
        result['finalization_wait'] = _wait(body['finalization_wait'])
        choice(body['label_precision_policy'], {'conservative_date_boundary', 'exact_timestamp'}, 'label_precision_policy')
        choice(body['unknown_availability'], {'allow_uncertified', 'reject'}, 'unknown_availability')
    elif kind == 'mathematical_validity':
        required = {'kind':kind, 'missing':'retain_null', 'stale':'reject',
                    'nonpositive_start':'retain_null', 'nonfinite':'reject_source',
                    'negative_end':'retain_null', 'zero_terminal':'source_contract',
                    'period_coverage':'exact_complete'}
        object_fields(body, set(required), path=kind)
        if body != required:
            raise DefinitionError('Unsupported mathematical or missing observation policy')
    elif kind == 'return_calculation':
        object_fields(body, {'kind', 'calculation_version', 'arithmetic'}, path=kind)
        if body['calculation_version'] != CALCULATION_VERSION or body['arithmetic'] != 'decimal_50_then_binary64_guard':
            raise DefinitionError('Unsupported return calculation version')
    elif kind == 'target_schedule':
        object_fields(body, {'kind', 'calendar_id', 'calendar_version', 'timezone',
                            'observation_convention', 'temporal_precision', 'anchor_convention'}, path=kind)
        for field in ('calendar_id', 'observation_convention'):
            token(body[field], field)
        if not isinstance(body['calendar_version'], str) or not VERSION.fullmatch(body['calendar_version']):
            raise ContractError('calendar_version must be a semantic version')
        text(body['timezone'], 'timezone')
        choice(body['temporal_precision'], {'date', 'utc_timestamp'}, 'temporal_precision')
        choice(body['anchor_convention'], {'declared_marks'}, 'anchor_convention')
    else:
        raise DefinitionError(f'Unsupported Target policy kind: {kind!r}')
    return result


def create_policy(body, display_name='Target policy'):
    normalized = normalize_policy_body(body)
    text(display_name, 'display_name')
    return {'schema_version':SCHEMA_VERSION, 'record_type':'policy_definition',
            'id':'POLICY_' + digest({'identity_profile':IDENTITY_PROFILE, 'kind':'policy', 'body':normalized}),
            'version':'1.0.0', 'display_name':display_name, 'body':normalized}


def validate_policy(record, *, kind=None):
    validate_schema(record)
    object_fields(record, {'schema_version', 'record_type', 'id', 'version', 'display_name', 'body'}, path='Target policy')
    expected = create_policy(record['body'], record['display_name'])
    if record != expected:
        raise DefinitionError('Target policy identity/version differs from canonical content')
    if kind is not None and record['body']['kind'] != kind:
        raise DefinitionError(f'Expected {kind} policy')
    return expected


def normalize_definition_body(body):
    from .scheduling import normalize_entry, normalize_horizon, normalize_endpoint
    fields = {'sources', 'construction', 'unit', 'currency', 'economic_coverage',
              'schedule_policy', 'anchor_policy', 'entry', 'horizon', 'endpoint',
              'outcome_policy', 'validity_policy', 'calculation', 'dependencies'}
    object_fields(body, fields, path='Target definition body')
    result = deepcopy(body)
    if type(body['sources']) is not list or not body['sources']:
        raise DefinitionError('Target requires canonical source bindings')
    sources = []
    for source in body['sources']:
        object_fields(source, {'role', 'source_view', 'selection', 'economic_policy'}, path='Target source')
        sources.append({'role':choice(source['role'], {'instrument', 'benchmark'}, 'source.role'),
                        'source_view':normalize_reference(source['source_view']),
                        'selection':normalize_selection(source['selection']),
                        'economic_policy':normalize_reference(source['economic_policy'])})
    roles = [s['role'] for s in sources]
    if len(set(roles)) != len(roles) or 'instrument' not in roles:
        raise DefinitionError('Target requires exactly one instrument and at most one benchmark')
    result['sources'] = sorted(sources, key=lambda s:s['role'])
    construction = body['construction']
    object_fields(construction, {'basis', 'representation', 'comparison', 'instrument_basis', 'benchmark_basis'}, path='construction')
    basis = choice(construction['basis'], {'price', 'total_return', 'benchmark_excess'}, 'basis')
    representation = choice(construction['representation'], {'simple', 'log'}, 'representation')
    choice(construction['instrument_basis'], {'price', 'total_return'}, 'instrument_basis')
    if basis == 'benchmark_excess':
        choice(construction['benchmark_basis'], {'price', 'total_return'}, 'benchmark_basis')
        expected = 'arithmetic_difference' if representation == 'simple' else 'log_difference'
        if roles.count('benchmark') != 1 or construction['comparison'] != expected:
            raise DefinitionError('Excess return requires benchmark and explicit matching comparison convention')
        if construction['instrument_basis'] != construction['benchmark_basis']:
            raise DefinitionError('Initial excess contract requires compatible matching economic return bases')
    elif construction['comparison'] != 'none' or construction['benchmark_basis'] is not None or 'benchmark' in roles or construction['instrument_basis'] != basis:
        raise DefinitionError('Standalone return basis/benchmark/comparison mismatch')
    expected_unit = 'dimensionless_fraction' if representation == 'simple' else 'natural_log_return'
    if body['unit'] != expected_unit:
        raise DefinitionError('Return unit must match mathematical representation')
    token(body['currency'], 'currency'); token(body['economic_coverage'], 'economic_coverage')
    for field in ('schedule_policy', 'outcome_policy', 'validity_policy', 'calculation'):
        result[field] = normalize_reference(body[field])
    result['dependencies'] = normalize_references(body['dependencies'])
    anchor = body['anchor_policy']
    object_fields(anchor, {'mode', 'anchor_set_id'}, path='anchor_policy')
    choice(anchor['mode'], {'market_schedule', 'explicit'}, 'anchor_policy.mode')
    if anchor['mode'] == 'explicit':
        token(anchor['anchor_set_id'], 'anchor_set_id')
    elif anchor['anchor_set_id'] is not None:
        raise DefinitionError('Market schedule anchors do not use an explicit anchor-set identity')
    result['entry'] = normalize_entry(body['entry'])
    result['horizon'] = normalize_horizon(body['horizon'])
    result['endpoint'] = normalize_endpoint(body['endpoint'])
    return result


def create_definition(body, display_name='Investment return Target'):
    normalized = normalize_definition_body(body)
    text(display_name, 'display_name')
    return {'schema_version':SCHEMA_VERSION, 'record_type':'target_definition',
            'id':'TARGET_' + digest({'identity_profile':IDENTITY_PROFILE, 'kind':'target_definition', 'body':normalized}),
            'version':'1.0.0', 'display_name':display_name, 'body':normalized}


def validate_definition(record):
    validate_schema(record)
    object_fields(record, {'schema_version', 'record_type', 'id', 'version', 'display_name', 'body'}, path='Target definition')
    expected = create_definition(record['body'], record['display_name'])
    if record != expected:
        raise DefinitionError('Target definition identity/version differs from canonical semantic body')
    return expected


def validate_observation(row):
    validate_schema(row)
    fields = {'schema_version', 'record_type', 'id', 'target', 'instrument_id',
              'investment_series_id', 'prediction_anchor', 'anchor_id', 'temporal_precision',
              'entry_time', 'intended_end', 'exit_time', 'horizon', 'value', 'unit', 'currency',
              'status', 'reason_code', 'selected_sources', 'source_availability',
              'outcome_selection_cutoff', 'label_available_at', 'historical_eligibility_certified',
              'availability_basis', 'label_precision_policy', 'economic_coverage'}
    object_fields(row, fields, path='Target observation')
    if row['schema_version'] != SCHEMA_VERSION or row['record_type'] != 'target_observation':
        raise ContractError('Wrong Target observation profile')
    normalize_reference(row['target'])
    precision = choice(row['temporal_precision'], {'date', 'utc_timestamp'}, 'temporal_precision')
    for field in ('prediction_anchor', 'entry_time', 'intended_end', 'exit_time', 'outcome_selection_cutoff'):
        normalize_time(row[field], precision, field)
    for field in ('source_availability', 'label_available_at'):
        if row[field] is not None:
            normalize_time(row[field], precision, field)
    for field in ('instrument_id', 'investment_series_id', 'unit', 'currency', 'economic_coverage', 'anchor_id'):
        token(row[field], field)
    if not row['prediction_anchor'] <= row['entry_time'] < row['exit_time']:
        raise ContractError('Target observation has invalid temporal ordering')
    from .scheduling import normalize_horizon
    normalize_horizon(row['horizon'])
    status = choice(row['status'], {'valid', 'invalid', 'missing', 'pending'}, 'status')
    if status == 'valid':
        canonical_decimal(row['value'])
        if not math.isfinite(float(row['value'])) or row['reason_code'] is not None:
            raise ContractError('Target valid value must be finite and have no reason')
    elif row['value'] is not None or row['reason_code'] not in REASONS:
        raise ContractError('Target unsuccessful observation requires null and controlled reason')
    _boolean(row['historical_eligibility_certified'], 'historical_eligibility_certified')
    choice(row['availability_basis'], AVAILABILITY_BASES, 'availability_basis')
    choice(row['label_precision_policy'], {'conservative_date_boundary', 'exact_timestamp'}, 'label_precision_policy')
    if row['historical_eligibility_certified'] and (status != 'valid' or row['label_available_at'] is None or row['availability_basis'] == 'unknown'):
        raise ContractError('Invalid historical eligibility certification')
    if row['label_available_at'] is not None:
        if row['label_available_at'] < row['exit_time'] or (row['source_availability'] is not None and row['label_available_at'] < row['source_availability']):
            raise ContractError('Target label availability precedes required outcome/evidence')
    if type(row['selected_sources']) is not list:
        raise ContractError('Target selected_sources must be a list')
    for source in row['selected_sources']:
        object_fields(source, {'role', 'source_view', 'source_snapshots', 'economic_policy', 'provenance', 'operands'}, path='selected source')
        choice(source['role'], {'instrument', 'benchmark'}, 'selected source role')
        normalize_reference(source['source_view']); normalize_reference(source['economic_policy'])
        normalize_references(source['source_snapshots'])
        if type(source['provenance']) is not dict or type(source['operands']) is not list:
            raise ContractError('Invalid selected source provenance/operands')
        for operand in source['operands']:
            object_fields(operand, {'role', 'reference_time', 'available_at', 'vintage_id', 'lineage', 'interval_start', 'interval_end'}, path='operand')
            token(operand['role']); token(operand['vintage_id']); normalize_reference(operand['lineage'])
            normalize_time(operand['reference_time'], precision); normalize_time(operand['available_at'], precision)
            for field in ('interval_start', 'interval_end'):
                if operand[field] is not None: normalize_time(operand[field], precision)
    expected = 'TARGETOBS_' + digest({k:v for k,v in row.items() if k != 'id'})
    if row['id'] != expected:
        raise ContractError('Target observation identity differs from contents')
    return deepcopy(row)


def validate_record(record):
    kind = record.get('record_type') if type(record) is dict else None
    if kind == 'target_definition': return validate_definition(record)
    if kind == 'policy_definition': return validate_policy(record)
    if kind == 'target_observation': return validate_observation(record)
    raise ContractError('Unsupported Target record')
