# 12 — Data pipeline and storage implementation specification

> Implementation update: [17](17_stored_feature_trial.md) governs stored Feature/Signal
> records; [18](18_return_targets.md) governs executable return Target records. For Targets,
> the reserved definition/catalog/shared-payload paths below are retained; current 0.4
> date-preserving JSONL and output-bound materialization identity supersede this draft’s
> generic Parquet/UTC-only/request-only Target proposals. The old 0.2 schema is preserved.

Status: **review draft v0.2.0; no stores, adapters, engines or migration implemented**. The user's current instructions establish the flow and reusable signal identity. This document proposes the precise storage and data contracts needed to implement it. The formal record shapes are in [platform.schema.json](schemas/platform.schema.json); [01](01_canonical_objects.md) owns identity and [10](10_runtime_recovery_storage.md) owns publication/recovery. The [legacy capability map](../docs/legacy_capability_map.md) separates inspected evidence from reuse proposals.

## Pipeline and object ownership

```text
immutable raw evidence → PIT observations + explicit source views
                                    ↓
                       optional ordered interactions
                                    ↓
                         ordered transformations
                                    ↓
                     Feature definition/materialization
                                    ↓
                         Feature Store observations

PIT outcome-source observations → registered ex-post outcome recipe → Target Store

Feature + Target + Scope + Expected Direction + Research Spec
   → individual trials → Trial Ledger + Trial Artifact Store
   → P1 admission records → P2 validation records → Signal Library links under the same predictor SIGNAL_id
```

The top line is the user's raw → PIT → optional interactions → transformations → feature/target-store flow. The target branch is separately typed: a future outcome is allowed only in the Target Store and evaluation input. It never becomes an input to a predictor recipe. A predictor and a target may share immutable price-source bytes while differing in information permissions and definition.

| Layer | Authoritative content | Boundary and proposed behavior |
| --- | --- | --- |
| Raw | Retrieved bytes and ingestion/source provenance | Preserve exact bytes, request and source identity, retrieval time, checksums and parser version. Existing raw stores remain read only. |
| PIT/source views | Dataset contract, observation/vintage history, availability policy, deterministic selection/mapping | Select only information defensibly available at each historical cutoff. A final revised snapshot is not a historical feature history. Source views specify series slice, units, frequency, alignment and entity mappings. |
| Interactions | Versioned multi-input operation with ordered operands, alignment and units | Optional recipe prefix. Missing operand, incompatible units, alignment ambiguity or unavailable observations fails explicitly. No implicit lag, imputation or cross-asset ranking. |
| Transformations | Versioned deterministic operators and parameter policies | Apply the pinned ordered recipe after the interaction phase, independently per series unless a scope-aware operator expressly says otherwise. Do not silently expand a parameter grid or choose a window. |
| Feature | One authoritative recipe over explicitly pinned source views/series slices; independently identified materializations | The canonical recipe lives only under definitions/features. Parent `SIGNAL_<hash>` and `FEATURE_<samehash>` name that same mechanical definition. |
| Target | One exact outcome recipe, source binding, units, orientation and horizon convention | Target availability follows its observed endpoint and definition. Changes in horizon or payoff yield a different Target; neither changes the parent predictor SIGNAL_id. |
| Trial/admission/validation | Compact authoritative trial results, separate P1 admission decisions and P2 validation evidence, metric-definition references, method/period/scope/direction and input lineage | P1 decisions are admitted/rejected/unresolved; P2 decisions are validated/failed/unresolved. Detailed evidence belongs in artifacts. A storage error is not a scientific result. |
| Signal library | Links grouping relationship/trial/admission/validation records by immutable Feature and derived SIGNAL_id | Index every attempted/tested relationship for that predictor. No editable metric or separate recipe copy. Eligibility for P3 attaches to a specific validated relationship, never the parent alone. |

An implementation/code-environment manifest is an execution dependency, not parent predictor identity. A code correction under unchanged approved mathematical semantics changes the bound materialization/trial execution identity; a changed formula, policy, source view or operator semantics requires a new definition/version and therefore a new parent recipe identity.

Source-view aliases and recipe step order are semantic. A named operator is insufficient without namespace, version, definition hash, parameters and information-set policy. Raw dataset names alone cannot identify a signal when series slices, source views, interaction operands or ordered transforms differ. Dataset snapshots, evaluation scope, tested asset/target, horizon, expected direction, Research Spec and period belong to materialization or relationship/trial identities rather than the parent recipe, except that an explicitly fixed predictor source slice remains part of the recipe.

A scope-dependent recipe (for example a declared cross-sectional operator) is reusable as a rule, but its values are not portable between scopes. Resolve and hash the actual calculation scope and membership snapshot **before** computing values. If the recipe binds a fixed universe itself, that fixed policy is recipe content. Do not compute a universe-neutral cache and relabel it afterward.

## Exact proposed locations

Let `PLATFORM_ROOT` be the application directory, currently `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`. All paths below are relative to it. They are templates for future runtime outputs, not folders populated in this specification task. Existing legacy mappings stay in ignored `config/storage.local.json`. A portable machine-readable proposal is [storage_layout.example.json](../config/storage_layout.example.json).

| Content | Exact location template | Authority/schema entry |
| --- | --- | --- |
| Dataset definitions | `definitions/datasets/<id>/<version>.json` | `dataset_definition` |
| Source views and series slices | `definitions/source_views/<id>/<version>.json` | `source_view_definition` |
| Optional interaction operators | `definitions/interactions/<id>/<version>.json` | `interaction_definition` |
| Transformation operators | `definitions/transformations/<id>/<version>.json` | `transformation_definition` |
| Feature recipes / signal definitions | `definitions/features/<FEATURE_id>/<version>.json` | `feature_definition`; no second definitions/signals store |
| Target recipes | `definitions/targets/<id>/<version>.json` | `target_definition` |
| Scopes, Research Specs and policies | `definitions/scopes/<id>/<version>.json`, `definitions/research_specs/<id>/<version>.json`, `definitions/policies/<id>/<version>.json` | `scope_definition`, `research_spec_definition`, `policy_definition` |
| Immutable data snapshot manifests | `storage/catalog/snapshots/<snapshot_id>/manifest.json` | `snapshot_manifest` |
| Code/environment manifests | `storage/catalog/implementations/<id>/manifest.json` | `implementation_manifest` |
| Compact lineage manifests | `storage/catalog/lineage/<id>/manifest.json` | `lineage_manifest` |
| Feature materialization manifests | `storage/catalog/feature_store/<materialization_id>/manifest.json` | `materialization_manifest` with feature role |
| Target materialization manifests | `storage/catalog/target_store/<materialization_id>/manifest.json` | `materialization_manifest` with target role |
| Compact Trial Ledger | `storage/catalog/trial_ledger/records/<trial_id>.json` | `trial_record` |
| P1 Admission Ledger | `storage/catalog/admission_ledger/records/<admission_id>.json` | `admission_record`; P1 admitted/rejected/unresolved decisions only |
| Validation Ledger | `storage/catalog/validation_ledger/records/<validation_id>.json` | `validation_record`; P2 validated/failed/unresolved decisions only |
| Detailed trial/validation evidence manifests | `storage/catalog/trial_artifacts/<artifact_id>/manifest.json` | `artifact_manifest`; evidence role distinguishes the stage |
| Individually tested relationship definitions | `storage/catalog/signal_library/relationships/<relationship_id>.json` | `relationship_record` |
| Signal grouping snapshots | `storage/catalog/signal_library/entries/<SIGNAL_id>/<entry_sha256>.json` | `signal_library_entry`; immutable link-only derived projection |
| Observation/evidence bytes | `storage/payloads/sha256/<first-two-hex>/<full-sha256>.<format>` | Byte-addressed blob; observation contents obey `observation_row` |
| Additional physical representations (future) | `storage/catalog/representations/<semantic_id>/<representation_sha256>.json` | Physical wrapper/schema deferred; initial canonical manifests remain immutable and repacking is gated |
| Catalog query indexes | `storage/catalog/<catalog-name>/index.sqlite` | Rebuildable lookup/projection; never independent scientific authority |
| Blob locator records | `storage/catalog/locators/<blob_sha256>/<store_id>/<locator_path_sha256>.json` | `payload_locator_record`; hash of relative path disambiguates placements without changing scientific identity |
| Readiness certificates | `storage/catalog/readiness/records/<certificate_id>.json` | Required fields and semantics in [02](02_data_and_readiness.md); structural schema remains a later implementation task |
| Exposure, corrections and revocations | `storage/catalog/research_exposure/records/<event_id>.json`, `storage/catalog/corrections/records/<event_id>.json` | Append-only evidence, never overwritten original results; schema implementation deferred |

Use full digest identities prescribed by [01](01_canonical_objects.md). Path-segment identifiers must pass the declared ASCII grammar, reject separators and traversal, and resolve inside their registered root. Absolute machine paths must not enter scientific hashes. A locator may move without changing a scientific object; observed bytes/hash must remain the same. Definitions are JSON suitable for version control; payloads, catalogs and machine-specific mappings stay outside version control under existing ignore rules.

## Record and observation schemas

The v0.2.0 schema defines separate typed records, not one permissive catch-all. Every definition pins immutable `{id, version, content_sha256}` dependencies. Descriptive names may explain a recipe; only the identity-bearing projection in [01](01_canonical_objects.md) defines it. Null or an unresolved reference is not a substitute for a required scientific definition. JSON Schema proves structural shape only; cross-object checks below are mandatory before use.

| Object | Required semantic contents beyond envelope | Cross-object checks |
| --- | --- | --- |
| Snapshot | Layer (raw/PIT/membership), immutable definition reference resolving dataset/source view or membership, half-open period/cutoff, members with role/format/bytehash/count, normalized semantic content digest and record count, upstream snapshots, policies, implementation when applicable and lineage | Verify bytes, availability/vintage policy, schema, source/ingestion evidence and snapshot closure. External legacy bytes are referenceable in place only after verification. |
| Materialization | Feature/target definition, input snapshot/materialization refs, actual calculation scope/membership where required, period/cutoff, implementation/policy/lineage refs, observation schema version, counts, partitions and semantic row digest; complete publication is signaled by the installed manifest | Resolve every dependency. Partition rows are unique, correctly sorted, finite or explicitly failed, within requested bounds; counts/min/max keys/hash match. Scope-aware values bind scope before compute. No completed manifest points to partial blobs. |
| Trial | Scientific key: relationship, Research Spec, evaluation period/stage, exact feature and target materializations and resolved dependencies; metric-definition refs plus values/status/counts; provenance and artifact refs | Resolve the same Feature used by the parent SIGNAL_id and relationship; exact target horizon and scope; explicit direction; enforce permitted sample and stage. Duplicate completed scientific key with conflicting content blocks. |
| Admission | Exact P1 trial, relationship, admission policy, evidence and decision/reasons | P1 admitted/rejected/unresolved is separate from P2 validation. Admission never implies eligibility for P3. |
| Validation | Exact originating/evaluation trial/evidence, relationship and P2 validation policy, decision and reasons | P2 validated/failed/unresolved only. No validation of a different recipe, target, direction or scope under the same relationship. Preserve validation period and exposure. |
| Artifact | Owner trial scientific-key digest (`scientific_key_sha256`, not the completed result digest), detailed-evidence roles, blob refs, counts and checksums; exact inputs and computation provenance for replay | Link shared Feature/Target/membership blobs instead of copying histories. Artifact ownership binds the precomputed trial scientific-key digest; the completed result then references the artifact manifest hash, avoiding a content-reference cycle. Validation evidence binds its exact originating/evaluation trial and is referenced by the validation record. Unique IC-by-time, exclusions or other evidence may have distinct payloads. Compression alone cannot justify deleting evidence. |
| Relationship | Parent SIGNAL_id/Feature, Target with exact horizon, evaluation Scope, explicit direction, research mode | Parent identity stays fixed across tested assets and horizons; each relationship retains its own identity. Research Spec, stage and evaluation period distinguish its individual trials. |
| Signal grouping | Exact Feature and SIGNAL_id plus relationship/trial/admission/validation links and explicit operational attempt IDs | No `metrics`, editable status, score override or copied IC column. Read performance by resolving authoritative results. Attempt links preserve crashes/unresolved work without fabricating a scientific result. Missing reference is unresolved, never silently omitted. |

Canonical **new** feature/target observation blobs are proposed as Parquet. The logical row follows `observation_row`: materialization ID, entity ID, observation time, value, status/reason, availability time, lineage reference and target endpoint time. The exact horizon and unit come from the immutable definition/manifest rather than drifting per row. The unique row key is `(materialization_id, entity_id, observation_time)`; a recipe that produces several outputs must use separate typed materializations. Emit stable entity/time ordering. Parquet uses UTF-8 for IDs and canonical scientific decimal strings, `timestamp[us, tz=UTC]` for timestamps, and a struct for each immutable lineage reference; counts use integer columns and explicit nullability. JSON timestamp interchange uses exact `YYYY-MM-DDTHH:MM:SS.ffffffZ` strings. This retains the schema's exact decimal serialization without silently introducing a floating-point storage convention. Decimal precision/rounding for scientific calculations must be pinned by the chosen implementation policy; serialization does not choose a new estimator.

For valid features, value and availability must exist, target endpoint is null, and every source contribution is available at or before the feature's allowed cutoff. For targets, observation time is the anchor, endpoint and target-availability ordering are checked against the outcome definition, and availability after anchor is expected. Missing/invalid values are null with explicit reasons, not NaN, zero or an invented metric. Target label maturity is checked again before an estimator consumes it. A read API returns exact typed rows plus a manifest reference; it never forward-fills or normalizes secretly.

PIT archives retain richer vintage/release metadata than feature rows. That information remains in immutable source/lineage snapshots, with compact exact references from output rows. A lineage reference must resolve the complete selected source set or a verified compact equivalent; a single maximum timestamp alone is insufficient evidence.

Proposed observation partition policy: entity plus UTC observation calendar year, retaining only nonempty partitions. The schema-safe partition key is `P_<full_sha256>` over canonical `{entity_id, utc_observation_year}`; physical path location remains the blob hash, not this logical key. Manifests enumerate exact logical partition keys and blob checksums; payload paths remain content addressed. The semantic immutable-reference projection for a snapshot excludes its physical `members` list and includes `semantic_content_sha256` plus `record_count` and all other identity-bearing manifest fields. The materialization projection excludes its physical `partitions` list and includes `semantic_rows_sha256`, logical counts, inputs, scope/membership, information cutoff, policies and implementation. Exact projections and row-hash rules are owned by [01](01_canonical_objects.md). Byte hashes remain mandatory integrity checks for the selected physical encoding; they are not substituted for the semantic digest. For raw snapshots the semantic content digest must preserve exact raw evidence bytes and their source roles, so changing raw content is never a representation-only operation.

A materialization ID is computed from the scientific request inputs before computation: definition, source/upstream refs, actual calculation scope/membership, period/cutoff, implementation/environment, policies and any prescribed randomness. The normalized semantic-row digest verifies the output and does not determine that request ID; its projection omits the redundant materialization ID. Different output under the exact same inputs is a determinism/content conflict, not permission to issue a new materialization ID that conceals the difference.

The initial canonical manifest at the location above is immutable, including its chosen physical representation. A later physical repartition/re-encoding must preserve the semantic digest and retain the original. Additional representations require a separate immutable physical wrapper under the proposed `storage/catalog/representations/<semantic_id>/<representation_sha256>.json`, binding the semantic reference, exact representation/manifest byte hash and blob list. That wrapper schema, publication/read selection and bounded equivalence tests remain a separate implementation task; repacking is disabled until they exist. No runtime folder or wrapper is created now. Consequently a future representation change does not authorize rewriting a canonical manifest or silently changing a trial scientific key. This partition choice is an engineering proposal to review against a bounded sample, not a performance claim. Legacy JSONL/gzip/Parquet layouts continue to be read through version-specific adapters in place.

## Indexed research memory and signal query contract

The requested query `SIGNAL_X` resolves its Feature recipe, lists **all** relationship IDs, and then their trials, P1 admission records, P2 validation records and operational attempt links. A crash before result publication remains an attempted relationship with no metrics; it is not a fake scientific Trial Result. A completed empirical rejection remains a completed result with its explicit decision evidence. Users may filter target, target horizon, asset/scope, expected direction, Research Spec, stage, evaluation period or result status. No default query may discard rejected, failed or unresolved outcomes. Never aggregate different directions, scopes, versions, periods or methods into one unqualified IC. Comparisons expose the metric definition, value, units/status, sample count and evidence reference together.

Indexes cover exact IDs and the filter fields above, plus created/persisted times for operational lookup. Index creation/update stores the authoritative record hash and source path. Query results verify record references; an index cannot change a scientific record. Rebuild the full library grouping from relationship, trial, admission and validation records; materialized entry snapshots are disposable projections only if all those authoritative inputs remain reachable. The recipes themselves are never reconstructed from display names or inferred from results.

## Legacy compatibility and reuse contract

The current user selected retaining verified legacy P1/P2 methods as versioned policies after compatibility checks. Retain source methodologies and scientific evidence; adapt namespaces, versioned references and adapters; replace target-dependent legacy parent Signal identity with the specified predictor parent + relationship/trial structure. Preserve every legacy ID as `namespace + legacy_id + legacy_version + fingerprint` in crosswalk/lineage metadata. New IDs must never masquerade as a reissued old ID. One legacy signal may map to a parent plus a specific relationship; multiple legacy signals may map to the same parent only if their full mechanical recipes match exactly.

Compatibility review must establish: exact operator/recipe semantics, source view, series slice, operand ordering, parameter grids and extensions, units and orientation, causal cutoff behavior, target convention, scope/membership, prescribed direction, Research Spec, evaluation window/exposure and implementation/environment. Unknowns block reuse of that item without deleting it. In particular legacy direction inferred from a statistic is not the new hypothesis-expected direction; find its explicit frozen source or retain only namespaced historical evidence with an unresolved mapping. Without a prescribed ex-ante direction, no canonical relationship satisfying the required-direction contract can be constructed. A legacy `validated` label does not certify current validity. Reading an old validation sample does not make it untouched again.

No adapters, catalog imports, payload copies, recomputation, compaction, archive transfer or deletions occur in this task. Later implementation should first add a read-only bounded adapter and compare exact values/lineage; broad migration is unnecessary for launch.

## Acceptance criteria before enabling a real experiment

1. Same canonical recipe yields the same parent SIGNAL_id across targets, horizons and evaluation assets; changing source slice, operand order, operator/version or parameter yields a different parent. Human display renames do not change it.
2. Different scope-aware calculation memberships yield distinct materializations, with their values computed only after scope resolution. Scope-independent histories are reused across compatible trials.
3. Historical revisions unavailable at cutoff cannot enter features; target labels cannot appear in a feature recipe. Target maturity and partition/exposure policies block unauthorized use.
4. One shared feature/target history can support many trials without duplicate history payloads. All authoritative metrics resolve from exactly one result record per scientific result.
5. Rejected, insufficient and unresolved tests remain queryable beneath the same parent. A validated relationship grants no eligibility to untested horizons/assets.
6. Checksum corruption, wrong immutable reference, stale index, missing artifacts and interrupted commits behave as specified in [10](10_runtime_recovery_storage.md); no partial state appears ready.
7. A bounded legacy adapter comparison records precise semantic/byte equivalence or a documented incompatibility. Full old-store certification is not implied by passing synthetic schema tests.

Later policy approval/revocation is separate append-only lifecycle evidence in `storage/catalog/corrections/records/<event_id>.json`, under a future explicitly typed policy-lifecycle event schema. A pinned policy definition and any historical approval annotation are immutable; changing a marker inside that definition is not a valid live eligibility mechanism. The resolver must check the applicable external decision/revocation evidence as well as the pinned semantic policy.

Remaining decisions: review the proposed Parquet representation and partition/precision policy; choose the first dataset, scope and trial matrix; resolve each chosen legacy contract's compatibility gaps; select backup/durability objectives and operational writer deployment; approve readiness evidence/expiry policy and unresolved scientific definitions recorded in the specification index. These decisions gate their affected implementation, not completion of this review draft.


## Implemented transformation foundation update

[Specification16](16_transformation_execution.md) now implements the scoped single-series
operators, canonical execution envelopes, recipe identities and fixture-only computation.
Existing0.2 definition/Feature/Signal conventions are reused. Date-aware transient results
have an explicitly tagged execution identity profile; they are not published production
materialization manifests. Definition registrations remain separate from observation stores.
No Feature observations or Signal registrations were produced by this foundation task.
