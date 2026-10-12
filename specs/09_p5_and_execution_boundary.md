# 09 — P5 shared capital and execution boundary

Status: **review draft; ownership decided, allocation/feedback algorithm unresolved**. Dependencies: [00](00_system_boundaries.md), [01](01_canonical_objects.md), [08](08_p4_portfolios.md). No allocation engine, broker connector or order service is implemented.

## Decision and source boundary

**User decision, 2026-10-08:** P4 constructs trading sleeves and P5 allocates shared capital. The original foundation's ownership question is therefore partially resolved. P5 owns the shared-pool allocation and aggregate-capital/constraint context; P4 owns economically chosen, mandate-constrained sleeve positions under that context. Neither owner is allowed to infer an unapproved feedback/convergence algorithm from this division.

**Source requirement:** RequiredTrade is not order authorization. Research inputs never encode capital, positions, costs, mandate, venue or trading authority. Execution ultimately submits/reconciles orders only under separate explicit authority. **Proposed interfaces below** make ownership reviewable without inventing P5 mathematics or order policy.

## 1. Inputs

P5 receives versioned shared capital/account snapshots, reconciled holdings/commitments/reservations, aggregate constraints, eligible sleeve definitions and mandates, P4 proposals with exact capital assumptions, and any approved allocation policy. All participating sleeves and exclusions must be explicit; a missing sleeve is not assumed to have zero exposure. Record currency/valuation/availability basis for capital and aggregate exposures.

The Execution boundary receives the exact final RequiredTrade/proposal version, applicable sleeve and aggregate feasibility evidence, account/venue context, current reconciliation state and an independently issued execution authorization. The five research inputs cannot supply that authority. Executor credentials and provider secrets never enter scientific objects or documentation.

## 2. Permitted information set

An allocation decision binds the shared capital, outstanding commitments, holdings and constraints observed at a declared cutoff. Account state arriving after that cutoff cannot be silently substituted. Before execution, freshness/reconciliation requirements must be checked again according to an approved operational policy. Ambiguous order outcomes are reconciled before capital or position state is treated as final.

Exact freshness limits, reservation semantics and snapshot concurrency remain review gates. No timeout or inferred absence of a process proves that capital is free or an order was not executed.

## 3. Calculations and feedback gate

The division of responsibility is fixed, but **no allocation objective, risk budget formula, netting rule, leverage sharing rule, sleeve priority or iterative feedback/convergence method is selected here**. Those are explicit policy decisions still needed before P5 computation.

Any approved protocol must satisfy these interface invariants:

- A capital allocation has an immutable identity and names the shared pool, participating sleeves, budgets/constraints and the input state that supports it.
- Each P4 proposal states the allocation version and capital assumptions under which it is feasible.
- A changed P5 allocation invalidates affected P4 feasibility. P5 must request or verify a corresponding P4 reconstruction/revalidation, not silently scale a trade list and assume lot, liquidity, cost or margin feasibility survives.
- Final aggregate feasibility refers to the exact set of sleeve proposals and allocation state being considered; local feasibility alone is insufficient.
- A disagreement or non-convergent allocation/feedback cycle stays unresolved. No final trade authorization is implied by a provisional allocation or iteration.

Whether the protocol is sequential, iterative or jointly solved, how reservations prevent competing decisions, who publishes final aggregate feasibility, and how to reconcile netted/executable quantities remain open. These invariants do not prematurely select one algorithm.

## 4. Output units and shape

**Proposed P5 interface:** allocation decision/reference, shared-pool and snapshot identity, per-sleeve budget/constraint context with units, aggregate exposures/margin/capital usage, exact P4 proposal roster, feasibility evidence and unresolved conflicts. A policy-required field cannot be populated with a fictitious zero. Amounts explicitly state currency, notional/weight/executable basis and valuation cutoff.

**Execution interface:** immutable authorized intent links a RequiredTrade/proposal, final applicable allocation/feasibility context, authority/limits/expiry, account/venue, and client idempotency identity. Orders, acknowledgments, fills, cancellations and reconciliation records are separate operational evidence. An unknown exchange outcome is not a rejected order and not permission for a blind duplicate submission. Exact schemas/state transitions are future operational specifications, not implemented services.

## 5. Validity and readiness

Validate compatible currencies/units/valuation times, actual available shared capital, aggregate constraints, sleeve membership and proposal versions, unchanged holdings/reservations, required live/account evidence, and valid explicit execution authority. No P5 decision alters a parent Signal, tested relationship, P1/P2 result or forecast. No per-sleeve capital is presumed independent when it comes from the same pool.

## 6. Failure behavior

Missing or conflicting capital state, unknown commitments, stale sleeve assumptions, violated aggregate limits, absent allocation policy or unresolved feedback produce blockers with affected references. Keep operational failures separate from rejected allocation proposals and scientific outcomes. Execution must report denied/expired authorization, venue rejection, partial fill and unknown outcome distinctly under its future approved state contract. There is no automatic order submission, flattening, retry, liquidation or “best effort” allocation policy in this draft.

## 7. Reuse and invalidation

Capital/holdings/reservation/aggregate-limit/mandate changes invalidate affected allocations and dependent proposals. A physical locator change does not. Reuse valid forecasts and unrelated sleeve computation where dependencies are unchanged. A retry of an operational request retains its idempotency semantics and original recorded state; it does not silently mint a new authorized trade or claim a changed account snapshot is the same decision.

## 8. Persistence

Preserve allocation policy/input snapshots, provisional/final decision versions, exact proposal roster, feasibility/conflict evidence, feedback history, reservations and authorization records. Execution retains all order-state and reconciliation evidence, including failures and unknown outcomes. The catalog references these authoritative records; UI logs and copied spreadsheet values are not the capital or position ledger. Detailed account storage/atomicity lives in the future runtime contract and [10](10_runtime_recovery_storage.md).

## 9. Acceptance scenarios

- Two sleeves sharing one pool cannot both spend the same unreserved capital merely because their individual P4 solves succeeded.
- After reallocation, a proposal bound to the old allocation is stale and cannot pass final feasibility unchanged.
- Lot-size/aggregate-margin constraints that break after scaling produce an explicit unresolved/infeasible result, not an adjusted hidden trade.
- A final feasibility record for proposals A/B cannot authorize a different revision of A.
- A RequiredTrade with no explicit live execution authority never creates an order.
- An uncertain order response requires reconciliation under the approved protocol; the system cannot assume no fill and submit a duplicate.

Remaining decision package: allocation objective and constraints, capital/reservation semantics, P4/P5 feedback and convergence/failure policy, final feasibility ownership, currency/netting treatment, account-state freshness and explicit authorization/reconciliation protocol. These are gated implementation decisions, not unresolved high-level process ownership.
