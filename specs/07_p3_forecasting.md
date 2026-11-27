# 07 — P3 individual forecasting and combination

Status: **review draft with explicit scientific gates; no canonical P3 engine implemented**. The TS/CS calibration and basket-baseline contract is now defined in [25](25_p3_ts_cs_calibration.md); its bounded version-1 defaults are specification choices, not installed production policies or empirical certification. The user's additional flat/hierarchical architectures and manual family mapping are defined in [26](26_p3_combination_architectures.md), explicitly amending the original flat-only combination requirement. Dependencies: [01](01_canonical_objects.md), [02](02_data_and_readiness.md), [03](03_features_targets_scopes.md), [06](06_p2_validation.md). The [preserved P3/P4 reference](references/p3_p4_design_reference.txt) remains the intended design. Source requirements below are distinguished from proposed interfaces; unresolved estimators are not filled with legacy defaults.

P3 also exists to measure each signal's incremental predictive value to the model containing it. That evidence is first-class derived Signal metadata and supplies the ranked Signal Library in [27](27_p3_incremental_value_and_library_ranking.md), separately from current forecast weights and additive return attribution.

## 1. Inputs and boundary

**Source requirement:** receive validated SignalHorizon relationships, historical PIT scores and exact Target returns, current available score, frozen Expected Direction, validation evidence, availability timestamps and upstream lineage. **Current identity decision:** each relationship references a parent `SIGNAL_X` through its Feature definition. Parent recipe identity excludes tested assets, Scope, Target/horizon, direction, Research Spec and period; those remain explicit relationship/trial context. An eligible roster contains relationship identities and their exact validation/certification evidence, not just parent IDs or a producer's run directory.

P3 admits only the exact relationship with valid P2 evidence and compatible readiness at its forecast cutoff. A library may display all tested relationships, but failed, unresolved, merely admitted and historical-unmapped relationships cannot enter P3. A 63-observation relationship is not a 7-observation forecast. For CS, bind validated Scope and membership/eligibility before score generation and forecast allocation to instrument members.

**Proposed input bundle:** eligible relationship roster, immutable scoped score/Target histories, current score references, forecast cutoff, pinned calibration/decay/dependence/combination policies and implementation manifest, required readiness evidence and applicable randomness. FamilyMapping is manually assigned by the user and required for hierarchical architectures in [26](26_p3_combination_architectures.md); it is optional for flat numerical combination. It never replaces constituent relationship identities or supplies scientific validation.

## 2. Permitted information set

Every historical forecast must be reproducible using only information available at its recorded cutoff. Predictor observations satisfy their PIT policy; a historical label may enter estimation only after its Target endpoint and availability requirements have matured. Preserve each fit cutoff, eligible training observations, refit time and live forecast cutoff separately. Replaying a final model across earlier history is not automatically valid forecast-error history.

**Calibration decision:** [25](25_p3_ts_cs_calibration.md) defines the version-1 TS/CS mapping, common Target units, historical-mean or independently validated basket provider, 60-month matured-label fitting window, monthly refits, sample requirements and forward evaluation/exposure rules. Implement and verify that contract before forecasting. **Remaining scientific gates:** decay-fitting, covariance-fitting and weight-estimation timelines and their exact numerical policies remain unresolved. Their windows, update frequency, holdout usage, label overlap/maturity treatment and exposure policy must be explicit before calculation. Retaining P1/P2 methods does not select a P3 estimator or authorize using an already examined validation window for tuning.

## 3. Source calculations and unresolved estimator choices

| Stage | Intended source requirement | Contract gate before implementation |
| --- | --- | --- |
| Individual calibration | TS maps directly to full Target return; CS maps centered ranks to relative return and reconstructs full return with one explicit baseline provider. Both use the exact Target economic units. | Mapping, estimator, fit/refit sample, minimum evidence, exposure and provider rules are defined in [25](25_p3_ts_cs_calibration.md); closed validators and numerical/adapter implementation remain required. |
| Decay | `d(0)=1`; decayed forecast is fresh forecast × `d(age)`; aging reduces predictive influence. Apply the same historical decay rule when calculating forecast errors. | Define age clock, defensible model, freshness eligibility and estimation timeline. Unsupported decay cannot become indefinite invented carry-forward. |
| Forecast-error histories | For compatible instrument × Target basis × horizon, error is realized Target return minus the historical constituent forecast. | Pin historical forecast versions, realized label availability, compatible sample alignment and treatment of missing/overlapping histories. |
| Dependence | Estimate a shrinkage covariance of constituent forecast errors, separate from market return covariance. | Approve estimator/shrinkage target, sample requirements, numerical tolerances and missing-history policy. |
| Combination | Retain flat constrained GLS with shrinkage error covariance; add the six flat/hierarchical equal, inverse-MSE and simplex-ridge alternatives in [26](26_p3_combination_architectures.md). | Freeze architecture, required user family mapping, weight-history/tuning/solver/missing-data policy. Equal weighting must be explicitly selected; it is never a fallback for another method. |
| Diagnostics | Preserve forecast dispersion, effective independent count, largest contributions, signal/family concentrations and decay contributions. | Define exact diagnostic formulas and units; do not invent a count/concentration metric to fill a field. |
| Incremental value | Compare full and causally refitted without-signal models on paired evaluation labels; preserve model-context incremental accuracy metadata and library ranking under [27](27_p3_incremental_value_and_library_ranking.md). | Pin removal/dependency/null rules, matched sample, evaluation/exposure/inference and ranking profile; unavailable evidence is unranked, not zero. |

Only compatible `FULL_TARGET_RETURN` constituents enter combination. A CS rank or `RELATIVE_ONLY` diagnostic is not a full forecast. Basket context is attributed inside the CS reconstruction, never appended to an already full TS forecast or entered as an additional pair-signal vote. Shared provider dependence remains in the full-return error histories; see [25](25_p3_ts_cs_calibration.md).

Every eligible constituent remains individually calibrated, represented and attributed, even with zero combination weight. Hierarchical architectures may explicitly form family forecasts after individual calibration, while retaining every original constituent and its effective final weight. User-owned family membership and declared architecture determine grouping; no family assignment is inferred automatically. Do not choose numerical weights from IC, Sharpe, family names or retrospective subjective preference.

### 3a. Available combination architectures

| Architecture | Individual/family stage | Final stage |
| --- | --- | --- |
| Existing flat covariance-aware | All individual forecasts remain separate | Constrained GLS using shrinkage forecast-error covariance |
| Flat equal weight | All individual forecasts remain separate | Equal weights |
| Flat error weighted | All individual forecasts remain separate | Inverse historical forecast MSE |
| Flat ridge | All individual forecasts remain separate | Simplex-constrained ridge |
| Hierarchical equal weight | Equal weights within each manually assigned family | Equal weights across family forecasts |
| Hierarchical error weighted | Inverse forecast MSE within each manually assigned family | Inverse historical family-forecast MSE across families |
| Hierarchical ridge | Simplex-constrained ridge within each manually assigned family | Simplex-constrained ridge across family forecasts |

The user explicitly chose the same named method at both hierarchical levels. The original method remains available; no new architecture is selected automatically. [26](26_p3_combination_architectures.md) defines exact formulae, manual FamilyMapping provenance, nested causal family-history requirements, missing-data behavior and acceptance cases. Its explicit alternatives supersede the original prohibition on family forecasts/equal weighting without altering the preserved reference text. All architectures retain the nonnegative, sum-to-one weight convention and combine compatible full-return forecasts.

### 3b. Incremental contribution and ranking

For each signal in each model, P3 evaluates a paired causal refit-ablation:
`incremental_MSE_gain = MSE_without_signal - MSE_full`, and the headline ranking score is
`100 * incremental_MSE_gain / MSE_without_signal`. Positive means the signal helped
out-of-sample predictive accuracy; negative means it hurt. A zero denominator makes
the percentage unavailable. Each result retains its exact model, architecture,
family mapping, removal unit, pair/Target/horizon, evaluation period and uncertainty.

The Signal Library ranks greatest to least by saved incremental contribution,
including zero and negative measured values. A versioned ranking profile selects
models and aggregates all applicable model-context scores with coverage shown;
missing/unevaluated contributions remain explicitly unranked. Weights, standalone
metrics and P2 validation never substitute for incremental value. Original per-signal,
family and shared-basket dependencies remain visible. [27](27_p3_incremental_value_and_library_ranking.md)
defines refitting, null references, non-additivity, grouped recipe ranking, temporal
exposure and the bounded read-only ranking projection. No automatic pruning,
weight adjustment, model switching or trade follows from the ranking.

## 4. Output units and shape

**Proposed interface:** a SignalForecast references one validated relationship, its parent, instrument/member, exact Target/horizon, forecast timestamp, score, calibration fit, fresh value, decay policy/age and resulting decayed value. InstrumentHorizonForecast contains the instrument, Target reference and economic basis, explicit horizon quantity/unit, cutoff/availability, expected return, typed uncertainty, exact architecture and constituent roster, original leaf and any within-family/across-family/effective weights/contributions, optional user FamilyMapping and FamilyForecast references, diagnostics, exclusions/blockers and complete lineage. Separate SignalIncrementalContribution records reference the model/forecast and full-versus-without-signal evaluation; RankingProfile/RankingSnapshot records supply model-context scores, coverage and ranks as derived Signal Library metadata. They are published after mature outcomes with their own availability timestamps, never retroactively inserted into issued forecasts. A field whose method is not approved is unavailable with a reason, not a fabricated zero.

For a Target whose canonical return unit is `U`, calibrated expected return and forecast error are in `U`, and forecast-error covariance/variance is in `U²`. If a standard deviation is displayed, it must be explicitly typed and converted from the appropriate variance. Source `w' Σe w` denotes a combination of forecast-error covariances; it is not automatically uncertainty of an estimated conditional expected return. **The relation to P4's expected-return-estimation covariance remains an explicit scientific gate.** No default spot basis, calendar horizon, percentage scale or interchangeable generic uncertainty scalar is selected here.

## 5. Validity and readiness

Verify exact relationship validation/certification, data/definition/policy/code fingerprints, required label maturity, Scope/member eligibility, matching return basis/horizon, known calibration/decay age semantics and approved history. Distinguish forecast availability from subsequent outcome availability. Covariance ordering must match the constituent roster and its mathematical/numerical validity checks. Historical-replay evidence does not establish live-generation capability; current batches still require their own checks.

Historical old `SIGNAL_*` records remain evidence. They become new eligible relationships only through explicit identity/provenance compatibility and certification; observed sign cannot supply missing ex ante direction. A valid parent or family alone never grants P3 eligibility.

## 6. Failure behavior

Unknown method/unit/timeline, unverified certificate, absent fit history, incompatible Target basis, stale score without defensible freshness/decay policy or invalid covariance yields a structured blocker. Preserve reason, affected relationship/group and input references. A contract/digest mismatch is an integrity failure; a solver failure is operational failure. Do not emit a zero forecast, equal weights, interpolated horizon or “ready” forecast as a fallback. If a policy later allows dropping constituents, record the exact permitted exclusion and recompute its identity; silent drops are prohibited.

## 7. Reuse and invalidation

Reuse fit/forecast artifacts only for identical scoped inputs, fitting policy, permitted information set, implementation and valid evidence. Parent recipe reuse does not imply identical scoped scores. A corrected target, changed validation decision, member set, decay rule, covariance fit or current score invalidates its affected forecast group and descendants. Retain unaffected valid work and all failed attempts. Display names, storage paths and retry identities do not change scientific meaning.

## 8. Persistence

Persist compact immutable fit manifests, individual forecast/error-history references, covariance/roster ordering, architecture and policy references, any user FamilyMapping/family forecasts and inner/outer/effective leaf weights, diagnostic definitions/evidence, source decisions and final forecast records. Large histories live once as referenced payloads. Record forecast versions as they existed before observing subsequent labels; later estimates never overwrite them. P3 attribution references parent and exact relationship IDs. Persist incremental full/reduced model evaluations and ranking snapshots separately with available-at times and immutable model/parent/removal references. The library reads authoritative evidence and does not become a second forecast or editable score store.

## 9. Acceptance scenarios

- A parent with validated 63-observation and failed 21-observation relationships supplies only 63-observation evidence; no 7-observation output is created.
- Different CS Scopes bind before score computation; changing Scope invalidates scoped scores while preserving the parent recipe identity.
- Two constituents in one family remain separately calibrated and attributed. Hierarchical equal weighting uses explicit family/leaf weights from 26; a label alone never changes validation or selects an architecture. Missing manual assignments block only architectures requiring them.
- Hierarchical error and ridge fit both levels causally; outer history uses original family forecast vintages, not today-refitted inner weights. All seven architecture outputs retain original-leaf and shared-basket attribution.
- A not-yet-matured label cannot influence any fit at an earlier cutoff; historical decay matches operational decay exactly.
- Unsupported stale carry-forward blocks; it does not create a fresh forecast with an invented decay coefficient.
- Weight/roster mismatch, missing covariance validity, missing uncertainty type or mixed economic bases fails validation.
- A new data batch without live readiness is not admitted solely on an old historical certificate.
- Full/without-signal refits share evaluation labels and causal fit cutoffs; hierarchical and basket dependencies cannot leak an ablated signal back into the counterfactual.
- The library ranks positive/zero/negative measured incremental value under a visible model profile; absent evidence receives no invented score, and later ranks cannot appear in earlier as-of metadata.

These are required future engine acceptance cases, not scientific tests run now. Specification [25](25_p3_ts_cs_calibration.md) supplies the calibration/baseline contract and bounded arithmetic reference cases. Specification [26](26_p3_combination_architectures.md) defines the additional combination architectures; [27](27_p3_incremental_value_and_library_ranking.md) defines incremental-value metadata and ranking. Other return families and horizon clocks, forecast-error versus estimation uncertainty, concrete decay/dependence/weight-history/tuning/solver policies, diagnostics and engine equivalence evidence remain gated. P3 produces forecasts and attribution; it never chooses positions.
