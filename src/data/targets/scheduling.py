"""Executable finite canonical market schedules and leakage-safe alignment.

The schedule is independently certified expected calendar evidence, never a list
inferred from observed prices. The definition binds its semantic policy, while
the materialization binds these exact marks, requested anchors and coverage.
Canonical temporal values reuse transformations.contracts.normalize_time.
"""
from bisect import bisect_left, bisect_right
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from data.transformations.contracts import (
    ContractError, VERSION, choice, normalize_reference, normalize_time,
    object_fields, text, token,
)
from data.transformations.identity import digest

SCHEDULE_VERSION = "1.0.0"
PRECISIONS = {"date", "utc_timestamp"}
TIME_UNITS = {"calendar_days", "elapsed_seconds"}
HORIZON_UNITS = TIME_UNITS | {"trading_sessions", "scheduled_bars"}


def _integer(value, *, positive=False, path="amount"):
    if type(value) is not int or value < (1 if positive else 0):
        raise ContractError(f"{path}: expected {'positive' if positive else 'nonnegative'} integer")
    return value


def _duration(value, *, positive=False, path="duration"):
    object_fields(value, {"amount", "unit"}, path=path)
    return {"amount": _integer(value["amount"], positive=positive, path=path + ".amount"),
            "unit": choice(value["unit"], TIME_UNITS, path + ".unit")}


def normalize_entry(value):
    object_fields(value, {"rule", "delay"}, path="entry")
    return {"rule": choice(value["rule"], {"anchor_mark", "next_scheduled"}, "entry.rule"),
            "delay": _duration(value["delay"], path="entry.delay")}


def normalize_horizon(value):
    object_fields(value, {"amount", "unit", "counting"}, path="horizon")
    return {"amount": _integer(value["amount"], positive=True, path="horizon.amount"),
            "unit": choice(value["unit"], HORIZON_UNITS, "horizon.unit"),
            "counting": choice(value["counting"], {"exclusive_entry"}, "horizon.counting")}


def normalize_endpoint(value):
    object_fields(value, {"rule", "tolerance"}, path="endpoint")
    rule = choice(value["rule"], {"exact", "next_scheduled"}, "endpoint.rule")
    tolerance = _duration(value["tolerance"], positive=rule == "next_scheduled", path="endpoint.tolerance")
    if rule == "exact" and tolerance["amount"] != 0:
        raise ContractError("exact endpoint requires zero tolerance")
    return {"rule": rule, "tolerance": tolerance}


def _zone(name):
    text(name, "timezone")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ContractError("timezone: require an installed IANA timezone") from error


def _instant(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt_timezone.utc)


def _utc(value):
    return value.astimezone(dt_timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def validate_schedule(config):
    """Validate and order an explicit certified expected-session/bar calendar.

    Timestamps require independently supplied local clock/offset evidence that
    agrees with the IANA timezone. This validates DST and shortened-session
    marks without inventing an exchange holiday generator. Certification and
    exact evidence references remain obligations of the canonical adapter.
    """
    fields = {"policy_id", "version", "temporal_precision", "calendar_id", "calendar_version",
              "timezone", "observation_convention", "coverage_start", "coverage_end", "marks", "evidence"}
    object_fields(config, fields, path="schedule")
    result = deepcopy(config)
    result["policy_id"] = token(config["policy_id"], "schedule.policy_id")
    if config["version"] != SCHEDULE_VERSION:
        raise ContractError("unsupported schedule policy interpretation version")
    token(config["calendar_id"], "schedule.calendar_id")
    if type(config["calendar_version"]) is not str or not VERSION.fullmatch(config["calendar_version"]):
        raise ContractError("invalid calendar definition version")
    precision = choice(config["temporal_precision"], PRECISIONS, "schedule.temporal_precision")
    zone = _zone(config["timezone"])
    token(config["observation_convention"], "schedule.observation_convention")
    result["evidence"] = normalize_reference(config["evidence"], "schedule.evidence")
    for field in ("coverage_start", "coverage_end"):
        normalize_time(config[field], precision, "schedule." + field)
    if config["coverage_start"] >= config["coverage_end"]:
        raise ContractError("schedule coverage must have ordered distinct inclusive bounds")
    if type(config["marks"]) is not list or not config["marks"]:
        raise ContractError("schedule requires a nonempty expected mark list")
    marks, identities, times, sessions = [], set(), set(), []
    seen_sessions = set()
    for item in config["marks"]:
        required = {"mark_id", "time", "session_id"} | ({"local_time"} if precision == "utc_timestamp" else set())
        object_fields(item, required, path="schedule.mark")
        token(item["mark_id"], "mark_id")
        token(item["session_id"], "session_id")
        normalize_time(item["time"], precision, "mark.time")
        if not config["coverage_start"] <= item["time"] <= config["coverage_end"]:
            raise ContractError("expected mark lies outside certified calendar coverage")
        if item["mark_id"] in identities or item["time"] in times:
            raise ContractError("duplicate expected mark identity or time")
        identities.add(item["mark_id"])
        times.add(item["time"])
        if precision == "utc_timestamp":
            local_text = item["local_time"]
            if type(local_text) is not str:
                raise ContractError("mark.local_time: require explicit local clock and UTC offset evidence")
            try:
                local = datetime.fromisoformat(local_text)
            except ValueError as error:
                raise ContractError("invalid local clock evidence") from error
            expected = _instant(item["time"]).astimezone(zone)
            if local.tzinfo is None or local.utcoffset() is None:
                raise ContractError("local clock evidence requires an explicit UTC offset")
            if (local.replace(tzinfo=None) != expected.replace(tzinfo=None)
                    or local.utcoffset() != expected.utcoffset()):
                raise ContractError("local clock/offset evidence does not match UTC time and timezone")
        marks.append(deepcopy(item))
    marks.sort(key=lambda mark: mark["time"])
    for mark in marks:
        if not sessions or sessions[-1] != mark["session_id"]:
            if mark["session_id"] in seen_sessions:
                raise ContractError("session marks must be contiguous and ordered")
            sessions.append(mark["session_id"])
            seen_sessions.add(mark["session_id"])
    result["marks"] = marks
    return result


def schedule_semantics(config):
    """Logical policy projection; exact finite marks/coverage are run evidence."""
    value = validate_schedule(config)
    return {key: value[key] for key in ("policy_id", "version", "temporal_precision", "calendar_id",
            "calendar_version", "timezone", "observation_convention")}


def normalize_anchors(config, anchors):
    """Order stable anchors, binding explicit sets to their declared policy ID.

    Explicit anchor_set_id is checked against the Target definition by preflight;
    finite actual members remain materialization evidence. Date precision is
    retained, and neither appending future members nor caller order changes IDs.
    """
    schedule = validate_schedule(config)
    if type(anchors) is not dict:
        raise ContractError("anchors: expected explicit anchor request object")
    mode = choice(anchors.get("mode"), {"market_schedule", "explicit"}, "anchors.mode")
    if mode == "market_schedule":
        object_fields(anchors, {"mode", "mark_ids"}, path="anchors")
        members = anchors["mark_ids"]
        if type(members) is not list or not members or any(type(x) is not str for x in members):
            raise ContractError("market anchors require nonempty mark_ids")
        if len(members) != len(set(members)):
            raise ContractError("duplicate requested anchor mark")
        by_id = {mark["mark_id"]: mark for mark in schedule["marks"]}
        if set(members) - by_id.keys():
            raise ContractError("requested anchor is absent from expected calendar marks")
        times = [by_id[key]["time"] for key in members]
    else:
        object_fields(anchors, {"mode", "anchor_set_id", "times"}, path="anchors")
        token(anchors["anchor_set_id"], "anchors.anchor_set_id")
        times = anchors["times"]
        if type(times) is not list or not times:
            raise ContractError("explicit anchors require nonempty canonical times")
        for value in times:
            normalize_time(value, schedule["temporal_precision"], "anchor")
        if len(times) != len(set(times)):
            raise ContractError("duplicate explicit anchor time")
    result = []
    semantics = schedule_semantics(schedule)
    for value in sorted(times):
        if not schedule["coverage_start"] <= value <= schedule["coverage_end"]:
            raise ContractError("prediction anchor outside certified calendar coverage")
        identity = {"kind": "target_prediction_anchor", "version": SCHEDULE_VERSION,
                    "schedule_semantics": semantics, "anchor_mode": mode,
                    "anchor_set_id": anchors.get("anchor_set_id"), "time": value}
        result.append({"anchor_id": "ANCHOR_" + digest(identity), "prediction_anchor": value,
                       "temporal_precision": schedule["temporal_precision"]})
    return result


def _add(value, duration, precision, zone):
    amount, unit = duration["amount"], duration["unit"]
    if precision == "date":
        if unit != "calendar_days":
            raise ContractError("elapsed duration requires timestamp precision, including zero durations")
        try:
            return (date.fromisoformat(value) + timedelta(days=amount)).isoformat()
        except OverflowError as error:
            raise ContractError("calendar duration overflows supported date range") from error
    if amount == 0:
        return value
    try:
        start = _instant(value)
        if unit == "elapsed_seconds":
            return _utc(start + timedelta(seconds=amount))
        # A local calendar interval retains the local clock, not 24 elapsed hours.
        wall = start.astimezone(zone).replace(tzinfo=None) + timedelta(days=amount)
        possible = []
        for fold in (0, 1):
            candidate = wall.replace(tzinfo=zone, fold=fold)
            if candidate.astimezone(dt_timezone.utc).astimezone(zone).replace(tzinfo=None) == wall:
                stamp = _utc(candidate)
                if stamp not in possible:
                    possible.append(stamp)
        if len(possible) != 1:
            raise ContractError("calendar interval reaches ambiguous or nonexistent local clock")
        return possible[0]
    except OverflowError as error:
        raise ContractError("duration overflows supported timestamp range") from error


def add_duration(value, duration, precision, timezone):
    """Apply the same declared duration semantics to entry or finalization waits."""
    normalize_time(value, precision)
    return _add(value, _duration(duration), precision, _zone(timezone))


def resolve_intervals(config, anchors, entry, horizon, endpoint):
    """Preflight all scheduling choices before any price calculation.

    Exact endpoint requires an expected mark; next_scheduled chooses the first
    expected mark at or after the intended endpoint within explicit tolerance.
    This is schedule matching only. Missing prices never move these endpoints.
    A trading-session horizon requires one declared observation mark per session;
    intraday calendars instead use scheduled_bars or explicit temporal horizons.
    """
    schedule = validate_schedule(config)
    entry, horizon, endpoint = normalize_entry(entry), normalize_horizon(horizon), normalize_endpoint(endpoint)
    precision, zone = schedule["temporal_precision"], _zone(schedule["timezone"])
    if precision == "date" and (horizon["unit"] == "elapsed_seconds"
            or entry["delay"]["unit"] == "elapsed_seconds"
            or endpoint["tolerance"]["unit"] == "elapsed_seconds"):
        raise ContractError("elapsed duration policies require timestamp precision")
    marks = schedule["marks"]
    times = [mark["time"] for mark in marks]
    by_time = {mark["time"]: index for index, mark in enumerate(marks)}
    if horizon["unit"] == "trading_sessions" and len({m["session_id"] for m in marks}) != len(marks):
        raise ContractError("trading_sessions requires one declared observation mark per session")
    intervals = []
    for anchor in normalize_anchors(schedule, anchors):
        threshold = _add(anchor["prediction_anchor"], entry["delay"], precision, zone)
        if entry["rule"] == "anchor_mark":
            if threshold not in by_time:
                raise ContractError("anchor_mark plus declared delay is not an exact expected mark")
            start_index = by_time[threshold]
        else:
            start_index = bisect_right(times, threshold)
            if start_index == len(times):
                raise ContractError("insufficient calendar coverage for strictly subsequent entry")
        start = marks[start_index]
        if horizon["unit"] in {"trading_sessions", "scheduled_bars"}:
            intended_index = start_index + horizon["amount"]
            if intended_index >= len(marks):
                raise ContractError("insufficient calendar coverage for scheduled horizon")
            intended_end = marks[intended_index]["time"]
        else:
            intended_end = _add(start["time"], horizon, precision, zone)
        if intended_end > schedule["coverage_end"]:
            raise ContractError("insufficient calendar coverage for intended endpoint")
        if endpoint["rule"] == "exact":
            if intended_end not in by_time:
                raise ContractError("exact intended endpoint is not an expected calendar mark")
            exit_index = by_time[intended_end]
        else:
            exit_index = bisect_left(times, intended_end)
            if exit_index >= len(marks):
                raise ContractError("insufficient calendar coverage to resolve next scheduled endpoint")
            limit = _add(intended_end, endpoint["tolerance"], precision, zone)
            if marks[exit_index]["time"] > limit:
                raise ContractError("next scheduled endpoint exceeds bounded tolerance")
        finish = marks[exit_index]
        if finish["time"] <= start["time"]:
            raise ContractError("return endpoint must be strictly after resolved entry")
        intervals.append({**anchor, "entry_time": start["time"], "intended_end": intended_end,
                          "exit_time": finish["time"], "entry_mark_id": start["mark_id"],
                          "exit_mark_id": finish["mark_id"]})
    return intervals


def temporal_eligible(available_at, available_precision, cutoff, cutoff_precision,
                      policy="strict", timezone=None):
    """Certify historical ordering without fabricating date-only intraday times.

    strict requires identical precision. Date-only evidence must precede the
    cutoff date strictly. conservative_next_day permits mixed precision only
    with an explicit common timezone and compares whole local dates. Unknown
    availability cannot qualify. Exact timestamp equality is eligible.
    """
    choice(policy, {"strict", "conservative_next_day"}, "temporal policy")
    choice(available_precision, PRECISIONS, "availability precision")
    normalize_time(cutoff, cutoff_precision, "historical cutoff")
    if available_at is None:
        return {"eligible": False, "reason": "AVAILABILITY_UNKNOWN"}
    normalize_time(available_at, available_precision, "available_at")
    if available_precision == cutoff_precision == "utc_timestamp":
        eligible = available_at <= cutoff
        return {"eligible": eligible, "reason": None if eligible else "NOT_YET_AVAILABLE"}
    if available_precision != cutoff_precision:
        if policy != "conservative_next_day" or timezone is None:
            return {"eligible": False, "reason": "TEMPORAL_PRECISION_INCOMPATIBLE"}
        zone = _zone(timezone)
        available_date = (_instant(available_at).astimezone(zone).date().isoformat()
                          if available_precision == "utc_timestamp" else available_at)
        cutoff_date = (_instant(cutoff).astimezone(zone).date().isoformat()
                       if cutoff_precision == "utc_timestamp" else cutoff)
    else:
        available_date, cutoff_date = available_at, cutoff
    eligible = available_date < cutoff_date
    reason = None if eligible else ("AMBIGUOUS_SAME_DAY" if available_date == cutoff_date else "NOT_YET_AVAILABLE")
    return {"eligible": eligible, "reason": reason}


def align_feature(feature, feature_precision, interval, *, policy="strict", timezone=None):
    """Check a persisted Feature observation against a Target prediction cutoff.

    This does not check Target label eligibility, which belongs to the separate
    historical training cutoff. It never modifies or recalculates a Feature.
    """
    if type(feature) is not dict or "available_at" not in feature:
        raise ContractError("Feature alignment requires explicit available_at evidence")
    if type(interval) is not dict or not {"anchor_id", "prediction_anchor", "temporal_precision"} <= interval.keys():
        raise ContractError("Feature alignment requires a resolved canonical Target anchor")
    result = temporal_eligible(feature["available_at"], feature_precision,
                               interval["prediction_anchor"], interval["temporal_precision"], policy, timezone)
    if result["eligible"]:
        for field in ("evaluation_cutoff", "reference_time"):
            if feature.get(field) is not None:
                evidence = temporal_eligible(feature[field], feature_precision, interval["prediction_anchor"],
                                             interval["temporal_precision"], policy, timezone)
                if not evidence["eligible"]:
                    result = {"eligible": False, "reason": "FEATURE_" + field.upper() + "_AFTER_ANCHOR"}
                    break
    if result["eligible"] and feature.get("status", "valid") != "valid":
        result = {"eligible": False, "reason": "FEATURE_INVALID"}
    return {**result, "anchor_id": interval["anchor_id"], "prediction_anchor": interval["prediction_anchor"],
            "feature_available_at": feature["available_at"], "feature_temporal_precision": feature_precision}


def select_feature_at_anchor(rows, feature_precision, interval, *, policy="strict", timezone=None):
    """Select the latest eligible observation of one already selected Feature series.

    Mixed entity/measure/dimension sets and duplicate temporal candidates are
    rejected rather than choosing arbitrary source order. Appending future
    observations cannot change an earlier eligible selection.
    """
    if type(rows) is not list:
        raise ContractError("Feature rows must be a list")
    selected, keys, series = [], set(), set()
    for row in rows:
        if type(row) is not dict:
            raise ContractError("invalid Feature observation")
        series.add(digest({field: row.get(field) for field in ("entity_id", "measure", "dimensions")}))
        alignment = align_feature(row, feature_precision, interval, policy=policy, timezone=timezone)
        if not alignment["eligible"]:
            continue
        key = (row.get("evaluation_cutoff") or row["available_at"], row.get("reference_time") or "")
        if key in keys:
            raise ContractError("ambiguous duplicate Feature observation at eligible temporal key")
        keys.add(key)
        selected.append((key, row))
    if len(series) > 1:
        raise ContractError("Feature alignment requires one selected entity/measure/dimension series")
    return deepcopy(max(selected, key=lambda pair: pair[0])[1]) if selected else None
