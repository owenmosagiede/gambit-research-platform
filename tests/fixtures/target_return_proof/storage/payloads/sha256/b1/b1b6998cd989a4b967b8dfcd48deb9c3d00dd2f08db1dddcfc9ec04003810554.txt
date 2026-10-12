"""Pure structural validation and identities for the proposed foundation contract.

A passing object is syntactically well formed, NOT registered, ready, or executable.
No filesystem, registry, data, environment, or certificate is read by these functions.
"""

import hashlib
import json
import re

CONTRACT_VERSION = "0.1.0"
_SCIENTIFIC_REFS = ("feature", "target", "scope", "research_spec")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}\Z", re.ASCII)
_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REQUEST_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z", re.ASCII)
_DEPENDENCIES = {
    "data_snapshots": {"required"},
    "availability_policy": {"required"},
    "implementation_manifest": {"required"},
    "scope_membership_and_eligibility": {"required", "inapplicable"},
    "readiness_evidence": {"required", "optional", "inapplicable"},
    "randomness_settings": {"required", "inapplicable"},
}


class ContractError(ValueError):
    """Malformed structural contract; not a scientific rejection."""


def _object(value, fields, path):
    if type(value) is not dict:
        raise ContractError(f"{path}: expected object")
    if any(type(key) is not str for key in value):
        raise ContractError(f"{path}: object keys must be strings")
    missing = set(fields) - set(value)
    extra = set(value) - set(fields)
    if missing or extra:
        raise ContractError(f"{path}: missing={sorted(missing)}, unexpected={sorted(extra)}")


def _pattern(value, pattern, path):
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ContractError(f"{path}: invalid string format")
    return value


def _choice(value, choices, path):
    if type(value) is not str or value not in choices:
        raise ContractError(f"{path}: expected one of {sorted(choices)}")
    return value


def _reference(value, path, immutable=False):
    fields = {"id", "version", "content_sha256"} if immutable else {"id", "version"}
    _object(value, fields, path)
    result = {
        "id": _pattern(value["id"], _ID, path + ".id"),
        "version": _pattern(value["version"], _VERSION, path + ".version"),
    }
    if immutable:
        result["content_sha256"] = _pattern(value["content_sha256"], _HASH, path + ".content_sha256")
    return result


def normalize_experiment(value):
    """Return a detached, validated five-input definition without lossy coercion."""
    _object(value, {*_SCIENTIFIC_REFS, "expected_direction"}, "experiment")
    result = {name: _reference(value[name], "experiment." + name) for name in _SCIENTIFIC_REFS}
    result["expected_direction"] = _choice(value["expected_direction"], {"POSITIVE", "NEGATIVE"}, "experiment.expected_direction")
    return result


def validate_submission(value):
    """Validate a request envelope, without recording or accepting a submission."""
    _object(value, {"contract_version", "request_id", "experiment"}, "submission")
    _choice(value["contract_version"], {CONTRACT_VERSION}, "submission.contract_version")
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": _pattern(value["request_id"], _REQUEST_ID, "submission.request_id"),
        "experiment": normalize_experiment(value["experiment"]),
    }


def _dependency(value, name):
    path = "dependencies." + name
    if type(value) is not dict:
        raise ContractError(f"{path}: expected object")
    requirement = _choice(value.get("requirement"), _DEPENDENCIES[name], path + ".requirement")
    bindings = value.get("bindings")
    if type(bindings) is not list:
        raise ContractError(f"{path}.bindings: expected list")
    if requirement == "required" and not bindings:
        raise ContractError(f"{path}: required dependency cannot be unresolved")
    if requirement == "inapplicable" and bindings:
        raise ContractError(f"{path}: inapplicable dependency cannot have bindings")
    fields = {"requirement", "bindings"} if bindings else {"requirement", "bindings", "reason_code"}
    _object(value, fields, path)
    if name in {"availability_policy", "implementation_manifest", "randomness_settings"} and bindings and len(bindings) != 1:
        raise ContractError(f"{path}: requires exactly one immutable manifest or policy")
    result = {"requirement": requirement, "bindings": []}
    roles = set()
    for index, binding in enumerate(bindings):
        bp = f"{path}.bindings[{index}]"
        _object(binding, {"role", "artifact"}, bp)
        role = _pattern(binding["role"], _ID, bp + ".role")
        if role in roles:
            raise ContractError(f"{path}: duplicate role {role}")
        roles.add(role)
        result["bindings"].append({"role": role, "artifact": _reference(binding["artifact"], bp + ".artifact", immutable=True)})
    result["bindings"].sort(key=lambda item: item["role"])
    if not bindings:
        result["reason_code"] = _pattern(value["reason_code"], _ID, path + ".reason_code")
    return result


def normalize_resolved_experiment(value):
    """Validate claimed immutable bindings, not their truth or scientific readiness."""
    _object(value, {"contract_version", "experiment", "definition_bindings", "dependencies"}, "resolved")
    _choice(value["contract_version"], {CONTRACT_VERSION}, "resolved.contract_version")
    experiment = normalize_experiment(value["experiment"])
    _object(value["definition_bindings"], _SCIENTIFIC_REFS, "definition_bindings")
    definitions = {}
    for name in _SCIENTIFIC_REFS:
        ref = _reference(value["definition_bindings"][name], "definition_bindings." + name, immutable=True)
        if {key: ref[key] for key in ("id", "version")} != experiment[name]:
            raise ContractError(f"definition_bindings.{name}: differs from requested reference")
        definitions[name] = ref
    _object(value["dependencies"], _DEPENDENCIES, "dependencies")
    return {
        "contract_version": CONTRACT_VERSION,
        "experiment": experiment,
        "definition_bindings": definitions,
        "dependencies": {name: _dependency(value["dependencies"][name], name) for name in _DEPENDENCIES},
    }


def _canonical_bytes(value):
    # Validated contracts contain only ASCII strings, objects, and binding arrays.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def canonical_experiment_bytes(value):
    return _canonical_bytes({"contract_version": CONTRACT_VERSION, "experiment": normalize_experiment(value)})


def canonical_resolved_bytes(value):
    return _canonical_bytes(normalize_resolved_experiment(value))


def _identity(prefix, payload):
    return prefix + hashlib.sha256(payload).hexdigest()


def experiment_id(value):
    return _identity("exp_v0_1_sha256_", canonical_experiment_bytes(value))


def resolved_experiment_id(value):
    return _identity("resolved_v0_1_sha256_", canonical_resolved_bytes(value))


def submission_content_fingerprint(value):
    request = validate_submission(value)
    return _identity("requestcontent_v0_1_sha256_", canonical_experiment_bytes(request["experiment"]))


def load_json_strict(text):
    """Decode JSON without duplicate-key overwrite or non-JSON NaN/Infinity values.

    Follow this with the relevant validator. Parsing alone does not validate a
    contract. This function does not execute strings or inspect registered data.
    """
    def pairs_hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"JSON: duplicate object key {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ContractError(f"JSON: invalid constant {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=invalid_constant)
    except (TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"JSON: {error}") from error
