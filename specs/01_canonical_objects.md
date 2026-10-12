# 01 — Canonical objects and identities

> Target authority update: [specification 18](18_return_targets.md) defines executable
> 0.4 return Target identities and materializations. Its explicit `target_return.1.0.0`
> profile supersedes this draft’s Target projections only. Existing experiment, Feature,
> Signal and historical 0.2 examples remain unchanged.

Status: **reviewable implementation specification, record profile 0.2.0**. The existing
experiment/request/resolved structural contract remains **0.1.0** and its executable
normalization and test vectors are unchanged. New record schemas and examples specify
future persistence; they do not implement a registry, materializer, researcher or service.

## Authority and decisions

The user's October 8 clarification is authoritative: one signal definition represents its
predictor dataset(s) and transformation recipe and may be tested against many assets and
horizons. The same signal may appear in many trials. The user also selected verified legacy
P1/P2 methods as versioned policies and P4 sleeve construction with P5 shared-capital allocation.
[Decision register](../docs/specification_decisions.md) separates these decisions from new
engineering proposals and scientific questions. The preserved [foundation](references/codex_foundation_prompt.txt)
and [P3/P4 reference](references/p3_p4_design_reference.txt) retain their source wording.

Verified legacy evidence: [feature store](../../Data/docs/derived-feature-store.md) already
separates reusable `FEATURE_*` definitions from observations and target-specific trials.
[Signal repository](../../Data/docs/signal-repository.md), by contrast, includes target,
horizon, research mode, scope and observed direction in legacy `SIGNAL_*` identity. These
legacy signals are relationship-level objects; their IDs must never be silently reinterpreted
as the new parent signal. [Reuse map](../docs/legacy_capability_map.md) records exact mappings.

## One parent predictor definition, many relationships

The authoritative predictor recipe lives once in `definitions/features/`, described by
`feature_definition` in [platform schemas](schemas/platform.schema.json). The existing
five-input submission continues to reference that definition through its `feature` field.
There is no sixth input and no separately editable signal-definition registry.

**Proposed identifier spelling:** canonical recipe digest `h` produces `FEATURE_<h>` and
`SIGNAL_<h>`, with all 64 lowercase SHA-256 hex digits. They are typed identifiers for the
same authoritative recipe, not two sources of its contents. The Signal library maps the
parent Signal ID to the pinned Feature definition. A readable display name describes the
dataset and operations; renaming a display label does not redefine the signal.

The recipe fixes:

- The exact source Dataset and Source View definitions, including source entity/slice or
  collection selection, dimension and sampling semantics. A Source View must transitively
  pin them; an unresolved dataset, mutable selection or mutable `latest` is invalid.
- Ordered optional interaction and transformation steps with exact operator definitions,
  versions, library namespaces, operand order and typed parameter values. Lookbacks and
  other calculation parameters are scientific identity. Distinct catalog namespaces cannot
  be merged merely because an operator has the same short name.
- The selected output node and economic units, calculation geometry and any intrinsic
  calculation-scope policy. Source collections belong to the recipe; evaluation membership
  is a separate bound dependency where the calculation requires it.

The recipe **does not contain** evaluated target, target instrument, target horizon,
declared Expected Direction, evaluation Scope, Research Spec, discovery/validation period,
trial result, IC, admission decision, current data snapshot, code build, run folder or timestamp.
A predictor source that is itself asset-specific remains identified as that source. Changing
that source is different from testing the unchanged predictor against another target asset.

A scope-dependent recipe can be the same parent Signal in two evaluated universes, but its
materialized values cannot be reused across those universes without an exact compatible
Scope and membership binding. For example, a cross-sectional rank must bind the universe
before ranking; a later filter does not make an unscoped result valid. These dependencies
change the materialization/trial, not the parent recipe when the recipe is unchanged.

## Canonical object hierarchy

| Object | Scientific meaning | Where authority resides |
| --- | --- | --- |
| Dataset / Source View / operator definition | Registered meaning, allowed inputs and versioned calculation rules | Versioned definition documents |
| Feature / parent Signal | One target-independent predictor recipe | One Feature definition; Signal ID is derived |
| Feature materialization | Values for that recipe under exact data, code, policy and applicable Scope bindings | Feature-store manifest and referenced observations |
| Target definition / materialization | Exact ex-post outcome including return basis and horizon; actual realized values | Target definition and separate target store |
| Experiment | Exactly Feature, Target, Scope, Expected Direction, Research Spec | Existing 0.1.0 contract |
| Relationship | Parent Signal + exact Target (already fixes horizon) + evaluation Scope + declared direction + TS/CS mode | Immutable relationship record |
| Trial | A relationship evaluated under exact Research Spec, evaluation period/stage and resolved dependencies | Immutable trial record; request and attempt provenance linked |
| Trial result | Compact prescribed metrics, counts, scientific outcome and provenance for a trial | Trial ledger |
| P1 admission decision | Exact discovery trial, admission policy, decision and evidence | Admission ledger; admitted/rejected/unresolved |
| P2 validation decision | Exact originating P1 trial, planned P2 context and actual P2 evaluation trial when one exists | Validation ledger; validated/failed/unresolved |
| Artifact bundle | Detailed trial/validation evidence plus references to shared input histories | Artifact manifest and immutable payload objects |
| Signal library entry | Parent grouping plus links to tested relationships and their authoritative result records | Rebuildable library index over durable link records |
| SignalHorizon | An exact relationship with applicable successful validation and still-valid dependency evidence | Validated projection, never a parent-wide pass flag |
| Attempt | Actual operational execution, timestamps, failures and recovery history | Runtime records; not a scientific identity |

Every tested relationship is discoverable, including rejected, failed, insufficient and
unresolved outcomes. A relationship being listed never means it passed. Metrics in the
Signal library are dereferenced from the original Trial/Validation result; no second editable
copy or independent metric recalculation exists there. Only a specifically validated,
compatible relationship can be passed to P3; validation at one horizon does not validate another.

P1 admission and P2 validation use distinct record types and library links. A validation
record retains the originating P1 `trial`, frozen P2 `research_spec`, `evaluation_period`
and `implementation`, plus `evaluation_trial` only if P2 calculation occurred. A blocked
precheck can record failed/unresolved with no P2 trial or metrics; it cannot claim validated.
Calculated P2 metrics belong to the P2 Trial; only additional prescribed gate-derived
metrics belong to the validation record. Each metric has one authoritative owner.

## Additional record identity profile 0.2.0 (specified, not implemented)

All scientific references use exact `{id, version, content_sha256}` bindings. Legacy
references remain in an explicit legacy namespace with their original IDs and fingerprints;
they are not assumed to obey new prefixes or hashing rules. Any adaptation record records
both old and new references and the mapping policy/evidence.

For record-profile 0.2.0 canonicalization:

1. Reject duplicate JSON keys, unknown fields, missing fields, non-finite numbers and type
   coercion. Identifier tokens are case-sensitive ASCII. Human display text is outside
   scientific projections; no whitespace/case rewriting is performed on scientific tokens.
2. Scientific numeric parameters use typed canonical decimal/integer strings. Decimal form
   is plain base-10 with no exponent, leading plus, leading zeros, negative zero or redundant
   fractional trailing zeros. Examples: `0`, `21`, `-0.5`, `1.25`; reject `01`, `1.0`, `1e0`.
   Boolean parameters remain JSON booleans. Parameters have explicit names and types.
3. Sources are sorted by unique alias; parameter bindings by unique name. Step order and
   operand order remain meaningful and must not be sorted. Node names/aliases are stable
   recipe keys; a different encoding requires explicit migration, not guessed equivalence.
4. Serialize the indicated identity projection with sorted object keys, compact separators,
   ASCII escaping, no trailing newline and UTF-8. Hash the exact bytes with SHA-256.
   The domain/version envelope below prevents type ambiguity.

| Identity | Canonical projection, excluding supplied identity fields |
| --- | --- |
| Recipe digest `h` | `{"identity_profile":"0.2.0","kind":"predictor_recipe","recipe":<normalized complete recipe>}` |
| Definition content digest | `{"schema_version", "record_type", "id", "version", "body"}` from the closed definition envelope; excludes display name |
| Relationship | `{"identity_profile":"0.2.0","kind":"relationship","signal_id", "target", "evaluation_scope", "expected_direction", "mode"}` |
| Trial scientific identity | `{"identity_profile":"0.2.0","kind":"trial","scientific_key":<complete schema-defined scientific_key>}` |
| Materialization identity | `{"identity_profile":"0.2.0","kind":"materialization","input_key":<scientific input fields below>}`; known before computing output |
| Physical payload identity | SHA-256 of the actual stored bytes; separate from scientific/materialization identity |

The Materialization input key contains exactly `dataset_role`, `definition`,
`source_snapshots`, `upstream_materializations`, `calculation_scope`, `membership_snapshot`,
`information_cutoff`, `period`, `observation_schema_version`, `implementation` and
`policy_bindings`. Applicable randomness is an explicitly pinned policy/settings dependency;
absence/inapplicability must be established from the approved deterministic implementation.
The physical `partitions`, output `row_count`, `status_counts`, `semantic_rows_sha256` and
output `lineage` are not input-key fields. They are output integrity checks. A different
output under the identical input key is a determinism/content conflict, not permission to
mint a different materialization ID and hide it.

A normalized observation-row digest orders rows by entity and observation time, rejects
duplicate keys, omits the redundant `materialization_id`, and includes all remaining declared
row fields (including value/status/reason, availability, lineage and target endpoint).
Exact Source View/lineage contracts define canonical PIT/vintage/raw snapshot logical content.
Snapshot `content_sha256` covers its canonical record **excluding physical `members`**;
it still binds `semantic_content_sha256`, `record_count`, definitions and all scientific
input metadata. Materialization `content_sha256` similarly excludes physical `partitions`
but binds the normalized output digest, counts and scientific fields. Definition digest
excludes only display metadata as above. Other durable record reference digests cover their
complete canonical records. Actual stored-file/blob byte checksums remain separate and
must always be verified; a semantic digest is not evidence that a particular file is intact.

This separation prevents an encoding/partition layout from entering scientific references.
Original published manifests are immutable and retained. Publishing alternative encodings
requires the separately reviewed representation wrapper/equivalence protocol in [12](12_data_pipeline_and_storage.md);
it is not implemented or authorized as a repacking task here. For raw source evidence,
byte preservation remains mandatory; a logical-content digest does not permit rewriting
provider evidence or equating different original payloads.

The Trial scientific key includes the immutable relationship and Research Spec, evaluation
period/stage, exact Feature and Target materializations, resolved dependencies and existing
resolved-experiment ID. None may be omitted from its hash. New content-addressed Feature
records use definition version `1.0.0` in this initial registry profile; a semantic recipe change
creates a new ID, not an equivalent-recipe re-version alias. Existing legacy versions remain
unchanged, and the 0.1.0 submission validator remains a structural grammar validator rather
than an implementation of this registry rule.

Relationship and Trial projections must resolve to the fields named in their schemas. Target
horizon is resolved from the pinned Target definition, never independently supplied with a
conflicting value. Trial result metrics do not enter the Trial specification identity. The trial-result record
retains its Trial scientific ID plus its own immutable content fingerprint. Retries must reconcile identical
results and report conflicting outputs, preserving failed attempts. Timestamp and request IDs
belong in provenance and do not create a different scientific test.

A policy definition’s `approval_state` is its immutable initial publication annotation,
not a mutable eligibility switch. Production use requires an approved frozen policy plus
applicable external lifecycle/readiness evidence. Later revocation is append-only evidence;
no policy or parent recipe is rewritten merely to refresh governance state.

A definition ID/version binds one immutable scientific digest. Display metadata can be shown
through a separately indexed alias without changing science; rewriting an already published
file under an existing immutable path remains forbidden. A semantic recipe change generates
new Feature/Signal IDs. A snapshot or implementation change creates a new materialization
and trial binding but leaves the recipe ID unchanged unless the scientific operator definition
itself changed. Code fixes cannot silently reuse old readiness evidence.

The existing 0.1.0 `content_sha256` input asserts an externally verified semantic binding.
Its Python helper does not compute or verify any definition, snapshot or certificate digest.
Do not mix the new 0.2.0 projection rules into existing experiment canonical bytes.

## Deterministic normalization and identity

The normative implementation is
[`src/contracts/experiment.py`](../src/contracts/experiment.py). Its normalization
profile is intentionally small and versioned:

1. Decode JSON with duplicate object keys rejected, including nested duplicates;
   reject NaN and Infinity. Use `load_json_strict`, then a relevant validator.
2. Require exact object fields and types. Reject unknown fields at every supported
   level. Never evaluate text, strip whitespace, lowercase names, coerce numbers,
   apply Unicode normalization, infer direction, or fill a missing dependency.
3. All accepted scalar values are ASCII strings. Exact lowercase hexadecimal
   digests and UUID v4 request identifiers avoid multiple accepted spellings.
4. Sort dependency binding lists by their unique case-sensitive `role`. Lists
   represent role-addressed dependency sets, not order-sensitive calculations.
   An order-sensitive sequence belongs inside its own pinned immutable manifest.
5. Serialize with sorted object keys, compact separators, no trailing newline,
   `ensure_ascii=True`, `allow_nan=False`, then UTF-8 encode. No floats participate.
6. Hash these bytes with SHA-256 and retain the full hex digest with a type prefix.

| Identity | Canonical hash content | Prefix / ownership |
| --- | --- | --- |
| Experiment | `{"contract_version":"0.1.0","experiment":<normalized five inputs>}` | `exp_v0_1_sha256_` |
| Request content fingerprint | Same canonical scientific envelope; excludes request ID | `requestcontent_v0_1_sha256_` |
| Resolved experiment | Entire normalized resolved envelope | `resolved_v0_1_sha256_` |
| Request ID | Caller-provided canonical lowercase UUID v4; not a scientific hash | Operational idempotency key |
| Attempt ID | Fresh identifier per actual attempt; proposed UUID v4 | Deferred operational store |

The request fingerprint deliberately shares the experiment's digest payload but
has its own type prefix. Any change to this normalization or hashed payload
requires an explicit contract revision and preserved historical rules.

| Change | Experiment identity | Resolved identity | Operational identities |
| --- | --- | --- | --- |
| Any of five inputs changes | Changes | Changes | New request content; new attempt if ever executed |
| Data snapshot or availability policy changes | Same | Changes | New attempt if executed |
| Code/environment manifest or applicable randomness changes | Same | Changes | New attempt if executed |
| Definition version changes | Changes | Changes | New request content |
| Conflicting definition bytes under same ID/version | Same input reference | Hash would differ structurally, but resolution must reject conflict | Blocked, never accepted as a valid mutation |
| Membership/eligibility or required readiness dependency changes | Same if five inputs unchanged | Changes | New attempt when executed |
| Folder/locator moves; logs or certificate issuance timestamp changes | Same | Same | Operational metadata may change |
| Retry same request ID and content | Same | Reuse original accepted binding; do not silently refresh snapshots | Return existing submission |
| New execution attempt of the same frozen resolved experiment | Same | Same | New attempt ID |

A readiness evidence digest must cover its immutable dependency state, validation
policy, checks, valid information interval, and substantive evidence. Issuance
clock time, signature envelope, log location, and storage path belong outside
that semantic digest. A changed semantic validity interval or policy changes the
binding. The evidence format and invalidation rules remain future specification
work; this task creates no real certificate.


## Link integrity and acceptance criteria

- The same recipe tested on two assets and two target horizons yields one parent Signal and
  distinct Relationship/Trial identities. All results remain queryable below that parent.
- Changing a lookback, source selection, interaction operand order or operator definition
  changes parent identity. Moving a file, receiving new observations or retrying does not.
- Scope-dependent materializations cannot reuse incompatible Scope/membership bindings.
- A library metric reference identifies one immutable result and a specific metric key;
  a missing/different digest returns an explicit unresolved integrity error, never zero.
- Legacy result-derived direction is not evidence of ex-ante declaration. Historical results
  can remain accessible even when new-contract eligibility is blocked.
- Trials from different methods, periods, snapshots or validation stages coexist without
  overwriting each other; the UI cannot silently choose the most favorable result.
- Scientific rejection is distinct from an operational crash. P3 input validity is checked
  per relationship and validation dependency state, not once per parent Signal.

Schemas enforce shape; hashing, referential integrity, temporal validity, immutable storage,
legacy parity and scientific eligibility require the future conformance checks in [12](12_data_pipeline_and_storage.md).
No new record identity engine or persistence service is implemented by this specification task.


## Implemented transformation foundation update

[Specification16](16_transformation_execution.md) now implements the scoped single-series
operators, canonical execution envelopes, recipe identities and fixture-only computation.
Existing0.2 definition/Feature/Signal conventions are reused. Date-aware transient results
have an explicitly tagged execution identity profile; they are not published production
materialization manifests. Definition registrations remain separate from observation stores.
No Feature observations or Signal registrations were produced by this foundation task.
