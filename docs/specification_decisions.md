# Specification decisions and implementation gates

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

## Scientific and operational questions still open

| ID | Question / exact gate | Blocks | Needed evidence or decision |
| --- | --- | --- | --- |
| Q01 | Resolved for the present FX gross spot family by U10–U12; which basis and clock apply to other research cases remains open | Only other cases lacking explicit contracts; not this approved FX completion | Register a case-specific policy; no global default, valid-observation substitution or reinterpretation of this FX approval |
| Q02 | What return basis/common clock and transformation are permitted for P3 calibration and P4 horizon combination? | P3/P4 affected calculations | Approved dimensional specification; supplied log example is conceptual, not universal |
| Q03 | How does forecast error covariance relate to uncertainty in estimated expected returns? | P3 uncertainty and P4 alpha-estimation-risk penalty | Separate definitions, units, estimators and empirical acceptance tests |
| Q04 | Which as-of, training/refit, target-maturity and reuse timelines apply to calibration, decay, covariance and weights? | P3/P4 estimators | Leakage-safe versioned policies and replay cases |
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
