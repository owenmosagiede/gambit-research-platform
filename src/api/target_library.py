"""Read-only Target catalog and explicitly pinned observation retrieval.

Selection of a stored materialization is mandatory for observation reads. A list
response is discovery evidence, never permission to use a label before maturity.
"""
import re

from data.transformations.contracts import normalize_time, ContractError, token
from data.targets.service import (TargetNotFound, list_targets,
                                  retrieve_target)

TARGET_ID = re.compile(r'TARGET_[0-9a-f]{64}\Z', re.ASCII)
MATERIALIZATION_ID = re.compile(r'MATERIALIZATION_[0-9a-f]{64}\Z', re.ASCII)


class InvalidTargetQuery(ValueError):
    pass


def list_target_library(root, instrument_id=None, horizon_amount=None, horizon_unit=None, *, metadata_only=False):
    """Filter the same verified registry; registered instruments are not Target labels."""
    if instrument_id is not None:
        try: token(instrument_id, 'instrument_id')
        except ContractError as error: raise InvalidTargetQuery('Invalid instrument identity') from error
    if (horizon_amount is None) != (horizon_unit is None):
        raise InvalidTargetQuery('Horizon amount and unit are required together')
    if horizon_amount is not None:
        if not isinstance(horizon_amount, str) or not re.fullmatch(r'[1-9][0-9]{0,8}', horizon_amount):
            raise InvalidTargetQuery('Horizon amount must be a positive integer')
        if horizon_unit not in {'trading_sessions', 'scheduled_bars', 'calendar_days', 'elapsed_seconds'}:
            raise InvalidTargetQuery('Unsupported horizon unit')
    if metadata_only:
        from api.target_catalog import list_target_catalog
        result = list_target_catalog(root)
    else:
        result = list_targets(root)
    if instrument_id is None and horizon_amount is None:
        return result
    selected = []
    for item in result['targets']:
        if instrument_id is not None and item.get('instrument_id', item['investment_series']) != instrument_id:
            continue
        if horizon_amount is not None and (item['horizon']['amount'] != int(horizon_amount) or item['horizon']['unit'] != horizon_unit):
            continue
        selected.append(item)
    result = dict(result, targets=selected, target_count=len(selected))
    if 'instruments' in result:
        instruments = [item for item in result['instruments'] if instrument_id is None or item['instrument_id'] == instrument_id]
        result.update(instruments=instruments, instrument_count=len(instruments))
    result['selection'] = {'instrument_id':instrument_id, 'horizon_amount':int(horizon_amount) if horizon_amount else None,
                           'horizon_unit':horizon_unit}
    return result


def get_target_detail(root, identifier, materialization_id, training_cutoff=None,
                      cutoff_precision=None, start_inclusive=None, end_exclusive=None,
                      range_precision=None):
    if not TARGET_ID.fullmatch(identifier):
        raise TargetNotFound('Unknown Target')
    if not isinstance(materialization_id, str) or not MATERIALIZATION_ID.fullmatch(materialization_id):
        raise InvalidTargetQuery('An exact materialization_id is required')
    if (training_cutoff is None) != (cutoff_precision is None):
        raise InvalidTargetQuery('training_cutoff and cutoff_precision are required together')
    if cutoff_precision is not None and cutoff_precision not in {'date', 'utc_timestamp'}:
        raise InvalidTargetQuery('Unsupported cutoff precision')
    if training_cutoff is not None:
        try:
            normalize_time(training_cutoff, cutoff_precision, 'training_cutoff')
        except ContractError as error:
            raise InvalidTargetQuery('Invalid training cutoff') from error
    bounds = (start_inclusive, end_exclusive, range_precision)
    if any(value is not None for value in bounds):
        if range_precision not in {'date', 'utc_timestamp'} or (start_inclusive is None and end_exclusive is None):
            raise InvalidTargetQuery('Date-range bounds require their exact temporal precision')
        for value in (start_inclusive, end_exclusive):
            if value is not None:
                try: normalize_time(value, range_precision, 'date range')
                except ContractError as error: raise InvalidTargetQuery('Invalid date range') from error
        if start_inclusive is not None and end_exclusive is not None and start_inclusive >= end_exclusive:
            raise InvalidTargetQuery('Date-range bounds must increase')
    # The shared temporal contract validates the exact cutoff representation;
    # never truncate a timestamp, add midnight, or silently infer its precision.
    result = retrieve_target(root, identifier, materialization_id,
                             training_cutoff=training_cutoff,
                             cutoff_precision=cutoff_precision)
    if range_precision is not None:
        precision = result['manifest']['input_key']['temporal_precision']
        if precision != range_precision:
            raise InvalidTargetQuery('Date range precision must match the stored observations')
        rows = result['observations']
        selected = [row for row in rows if
            (start_inclusive is None or row['prediction_anchor'] >= start_inclusive) and
            (end_exclusive is None or row['prediction_anchor'] < end_exclusive)]
        result = dict(result, observations=selected, range_selection={
            'start_inclusive':start_inclusive, 'end_exclusive':end_exclusive,
            'temporal_precision':range_precision, 'field':'prediction_anchor',
            'selected_count':len(selected), 'excluded_count':len(rows)-len(selected)})
    return result
