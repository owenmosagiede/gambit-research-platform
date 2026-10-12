"""Approved archive-date scheduling for a bounded monthly change recipe.

This wrapper selects real PIT operands and delegates all arithmetic to the
registered transformation engine. It creates no dates, source rows, vintages,
release events, observations on disk, or provider-specific interpretation.
"""
from copy import deepcopy
from datetime import datetime, timezone

from data.pit_selection import select_asof
from data.transformations.contracts import (
    ContractError, normalize_input, normalize_reference, normalize_result,
)
from data.transformations.identity import (
    digest, make_feature_definition, normalize_parameter, normalize_recipe, reference,
)

EVALUATION_POLICY_ID = 'POL_TRANSFORM_EVALUATION_NATIVE_VINTAGES'
EVALUATION_POLICY_VERSION = '2.0.0'
POLICY_RULES = {
    'cutoff_schedule': 'all_observed_native_vintage_dates',
    'current_reference': 'latest_reference_month_at_cutoff',
    'denominator_reference': 'previous_calendar_month',
    'missing_required': 'retain_null',
    'history_mode': 'resolved_state',
    'temporal_precision': 'date',
    'interpretation': 'archive_date_replay',
}


class EvaluationPolicyError(ContractError):
    """The requested schedule or its source binding is not approved here."""


def _parameters(policy):
    parameters = {}
    for value in policy['body']['parameters']:
        value = normalize_parameter(value)
        name = value['name']
        if name in parameters:
            raise EvaluationPolicyError('Duplicate evaluation-policy parameter')
        unit, kind = ('source_view', 'reference') if name == 'source_view' else ('policy_setting', 'token')
        if value['unit'] != unit or value['value']['kind'] != kind:
            raise EvaluationPolicyError('Evaluation-policy parameter type or unit differs from the approved rule')
        parameters[name] = value['value']['value']
    return parameters


def resolve_native_schedule(series, recipe, registry):
    """Resolve all distinct actual availability dates under one pinned policy.

    No count, provider, dataset identifier, coverage date, daily grid, UTC time,
    or live-availability claim is inferred. The source-specific approval is the
    exact SourceView reference in the policy, not a display label.
    """
    source = normalize_input(series)
    recipe = normalize_recipe(recipe)
    binding = recipe.get('evaluation_policy')
    if binding is None:
        raise EvaluationPolicyError('An approved evaluation policy is required')
    policy = registry.resolve_policy(binding)
    if (policy['id'] != EVALUATION_POLICY_ID or policy['version'] != EVALUATION_POLICY_VERSION
            or policy['body']['kind'] != 'selection'):
        raise EvaluationPolicyError('Unsupported evaluation policy')
    if _parameters(policy) != dict(POLICY_RULES, source_view=source['source_view']):
        raise EvaluationPolicyError('Evaluation-policy rules or exact SourceView binding differ')
    if recipe['sources'][0]['source_view'] != source['source_view'] or recipe['selection'] != source['selection']:
        raise EvaluationPolicyError('Recipe and input resolve different source selections')
    if (recipe['history_mode'] != 'resolved_state' or source['temporal_precision'] != 'date'
            or source['cadence']['frequency'] != 'monthly'
            or source['cadence']['ordering'] != 'reference_time'):
        raise EvaluationPolicyError('Archive-date evaluation requires date precision and resolved monthly history')
    # A month cannot denote two different native reference labels. Revisions of
    # the same reference label remain ordinary PIT rows and are preserved.
    references = {}
    for row in source['observations']:
        month = row['reference_time'][:7]
        previous = references.setdefault(month, row['reference_time'])
        if previous != row['reference_time']:
            raise EvaluationPolicyError('Ambiguous monthly reference labels')
    cutoffs = sorted({row['available_at'] for row in source['observations']})
    if not cutoffs:
        raise EvaluationPolicyError('Native evaluation schedule is empty')
    return cutoffs


def _previous_month(reference_time):
    year, month = (int(value) for value in reference_time[:7].split('-'))
    total = year * 12 + month - 2
    return f'{total // 12:04d}-{total % 12 + 1:02d}'


def _operands(source, cutoff):
    state = select_asof(source['observations'], cutoff, reference_cutoff=cutoff)
    if not state:
        return state, None, None
    numerator = state[-1]
    required = _previous_month(numerator['reference_time'])
    denominator = next((row for row in state if row['reference_time'][:7] == required), None)
    return state, numerator, denominator


def _gap_lineage(source, recipe, implementation, bindings, numerator):
    # The absence of a required role is established against the complete pinned
    # snapshot. There is deliberately no fabricated missing source operand.
    inputs = [{'role': 'source_view', 'artifact': source['source_view']}]
    inputs.extend({'role': 'snapshot_' + str(index), 'artifact': item}
                  for index, item in enumerate(source['source_snapshots']))
    if numerator is not None:
        inputs.append({'role': 'numerator', 'artifact': numerator['lineage']})
    record = {'schema_version': '0.2.0', 'record_type': 'lineage_manifest',
              'version': '1.0.0', 'inputs': inputs,
              'operation': reference(make_feature_definition(recipe)),
              'implementation': implementation, 'policy_bindings': bindings}
    record['id'] = 'LINEAGE_' + digest(record)
    return record


def execute_scheduled_recipe(series, recipe, *, registry, implementation, executed_at=None):
    """Return one result and exact operand roles for every native archive date.

    The bounded operation is the generic registered monthly change.pct(k=1).
    Whole-history execution is used whenever all required periods are present.
    When an older unrelated calendar gap exists, the same engine receives the
    two actual adjacent operands: those are this operator's complete support.
    The outer identity always binds the complete original source and schedule.
    Missing required months are retained as null MISSING_PERIOD output rows.
    """
    # Runtime import permits the generic engine to validate this optional policy
    # in its own preflight without a module-import cycle.
    from data.transformations import engine

    source = normalize_input(series)
    recipe = normalize_recipe(recipe)
    cutoffs = resolve_native_schedule(source, recipe, registry)
    implementation = normalize_reference(implementation)
    executed_at = executed_at or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    compiled = engine._preflight(source, recipe, registry)
    if (len(compiled) != 1 or compiled[0][0]['id'] != 'TR_BASE_change_pct'
            or compiled[0][0]['version'] != '2.0.0'
            or compiled[0][0]['body']['execution_contract']['kernel'] != 'change.pct'
            or compiled[0][0]['body']['execution_contract']['temporal_mode'] != 'reference_state'
            or compiled[0][1] != {'k': 1}
            or source['value_semantics'] != 'numeric_level'):
        raise EvaluationPolicyError('This evaluation wrapper supports only the generic monthly change.pct(k=1) recipe')
    _, _, unit, semantics, _ = compiled[0]
    states = [_operands(source, cutoff) for cutoff in cutoffs]
    operand_links = [dict((role, row['lineage']) for role, row in
                         (('numerator', numerator), ('denominator', denominator)) if row is not None)
                     for _, numerator, denominator in states]
    whole_history = all(numerator is not None and denominator is not None
                        for _, numerator, denominator in states)
    if whole_history:
        for state, _, _ in states:
            try:
                engine._check_gaps(state, source['cadence'])
            except engine.InputError as error:
                if not str(error).startswith('MISSING_PERIOD:'):
                    raise
                whole_history = False
                break
    if whole_history:
        result = engine.execute_recipe(source, recipe, cutoffs, registry=registry,
                                       implementation=implementation, executed_at=executed_at)
        return {'result': result, 'operand_links': operand_links, 'cutoffs': cutoffs}

    final_rows, final_points, records, extra = [], [], {}, []
    bindings = engine._policies(recipe)
    for cutoff, (_, numerator, denominator) in zip(cutoffs, states):
        if numerator is None or denominator is None:
            record = _gap_lineage(source, recipe, implementation, bindings, numerator)
            binding = reference(record)
            records[record['id']] = record
            extra.append(binding)
            final_rows.append({'reference_time': None if numerator is None else numerator['reference_time'],
                               'lineage': binding})
            final_points.append({'value': None, 'reason': 'MISSING_PERIOD'})
            continue
        supported = deepcopy(source)
        supported['observations'] = [denominator, numerator]
        # Release anchors are not used by this resolved-state generic operator;
        # retain only the native PIT evidence needed for its finite support.
        supported.pop('release_events', None)
        partial = engine.execute_recipe(supported, recipe, [cutoff], registry=registry,
                                        implementation=implementation, executed_at=executed_at)
        row = partial['observations'][0]
        final_rows.append(row)
        final_points.append({'value': row['value'], 'reason': row['reason_code']})
        records.update({record['id']: record for record in partial['execution']['lineage_records']})
        extra.extend(partial['execution']['lineage'])
    result = engine._envelope(source, recipe, final_rows, final_points, cutoffs, unit, semantics,
                              implementation, executed_at, extra=extra)
    records.update({record['id']: record for record in result['execution']['lineage_records']})
    result['execution']['lineage_records'] = list(records.values())
    result['execution']['lineage'] = [reference(record) for record in records.values()]
    return {'result': normalize_result(result), 'operand_links': operand_links, 'cutoffs': cutoffs}
