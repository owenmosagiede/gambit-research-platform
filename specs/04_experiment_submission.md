# 04 — Canonical experiment submission — preserved v0.1.0

Status: review draft integrated with the record-profile 0.2.0 specifications. The three
existing 0.1.0 machine-readable shapes, Python validators and identity vectors are unchanged. No request is stored, resolved, queued, running,
scientifically approved, or ready merely because these functions return.

Source requirements: [foundation prompt](references/codex_foundation_prompt.txt).
Verified legacy evidence and common normalization are recorded in
[01_canonical_objects.md](01_canonical_objects.md). All new field names and
engineering format choices below are proposals, not ratified scientific policy.

## Integration with the parent Signal and new stores

The October 8 user clarification adds a target-independent parent Signal to the registered
Feature recipe; it does not change this five-input wire contract. The `feature` reference
resolves one authoritative Feature definition and its derived parent Signal ID under
[01](01_canonical_objects.md). A target asset/horizon change creates another tested
relationship/trial beneath the same parent recipe. Do not add a separate Signal input.

The source definitions, observations, ledger/artifact records and Signal-library link shapes
are specified in [platform.schema.json](schemas/platform.schema.json); their exact locations
are in [12](12_data_pipeline_and_storage.md). Their **0.2.0 record profile is distinct from
this 0.1.0 experiment wire version**. The record schemas do not silently revise existing
experiment hashes, require data migration or cause a submission to execute.

The user selected reuse of verified legacy P1/P2 methods as pinned policies. A selected
Research Spec must bind the exact compatible retained implementation and record any unclosed
parity/period-exposure/direction-provenance issue as a blocker. An old result-derived direction
must not be converted to the request's ex-ante direction. Legacy metadata can remain visible
without satisfying this new submission contract.

A single request identifies one exact target and one exact scope. Testing a parent Signal
against multiple targets/horizons can be represented by separate requests. Any future batch
or expansion mode requires an explicitly registered deterministic expansion contract; neither
this schema nor the retained transformation parameter grids authorize an implicit search.

## Exactly five scientific inputs

| Field | Accepted input | Meaning the future resolver must verify |
| --- | --- | --- |
| `feature` | Exact `{id, version}` reference | Registered predictor with permitted information set and declared transformation dependencies |
| `target` | Exact `{id, version}` reference | Exact outcome with unambiguous return basis, output units, and horizon convention |
| `scope` | Exact `{id, version}` reference | Instrument or universe with applicable membership, eligibility and exclusion rules |
| `expected_direction` | `POSITIVE` or `NEGATIVE` | Ex ante sign, frozen before results are inspected |
| `research_spec` | Exact `{id, version}` reference | Prescribed TS/CS mode, periods, tests, and pinned admission policy |

Four references plus one direction constitute five inputs. No unversioned names,
mutable `latest`, inline formulas, scripts, arbitrary executable text, guessed
signs, missing defaults, or unknown fields are accepted. There is no freeform
executable payload. IDs are inert tokens, never evaluated or imported.

The Target defines the outcome rather than taking a separate UI horizon field.
The Research Spec defines methodology rather than taking a separate UI TS/CS,
period, test or admission field. Its prescribed admission policy may be a pinned
separate definition, preserving the useful legacy separation of method and gate.
This task does not populate that definition or choose thresholds.

These five inputs do not contain capital, positions, costs, financing, mandate,
venue context, or trading authorization. Those belong to downstream portfolio and
execution contracts, not hidden Research Spec settings.

## Machine-readable structures and Python interface

[`schemas/contracts.schema.json`](schemas/contracts.schema.json) is a self-contained
JSON Schema Draft 2020-12 document. Its three entry points are:

- `#/$defs/experiment_definition`: exactly the five scientific fields.
- `#/$defs/submission_request`: `contract_version`, `request_id`, `experiment`.
- `#/$defs/resolved_experiment`: `contract_version`, `experiment`,
  `definition_bindings`, `dependencies`.

The document root accepts exactly one of these forms. Every object is closed to
unknown fields. References have `id`, `version`; immutable references additionally
have `content_sha256`. The pure Python validator also enforces two cross-field
invariants not expressible here in portable standard JSON Schema: unique roles
within each dependency list, and equality between each definition binding's
ID/version and the corresponding experiment reference.

The public functions in `src/contracts/` are:

- `load_json_strict(text)` — reject duplicate-key overwrites and non-JSON constants.
- `normalize_experiment(value)`, `validate_submission(value)`,
  `normalize_resolved_experiment(value)` — validate and return detached structures.
- `canonical_experiment_bytes(value)`, `canonical_resolved_bytes(value)` — frozen
  canonical bytes for the validated forms.
- `experiment_id(value)`, `resolved_experiment_id(value)`,
  `submission_content_fingerprint(value)` — deterministic identity functions.

They raise `ContractError` for malformed inputs. They have no side effects,
filesystem access, registry lookup, readiness test, environment inspection, or
scientific calculations. For data coming from JSON, callers must use the strict
parser before validation; a decoder that already discarded duplicate keys cannot
recover those duplicates afterward.

## Submission request and future idempotency

A synthetic shape is:

```json
{
  "contract_version": "0.1.0",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "experiment": {
    "feature": {"id": "SYNTHETIC_FEATURE", "version": "1.0.0"},
    "target": {"id": "SYNTHETIC_TARGET", "version": "1.0.0"},
    "scope": {"id": "SYNTHETIC_SCOPE", "version": "1.0.0"},
    "expected_direction": "POSITIVE",
    "research_spec": {"id": "SYNTHETIC_RESEARCH_SPEC", "version": "1.0.0"}
  }
}
```

The UUID is operational metadata; the five-input definition has no sixth scientific
field. A future persistent service must atomically bind request ID to normalized
request content and a stable submission record within its explicit idempotency
namespace. The same ID and content return the existing submission. The same ID
with different content is an error. JSON formatting or object key order do not
change content. An initial unresolved/blocked record is still returned on retry;
a retry must not silently create a new submission or rebind its frozen snapshots.

This task implements only the content fingerprint needed for that comparison.
It does not implement a request store, transaction, response schema, API, user
namespace, authentication, executor, or concurrency guarantees. A different request
ID can express the same experiment identity; whether to reuse already valid work
requires explicit readiness and reuse policy, not an assumed new scientific trial.

## Resolution and dependency binding

The future resolver must reject an unknown or conflicting registered reference,
verify its immutable scientific content, and pin exactly the four requested
registered definitions. `definition_bindings` contains `feature`, `target`, `scope`,
and `research_spec`, each with the same ID/version and a verified content digest.
A digest-shaped string in a fixture is not that verification.

`dependencies` contains these explicit envelopes:

| Dependency | Permitted requirement | Meaning of bound artifact(s) |
| --- | --- | --- |
| `data_snapshots` | required | Exact immutable snapshot manifests covering selected observations, source/vintage lineage, availability and release metadata; at least one |
| `availability_policy` | required | Exactly one immutable policy covering the permitted information set and cutoff rules |
| `implementation_manifest` | required | Exactly one immutable manifest pinning every relevant implementation version/content and reproducible environment/dependency version; no mutable code checkout or machine path |
| `scope_membership_and_eligibility` | required or inapplicable | Exact applicable membership history, exclusion/eligibility evidence and mappings; applicability determined from the pinned Scope and method |
| `readiness_evidence` | required, optional or inapplicable | Relevant immutable evidence bound to exact dependencies and validation policy; historical reproduction and live generation distinguished |
| `randomness_settings` | required or inapplicable | Exactly one immutable settings manifest when stochastic behavior applies, including algorithm, seed/stream assignments and relevant library/runtime behavior |

An envelope is either:

```json
{
  "requirement": "required",
  "bindings": [
    {
      "role": "observations",
      "artifact": {
        "id": "SYNTHETIC_SNAPSHOT",
        "version": "1.0.0",
        "content_sha256": "1111111111111111111111111111111111111111111111111111111111111111"
      }
    }
  ]
}
```

or an explicit absence permitted by policy, for example:

```json
{
  "requirement": "inapplicable",
  "bindings": [],
  "reason_code": "SYNTHETIC_DETERMINISTIC_CALCULATION"
}
```

`required` always has nonempty bindings. `optional` can have bindings, or an empty
list with a reason code. `inapplicable` always has an empty list and reason code.
Absent keys, nulls, fake versions, and empty required bindings are errors.
A nonempty envelope has only `requirement` and `bindings`; no omission reason.
Each binding has an exact unique role within its dependency group.

The future resolver, not the user-facing form, derives these requirement choices
from the pinned definitions and policy. A caller cannot bypass needed certification
by labeling it optional or inapplicable. The structural validator intentionally
cannot certify that such a choice is true. Inapplicable randomness does not mean a
fabricated seed of zero. A missing required certificate or unknown snapshot means
unresolved/blocked and no valid resolved scientific object. Unresolved candidates
and reasons belong in the operational resolution record, whose storage is deferred.

Certificates must have substantive dependency/policy bindings and invalidation
rules; they are not permanent permission to trust a changing dataset. Live data
requires appropriate new batch checks. Historical reproducibility evidence alone
must never claim live-generation readiness. A structurally valid resolved fixture
therefore proves neither historical nor live readiness.

Data locator changes are excluded from all identities. Snapshot and implementation
manifests are external immutable dependencies, stored once and referenced. All
transitive scientific dependencies must be pinned inside those manifests or the
registered definitions; an arbitrary current path is not an adequate replacement.
Manifest body shapes are specified in the new platform schema; actual snapshot hashing, certificate issuance and referential verification remain unimplemented. See specifications 02 and 12 for their review-draft requirements.

Scope must be resolved and bound before any calculation whose meaning depends on
it, including cross-sectional transformations and sample construction. Filtering
results after an unscoped transformation does not satisfy this contract. Provider
provenance stays in lineage; after normalization scientific calculations must not
branch on provider name.

## Trials, attempts, outcomes and truthful status

If a pinned Research Spec permits a request to expand into several trials, a future
expansion contract must specify a deterministic enumeration, explicit stable trial
identities, canonical ordering and duplicate policy, and preserve the mapping back
to the resolved experiment. It must bind each trial's exact Scope, Target and any
explicitly prescribed choices. No grid, default horizon, expansion engine, or
multiple-testing policy is invented or executed in this foundation.

An execution attempt is a separate operational object with a fresh identity and
actual timestamps, referencing the resolved identity. Failed attempts remain
historical evidence. Retrying the same resolved calculation does not create a new
scientific definition. Recovery must replace affected work and reconcile dependent
successors without discarding unrelated valid work.

Execution state and scientific result are distinct. A completed test can reject its
hypothesis successfully; a crash is an execution failure; missing readiness evidence
is a blocker. Retained P1/P2 decision vocabulary and policy mappings are specified in 05/06; operational transitions are proposed in 10. Their services and enforcement are not implemented. Recording a request must never report `running` when no
executor exists. The present library returns validated data or `ContractError`, not
submission/progress/readiness status.

## Synthetic fixtures and actual verification boundary

`tests/fixtures/README.md` marks all fixture identities and digests as synthetic.
No fixture registers a production definition, supplies scientific calculations,
represents an actual snapshot, or asserts a successful validation certificate.

Run from the platform root with an available Python 3 interpreter:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Tests cover required/unexpected fields, invalid direction, exact pinned versions,
strict JSON parsing, deterministic byte/hash vectors, normalization, operational
request IDs, dependency changes, explicit applicability, cross-field binding
consistency, locator exclusion, and self-contained closed JSON Schema structure.
They do not prove registry integrity, scientific correctness, readiness, persistent
idempotency, actual attempts, or recovery. No JSON Schema engine is bundled; the
schema inspection test parses JSON, checks local references/closed object shapes,
and compiles regex patterns, but is not full Draft 2020-12 conformance validation.
The small pure Python validator is the executable check run in this foundation.

## Implementation gates

Definition, manifest, library and ledger record schemas and their storage locations are now
specified in the companion review draft. Runtime persistence, idempotency namespace and
truthful state requirements are in [10](10_runtime_recovery_storage.md); the minimum initial
page/service behavior is in [11](11_ui_and_observability.md). Their implementation and
verification remain future work. No schema-only check proves registration or readiness.

Select exact retained policies and reconcile historical period exposure before real P1/P2
execution. P4/P5 top-level ownership is settled (P4 sleeves; P5 shared capital); the detailed
capital/feasibility protocol and remaining P3/P4 mathematics remain gated as recorded in the
[decision register](../docs/specification_decisions.md). They need not be invented to build
truthful submission intake. Existing 0.1.0 contract tests must continue to pass unchanged.
