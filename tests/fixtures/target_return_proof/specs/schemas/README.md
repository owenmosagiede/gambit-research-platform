# Machine-readable specification records — versioned contracts

The original foundation contains two separate contracts; subsequent implemented
extensions are indexed below. Return Targets use the new 0.4 contract in
[target_store.schema.json](target_store.schema.json) and
[target_materialization.schema.json](target_materialization.schema.json), governed by
[specification 18](../18_return_targets.md). The following 0.2 entry-point table is
preserved for that historical schema only. `contracts.schema.json` and its
existing Python validators remain the frozen foundation v0.1.0 experiment contract.
`platform.schema.json` specifies proposed durable definitions and storage records.
It is not a registry, resolver, scientific engine, database, migration or readiness
certification service. See [canonical identity](../01_canonical_objects.md) and
[storage specification](../12_data_pipeline_and_storage.md).

## Entry points and ownership

Use `#/$defs/<name>` with Draft 2020-12. The document root accepts one of the 20
record types below. Every object is closed to unexpected fields. All listed fields
are required; explicit `null` means the schema allows an inapplicable/unknown value,
not permission to invent missing scientific policy.

| Entry point | Durable content |
| --- | --- |
| `dataset_definition` | Economic source entities, field types/units, event and availability columns, revision keys and exact source/availability/revision/quality policies |
| `source_view_definition` | Exact dataset reference, fixed source entities or calculation-scope entity binding, selected fields, typed filters, alignment and selection policies |
| `interaction_definition` | Semantic binary/multi-input operator contract, input arity, parameter specifications, geometry and unit/missing-data policies |
| `transformation_definition` | Semantic transformation contract with the same operator specification shape |
| `feature_definition` | The only authoritative predictor recipe, `FEATURE_<digest>`, and its `SIGNAL_<same digest>` projection; no separate editable signal definition |
| `target_definition` | Exact source views, outcome policy, horizon count/clock/calendar/endpoint policy, return basis, units, orientation, financing and realization policy |
| `scope_definition` | Instrument/universe entity membership and pinned membership, eligibility and exclusion policies |
| `policy_definition` | Policy kind, immutable semantic specification, typed parameters, approval state and compatibility evidence; no inline executable expression |
| `research_spec_definition` | TS/CS mode, prescribed P1/P2 stages and periods, method/metrics/admission/exposure policies, readiness/randomness policy and explicit single-relationship expansion |
| `snapshot_manifest` | Raw/PIT/membership coverage, cutoff, content-addressed files, input snapshots, policy and lineage bindings |
| `materialization_manifest` | Feature/target observations, source snapshots, applicable calculation Scope/membership, cutoff, implementation, policy bindings, Parquet partitions, counts and semantic row hash |
| `implementation_manifest` | Code and environment payload hashes, inert entrypoint ID and determinism policy; runtime must use allowlisted code, never execute these strings |
| `lineage_manifest` | Exact scientific inputs, semantic operation and execution/policy dependencies |
| `relationship_record` | Parent Signal and canonical Feature, Target with horizon, evaluation Scope, declared direction and TS/CS mode; no metrics |
| `trial_record` | Scientific key, original v0.1 experiment/resolved/request provenance, successful/insufficient scientific outcome, prescribed compact metrics, artifact and exposure references |
| `admission_record` | Exact P1 Trial/Relationship/policy/evidence; `admitted`, `rejected` or `unresolved` discovery admission decision and optional supersession reference |
| `validation_record` | Originating P1 Trial, optional actual P2 evaluation Trial, exact Relationship/policy/evidence and planned Research Spec/period/implementation; `validated`, `failed` or `unresolved` decision, gate-specific metrics and optional supersession reference |
| `artifact_manifest` | Trial scientific-key fingerprint and content-addressed detailed evidence files; shared feature/target observations remain references |
| `signal_library_entry` | Immutable grouping snapshot linking relationships, trial results, separately typed admission/validation results and operational attempt IDs; no metric copies or parent-wide admission flag |
| `payload_locator_record` | Non-scientific local mapping of byte hash to store ID and relative path, read-only/managed access and last verified byte count/time |

Definitions have `{schema_version, record_type, id, version, display_name, body}`.
Other scientific records have `{schema_version, record_type, id, version, ...}`.
The locator is operational and has no scientific ID. All immutable references have
exactly `{id, version, content_sha256}`. Prefixes and namespace-qualified operator
IDs are case sensitive. For example, `base.rank` and `price_technical.rank` are
distinct identities even when the short operator names overlap. An exact semantic
specification reference pins formula, parameter units and scientific behavior;
concrete code/environment versions are bound separately at materialization/execution.

Policy `approval_state` describes the immutable initial publication. A production
recipe may bind only approved, compatibility-checked published definitions. Later
revocation, eligibility and refreshed readiness evidence live outside that immutable
policy body. Do not mutate an approved policy, change a parent Signal or manufacture
a new policy version merely to refresh an operational certificate. Synthetic policies
here remain unpublished draft examples.

The initial content-addressed Feature profile fixes its registry version at `1.0.0`.
A semantic recipe change creates a new Feature/Signal ID. Republishing an equivalent
recipe with a new version is prohibited by this profile; it would create unnecessary
aliases and conflicting redundant feature references in relationship records. Existing
legacy IDs and versions are preserved in their own namespaces. The original v0.1
input validator still accepts exact semantic versions; future resolution enforces
this additional rule for newly registered content-addressed Features.

## Recipe and record identity

Recipe sources are sorted by unique `alias`; each step's parameters by unique `name`.
Step order and operand order remain meaningful. Each parameter has `name`, `unit`,
and a typed value. Scientific decimal/integer values are canonical strings; JSON
booleans remain booleans. No floating-point JSON number participates in a scientific
parameter/result. Nonnegative storage counts are JSON integers.

Use the exact identity domain and canonical encoding in [01](../01_canonical_objects.md).
The recipe includes every source-view reference, ordered optional interaction and
transformation, parameter, output node/unit and calculation-scope requirement/policy.
It excludes target, evaluated asset/scope, horizon, direction, Research Spec, period,
data snapshots, concrete code versions and display name. A source entity explicitly
selected in a source view remains part of the recipe. A broad calculation-scope
selector remains the same recipe, but its output is separately materialized for the
bound Scope/membership; it does not imply identical observations across all assets.

Definition `content_sha256` hashes the semantic envelope with `display_name` excluded.
It is distinct from the file-byte checksum. Scientific record content references
hash their canonical complete record, except snapshot projections exclude physical
`members` and materialization projections exclude physical `partitions`. Snapshots
instead bind `semantic_content_sha256` and `record_count` under their pinned
source-contract normalization; materializations bind `semantic_rows_sha256`,
`row_count` and status counts. These rules preserve scientific content across
verified re-encoding while retaining exact logical values and dependencies.
Semantic identity projections exclude their own ID fields as specified in 01.
Stored file bytes may have whitespace differences
without changing semantic content. An existing immutable catalog record is never
silently rewritten for a changed display label or operational attempt.

The initially published catalog manifest is retained unchanged, including its exact
physical member list. Additional representation wrappers and their verification
workflow are deferred; v0.2 does not authorize repacking/replacing that manifest.
Alternative layout support must verify identical logical content before recording
new physical representations. Logical-digest invariance is not permission to accept
arbitrary payload bytes or to discard the original representation.

Materialization identity hashes the scientific input key before calculation, under
the exact domain envelope in 01. Its input fields are `dataset_role`, `definition`,
`source_snapshots`, `upstream_materializations`, `calculation_scope`,
`membership_snapshot`, `information_cutoff`, `period`, `observation_schema_version`,
`implementation` and `policy_bindings`. Any applicable randomness is an explicit
policy binding. Partition bytes, output rows/counts and output lineage are excluded
from the input identity; a different output digest for the same frozen inputs is
a hard reproducibility conflict. The logical row projection excludes the redundant
`materialization_id`, sorts unique `(entity_id, observation_time)` keys and retains
values, statuses/reasons, availability/endpoints and lineage.

Trial identity hashes the full `scientific_key` under the trial domain envelope.
Its fields are `relationship`, `research_spec`, `evaluation_period`, `stage`,
`feature_materialization`, `target_materialization`, `resolved_experiment_id` and
`resolved_dependencies`. Request IDs and the attempt that first committed results
are provenance. Retry result comparison uses exactly `scientific_key`, `outcome`,
`outcome_reason`, `metrics`, `artifact_manifests`, `lineage` and `exposure_record`;
operational provenance is excluded. Identical retries retain the original immutable
record and add an attempt link. Conflicting results preserve the original and create
separate conflict evidence. No last-writer-wins behavior is permitted.

## Observation interchange contract

`#/$defs/observation_row` is a separate row shape, not a catalog record. Proposed
Parquet columns correspond to these fields:

| Column | Logical type and meaning |
| --- | --- |
| `materialization_id` | Full materialization ID, bound to the enclosing manifest |
| `entity_id` | Exact source/output economic entity identifier |
| `observation_time` | UTC microsecond timestamp; time at which the value is indexed |
| `value` | Canonical decimal string or null; engine may use numeric arrays internally, but serialized value must preserve its declared precision policy |
| `status` | `valid`, `missing` or `invalid`; never convert missing/invalid to zero |
| `reason_code` | Null for a valid value, otherwise an explicit inert reason token |
| `available_at` | Earliest permitted use under the pinned policy; must be present for valid observations |
| `target_end_time` | Null for Feature rows; realized outcome endpoint for valid Target rows |
| `lineage` | Struct of immutable `id`, `version`, `content_sha256` reference |

UTC JSON form is `YYYY-MM-DDTHH:MM:SS.ffffffZ`; Parquet timestamp columns use
`timestamp[us, tz=UTC]`. Value is proposed UTF-8 canonical decimal text; a future
optimized numeric physical encoding needs a separately versioned, lossless contract.
PIT raw/revision payload schemas remain source-specific and are pinned by dataset
and snapshot references; this compact value row is not a substitute for raw/PIT
revision history.

An empty materialization has `row_count: 0`, all three status counts zero and
`partitions: []`. Nonempty materializations have at least one partition, and every
partition contains at least one row. Partition totals and logical digests still
require the semantic checks below; accepting an empty shape does not prove readiness.

Observation uniqueness is `(materialization_id, entity_id, observation_time)`.
Target horizon is already part of the exact Target definition; no independently
editable horizon value is added to the row. A valid Target must have a real endpoint
and an availability time at/after realization under its policy. Feature availability
must precede the admissible decision cutoff. JSON Schema cannot prove these facts.

## Required semantic checks beyond JSON Schema

The following are future resolver/store acceptance requirements. The small fixture
tests illustrate selected rules; they are not their production implementation.

1. Resolve every exact reference and verify its semantic digest, required record
   kind, immutable ID/version binding, approved policy state and compatibility.
   Source-view selection must match its dataset fields/entities; parameters must
   match operator definitions with every required name/unit/type and no extras.
2. Enforce unique source aliases, graph nodes, parameter names, binding roles,
   metric-definition references, entity IDs and library result links. All recipe
   operands refer to prior sources/nodes. Interactions precede transformations;
   at least one transformation is required (an explicitly defined identity
   transformation is permitted). Input order remains meaningful.
3. Bind calculation Scope and membership before any scope-dependent operation.
   Reject a missing/incompatible binding or post-hoc filtering of an unscoped result.
   Dataset/source selection is part of the recipe; target evaluation is separate.
4. Validate increasing periods, actual UTC dates, nonoverlapping/unique observation
   keys, valid Target endpoints, availability and no-lookahead, total/partition/status
   counts, semantic row hashes and payload byte hashes. Range, unit, return-basis and
   precision rules come from approved definitions, never from fixture numbers.
5. Verify relationship Feature/Signal digest equality, Target horizon, Scope, mode
   and declared direction. Verify trial Research Spec stage/period and original
   resolved-experiment bindings. Ex-ante declaration cannot be inferred from a
   favorable historical metric or a legacy sign inferred after evaluation.
6. Check artifact/trial scientific-key equality; admission/validation Trial/Relationship
   equality; library result ownership; resolvable result digests and metric keys.
   Validation metrics represent validation-specific calculations, not independent
   editable copies of discovery metrics. A query retrieves metrics from their owner.
   Admission records own P1 trials. A validation record's `trial` is the originating
   P1 trial; `evaluation_trial` is its actual P2 trial or null if a precheck blocked
   evaluation. `research_spec`, `evaluation_period` and `implementation` preserve
   planned P2 context even when no P2 data were opened. A `validated` result requires
   a genuine P2 evaluation trial and evidence resolving the admitted originating P1
   decision, its exact policy and provenance. A P1 trial alone is insufficient. Null
   `evaluation_trial` requires
   empty metrics; a failed precheck cannot manufacture P2 observations/results.
   Actual P2 calculation metrics belong to the P2 trial, while the validation record
   owns only additional prescribed gate-derived metrics; each metric has exactly one
   authoritative owner. The
   library has separate `admission_results` and `validation_results` reference lists.
   `admitted` is never silently translated to P2 `validated`; P2 `failed` is a
   scientific validation outcome, not an execution crash.
7. P3 eligibility requires the exact relationship's applicable P2 validation,
   approved policies, compatible dependencies and current validity evidence. A
   parent Signal having another admitted horizon, or an admitted P1 gate result,
   does not make this relationship eligible.
8. Treat unresolved/crashed attempts as operational records referenced by
   `attempt_ids`. Do not fabricate scientific results. Scientific rejection is a
   completed result; insufficient data has an explicit reason. Preserve all outcomes.

Concrete production policies, formulas, return bases, sample periods, metric
definitions, thresholds and readiness rules are not populated by this schema. The
accepted approach is to retain verified legacy P1/P2 policies as versioned contracts
after compatibility checks. P3/P4 unresolved scientific choices remain blockers in
the specification index. No generic `formula`, script, SQL or executable payload is
accepted. The single-relationship Research Spec profile intentionally supplies no
implicit target/horizon grid; broader expansion needs its own reviewed revision.

## Actual schema verification

The optional test tool is `jsonschema==4.25.1`. It was installed only in
`/private/tmp/research_platform_schema_check_v02`; no global or project environment
was changed. The tests use its Draft 2020-12 validator with a standard-library UTC
calendar-date format checker (the optional third-party format extras are absent) and
also run fixture-only identity, graph and authoritative-link assertions.

From the platform root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests/specifications -v
```

To reproduce in a fresh ordinary temporary directory:

```sh
python3 -m pip install --target /private/tmp/research_platform_schema_check_v02 jsonschema==4.25.1
```

When the optional dependency is absent, the eleven full JSON Schema tests explicitly
skip; the original foundation tests and standard-library fixture assertions still
run. A skipped schema engine is not reported as a successful conformance check.
See the fixture README for the synthetic-data limits.

## Implemented bounded onboarding extension

[onboarding.schema.json](onboarding.schema.json) adds four separate 0.1.0 records for the
[ALFRED pilot](../13_provider_onboarding.md): provider_contract, ingestion_receipt,
capability_assessment and onboarding_evidence. It leaves the two original schemas unchanged.
Its live_api_daily_pull capability is narrower than full live_generation readiness.
Actual registered data and results are documented in the [onboarding report](../../docs/alfred_onboarding_report.md).

## Implemented ALFRED PIT row extension

[alfred_pit_rows.schema.json](alfred_pit_rows.schema.json) is a source-specific 0.1.0 change-event
row contract for CES0500000003. It preserves observation/vintage dates, values or explicit missingness,
exclusive successor dates and exact raw/view lineage. It deliberately has no fabricated
`available_at` timestamp. [Specification 14](../14_alfred_pit_store.md) documents runtime interval,
provenance and as-of checks. Every PIT publication pins the schema bytes as immutable evidence;
subsequent reads use that pinned schema. The existing three schemas and identity profiles are unchanged.


## Implemented transformation execution extension

[transformation_execution.schema.json](transformation_execution.schema.json) describes the
uniform 1.0 canonical input/intermediate/result envelope. Its semantic validators are in
`src/data/transformations/contracts.py`; identity utilities are in `identity.py`.
`platform.schema.json` now permits the strict operator `execution_contract` and the
explicit executable-recipe selection/history/execution-policy fields while retaining old
record validity. [Specification16](../16_transformation_execution.md) explains precision,
emitted ordering and output-coverage identities. Both suites in the root README use the
project environment with JSON Schema installed; skipped tests must not count as passes.


## Implemented stored Feature extension

[feature_store.schema.json](feature_store.schema.json) adds the bounded **0.3.0** date-preserving Feature observation, materialization, PIT operand, Signal Library and operational audit contracts. The validators in `src/data/feature_store_contracts.py` enforce semantic identities, exact coverage and lineage coordinates; `feature_store.py` resolves immutable dependencies and payloads. The existing recipe schema also permits a pinned optional `evaluation_policy`, which participates in Feature/Signal identity. Earlier identity vectors remain unchanged. [Specification 17](../17_stored_feature_trial.md) and the [real trial report](../../docs/first_signal_trial_report.md) document this implemented path; Target storage is now implemented by specification 18; research stores remain separate work.

## Executable return Target extension

[target_store.schema.json](target_store.schema.json) documents closed **0.4.0** Target
definition, versioned policy and observation records. [target_materialization.schema.json](target_materialization.schema.json)
provides the corresponding manifest contract. Semantic validation
resides in `src/data/targets/contracts.py`, scheduling in `scheduling.py`, and persistence
validation in `store.py`. [Specification 18](../18_return_targets.md) is authoritative.
The old 0.2 Target definition/materialization examples remain historical conformance
fixtures and are not automatically admitted as executable 0.4 Targets. Existing Feature
recipes, Signals and pinned schema evidence retain their original versions.
