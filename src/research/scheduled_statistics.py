"""Version 2 HAC on actual scheduled weekdays, without compressing missing dates.

The fitted OLS coefficient or mean uses actual usable observations only. Bartlett
score cross-products use Monday–Friday schedule distance, with no holiday removal.
An absent observation contributes no score product and is never a zero-valued
observation. The covariance denominator remains the actual usable sample size.
These helpers do not replace the immutable retained-legacy implementation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
from typing import Any, Mapping, Sequence

from research.legacy import p2 as ranks
from research.p1_discovery.contract import ResearchContractError, iso_date, numeric


POLICY = "scheduled_weekday_hac_v2"


def weekday_position(value: str) -> int:
    """Monotonically index scheduled weekdays; Friday to Monday is one step."""
    parsed = date.fromisoformat(iso_date(value, "HAC observation date"))
    if parsed.weekday() >= 5:
        raise ResearchContractError("HAC observation date must be a scheduled Monday–Friday date")
    weeks, day = divmod(parsed.toordinal() - 1, 7)  # 0001-01-01 was Monday.
    return weeks * 5 + day


def _calendar(dates: Sequence[str], maxlags: int) -> list[int]:
    if type(maxlags) is not int or maxlags < 0:
        raise ResearchContractError("HAC maxlags must be a nonnegative integer")
    positions = [weekday_position(value) for value in dates]
    if any(right <= left for left, right in zip(positions, positions[1:])):
        raise ResearchContractError("HAC dates must be unique and chronologically ordered")
    return positions


def _number(value: Any) -> float | None:
    if value is None:
        return None
    result = numeric(value)
    if result is None:
        raise ResearchContractError("HAC values must be finite numeric values or explicit nulls")
    return result


def _diagnostics(dates: Sequence[str], positions: Sequence[int], maxlags: int) -> dict[str, Any]:
    observed = set(positions)
    return {
        "policy": POLICY,
        "clock": "Monday-Friday; no holiday exclusions",
        "maxlags": maxlags,
        "usable_observation_count": len(positions),
        "usable_dates": list(dates),
        "scheduled_span": positions[-1] - positions[0] + 1 if positions else 0,
        "missing_scheduled_period_count": positions[-1] - positions[0] + 1 - len(positions) if positions else 0,
        "lag_pair_counts": [{"lag": lag, "pair_count": sum(position - lag in observed for position in positions)}
                            for lag in range(1, maxlags + 1)],
        "missing_rule": "absent score cross-products; no observation-value imputation",
    }


def _empty(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {"alpha": None, "effect": None, "standard_error": None, "t_statistic": None,
            "scheduled_hac": dict(diagnostics)}


def ols_hac(dates: Sequence[str], feature: Sequence[Any], target: Sequence[Any],
            maxlags: int) -> dict[str, Any]:
    """Intercept OLS, uncorrected Bartlett HAC by actual weekday separation."""
    if len(dates) != len(feature) or len(feature) != len(target):
        raise ResearchContractError("HAC date, feature and target lengths differ")
    positions = _calendar(dates, maxlags)
    usable = []
    for when, position, raw_x, raw_y in zip(dates, positions, feature, target):
        x, y = _number(raw_x), _number(raw_y)
        if x is not None and y is not None:
            usable.append((when, position, x, y))
    selected_dates = [row[0] for row in usable]
    selected_positions = [row[1] for row in usable]
    diagnostic = _diagnostics(selected_dates, selected_positions, maxlags)
    count = len(usable)
    if count < 2:
        return _empty(diagnostic)
    x_values, y_values = [row[2] for row in usable], [row[3] for row in usable]
    x_mean, y_mean = sum(x_values) / count, sum(y_values) / count
    denominator = sum((value - x_mean) ** 2 for value in x_values)
    if denominator == 0:
        return _empty(diagnostic)
    beta = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denominator
    alpha = y_mean - beta * x_mean
    residuals = [y - alpha - beta * x for x, y in zip(x_values, y_values)]
    sum_x, sum_x2 = sum(x_values), sum(x * x for x in x_values)
    determinant = count * sum_x2 - sum_x * sum_x
    if determinant == 0:
        raise ResearchContractError("OLS normal matrix is numerically singular")
    inverse = ((sum_x2 / determinant, -sum_x / determinant),
               (-sum_x / determinant, count / determinant))
    scores = [(residual, residual * x) for residual, x in zip(residuals, x_values)]
    by_position = dict(zip(selected_positions, scores))
    meat = [[0.0, 0.0], [0.0, 0.0]]
    for score in scores:
        for row in range(2):
            for column in range(2):
                meat[row][column] += score[row] * score[column]
    for lag in range(1, maxlags + 1):
        weight = 1.0 - lag / (maxlags + 1.0)
        for position, current in zip(selected_positions, scores):
            prior = by_position.get(position - lag)
            if prior is None:
                continue
            for row in range(2):
                for column in range(2):
                    meat[row][column] += weight * (current[row] * prior[column] + prior[row] * current[column])
    intermediate = [[sum(inverse[row][inner] * meat[inner][column] for inner in range(2))
                     for column in range(2)] for row in range(2)]
    covariance = [[sum(intermediate[row][inner] * inverse[inner][column] for inner in range(2))
                   for column in range(2)] for row in range(2)]
    variance = covariance[1][1]
    standard_error = math.sqrt(variance) if variance > 0 else None
    return {"alpha": alpha, "effect": beta, "standard_error": standard_error,
            "t_statistic": beta / standard_error if standard_error else None,
            "scheduled_hac": diagnostic}


def mean_hac(dates: Sequence[str], values: Sequence[Any], maxlags: int) -> dict[str, Any]:
    """Mean and Bartlett HAC over usable date-level values, preserving date gaps."""
    if len(dates) != len(values):
        raise ResearchContractError("HAC date and value lengths differ")
    positions = _calendar(dates, maxlags)
    usable = []
    for when, position, raw in zip(dates, positions, values):
        number = _number(raw)
        if number is not None:
            usable.append((when, position, number))
    selected_dates, selected_positions = [row[0] for row in usable], [row[1] for row in usable]
    diagnostic = _diagnostics(selected_dates, selected_positions, maxlags)
    if not usable:
        return _empty(diagnostic)
    average = sum(row[2] for row in usable) / len(usable)
    centered = [row[2] - average for row in usable]
    by_position = dict(zip(selected_positions, centered))
    long_run_sum = sum(value * value for value in centered)
    for lag in range(1, maxlags + 1):
        weight = 1.0 - lag / (maxlags + 1.0)
        product_sum = sum(value * by_position[position - lag]
                          for position, value in zip(selected_positions, centered)
                          if position - lag in by_position)
        long_run_sum += 2.0 * weight * product_sum
    variance = long_run_sum / (len(usable) * len(usable))
    standard_error = math.sqrt(variance) if variance > 0 else None
    return {"alpha": None, "effect": average, "standard_error": standard_error,
            "t_statistic": average / standard_error if standard_error else None,
            "scheduled_hac": diagnostic}


def raw_estimate(rows: Sequence[Mapping[str, Any]], research_type: str,
                 maxlags: int) -> dict[str, Any]:
    """P2-shaped statistics on legacy field names, with calendar positions retained.

    The input adapter owns frozen fixed-universe breadth. If supplied CS operands
    contain a null, this helper excludes that entire date rather than silently
    shrinking its cross section. Constant date-level ranks have a null IC; the
    following usable date retains its actual weekday position.
    """
    if research_type == "time_series":
        return ols_hac([row["observation_time"] for row in rows],
                       [row["feature_value"] for row in rows],
                       [row["target_value"] for row in rows], maxlags)
    if research_type != "cross_sectional":
        raise ResearchContractError("Scheduled HAC research_type must be time_series or cross_sectional")
    groups = defaultdict(list)
    for row in rows:
        when = row["observation_time"]
        weekday_position(when)
        groups[when].append(row)
    dates, effects, history = [], [], []
    for when in sorted(groups):
        group = groups[when]
        x = [_number(row["feature_value"]) for row in group]
        y = [_number(row["target_value"]) for row in group]
        if any(value is None for value in (*x, *y)):
            effect, reason = None, "MISSING_OPERAND"
        else:
            effect = ranks._pearson(ranks._average_ranks(x), ranks._average_ranks(y))
            reason = "UNAVAILABLE_RANK_IC" if effect is None else None
        history.append({"date": when, "rank_ic": effect, "instrument_count": len(group), "reason": reason})
        if effect is not None:
            dates.append(when)
            effects.append(effect)
    result = mean_hac(dates, effects, maxlags)
    result.update(period_effects=effects, period_dates=dates, period_history=history)
    return result
