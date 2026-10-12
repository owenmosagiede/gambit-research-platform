# 08 — P4 trading-sleeve construction

Status: **review draft with explicit scientific gates; no optimizer implemented**. Dependencies: [01](01_canonical_objects.md), [02](02_data_and_readiness.md), [07](07_p3_forecasting.md), [09](09_p5_and_execution_boundary.md).

**User decision, 2026-10-08:** P4 constructs trading sleeves; P5 allocates shared capital. The [preserved P3/P4 reference](references/p3_p4_design_reference.txt) defines the intended P4 portfolio mathematics. Its portfolio is interpreted here as the sleeve being constructed under its mandate and explicit capital context. This ownership clarification does not select the still-unresolved P4/P5 feedback or aggregate-feasibility algorithm.

## 1. Inputs

P4 receives exact InstrumentHorizonForecast objects and attribution from eligible relationships, plus immutable snapshots/references for current positions, prices, market-return history/covariance, transaction costs, financing/carry, liquidity, sleeve mandate, venue profile and P5-issued allocated-capital/constraint context. Reference every input at its actual as-of state; a mutable account balance or bare file path is insufficient.

Mandate context includes applicable instrument/factor/gross/net/leverage/margin/shorting/liquidity/turnover/cash/venue restrictions and the risk/uncertainty preferences required by the source objective. Values are supplied by approved versioned context, not invented by research or optimized retrospectively against backtests. Forecasts contain neither capital nor permission to trade. P4 does not reassess scientific validation.

## 2. Permitted information set

The decision cutoff must bound forecast availability, prices, holdings/reconciliation state, market/cost observations and capital allocation state. Store each estimate's fit cutoff and the exact versions known then. Targets used to estimate forecast errors must already be mature. Distinguish estimate availability, intended decision time and potential execution time.

**Scientific gate:** approve exact estimation timelines for common-clock horizon errors/weights, market covariance and alpha estimation uncertainty. No live decision may use a later revised holdings, capital or risk snapshot. A changed capital allocation requires a new or explicitly revalidated sleeve decision; stale proposals are not final trades.

## 3. Source calculations and review gates

1. Convert independently validated horizon forecasts to a common economic rate and transform their uncertainty consistently. The source's `log(1 + expected_return_h) / h` is conceptual; exact return basis, mathematical interpretation, domain and horizon clock are not approved for all Targets. There is no default spot-return basis or calendar-day assumption.
2. Combine compatible horizon forecasts through precision/dependence weighting using shrinkage cross-horizon forecast-error covariance and nonnegative weights. Preserve horizon weights/contributions in InstrumentAlpha. No equal-horizon fallback or invented missing horizon is permitted. Exact objective, estimator, normalization and incomplete-history policy require a versioned decision.
3. Separately estimate market return covariance `Σ_market`. Do not substitute Signal/horizon forecast-error covariance for market risk.
4. Represent expected-return-estimation uncertainty in `Ω_alpha`. The relationship between this object and forecast-error variance is unresolved; they are not interchangeable merely because both are called uncertainty.
5. Solve the source's conceptual convex problem: maximize `x'μ − γ/2 x'Σ_market x − κ/2 x'Ω_alpha x − transaction_cost(Δx) − financing_cost(x)`, subject to the mandate. γ and κ come from the mandate. Do not add a second arbitrary uncertainty haircut to μ.
6. Apply mandate constraints within optimization. Translate economically chosen continuous targets to venue quantities afterward, preserving feasibility through approved rounding/reconciliation rules. No post-hoc scaling may be assumed to preserve minimum lots, margin or aggregate constraints.

**Still gated:** exact position units, rate/risk horizon alignment, convex cost/financing forms, covariance estimators, solver/tolerances, discrete-quantity treatment, failed-solve fallback and P4/P5 feedback. The equation above specifies intended structure, not an executable model or permission to invent coefficients.

## 4. Output units and shape

InstrumentAlpha references its exact forecast roster, common-rate unit/clock, expected alpha, typed alpha uncertainty, horizon weights/contributions and estimation lineage. A sleeve decision references mandate/venue, P5 allocation version, holdings/prices and every objective/constraint policy. Its TargetPosition and RequiredTrade records carry instrument, target weight/notional/executable quantity and explicit units, current position, required change, expected alpha, market-risk and uncertainty contributions, estimated transaction/financing costs, binding constraints and parent/relationship/horizon attribution.

At sleeve level preserve expected alpha/volatility, forecast-uncertainty exposure, gross/net/factor exposure, turnover, margin/constraint usage and costs in their declared units. A proposed result includes explicit feasibility status and blockers under the exact capital context. A RequiredTrade is not an authorized order; even locally feasible sleeve output cannot bypass P5 aggregate feasibility and execution authorization.

## 5. Validity and readiness

Require valid forecast and live-data evidence, consistent Target basis/common clock, matching instrument/covariance ordering, compatible units, current reconciled positions/capital, known cost/financing inputs, mandate applicability and venue rules. Verify both continuous and executable-quantity feasibility. Record aggregate-feasibility dependency separately: P4 local feasibility does not prove the shared pool can fund every sleeve.

The same forecasts can legitimately produce different sleeves under different mandates or capital contexts. P4 cannot silently change the forecast, P1/P2 methodology, expected direction or scope to achieve a preferred portfolio. Historical backtests are not live account readiness certificates.

## 6. Failure behavior

Missing common-clock or uncertainty semantics blocks portfolio construction. Stale holdings/capital, unknown costs, invalid covariance, conflicting mandates, solver failure, infeasible continuous solution or infeasible rounded quantities each retain structured failure/blocker evidence and the exact attempted context. No zero position, equal-weight portfolio or previous trade list is silently presented as a successful fresh solve. An approved future contingency policy must be explicit, versioned and separately visible.

## 7. Reuse and invalidation

Reuse horizon/risk estimates only under their pinned data and estimation policy; reuse complete sleeve targets only when forecasts, holdings, costs, mandate, venue, allocated capital and aggregate constraints remain valid. P5 reallocation invalidates affected sleeve feasibility even if forecasts are unchanged. Partial repair preserves unaffected estimates and failed attempts. New decision state does not overwrite the prior TargetPosition or RequiredTrade.

## 8. Persistence

Store immutable forecast/alpha, risk/uncertainty and cost references; capital/mandate/venue snapshots; objective/constraint manifests; solver and rounding diagnostics; local/aggregate feasibility references; target/trade proposals and full attribution. Shared matrices/history payloads are stored once and referenced. Parent Signal/library records do not become editable portfolio-state records. Order/fill/reconciliation history belongs to Execution.

## 9. Acceptance scenarios

- Identical forecasts with different approved sleeve mandates or capital allocations can produce different targets while retaining unchanged scientific forecast identities.
- A spot Target and an excess-return Target cannot be mixed under an unlabeled scalar; unsupported clock conversion blocks.
- Forecast-error covariance, alpha estimation covariance and market covariance retain different typed roles and compatible units.
- A continuous feasible target rounded to an invalid lot/margin state is not marked feasible; it requires approved correction or failure.
- P5 changes the allocation after P4 solves: the old proposal cannot be sent as current without revalidation/reconstruction.
- Two locally feasible sleeves that violate a shared aggregate constraint cannot proceed merely because each P4 succeeded.
- RequiredTrade without exact final allocation/feasibility/authorization context never reaches an order sender.

No numerical optimizer acceptance vector can be certified before the scientific and mandate/cost models are approved. P4/P5 responsibility is decided; their feedback, sequencing and final feasibility protocol remain the bounded ownership implementation gate in [09](09_p5_and_execution_boundary.md).
