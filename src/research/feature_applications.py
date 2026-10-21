"""Explicit Feature application capabilities; no preparation or scientific approval.

Bindings are additive metadata, outside immutable Feature identities. Only the
existing two adapters execute. Provider/entity mappings require a later contract.
"""
from copy import deepcopy
import re
from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore
from data.transformations.contracts import normalize_reference, token
from data.transformations.identity import reference, digest, canonical_bytes
from research.store import inside, install_bytes

CURRENCY_QUOTE = "currency_quote_input"
PER_MEMBER = "per_instrument_input"
SINGLE_SERIES = "selected_single_series"
ENTITY_MAPPED = "entity_mapped_series"

CONTRACTS = {
    PER_MEMBER: {
        "id": "APPLICATION_PER_INSTRUMENT_INPUT", "version": "1.0.0",
        "adapter": "fx_recipe_v1", "definition_type": "feature_recipe_definition",
        "scope_modes": {"instrument": "TS", "universe": "CS"},
        "input_binding": "each_member_own_registered_price_source",
        "orientation": "preserve_recipe_and_target_quotation_no_sign_conversion",
        "comparability": "existing_fx_input_contract_and_research_rules",
        "alignment": "existing_approved_retrospective_date_match",
    },
    CURRENCY_QUOTE: {
        "id":"APPLICATION_CURRENCY_QUOTE_INPUT", "version":"1.0.0",
        "adapter":"fx_currency_recipe_v1", "definition_type":"feature_recipe_definition",
        "scope_modes":{"universe":"CS"},
        "input_binding":"each_currency_price_in_common_quote",
        "orientation":"construct_price_before_feature_and_target",
        "comparability":"currency_against_quote_reference",
        "alignment":"existing_approved_retrospective_date_match",
    },
    SINGLE_SERIES: {
        "id": "APPLICATION_SELECTED_SINGLE_SERIES", "version": "1.0.0",
        "adapter": "stored_series_ts_v1", "definition_type": "feature_definition",
        "scope_modes": {"instrument": "TS"},
        "input_binding": "one_explicit_source_series_preserve_source_entity",
        "orientation": "preserve_source_values_and_target_quotation_no_sign_conversion",
        "comparability": "single_series_ts_only_no_universe_broadcast",
        "alignment": "existing_approved_external_daily_state_policy",
    },
    ENTITY_MAPPED: {
        "id": "APPLICATION_ENTITY_MAPPED_SERIES", "version": "1.0.0",
        "adapter": None, "definition_type": None, "scope_modes": {},
        "input_binding": "requires_approved_explicit_entity_operand_mapping",
        "orientation": "unresolved", "comparability": "unresolved", "alignment": "unresolved",
    },
}


class ApplicationBlocked(ValueError):
    def __init__(self, code, message):
        self.blockers = [{"code": code, "message": message}]
        super().__init__(message)


def contract(kind):
    if kind not in CONTRACTS:
        raise ApplicationBlocked("UNKNOWN_APPLICATION", "Unknown Feature application contract")
    return {"schema_version": "1.0.0", "kind": kind, **deepcopy(CONTRACTS[kind])}


def contract_ref(value):
    return {"id": value["id"], "version": value["version"], "content_sha256": digest(value)}


def _binding_path(root, selection):
    token(selection["id"])
    if not isinstance(selection["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", selection["version"]):
        raise ApplicationBlocked("INVALID_FEATURE_VERSION", "An exact Feature version is required")
    return inside(root, f"definitions/feature_applications/bindings/{selection['id']}/{selection['version']}.json")


def load_definition(root, selection):
    """Determine storage type from a verified record, never ID-prefix semantics."""
    token(selection["id"])
    if not isinstance(selection["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", selection["version"]):
        raise ApplicationBlocked("INVALID_FEATURE_VERSION", "An exact Feature version is required")
    store = FeatureStore(root)
    paths = [store.path(f"definitions/{folder}/{selection['id']}/{selection['version']}.json")
             for folder in ("feature_recipes", "features")]
    present = [path for path in paths if path.is_file()]
    if len(present) != 1:
        raise ApplicationBlocked("AMBIGUOUS_FEATURE", "One exact registered Feature definition is required")
    value = strict_json(stable_read(present[0])); store._validate(value)
    if value["id"] != selection["id"] or value["version"] != selection["version"]:
        raise ApplicationBlocked("FEATURE_IDENTITY_CHANGED", "Feature path and identity differ")
    return value


def install_binding(root, record, kind):
    """Explicit installer only; never called by selection or execution."""
    value = contract(kind)
    if value["adapter"] is None:
        raise ApplicationBlocked("APPLICATION_NOT_IMPLEMENTED", "Entity-mapped applications require provider onboarding and an implemented adapter")
    actual = load_definition(root, {"id": record["id"], "version": record["version"]})
    if reference(actual) != reference(record) or record["record_type"] != value["definition_type"]:
        raise ApplicationBlocked("APPLICATION_INPUT_MISMATCH", "Feature definition does not match application contract")
    if kind in (PER_MEMBER,CURRENCY_QUOTE):
        from data.reusable_feature_contracts import validate_record
        validate_record(record)
        profile='fx_currency_price.1.0.0' if kind==CURRENCY_QUOTE else 'fx_price.1.0.0'
        if record['body']['input_contract']['source_profile']!=profile:
            raise ApplicationBlocked('APPLICATION_INPUT_MISMATCH','Price orientation does not match application')
    else:
        from research.external_features import definition
        definition(root, {"id": record["id"], "version": record["version"]})
    binding = {"schema_version": "1.0.0", "feature": reference(record), "contract": contract_ref(value)}
    install_bytes(inside(root, f"definitions/feature_applications/contracts/{value['id']}/{value['version']}.json"), canonical_bytes(value)+b"\n")
    install_bytes(_binding_path(root, record), canonical_bytes(binding)+b"\n")
    return binding


def binding_for(root, selection):
    try:
        binding = strict_json(stable_read(_binding_path(root, selection)))
    except FileNotFoundError as exc:
        raise ApplicationBlocked("APPLICATION_NOT_REGISTERED", "Feature application contract is not registered; onboarding must explicitly bind it") from exc
    if set(binding) != {"schema_version", "feature", "contract"} or binding["schema_version"] != "1.0.0":
        raise ApplicationBlocked("INVALID_APPLICATION_BINDING", "Invalid Feature application binding")
    normalize_reference(binding["feature"]); normalize_reference(binding["contract"])
    candidates = [contract(kind) for kind in CONTRACTS if contract_ref(contract(kind)) == binding["contract"]]
    if len(candidates) != 1:
        raise ApplicationBlocked("APPLICATION_NOT_IMPLEMENTED", "Feature application contract has no verified implementation")
    value = candidates[0]
    path = inside(root, f"definitions/feature_applications/contracts/{value['id']}/{value['version']}.json")
    if strict_json(stable_read(path)) != value:
        raise ApplicationBlocked("APPLICATION_CONTRACT_CHANGED", "Stored application contract differs from its implementation")
    definition = load_definition(root, selection)
    if definition["record_type"] != value["definition_type"]:
        raise ApplicationBlocked("APPLICATION_INPUT_MISMATCH", "Feature definition does not match application contract")
    if binding["feature"] != reference(definition):
        raise ApplicationBlocked("FEATURE_IDENTITY_CHANGED", "Feature definition differs from its application binding")
    return binding, value


def resolve(root, selection, scope):
    """Shared read-only application gate. Coverage/policy checks remain in adapters."""
    binding, value = binding_for(root, selection)
    members = scope.get("members", [])
    if scope.get("kind") == "instrument" and len(members) != 1:
        raise ApplicationBlocked("INVALID_APPLICATION_SCOPE", "Instrument Scope must contain exactly one member")
    if not members or len(members) != len(set(members)):
        raise ApplicationBlocked("INVALID_APPLICATION_SCOPE", "Scope must contain explicit, unique members")
    mode = value["scope_modes"].get(scope.get("kind"))
    if value["adapter"] is None or mode is None:
        if value["kind"]==CURRENCY_QUOTE:
            raise ApplicationBlocked("UNSUPPORTED_FEATURE_SCOPE","Currency-reference Features require one of the seven currency CS universes.")
        raise ApplicationBlocked("UNSUPPORTED_FEATURE_SCOPE", "Selected single-series Features support individual instrument TS only; universe broadcasting is unsupported")
    _basis(value,scope)
    return {"binding": deepcopy(binding), "contract": value, "mode": mode,
            "scope_kind": scope["kind"], "entity_mapping": None}


def _basis(value,scope):
    currency=scope.get('research_basis')=='currency_against_quote_reference'
    if currency:
        from data.transformations.fx_currency import members,REFERENCES
        quote=scope.get('reference_currency')
        if quote not in REFERENCES or scope.get('members')!=members(quote):
            raise ApplicationBlocked('ORIENTATION_MISMATCH','Currency Scope must freeze all currencies against its declared quote')
        normalize_reference(scope['price_catalog'])
    if (value['kind']==CURRENCY_QUOTE)!=currency:
        raise ApplicationBlocked('ORIENTATION_MISMATCH','Feature and Scope must use the same price orientation')


def validate_frozen(value, feature, scope, mode):
    """Validate frozen semantics without consulting a mutable registry."""
    expected = contract(value["contract"]["kind"])
    _basis(expected,scope)
    if (value["contract"] != expected or expected["adapter"] is None
            or value["binding"] != {"schema_version": "1.0.0", "feature": feature, "contract": contract_ref(expected)}
            or value["mode"] != mode or value["scope_kind"] != scope["kind"]
            or expected["scope_modes"].get(scope["kind"]) != mode or value["entity_mapping"] is not None):
        raise ApplicationBlocked("FROZEN_APPLICATION_CHANGED", "Frozen Feature application semantics differ")
