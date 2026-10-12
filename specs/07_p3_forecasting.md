# 07 — P3 individual forecasting and combination

Status: **review draft with explicit scientific gates; no P3 engine implemented**. Dependencies: [01](01_canonical_objects.md), [02](02_data_and_readiness.md), [03](03_features_targets_scopes.md), [06](06_p2_validation.md). The [preserved P3/P4 reference](references/p3_p4_design_reference.txt) remains the intended design. Source requirements below are distinguished from proposed interfaces; unresolved estimators are not filled with legacy defaults.

## 1. Inputs and boundary

**Source requirement:** receive validated SignalHorizon relationships, historical PIT scores and exact Target returns, current available score, frozen Expected Direction, validation evidence, availability timestamps and upstream lineage. **Current identity decision:** each relationship references a parent `SIGNAL_X` through its Feature definition. Parent recipe identity excludes tested assets, Scope, Target/horizon, direction, Research Spec and period; those remain explicit relationship/trial context. An eligible roster contains relationship identities and their exact validation/certification evidence, not just parent IDs or a producer's run directory.

P3 admits only the exact relationship with valid P2 evidence and compatible readiness at its forecast cutoff. A library may display all tested relationships, but failed, unresolved, merely admitted and historical-unmapped relationships cannot enter P3. A 63-observation relationship is not a 7-observation forecast. For CS, bind validated Scope and membership/eligibility before score generation and forecast allocation to instrument members.

**Proposed input bundle:** eligible relationship roster, immutable scoped score/Target histories, current score references, forecast cutoff, pinned calibration/decay/dependence/combination policies and implementation manifest, required readiness evidence and applicable randomness. Family ID is optional derived metadata, never a prerequisite that replaces constituent relationships.

## 2. Permitted information set

Every historical forecast must be reproducible using only information available at its recorded cutoff. Predictor observations satisfy their PIT policy; a historical label may enter estimation only after its Target endpoint and availability requirements have matured. Preserve each fit cutoff, eligible training observations, refit time and live forecast cutoff separately. Replaying a final model across earlier history is not automatically valid forecast-error history.

**Scientific gate:** the exact training/calibration, decay-fitting, covariance-fitting and weight-estimation timelines are not yet approved. Their windows, update frequency, holdout usage, label overlap/maturity treatment and exposure policy must be explicit before calculation. Retaining P1/P2 methods does not select a P3 estimator or authorize using an already examined validation window for tuning.

## 3. Source calculations and unresolved estimator choices

| Stage | Intended source requirement | Contract gate before implementation |
| --- | --- | --- |
| Individual calibration | Convert each validated relationship's score independently into expected return in its exact Target economic units. TS/CS estimators may differ. | Approve estimator, training sample, mapping, regularization and minimum evidence for each permitted geometry. |
| Decay | `d(0)=1`; decayed forecast is fresh forecast × `d(age)`; aging reduces predictive influence. Apply the same historical decay rule when calculating forecast errors. | Define age clock, defensible model, freshness eligibility and estimation timeline. Unsupported decay cannot become indefinite invented carry-forward. |
| Forecast-error histories | For compatible instrument × Target basis × horizon, error is realized Target return minus the historical constituent forecast. | Pin historical forecast versions, realized label availability, compatible sample alignment and treatment of missing/overlapping histories. |
| Dependence | Estimate a shrinkage covariance of constituent forecast errors, separate from market return covariance. | Approve estimator/shrinkage target, sample requirements, numerical tolerances and missing-history policy. |
| Combination | Constrained generalized least squares using shrinkage forecast-error covariance; weights nonnegative and sum to one. | Pin estimator/solver/tie/failure rules. No equal-family or equal-signal fallback is implied. |
| Diagnostics | Preserve forecast dispersion, effective independent count, largest contributions, signal/family concentrations and decay contributions. | Define exact diagnostic formulas and units; do not invent a count/concentration metric to fill a field. |

Every eligible constituent is individually represented, even when it receives zero combination weight. Family metadata supports redundancy diagnosis and attribution; it never collapses members into an equal-weight family score. Do not choose combination weights from IC, Sharpe, family names or retrospective subjective preference.

## 4. Output units and shape

**Proposed interface:** a SignalForecast references one validated relationship, its parent, instrument/member, exact Target/horizon, forecast timestamp, score, calibration fit, fresh value, decay policy/age and resulting decayed value. InstrumentHorizonForecast contains the instrument, Target reference and economic basis, explicit horizon quantity/unit, cutoff/availability, expected return, typed uncertainty, exact constituent roster, weights/contributions, diagnostic and family metadata references, exclusions/blockers and complete lineage. A field whose method is not approved is unavailable with a reason, not a fabricated zero.

For a Target whose canonical return unit is `U`, calibrated expected return and forecast error are in `U`, and forecast-error covariance/variance is in `U²`. If a standard deviation is displayed, it must be explicitly typed and converted from the appropriate variance. Source `w' Σe w` denotes a combination of forecast-error covariances; it is not automatically uncertainty of an estimated conditional expected return. **The relation to P4's expected-return-estimation covariance remains an explicit scientific gate.** No default spot basis, calendar horizon, percentage scale or interchangeable generic uncertainty scalar is selected here.

## 5. Validity and readiness

Verify exact relationship validation/certification, data/definition/policy/code fingerprints, required label maturity, Scope/member eligibility, matching return basis/horizon, known calibration/decay age semantics and approved history. Distinguish forecast availability from subsequent outcome availability. Covariance ordering must match the constituent roster and its mathematical/numerical validity checks. Historical-replay evidence does not establish live-generation capability; current batches still require their own checks.

Historical old `SIGNAL_*` records remain evidence. They become new eligible relationships only through explicit identity/provenance compatibility and certification; observed sign cannot supply missing ex ante direction. A valid parent or family alone never grants P3 eligibility.

## 6. Failure behavior

Unknown method/unit/timeline, unverified certificate, absent fit history, incompatible Target basis, stale score without defensible freshness/decay policy or invalid covariance yields a structured blocker. Preserve reason, affected relationship/group and input references. A contract/digest mismatch is an integrity failure; a solver failure is operational failure. Do not emit a zero forecast, equal weights, interpolated horizon or “ready” forecast as a fallback. If a policy later allows dropping constituents, record the exact permitted exclusion and recompute its identity; silent drops are prohibited.

## 7. Reuse and invalidation

Reuse fit/forecast artifacts only for identical scoped inputs, fitting policy, permitted information set, implementation and valid evidence. Parent recipe reuse does not imply identical scoped scores. A corrected target, changed validation decision, member set, decay rule, covariance fit or current score invalidates its affected forecast group and descendants. Retain unaffected valid work and all failed attempts. Display names, storage paths and retry identities do not change scientific meaning.

## 8. Persistence

Persist compact immutable fit manifests, individual forecast/error-history references, covariance/roster ordering, combination weights, diagnostic definitions/evidence, source decisions and final forecast records. Large histories live once as referenced payloads. Record forecast versions as they existed before observing subsequent labels; later estimates never overwrite them. P3 attribution references parent and exact relationship IDs. The library reads authoritative evidence and does not become a second forecast store.

## 9. Acceptance scenarios

- A parent with validated 63-observation and failed 21-observation relationships supplies only 63-observation evidence; no 7-observation output is created.
- Different CS Scopes bind before score computation; changing Scope invalidates scoped scores while preserving the parent recipe identity.
- Two constituents in one family remain separately calibrated and attributed. Family labels do not change their science or create equal weights.
- A not-yet-matured label cannot influence any fit at an earlier cutoff; historical decay matches operational decay exactly.
- Unsupported stale carry-forward blocks; it does not create a fresh forecast with an invented decay coefficient.
- Weight/roster mismatch, missing covariance validity, missing uncertainty type or mixed economic bases fails validation.
- A new data batch without live readiness is not admitted solely on an old historical certificate.

These are required future acceptance cases, not scientific tests run now. Approval gates remain exact return/horizon conventions, forecast-error versus estimation uncertainty, all estimation timelines, estimator/diagnostic details and bounded numerical reference cases. P3 produces forecasts and attribution; it never chooses positions.
