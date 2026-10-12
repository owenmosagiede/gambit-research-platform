# 02 — Data and readiness

Status: **review draft v0.2.0**. Dependencies: [00](00_system_boundaries.md), [01](01_canonical_objects.md), [12](12_data_pipeline_and_storage.md). A subsequent [bounded ALFRED pilot](13_provider_onboarding.md) implements one raw adapter and
scoped historical-vintage/daily-API assessments. A general resolver and live-generation readiness
service remain unimplemented. Machine-readable platform schemas specify snapshots and observations; the certificate shape below is a required future runtime contract, not an issued certificate.

## Evidence and decisions

Verified source evidence: [Data README](../../Data/README.md) separates immutable raw bytes, PIT observations and derived data. PIT research use depends on `available_at`; vintages preserve revisions. [Verified coverage documentation](../../Data/docs/verified-pit-coverage.md) binds dataset/source-view fingerprints, intervals and policy. Reading those sources does not re-certify their datasets. Existing raw/PIT stores stay external and read only via configuration. Current measured sizes and uncertainty remain in the [inventory](../docs/storage_inventory.md).

User-required flow: raw → PIT → optional interactions → ordered transformations → feature/target stores. [12](12_data_pipeline_and_storage.md) defines exact locations and a typed target branch. A future outcome never enters the feature's permitted information set. Retaining legacy P1/P2 after compatibility review does not waive availability or exposure rules.

## Data/readiness contract

| Dimension | Required implementation behavior |
| --- | --- |
| Inputs | Pin dataset, source view/slice, snapshot, source records/vintages, units/mappings, availability/quality policy, calculation scope/membership if applicable, recipe and implementation refs. Pin target construction and actual target maturity for evaluation. |
| Permitted information | For each predictor cutoff, select only records whose defensible availability is no later than cutoff, under an explicit as-of/vintage policy. Reference/observation date is not publication time. Preserve timestamp precision and inference method. Target outcomes may mature later, but enter research only at permitted evaluation/estimation time. |
| Calculations | Perform checksum/schema/foreign-key checks, coverage and policy compatibility, ordered duplicate-key checks, vintage ordering, information-time ordering, typed units and mapping checks. Every normalization/imputation/resampling step requires a pinned source view/operator; none is automatic. |
| Shape/units | Feature/target row and manifest schemas are in platform.schema.json. Keep native source metadata and exact lineage snapshots alongside compact derived rows. UTC timestamps and explicit horizon units remain distinct from calendar labels. |
| Validity | A ready decision binds every dependency it checked, actual requested interval and geometry, certification capability and policy. A folder existing, a latest alias or a legacy READY string is insufficient. |
| Failure | `unresolved` means required evidence or a decision is missing; `blocked` means a known failing dependency/policy. Return structured reasons and exact affected dependencies. A null observation cannot become zero or an inferred positive result. |
| Reuse/invalidation | Reuse only with exact dependency hashes, interval and policy compatibility, no applicable revocation, and all relevant evidence still accessible. New source batches require fresh checks. Changed source view, membership, units, code or policy invalidates affected descendants. |
| Persistence | Preserve source snapshots, certificates, failures and revocations as immutable evidence; indexes are derived. Relocating verified bytes changes only the operational locator. |
| Acceptance | Lookahead/revision, target maturity, wrong member map, incompatible units, duplicate observation, missing partition, stale certificate, revocation and path-relocation cases must be tested with bounded fixtures before real data. |

## Readiness evidence envelope

Proposed certificate storage: `storage/catalog/readiness/records/<certificate_id>.json`. Required fields for the future schema are: schema version; certificate ID/content digest; capability (`historical_replay` or `live_generation`); immutable dataset/source-view/recipe/scope bindings; snapshot and membership hashes; interval and information cutoff; exact policy/version/hash; implementation and check suite references; typed checks with evidence refs and outcomes; overall decision (`ready`, `unresolved`, `blocked`); reasons; issuance time; policy-defined validity conditions; and explicit supersession/revocation references. A ready certificate must not contain unresolved mandatory checks. The structural schema and signer/trust mechanism are deferred to the resolver implementation; no synthetic certificate can establish real readiness.

Historical and live capability are separate. Archived evidence may prove a historical interval without proving a live feed's continued release schedule, availability or delivery. A live subscription cannot retroactively certify historical first-release values. Mixed/partial coverage must preserve exact interval boundaries; the planner reports unsupported requests rather than silently shortening an experiment.

Readiness is an assessment of identified dependencies, not permission to use a previously exposed holdout. Research exposure events and stage partitions are checked independently. Preserve exact temporal boundary inclusivity; half-open intervals are proposed for new period contracts. Legacy fixed periods remain evidence, not assumed newly untouched samples.

## Snapshot resolution and legacy admission

Resolve an external object through registered `store_id + relative_path`, verify permitted root and expected checksum, then bind the exact bytes in a snapshot manifest. A source file changing during verification fails resolution; never rely solely on path/mtime. Large legacy snapshots need a future stable-snapshot/quiescence procedure, since the inventory did not establish writer absence. No legacy data is hashed wholesale in this specification task.

New batches append snapshots and lineage. They never rewrite an existing immutable snapshot or mutate a past materialization to incorporate a revised vintage. Existing transformation causal rules, null/failure reasons and explicit target maturity may be retained through adapters after bounded compatibility checks. A proposed schema does not certify a legacy adapter.

Open: first dataset/source view and bounded interval, source-availability trust/attestation, live certificate invalidation/expiry rules, source stabilization procedure, any missing target units/return basis and stage exposure decisions. Known legacy contracts and retain/adapt/replace treatments are itemized in [the capability map](../docs/legacy_capability_map.md).
