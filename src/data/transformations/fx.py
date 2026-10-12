"""Reusable canonical FX quotes, upstream of Features and forward return Targets.

This module does no I/O, vintage selection, calendar generation or publication.
Inputs must already select one pinned retrospective/vintage state. Unknown source
availability remains unknown. A shared input leg is normalized once when building
the universe; original direct prices never make reciprocal round trips.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, localcontext
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import (ContractError, canonical_decimal, choice, decimal_text,
    normalize_reference, normalize_time, object_fields, text, token)
from .identity import digest

VERSION = "1.0.0"
SOURCE_SYMBOLS = ("AUD/USD", "EUR/USD", "GBP/USD", "NZD/USD", "USD/CNH",
    "CAD/USD", "CHF/USD", "JPY/USD", "CZK/USD", "HKD/USD", "HUF/USD", "ILS/USD",
    "MXN/USD", "NOK/USD", "PLN/USD", "SEK/USD", "SGD/USD", "ZAR/USD")
DIRECT = ("AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCNH")
INVERSE = ("USDCAD", "USDCHF", "USDJPY", "USDCZK", "USDHKD", "USDHUF", "USDILS",
    "USDMXN", "USDNOK", "USDPLN", "USDSEK", "USDSGD", "USDZAR")
CROSS = ("AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "CADCHF", "CADJPY", "CHFJPY",
    "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "GBPAUD", "GBPCAD",
    "GBPCHF", "GBPJPY", "GBPNZD", "NZDCAD", "NZDCHF", "NZDJPY", "EURCZK", "EURHUF",
    "EURNOK", "EURPLN")
INSTRUMENTS = DIRECT + INVERSE + CROSS
SOURCE_BY_CURRENCY = {symbol.split("/")[1] if symbol.startswith("USD/") else symbol.split("/")[0]: symbol
                      for symbol in SOURCE_SYMBOLS}
assert len(SOURCE_SYMBOLS) == len(set(SOURCE_SYMBOLS)) == 18
assert len(INSTRUMENTS) == len(set(INSTRUMENTS)) == 43
assert (len(DIRECT), len(INVERSE), len(CROSS)) == (5, 13, 25)


def instrument_spec(instrument_id):
    if instrument_id not in INSTRUMENTS:
        raise ContractError("FX instrument is outside the exact requested 43-instrument universe")
    base, quote = instrument_id[:3], instrument_id[3:]
    dependencies = sorted({SOURCE_BY_CURRENCY[currency] for currency in (base, quote) if currency != "USD"})
    return {"instrument_id": instrument_id, "economic_id": "FX_" + base + "_" + quote,
            "base_currency": base, "quote_currency": quote, "unit": quote + "_per_" + base,
            "method": "direct" if instrument_id in DIRECT else "inverse" if instrument_id in INVERSE else "usd_triangulation",
            "source_symbols": dependencies}


def universe_specs():
    return [instrument_spec(instrument) for instrument in INSTRUMENTS]


def _zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise ContractError("FX timing requires a valid IANA timezone") from error


def normalize_metadata(symbol, value):
    if symbol not in SOURCE_SYMBOLS:
        raise ContractError("Unknown FX source; another currency, including CNY, cannot substitute")
    required = {"base_currency", "quote_currency", "unit", "price_basis", "price_field", "timing"}
    object_fields(value, required, {"source_view", "dataset_id"}, "FX source metadata")
    base, quote = symbol.split("/")
    if (value["base_currency"], value["quote_currency"], value["unit"]) != (base, quote, quote + "_per_" + base):
        raise ContractError("Verified source currencies/units do not match the explicitly requested source direction")
    if value["price_field"] != "close":
        raise ContractError("Only canonical endpoint close observations are supported; no reconstructed OHLC or volume")
    choice(value["price_basis"], {"unknown", "midpoint", "bid", "ask", "provider_close"}, "price_basis")
    timing = value["timing"]
    object_fields(timing, {"timezone", "bar_boundary", "session_convention", "synchronization"}, path="FX timing")
    choice(timing["synchronization"], {"exact", "unverified"}, "timing.synchronization")
    if timing["timezone"] is not None:
        _zone(timing["timezone"])
    for field in ("bar_boundary", "session_convention"):
        if timing[field] is not None:
            text(timing[field], "timing." + field)
    if timing["synchronization"] == "exact" and any(timing[field] is None for field in ("timezone", "bar_boundary", "session_convention")):
        raise ContractError("Exact valuation requires documented timezone, bar boundary and session convention")
    result = deepcopy(value)
    if "source_view" in value:
        result["source_view"] = normalize_reference(value["source_view"])
    if "dataset_id" in value:
        token(value["dataset_id"], "dataset_id")
    return result


def normalize_alignment_policy(value):
    object_fields(value, {"id", "version", "mode", "approval_state", "approval_evidence",
                          "max_date_gap", "max_valuation_gap_seconds"}, path="FX alignment policy")
    token(value["id"], "alignment_policy.id")
    if value["version"] != VERSION:
        raise ContractError("Unsupported FX alignment version")
    choice(value["mode"], {"single_source_observation", "retrospective_date_label", "exact_valuation"}, "FX alignment mode")
    if value["approval_state"] != "approved":
        raise ContractError("An explicitly approved FX alignment policy is required before construction")
    normalize_reference(value["approval_evidence"], "alignment approval evidence")
    if type(value["max_date_gap"]) is not int or value["max_date_gap"] != 0:
        raise ContractError("Only equal native date labels are supported; no date carry or filling")
    expected = 0 if value["mode"] == "exact_valuation" else None
    if value["max_valuation_gap_seconds"] != expected or (expected == 0 and type(value["max_valuation_gap_seconds"]) is not int):
        raise ContractError("Exact synchronization needs zero seconds; retrospective/single-source wall-clock tolerance is unknown")
    return deepcopy(value)


def recipe(instrument_id, source_metadata, alignment_policy=None):
    """Semantic recipe only; no observation values, coverage or Target dependency.

    A pending recipe can be registered without alignment approval; actual cross
    execution always requires the explicitly approved policy. Callers publishing
    bound recipes should pass the policy, whose full versioned semantics are kept.
    """
    spec = instrument_spec(instrument_id)
    metadata = {symbol: normalize_metadata(symbol, source_metadata[symbol]) for symbol in spec["source_symbols"]}
    alignment = None if alignment_policy is None else normalize_alignment_policy(alignment_policy)
    if alignment and alignment["mode"] == "single_source_observation" and spec["method"] == "usd_triangulation":
        raise ContractError("Single-source alignment cannot authorize a two-leg FX cross")
    body = {"kind": "canonical_fx_price", "version": VERSION, **spec,
            "formula": "P_A_B=U_A/U_B; U_X=USD per X; U_USD=1",
            "arithmetic": "decimal_50_then_binary64_guard", "sources": metadata,
            "normalization": {symbol: "reciprocal" if symbol.startswith("USD/") else "identity" for symbol in metadata},
            "direct_source_retention": spec["method"] == "direct",
            "fallback": "none", "missing": "retain_null", "nonpositive": "retain_null",
            "alignment_policy": alignment}
    return {"id": "FXRECIPE_" + digest(body), "version": VERSION, "body": body}


def _precision(value):
    return "utc_timestamp" if isinstance(value, str) and "T" in value else "date"


def _time_or_none(value):
    if value is not None:
        normalize_time(value, _precision(value))
    return value


def _row(symbol, original, metadata):
    required = {"reference_time", "value", "status", "reason_code", "lineage", "available_at", "original_ingested_at", "vintage_id"}
    optional = {"valuation_time", "local_time", "stale", "quality_flags"}
    object_fields(original, required, optional, "FX source row")
    normalize_time(original["reference_time"], "date", "FX native bar date")
    text(original["lineage"], "FX source record lineage")
    token(original["vintage_id"], "FX source vintage")
    choice(original["status"], {"valid", "missing", "invalid"}, "FX source status")
    _time_or_none(original["available_at"])
    if original["original_ingested_at"] is not None:
        normalize_time(original["original_ingested_at"], "utc_timestamp", "original_ingested_at")
    if original.get("valuation_time") is not None:
        normalize_time(original["valuation_time"], "utc_timestamp", "valuation_time")
    if "stale" in original and type(original["stale"]) is not bool:
        raise ContractError("stale must be evidenced boolean, never inferred from unchanged prices")
    flags = original.get("quality_flags", [])
    if type(flags) is not list or any(type(flag) is not str for flag in flags):
        raise ContractError("quality_flags must be an explicit string list")
    row = deepcopy(original)
    row.setdefault("valuation_time", None)
    row.setdefault("local_time", None)
    row.setdefault("stale", False)
    row["quality_flags"] = sorted(set(flags))
    reason = None
    if row["status"] != "valid":
        reason = "SOURCE_MISSING" if row["status"] == "missing" else "SOURCE_INVALID"
    elif row["stale"] or "stale" in flags:
        reason = "STALE_SOURCE_OBSERVATION"
    elif (row["available_at"] is not None and row["valuation_time"] is not None
          and _precision(row["available_at"]) == "utc_timestamp" and row["available_at"] < row["valuation_time"]):
        reason = "AVAILABILITY_PRECEDES_VALUATION"
    elif row["available_at"] is not None and _precision(row["available_at"]) == "date" and row["available_at"] < row["reference_time"]:
        reason = "AVAILABILITY_PRECEDES_VALUATION"
    else:
        try:
            number = Decimal(row["value"]) if type(row["value"]) is str else None
            if number is None:
                reason = "NON_NUMERIC_INPUT"
            elif not number.is_finite():
                reason = "NONFINITE_INPUT"
            elif number <= 0:
                reason = "NONPOSITIVE_INPUT"
            else:
                canonical_decimal(row["value"])
                if not math.isfinite(float(number)):
                    reason = "NONFINITE_INPUT"
        except (DecimalException, ValueError, TypeError, ContractError, OverflowError):
            reason = "NON_NUMERIC_INPUT"
    semantics = {"source_symbol": symbol, "source_metadata": metadata, "row": row}
    dependency = {"id": "FXINPUT_" + digest(semantics), "source_symbol": symbol,
                  "reference_time": row["reference_time"], "lineage": row["lineage"],
                  "vintage_id": row["vintage_id"], "value": row["value"], "status": row["status"],
                  "available_at": row["available_at"], "original_ingested_at": row["original_ingested_at"],
                  "valuation_time": row["valuation_time"]}
    return {"row": row, "dependency": dependency, "failure": reason}


def _prepare(sources, source_metadata):
    if type(sources) is not dict or set(sources) - set(SOURCE_SYMBOLS):
        raise ContractError("Sources must use only the exact 18 requested provider symbols")
    prepared = {}
    for symbol, rows in sources.items():
        if symbol not in source_metadata:
            raise ContractError("Every supplied source needs explicit economic/timing metadata")
        metadata = normalize_metadata(symbol, source_metadata[symbol])
        if type(rows) is not list:
            raise ContractError("FX source observations must be an explicit list")
        groups = {}
        for original in rows:
            point = _row(symbol, original, metadata)
            groups.setdefault(point["row"]["reference_time"], []).append(point)
        prepared[symbol] = {}
        for day, points in sorted(groups.items()):
            unique = {point["dependency"]["id"]: point for point in points}
            points = [unique[key] for key in sorted(unique)]
            # True repeat copies may be reused. Competing selected rows/vintages
            # are an unresolved conflict, never an implicit latest/first choice.
            failure = "CONFLICTING_SOURCE_OBSERVATIONS" if len(points) > 1 else points[0]["failure"]
            prepared[symbol][day] = {"point": points[0], "dependencies": [p["dependency"] for p in points],
                                     "failure": failure, "duplicate_count": len(groups[day]) - len(points)}
    return prepared


def _number(operation, first, second=None):
    try:
        with localcontext() as context:
            context.prec = 50
            a = Decimal(first)
            value = a if operation == "direct" else Decimal(1) / a if operation == "inverse" else a / Decimal(second)
            if not value.is_finite() or value <= 0 or not math.isfinite(float(value)):
                return None, "NONFINITE_OUTPUT"
            return decimal_text(value), None
    except (DecimalException, OverflowError, ValueError, TypeError):
        return None, "NONFINITE_OUTPUT"


def _normalize_prepared(prepared):
    result = {}
    for symbol, rows in prepared.items():
        currency = symbol.split("/")[1] if symbol.startswith("USD/") else symbol.split("/")[0]
        operation = "inverse" if symbol.startswith("USD/") else "direct"
        currency_rows = []
        for day, point in rows.items():
            source = point["point"]["row"]
            failure = point["failure"]
            value = None
            if failure is None:
                value, failure = _number(operation, source["value"])
            item = {"currency": currency, "reference_time": day, "value": value,
                    "unit": "USD_per_" + currency, "normalization": "reciprocal" if operation == "inverse" else "identity",
                    "status": "valid" if failure is None else "missing" if failure == "SOURCE_MISSING" else "invalid",
                    "reason_code": failure, "input_dependencies": point["dependencies"],
                    "available_at": source["available_at"], "original_ingested_at": source["original_ingested_at"],
                    "valuation_time": source["valuation_time"], "duplicate_count": point["duplicate_count"]}
            # Duplicate count is diagnostics, not an economic change.
            item["id"] = "FXLEG_" + digest({k: v for k, v in item.items() if k != "duplicate_count"})
            currency_rows.append(item)
        result[currency] = currency_rows
    return result


def normalize_legs(sources, *, source_metadata):
    """Normalize each supplied currency once to USD per currency, with lineage."""
    return _normalize_prepared(_prepare(sources, source_metadata))


def _exact_evidence(symbol, point, metadata):
    timing = metadata["timing"]
    if timing["synchronization"] != "exact":
        return "UNVERIFIED_VALUATION_TIME"
    row = point["point"]["row"]
    if row["valuation_time"] is None or row["local_time"] is None:
        return "UNVERIFIED_VALUATION_TIME"
    try:
        instant = datetime.fromisoformat(row["valuation_time"].replace("Z", "+00:00"))
        local = datetime.fromisoformat(row["local_time"])
        expected = instant.astimezone(_zone(timing["timezone"]))
        if (local.tzinfo is None or local.utcoffset() != expected.utcoffset()
                or local.replace(tzinfo=None) != expected.replace(tzinfo=None)
                or local.date().isoformat() != row["reference_time"]):
            return "INCOMPATIBLE_VALUATION_TIME"
    except (ValueError, TypeError):
        return "INCOMPATIBLE_VALUATION_TIME"
    return None


def _retrospective_evidence(point, metadata):
    """Check supplied timing facts without requiring facts that are unknown.

    An offset local timestamp is evidence; a bare provider date is not midnight.
    Derived instants here are used only to detect contradictions, never published
    as fabricated source valuation/availability timestamps.
    """
    row = point["point"]["row"]
    local_text, utc_text = row["local_time"], row["valuation_time"]
    zone_name = metadata["timing"]["timezone"]
    instant = datetime.fromisoformat(utc_text.replace("Z", "+00:00")) if utc_text is not None else None
    local = None
    if local_text is not None:
        try:
            local = datetime.fromisoformat(local_text)
        except (ValueError, TypeError):
            return "INCOMPATIBLE_VALUATION_TIME", None
        if local.tzinfo is None or local.utcoffset() is None or local.date().isoformat() != row["reference_time"]:
            return "INCOMPATIBLE_VALUATION_TIME", None
        local_instant = local.astimezone(timezone.utc)
        if instant is not None and local_instant != instant:
            return "INCOMPATIBLE_VALUATION_TIME", None
        instant = local_instant
    if zone_name is not None and instant is not None:
        expected = instant.astimezone(_zone(zone_name))
        if expected.date().isoformat() != row["reference_time"]:
            return "INCOMPATIBLE_VALUATION_TIME", None
        if local is not None and (local.utcoffset() != expected.utcoffset()
                                  or local.replace(tzinfo=None) != expected.replace(tzinfo=None)):
            return "INCOMPATIBLE_VALUATION_TIME", None
    return None, instant


def _retrospective_incompatibility(points, source_metadata):
    """Unknown timing permits a date proxy; contradictory known timing does not.

    No elapsed-time tolerance is inferred. Different timezone names alone do not
    prove different sessions: they may be aliases or representations of the same
    global close. A synchronization evidence grade is not a session definition.
    """
    timings = [source_metadata[symbol]["timing"] for symbol in points]
    for field in ("bar_boundary", "session_convention"):
        known = {timing[field] for timing in timings if timing[field] is not None}
        if len(known) > 1:
            return "INCOMPATIBLE_SESSION_CONVENTION"
    instants = []
    for symbol, point in points.items():
        if point is None:
            continue
        failure, instant = _retrospective_evidence(point, source_metadata[symbol])
        if failure:
            return failure
        if instant is not None:
            instants.append(instant)
    if len(set(instants)) > 1:
        return "INCOMPATIBLE_VALUATION_TIME"
    return None


def _max_known(values):
    if not values or any(value is None for value in values):
        return None
    if len({_precision(value) for value in values}) != 1:
        return None
    return max(values)


def _construct(instrument_id, prepared, source_metadata, alignment, legs):
    specification = instrument_spec(instrument_id)
    bound_recipe = recipe(instrument_id, source_metadata, alignment)
    symbols = specification["source_symbols"]
    dates = sorted(set().union(*(set(prepared.get(symbol, {})) for symbol in symbols)))
    leg_lookup = {currency: {row["reference_time"]: row for row in rows} for currency, rows in legs.items()}
    result = []
    for day in dates:
        points = {symbol: prepared.get(symbol, {}).get(day) for symbol in symbols}
        dependencies = [item for symbol in symbols if points[symbol] is not None for item in points[symbol]["dependencies"]]
        failure = "MISSING_REQUIRED_OBSERVATION" if any(point is None for point in points.values()) else None
        for point in points.values():
            if point is not None and point["failure"] is not None:
                failure = point["failure"]
                break
        timing_failure = None
        if alignment["mode"] == "exact_valuation":
            conventions = [source_metadata[symbol]["timing"] for symbol in symbols]
            if any(item != conventions[0] for item in conventions[1:]):
                timing_failure = "INCOMPATIBLE_SESSION_CONVENTION"
            else:
                for symbol, point in points.items():
                    if point is not None:
                        timing_failure = _exact_evidence(symbol, point, source_metadata[symbol])
                        if timing_failure:
                            break
                valuations = {point["point"]["row"]["valuation_time"] for point in points.values() if point is not None}
                if timing_failure is None and len(valuations) > 1:
                    timing_failure = "INCOMPATIBLE_VALUATION_TIME"
            failure = failure or timing_failure
        elif alignment["mode"] == "retrospective_date_label" and specification["method"] == "usd_triangulation":
            timing_failure = _retrospective_incompatibility(points, source_metadata)
            failure = failure or timing_failure
        bases = {source_metadata[symbol]["price_basis"] for symbol in symbols}
        if len(bases) > 1:
            failure = failure or "INCOMPATIBLE_PRICE_BASIS"
        value, normalized = None, []
        for currency in (specification["base_currency"], specification["quote_currency"]):
            if currency == "USD":
                normalized.append({"currency": "USD", "id": "FXCONST_USD_ONE", "value": "1"})
            else:
                item = leg_lookup.get(currency, {}).get(day)
                normalized.append({"currency": currency, "id": item["id"] if item else None,
                                   "value": item["value"] if item else None})
        if failure is None:
            if specification["method"] == "direct":
                value = points[symbols[0]]["point"]["row"]["value"]
            elif specification["method"] == "inverse":
                value, failure = _number("inverse", points[symbols[0]]["point"]["row"]["value"])
            else:
                value, failure = _number("cross", normalized[0]["value"], normalized[1]["value"])
        available = _max_known([point["point"]["row"]["available_at"] if point else None for point in points.values()])
        ingested = _max_known([point["point"]["row"]["original_ingested_at"] if point else None for point in points.values()])
        basis = next(iter(bases)) if len(bases) == 1 else "incompatible"
        synchronization = ("not_applicable_single_source" if specification["method"] != "usd_triangulation" else
                           "exact" if alignment["mode"] == "exact_valuation" and timing_failure is None and failure is None else "unverified")
        flags = sorted(set(flag for point in points.values() if point for flag in point["point"]["row"]["quality_flags"]))
        if basis == "unknown":
            flags.append("PRICE_BASIS_UNKNOWN")
        if synchronization == "unverified":
            flags.append("SYNCHRONIZATION_UNVERIFIED")
        if available is None:
            flags.append("HISTORICAL_AVAILABILITY_UNKNOWN")
        row = {"instrument_id": instrument_id, "economic_id": specification["economic_id"], "recipe_id": bound_recipe["id"],
               "reference_time": day, "temporal_precision": "date", "method": specification["method"],
               "base_currency": specification["base_currency"], "quote_currency": specification["quote_currency"],
               "unit": specification["unit"], "price_basis": basis,
               "price_description": ("triangulated_midpoint_proxy" if basis == "midpoint" else "triangulated_" + basis + "_proxy")
                   if specification["method"] == "usd_triangulation" else "observed_" + basis if specification["method"] == "direct" else "inverse_" + basis,
               "value": value, "status": "valid" if failure is None else "missing" if failure in {"SOURCE_MISSING", "MISSING_REQUIRED_OBSERVATION"} else "invalid",
               "reason_code": failure, "available_at": available, "availability_precision": _precision(available) if available else None,
               "original_ingested_at": ingested, "synchronization": synchronization,
               "valuation_time": next((point["point"]["row"]["valuation_time"] for point in points.values() if point), None)
                   if alignment["mode"] == "exact_valuation" and timing_failure is None else None,
               "historical_eligibility_certified": False,
               "input_dependencies": dependencies, "normalized_leg_dependencies": normalized,
               "quality_flags": sorted(set(flags)), "alignment_policy_id": alignment["id"], "alignment_policy_version": alignment["version"]}
        row["id"] = "FXPRICE_" + digest(row)
        row["duplicate_input_count"] = sum(point["duplicate_count"] for point in points.values() if point)
        result.append(row)
    return result


def construct_prices(instrument_id, sources, *, alignment_policy, source_metadata):
    """Preserve the union of required input dates; never fill or shift a date."""
    alignment = normalize_alignment_policy(alignment_policy)
    spec = instrument_spec(instrument_id)
    if alignment["mode"] == "single_source_observation" and spec["method"] == "usd_triangulation":
        raise ContractError("Single-source policy cannot construct an FX cross")
    # Validate all supplied names, then process only this instrument's dependencies.
    if type(sources) is not dict or set(sources) - set(SOURCE_SYMBOLS):
        raise ContractError("Unexpected source outside the exact 18-source universe")
    selected = {symbol: sources.get(symbol, []) for symbol in spec["source_symbols"]}
    prepared = _prepare(selected, source_metadata)
    return _construct(instrument_id, prepared, source_metadata, alignment, _normalize_prepared(prepared))


def iter_construct_universe(sources, *, alignment_policy, source_metadata, single_source_policy=None):
    """Yield each instrument's rows while retaining only shared source/leg caches."""
    if type(sources) is not dict or set(sources) != set(SOURCE_SYMBOLS):
        raise ContractError("Universe construction requires exactly the 18 requested source keys (empty history allowed)")
    alignment = normalize_alignment_policy(alignment_policy)
    if alignment["mode"] == "single_source_observation":
        raise ContractError("The full universe contains crosses requiring a cross-alignment policy")
    single = alignment if single_source_policy is None else normalize_alignment_policy(single_source_policy)
    if single_source_policy is not None and single["mode"] != "single_source_observation":
        raise ContractError("single_source_policy must explicitly use single_source_observation")
    prepared = _prepare(sources, source_metadata)
    legs = _normalize_prepared(prepared)
    for instrument in INSTRUMENTS:
        yield instrument, _construct(instrument, prepared, source_metadata,
                                     alignment if instrument in CROSS else single, legs)


def construct_universe(sources, *, alignment_policy, source_metadata, single_source_policy=None):
    """Materialized convenience wrapper; large persisted builds should iterate."""
    return dict(iter_construct_universe(sources, alignment_policy=alignment_policy,
                                       source_metadata=source_metadata, single_source_policy=single_source_policy))


def affected_price_rows(rows, changed_input_ids):
    """Local dependency invalidation; unrelated input changes return no row IDs."""
    changed = set(changed_input_ids)
    return [row["id"] for row in rows if any(item["id"] in changed for item in row["input_dependencies"])]
