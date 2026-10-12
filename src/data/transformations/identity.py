"""Deterministic canonical identities; fixture utilities do not publish records.

Feature/Signal identities use the existing 0.2.0 predictor-recipe projection.
Date-aware transient execution keys have an explicitly separate identity profile;
they are not platform0.2 materialization manifests or a second persistent store.
"""
from copy import deepcopy
import hashlib
import json

from .contracts import (ContractError, EXECUTION_IDENTITY_PROFILE, INTEGER, canonical_decimal,
    choice, normalize_cutoffs, normalize_input, normalize_reference, normalize_references,
    normalize_selection, normalize_time, object_fields, token)


def canonical_bytes(value):
    def check(item):
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise ContractError("Canonical objects require string keys")
            for child in item.values(): check(child)
        elif type(item) is list:
            for child in item: check(child)
        elif type(item) not in (str, int, bool, type(None)):
            raise ContractError("Canonical values do not include floats or custom objects")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def semantic_record(record):
    result = deepcopy(record)
    result.pop("display_name", None)
    if result.get("record_type") == "snapshot_manifest": result.pop("members", None)
    if result.get("record_type") == "materialization_manifest": result.pop("partitions", None)
    return result


def reference(record):
    return normalize_reference({"id":record["id"], "version":record["version"], "content_sha256":digest(semantic_record(record))})


immutable_reference = reference


def normalize_bindings(values):
    if type(values) not in (list, tuple):
        raise ContractError("policy bindings: expected list")
    result = []
    for value in values:
        object_fields(value, {"role", "artifact"}, path="policy binding")
        result.append({"role":token(value["role"]), "artifact":normalize_reference(value["artifact"])})
    if len(result) != len({item["role"] for item in result}):
        raise ContractError("policy bindings: duplicate role")
    return sorted(result, key=lambda x:x["role"])


def normalize_parameter(value):
    object_fields(value, {"name", "unit", "value"}, path="parameter")
    typed = value["value"]
    object_fields(typed, {"kind", "value"}, path="parameter value")
    kind = choice(typed["kind"], {"decimal", "integer", "boolean", "token", "reference"}, "parameter kind")
    data = typed["value"]
    if kind == "decimal": canonical_decimal(data)
    elif kind == "integer":
        if type(data) is not str or not INTEGER.fullmatch(data):
            raise ContractError("parameter: expected canonical integer string")
    elif kind == "boolean":
        if type(data) is not bool: raise ContractError("parameter: expected boolean")
    elif kind == "token": token(data)
    else: data = normalize_reference(data)
    return {"name":token(value["name"]), "unit":token(value["unit"]), "value":{"kind":kind, "value":data}}


def normalize_recipe(value, *, execution=True):
    """Normalize 0.2 fields; execution defaults to this library's strict subset.

    execution=False supports existing record-profile recipes for identity parity;
    it does not make general multi-series graphs executable by this library.
    """
    required = {"sources", "steps", "output_node", "output_unit", "calculation_scope_requirement", "scope_policy"}
    extensions = {"selection", "history_mode", "history_policy", "execution_policy"}
    object_fields(value, required, extensions | {"evaluation_policy"}, "predictor_recipe")
    if extensions & set(value) and not extensions <= set(value):
        raise ContractError("recipe execution fields must be supplied together")
    if execution and not extensions <= set(value):
        raise ContractError("executable recipe requires explicit selection/history/execution policies")
    if type(value["sources"]) is not list or not value["sources"] or type(value["steps"]) is not list or not value["steps"]:
        raise ContractError("recipe requires sources and ordered steps")
    sources, known = [], set()
    for source in value["sources"]:
        object_fields(source, {"alias", "source_view"}, path="recipe source")
        alias = token(source["alias"])
        if alias in known: raise ContractError("duplicate source alias")
        known.add(alias)
        sources.append({"alias":alias, "source_view":normalize_reference(source["source_view"])})
    if execution and len(sources) != 1: raise ContractError("only one input source is supported")
    previous, transformed, steps = sources[0]["alias"], False, []
    for original in value["steps"]:
        object_fields(original, {"node", "phase", "operator", "inputs", "parameters"}, {"grid_policy"}, "recipe step")
        node = token(original["node"])
        phase = choice(original["phase"], {"interaction", "transformation"}, "recipe phase")
        if node in known: raise ContractError("duplicate recipe node")
        if type(original["inputs"]) is not list or not original["inputs"]:
            raise ContractError("recipe inputs must be an ordered nonempty list")
        inputs = [token(x) for x in original["inputs"]]
        if any(x not in known for x in inputs): raise ContractError("recipe has forward or missing inputs")
        if transformed and phase == "interaction": raise ContractError("interaction cannot follow a transformation")
        if execution and (phase != "transformation" or inputs != [previous]):
            raise ContractError("only an explicitly ordered single-series transformation chain is supported")
        if type(original["parameters"]) is not list: raise ContractError("parameters must be a list")
        params = [normalize_parameter(p) for p in original["parameters"]]
        if len(params) != len({p["name"] for p in params}): raise ContractError("duplicate parameter name")
        step = {"node":node, "phase":phase, "operator":normalize_reference(original["operator"]), "inputs":inputs, "parameters":sorted(params,key=lambda p:p["name"])}
        if "grid_policy" in original: step["grid_policy"] = normalize_reference(original["grid_policy"])
        steps.append(step); known.add(node); previous = node; transformed |= phase == "transformation"
    output = token(value["output_node"])
    if output not in known or not transformed or (execution and output != previous):
        raise ContractError("invalid recipe output node")
    scope = choice(value["calculation_scope_requirement"], {"none", "bound_at_materialization"}, "calculation scope")
    if scope == "none":
        if value["scope_policy"] is not None: raise ContractError("scope_policy must be null for scope-independent recipes")
        policy = None
    else: policy = normalize_reference(value["scope_policy"])
    if execution and scope != "none": raise ContractError("cross-sectional/scoped calculations are outside this single-series library")
    result = {"sources":sorted(sources,key=lambda s:s["alias"]), "steps":steps, "output_node":output,
              "output_unit":token(value["output_unit"]), "calculation_scope_requirement":scope, "scope_policy":policy}
    if extensions <= set(value):
        result.update(selection=normalize_selection(value["selection"]),
                      history_mode=choice(value["history_mode"], {"resolved_state", "emitted_history"}, "history_mode"),
                      history_policy=normalize_reference(value["history_policy"]), execution_policy=normalize_reference(value["execution_policy"]))
    if "evaluation_policy" in value:
        result["evaluation_policy"] = normalize_reference(value["evaluation_policy"])
    return result


def recipe_digest(recipe):
    return digest({"identity_profile":"0.2.0", "kind":"predictor_recipe", "recipe":normalize_recipe(recipe, execution=False)})


def feature_id(recipe): return "FEATURE_" + recipe_digest(recipe)
def signal_id(recipe): return "SIGNAL_" + recipe_digest(recipe)


def make_feature_definition(recipe, display_name="Fixture feature"):
    normalized = normalize_recipe(recipe)
    if type(display_name) is not str or not display_name or len(display_name)>500 or any(ord(c)<32 or ord(c)>126 for c in display_name):
        raise ContractError("invalid display name")
    return {"schema_version":"0.2.0", "record_type":"feature_definition", "id":feature_id(normalized), "version":"1.0.0",
            "display_name":display_name, "body":{"signal_id":signal_id(normalized), "recipe":normalized}}


MATERIALIZATION_FIELDS = {"dataset_role", "definition", "source_snapshots", "upstream_materializations", "calculation_scope", "membership_snapshot", "information_cutoff", "period", "observation_schema_version", "implementation", "policy_bindings"}


def materialization_input_key(value):
    """Existing exact platform0.2 UTC materialization request projection."""
    object_fields(value, MATERIALIZATION_FIELDS, path="materialization input_key")
    result = deepcopy(value)
    choice(result["dataset_role"], {"feature", "target"}, "dataset_role")
    for field in ("definition", "implementation"): result[field] = normalize_reference(result[field])
    for field in ("source_snapshots", "upstream_materializations"): normalize_references(result[field],field)
    if not result["source_snapshots"]: raise ContractError("source_snapshots cannot be empty")
    for field in ("calculation_scope", "membership_snapshot"):
        if result[field] is not None: result[field] = normalize_reference(result[field])
    normalize_time(result["information_cutoff"], "utc_timestamp")
    object_fields(result["period"], {"start_inclusive", "end_exclusive"}, path="period")
    for time in result["period"].values(): normalize_time(time,"utc_timestamp")
    if result["period"]["start_inclusive"] >= result["period"]["end_exclusive"]: raise ContractError("period must be nonempty")
    choice(result["observation_schema_version"], {"0.2.0"}, "observation_schema_version")
    normalize_bindings(result["policy_bindings"])
    if not result["policy_bindings"]: raise ContractError("materialization policy bindings are required")
    return result


def materialization_id(input_key):
    return "MATERIALIZATION_" + digest({"identity_profile":"0.2.0", "kind":"materialization", "input_key":materialization_input_key(input_key)})


def input_series_digest(series):
    normalized = normalize_input(series)
    normalized.pop("provenance", None)
    if normalized.get("execution") is not None:
        normalized["execution"].pop("executed_at", None)
    return digest(normalized)


def execution_materialization_key(recipe_ref, input_series, cutoffs, implementation_ref, policy_bindings=(), *, output_index=None):
    series = normalize_input(input_series)
    precision = series["temporal_precision"]
    normalized_cutoffs = normalize_cutoffs(cutoffs, precision)
    key = {"recipe":normalize_reference(recipe_ref), "source_snapshots":series["source_snapshots"],
           "input_series_sha256":input_series_digest(series), "temporal_precision":precision,
           "evaluation_cutoffs":normalized_cutoffs,
           "implementation":normalize_reference(implementation_ref), "policy_bindings":normalize_bindings(policy_bindings)}
    if output_index is None:
        key["output_projection"] = "latest_per_cutoff"
    else:
        if type(output_index) is not list:
            raise ContractError("output_index must be an explicit list")
        result, seen = [], set()
        for row in output_index:
            object_fields(row, {"reference_time", "evaluation_cutoff"}, path="output_index")
            cutoff = normalize_time(row["evaluation_cutoff"], precision, "output_index.evaluation_cutoff")
            reference_time = row["reference_time"]
            if reference_time is not None:
                normalize_time(reference_time, precision, "output_index.reference_time")
            if cutoff not in normalized_cutoffs or (reference_time is not None and reference_time > cutoff):
                raise ContractError("output_index exceeds the declared cutoff")
            pair = (cutoff, reference_time)
            if pair in seen:
                raise ContractError("output_index has a duplicate temporal key")
            seen.add(pair)
            result.append({"reference_time":reference_time,"evaluation_cutoff":cutoff})
        key["output_index"] = sorted(result, key=lambda row:(row["evaluation_cutoff"], row["reference_time"] or ""))
    return key


def execution_materialization_id(recipe_ref, input_series, cutoffs, implementation_ref, policy_bindings=(), *, output_index=None):
    key = execution_materialization_key(recipe_ref,input_series,cutoffs,implementation_ref,policy_bindings,output_index=output_index)
    return "MATERIALIZATION_" + digest({"identity_profile":EXECUTION_IDENTITY_PROFILE, "kind":"materialization", "input_key":key})
