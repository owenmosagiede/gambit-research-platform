"""Explicit input boundary for pure retained statistical kernels.

This is not research authorization. The execution service must resolve a pinned,
approved Research Spec before calling the kernels. Date values stay dates;
normalization never invents a historical availability timestamp.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any, Iterable, Mapping, Sequence


class ResearchContractError(ValueError):
    """A caller has not supplied a compatible, frozen statistical contract."""


def iso_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ResearchContractError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ResearchContractError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ResearchContractError(f"{field} must preserve date precision")
    return value


def numeric(value: Any) -> float | None:
    # Immutable platform observations encode decimal values as strings. Convert
    # only here, at the retained binary64 calculation boundary; source/operand
    # lineage remains unchanged. This does not parse arbitrary UI text as data.
    if isinstance(value, str):
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value):
            return None
        try:
            decimal = Decimal(value)
            result = float(decimal)
        except (InvalidOperation, OverflowError, ValueError):
            return None
        return result if decimal.is_finite() and math.isfinite(result) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def normalize_direction(value: Any) -> str:
    """Normalize UI/storage capitalization, never infer or reverse direction."""
    if not isinstance(value, str) or value not in {"positive", "negative", "POSITIVE", "NEGATIVE"}:
        raise ResearchContractError("expected_direction must be positive or negative")
    return value.lower()


def validate_profile(*, mode: str, horizon: int, members: Sequence[str],
                     expected_direction: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    if mode not in {"TS", "CS"}:
        raise ResearchContractError("mode must be TS or CS; a universe is CS only")
    if type(horizon) is not int or horizon not in (1, 7, 21, 63, 252):
        raise ResearchContractError("unsupported horizon")
    normalize_direction(expected_direction)
    if isinstance(members, (str, bytes)) or not members or any(not isinstance(member, str) or not member for member in members):
        raise ResearchContractError("exact frozen members are required")
    if len(set(members)) != len(members):
        raise ResearchContractError("duplicate scope members")
    if (mode == "TS" and len(members) != 1) or (mode == "CS" and len(members) < 2):
        raise ResearchContractError("TS requires one member; CS requires at least two")
    if not isinstance(profile, Mapping):
        raise ResearchContractError("explicit statistical compatibility profile is required")
    policies = {"retained_legacy_v1": "legacy_failed_v1",
                "scheduled_weekday_hac_v2": "unresolved_required_v1"}
    kernel_policy = profile.get("kernel_policy")
    if kernel_policy not in policies:
        raise ResearchContractError("unapproved or unsupported kernel_policy")
    required = {
        "spacing": 1,
        "clock_compatibility": "approved",
        "missing_evidence": policies[kernel_policy],
    }
    for key, value in required.items():
        if profile.get(key) != value or (key == "spacing" and isinstance(profile.get(key), bool)):
            raise ResearchContractError(f"unapproved or unsupported {key}")
    if profile.get("horizon_unit") not in {"subsequent_valid_observations", "scheduled_weekdays"}:
        raise ResearchContractError("horizon_unit must be explicit")
    if kernel_policy == "scheduled_weekday_hac_v2" and profile.get("horizon_unit") != "scheduled_weekdays":
        raise ResearchContractError("scheduled weekday HAC requires scheduled-weekday Targets")
    start = iso_date(profile.get("window_start"), "window_start")
    end = iso_date(profile.get("window_end_exclusive"), "window_end_exclusive")
    if end <= start:
        raise ResearchContractError("window_end_exclusive must follow window_start")
    if mode == "CS":
        iso_date(profile.get("structural_common_start"), "structural_common_start")
    return deepcopy(dict(profile))


def prepare_rows(rows: Iterable[Mapping[str, Any]], *, mode: str,
                 members: Sequence[str], profile: Mapping[str, Any]) -> tuple[list[dict], list[dict], dict]:
    """Validate declared pairs and exclude complete dates when fixed CS is incomplete.

    Input rows preserve lineage and nullable observations. The parent adapter must
    include scheduled missing pairs; a wholly absent date cannot be inferred here.
    Structural common start is supplied from raw/source structure, not inferred
    from first non-null transformed values.
    """
    supplied = []
    member_set = set(members)
    for value in rows:
        if not isinstance(value, Mapping):
            raise ResearchContractError("research row must be an object")
        row = deepcopy(dict(value))
        invalid_values = {}
        for field in ("feature", "target"):
            number = row.get(field)
            if isinstance(number, float) and not math.isfinite(number):
                invalid_values[field] = repr(number)
                row[field] = None
        if invalid_values:
            row["invalid_numeric_inputs"] = invalid_values
        iso_date(row.get("date"), "row date")
        if profile.get("kernel_policy") == "scheduled_weekday_hac_v2" and date.fromisoformat(row["date"]).weekday() >= 5:
            raise ResearchContractError("observation date is outside the approved weekday grid")
        if row.get("instrument") not in member_set:
            raise ResearchContractError("row instrument is outside the frozen Scope")
        if row.get("target_end") is not None:
            iso_date(row["target_end"], "target_end")
            if profile.get("kernel_policy") == "scheduled_weekday_hac_v2" and date.fromisoformat(row["target_end"]).weekday() >= 5:
                raise ResearchContractError("Target endpoint is outside the approved weekday grid")
            if row["target_end"] <= row["date"]:
                raise ResearchContractError("target_end must follow the observation date")
        supplied.append(row)
    supplied.sort(key=lambda row: (row["date"], row["instrument"]))
    counts = Counter((row["date"], row["instrument"]) for row in supplied)
    accepted, excluded = [], []
    start, end = profile["window_start"], profile["window_end_exclusive"]
    for row in supplied:
        reason = None
        if counts[(row["date"], row["instrument"])] > 1:
            reason = "DUPLICATE_OBSERVATION"
        elif not start <= row["date"] < end:
            reason = "OUTSIDE_FROZEN_WINDOW"
        elif mode == "CS" and row["date"] < profile["structural_common_start"]:
            reason = "BEFORE_STRUCTURAL_COMMON_START"
        elif row.get("valid") is False or row.get("status", "valid") != "valid":
            reason = row.get("reason") or "INVALID_OR_MISSING_PAIR"
        elif numeric(row.get("feature")) is None:
            reason = "FEATURE_MISSING_OR_INVALID"
        elif numeric(row.get("target")) is None or row.get("target_end") is None:
            reason = "TARGET_MISSING_OR_INVALID"
        elif not start <= row["target_end"] < end:
            reason = "TARGET_ENDPOINT_OUTSIDE_FROZEN_WINDOW"
        if reason:
            excluded.append({**row, "exclusion_reason": reason})
        else:
            row["feature"], row["target"] = numeric(row["feature"]), numeric(row["target"])
            accepted.append(row)
    incomplete_dates = []
    if mode == "CS":
        grouped = defaultdict(list)
        for row in accepted:
            grouped[row["date"]].append(row)
        accepted = []
        declared_dates = {row["date"] for row in supplied if start <= row["date"] < end
                          and row["date"] >= profile["structural_common_start"]}
        for current in sorted(declared_dates):
            values = grouped[current]
            present = {row["instrument"] for row in values}
            if present != member_set:
                incomplete_dates.append({"date": current, "required_members": list(members),
                                         "missing_or_invalid_members": sorted(member_set - present)})
                excluded.extend({**row, "exclusion_reason": "INCOMPLETE_FIXED_UNIVERSE"} for row in values)
            else:
                accepted.extend(values)
    available = Counter(row["instrument"] for row in accepted)
    coverage = {
        "required_members": list(members),
        "members": [{"instrument": member, "supplied_rows": sum(row["instrument"] == member for row in supplied),
                     "usable_rows": available[member]} for member in members],
        "supplied_pair_count": len(supplied), "usable_pair_count": len(accepted),
        "usable_date_count": len({row["date"] for row in accepted}),
        "incomplete_dates": incomplete_dates,
        "structural_common_start": profile.get("structural_common_start") if mode == "CS" else None,
    }
    return accepted, excluded, coverage


def legacy_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Field adapter only: these are date strings, never availability timestamps."""
    return [{**row, "feature_value": row["feature"], "target_value": row["target"],
             "anchor_date": row["date"], "observation_time": row["date"],
             "target_start_time": row["date"], "target_end_time": row["target_end"],
             "observation_id": f'{row["date"]}:{row["instrument"]}'} for row in rows]
