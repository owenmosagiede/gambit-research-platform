# Specification decisions and implementation gates

> Subsequent 27 November 2026 incremental-value decision: the user requires P3
> to measure each signal's incremental value to the model containing it, preserve
> this as metadata, and support a Signal Library ranked greatest to least by
> incremental contribution. [Specification 27](../specs/27_p3_incremental_value_and_library_ranking.md)
> defines paired causal refit ablation, predictive-loss scores, exact model context,
> coverage/exposure and read-only as-of ranking. The predictive-MSE score, null
> references and aggregation conventions are explicit design choices. No current
> P2 result is reinterpreted as an incremental score; no engine or page is deployed.

> Subsequent 27 November 2026 architecture decision: the user added six P3
> combination alternatives alongside the existing flat covariance-aware method,
> required manual family membership, and explicitly selected equal/equal,
> error/error and ridge/ridge at the two hierarchical levels.
> [Specification 26](../specs/26_p3_combination_architectures.md) records the
> amendment to the original flat-only/no-family-forecast rule. The reference text
> and all historical research identities remain unchanged. The new architecture
> semantics do not install a policy, infer a user's family assignment or close
> the outstanding numeric/readiness/implementation gates.

> 27 November 2026 calibration design update: the user requested a complete P3
> TS/CS comparison and basket-component definition. [Specification 25](../specs/25_p3_ts_cs_calibration.md)
> now defines the exact-Target full-return boundary, version-1 TS/CS estimators,
> baseline providers, calibration timing/sample defaults, exposure and no-double-counting
> rules. This resolves those design choices only. No production policy is registered,
> P1/P2 result reinterpreted, canonical P3 engine implemented, or P4 uncertainty/solver
> gate closed by the document. The older decision register below remains historical
> context except where this dated update explicitly narrows a gate.

> Subsequent 9 October FX approval: the user resolved the two pending FX-family decisions.
> Simple gross spot returns at 1, 7, 21, 63 and 252 scheduled weekdays now use an explicit
> Monday–Friday/no-holiday calendar, exclusive forward counting, anchor-close entry and exact
> endpoints. Equal provider-date cross alignment is approved provisionally where timing is
> unknown; demonstrated incompatibility remains blocked. These rules apply only to this
> FX family and do not relax Feature availability, historical label/training cutoffs or live
> readiness. [Specification 19](../specs/19_fx_sources_and_return_targets.md) records the
> complete amendment. Earlier review text remains decision history, not evidence approval
> existed before the user's subsequent instruction.

> October 9 implementation update: the user authorized the complete continuous return
> Target subsystem, including executable scheduling, availability, storage and API integration.
> [Specification 18](../specs/18_return_targets.md) now resolves those implementation choices;
> [the Target report](target_implementation_report.md) records evidence. Q01 below now concerns
> a concrete real-source research binding, not an absent Target constructor or another design
> task. Scheduled sessions/bars, calendar days and elapsed durations are distinct supported
> policies; legacy valid-observation horizons are not silently reused. The subsequent FX source
> onboarding and family approval supersede the original market-source prerequisite for that
> bounded retrospective family. The original October 8 review follows as
> decision history; its original task/follow-on status is not the current implementation status.

Review draft recorded 2026-10-08. This document distinguishes direct user decisions,
engineering proposals, verified legacy evidence and unresolved scientific decisions.
The source documents are preserved without alteration. No approval is inferred from legacy
code, synthetic fixture values, directory names or the existence of a schema.

## User decisions (authoritative for this revision)

| ID | Decision | Consequence |
| --- | --- | --- |
| U01 | Complete the implementation specifications and legacy reuse map now; no bulk migration | All writes are new-platform specifications, schema examples/tests and supporting notes; legacy stays read-only |
| U02 | Raw → PIT → optional interactions → transformations → Feature/Target stores | Typed causal predictor and ex-post outcome branches share definitions where applicable; target leakage is forbidden |
| U03 | One Signal ID represents its source dataset(s) and transformation definition and can be tested on multiple assets × horizons | Target-independent parent recipe; individually identified tested relationships and trials |
| U04 | Ledger stores compact trial metadata/results; indexed artifact store holds detailed evidence | Separate durable records, evidence manifests, payload references and rebuildable indexes |
| U05 | Signal library shows every tested target × horizon and metrics for the signal specification | Metrics resolve to authoritative trial/validation records; failures and rejections remain visible |
| U06 | Retain verified legacy P1/P2 methods as explicitly versioned policies after compatibility checks | Preserve numerical methods and thresholds where verified; record semantic gaps instead of silently changing or approving them |
| U07 | P4 constructs individual trading sleeves; P5 allocates shared capital across sleeves | High-level ownership settled; exact capital feedback, aggregate constraints and final feasibility protocol still needs specification |
| U08 | Initial interface has exactly Feature, Target, Scope, Expected Direction, Research Spec | Parent Signal derives from Feature definition; no sixth research input; humans and agents share contract |
| U09 | Onboard exactly the selected 18 legacy Twelve Data sources and register the requested 43 economic instruments | Existing captures and completed work are preserved; no extra provider, download, source, migration or FTMO eligibility inference |
| U10 | Approve this FX gross spot family: simple decimal-fraction returns for 1/7/21/63/252 scheduled weekdays, Monday–Friday with no holiday exclusions | Exactly 215 logical instrument/horizon combinations; resolve exact endpoints first, exclude anchor from counting, retain unavailable reasons; no extra convention or unrelated-family default |
| U11 | Approve provisional cross construction on equal provider date labels where historical timing is unknown | Unknown synchronization does not alone prevent this family's materialization; known incompatible sessions, currency/direction mismatches, invalid prices and conflicts remain blocked |
| U12 | Zero scheduled entry delay anchors returns at the anchor close only | No execution-fill certification; Feature availability, label maturity, strict training cutoffs, discovery/validation boundaries and live readiness remain unchanged |
| U13 | Add flat equal/error/ridge and hierarchical equal/error/ridge alongside existing P3 combination; families are assigned manually by the user, with the same method at both hierarchical levels | Optional family forecast nodes retain all individual calibrated leaves, nested provenance and effective contributions; no automatic clustering/assignment or default architecture change |
| U14 | P3 measures each signal's incremental value to its model as metadata, enabling a Signal Library ranked by incremental contribution | P3 owns derived full-versus-without-signal evaluation; the library ranks saved model-context evidence and preserves original research identities/results |
| U15 | A signal can belong to many models; show every membership and its rank in each, with library filtering/ordering by the model being evaluated | Default SINGLE_MODEL ranking uses one exact model/version/context; optional multi-model summaries never replace per-model scores/ranks or invent nonmember scores |

## Engineering proposals introduced in this draft

| ID | Proposed choice | Review/verification requirement |
| --- | --- | --- |
| E01 | Single authoritative predictor recipe in definitions/features; FEATURE_<hash> and SIGNAL_<same hash> are typed identifiers | No second editable signal definition; hash and cross-reference conformance examples |
| E02 | Full SHA-256, canonical versioned JSON projections, exact immutable refs; typed numeric strings | Freeze identity vectors before production; existing experiment0.1.0 unchanged |
| E03 | JSON compact durable records, content-addressed large payloads, rebuildable SQLite indexes | Atomic publication, conflict rejection, crash recovery and index-rebuild tests |
| E04 | Exact storage layout and machine schemas published in specs12 and schemas/platform.schema.json | Schema and semantic acceptance checks; no production database created by this task |
| E05 | Parent library is a projection over relationship and result links | All results remain traceable to one authoritative record; no editable metric copies |
| E06 | Read-only legacy adapters and explicit mapping records before any migration | Preserve original IDs/content and exposed research periods; establish exact compatibility |
| E07 | Stage-specific implementation gates allow intake/storage work before unresolved forecasting/portfolio mathematics | A blocked calculation never produces fake readiness or running status |
| E08 | Define error weighting as inverse historical forecast MSE and ridge as positive-lambda, simplex-constrained squared-error/L2 combination, preserving the original nonnegative sum-to-one boundary | Full node-history/tuning/solver policies and isolated numerical implementation remain required; unconstrained ridge needs a distinct architecture |
| E09 | Use causal refit ablation and paired out-of-sample MSE reduction, normalised by without-signal loss, as the headline incremental-accuracy score; rank within a selected model by default and aggregate applicable contexts only in an explicit summary profile | Model/architecture/pair/Target/horizon/window and coverage remain explicit; scores are non-additive, negative values retained, missing evidence unranked; schemas/refits/inference/projections remain implementation work |

## Scientific and operational questions still open

| ID | Question / exact gate | Blocks | Needed evidence or decision |
| --- | --- | --- | --- |
| Q01 | Resolved for the present FX gross spot family by U10–U12; which basis and clock apply to other research cases remains open | Only other cases lacking explicit contracts; not this approved FX completion | Register a case-specific policy; no global default, valid-observation substitution or reinterpretation of this FX approval |
| Q02 | P3 calibration resolved for the bounded current FX profile by [25](../specs/25_p3_ts_cs_calibration.md): preserve exact Target/horizon/units, reconstruct full CS return once. Other Target families and P4 horizon-rate conversion remain open. | Other families and P4 horizon combination; not the defined P3 calibration geometry | Implement and verify the versioned calibration contract; a log/common-rate convention is not inferred for P4 |
| Q03 | How does forecast error covariance relate to uncertainty in estimated expected returns? | P3 uncertainty and P4 alpha-estimation-risk penalty | Separate definitions, units, estimators and empirical acceptance tests |
| Q04 | P3 calibration timing/refits, mature-only inputs and exposure rules are defined in [25](../specs/25_p3_ts_cs_calibration.md). Decay, covariance and weight estimation timelines remain open. | Remaining P3/P4 estimators and unimplemented calibration | Closed policies/validators, bounded arithmetic and leakage-safe replay evidence; retrospective selected-roster replay is not an untouched forecast record |
| Q05 | How do P5 capital allocations/aggregate constraints feed P4 sleeve feasibility and final execution quantities? | P4/P5 executable allocation | Capital-envelope protocol, aggregate-risk model, rounding/feasibility checks and conflict policy |
| Q06 | Which existing periods are already exposed and which validation cases remain admissible? | New P1/P2 scientific certification | Reconcile retained exposure histories and policies; never declare legacy-inspected periods untouched |
| Q07 | Can each retained legacy method/operator reproduce its original result under the new interface? | Adoption of that component | Source/definition/implementation pins and bounded parity tests; no blanket certification |
| Q08 | Does an old record contain independently supported ex-ante Expected Direction? | New-contract eligibility for that legacy relationship | Frozen pre-result record; never backfill from IC/coefficient sign |
| Q09 | Which source/manifest/readiness policies and current writer guarantees can be certified? | Real data execution and later cleanup | Dependency-bound evidence, appropriate batch checks and explicit safe access; old inventory writers remain UNKNOWN |
| Q10 | Which exact pilot feature, scope, target(s) and frozen Research Spec will exercise the first end-to-end run? | Later pilot execution, not this specification task | Explicit bounded research selection after the spec review; no implicit full grid |

The user's U06 resolves whether verified legacy methodology is the starting point. It does
not approve every historical implementation bug, unclear policy or unverified artifact. U07
resolves top-level ownership, not the numerical capital/constraint coordination algorithm.

## Follow-on task boundaries

1. Review these specifications and close gates needed for submission intake; implement the
   plain white five-input page and minimum shared durable backend with truthful states.
2. Select one bounded pilot and verify/adapt its required legacy components; implement its
   data/store/P1/P2 path under the reviewed policies with trial and signal-library evidence.
3. Expand scientific execution only as stage-specific gates pass. P3/P4/P5 numerical engines,
   a full research replay, bulk migration, archiving and deletion remain separately scoped.

No additional user input is needed to finish this reviewable draft. Questions above require
answers before their affected scientific implementations, not invented defaults in this task.


The registered completion bundle is `config/fx_retrospective_completion.json`. It pins
`EVIDENCE_63a162f8a975a25fda80701febe60896047eaf299903c3bcc8d83081f26b818c@1.0.0`
and retrospective policy
`POLICY_2ba9539c29b93277e30ee4c2b0752c3e54cbcf9a101ec19b2628dc5fb43ec14b@1.0.0`.
These are actual registered approval identities, not output-completion evidence.

## FX approval evidence and preserved limitations

The subsequent approval attachment has SHA-256
`30a1a93f2ca0dbc2fb199dcfeadd73e04abdc6f04a3d38d1639c63d79b410bfb`.
The active policy registry and each actual build must pin the corresponding evidence and
versions. The two formerly pending choices are resolved; do not stop again for their approval.
A genuinely new source defect or unresolved requirement stops only affected work.

This approval permits construction, persistence and provisional retrospective inspection.
It does not establish unknown publication times, source vintages, daily-close synchronization,
price basis, live/executable readiness or FTMO account eligibility. Direct and inverse quotes
carry these limitations just as crosses do. Successful recipe registration alone does not
make an instrument or Target ready. Coverage, missing/invalid/pending outcomes and actual
stored labels must be reported independently for every approved combination.
