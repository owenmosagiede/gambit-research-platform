"""Pure P1 adapter for the frozen legacy TS and fixed-universe CS methods.

No acquisition, preparation, persistence, or research launch occurs on import.
The legacy policy uses verbatim helpers under research.legacy. The separately
versioned scheduled_weekday_hac_v2 policy preserves real weekday lag distances;
both retain their explicitly approved execution contract and admission rules.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from research.legacy import admission as frozen_gate, p1
from research import scheduled_statistics
from .contract import legacy_rows, prepare_rows, validate_profile


def _coverage_after_exclusions(sample: dict, rows: Sequence[Mapping[str, Any]]) -> None:
    counts = Counter(row["instrument"] for row in rows)
    sample["usable_pair_count"] = len(rows)
    sample["usable_date_count"] = len({row["date"] for row in rows})
    for member in sample["members"]:
        member["usable_rows"] = counts[member["instrument"]]


def _scheduled_stability(rows: Sequence[Mapping[str, Any]], mode: str,
                         full_sign: str | None) -> dict[str, Any]:
    """Retained equal-count block policy, carrying real dates into every estimate."""
    periods = []
    for index, block in enumerate(p1._three_blocks(rows), 1):
        effect = None
        if mode == "TS":
            x, y = [row["feature"] for row in block], [row["target"] for row in block]
            if len(block) < 2:
                status = "insufficient_data"
            elif p1._constant(x):
                status = "constant_feature"
            elif p1._constant(y):
                status = "constant_target"
            else:
                effect = scheduled_statistics.ols_hac([row["date"] for row in block], x, y, 0)["effect"]
                status = "valid"
            dates = [row["date"] for row in block]
        else:
            dates = [row["anchor_date"] for row in block]
            if block:
                effect = scheduled_statistics.mean_hac(dates, [row["rank_ic"] for row in block], 0)["effect"]
            status = "valid" if block else "insufficient_data"
        periods.append({"subperiod_index": index, "start": dates[0] if dates else None,
                        "end": dates[-1] if dates else None, "observation_count": len(block),
                        "primary_statistic": effect, "statistic_sign": p1._sign(effect),
                        "calculation_status": status})
    valid = [row for row in periods if row["calculation_status"] == "valid"]
    return {"subperiods": periods, "full_sample_sign": full_sign,
            "same_sign_subperiod_count": sum(full_sign is not None and row["statistic_sign"] == full_sign for row in valid),
            "valid_subperiod_count": len(valid)}


def run_p1(rows: Iterable[Mapping[str, Any]], *, mode: str, horizon: int,
           members: Sequence[str], expected_direction: str,
           profile: Mapping[str, Any]) -> dict[str, Any]:
    """Compute one horizon, never one TS trial per member of a CS universe."""
    policy = validate_profile(mode=mode, horizon=horizon, members=members,
                              expected_direction=expected_direction, profile=profile)
    aligned, excluded, sample = prepare_rows(rows, mode=mode, members=members, profile=policy)
    scheduled = policy["kernel_policy"] == scheduled_statistics.POLICY
    if scheduled:
        for row in aligned:
            scheduled_statistics.weekday_position(row["date"])
    maxlags = horizon - 1  # Retained policy permits spacing=1 only.
    minimum = max(3, maxlags + (3 if mode == "TS" else 2))
    metrics = {"primary_effect": None, "hac_standard_error": None,
               "hac_t_statistic": None, "hac_maxlags": maxlags,
               "primary_statistic": "predictive_coefficient_beta" if mode == "TS" else "mean_rank_ic"}
    history, failure, schedule_diagnostics = [], None, None
    if mode == "TS":
        x, y = [row["feature"] for row in aligned], [row["target"] for row in aligned]
        if len(aligned) < minimum:
            failure = "INSUFFICIENT_SAMPLE"
        elif p1._constant(x):
            failure = "CONSTANT_FEATURE"
        elif p1._constant(y):
            failure = "CONSTANT_TARGET"
        else:
            if scheduled:
                estimate = scheduled_statistics.ols_hac([row["date"] for row in aligned], x, y, maxlags)
                alpha, beta, se, t = (estimate[key] for key in ("alpha", "effect", "standard_error", "t_statistic"))
                schedule_diagnostics = estimate["scheduled_hac"]
            else:
                alpha, beta, se, t = p1._ols_with_hac(x, y, maxlags)
            if se is None:
                failure = "ZERO_HAC_VARIANCE"
            else:
                metrics.update(primary_effect=beta, alpha=alpha, predictive_coefficient=beta,
                               hac_standard_error=se, hac_t_statistic=t,
                               time_series_spearman_ic=p1._spearman(x, y))
        stability = (_scheduled_stability(aligned, mode, p1._sign(metrics["primary_effect"])) if scheduled
                     else p1._time_series_stability(legacy_rows(aligned), p1._sign(metrics["primary_effect"])))
    else:
        grouped = defaultdict(list)
        for row in aligned:
            grouped[row["date"]].append(row)
        retained = []
        for current in sorted(grouped):
            group = grouped[current]
            x, y = [row["feature"] for row in group], [row["target"] for row in group]
            reason = "CONSTANT_FEATURE" if p1._constant(x) else "CONSTANT_TARGET" if p1._constant(y) else None
            rank_ic = p1._spearman(x, y) if reason is None else None
            if rank_ic is None:
                excluded.extend({**row, "exclusion_reason": reason or "INVALID_VALUE"} for row in group)
                continue
            retained.extend(group)
            history.append({"anchor_date": current, "decision_time": current,
                            "instrument_count": len(group), "rank_ic": rank_ic})
        aligned = retained
        if len(history) < minimum:
            failure = "INSUFFICIENT_SAMPLE"
        else:
            values = [row["rank_ic"] for row in history]
            if scheduled:
                estimate = scheduled_statistics.mean_hac([row["anchor_date"] for row in history], values, maxlags)
                effect, se, t = (estimate[key] for key in ("effect", "standard_error", "t_statistic"))
                schedule_diagnostics = estimate["scheduled_hac"]
            else:
                effect, se, t = p1._mean_hac(values, maxlags)
            if se is None:
                failure = "ZERO_HAC_VARIANCE"
            else:
                metrics.update(primary_effect=effect, mean_rank_ic=effect,
                               median_rank_ic=median(values), hac_standard_error=se, hac_t_statistic=t,
                               positive_ic_frequency=sum(v > 0 for v in values) / len(values),
                               negative_ic_frequency=sum(v < 0 for v in values) / len(values))
        stability = (_scheduled_stability(history, mode, p1._sign(metrics["primary_effect"])) if scheduled
                     else p1._cross_sectional_stability(history, p1._sign(metrics["primary_effect"])))
    if scheduled:
        metrics["hac_clock"] = scheduled_statistics.POLICY
    _coverage_after_exclusions(sample, aligned)
    sample.update(minimum_observations=minimum,
                  inference_observation_count=len(aligned) if mode == "TS" else len(history),
                  inference_observation_unit="dates" if mode == "CS" else "instrument_dates",
                  excluded_pair_count=len(excluded),
                  exclusion_counts=dict(sorted(Counter(row["exclusion_reason"] for row in excluded).items())),
                  sample_start=min((row["date"] for row in aligned), default=None),
                  sample_end=max((row["date"] for row in aligned), default=None))
    # Preserve the actual legacy gate's evidence precedence, including missing
    # block evidence and zero-sign consistency checks; no rewritten approximation.
    trial = {"metrics": metrics, "stability": stability}
    criteria = [{"criterion_id": "execution_completed", "criterion_type": "structural", "required": True,
                 "status": "unresolved" if failure else "pass", "observed_value": failure or "completed"}]
    criteria.append(frozen_gate._numeric_threshold(trial, {
        "criterion_id": "absolute_hac_t", "source_trial_field": "metrics.hac_t_statistic",
        "operator": "absolute_greater_than_or_equal", "required_value": 2.0}))
    criteria.append(frozen_gate._sign_stability(trial, {
        "criterion_id": "sign_stability", "reference_sign_field": "metrics.primary_effect",
        "subperiods_field": "stability.subperiods", "source_trial_field": "stability.same_sign_subperiod_count",
        "operator": "greater_than_or_equal", "required_value": 2, "total_subperiod_count": 3}))
    if mode == "CS":
        criteria.append(frozen_gate._numeric_threshold(trial, {
            "criterion_id": "absolute_mean_ic", "source_trial_field": "metrics.primary_effect",
            "operator": "absolute_greater_than_or_equal", "required_value": 0.03}))
    evidence = {row["criterion_id"]: {"status": row["status"], "observed": row.get("observed_value"),
                                       "minimum": row.get("required_value")} for row in criteria}
    admission = frozen_gate._decision_from_results(criteria)
    if failure:
        reasons = [failure]
    else:
        unavailable = [key for key, row in evidence.items() if row["status"] == "unresolved"]
        failed = [key for key, row in evidence.items() if row["status"] == "fail"]
        reasons = [key.upper() + "_EVIDENCE_UNAVAILABLE" for key in unavailable] or [key.upper() + "_GATE_FAILED" for key in failed]
    return {
        "stage": "P1", "mode": mode, "horizon": horizon,
        "expected_direction": expected_direction, "profile": policy,
        "execution_status": "not_computable" if failure else "completed",
        "admission": admission, "reason_codes": reasons,
        "metrics": metrics, "sample": sample, "evidence": evidence,
        "multiple_testing": {"method": "none", "applied": False},
        "artifacts": {"aligned_sample": aligned, "observation_exclusions": excluded,
                      "cross_sectional_ic_history": history, "stability": stability,
                      "admission_criteria": criteria,
                      **({"scheduled_hac": schedule_diagnostics} if scheduled else {})},
    }
