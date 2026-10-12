"""Frozen legacy admission evidence helpers. See provenance.json."""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping

def _path(document: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = document
    for component in dotted_path.split("."):
        if not isinstance(value, Mapping) or component not in value:
            return None
        value = value[component]
    return value


def _result(
    criterion_id: str,
    *,
    criterion_type: str = "structural",
    required: bool = True,
    status: str,
    observed_value: Any,
    operator: str | None,
    required_value: Any,
    source_trial_field: str | None,
    reason_code: str | None,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "criterion_type": criterion_type,
        "required": required,
        "status": status,
        "observed_value": deepcopy(observed_value),
        "operator": operator,
        "required_value": deepcopy(required_value),
        "source_trial_field": source_trial_field,
        "reason_code": reason_code,
        "evidence": deepcopy(dict(evidence or {})),
    }


def _sign(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _numeric_threshold(
    trial_result: Mapping[str, Any], criterion: Mapping[str, Any]
) -> dict[str, Any]:
    value = _path(trial_result, criterion["source_trial_field"])
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _result(
            criterion["criterion_id"],
            criterion_type="numeric_threshold",
            status="unresolved",
            observed_value=value,
            operator=criterion["operator"],
            required_value=criterion["required_value"],
            source_trial_field=criterion["source_trial_field"],
            reason_code="REQUIRED_METRIC_MISSING",
        )
    passed = abs(float(value)) >= float(criterion["required_value"])
    return _result(
        criterion["criterion_id"],
        criterion_type="numeric_threshold",
        status="pass" if passed else "fail",
        observed_value=value,
        operator=criterion["operator"],
        required_value=criterion["required_value"],
        source_trial_field=criterion["source_trial_field"],
        reason_code=None if passed else "STATISTICAL_CRITERION_FAILED",
        evidence={"absolute_observed_value": abs(float(value))},
    )


def _sign_stability(
    trial_result: Mapping[str, Any], criterion: Mapping[str, Any]
) -> dict[str, Any]:
    reference_value = _path(trial_result, criterion["reference_sign_field"])
    subperiods = _path(trial_result, criterion["subperiods_field"])
    required_matches = int(criterion["required_value"])
    total = int(criterion["total_subperiod_count"])
    if (
        isinstance(reference_value, bool)
        or not isinstance(reference_value, (int, float))
        or not isinstance(subperiods, list)
        or len(subperiods) != total
        or any(
            row.get("calculation_status") != "valid"
            or row.get("statistic_sign") is None
            or isinstance(row.get("primary_statistic"), bool)
            or not isinstance(row.get("primary_statistic"), (int, float))
            for row in (subperiods or [])
        )
    ):
        return _result(
            criterion["criterion_id"],
            criterion_type="sign_stability",
            status="unresolved",
            observed_value=None,
            operator=criterion["operator"],
            required_value=required_matches,
            source_trial_field=criterion["source_trial_field"],
            reason_code="STABILITY_EVIDENCE_MISSING",
            evidence={"required_matching_count": required_matches, "total_subperiod_count": total},
        )
    reference_sign = _sign(float(reference_value))
    subperiod_signs = [row["statistic_sign"] for row in subperiods]
    calculated_signs = [_sign(float(row["primary_statistic"])) for row in subperiods]
    reported_reference = trial_result["stability"]["full_sample_sign"]
    reported_matches = trial_result["stability"]["same_sign_subperiod_count"]
    matching = sum(sign == reference_sign and sign != "zero" for sign in subperiod_signs)
    evidence = {
        "reference_sign": reference_sign,
        "reported_reference_sign": reported_reference,
        "subperiod_signs": subperiod_signs,
        "matching_subperiod_count": matching,
        "reported_matching_subperiod_count": reported_matches,
        "required_matching_count": required_matches,
        "total_subperiod_count": total,
    }
    if calculated_signs != subperiod_signs or reported_reference != reference_sign or reported_matches != matching:
        return _result(
            criterion["criterion_id"],
            criterion_type="sign_stability",
            status="unresolved",
            observed_value=matching,
            operator=criterion["operator"],
            required_value=required_matches,
            source_trial_field=criterion["source_trial_field"],
            reason_code="STABILITY_EVIDENCE_INCONSISTENT",
            evidence=evidence,
        )
    passed = reference_sign != "zero" and matching >= required_matches
    return _result(
        criterion["criterion_id"],
        criterion_type="sign_stability",
        status="pass" if passed else "fail",
        observed_value=matching,
        operator=criterion["operator"],
        required_value=required_matches,
        source_trial_field=criterion["source_trial_field"],
        reason_code=None if passed else "SIGN_STABILITY_CRITERION_FAILED",
        evidence=evidence,
    )


def _decision_from_results(results: list[Mapping[str, Any]]) -> str:
    structural = [row for row in results if row["criterion_type"] == "structural" and row["required"]]
    statistical = [row for row in results if row["criterion_type"] != "structural" and row["required"]]
    if any(row["status"] == "fail" for row in structural):
        return "rejected"
    if any(row["status"] == "unresolved" for row in structural):
        return "unresolved"
    if any(row["status"] == "unresolved" for row in statistical):
        return "unresolved"
    if any(row["status"] == "fail" for row in statistical):
        return "rejected"
    return "admitted"

