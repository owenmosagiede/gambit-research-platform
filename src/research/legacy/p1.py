"""Frozen legacy numerical helpers. See provenance.json; do not edit scientific formulas."""
from __future__ import annotations
import math
from typing import Any, Mapping, Sequence

def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _sign(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _constant(values: Sequence[float]) -> bool:
    return bool(values) and all(value == values[0] for value in values[1:])


def _average_ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_rank = ((start + 1) + end) / 2.0
        for position in range(start, end):
            ranks[ordered[position][0]] = average_rank
        start = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_centered)
        * sum(value * value for value in right_centered)
    )
    if denominator == 0:
        return None
    return sum(a * b for a, b in zip(left_centered, right_centered)) / denominator


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if _constant(left) or _constant(right):
        return None
    return _pearson(_average_ranks(left), _average_ranks(right))


def _ols_with_hac(
    feature: Sequence[float], target: Sequence[float], maxlags: int
) -> tuple[float, float, float | None, float | None]:
    """OLS with intercept and uncorrected Newey-West/Bartlett covariance."""
    count = len(feature)
    feature_mean = sum(feature) / count
    target_mean = sum(target) / count
    denominator = sum((value - feature_mean) ** 2 for value in feature)
    if denominator == 0:
        raise ValueError("constant feature")
    beta = sum(
        (x_value - feature_mean) * (y_value - target_mean)
        for x_value, y_value in zip(feature, target)
    ) / denominator
    alpha = target_mean - beta * feature_mean
    residuals = [
        y_value - alpha - beta * x_value
        for x_value, y_value in zip(feature, target)
    ]

    sum_x = sum(feature)
    sum_x2 = sum(value * value for value in feature)
    determinant = count * sum_x2 - sum_x * sum_x
    inverse = (
        (sum_x2 / determinant, -sum_x / determinant),
        (-sum_x / determinant, count / determinant),
    )
    scores = [(residual, residual * x_value) for residual, x_value in zip(residuals, feature)]
    meat = [[0.0, 0.0], [0.0, 0.0]]
    for score in scores:
        for row in range(2):
            for column in range(2):
                meat[row][column] += score[row] * score[column]
    for lag in range(1, maxlags + 1):
        weight = 1.0 - lag / (maxlags + 1.0)
        for index in range(lag, count):
            current = scores[index]
            prior = scores[index - lag]
            for row in range(2):
                for column in range(2):
                    meat[row][column] += weight * (
                        current[row] * prior[column] + prior[row] * current[column]
                    )
    intermediate = [
        [sum(inverse[row][inner] * meat[inner][column] for inner in range(2)) for column in range(2)]
        for row in range(2)
    ]
    covariance = [
        [sum(intermediate[row][inner] * inverse[inner][column] for inner in range(2)) for column in range(2)]
        for row in range(2)
    ]
    variance = covariance[1][1]
    if variance < 0 and abs(variance) < 1e-15:
        variance = 0.0
    standard_error = math.sqrt(variance) if variance > 0 else None
    t_statistic = beta / standard_error if standard_error is not None else None
    return alpha, beta, standard_error, t_statistic


def _mean_hac(values: Sequence[float], maxlags: int) -> tuple[float, float | None, float | None]:
    """Mean with uncorrected Newey-West/Bartlett variance of the sample mean."""
    count = len(values)
    average = sum(values) / count
    centered = [value - average for value in values]
    long_run_sum = sum(value * value for value in centered)
    for lag in range(1, maxlags + 1):
        weight = 1.0 - lag / (maxlags + 1.0)
        long_run_sum += 2.0 * weight * sum(
            centered[index] * centered[index - lag]
            for index in range(lag, count)
        )
    variance = long_run_sum / (count * count)
    if variance < 0 and abs(variance) < 1e-15:
        variance = 0.0
    standard_error = math.sqrt(variance) if variance > 0 else None
    t_statistic = average / standard_error if standard_error is not None else None
    return average, standard_error, t_statistic


def _three_blocks(items: Sequence[Any]) -> tuple[Sequence[Any], Sequence[Any], Sequence[Any]]:
    quotient, remainder = divmod(len(items), 3)
    sizes = [quotient + (1 if index < remainder else 0) for index in range(3)]
    blocks = []
    offset = 0
    for size in sizes:
        blocks.append(items[offset:offset + size])
        offset += size
    return tuple(blocks)  # type: ignore[return-value]


def _time_series_stability(
    sample: Sequence[Mapping[str, Any]], full_sign: str | None
) -> dict[str, Any]:
    subperiods = []
    for index, block in enumerate(_three_blocks(sample), start=1):
        values_x = [float(record["feature_value"]) for record in block]
        values_y = [float(record["target_value"]) for record in block]
        statistic = None
        if len(block) < 2:
            status = "insufficient_data"
        elif _constant(values_x):
            status = "constant_feature"
        elif _constant(values_y):
            status = "constant_target"
        else:
            _alpha, statistic, _se, _t = _ols_with_hac(values_x, values_y, 0)
            status = "valid"
        subperiods.append({
            "subperiod_index": index,
            "start": block[0]["anchor_date"] if block else None,
            "end": block[-1]["anchor_date"] if block else None,
            "observation_count": len(block),
            "primary_statistic": statistic,
            "statistic_sign": _sign(statistic),
            "calculation_status": status,
        })
    valid = [record for record in subperiods if record["calculation_status"] == "valid"]
    same_sign = sum(
        1 for record in valid
        if full_sign is not None and record["statistic_sign"] == full_sign
    )
    return {
        "subperiods": subperiods,
        "full_sample_sign": full_sign,
        "same_sign_subperiod_count": same_sign,
        "valid_subperiod_count": len(valid),
    }


def _cross_sectional_stability(
    history: Sequence[Mapping[str, Any]], full_sign: str | None
) -> dict[str, Any]:
    subperiods = []
    for index, block in enumerate(_three_blocks(history), start=1):
        statistic = (
            sum(float(record["rank_ic"]) for record in block) / len(block)
            if block else None
        )
        subperiods.append({
            "subperiod_index": index,
            "start": block[0]["anchor_date"] if block else None,
            "end": block[-1]["anchor_date"] if block else None,
            "observation_count": len(block),
            "primary_statistic": statistic,
            "statistic_sign": _sign(statistic),
            "calculation_status": "valid" if block else "insufficient_data",
        })
    valid = [record for record in subperiods if record["calculation_status"] == "valid"]
    same_sign = sum(
        1 for record in valid
        if full_sign is not None and record["statistic_sign"] == full_sign
    )
    return {
        "subperiods": subperiods,
        "full_sample_sign": full_sign,
        "same_sign_subperiod_count": same_sign,
        "valid_subperiod_count": len(valid),
    }

