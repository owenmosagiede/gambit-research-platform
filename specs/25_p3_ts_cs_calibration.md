# 25 — P3 TS/CS return calibration and basket baseline

Design contract **P3CAL_TS_CS_RETURN@1.0.0**, defined 27 November 2026 in response
to the user's request to finish the TS/CS calibration and basket design.
**Specification only: no engine, registry policy, data migration, forecast or
production certification is installed by this change.** This contract resolves
the calibration geometry and the bounded default estimation profile below. It
amends the calibration clauses of [07](07_p3_forecasting.md), not P1/P2 decisions,
their historical identities, the preserved source reference, or P4's mandate.
Other P3 decay, dependence, solver and uncertainty-estimator gates remain explicit.

## 1. One output meaning

TS and CS must reach the same `FULL_TARGET_RETURN` contract before P3 combination:

`instrument + exact Target + horizon quantity/clock + forecast cutoff -> expected return in Target unit U`

Matching requires the same orientation, entry/exit convention, return
representation, funding/capital convention, availability regime and eligible
forecast time. Target IDs may be instrument-specific; economic conventions must
match explicitly. A 7-scheduled-weekday decimal Spot forecast is not a
21-calendar-day forecast, a percentage value, or a Modelled Total Return forecast.
No annualisation, horizon interpolation, Spot-to-TR conversion or price-return
approximation occurs in P3. Each actual instrument Target remains referenced.

P2 owns predictive relationship validation. P3 owns the magnitude mapping and its
estimation/evaluation evidence. Rank IC is not a return coefficient. P3 cannot
replace a failed P2 relationship, flip its validated direction, expand its Scope,
or claim that calibration establishes new predictive certification.

## 2. The two calibration routes

### TS: calibrate directly to the full Target

For one exact relationship, orient its PIT score by its frozen P2 direction:
`x = direction * score`, where direction is +1 or -1. On the eligible training
sample calculate `x_mean`, population `x_sd`, `y_mean` and
`z = (x - x_mean) / x_sd`. Keep those fit statistics fixed until the next refit.

Fit an intercept and one slope by equal-anchor-weight ordinary least squares:

`b = mean[z * (y - y_mean)] / mean[z^2]`

`mu_TS(t) = y_mean + b * z_current(t)`

The version-1 mapping has no winsorisation, score clipping, ridge penalty,
member pooling or outcome-selected hyperparameters. `b <= 0`, zero/nonfinite
score scale or insufficient evidence blocks the fit; do not reverse the frozen
direction or silently replace the signal with an intercept-only forecast.
An observed current `z = 0` legitimately forecasts the intercept.

This is already a full-return forecast. Its fitted intercept is part of its
calibration. A basket forecast is never appended to it.

### CS: calibrate relative returns, then reconstruct full Target returns

Bind the P2-validated fixed Scope, its ordered members, exact Target per member
and the chosen baseline provider before reading calibration labels. Version 1
supports a fixed universe of at least three members with equal reference weights
`w_i = 1/N`. These are calibration reference weights, not P4 trading weights.
Unequal/dynamic weights or dynamic membership require a distinct calibration
policy and compatible upstream evidence; there is no automatic renormalisation.

At each complete historical anchor `s`, define:

`B_s = sum_i w_i * y_i,s`

`u_i,s = y_i,s - B_s`

Orient the scores by frozen direction, use ascending midranks for ties and define
`q_i,s = 2 * (rank_i,s - 1) / (N - 1) - 1`.
Equal weights imply `sum_i w_i*q_i,s = 0` and
`sum_i w_i*u_i,s = 0`. A tied observation's zero is defined, not imputed.

Fit one shared relationship slope, with each anchor carrying equal total weight:

`b_CS = mean_s[sum_i w_i*q_i,s*u_i,s] / mean_s[sum_i w_i*q_i,s^2]`

`a_i,t = b_CS*q_i,t`

`mu_CS,i,t = B_hat_t + a_i,t`

There are no member intercepts, per-date future intercepts, beta estimates or
cross-sectional z-score/outcome tuning. Nonpositive `b_CS` or zero aggregate rank
dispersion blocks the fit. A current all-tied cross section legitimately has
`a_i,t = 0` for every member and carries `NO_CURRENT_CS_DISPERSION`; it does not
supply asset-selection information. It still needs a valid baseline provider.

Subtracting the same `B_s` from every member preserves Target ranks, so this
mapping is compatible with the existing full-return Spearman-IC relationship.
Subtracting member-specific factor loadings generally changes ranks and is not
covered by that certificate. Neither a CS pass nor a pooled magnitude fit creates
an individually P2-validated TS relationship for every member.

## 3. What the basket actually is

`B` is the arithmetic mean of the Scope members' exact horizon Target returns.
For simple-return Targets it corresponds to fixed initial equal-weight leg
exposures over that horizon, not a daily rebalanced index. For other return
representations it is a declared statistical mean, not automatically the return
of an investable portfolio. Version 1's executable-profile proposal below is
bounded to the current simple-return FX family.

Every basket definition pins member order, weights, member Target versions,
orientation, horizon, anchor/endpoints, funding basis, capital convention and
availability policy. Modelled Total Return already includes its defined funding
component; it is not added a second time to either basket or member forecasts.

This is a cross-sectional mean decomposition, not a claim that all FX pairs have
unit sensitivity to an economic dollar factor. An AUDUSD/USDJPY mixture has
opposite dollar exposures; its arithmetic mean must never be labelled a pure
dollar index. Permitted comparisons preserve each member's declared quotation.
For a currency-basket economic interpretation, require a separately defined
common-numeraire Scope and exact registered Targets before P1/P2. P3 does not
negate a simple inverse return, infer untested crosses, enforce synthetic-price
triangles, or create a new currency mapping from pair labels.

## 4. Two explicit baseline providers

### Default: `HISTORICAL_BASKET_MEAN_V1`

`B_hat_t = mean_s B_s`, using the same complete, matured calibration anchors as
the CS slope. This is the pooled full-return regression's fitted intercept.
It estimates an unconditional baseline; it makes no claim to predict changing
risk appetite or the next dollar regime. It is not a new predictive Feature,
P2-validated Signal, separate combination vote, or a retrospective realised
future basket return. Zero may be the actual fitted value, but missing baseline
evidence is unavailable, never a fabricated zero.

This default makes TS and CS comparable in the same Target units without
requiring an extra basket-alpha model. Report the baseline and relative
contributions separately so consumers can see precisely what is forecast.

### Optional: `VALIDATED_BASKET_FORECAST_V1`

To predict the basket conditionally, require a separately defined basket Target
whose realised labels exactly equal `B_s`, plus its Scope, fixed constituents,
readiness and an exact P2-validated **TS basket relationship** at the same horizon.
P3 calibrates that relationship with the TS route above and requests its full
return forecast at cutoff `t`. The basket output becomes `B_hat_t` for the CS
reconstruction. The basket registration/research is separate work; a member's TS
pass or the CS rank pass is not a basket-validation certificate.

The provider may consume only a full-return basket forecast, not a relative CS
forecast that recursively needs the same baseline. Dependency cycles are invalid.
The selection of provider is frozen in the policy/forecast request before
evaluation outcomes; changing provider creates a new fit/forecast lineage.
If the chosen provider is missing, stale, incompatible or invalidated, full CS
output is blocked. A computed relative diagnostic can remain visible as
`RELATIVE_ONLY`, with no P4-eligible full forecast. No automatic switch to the
historical mean, zero, a realised basket return or an unrelated TS model occurs.

The provider's exact training and forecast records must be available before `t`.
The CS slope never trains on future provider forecasts. Its residual labels stay
the identity `u = y - B`, not `y - B_hat`; baseline forecast errors belong in the
full forecast error and its uncertainty.

## 5. Bounded calibration profile, information and timing

These are explicit version-1 design choices, not empirically optimal values or
registered production permissions. Any revision gets a new policy identity and
an exposure record, not a silent retry on the same evaluation window.

| Choice | Version-1 rule |
| --- | --- |
| Target profile | Current FX simple decimal Spot or Modelled Total Return; fit each exact basis separately. Horizons 1/7/21/63 scheduled weekdays only. Other clocks, representations and the 252 policy require their own versioned profile. |
| Fit cutoff | First scheduled Monday–Friday date of each UTC calendar month at 00:00 UTC; no holiday exclusion. Initial output waits for the first such cutoff at/after relationship and policy eligibility. |
| Label eligibility | Anchor in `[cutoff minus 60 calendar months, cutoff)`; label endpoint **and** label availability strictly before cutoff. Preserve reference dates and PIT feature values as available at the historical anchor. Calendar subtraction clamps a missing month-day to that month's last day. |
| Estimator | Univariate intercept OLS for TS; one equal-date-weighted pooled slope on centered ranks/residual returns for CS. No calibration regularisation in this bounded version. |
| Minimum evidence | At least 24 calendar months from earliest eligible anchor to fit cutoff; at least 20 maximum-cardinality non-overlapping Target intervals. CS counts common anchor intervals with nonzero rank dispersion, never `members x dates` as independent time observations. |
| Interval clock | Use actual pinned Target start/end intervals; greedy earliest-end selection, next start >= previous selected end, with stable anchor/ID tie breaks. Keep all eligible rows in the fit; the non-overlap subset supplies the sufficiency diagnostic only. |
| Full CS sample | All frozen members have valid PIT scores and compatible, matured labels at that anchor; otherwise omit the whole anchor with a reason. Current scores require the entire Scope; future labels are not required for current scoring. |
| Missing data | No score/label interpolation, zero filling, opportunistic member dropping or Scope shrinkage. An upstream approved held state retains its original source age; copying the row does not refresh it. |
| Refit/reuse | Use the latest eligible monthly fit until the next scheduled refit. A failed required refit blocks fresh full forecasts; do not quietly reuse an older fit. Each current forecast still checks fresh-score and provider readiness. |
| Evaluation | Freeze the mapping/profile first; preserve rolling-origin forecast versions with mature-only refits. Default P3 evaluation is forward shadow after policy and relationship eligibility, with each error recorded only after its label matures. |

Historical P1/P2 labels may be used for calibration only after their recorded
availability and any exposure-policy restrictions permit it; doing so is exposed
training, not an untouched holdout. A replay using relationships selected later
is labelled `SELECTION_CONDITIONAL_REPLAY`, even when its numerical fitting uses
past-only labels. It cannot become an ex-ante error record or a fresh P3 holdout.
No calibration score, slope or training window is selected from P3 evaluation
returns. Calendar coverage, missing-anchor reasons, effective N, distinct score
values and original source-update counts are persisted separately.

## 6. Combination, decay and one common contribution

Complete each constituent's return mapping before P3's existing constrained
combination. Only `FULL_TARGET_RETURN` values for the same instrument, exact
Target basis, horizon and decision cutoff enter the convex combination:

`mu_combined = sum_j v_j*mu_j`, with `v_j >= 0` and `sum_j v_j = 1`.

A TS forecast is not summed with a CS forecast. A shared basket provider is
context inside each reconstructed CS forecast, not another pair-forecast vote.
For multiple CS constituents with the same provider, the aggregate baseline
contribution before decay is `(sum_j v_j)*B_hat`, not `number_of_signals*B_hat`.
TS fitted intercepts remain attributed to their own calibration. Baseline
contributions must add exactly to each full forecast and to its final weight.
Different CS Scopes/providers can contribute only after each produces the same
member Target output; retain each context separately in attribution.

The source design's whole-forecast decay remains unchanged: under an approved
decay policy apply `d_j(age_j)` once to `mu_j`, replay it historically and record
both baseline and relative components multiplied by that same `d_j`. After
combination a shared CS baseline contributes `sum_j v_j*d_j*B_hat`; it is not
claimed to remain exactly `B_hat` when decay differs. The CS age is the age of
the scoped signal under its pinned freshness policy, not an arbitrary member's
release date. Request the provider's readiness-checked **undecayed calibration
value** before applying this whole-constituent decay; a provider already aged
under a separate policy is incompatible without a defined joint rule. This
preserves the source's whole-forecast decay and can attenuate its baseline along
with the relative component. Component-specific decay remains a distinct future
policy, not a hidden change to the preserved P3 design.

Fit the existing forecast-error dependence system on each **full reconstructed**
forecast, not on a mixture of full TS errors and relative CS errors. The
constituent roster retains the common-provider dependency. CS basket context
does not grant additional independent signal count or family weight.

## 7. Error and uncertainty semantics

`e_TS = y - mu_TS`

`e_CS,i = (B - B_hat) + (u_i - a_i)`

Consequently `Var(e_CS,i) = Var(e_B) + Var(e_relative,i) + 2*Cov(e_B,e_relative,i)`.
Shared baseline error creates cross-member and cross-signal dependence; it never
diversifies away merely because several CS signals reference the same provider.
Preserve full joint error histories. In-sample residuals from the final fit are
not historical forecasts and cannot masquerade as forecast-error histories.

Return estimates are in `U`, all error covariance entries in `U^2`. Record the
type and provenance of forecast-error variance separately from parameter/mean
estimation uncertainty. This contract does **not** equate `v' Sigma_error v`
with P4's `Omega_alpha`. The latter's estimator and the complete P3 covariance
and combination numerical policies remain the gates in 07/08; this calibration
definition does not supply invented uncertainty values or production readiness.

## 8. Persistent contracts and data requirements

Use immutable content-addressed manifests and shared payloads under the existing
store conventions. This change defines logical objects, not a new authority or
an installed schema. Before an engine is released its closed validators must
implement these required fields and reject unknown/incompatible modes.

| Object | Required content |
| --- | --- |
| CalibrationPolicy | ID/version/hash, mapping mode, exact Target profile, rank/tie/normalisation rules, estimator, sign constraint, sample/fit/refit/maturity rules, minimum evidence, missing/Scope rules, chosen provider mode, exposure/evaluation policy and implementation. |
| BasketDefinition | Immutable Scope and member order, equal fixed weights, exact member Target refs, Target basis/representation/capital/funding/orientation, horizon and availability contracts; optional registered basket Target ref. |
| CalibrationFit | Relationship and P2 evidence, policy, fit cutoff, source/Target payload refs, eligible/excluded anchors, actual intervals/effective N, exposure, TS mean/scale/intercept/slope or CS rank slope and historical basket mean, provider identity and implementation. |
| BasketContextForecast | Definition and provider mode, cutoff, horizon, baseline value or unavailable reason, historical-mean fit ref or exact eligible basket relationship/forecast ref, freshness, uncertainty type/status, shared dependency identity. No separate pair-signal vote. |
| SignalForecast | Original exact relationship/member, output kind (`FULL_TARGET_RETURN` or diagnostic `RELATIVE_ONLY`), cutoff, Target/horizon/unit, fit and current-score refs, frozen direction, baseline and relative contributions, provider ref, fresh full value, decay policy/age and decayed contributions, readiness/exposure and typed uncertainty/blockers. |
| InstrumentHorizonForecast | Existing 07 fields plus matching full-target roster, per-constituent weights/contributions and shared-provider attribution; retain omitted relative-only diagnostics outside the eligible roster. |

TS needs its PIT score history, exact Target labels and their availability. CS
additionally needs synchronized complete Scope scores and Target histories,
membership/orientation evidence and a BasketDefinition. The default baseline
uses those same labels; no extra live data feed is needed merely to compute the
historical mean. A conditional basket forecaster additionally needs its own
registered Target, predictive data, P1/P2 evidence and eligible current forecast.
The current imported macro adapter remains TS-only; this specification does not
silently broadcast its pair series into a CS universe or certify a new adapter.

## 9. Failure, invalidation and acceptance

Structured blockers distinguish incompatible Target/units/clock, invalid or
changed Scope, missing orientation, immature labels, insufficient history,
nonpositive calibration slope, unavailable current scores, missing basket
provider, cyclic dependencies and integrity failures. Never repair these by
reusing a different target, flipping a sign, shrinking the universe or supplying
a zero/full-ready forecast. Retain all failed attempts and diagnostics.

Changing weights, member order/membership, quotation, Target, horizon, provider,
fit cutoff, policy, input bytes or readiness invalidates affected fits/forecasts
and descendants, not old immutable artifacts. A new current score creates a new
forecast, not a rewrite of its fit. Withdrawn P2/provider eligibility withdraws
dependent full forecasts; unrelated valid forecasts remain reusable.

Required bounded reference cases before engine release:

1. Basket -1%, relative +0.4% gives a **full -0.6%** forecast; ranking is not an
   absolute positive-return claim. Future realised basket labels cannot supply
   the current baseline.
2. Three equal-weight ranks `[-1,0,1]`, realised returns `[-0.014,-0.010,-0.006]`
   give `B=-0.010`, residuals `[-0.004,0,0.004]`, `b_CS=0.004`; positive slope
   survives a common additive shift to all labels. The shifted baseline, not
   relative alpha, changes by that shift.
3. Historical basket means `[-0.020,0,0.010]` give baseline `-0.010/3`, proving the
   provider is an estimated return value, not an unconditional zero convention.
4. TS +1.0% and reconstructed CS +1.4%, weighted 50/50, give +1.2%. No extra
   basket is added. A shared +1% baseline across two CS signals contributes +1%
   under weights summing to one before decay, not +2%.
5. Equal raw scores use midranks; an all-tied current cross section has zero
   relative contributions. Globally zero training dispersion blocks fitting.
6. A negative validated direction is applied before TS scaling/CS ranking; a
   nonpositive oriented calibration slope blocks rather than reversing it.
7. A missing member drops the entire historical CS anchor; a missing current
   member blocks current scoring. Changing membership/weights changes identity.
8. Endpoint or label availability equal to the fit cutoff is ineligible. A
   21-weekday label crossing that cutoff cannot enter a 1-weekday fit by reuse.
9. Twenty non-overlapping common intervals across 30 members count as twenty
   temporal observations, not six hundred. An insufficient sample stays blocked.
10. Basket error variance 4, relative variance 9 and covariance -2 (all in `U^2`)
    give full error variance 9, not 13. Persist shared-provider cross-covariance.
11. Spot/TR, percent/fraction, quote inversions and different clocks cannot mix.
    Missing or invalidated conditional provider blocks full CS output without
    changing the provider choice or admitting the relative diagnostic to P4.
12. Historical fits with a future-selected roster are exposure-labelled replay.
    They cannot be presented as forecasts issued before P2/policy eligibility.

Synthetic arithmetic examples establish these contract identities, not empirical
forecast skill, a completed CS experiment, implementation parity or live readiness.

## 10. Evidence and remaining boundaries

The [preserved design](references/p3_p4_design_reference.txt) supplies individual
return calibration before constrained forecast combination. The distinction
between relative selection and common market exposure is supported by
[Goyal and Jegadeesh (2018)](https://doi.org/10.1093/RFS/HHX131); it does not select
our particular estimator, basket or numeric sample thresholds. Past-only
rolling-origin evaluation follows the principle described by
[Hyndman and Athanasopoulos](https://otexts.com/fpp3/tscv.html). The version-1
defaults here are explicit engineering/research design choices for review and
implementation, not claims that either source validated Gambit's parameters.

This closes the TS/CS calibration and baseline-definition gap. Remaining P3
implementation work includes closed object/schema validators, exact estimators
and reproducibility fixtures, relationship/readiness adapters, independently
specified decay, covariance/shrinkage/solver tolerances, the P4 estimation-risk
bridge, isolated end-to-end tests and controlled release. Current production
research and the separately gated PR52 release are unaffected.
