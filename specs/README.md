# Specification index — foundation and bounded implementations

> Current Submit/P1/P2 authority: [23 P1/P2 Submit execution](23_p1_p2_submit_execution.md)
> implements the four-input submission, exact Scope routing, versioned kernels, local worker
> and additive 0.8 research stores. Approved Research Spec `RSPEC_FX_SCOPE_ROUTED_SUBMIT`
> **2.0.0** binds scheduled-weekday HAC, required-evidence rules, frozen periods and exact
> source/Target completion references. Submit is enabled by verified profile readiness;
> installation and selection launch no production research. Earlier pending-profile,
> five-input/read-only/service-unimplemented statements describe historical revisions.

> Signal Library presentation follows [22 Reusable recipe summaries](22_signal_library_recipe_summaries.md);
> specification 21 remains the authority for Feature/Scope identity and coverage.

> Current Feature selection authority: [21 Reusable Features and Scope](21_reusable_features_and_scope.md)
> exposes 180 instrument-independent FX recipe definitions. Scope determines application;
> stored observations and readiness are resolved separately per member. Historical
> instrument-bound records in specification 20 remain intact as compatibility bindings.

> Current additive FX Feature support: [20 FX log recipes](20_fx_feature_recipes.md)
> registers approved daily parameter grids across 43 pairs and extends the existing
> Feature Store with bounded, explicitly retrospective samples. Registered recipes
> remain separate from materialized outputs; recipe definitions are selectable under
> specification 21 even when no instrument output has been prepared. Historical/live limits remain.

> Additive FX adapter: [19 Legacy FX sources and return Targets](19_fx_sources_and_return_targets.md)
> preserves the exact 18 requested source histories, registers the 43 requested construction
> recipes and extends the existing stores with 0.5 snapshot/partition profiles. The scientific
> Target definitions in specification 18 remain authoritative. The user's subsequent approval
> authorizes provisional date-aligned crosses and simple returns at 1/7/21/63/252 scheduled
> weekdays on a Monday–Friday/no-holiday calendar for this FX family only. Zero delay means
> return anchoring, not executable entry; historical PIT and live limits remain. Registration
> is not evidence of populated Targets. See [FX data contracts](../docs/fx_data_contracts.md).

> Current Target authority: [18 Return Targets](18_return_targets.md) implements continuous
> investment return contracts, canonical adaptation, exact schedules, historical availability,
> immutable storage/retrieval and API selection. It supersedes the earlier Target draft clauses
> only; old schema examples and stored Feature/Signal identities remain unchanged.
> See the [Target library](../docs/target_library.md) and [implementation evidence](../docs/target_implementation_report.md).

> Current implementation: the first stored Feature and parent Signal now use the approved
> archive-date PIT evaluation rule, with independent canonical retrieval and no research
> metrics. See [17 Stored Feature trial](17_stored_feature_trial.md) and the
> [completion report](../docs/first_signal_trial_report.md). Earlier specification-only
> statements describe their original revision, not the current implementation.
>
> The redundant 2018 sample was physically removed. Full-history reads/replays stand alone;
> [removal details](../docs/alfred_sample_removal.md).

This revision completes the requested **reviewable implementation specification** for the
pipeline, definitions, storage, scientific-memory records, reusable parent Signal and legacy
reuse. It records the user-confirmed P1/P2 reuse and P4/P5 ownership decisions. It does not
claim that every scientific estimator or deployment policy is settled. Explicit gates remain
where the sources do not supply an approved answer.

The small executable experiment contract remains version **0.1.0** unchanged. Platform
feature definitions and recipe identities retain **0.2.0** conventions. The subsequent stored
Feature path adds **0.3.0** date-preserving observation/materialization, operand, library and
audit contracts while retaining the **1.0.0** calculation envelope. These additions do not
upgrade or recompute existing experiment IDs. The original specification revision itself did
not implement stores or services; the subsequent bounded implementations below do.

Subsequent implementation: [13 Provider onboarding](13_provider_onboarding.md) and the
[ALFRED completion report](../docs/alfred_onboarding_report.md) describe the first bounded
real-data pilot. [14 ALFRED PIT store](14_alfred_pit_store.md) and its [completion report](../docs/alfred_pit_report.md)
cover the separate materialized PIT store and historical query database. The statements above
describe the earlier specification revision.

## Authority, evidence and decisions

- **User decisions:** October 8 clarified flow, dataset/recipe-based parent Signal, indexed
  ledger/artifact split, all tested relationships and authoritative metrics; confirmed retained
  verified P1/P2 methods and P4 sleeves/P5 shared-capital ownership.
- **Verified facts:** targeted inspection of existing documents, registries and source code.
  Reading a historical claim does not certify current data, writer state or scientific fitness.
- **Engineering proposals:** field names, full digest identifiers, JSON/Parquet/catalog layout,
  publication protocol and acceptance scenarios introduced for review.
- **Unresolved:** scientific/operational choices listed in the [decision register](../docs/specification_decisions.md)
  with the specific work they block. No hidden defaults or retrospective direction inference.

The [foundation prompt](references/codex_foundation_prompt.txt) and [P3/P4 design](references/p3_p4_design_reference.txt)
remain preserved verbatim with [provenance](references/source_manifest.json). Current user
instructions subsequently authorized the UI, raw/PIT onboarding, transformation foundation
and one stored Feature/Signal path. Legacy instructions remain source evidence and never
authorize running their jobs. Legacy Data/FX remain read only.

## Original foundation specification coverage

The table records the scope and gates of the original 00–12 review. Subsequent implementation
status is recorded in 13–23 and the current authority pointers above.

| File | Purpose and dependencies | Sources | Review status / remaining gates |
| --- | --- | --- | --- |
| [00 System boundaries](00_system_boundaries.md) | Ownership and canonical handoffs; governs 01–12 | User decisions, foundation, supplied P3/P4 | Interfaces specified; scientific stage gates explicit |
| [01 Canonical objects](01_canonical_objects.md) | Parent recipe, relationship, trial/materialization identities; used by 03–12 | User Signal clarification; legacy Feature/Signal/ledger identities | Exact identity projections proposed; v0.1 implemented behavior unchanged; future hash/reference enforcement tested through examples only |
| [02 Data and readiness](02_data_and_readiness.md) | Information sets, snapshots, validity/invalidation; needs 01/03/12 | Legacy PIT/source-view/coverage contracts | Readiness requirements specified; issuer/current-data certification and complete certificate schema/implementation gated |
| [03 Features, targets, scopes](03_features_targets_scopes.md) | Definition ownership, typed dataflow and retained operator rules; needs 01/02/04/12 | Transformation/Feature/Target/Scope registries and source | Definition/pipeline schema specified; individual scientific registrations and admissible data remain future work |
| [04 Experiment submission](04_experiment_submission.md) | Exactly five inputs, request, resolution and attempts; needs 01–03/10/12 | Preserved foundation and current parent-Signal clarification | Existing structural implementation retained; persistent service and actual resolution unimplemented |
| [05 P1 discovery](05_p1_discovery.md) | Retained methods, admission and outcomes; needs 01–04/12 | Versioned legacy engine/Research Spec/Admission source | Concrete method/version matrix and acceptance boundaries; exact component parity, exposure and selected-policy readiness required |
| [06 P2 validation](06_p2_validation.md) | Prescribed validation into per-relationship eligibility; needs 01–05/12 | Legacy validation source and current user reuse decision | Retained rules/diagnostics and explicit gates; historical certification not copied automatically |
| [07 P3 forecasting](07_p3_forecasting.md) | Individual calibration, decay, dependence and combination; needs 01/02/03/06 | Supplied P3/P4 design | Interfaces/validity/acceptance specified; exact units, uncertainty meaning and estimation timeline block numerical implementation |
| [08 P4 portfolios](08_p4_portfolios.md) | Sleeve construction using forecasts, market risk, costs and mandate; needs 01/02/07/09 | Supplied P3/P4 plus user sleeve decision | Ownership specified; common clock, uncertainty/cost/risk estimators and feasibility details gated |
| [09 P5 and execution](09_p5_and_execution_boundary.md) | Shared-capital coordination and explicit order authority; needs 00/01/08 | User allocation decision, foundation and supplied boundary | Ownership settled; allocation mathematics, capital feedback, aggregate feasibility and execution policy remain open |
| [10 Runtime/recovery/storage](10_runtime_recovery_storage.md) | Idempotency, publication, index recovery and retention; needs 01/02/04/12 | Legacy ledger and compact artifacts; storage inventory | Local publication/recovery protocol specified; runtime service/events, deployment policies and durability tests future |
| [11 UI/observability](11_ui_and_observability.md) | Plain white five-input page and truthful shared backend; needs 04/10 | Foundation and current clarified library role | Initial page/service acceptance specified; no page/API built |
| [12 Pipeline and storage](12_data_pipeline_and_storage.md) | Exact paths, record ownership, schemas, observations and legacy adapters; needs 01–06/10 | Source/registry capability map and user dataflow | Concrete layout and checks proposed; production stores/adapters and representation-repacking implementation not built |

## Companion artifacts

- [Platform schema](schemas/platform.schema.json), [schema usage and conformance notes](schemas/README.md),
  and [unchanged experiment schema](schemas/contracts.schema.json).
- [Legacy capability map](../docs/legacy_capability_map.md) and [machine-readable map](../docs/legacy_capability_map.csv):
  92 operator/extension records across distinct catalogs, plus 13 component decisions. This is
  targeted verified coverage, not proof that every legacy script or scientific behavior was audited.
- [Portable exact layout](../config/storage_layout.example.json); actual legacy raw/PIT machine mappings
  stay in ignored local configuration. The new root contains the full-history raw/PIT package;
  its redundant pilot was retired without changing the preserved scientific history.
  Specification 17 implements scoped Feature JSONL persistence in the existing reserved paths;
  specification 18 implements Target JSONL persistence in the same shared payload store; Parquet remains future work.
- [Decisions/open gates](../docs/specification_decisions.md), [current verification](../docs/specification_verification.md),
  and [historical storage inventory](../docs/storage_inventory.md).

## Transformation specification requirements

Every transformation/stage specification must cover: inputs; permitted information set;
calculations; output units/shape; validity; failure behavior; reuse/invalidation; persistence;
and acceptance tests. The stage drafts make each dimension explicit. A missing numerical
choice stays a named implementation blocker rather than an invented calculation.

## What happens next

The UI, raw/PIT onboarding, transformations, reusable Feature preparation, populated FX
Targets and durable P1/P2 Submit pathway are implemented. Research Spec 2.0.0 approves
retrospective date-label analysis with all eligible history through 31 December 2021
for discovery, then 1 January 2022 through 31 August 2026 as the **Validation period**.
The discovery start is resolved from selected members' structural history and frozen in
the plan. Specific-recipe prior exposure is unknown; the period is not certified untouched.
The next research execution begins only on explicit Submit. Existing records and historical
reports remain unchanged. Historical/live certification, non-FX research alignment and
downstream P3/P4/P5 mathematics remain separate work. See [23](23_p1_p2_submit_execution.md).

## Subsequent full-history implementation

[15 ALFRED full history](15_alfred_full_history.md) specifies the separately versioned raw/PIT
extension. The [completion report](../docs/alfred_full_history_report.md) records actual full-history
coverage, historical comparisons, paths and tests. The redundant 2018 pilot was subsequently removed.

## Implemented transformation execution

[16 Transformation execution](16_transformation_execution.md) is the current implemented
contract for the single-series library. It supplies executable canonical input/intermediate/
result validation, recipe and materialization identity utilities, approved operator/policy
resolution, composition and cutoff-scoped historical calculation. The
[active operator catalogue](../docs/transformation_library.md) is generated from all 98
version 2 registrations; [the historical catalogue](../docs/transformation_library_catalogue.md)
is preserved. See the [completion report](../docs/transformation_foundation_report.md)
for actual tests and remaining source gates. Earlier specification-only statements above
remain historical context, not the current implementation status.

## Implemented stored Feature and Signal path

[17 Stored Feature trial](17_stored_feature_trial.md) specifies the verified source resolver,
canonical adapter, approved archive-date schedule, exact generic percentage-change recipe,
additive 0.3.0 Feature Store contracts and independent retrieval. The
[completion report](../docs/first_signal_trial_report.md) records actual production identities,
coverage, historical operand comparisons, retry/retrieval checks and source preservation.
One logical Signal groups its materializations; future tested Target/horizon relationships and
authoritative result links remain separate. Materialized does not mean scientifically tested
or live certified.

## 18 — Return Target implementation

[18 Return Targets](18_return_targets.md) is the authoritative executable return-only
Target contract, with separate basis/representation/comparison, certified economics,
versioned scheduling/availability, deterministic identity, immutable materialization
and explicit historical retrieval. The [Target schema](schemas/target_store.schema.json)
and runtime semantic validators add 0.4 records without rewriting old approved versions.
Production source eligibility remains distinct from tested implementation capability.

## 19 — Legacy FX source and reusable price adapter

[19 Legacy FX sources and return Targets](19_fx_sources_and_return_targets.md) specifies the
exact 18-source/43-instrument universe, read-only raw locators, captured-history PIT rows,
role-independent normalized/constructed prices and compact return materializations in the
existing Target Store. [FX data contracts](../docs/fx_data_contracts.md) lists exact storage
paths, callable interfaces, identity/reuse rules and API inspection. The
[additive FX schema](schemas/fx.schema.json) uses 0.5 envelopes while retaining 0.4 scientific
Target definitions and earlier approved Feature/Signal artifacts.

Verified historical captures have unknown publication times, daily-close conventions and
price basis. They cannot receive strict historical replay certification. The subsequent user
approval resolves provisional equal-date cross alignment and the 1/7/21/63/252 scheduled-
weekday simple-return batch for this FX family. The approved schedule is Monday–Friday with
no holiday exclusions, exclusive forward counting, anchor-close entry and exact endpoints.
Known incompatible observations remain blocked. Earlier pending-decision audits remain
historical evidence. Final execution counts and tests must be taken from the execution report
and completed catalog artifacts, not inferred from approval, code or recipe registration.

## 23 — Installed P1/P2 Submit execution

[23 P1/P2 Submit execution](23_p1_p2_submit_execution.md) records the current four-input
service, five-horizon TS/CS routing, retained numerical source provenance, preparation
boundaries, immutable 0.8 research records, recovery and scoped-result reads. The exact
registered profile is `definitions/research_specs/RSPEC_FX_SCOPE_ROUTED_SUBMIT/2.0.0.json`,
referenced by ID/version/content hash from `config/research_execution.json`. Its new
`scheduled_weekday_hac_v2` and `unresolved_required_v1` policies preserve older versions.
The profile pins 43 source snapshots and 215 completed Targets; no historical experiment
schema, stored observation or scientific record is migrated by this addition.

- [Feature application foundation](24_feature_application_contracts.md): explicit application bindings, shared compatibility checks, frozen semantics, and deferred entity mapping.
