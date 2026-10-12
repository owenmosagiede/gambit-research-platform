"""Versioned P2 evidence and gate adapter for one admitted relationship/horizon.

Historical profiles retain their exact numerical and missing-evidence behavior.
The scheduled-weekday policy uses dated HAC pairs and records unavailable required
statistics as unresolved, while keeping the long-horizon t/p evidence diagnostic.
"""
from __future__ import annotations

from collections import defaultdict
import math
from typing import Any, Iterable, Mapping, Sequence

from research.legacy import p2
from research.p1_discovery.contract import ResearchContractError, legacy_rows, normalize_direction, numeric, prepare_rows, validate_profile


def select_non_overlapping_intervals(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Legacy 1.1 interval algorithm on already validated ISO dates.

    Adjacent intervals sharing a boundary price do not share a return increment.
    Date comparison preserves that rule without asserting intraday availability.
    """
    selected, prior_end = [], None
    for row in sorted(rows, key=lambda value: (value["target_end"], value["date"], value["instrument"])):
        if prior_end is None or row["date"] >= prior_end:
            selected.append(row)
            prior_end = row["target_end"]
    return selected


def _gate(evidence: Mapping[str, Any], horizon: int, *,
          missing_evidence: str = "legacy_failed_v1") -> tuple[str, list[str]]:
    if evidence["discovery_direction"]["status"] == "fail":
        return "FAILED", ["DISCOVERY_EFFECT_CONTRADICTS_EXPECTED_DIRECTION"]
    if missing_evidence == "legacy_failed_v1" and evidence["sample_sufficiency"]["status"] != "pass":
        return "UNRESOLVED", ["INSUFFICIENT_EFFECTIVE_SAMPLE"]
    required = ("direction", "magnitude", "stability") + (() if horizon == 252 else ("inference",))
    if missing_evidence == "unresolved_required_v1":
        # A measured N below the fixed minimum is a failed criterion, whereas
        # an unavailable required statistic remains unresolved. Evaluate missing
        # evidence first so a failed criterion cannot disguise an unknown one.
        required = ("sample_sufficiency",) + required
    missing = [key for key in required if evidence[key]["status"] not in {"pass", "fail"}]
    if missing:
        return "UNRESOLVED", [key.upper() + "_EVIDENCE_UNAVAILABLE" for key in missing]
    failed = [key for key in required if evidence[key]["status"] == "fail"]
    return ("FAILED", [key.upper() + "_GATE_FAILED" for key in failed]) if failed else ("VALIDATED", [])


def _required_stability(blocks, leaveouts, slices, horizon):
    """Require evidence before deciding the compound stability criterion.

    Missing-evidence precedence is the same as the top-level gate: an unavailable
    required statistic is unresolved even if another observed statistic fails.
    The 252 policy needs signs only; neither block nor full-sample t is its gate.
    """
    missing = []
    for block in blocks:
        if block["oriented_effect"] is None:
            missing.append(f"block_{block['block_index']}_effect")
        if horizon != 252 and block["directional_t_statistic"] is None:
            missing.append(f"block_{block['block_index']}_directional_t")
    for row in leaveouts:
        if row["oriented_effect"] is None:
            missing.append(f"leave_out_{row['omitted_block']}_effect")
    if horizon == 252:
        for row in slices:
            if row["oriented_effect"] is None:
                missing.append(row["slice_id"] + "_effect")
    known_blocks = [block for block in blocks if block["oriented_effect"] is not None]
    expected = sum(block["oriented_effect"] > 0 for block in known_blocks)
    all_leave = (None if any(row["oriented_effect"] is None for row in leaveouts)
                 else all(row["oriented_effect"] > 0 for row in leaveouts))
    all_slices = (None if any(row["oriented_effect"] is None for row in slices)
                  else all(row["oriented_effect"] > 0 for row in slices))
    no_opposite = (None if any(block["directional_t_statistic"] is None for block in blocks)
                   else all(block["directional_t_statistic"] > -1.645 for block in blocks))
    observed = {"expected_sign_blocks": expected, "available_sign_blocks": len(known_blocks),
                "all_leave_out_expected_sign": all_leave,
                "no_significant_opposite_block": no_opposite,
                "all_robustness_slices_expected_sign": all_slices}
    if missing:
        status = "unresolved"
    else:
        passed = (expected == 3 and all_leave and all_slices if horizon == 252
                  else expected >= 2 and all_leave and no_opposite)
        status = "pass" if passed else "fail"
    return {"status": status, "observed": observed, "missing_required_evidence": missing}


def run_p2(rows: Iterable[Mapping[str, Any]], *, mode: str, horizon: int,
           members: Sequence[str], expected_direction: str, discovery_effect: float,
           profile: Mapping[str, Any]) -> dict[str, Any]:
    policy = validate_profile(mode=mode, horizon=horizon, members=members,
                              expected_direction=expected_direction, profile=profile)
    discovery = numeric(discovery_effect)
    if discovery is None:
        raise ResearchContractError("finite discovery_effect is required")
    orientation = 1.0 if normalize_direction(expected_direction) == "positive" else -1.0
    oriented_discovery = orientation * discovery
    flags = ["LONG_HORIZON_LOW_SAMPLE_CONFIDENCE"] if horizon == 252 else []
    minimum = 4 if horizon == 252 else 15
    unresolved_missing = policy["missing_evidence"] == "unresolved_required_v1"
    base = {"stage": "P2", "mode": mode, "horizon": horizon,
            "expected_direction": expected_direction, "profile": policy,
            "confidence_flags": flags,
            "missing_evidence_policy": policy["missing_evidence"]}
    # Deliberately before any iteration/access of the supplied validation sample.
    if oriented_discovery <= 0:
        evidence = {"discovery_direction": {"status": "fail", "observed": p2._sign(discovery)},
                    **{key: {"status": "unresolved", "observed": None}
                       for key in ("sample_sufficiency", "direction", "magnitude", "inference", "stability")}}
        decision, reasons = _gate(evidence, horizon, missing_evidence=policy["missing_evidence"])
        return {**base, "execution_status": "discovery_direction_failed", "decision": decision,
                "reason_codes": reasons, "evidence": evidence,
                "metrics": {"raw_discovery_effect": discovery, "oriented_discovery_effect": oriented_discovery,
                            "primary_effect": None, "effect_retention_ratio": None},
                "sample": {"validation_data_accessed": False, "effective_observation_count": 0,
                           "required_members": list(members), "minimum_effective_observations": minimum},
                "fdr_diagnostics": {"method": "benjamini_hochberg", "diagnostic_only": True,
                                    "family_size": 0, "raw_p_value": None, "adjusted_p_value": None},
                "artifacts": {"aligned_sample": [], "observation_exclusions": [],
                              "cross_sectional_ic_history": [], "blocks": [], "leaveouts": [], "robustness_slices": []}}
    aligned, excluded, sample = prepare_rows(rows, mode=mode, members=members, profile=policy)
    groups = defaultdict(list)
    for row in aligned:
        groups[row["date"]].append(row)
    if mode == "CS" and any(len({row["target_end"] for row in values}) != 1 for values in groups.values()):
        raise ResearchContractError("fixed CS members must share the horizon endpoint at each date")
    legacy = legacy_rows(aligned)
    research_type = "time_series" if mode == "TS" else "cross_sectional"
    maxlags = horizon - 1
    scheduled = policy["kernel_policy"] == "scheduled_weekday_hac_v2"
    if scheduled:
        from research.scheduled_statistics import raw_estimate
    else:
        raw_estimate = p2._raw_estimate
    estimate = raw_estimate(legacy, research_type, maxlags)
    effect, raw_t = estimate.get("effect"), estimate.get("t_statistic")
    if unresolved_missing:
        effect, raw_t = numeric(effect), numeric(raw_t)
    oriented = orientation * effect if effect is not None else None
    directional_t = orientation * raw_t if raw_t is not None else None
    retention = oriented / oriented_discovery if oriented is not None else None
    p_value = 0.5 * math.erfc(directional_t / math.sqrt(2)) if directional_t is not None else None
    blocks, leaveouts, slices = [], [], []
    split = p2._blocks(legacy, 3, research_type=research_type)
    for index, block in enumerate(split, 1):
        result = raw_estimate(block, research_type, 0)
        value, statistic = result.get("effect"), result.get("t_statistic")
        if unresolved_missing:
            value, statistic = numeric(value), numeric(statistic)
        directional = orientation * value if value is not None else None
        blocks.append({"block_index": index, "observation_count": len(block),
                       "date_count": len({row["observation_time"] for row in block}),
                       "start": block[0]["observation_time"] if block else None,
                       "end": block[-1]["observation_time"] if block else None,
                       "raw_effect": value, "oriented_effect": directional,
                       "directional_t_statistic": orientation * statistic if statistic is not None else None,
                       "expected_sign": (None if unresolved_missing and directional is None
                                         else directional is not None and directional > 0),
                       **({"scheduled_hac": result.get("scheduled_hac")} if scheduled else {})})
    for index in range(3):
        subset = tuple(row for block_index, block in enumerate(split) if block_index != index for row in block)
        result = raw_estimate(subset, research_type, 0)
        value = result.get("effect")
        if unresolved_missing:
            value = numeric(value)
        leaveouts.append({"omitted_block": index + 1, "raw_effect": value,
                          "oriented_effect": orientation * value if value is not None else None,
                          **({"scheduled_hac": result.get("scheduled_hac")} if scheduled else {})})
    for index, part in enumerate(p2._blocks(legacy, 2, research_type=research_type), 1):
        result = raw_estimate(part, research_type, 0)
        value = result.get("effect")
        if unresolved_missing:
            value = numeric(value)
        slices.append({"slice_id": f"chronological_half_{index}", "raw_effect": value,
                       "oriented_effect": orientation * value if value is not None else None,
                       **({"scheduled_hac": result.get("scheduled_hac")} if scheduled else {})})
    # A CS date with no computable IC is not an effective statistical observation.
    # Preserve historical counting for v1; v2 uses the same usable dates as HAC.
    effective_rows = aligned
    if scheduled and mode == "CS":
        usable_dates = set(estimate.get("period_dates", []))
        effective_rows = [row for row in aligned if row["date"] in usable_dates]
    selected = select_non_overlapping_intervals(effective_rows)
    effective_n = len(selected)
    state = lambda value: "pass" if value else "fail"
    if unresolved_missing:
        stability = _required_stability(blocks, leaveouts, slices, horizon)
        criterion = lambda value, predicate: "unresolved" if value is None else state(predicate(value))
    else:
        # Exact historical policy: intentionally retain legacy null coercions.
        block_expected = sum(bool(block["expected_sign"]) for block in blocks)
        all_leave = all((row["oriented_effect"] or 0) > 0 for row in leaveouts)
        no_opposite = all(block["directional_t_statistic"] is None or block["directional_t_statistic"] > -1.645 for block in blocks)
        stable = (block_expected == 3 and all_leave and all((row["oriented_effect"] or 0) > 0 for row in slices)
                  if horizon == 252 else block_expected >= 2 and all_leave and no_opposite)
        stability = {"status": state(stable), "observed": {
            "expected_sign_blocks": block_expected, "all_leave_out_expected_sign": all_leave,
            "no_significant_opposite_block": no_opposite}}
        criterion = lambda value, predicate: state(value is not None and predicate(value))
    evidence = {
        "discovery_direction": {"status": "pass", "observed": p2._sign(discovery)},
        "sample_sufficiency": {"status": state(effective_n >= minimum), "observed": effective_n},
        "direction": {"status": criterion(oriented, lambda value: value > 0), "observed": oriented},
        "magnitude": {"status": criterion(retention, lambda value: value >= 0.25), "observed": retention},
        "inference": {"status": "diagnostic" if horizon == 252 else criterion(directional_t, lambda value: value >= 1.645), "observed": directional_t},
        "stability": stability,
    }
    decision, reasons = _gate(evidence, horizon, missing_evidence=policy["missing_evidence"])
    history = []
    if mode == "CS":
        for current in sorted(groups):
            values = groups[current]
            rank_ic = p2._pearson(p2._average_ranks([row["feature"] for row in values]),
                                  p2._average_ranks([row["target"] for row in values]))
            history.append({"date": current, "instrument_count": len(values), "rank_ic": rank_ic,
                            "status": "valid" if rank_ic is not None else "constant_cross_section"})
    sample.update(validation_data_accessed=True, effective_observation_count=effective_n,
                  minimum_effective_observations=minimum,
                  effective_observation_method="maximum_non_overlapping_target_intervals",
                  non_overlap_boundary_rule="next_target_start_gte_previous_target_end",
                  inference_observation_count=len(aligned) if mode == "TS" else len(estimate.get("period_effects", [])),
                  inference_observation_unit="dates" if mode == "CS" else "instrument_dates",
                  sample_start=min((row["date"] for row in aligned), default=None),
                  sample_end=max((row["date"] for row in aligned), default=None))
    return {**base, "execution_status": "completed", "decision": decision, "reason_codes": reasons,
            "metrics": {"raw_discovery_effect": discovery, "oriented_discovery_effect": oriented_discovery,
                        "primary_effect": effect, "raw_validation_effect": effect, "oriented_validation_effect": oriented,
                        "effect_retention_ratio": retention, "alpha": estimate.get("alpha"),
                        "hac_t_statistic": raw_t, "directional_hac_t_statistic": directional_t,
                        "hac_standard_error": estimate.get("standard_error"), "hac_maxlags": maxlags,
                        "directional_p_value": p_value,
                        **({"scheduled_hac": estimate.get("scheduled_hac")} if scheduled else {})},
            "sample": sample, "evidence": evidence,
            "fdr_diagnostics": {"method": "benjamini_hochberg", "diagnostic_only": True,
                                "family_scope": "singleton_relationship_horizon", "family_size": 1 if p_value is not None else 0,
                                "raw_p_value": p_value,
                                "adjusted_p_value": p2.benjamini_hochberg([p_value])[0] if p_value is not None else None},
            "artifacts": {"aligned_sample": aligned, "observation_exclusions": excluded,
                          "cross_sectional_ic_history": history, "blocks": blocks,
                          "leaveouts": leaveouts, "robustness_slices": slices,
                          "selected_non_overlapping_intervals": [{"date": row["date"], "target_end": row["target_end"],
                                                                  "instrument": row["instrument"]} for row in selected]}}
