"""Pure, provider-independent numeric-series contracts for fixture execution.

Structural checks do not establish source eligibility or resolve PIT history.
Calendar gaps and operand availability are checked by the engine at each cutoff.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from contracts.experiment import ContractError, load_json_strict

CONTRACT_VERSION = "1.0.0"
EXECUTION_IDENTITY_PROFILE = "transformation_execution.1.0.0"
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}\Z", re.ASCII)
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z", re.ASCII)
HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
DECIMAL = re.compile(r"(?:0|-?(?:[1-9][0-9]*(?:\.[0-9]*[1-9])?|0\.[0-9]*[1-9]))\Z", re.ASCII)
INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z", re.ASCII)
VALUE_SEMANTICS = frozenset({"numeric_level", "price", "difference", "fractional_change", "log_change", "log_level", "score", "volatility", "indicator", "count", "statistic"})
FREQUENCIES = frozenset({"daily", "weekly", "monthly", "quarterly", "annual", "semiannual", "tick", "intraday", "irregular", "event"})
CAPABILITIES = frozenset({"revision_history", "resolved_state", "release_events"})
HISTORY_MODES = frozenset({"resolved_state", "emitted_history"})
REASON_CODES = frozenset({
    "SOURCE_MISSING", "SOURCE_INVALID", "NON_NUMERIC_INPUT", "INSUFFICIENT_HISTORY",
    "MISSING_REQUIRED_OBSERVATION", "NONPOSITIVE_LOG_INPUT", "NONPOSITIVE_INPUT",
    "ZERO_DENOMINATOR", "ZERO_VARIANCE", "ZERO_MAD", "ZERO_RANGE", "ZERO_PATH_LENGTH",
    "UNDEFINED_SEASONAL_BUCKET", "INSUFFICIENT_SEASONAL_HISTORY", "NUMERICAL_FAILURE",
    "NONFINITE_OUTPUT", "MISSING_PERIOD", "UNSUPPORTED_DOMAIN", "UNSUPPORTED_CADENCE",
    "INAPPLICABLE", "UNDECLARED_HISTORY_MODE",
})


def object_fields(value, required, optional=(), path="object"):
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise ContractError(f"{path}: expected an object with string keys")
    missing, extra = set(required)-set(value), set(value)-set(required)-set(optional)
    if missing or extra:
        raise ContractError(f"{path}: missing={sorted(missing)}, unexpected={sorted(extra)}")


def token(value, path="token"):
    if type(value) is not str or not TOKEN.fullmatch(value):
        raise ContractError(f"{path}: invalid identifier token")
    return value


def choice(value, choices, path):
    if type(value) is not str or value not in choices:
        raise ContractError(f"{path}: expected one of {sorted(choices)}")
    return value


def text(value, path="text"):
    if type(value) is not str or not value or any(ord(c)<32 or ord(c)>126 for c in value):
        raise ContractError(f"{path}: expected nonempty printable ASCII text")
    return value


def normalize_reference(value, path="reference"):
    object_fields(value, {"id", "version", "content_sha256"}, path=path)
    token(value["id"], path+".id")
    if type(value["version"]) is not str or not VERSION.fullmatch(value["version"]):
        raise ContractError(f"{path}: invalid semantic version")
    if type(value["content_sha256"]) is not str or not HASH.fullmatch(value["content_sha256"]):
        raise ContractError(f"{path}: invalid content digest")
    return dict(value)


def normalize_references(values, path="references"):
    if type(values) is not list:
        raise ContractError(f"{path}: expected list")
    result = [normalize_reference(v, f"{path}[{i}]") for i,v in enumerate(values)]
    seen = {}
    for item in result:
        key = (item["id"], item["version"])
        if key in seen:
            raise ContractError(f"{path}: duplicate or conflicting reference identity")
        seen[key] = item["content_sha256"]
    return sorted(result, key=lambda x:(x["id"], x["version"]))


def canonical_decimal(value):
    """Require already-canonical decimal text; never coerce JSON numbers."""
    if type(value) is not str or not DECIMAL.fullmatch(value):
        raise ContractError("value: expected canonical finite decimal text")
    return value


def decimal_text(value):
    """Explicit numeric-boundary formatter; strict contracts do not call this."""
    if isinstance(value, bool):
        raise ContractError("Cannot format a boolean as a scientific decimal")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ContractError("Cannot format a scientific decimal") from error
    if not number.is_finite():
        raise ContractError("Cannot format a nonfinite scientific decimal")
    result = format(number, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    if number == 0:
        result = "0"
    return canonical_decimal(result)


def normalize_time(value, precision, path="time"):
    choice(precision, {"date", "utc_timestamp"}, "temporal_precision")
    pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2}" if precision == "date" else r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        raise ContractError(f"{path}: time must preserve {precision} precision")
    try:
        date.fromisoformat(value) if precision == "date" else datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ContractError(f"{path}: invalid calendar time") from error
    return value


def normalize_cutoffs(values, precision):
    if type(values) is not list or not values:
        raise ContractError("cutoffs: expected a nonempty list")
    result = [normalize_time(v, precision, "cutoff") for v in values]
    if len(result) != len(set(result)):
        raise ContractError("cutoffs: duplicate evaluation cutoff")
    return sorted(result)


validate_cutoffs = normalize_cutoffs


def normalize_dimensions(values):
    if type(values) is not list:
        raise ContractError("dimensions: expected list")
    result = []
    for item in values:
        object_fields(item, {"name", "value"}, path="dimension")
        result.append({"name":token(item["name"], "dimension.name"), "value":text(item["value"], "dimension.value")})
    if len({v["name"] for v in result}) != len(result):
        raise ContractError("dimensions: duplicate dimension name")
    return sorted(result, key=lambda x:x["name"])


def normalize_selection(value):
    object_fields(value, {"measure", "entity_id", "dimensions"}, path="selection")
    return {"measure":token(value["measure"], "selection.measure"), "entity_id":token(value["entity_id"], "selection.entity_id"), "dimensions":normalize_dimensions(value["dimensions"])}


def normalize_cadence(value):
    object_fields(value, {"frequency", "ordering", "gap_policy", "calendar"}, {"interval_seconds"}, path="cadence")
    result = {"frequency":choice(value["frequency"], FREQUENCIES, "cadence.frequency"),
              "ordering":choice(value["ordering"], {"reference_time", "evaluation_cutoff"}, "cadence.ordering"),
              "gap_policy":choice(value["gap_policy"], {"reject", "explicit_missing"}, "cadence.gap_policy"),
              "calendar":choice(value["calendar"], {"gregorian"}, "cadence.calendar")}
    if result["frequency"] == "intraday":
        interval = value.get("interval_seconds")
        if type(interval) is not str or re.fullmatch(r"[1-9][0-9]*", interval) is None:
            raise ContractError("intraday cadence requires a positive integer string interval_seconds")
        result["interval_seconds"] = interval
    elif "interval_seconds" in value:
        raise ContractError("interval_seconds is only supported for intraday cadence")
    return result


def normalize_execution(value, precision):
    fields = {"recipe", "materialization_id", "identity_profile", "implementation", "executed_at", "cutoffs", "status", "availability_semantics", "history_mode", "lineage"}
    object_fields(value, fields, {"lineage_records"}, path="execution")
    if type(value["materialization_id"]) is not str or not re.fullmatch(r"MATERIALIZATION_[0-9a-f]{64}", value["materialization_id"]):
        raise ContractError("execution: invalid materialization identity")
    result = {"recipe":normalize_reference(value["recipe"]), "materialization_id":value["materialization_id"],
            "identity_profile":choice(value["identity_profile"], {EXECUTION_IDENTITY_PROFILE}, "execution.identity_profile"),
            "implementation":normalize_reference(value["implementation"]),
            "executed_at":normalize_time(value["executed_at"], "utc_timestamp", "execution.executed_at"),
            "cutoffs":normalize_cutoffs(value["cutoffs"], precision),
            "status":choice(value["status"], {"complete", "partial", "no_valid_output"}, "execution.status"),
            "availability_semantics":choice(value["availability_semantics"], {"derived_at_cutoff"}, "execution.availability_semantics"),
            "history_mode":choice(value["history_mode"], HISTORY_MODES, "execution.history_mode"),
            "lineage":normalize_references(value["lineage"], "execution.lineage")}
    if "lineage_records" in value:
        if type(value["lineage_records"]) is not list:
            raise ContractError("lineage_records: expected list")
        records = [normalize_lineage_record(record) for record in value["lineage_records"]]
        if len({record["id"] for record in records}) != len(records):
            raise ContractError("lineage_records: duplicate identity")
        for record in records:
            binding = {"id":record["id"], "version":record["version"], "content_sha256":hashlib.sha256(_canonical(record)).hexdigest()}
            if binding not in result["lineage"]:
                raise ContractError("lineage record does not match an execution lineage reference")
        result["lineage_records"] = sorted(records, key=lambda r:r["id"])
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def normalize_lineage_record(value):
    fields = {"schema_version", "record_type", "id", "version", "inputs", "operation", "implementation", "policy_bindings"}
    object_fields(value, fields, path="lineage_manifest")
    choice(value["schema_version"], {"0.2.0"}, "lineage schema")
    choice(value["record_type"], {"lineage_manifest"}, "lineage record type")
    choice(value["version"], {"1.0.0"}, "lineage version")
    result = deepcopy(value)
    for field in ("inputs", "policy_bindings"):
        if type(value[field]) is not list: raise ContractError("lineage bindings must be lists")
        roles = set()
        for binding in result[field]:
            object_fields(binding, {"role", "artifact"}, path="lineage binding")
            role = token(binding["role"])
            if role in roles: raise ContractError("duplicate lineage role")
            roles.add(role)
            binding["artifact"] = normalize_reference(binding["artifact"])
    result["operation"] = normalize_reference(result["operation"])
    if result["implementation"] is not None:
        result["implementation"] = normalize_reference(result["implementation"])
    identity = "LINEAGE_" + hashlib.sha256(_canonical({k:v for k,v in result.items() if k != "id"})).hexdigest()
    if result["id"] != identity: raise ContractError("lineage manifest ID differs from canonical contents")
    return result


def normalize_series(value, *, require_execution=False):
    required = {"contract_version", "source_view", "source_snapshots", "selection", "unit", "value_semantics", "cadence", "history_policy", "capabilities", "temporal_precision", "provenance", "observations"}
    object_fields(value, required, {"release_events", "execution"}, "series")
    choice(value["contract_version"], {CONTRACT_VERSION}, "contract_version")
    precision = choice(value["temporal_precision"], {"date", "utc_timestamp"}, "temporal_precision")
    selection = normalize_selection(value["selection"])
    snapshots = normalize_references(value["source_snapshots"], "source_snapshots")
    if not snapshots:
        raise ContractError("source_snapshots: pinned input evidence is required")
    if type(value["capabilities"]) is not list or not value["capabilities"]:
        raise ContractError("capabilities: expected nonempty list")
    capabilities = [choice(v, CAPABILITIES, "capability") for v in value["capabilities"]]
    if len(set(capabilities)) != len(capabilities) or not ({"revision_history", "resolved_state"} & set(capabilities)):
        raise ContractError("capabilities: duplicate or missing history capability")
    provenance = value["provenance"]
    if type(provenance) is not dict:
        raise ContractError("provenance: expected label mapping")
    for key,label in provenance.items():
        token(key, "provenance label"); text(label, "provenance value")
    execution = value.get("execution")
    if require_execution and execution is None:
        raise ContractError("result: execution metadata is required")
    if execution is not None:
        execution = normalize_execution(execution, precision)
    if type(value["observations"]) is not list:
        raise ContractError("observations: expected list")
    rows = []
    seen = set()
    fields = {"reference_time", "available_at", "vintage_id", "value", "status", "reason_code", "lineage", "entity_id", "measure", "dimensions"}
    for original in value["observations"]:
        object_fields(original, fields, {"evaluation_cutoff"}, "observation")
        row = deepcopy(original)
        row_selection = normalize_selection({key:row[key] for key in ("measure", "entity_id", "dimensions")})
        if row_selection != selection:
            raise ContractError("observation: mixed entity/measure/dimension partition")
        row.update(row_selection)
        if row["reference_time"] is None:
            if execution is None or row["status"] != "invalid":
                raise ContractError("null reference time is allowed only for invalid derived rows")
        else:
            normalize_time(row["reference_time"], precision, "observation.reference_time")
        normalize_time(row["available_at"], precision, "observation.available_at")
        token(row["vintage_id"], "observation.vintage_id")
        row["lineage"] = normalize_reference(row["lineage"], "observation.lineage")
        choice(row["status"], {"valid", "missing", "invalid"}, "observation.status")
        if row["status"] == "valid":
            canonical_decimal(row["value"])
            if row["reason_code"] is not None:
                raise ContractError("valid observation cannot carry a failure reason")
        else:
            if row["value"] is not None:
                raise ContractError("failed observation must have a null value")
            choice(row["reason_code"], REASON_CODES, "observation.reason_code")
        cutoff = row.get("evaluation_cutoff")
        if execution is not None:
            if cutoff is None:
                raise ContractError("result observation requires its evaluation cutoff")
            normalize_time(cutoff, precision, "observation.evaluation_cutoff")
            if cutoff not in execution["cutoffs"] or row["available_at"] != cutoff or (row["reference_time"] is not None and row["reference_time"] > cutoff):
                raise ContractError("result observation exceeds its declared evaluation cutoff")
            if row["lineage"] not in execution["lineage"]:
                raise ContractError("result observation lineage is absent from execution provenance")
        elif cutoff is not None:
            normalize_time(cutoff, precision, "observation.evaluation_cutoff")
            if row["available_at"] > cutoff:
                raise ContractError("input observation exceeds its declared evaluation cutoff")
        key = (row["reference_time"], row["available_at"], cutoff)
        if key in seen:
            raise ContractError("observations: duplicate temporal key")
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda r: ((r.get("evaluation_cutoff") or ""), r["reference_time"] or "", r["available_at"]))
    if execution is not None:
        valid = sum(row["status"] == "valid" for row in rows)
        status = "no_valid_output" if not valid else "complete" if valid == len(rows) else "partial"
        if execution["status"] != status:
            raise ContractError("execution status differs from observed validity")
    cadence = normalize_cadence(value["cadence"])
    emitted = execution is not None and execution["history_mode"] == "emitted_history"
    expected_order = "evaluation_cutoff" if emitted else "reference_time"
    if cadence["ordering"] != expected_order or (emitted and cadence["frequency"] != "event"):
        raise ContractError("cadence ordering must represent reference history or emitted event history explicitly")
    result = {"contract_version":CONTRACT_VERSION, "source_view":normalize_reference(value["source_view"]),
              "source_snapshots":snapshots, "selection":selection, "unit":token(value["unit"], "unit"),
              "value_semantics":choice(value["value_semantics"], VALUE_SEMANTICS, "value_semantics"),
              "cadence":cadence, "history_policy":normalize_reference(value["history_policy"]),
              "capabilities":sorted(capabilities), "temporal_precision":precision,
              "provenance":dict(sorted(provenance.items())), "observations":rows}
    if "execution" in value or require_execution:
        result["execution"] = execution
    if "release_events" in value:
        if type(value["release_events"]) is not list:
            raise ContractError("release_events: expected list")
        events, keys = [], set()
        for event in value["release_events"]:
            object_fields(event, {"reference_time", "available_at", "lineage"}, path="release_event")
            item = {"reference_time":normalize_time(event["reference_time"], precision), "available_at":normalize_time(event["available_at"], precision), "lineage":normalize_reference(event["lineage"])}
            key = (item["reference_time"], item["available_at"])
            if key in keys:
                raise ContractError("release_events: duplicate event")
            keys.add(key); events.append(item)
        if events and "release_events" not in capabilities:
            raise ContractError("release_events require the declared capability")
        result["release_events"] = sorted(events, key=lambda r:(r["available_at"], r["reference_time"]))
    return result


def normalize_input(value):
    return normalize_series(value)


def normalize_result(value):
    return normalize_series(value, require_execution=True)


validate_input = normalize_input
validate_result = normalize_result
