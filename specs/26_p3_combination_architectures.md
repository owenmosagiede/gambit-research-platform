# 26 — P3 flat and hierarchical forecast-combination architectures

Design contract **P3COMB_ARCHITECTURES@1.0.0**, 27 November 2026.
The user requested six additional architectures alongside the existing P3 method
and explicitly selected the same named method at both hierarchical levels:
equal/equal, error/error and ridge/ridge. Family membership is assigned manually
by the user. **Specification only: no combination engine, family assignments,
registry policy, production forecast or trading decision is installed here.**

This amendment supersedes the blanket prohibition on family forecasts and equal
weighting in [07](07_p3_forecasting.md) for these explicitly selected methods.
The [preserved source design](references/p3_p4_design_reference.txt) remains
unchanged as historical evidence; its original flat covariance-aware method
remains available. Individual calibration and the TS/CS basket rules in
[25](25_p3_ts_cs_calibration.md) apply before every architecture.

## 1. Architecture catalogue

Identifiers below are logical specification names, not installed registry IDs.
Choosing an architecture pins its exact version and full fit policy.

| Display name | Architecture ID | Within-family stage | Final stage | Manual families required? |
| --- | --- | --- | --- | --- |
| Existing flat covariance-aware combination | `FLAT_CGLS_SHRINKAGE_V1` | None | Existing constrained GLS with shrinkage forecast-error covariance across all individual forecasts | No |
| Flat equal weight | `FLAT_EQUAL_V1` | None | Equal weights across all individual forecasts | No |
| Flat error weighted | `FLAT_INVERSE_MSE_V1` | None | Inverse historical forecast MSE across all individual forecasts | No |
| Flat ridge | `FLAT_RIDGE_SIMPLEX_V1` | None | Ridge combination of all individual forecasts | No |
| Hierarchical equal weight | `HIER_EQUAL_V1` | Equal weights across signals in each family | Equal weights across family forecasts | Yes |
| Hierarchical error weighted | `HIER_INVERSE_MSE_V1` | Inverse forecast MSE across signals in each family | Inverse historical **family-forecast** MSE across families | Yes |
| Hierarchical ridge | `HIER_RIDGE_SIMPLEX_V1` | Ridge combination of signals in each family | Ridge combination of family forecasts | Yes |

The existing method remains the retained default for configuration compatibility;
this catalogue neither activates it nor automatically changes a live method.
The six additions are explicit alternatives, not fallbacks for a failed solve.
One request selects one architecture. Comparing all seven creates seven distinct
P3 model identities; it does not average their outputs into an eighth model.

## 2. Common inputs and boundary

Each combination group is one instrument/member, exact Target return basis,
validated horizon quantity/clock and forecast cutoff. Its leaves are individually
calibrated, readiness-checked `FULL_TARGET_RETURN` forecasts after the selected
decay rule. TS and CS use the same boundary. Relative-only CS diagnostics and
raw scores cannot enter any flat or family combiner.

Freeze the ordered leaf roster, architecture, fitting policy, compatible history
and, where required, family mapping before evaluation-label access. Deduplicate
the same scientific forecast identity so retries cannot buy another vote.
Genuinely different validated TS/CS/Scope relationships remain separate leaves
with their dependencies visible. A family contains only leaves in this exact
combination group; it never averages different pairs, Targets or horizons.

All methods keep the existing P3 convex-weight convention at every node:
`w_j >= 0` and `sum_j w_j = 1`. The ridge variants are therefore explicitly
**simplex-constrained ridge**, not unconstrained regression with negative weights,
leverage or a new fitted intercept. Such alternatives need their own architecture
identity; a generic library's default Ridge/RidgeCV call is not this contract.
The input forecasts already have economic units and calibrated intercepts.

## 3. User-maintained family metadata

Family assignment is an explicit, immutable, versioned user-owned mapping:

`parent SIGNAL/Feature reference -> one primary family_id`

It is not inferred from recipe names, return correlations, country/pair labels,
P1/P2 outcomes, clusters, an agent's judgement or a missing-value fallback. This
task does not invent or populate families. A user may maintain additional tags,
but version 1 uses exactly one primary family per parent for combination.
All that parent's tested relationships inherit its primary family; research
identities and validation evidence remain unchanged.

Required FamilyMapping fields are mapping ID/version/content hash, explicit
parent references, stable family IDs, user actor/approval evidence,
recorded availability/decision time, effective-from time and supersession refs.
Keep both decision availability and effective time: a backdated effective date
does not make a later assignment historically known. A new assignment/removal
or reassignment produces a new mapping version with old bytes retained. Family
display labels live in separately versioned presentation metadata. Renaming a
family preserves its stable ID, numerical mapping identity and fitted weights.

For a hierarchical request, every selected leaf must resolve to exactly one
user-assigned primary family. Missing, conflicting or multiply assigned entries
block that hierarchical model. Do not create an `Other` family, ask an agent to
guess, silently drop the signal or switch to a flat method. Flat numerical fits
remain available without family metadata; optional family reporting does not
change their coefficients or scientific numerical identity.

For a given leaf roster, active families are precisely its nonempty mapped
groups. Families existing elsewhere in the library do not receive empty or zero
forecasts. An explicitly required active family with no eligible leaves is an
invalid roster. Store the complete leaf-to-family partition with each fit.

A changed numerical mapping invalidates affected hierarchical fits, family histories and
downstream forecasts, not old P1/P2 results or the underlying individual fits.
Flat attribution metadata can acquire a new referenced view without changing
its numerical fit. A mapping chosen after inspecting returns is exposed model
design; retrospective replay using it is selection-conditional, not an ex-ante
historical family forecast. Genuine historical error rows require the mapping
and all decisions to have been available at their recorded issue cutoff.

## 4. Shared node estimators

Let `f_s,j` be input forecast j **as issued at historical decision s**, `y_s` the
exact realised Target, and `e_s,j = y_s - f_s,j`. Historical input forecasts must
be from mature-only fits, with original decay/basket/calibration versions. All
estimated methods at a node use the same complete historical anchor set across
its frozen children; no pairwise deletion, in-sample fitted residual substitution
or different sample per child is permitted.

### Equal weight

For `K` children, `w_j = 1/K` and `F_t = sum_j w_j*f_t,j`.
Equal weighting needs valid current children and an explicit roster, but no
estimated weight history. Missing error history blocks associated precision or
uncertainty outputs; it never fabricates a variance or admits an unready forecast
to P4. A single child receives weight 1 by definition.

### Error weighted: inverse mean squared forecast error

`MSE_j = mean_s e_s,j^2`

`w_j = (1/MSE_j) / sum_k (1/MSE_k)`

This uses squared full-return forecast errors, including bias and basket errors;
it is not inverse signed error, inverse standard deviation, error variance alone,
IC, Sharpe or the existing full-covariance GLS method. MSE has unit `U^2`; weights
are dimensionless. Date weights are equal over the common eligible history.

All MSEs must be finite and nonnegative. If exactly `Z > 0` children have exactly
zero MSE, those receive `1/Z` each and others zero, the equal-rate limit of inverse
MSE weights as a common positive error floor tends to zero. Record this defined
`EXACT_ZERO_MSE` branch; it is not proof that future error is zero. No hidden
epsilon, near-zero rounding, concentration cap or zero-fill is implied. A future
floor/cap requires a separately pinned policy. Absent history is unavailable,
not zero MSE. Preserve concentration and common-error diagnostics because this
method does not account for off-diagonal dependence when choosing weights.

### Ridge: penalised squared error on the simplex

Fit the children against the same exact Target:

`min_w mean_s (y_s - sum_j w_j*f_s,j)^2 / scale_y^2 + lambda*sum_j w_j^2`

subject to `w_j >= 0`, `sum_j w_j = 1`, with strictly positive finite `lambda`.
Here `scale_y^2 = mean_s y_s^2` from that node's training fold only; zero or
nonfinite scale blocks the fit. The common scaling makes lambda dimensionless
and invariant to a common return-unit rescale. Do not separately z-score the
forecast columns, change their economic intercepts, add an intercept or mix
Target representations. Under the simplex, shrinking toward zero coefficients
is equivalent up to a constant to shrinking toward equal coefficients.

Lambda is selected from a positive finite grid frozen in CombinationPolicy using
nested chronological rolling-origin folds. The grid, training/refit windows,
fold dates, mature-label purging, minimum effective intervals, tie rule and solver
tolerances are required policy fields; no numerical library defaults are silently
adopted. The mean validation squared error is the selection loss, with the same
Target scaling; exact loss ties choose the larger lambda, then stable candidate
order. Every fold's scale is computed from its training labels, never the full
sample. Random row splits, shuffled K-fold, default leave-one-out/GCV and tuning
on the final architecture-comparison window are forbidden. A fixed positive
lambda may be used only by a distinctly pinned fixed-lambda policy.

This defines the ridge architecture without claiming that a grid/solver or
weight-estimation timeline has been scientifically selected. Those concrete
CombinationPolicy values and numerical engine acceptance remain implementation
gates under 07; the calibration defaults in 25 do not implicitly select them.

## 5. Flat and hierarchical execution

Flat methods run one node on all individual full-return forecasts. The existing
GLS method retains its own shrinkage covariance/solver requirements; inverse MSE
and ridge are distinct alternatives rather than new labels for it.

For hierarchical methods, partition the leaves by the frozen manual mapping.
For family `g`, fit/apply its selected method to obtain within-family weights
`u_g,j` and a family forecast `F_g,t = sum_{j in g} u_g,j*f_j,t`.
Then apply the **same method** across family forecasts to obtain weights `v_g`:

`F_t = sum_g v_g*F_g,t`

`effective_leaf_weight_j = v_family(j)*u_family(j),j`

For hierarchical equal weight, with `G` active families and `n_g` leaves in family
g, the final leaf weight is `1/(G*n_g)`. Flat equal instead gives `1/N_leaves`.
A family with more signals therefore does not receive extra top-level equal
weight solely because it has more members. Error and ridge variants estimate
both levels independently by their named estimator; there is no equal-weight
inner stage hidden inside either hierarchical variant.

For outer error weighting, `MSE_g` is measured from historical **family forecasts
as issued**, not the mean or sum of the member MSEs. For outer ridge, design
columns are those historical family forecasts, not current-weight reconstructions
of old member histories. Within-family ridge lambdas may differ by family, and
outer lambda is selected separately; all selected values and folds are pinned.

At historical s each family forecast must have been formed using only decisions,
inner fits and matured labels available before s. An outer training row becomes
eligible only after that row's Target label matures before the outer fit cutoff.
During outer lambda evaluation, recreate or resolve each family's causal vintage
using no label at/after its issue cutoff, including inner hyperparameter choices.
The current final output may use current inner fits, but outer fitting/evaluation
must not use today's inner weights to repaint historical family predictions.
This nesting rule applies to error/error as well as ridge/ridge; equal/equal
still records its historical roster/mapping vintages.

## 6. Basket components, dependence and attribution

Every leaf contains its full calibrated return, with the baseline/relative split
from 25. Neither a family node nor the outer node adds a basket again. The product
leaf weights are nonnegative and sum to one. A shared baseline contributes
`sum_j effective_leaf_weight_j * leaf_baseline_contribution_j`; with identical
undecayed baseline B in all leaves it contributes B once. If leaf decay or
providers differ, preserve their actual contributions instead of asserting B.
Any later approved basket/factor handling must enter the leaf's calibration
contract and error history, not become an extra family or a synthetic signal vote.

Retain original leaves, calibrations, family rosters, inner/outer fits and weights,
effective leaf weights, baseline/relative contributions, age/decay and exclusions.
Hierarchical grouping is an optional combination layer, not replacement or loss
of individual Signal evidence. A zero weight does not erase a member.

For a fixed weight vintage let c be the final effective leaf-weight vector and
Sigma_e their full-error covariance. Combined forecast-error variance is
`c' Sigma_e c`, including cross-family and shared-basket covariance. Equivalently
family error covariance uses the actual inner weight matrix for that vintage.
For historically changing weights, evaluate the realised combined errors of the
actual issued forecasts; do not apply today's weights to certify old uncertainty.
No model may treat family errors as independent or divide risk by the number
of families without evidence. Preserve forecast-error versus estimation-risk
typing and the still-open P4 `Omega_alpha` bridge.

## 7. Persistence, comparison and failure

Required CombinationPolicy content: architecture ID/version, compatibility key,
ordered leaf roster, current/history missing-data rules, estimator and weight
constraints, complete history selection/maturity/exposure/refit rules, required
evidence thresholds, manual mapping ref when hierarchical, node/solver/tuning
policies, uncertainty policy and implementation. FamilyForecast records reference
their exact child outputs, mapping, node fit and contributions. Final forecasts
reference architecture, full tree, original leaves, all fits/weights, target/clock,
error-history and dependency refs and readiness/blockers.

The default roster policy is strict: a required child missing/invalid at forecast
time blocks that model, including an emptied family. A separately versioned
roster-change policy may explicitly create a new identity; no silent dropping,
renormalisation, zero forecast, auto-family or automatic architecture substitution
is permitted. Bad lambda/grid, unavailable causal family vintages, insufficient
complete history, invalid covariance or failed numerical solve remains a typed
blocker. Equal weighting is valid only when explicitly selected, never an implicit
fallback after an error/ridge/GLS failure.

Compare architectures on frozen common eligibility, exact Targets/horizons and
cutoffs, with shared evaluation/exposure rules. Preserve all results, eligible
forecast counts and missingness; an architecture lacking evidence is unavailable,
not a losing zero-return strategy. A best retrospective score does not choose a
live architecture automatically or create a new P2 certificate. Architecture,
family-mapping and lambda searches are model-selection exposure and require a
separate forward evaluation before claiming unseen performance. Do not change
the P3/P4 interface or allocate positions as part of this comparison.

## 8. Required bounded acceptance cases

1. Signals `[0.01,0.02,0.04]` give flat equal `7/300`. Families A containing the
   first two and B containing the third give hierarchical equal `0.0275`, with
   leaf weights `[1/4,1/4,1/2]`; the two equal architectures must remain distinct.
2. Child MSEs `[1,4] U^2` give weights `[4/5,1/5]`. Missing error history is not
   MSE zero. Exact zero MSEs `[0,0,4]` follow the documented `[1/2,1/2,0]` rule.
3. Errors `[1,-1]` and `[-1,1]` in an equal family have child MSEs 1 and 1 but
   family-forecast MSE 0. Outer error weighting must use the latter vintage, not
   infer its error by averaging child MSEs. Future error remains uncertain.
4. A two-child ridge fixture with forecasts `[0,1]` on two dates, labels `[0,1]`,
   scale squared `1/2` and lambda 1 has simplex optimum `[1/2,1/2]`, objective 1.
   With both labels 1, scale squared 1 and lambda 1, weights are `[1/3,2/3]`,
   objective `2/3`. Test the actual constrained solution, not a normalised
   unconstrained library fit. These fixtures illustrate fixed lambda, not tuning.
5. Both hierarchical ridge levels and both error-weighted levels use the named
   method. Nested product weights sum to one and reconstruct the saved final
   forecast and all original leaf contributions, including zeros.
6. A shared +1% basket contribution remains +1% under either flat or nested
   weights summing to one before decay. Heterogeneous leaf decay/provider
   contributions follow the actual product weights and preserve covariance.
7. A hierarchical model with an unmapped, conflicting or multiply assigned parent
   blocks; a flat model works numerically without the mapping. Only a user-owned
   new mapping version can change the partition; no original research ID changes.
8. A mapping assigned after a historical forecast's cutoff is unavailable to that
   genuine vintage, even if its effective date is backdated. Conditional replay
   preserves the later decision/exposure evidence and is not an ex-ante issue.
9. A late/immature label or future-fit inner family prediction cannot enter an
   outer fit. Replacing causal family histories with today-refitted histories
   fails provenance checks, even if it improves outer MSE or selected lambda.
10. Zero/nonfinite ridge scale, nonpositive lambda, missing folds or unknown solver
    tolerances block fitting. A common percentage/fraction rescale leaves valid
    ridge weights unchanged; separate column normalisation is incompatible.
11. Mixed pair/Target/horizon/clock, unavailable relative-only CS output, duplicate
    forecast identity or a missing required child never becomes a valid family
    forecast. A declared active empty family cannot receive a zero substitute.
12. A two-family covariance matrix with diagonal `[1,1]` and covariance 1 gives
    equal-family combined variance 1, not 1/2. Family labels do not create
    independent observations, independent alpha or additional validation passes.

These are future engine acceptance cases and bounded synthetic arithmetic,
not implemented algorithms or empirical architecture comparisons.

## 9. Sources and remaining implementation gates

The user's six architectures and explicit same-method-at-both-levels decision
authorize this extension to the original flat-only design. Manual assignment is
the user's requirement; versioning/provenance, inverse-MSE semantics and the
simplex ridge convention are explicit specification decisions. The familiar
squared-error plus L2 ridge objective is documented in the
[Ridge reference](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html);
our simplex, scaling and chronological nesting are additional declared contract
requirements, not that library's defaults or a selected implementation.

Remaining gates include user-supplied actual family metadata, registered closed
policies/schemas, concrete weight-history/fold/lambda/solver settings, causal
family-history generation, covariance/uncertainty methods, isolated numerical
and integration tests and controlled implementation/release. No new production
research, family inference, policy registration or deployment occurs here.
