# 11 — Submission UI, research library and observability

Status: **review draft; no UI or API built**. Dependencies: [01](01_canonical_objects.md), [03](03_features_targets_scopes.md), [04](04_experiment_submission.md), [10](10_runtime_recovery_storage.md). The current task completes specifications only.

## Source requirements and user decisions

The first future submission page is plain white with exactly five research inputs: **Feature + Target + Scope + Expected Direction + Research Spec**, plus Submit Experiment and truthful submission status. Human and agent submissions use the same backend contract; science remains outside the UI.

The Feature selection resolves the authoritative parent `SIGNAL_X` recipe in `definitions/features/`. A parent binds source dataset/source-view/slice and ordered optional interactions/transforms with versions/parameters; the UI does not create a second recipe or add a sixth scientific input. Tested assets/horizons/Scopes/directions/specs/periods belong to relationships. The research library must display **all tested relationships** and dereference authoritative trial/validation records for every metric. Parent-level success must never conceal failed or untested relationships. Library navigation is a separate later surface, not extra research inputs added to the white submission form.

## 1. Inputs

The submission UI consumes versioned registry summaries and exact selected references, then sends the [04](04_experiment_submission.md) envelope through the same service contract available to agents. Request/idempotency identity is operational metadata, not a research field. Registry display text may be mutable presentation, but scientific ID/version/digest binding comes from the resolver.

The library consumes a query projection linking parent recipe → tested relationship → trial/result/admission → validation result/decision → optional downstream forecast attribution. It receives exact source references and immutable metric units, policies, periods and as-of states. Observability consumes authoritative structured request/resolution/attempt/events, blockers, dependency/readiness evidence and storage measurements. It never infers facts from log phrases or directory names.

## 2. Permitted information set

Display the last known authoritative state with its observation/update time and stale/unavailable indicator. A UI refresh cannot silently repin “latest” definitions or update a frozen experiment's snapshots. Registry resolution and readiness are separate from structural validation. Metric visibility does not imply the period is untouched; viewing/testing exposure must be represented under the research-period policy, including known legacy exposure.

A prospective P3-eligible filter uses exact relationship certification and validity at the selected cutoff, not parent membership or a historical green badge. Incomplete historical mapping or missing ex ante direction must remain visible as such, without fabricating a current-ready state.

## 3. Presentation calculations and data ownership

The UI performs presentation-only formatting/filtering/sorting. It does not compute admission, re-estimate IC, infer Expected Direction, reconstruct a recipe from a label, combine horizons, impute missing metrics or select method thresholds. A displayed aggregate count must declare its query basis and include failed/unresolved rows in the underlying population. Sorting by a metric must preserve missingness rather than treating missing as zero.

**Proposed library row content:** parent recipe label/reference; tested instrument/universe and scope version; Target economic basis and explicit horizon unit; TS/CS mode; declared direction separately from observed effect; Research Spec/policy/version; tested period and known exposure; trial/attempt state; admission and validation outcomes; authoritative metric values/units with source record references; evidence availability and certification status. Expand a row to inspect the recipe and exact evidence; do not duplicate editable recipe or metric stores.

All tested relationships include scientifically rejected and failed/unresolved attempts. An untested relationship is not invented to fill a grid. Multiple immutable results/retries remain accessible under the same logical relationship, with a stated version/selection rule. Legacy evidence retains original IDs and statuses alongside any reviewed mapping.

## 4. Output shape and units

The submission form contains exactly the five fields above. Target determines horizon/basis; Research Spec determines methodology and periods, so no extra freeform horizon, parameter grid, capital or method field is added. Selected definitions may show read-only explanations without becoming new inputs. Expected Direction is an explicit POSITIVE/NEGATIVE declaration, never prefilled from results.

The response view separates request recorded, unresolved/blocked resolution, queued/running attempt where actually supported, completed execution and scientific decision. Exact serialized state names follow the approved runtime/API contract; prose here is not a competing enum. With the present pure contract library there is no submission service or executor, so no recorded/running success is claimed merely because structural validation passes.

Library return metrics use their source units and explicit basis; a valid-observation horizon is not relabeled calendar days. Forecast variance, standard deviation and estimated-mean uncertainty need distinct typed labels. Storage displays measurement time/method/coverage and separates measured bytes from retention candidates or actually reclaimed bytes.

## 5. Validity and readiness

The backend is authoritative for validation, exact reference resolution, policy compatibility, idempotency and readiness. Client validation may improve error messages but cannot weaken unknown-field rejection or immutability. Validate that every displayed scientific metric resolves to a source record, policy and units; a broken link makes evidence unavailable, not zero or approved. A stale certificate affects eligibility without erasing historical evidence.

The library is a view over evidence, not the canonical definition registry, trial ledger, validation ledger or position ledger. Roles/access control, pagination, query consistency and exposure logging need approved transport/runtime detail before implementation.

## 6. Failure behavior

Malformed forms show field-specific contract errors without implying an execution failure. Unknown references, compatibility gaps and missing certificates show unresolved/blocker reasons. Service/network errors cannot be presented as scientific rejection. An uncertain submit outcome must retain the original request ID for safe retry under [04](04_experiment_submission.md), not generate a new request blindly. A hypothesis rejection after successful calculation is shown separately from a crash. Missing metrics/evidence, partial query coverage and stale status remain explicit.

## 7. Reuse and invalidation

Cache immutable definition/evidence summaries by exact identity and version; keep operational state/query caches refreshable with visible freshness. Invalidated evidence changes eligibility projections, not historical metrics. A renamed parent label does not create a new recipe. A different recipe order/version does. A changed query filter never rewrites relationships or changes their underlying scientific identities.

## 8. Persistence and observability

Backend stores requests, resolutions, attempts and scientific evidence. UI selections/session state are not scientific truth. Record structured progress from actual completed/total work where defined; do not invent percentages, estimated completion or activity from timestamps alone. Observability distinguishes request state, execution progress, scientific decisions, blockers, failed attempts, readiness validity and storage coverage. Logs are supporting diagnostics and must omit credentials.

The library projection stores references/indexes and optional rebuildable caches, not independently editable metric copies. Keep provenance for every displayed legacy/new record. P4 sleeve/P5 allocation/execution status may be later separate operational views; they cannot appear as scientific input fields or trading authority on the submission page.

## 9. Acceptance scenarios

- A user and agent submitting the same exact five inputs receive equivalent normalized intent and idempotency behavior.
- Feature resolves the parent recipe without a sixth Signal selector. Target supplies the horizon; changing it does not rewrite the parent.
- One parent's validated 63-observation, failed 21-observation and unresolved 7-observation relationships all remain visible with exact source metrics; only the eligible 63-observation relationship appears in a P3-ready view.
- A historical observed-positive record without frozen ex ante direction shows missing provenance, not a fabricated POSITIVE declaration.
- A recorded request with no executor never displays running; structural validation alone never displays ready.
- Lost submit response reuses its request ID; conflicting content under that ID shows the backend conflict rather than creating duplicate research.
- Missing IC remains missing; deleted/unavailable source evidence is not represented by a stale editable cached metric.
- The white submission page contains exactly five research inputs and no executable expression, capital, venue or trading controls.

These are design acceptance cases, not browser tests performed now. Implement the first page only after the shared transport/status and applicable registry contracts are approved; the present task does not build a UI or imply a live submission service.
