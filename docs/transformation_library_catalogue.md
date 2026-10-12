# Transformation library — verified legacy catalogue

Status: **source-audited inventory and reuse proposal, 2026-10-08**. No scientific
transformation has been activated in the new platform by this task.

This document explains the existing registered operations in the legacy
`Multi-Asset Model/Data` transformation libraries, including their exact IDs, versions,
parameters, formulas, input requirements and observed implementation limits. It is complete
for the catalogues enumerated below; it is not an inventory of every mathematical operation
inside every research engine, or a claim that all possible transformations already exist.

## What exists

| Legacy catalogue | Version | Entries | Interpretation |
| --- | --- | ---: | --- |
| Base univariate library | 0.1.0 | 68 | 15 families of single-series transformations |
| Price technical library | 1.0.0 | 16 | 13 shared base names plus 3 price-specific names; preserve its separate namespace and parameter contract |
| ALFRED release-coherent library | 1.0.0 | 6 | Operators tied to explicitly selected release/vintage state |
| Binary library | 1.0.0 | 1 | Ordered difference interaction, placed before transformations |
| Additive parameter-grid extension | 1.0.0 | 1 | Weekly z-score window 156; a parameter permission, not another formula |
| **Total inventoried records** | | **92** | **90 transformation registrations + 1 interaction + 1 grid extension** |

The transformation registrations have 77 distinct literal IDs because 13 base names recur
in the price library. Counting repeated names once does not establish interchangeable
contracts. Each new registered operator must preserve its origin library, ID, version,
parameters, source-view assumptions and implementation evidence.

## Where the new library belongs

**Verified existing layout (definition paths are templates, not populated registrations):**

- `research_platform/definitions/transformations/<id>/<version>.json` — authoritative
  versioned transformation definitions. The directory exists; there are currently **zero
  operator JSON registrations**. This explanatory Markdown is not a registration.
- `research_platform/definitions/interactions/<id>/<version>.json` — separate approved
  multi-input operators, including a future adapter for the legacy difference operator.
- `research_platform/definitions/features/<id>/<version>.json` — the dataset/source-view
  and ordered operator recipe with exact parameters. This recipe defines the parent Signal.
- `research_platform/src/data/` — reusable data code; the existing ALFRED adapters live here.
  A new transformation adapter/module would be a later implementation within this code area.
- `research_platform/storage/catalog/feature_store/` and `research_platform/storage/payloads/`
  — Feature materialization manifests/indexes and observation bytes, respectively, under
  the existing storage specification. Transform outputs are not stored inside the definition
  library. Target definitions and materializations have their corresponding separate stores.

This inventory lives at `research_platform/docs/transformation_library_catalogue.md`.
`definitions/transformations/README.md` points here. The existing storage contract remains
`specs/12_data_pipeline_and_storage.md`; this document does not alter its ownership rules.

**Proposed reuse:** retain verified legacy behavior as versioned operators and adapt the
input/lineage envelope to the new PIT contracts. Register only after compatibility checks.
The optional interactions stage remains separate:

```text
raw → PIT/source view → optional interactions → transformations → Feature/Target stores
```

**Unresolved before execution:** approved dataset applicability, date-to-availability policy,
reference-period spacing/gaps, missing values, permitted parameter grids and treatment of
legacy edge cases. The detailed sections distinguish declared metadata from observed code
where they differ. These choices are not silently supplied by this catalogue.

## Base family overview

| Family | Entries |
| --- | ---: |
| Level | 2 |
| Change | 3 |
| Standardization | 4 |
| Smoothing | 4 |
| Trend | 10 |
| Momentum | 3 |
| Shock | 3 |
| Acceleration | 4 |
| Volatility | 10 |
| Volatility Scaling | 2 |
| Distribution | 5 |
| Extremes | 6 |
| Persistence | 4 |
| Threshold | 6 |
| Seasonality | 2 |

## Verified legacy base transformation catalogue

This is an exhaustive inventory of the **68 base univariate transformation IDs in 15 families** in the legacy Data library version `0.1.0` (registry schema `1.0.0`). It describes observed source behavior, not a claim that every method or parameterization has passed compatibility certification in `research_platform`. It covers this base catalogue only; separately catalogued interactions and post-transformation robustness operations must be inventoried separately.

The audit used static AST parsing and source inspection; it did not import the legacy engine, run scientific jobs, move data or install these methods in the new runtime. The exact Python IDs below are the canonical legacy IDs. The new system already reserves `definitions/transformations/<id>/<version>.json` for versioned definitions; populating that location remains a subsequent compatibility and specification step.

### Sources and verification

| Source | SHA-256 |
| --- | --- |
| [src/point_in_time_data/transformation_catalog.py](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py>) | `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b` |
| [src/point_in_time_data/transformations.py](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py>) | `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36` |
| [docs/transformation-library.md](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/docs/transformation-library.md>) | `14131fdd3a3f7cc8d1f28cead2e86ede62fae66a54b91d5b89b28c15c289675c` |
| [tests/test_transformations.py](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/tests/test_transformations.py>) | `5935528f9e62e9e5463b6fd7a04d28e37481c6ab9e69c0687220376871d73561` |

The AST check found 68 definitions, 68 unique IDs and 15 unique families. Every item below is generated from one source `_d(...)` declaration and paired with a source-based explanation. Legacy tests contain a 68-item catalogue count check and an execution smoke test that tries the first monthly parameter combination of each definition; **those tests were inspected, not executed by this audit**, and that smoke test does not certify every grid combination.

### Common interpretation and execution rules

- `x_t` is one numeric series at observation index t. `delta_k x_t = x_t - x_(t-k)`. Natural logs are used. Percent changes are fractions, not values multiplied by 100.
- `W_w` contains the last w observations **including t**; `W^-_w` contains the w observations **before t**. A window on changes has w changes and generally needs w+1 original levels. `y` means a one-observation diff, pct or log change selected by `basis`.
- All lags and rolling windows count observations, including the irregular/event frequencies. The engine does not infer missing calendar periods or annualize volatility. Its ordered-series primitive assumes the caller has supplied a correctly ordered single series.
- Rolling SD uses the sample denominator n-1 and rejects zero variance. Quantiles use Hyndman–Fan type 7 linear interpolation. Percentile ranks use `(number less + 0.5 × number equal) / count`.
- Exponential smoothing uses `alpha = 1 - exp(log(0.5)/h)`, seeds with the first value, and resets on missing input. EMA emits after h consecutive values. EW z-score compares with moments from before t and needs h prior consecutive values.
- Ordinary complete rolling windows reject any required missing input. No imputation, adaptive window shortening or parameter substitution occurs. Seasonal bucket methods are an explicit exception to complete-window checking: they filter missing history out; streak length also intentionally uses the available streak up to its cap.
- Metadata `requirements` strings describe intended validity; they are **not a generic validation layer**. The individual implementation branches and the parameter-validating PIT wrapper determine actual behavior. `apply_transform()` does not enforce the frequency grid; `run_pit_transformation()` does.
- The PIT wrapper selects source records available as of the supplied cutoff, filters dataset/entity/dimensions, orders reference periods, computes the latest value and preserves the selected lineage. A historical feature sequence must rerun that selection at every historical cutoff. Running once on final revised history is not PIT-safe.

Source anchors: [numeric, SD, quantile and EMA primitives](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:64>), [execution dispatch](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:262>), [PIT cutoff wrapper](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:663>).

### Fixed parameter grids

The five horizons below are written H1…H5. These are the legacy design choices being inventoried, not newly approved choices for the replacement platform.

| Frequency | H1, H2, H3, H4, H5 | Number of permitted base parameter combinations |
| --- | --- | --- |
| tick | 5, 20, 60, 120, 240 | 442 |
| intraday | 5, 20, 60, 120, 240 | 442 |
| daily | 5, 21, 63, 126, 252 | 442 |
| weekly | 4, 13, 26, 52, 104 | 441 |
| monthly | 3, 6, 12, 24, 60 | 441 |
| quarterly | 2, 4, 8, 12, 20 | 440 |
| semiannual | 2, 4, 6, 10, 20 | 438 |
| annual | 1, 2, 3, 5, 10 | 392 |
| irregular | 5, 10, 20, 40, 80 | 441 |
| event | 5, 10, 20, 40, 80 | 441 |

Counts are static enumeration of the grid rules across all 68 IDs. They count configured candidates, **not successful or scientifically admissible outputs**. For example, small annual windows can fall below a statistic’s minimum sample size, and seasonal entries are still enumerated for frequencies with no implemented bucket.

| Alias | Values | Monthly resolved example |
| --- | --- | --- |
| `K` | unique(1, H1, H2, H3, H4, H5) | 1, 3, 6, 12, 24, 60 |
| `W` | H1, H2, H3, H4, H5 | 3, 6, 12, 24, 60 |
| `W_STAT` | H2, H3, H4, H5 | 6, 12, 24, 60 |
| `HALF_LIFE` | H1, H2, H3, H4 | 3, 6, 12, 24 |
| `K_SHORT` | unique(1, H1, H2) | 1, 3, 6 |
| `K_SKIP` | H2, H3, H4, H5 | 6, 12, 24, 60 |
| `S_SKIP` | unique(1, H1) | 1, 3 |
| `K_ACCEL` | unique(1, H1, H2, H3) | 1, 3, 6, 12 |
| `SLOPE_W` | H2, H3, H4 | 6, 12, 24 |
| `VOL_W` | H2, H3, H4 | 6, 12, 24 |
| `TREND_W` | H1, H2, H3 | 3, 6, 12 |
| `K_SLOPE_CHANGE` | unique(1, H1) | 1, 3 |
| `AUTOCORR_LAG` | unique(1, H1) | 1, 3 |
| `VARIANCE_RATIO_K` | H1, H2 | 3, 6 |
| `VARIANCE_RATIO_W` | H3, H4, H5 | 12, 24, 60 |

Parameter meanings: `k` = change lag; `s` = skipped recent observations; `w` = rolling-window length; `v` = volatility-window length; `h` = exponential half-life; `fast`/`slow` = paired windows (half-lives for EMA crossover); `a` = autocorrelation lag; `basis` = one-observation change type; `q`, `low`, `high` = quantile probabilities; `history_years` = seasonal calendar-year lower-bound parameter.

The Cartesian grids are filtered as follows:

- MA crossover, EMA crossover and volatility ratio allow only `(H1,H2)`, `(H2,H3)`, `(H3,H4)`, `(H4,H5)`, `(H1,H3)`, `(H2,H4)`, `(H3,H5)` for `(fast,slow)`.
- Skip momentum requires `s < k`; shock methods require `k < w`.
- Quantile range permits only `(low,high)=(0.10,0.90)` or `(0.05,0.95)`.
- Difference autocorrelation requires `w >= 4*a`; variance ratio requires `w >= 4*k`.
- Other grid combinations are not filtered for statistical sample-size sufficiency.

[Grid declarations and expansion](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:143>).

### Exhaustive entries

#### Level (2)

##### 01. `level.raw` — Raw Level

Passes the current numeric level through unchanged. This is the identity transformation, not a return or normalized score.

- Catalogue formula: `x_t`.
- Parameters/grid: none.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:69>).

##### 02. `level.log` — Log Level

Takes the natural logarithm of the current level. Values at or below zero fail explicitly.

- Catalogue formula: `log(x_t)`.
- Parameters/grid: none.
- Declared requirements: `numeric_input`, `positive_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:70>).

#### Change (3)

##### 03. `change.diff` — Difference

Subtracts the level k observations earlier; the result remains in the original units.

- Catalogue formula: `x_t - x_(t-k)`.
- Parameters/grid: `k` = `K`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:71>).

##### 04. `change.pct` — Percent Change

Divides the current level by the level k observations earlier and subtracts one. The output is a fraction (0.01 means 1%), not a value multiplied by 100. A zero old level fails; negative levels are not categorically rejected.

- Catalogue formula: `x_t / x_(t-k) - 1`.
- Parameters/grid: `k` = `K`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:72>).

##### 05. `change.log` — Log Change

Subtracts two natural-log levels k observations apart. Both endpoints must be strictly positive.

- Catalogue formula: `log(x_t) - log(x_(t-k))`.
- Parameters/grid: `k` = `K`.
- Declared requirements: `numeric_input`, `positive_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:73>).

#### Standardization (4)

##### 06. `standard.zscore` — Rolling Z-Score

Compares the current level with the mean and sample standard deviation of the preceding w levels. The reference window excludes the current observation.

- Catalogue formula: `(x_t - mean(W^-_w)) / sd(W^-_w)`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:74>).

##### 07. `standard.robust_z` — Robust Z-Score

Compares the current level with the preceding-window median, scaled by 1.4826 times the median absolute deviation around that median. A zero MAD fails.

- Catalogue formula: `(x_t - median(W^-_w)) / (1.4826 * MAD(W^-_w))`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `nonzero_mad`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:75>).

##### 08. `standard.rank_centered` — Centered Rolling Rank

Ranks the current level against the preceding w levels, gives tied values half weight, and rescales the percentile to [-1, 1]. The current level is excluded from the reference sample.

- Catalogue formula: `2 * percentile_rank(x_t; W^-_w) - 1`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:76>).

##### 09. `standard.ew_zscore` — EW Z-Score

Compares the current value with exponentially weighted first and second moments calculated through the previous observation. Uses sqrt(EW[x²] - EW[x]²), without the sample-SD correction. Requires h prior consecutive nonmissing observations and positive variance.

- Catalogue formula: `(x_t - EWMean_(t-1,h)) / sqrt(EWVar_(t-1,h))`.
- Parameters/grid: `h` = `HALF_LIFE`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:77>).

#### Smoothing (4)

##### 10. `smooth.sma` — Simple Moving Average

Averages the last w levels, including the current level.

- Catalogue formula: `mean(W_w)`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:78>).

##### 11. `smooth.median` — Rolling Median

Takes the median of the last w levels, including the current level.

- Catalogue formula: `median(W_w)`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:79>).

##### 12. `smooth.ema` — Exponential Moving Average

Smooths levels using exponential weights with half-life h. Seeds the state with the first value of a consecutive nonmissing run and first emits after h observations.

- Catalogue formula: `EMA_h(x)_t`.
- Parameters/grid: `h` = `HALF_LIFE`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:80>).

##### 13. `smooth.ew_change` — EW Change

Applies the same exponentially weighted smoother to one-observation arithmetic differences. This is a smoothed change, not a return.

- Catalogue formula: `EMA_h(delta_1 x)_t`.
- Parameters/grid: `h` = `HALF_LIFE`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:81>).

#### Trend (10)

##### 14. `trend.ma_distance` — Moving-Average Distance

Subtracts the current-inclusive simple moving average from the current level; the distance is in original units.

- Catalogue formula: `x_t - MA_w(x)_t`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:82>).

##### 15. `trend.ma_relative` — Relative MA Distance

Divides the current level by its current-inclusive simple moving average and subtracts one. A zero moving average fails.

- Catalogue formula: `x_t / MA_w(x)_t - 1`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:83>).

##### 16. `trend.ema_distance` — EMA Distance

Subtracts the current-inclusive exponential moving average from the current level.

- Catalogue formula: `x_t - EMA_h(x)_t`.
- Parameters/grid: `h` = `HALF_LIFE`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:84>).

##### 17. `trend.ema_relative` — Relative EMA Distance

Divides the current level by its current-inclusive exponential moving average and subtracts one. A zero EMA fails.

- Catalogue formula: `x_t / EMA_h(x)_t - 1`.
- Parameters/grid: `h` = `HALF_LIFE`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:85>).

##### 18. `trend.ma_crossover` — MA Crossover

Divides the fast current-inclusive simple moving average by the slow one and subtracts one. Only seven specified fast/slow horizon pairings are in the grid.

- Catalogue formula: `MA_fast(x)_t / MA_slow(x)_t - 1`.
- Parameters/grid: `fast` = `W`; `slow` = `W`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:86>).

##### 19. `trend.ema_crossover` — EMA Crossover

Divides the fast current-inclusive exponential moving average by the slow one and subtracts one. The parameters named fast and slow are EMA half-lives even though their grid alias is W.

- Catalogue formula: `EMA_fast(x)_t / EMA_slow(x)_t - 1`.
- Parameters/grid: `fast` = `W`; `slow` = `W`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:87>).

##### 20. `trend.slope` — Rolling Linear Slope

Fits ordinary least squares to the last w levels against indices 0 through w-1. The result is a change in level per observation, not per calendar day. Requires at least three points.

- Catalogue formula: `OLS slope of x against observation index over W_w`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:88>).

##### 21. `trend.slope_tstat` — Slope T-Statistic

Divides that OLS slope by its residual-based standard error, using n-2 degrees of freedom. A zero standard error fails rather than producing infinity.

- Catalogue formula: `rolling OLS slope / standard error(slope)`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `defined_standard_error`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:89>).

##### 22. `trend.efficiency_ratio` — Trend Efficiency Ratio

Divides the signed net displacement over w changes by the sum of their absolute changes. Requires w+1 consecutive levels; returns between -1 and 1 and fails on a zero-length path.

- Catalogue formula: `(x_t-x_(t-w)) / sum_i(abs(delta_1 x_i))`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `nonzero_path_length`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:90>).

##### 23. `trend.breakout_position` — Breakout Position

Locates the current level relative to the minimum and maximum of the preceding w levels. It can be below 0 or above 1 because the current observation is excluded from the range.

- Catalogue formula: `(x_t-min(W^-_w)) / (max(W^-_w)-min(W^-_w))`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `nonzero_range`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:91>).

#### Momentum (3)

##### 24. `momentum.skip_diff` — Skip-Recent Difference

Measures the arithmetic change from k observations ago to s observations ago, deliberately omitting the most recent s observations. Requires s < k.

- Catalogue formula: `x_(t-s)-x_(t-k)`.
- Parameters/grid: `k` = `K_SKIP`; `s` = `S_SKIP`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:92>).

##### 25. `momentum.skip_return` — Skip-Recent Return

Measures the fractional return from k observations ago to s observations ago. Requires s < k and a nonzero old endpoint.

- Catalogue formula: `x_(t-s)/x_(t-k)-1`.
- Parameters/grid: `k` = `K_SKIP`; `s` = `S_SKIP`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:93>).

##### 26. `momentum.sign_balance` — Direction Balance

Averages the signs (-1, 0, +1) of the last w one-observation differences. Positive values indicate more positive than negative changes.

- Catalogue formula: `mean(sign(delta_1 x)) over W_w`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:94>).

#### Shock (3)

##### 27. `shock.standardized_change` — Standardized Change

Scales the current k-observation arithmetic difference by the sample SD of the preceding w k-observation differences. Does not subtract their mean.

- Catalogue formula: `delta_k x_t / sd(W^-_w(delta_k x))`.
- Parameters/grid: `k` = `K_SHORT`; `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:95>).

##### 28. `shock.change_zscore` — Change Z-Score

Subtracts the mean of the preceding w k-observation arithmetic differences from the current such difference, then divides by their sample SD.

- Catalogue formula: `(delta_k x_t-mean(W^-_w(delta_k x))) / sd(W^-_w(delta_k x))`.
- Parameters/grid: `k` = `K_SHORT`; `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:96>).

##### 29. `shock.change_percentile` — Change Percentile

Ranks the current k-observation arithmetic difference against the preceding w such differences, with half weight for ties, then maps the percentile to [-1, 1].

- Catalogue formula: `2*percentile_rank(delta_k x_t; W^-_w(delta_k x))-1`.
- Parameters/grid: `k` = `K_SHORT`; `w` = `W_STAT`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:97>).

#### Acceleration (4)

##### 30. `accel.second_diff` — Second Difference

Subtracts the previous k-observation arithmetic change from the current one. Uses levels at t, t-k and t-2k.

- Catalogue formula: `(x_t-x_(t-k))-(x_(t-k)-x_(t-2k))`.
- Parameters/grid: `k` = `K_ACCEL`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:98>).

##### 31. `accel.pct_change` — Percent-Change Acceleration

Subtracts the fractional return ending k observations ago from the current k-observation fractional return. Required denominators must be nonzero.

- Catalogue formula: `pct_change_k(t)-pct_change_k(t-k)`.
- Parameters/grid: `k` = `K_ACCEL`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:99>).

##### 32. `accel.log_change` — Log-Change Acceleration

Subtracts the log change ending k observations ago from the current k-observation log change. All required endpoints must be positive.

- Catalogue formula: `log_change_k(t)-log_change_k(t-k)`.
- Parameters/grid: `k` = `K_ACCEL`.
- Declared requirements: `numeric_input`, `positive_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:100>).

##### 33. `accel.slope_change` — Slope Change

Subtracts the w-observation OLS slope ending k observations ago from the current w-observation OLS slope.

- Catalogue formula: `slope_w(t)-slope_w(t-k)`.
- Parameters/grid: `w` = `SLOPE_W`; `k` = `K_SLOPE_CHANGE`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:101>).

#### Volatility (10)

##### 34. `vol.diff_sd` — Difference Volatility

Computes sample SD of the last w one-observation arithmetic differences. Constant changes fail as ZERO_VARIANCE; the implementation does not return zero volatility.

- Catalogue formula: `sd(W_w(delta_1 x))`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:102>).

##### 35. `vol.pct_sd` — Percent-Change Volatility

Computes sample SD of the last w one-observation fractional returns. Zero return denominators and zero variance fail.

- Catalogue formula: `sd(W_w(pct_change_1))`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `nonzero_denominator`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:103>).

##### 36. `vol.log_sd` — Log-Change Volatility

Computes sample SD of the last w one-observation log changes. Required levels must be positive; zero variance fails.

- Catalogue formula: `sd(W_w(log_change_1))`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `positive_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:104>).

##### 37. `vol.ewma` — EW Volatility

Computes the square root of the exponentially weighted mean of squared one-observation changes on the chosen basis. This is an uncentered root-mean-square, not an EW sample SD.

- Catalogue formula: `sqrt(EWMean_h(y^2))`.
- Parameters/grid: `basis` = `['diff', 'pct', 'log']`; `h` = `HALF_LIFE`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:105>).

##### 38. `vol.abs_change` — Mean Absolute Change

Averages the absolute last w one-observation changes on the selected diff, pct or log basis. Zero is a valid output for a constant series.

- Catalogue formula: `mean(W_w(abs(y)))`.
- Parameters/grid: `basis` = `['diff', 'pct', 'log']`; `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:106>).

##### 39. `vol.change` — Volatility Change

Subtracts the rolling sample-SD volatility ending k observations ago from the current rolling volatility, using the same w and change basis.

- Catalogue formula: `vol_w(t)-vol_w(t-k)`.
- Parameters/grid: `basis` = `['diff', 'pct', 'log']`; `w` = `VOL_W`; `k` = `K_SLOPE_CHANGE`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:107>).

##### 40. `vol.ratio` — Volatility Ratio

Divides short-window rolling sample-SD volatility by long-window volatility on the same basis. It does not subtract one. Both SD calls reject zero variance.

- Catalogue formula: `vol_fast(t)/vol_slow(t)`.
- Parameters/grid: `basis` = `['diff', 'pct', 'log']`; `fast` = `W`; `slow` = `W`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:108>).

##### 41. `vol.downside` — Downside Semivolatility

Takes the root mean square of the negative parts of the last w changes, treating positive changes as zero. The denominator counts the whole window, not only negative observations.

- Catalogue formula: `sqrt(mean(W_w(min(y,0)^2)))`.
- Parameters/grid: `basis` = `['diff', 'pct', 'log']`; `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:109>).

##### 42. `vol.upside` — Upside Semivolatility

Takes the root mean square of the positive parts of the last w changes, treating negative changes as zero. The denominator counts the whole window.

- Catalogue formula: `sqrt(mean(W_w(max(y,0)^2)))`.
- Parameters/grid: `basis` = `['diff', 'pct', 'log']`; `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:110>).

##### 43. `vol.asymmetry` — Volatility Asymmetry

Divides downside semivolatility by upside semivolatility over the same window; zero upside fails.

- Catalogue formula: `downside_vol_w/upside_vol_w`.
- Parameters/grid: `basis` = `['diff', 'pct', 'log']`; `w` = `W`.
- Declared requirements: `numeric_input`, `nonzero_denominator`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:111>).

#### Volatility Scaling (2)

##### 44. `volscale.diff` — Volatility-Scaled Difference

Divides the current k-observation arithmetic difference by the sample SD of the most recent w one-observation arithmetic differences, including the current difference.

- Catalogue formula: `delta_k x_t / sd(W_w(delta_1 x))`.
- Parameters/grid: `k` = `K_SHORT`; `w` = `VOL_W`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:112>).

##### 45. `volscale.trend` — Volatility-Scaled Trend

Divides the current level’s distance from its w-observation moving average by the sample SD of the last v one-observation arithmetic differences. Both reference windows include the current observation.

- Catalogue formula: `(x_t-MA_w(x)_t) / sd(W_v(delta_1 x))`.
- Parameters/grid: `w` = `TREND_W`; `v` = `VOL_W`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:113>).

#### Distribution (5)

##### 46. `distribution.skew` — Rolling Skewness

Computes the adjusted sample skewness of one-observation arithmetic differences over w observations. It needs at least three changes and nonzero variance.

- Catalogue formula: `sample skewness of W_w(delta_1 x)`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:114>).

##### 47. `distribution.kurtosis` — Rolling Excess Kurtosis

Computes bias-adjusted sample excess kurtosis of one-observation arithmetic differences; the normal-reference excess is zero. It needs at least four changes and nonzero variance.

- Catalogue formula: `sample excess kurtosis of W_w(delta_1 x)`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:115>).

##### 48. `distribution.iqr` — Interquartile Range

Computes the 75th percentile minus the 25th percentile of the last w one-observation arithmetic differences, using linearly interpolated type-7 quantiles.

- Catalogue formula: `Q75(W_w(delta_1 x))-Q25(W_w(delta_1 x))`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:116>).

##### 49. `distribution.quantile_range` — Quantile Range

Computes a symmetric central span of the last w arithmetic differences: either the 10th-to-90th or the 5th-to-95th percentile. Other low/high pairings are excluded.

- Catalogue formula: `Q_high(W_w(delta_1 x))-Q_low(W_w(delta_1 x))`.
- Parameters/grid: `w` = `W_STAT`; `low` = `[0.1, 0.05]`; `high` = `[0.9, 0.95]`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:117>).

##### 50. `distribution.quantile_skew` — Quantile Skewness

Computes quartile-based skewness of one-observation arithmetic differences: the asymmetry of the median within the interquartile range. A zero IQR produces ZERO_RANGE.

- Catalogue formula: `(Q75+Q25-2*Q50)/(Q75-Q25)`.
- Parameters/grid: `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `nonzero_iqr`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:118>).

#### Extremes (6)

##### 51. `extreme.range` — Rolling Range

Subtracts the minimum from the maximum of the last w levels, including the current level. A zero range is a valid result here.

- Catalogue formula: `max(W_w)-min(W_w)`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:119>).

##### 52. `extreme.new_high` — New High Indicator

Returns 1 only when the current level is strictly greater than all preceding w levels, otherwise 0. Ties are not new highs.

- Catalogue formula: `1[x_t>max(W^-_w)]`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:120>).

##### 53. `extreme.new_low` — New Low Indicator

Returns 1 only when the current level is strictly smaller than all preceding w levels, otherwise 0. Ties are not new lows.

- Catalogue formula: `1[x_t<min(W^-_w)]`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:121>).

##### 54. `extreme.time_since_high` — Time Since High

Counts observations since the most recent occurrence of the maximum in the current-inclusive w-level window. A maximum at the current point gives 0; tied highs use the latest tie.

- Catalogue formula: `observations since most recent max(W_w)`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `integer`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:122>).

##### 55. `extreme.time_since_low` — Time Since Low

Counts observations since the most recent occurrence of the minimum in the current-inclusive w-level window. A current low gives 0; tied lows use the latest tie.

- Catalogue formula: `observations since most recent min(W_w)`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `integer`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:123>).

##### 56. `extreme.max_drawdown` — Maximum Relative Drawdown

Tracks the running peak within the last w levels and returns the most negative relative decline from it. All levels in that window must be positive. The result is nonpositive and the peak does not predate the window.

- Catalogue formula: `min_v(x_v/running_peak_v-1) over W_w`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`, `positive_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:124>).

#### Persistence (4)

##### 57. `persistence.diff_autocorr` — Difference Autocorrelation

Computes Pearson correlation between two w-length sequences of one-observation differences separated by lag a. Uses w+a changes; a constant sequence fails.

- Catalogue formula: `corr(delta_1 x_t, delta_1 x_(t-a)) over W_w`.
- Parameters/grid: `a` = `AUTOCORR_LAG`; `w` = `W_STAT`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:125>).

##### 58. `persistence.sign` — Sign Persistence

Averages products of consecutive change signs over w adjacent pairs. Positive values indicate persistent direction, negative values indicate reversals, and zero changes contribute zero.

- Catalogue formula: `mean(sign(delta_1 x_t)*sign(delta_1 x_(t-1))) over W_w`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:126>).

##### 59. `persistence.sign_streak` — Signed Streak Length

Counts the current uninterrupted run of same-sign one-observation changes, capped at w, and attaches that sign. A zero current change returns 0. It can return a shorter streak before a full w changes exist.

- Catalogue formula: `current same-sign change streak capped at w`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `integer`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:127>).

##### 60. `persistence.variance_ratio` — Variance Ratio

Divides sample variance of overlapping k-observation arithmetic differences by k times sample variance of one-observation differences. The denominator uses w changes; the numerator uses w-k+1 overlapping changes within that span.

- Catalogue formula: `var(delta_k x)/(k*var(delta_1 x))`.
- Parameters/grid: `k` = `VARIANCE_RATIO_K`; `w` = `VARIANCE_RATIO_W`.
- Declared requirements: `numeric_input`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:128>).

#### Threshold (6)

##### 61. `threshold.positive_level` — Positive Level

Returns 1 if the current level is strictly above zero, otherwise 0.

- Catalogue formula: `1[x_t>0]`.
- Parameters/grid: none.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:129>).

##### 62. `threshold.positive_change` — Positive Change

Returns 1 if the current k-observation arithmetic difference is strictly positive, otherwise 0.

- Catalogue formula: `1[delta_k x_t>0]`.
- Parameters/grid: `k` = `K_ACCEL`.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:130>).

##### 63. `threshold.above_mean` — Above Historical Mean

Returns 1 if the current level is strictly above the mean of the preceding w levels. The current level is excluded from the threshold.

- Catalogue formula: `1[x_t>mean(W^-_w)]`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:131>).

##### 64. `threshold.above_median` — Above Historical Median

Returns 1 if the current level is strictly above the median of the preceding w levels.

- Catalogue formula: `1[x_t>median(W^-_w)]`.
- Parameters/grid: `w` = `W`.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:132>).

##### 65. `threshold.above_quantile` — Above Historical Quantile

Returns 1 if the current level strictly exceeds a chosen upper quantile of the preceding w levels: 0.75, 0.90 or 0.95.

- Catalogue formula: `1[x_t>Q_q(W^-_w)]`.
- Parameters/grid: `w` = `W_STAT`; `q` = `[0.75, 0.9, 0.95]`.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:133>).

##### 66. `threshold.below_quantile` — Below Historical Quantile

Returns 1 if the current level is strictly below a chosen lower quantile of the preceding w levels: 0.25, 0.10 or 0.05.

- Catalogue formula: `1[x_t<Q_q(W^-_w)]`.
- Parameters/grid: `w` = `W_STAT`; `q` = `[0.25, 0.1, 0.05]`.
- Declared requirements: `numeric_input`. Output: `binary`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:134>).

#### Seasonality (2)

##### 67. `seasonal.bucket_deviation` — Calendar-Bucket Deviation

Subtracts the mean of prior nonmissing observations in the same calendar bucket from the current level. The history-year bound and bucket selection follow the implementation described below; this is not a general seasonal-adjustment model.

- Catalogue formula: `x_t-mean(prior same-calendar-bucket observations)`.
- Parameters/grid: `history_years` = `[3, 5, 10]`.
- Declared requirements: `numeric_input`, `defined_seasonal_bucket`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:135>).

##### 68. `seasonal.bucket_zscore` — Calendar-Bucket Z-Score

Divides that same-calendar-bucket deviation by the sample SD of the selected bucket history. Requires at least two matching historical observations and nonzero variance.

- Catalogue formula: `same-bucket deviation/sd(prior same-bucket observations)`.
- Parameters/grid: `history_years` = `[5, 10]`.
- Declared requirements: `numeric_input`, `defined_seasonal_bucket`, `nonzero_variance`. Output: `number`.
- [Canonical source definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformation_catalog.py:136>).

### Validity and compatibility caveats observed in code

1. **Date-level PIT does not create historical vintages that never existed.** The wrapper can only enforce the available-at/lineage contract supplied by its caller; a stored final-vintage series must not be presented as historically knowable. This inventory does not change the new platform’s input availability policy.
2. **Warm-up and mathematical failure are retained as null plus reason.** Controlled codes are `NON_NUMERIC_INPUT`, `INSUFFICIENT_HISTORY`, `MISSING_REQUIRED_OBSERVATION`, `NONPOSITIVE_LOG_INPUT`, `NONPOSITIVE_INPUT`, `ZERO_DENOMINATOR`, `ZERO_VARIANCE`, `ZERO_MAD`, `ZERO_RANGE`, `ZERO_PATH_LENGTH`, `UNDEFINED_SEASONAL_BUCKET`, `INSUFFICIENT_SEASONAL_HISTORY`, `NUMERICAL_FAILURE`, `NONFINITE_OUTPUT`. Non-numeric or nonfinite inputs are rejected at series conversion; most point failures become null.
3. **Failure detail differs by branch.** The EMA/smoothed-change/EW-volatility branches label null output `INSUFFICIENT_HISTORY`, even if the underlying problem was a gap or invalid change basis input. The pointwise path has a final nonfinite-output guard, while special EW branches return directly. Compatibility work should inspect extreme finite-input overflow behavior before claiming uniform failure handling.
4. **Zero volatility is rejected by the legacy `_sd` implementation.** Thus `vol.diff_sd`, `vol.pct_sd`, `vol.log_sd` and methods built on rolling SD fail on constant changes. This differs from ordinary mathematical SD semantics. Semivolatility, absolute change, IQR and raw range may return zero. Catalogue requirements are not enough to infer these differences.
5. **Seasonal history is specific.** Buckets are weekday/hour/minute/second for tick and intraday; weekday for daily; ISO week number for weekly; month for monthly; quarter for quarterly; half-year for semiannual. Annual, irregular and event frequencies have no bucket implementation. Historical rows must have a strictly earlier calendar date, matching bucket, nonmissing value and year `>= current_year-history_years`. This uses a calendar-year bound, not an exact trailing number of days, and excludes same-day intraday observations. Only two selected history rows are required; `history_years` is not a minimum count. Missing current values are reported as insufficient seasonal history.
6. **Calendar spacing is not checked by the primitive.** A difference over one observation can cross a missing month. OLS slopes are per observation index. New wrappers need explicit approved cadence and gap policies; none are invented here.
7. **Scientific suitability is not universal.** Relative changes and drawdowns have different meaning on prices, spreads, rates and signed levels. Distribution methods use arithmetic first differences, not levels or user-selected returns. Existing metadata does not prove suitability for every dataset.
8. **Parameter validity is not numerical validity.** For example, annual `W_STAT` includes 2: slope needs at least 3 points, skewness needs 3, and kurtosis needs 4. Annual variance-ratio `k=1` is a degenerate identity wherever defined. Seasonality is enumerated even for unsupported frequencies. These are compatibility issues to retain visibly rather than silently “fix” under the same version.

Source anchors: [failure codes](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:21>), [special EW paths](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:277>), [sample SD](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:84>), [seasonal buckets](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:224>), [seasonal history filtering](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:585>), [legacy tests](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/tests/test_transformations.py:38>).

### Proposed transfer status and unresolved decisions

**Proposed:** retain these exact IDs and observed legacy semantics as candidates for explicitly versioned reuse, with source hashes, applicability constraints, allowed parameters and failure policy in each new definition. Adapt the wrapper to the new SourceView/PIT lineage and immutable definition contracts. Do not silently reinterpret an old ID or reuse its version for changed math. This document does not register or execute any transformation.

**Unresolved before activation:** confirm the scientific eligibility rules for each dataset family; cadence/gap and seasonal-history rules; treatment of degenerate grid cases; whether zero variance remains a failure; the EW failure/overflow behavior; and compatibility tests across all supported frequencies and relevant boundary cases. Existing tests are useful evidence but do not exhaust the configuration space.

The legacy documentation expressly excludes inverse levels, signed percent changes, clipping/winsorization, rolling AR models and multi-series operators from this **base** catalogue. Separate catalogues must be audited before treating those exclusions as statements about the entire old system.

## Additional legacy transformation registrations

This section is a static source audit, not an execution certificate. It covers the additional registries outside the 68-entry base univariate catalog. Versions and formulas below describe the legacy implementation as found; adoption into the new platform still requires compatibility checks.

Verified counts: **16 price registrations, 6 release-coherent registrations, 1 binary interaction registration and 1 parameter-grid extension**. Thirteen price IDs already occur in the base catalog. Across the base and these additions the inventory contains **90 versioned transformation registrations** (68 + 16 + 6), **one interaction** and **one grid extension**: 92 inventory entries, not 92 distinct formulas. There are 77 distinct univariate transformation IDs plus the one binary interaction ID. The grid extension is not an operator.

### Price technical registry — version 1.0.0

`P_t` is an ordered price observation; `w` and `k` count observations, not calendar days. `MA_w` includes the current observation. `EMA_h` uses half-life `h`, weight `1 − exp(log(0.5)/h)`, initializes at the first valid observation, and becomes available after `h` consecutive valid observations. Missing input resets EMA state. Standard deviations below use the sample denominator `n − 1`.

The registry requires named parameters but has no fixed numerical grid. The feature-definition builder accepts positive integers, requires `fast < slow` and `short < long`, and pins the registry and implementation hashes. See [price registry](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:20>) and [price definition builder](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/derived_feature_store.py:590>).

| Exact ID (all version 1.0.0) | Parameters | Meaning and implemented calculation | Source |
| --- | --- | --- | --- |
| `change.pct` | `k` | Fractional price change, `P_t/P_(t−k) − 1`. A result of 0.05 means 5%. The denominator must be nonzero; the delegated implementation does not enforce the registry's positive-price requirement. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:24>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:177>) |
| `change.log` | `k` | Continuously compounded return, `log(P_t) − log(P_(t−k))`; both endpoint prices must be positive. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:29>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:189>) |
| `momentum.sign_balance` | `w` | Average of the signs of the last `w` one-observation price changes. Rising, unchanged and falling moves contribute +1, 0 and −1. Measures directional consistency rather than magnitude; needs `w + 1` prices. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:34>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:432>) |
| `trend.ma_relative` | `w` | Relative distance from the current-inclusive arithmetic moving average: `P_t/MA_w(P)_t − 1`; undefined at zero mean. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:39>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:357>) |
| `trend.ma_crossover` | `fast`, `slow` | `MA_fast/MA_slow − 1`; positive when the shorter average exceeds the longer average. Both averages include the current observation; the slow average must be nonzero. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:44>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:376>) |
| `trend.ema_relative` | `h` | `P_t/EMA_h(P)_t − 1`, with the EMA convention above; denominator must be nonzero. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:49>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:366>) |
| `trend.ema_crossover` | `fast`, `slow` | `EMA_fast/EMA_slow − 1`; `fast` and `slow` are half-lives, not ordinary moving-average window lengths. Both EMA values must have completed warm-up and the slow EMA must be nonzero. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:54>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:382>) |
| `trend.breakout_position` | `w` | Position against the **preceding** `w` prices: `(P_t − min(history))/(max(history) − min(history))`. Current price is excluded from the range, so values may be below 0 or above 1. A flat range is undefined. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:59>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:409>) |
| `extreme.new_high` | `w` | Strict breakout flag: 1 if the current price exceeds every preceding `w` price, otherwise 0. Equal highs return 0. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:64>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:517>) |
| `trend.slope_tstat` | `w` | Trailing current-inclusive OLS slope against sequential observation index divided by its standard error. Requires at least three prices and nonzero standard error. A perfectly straight line is undefined here, rather than assigned an infinite score. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:69>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:390>) |
| `standard.zscore` | `w` | `(P_t − mean(preceding w prices))/sample_sd(preceding w prices)`. Current price is excluded from estimation of mean and deviation; a constant history is undefined. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:74>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:323>) |
| `accel.pct_change` | `k` | Difference between adjacent `k`-observation fractional returns: `pct_change_k(t) − pct_change_k(t−k)`. Requires `2k` history. This is acceleration of return, not a percentage change of returns. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:79>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:446>) |
| `accel.log_change` | `k` | Difference between adjacent `k`-observation log returns: `log_change_k(t) − log_change_k(t−k)`. Requires positive endpoint prices and `2k` history. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:84>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/transformations.py:446>) |
| `price.vol_normalized_log_return` | `k`, `w` | `log(P_t/P_(t−k)) / sample_sd(last w one-observation log returns)`. The volatility window **includes the current return**, is not annualized, and does not subtract a return mean from the numerator. Needs positive prices, at least `max(k,w)` history and nonzero volatility. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:89>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:189>) |
| `price.log_return_shape` | `short`, `long` | Short-horizon log return minus long-horizon log return, `log(P_t/P_(t−short)) − log(P_t/P_(t−long))`. Describes the difference in horizon shape; requires `short < long`, positive endpoints and `long` history. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:94>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:201>) |
| `price.oriented_new_low` | `w` | Negative strict breakdown flag: −1 if current price is below all preceding `w` prices, otherwise 0. Equal lows return 0. Unlike base `extreme.new_low`, the output is negated. Its implementation requires positive prices although registry metadata says only numeric input. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:99>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:213>) |

The frozen Technical + Momentum research program has **235 parameterized feature recipes**, not 235 transformations. Its lookbacks are `L = {1,2,5,10,21,42,63,126,252}`. Return and sign-balance use all `L`; MA/EMA distance, breakout position, high/low flags and z-score use `L` without 1; crossovers and shape use every ordered pair `short < long` from `L`; slope t-statistics use `{5,10,21,42,63,126,252}`; volatility-normalized returns use `w ∈ {21,42,63,126,252}` and `k ∈ L` with `k ≤ w`; acceleration uses `k ∈ {1,2,5,10,21}`. This is a research-program grid, not a restriction enforced by the price registry. [Program constants](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/research_orchestrator/technical_momentum_program.py:39>) and [recipe enumeration](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/research_orchestrator/technical_momentum_program.py:161>).

**Compatibility gates / verified discrepancies:** Thirteen registrations delegate directly to `apply_transform(..., frequency="daily")`; therefore their formulas reuse the base engine but carry a different registry version and parameter policy. The module's opening statement that it contains transforms absent from the base catalog is too broad: only the three `price.*` IDs are new. The price metadata declares positive input for percentage returns, relative averages, crossovers and percentage acceleration, but delegation does not add a general positive-input check. Conversely, `price.oriented_new_low` uses `_positive` despite numeric-only metadata. Preserve both the legacy identity and observed behavior; resolve these mismatches before certifying a new version. Direct mathematical functions do not replace the feature builder's parameter checks. Source-view selection, price orientation, missing observations and cutoff lineage must remain pinned outside the arithmetic layer. [Delegation and input conversion](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/price_technical_transformations.py:146>).

### ALFRED release-coherent registry — version 1.0.0

These six registrations require `SVIEW_ALFRED_RELEASE_COHERENT_AS_OF_STATE`. At a first-defensible release event, `x_t^(v_t)` means the current published value; each earlier operand uses the latest native-vintage value available at that same event, bounded by the defensible history start. Unchanged values carry forward and published revisions enter as soon as available. State selection and full operand lineage are part of the meaning, not optional preprocessing. Standard deviations use `n − 1`.

The legacy implementation indexes ordered observations/events, so `k=12` means 12 prior reference observations; it does not independently guarantee a one-year calendar interval if observations are missing. Source frequency and continuity must therefore be certified. [Source-view contract](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:176>), [state construction](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:367>), [persisted registry](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json>).

| Exact ID (all version 1.0.0) | Exact fixed parameter grid | Meaning and implemented calculation | Source |
| --- | --- | --- | --- |
| `release.level` | No parameters | Published level at the anchored release event, `x_t^(v_t)`. Keeps the exact native-vintage operand. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:248>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:571>) |
| `release.change_diff` | `k ∈ {1}` | `x_t^(v_t) − x_(t−k)^(v_t)`: change between two reference periods measured using one release's knowledge state, including already-known historical revisions. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:255>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:536>) |
| `release.change_pct` | `k ∈ {1,12}` | `x_t^(v_t)/x_(t−k)^(v_t) − 1`, with both operands from the same current release state. Previous value must be nonzero; negative values are not generally prohibited by this implementation. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:262>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:536>) |
| `release.standard_zscore` | `w ∈ {52,60}` | Current published level minus the mean of the preceding `w` levels in the **current** release state, divided by their sample deviation. Current value is excluded from the baseline. Requires `w + 1` state rows and nonzero variance. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:269>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:580>) |
| `release.trend_ma_relative` | `w ∈ {12}` | `x_t^(v_t)/mean(last w levels in current release state) − 1`. The mean includes the current level and must be nonzero. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:276>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:589>) |
| `release.shock_change_zscore` | `basis ∈ {diff,pct,log}`, `k ∈ {1}`, `w ∈ {20,52,60}` | Standardizes the current coherent change `g_t` against the preceding `w` release-event changes: `(g_t − mean(g_history))/sample_sd(g_history)`. Crucially, each historical `g_s` uses the information state at **its own** historical release event. Historical changes are not recomputed using today's revisions. `pct` requires nonzero prior value; `log` requires positive endpoints; `k < w` and nonzero variance are required. | [definition](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:283>), [calculation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/alfred_release_coherent.py:599>) |

**Compatibility gates:** Preserve the first-defensible anchor policy, availability-time precision, native-vintage selection, history boundary, frequency/continuity contract, exact fixed grids, current-versus-prior window boundaries, sample deviation, missing/failure semantics and every input's lineage. These cannot be replaced by a final-revised time series. The archived registry and source declare the same six formulas and grids. Whether the new platform's current date-precision PIT series meets all required release-state semantics remains a separate certification task; this inventory does not grant that certification.

### Binary interaction — version 1.0.0

**`combine.difference`** takes two ordered operands and computes `left_t − right_t` without scaling or ratio logic. Operand order is identity-bearing: long minus short differs from short minus long. Its registered alignment rule requires the same dataset, entity, reference period, availability time, vintage, ingestion and provider row group. The provider row group is the source-record ID before its final measure suffix. There are no numerical parameters. [Registry and implementation](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/binary_transformations.py:24>).

This belongs in the optional **interaction** stage, before applying a univariate transformation. It is not a new single-series recipe and does not imply a general spread/ratio/correlation engine exists. The arithmetic helper only converts operands to floats and subtracts; it does not enforce the alignment contract. The caller must enforce source membership, unique alignment, finite numeric input, units and lineage. The CFTC materializer implements strict paired-row matching and duplicate rejection in [its alignment function](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/research_orchestrator/cftc_cross_sectional.py:981>); its same-dataset scope is supplied by the frozen source resolver rather than the alignment tuple itself. Port the complete contract, not the subtraction helper alone.

### Parameter-grid extension — registry version 1.0.0

**Weekly `standard.zscore` version `0.1.0`, additional `w=156`.** This adds a permitted 156-observation weekly baseline to the existing z-score transform. The formula remains `(x_t − mean(preceding 156 values))/sample_sd(preceding 156 values)`. It is an additive parameter allowance: existing grids and identities are unchanged; the extension fingerprint must be preserved in identities that use it. It is neither a new operator nor a change to `standard.zscore` version `0.1.0`. [Extension registry and exact matcher](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/point_in_time_data/binary_transformations.py:63>).

### Other catalogs checked and audit boundary

Targeted inspection covered `Data/src`, `Data/docs`, `Data/schemas`, `Data/catalog`, `Data/planning`, `Data/scripts` and shallow `Data/derived/*/version` registry files. No extra generic transformation registry was located beyond the base, price, release-coherent, binary and grid-extension sources above. Raw payloads and the massive generated stores were not recursively scanned; this is an exhaustive enumeration of the located canonical transformation catalogs, not a claim about every formula in every research engine or all transformations that could ever be invented.

The CFTC cross-sectional registry contains **38 feature definitions** combining selected trader groups, source measures, `combine.difference` and existing base transformations (including the 156-week extension). It adds feature recipes, not additional primitive transformations. [Recipe construction](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/research_orchestrator/cftc_cross_sectional.py:491>) and [persisted feature registry](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/derived/cftc-fx-cross-sectional/v1.0.0/feature-registry.json>).

The legacy base-library prose says multi-series spreads belong to a future Interaction Library. The later binary difference registry is a concrete additional capability and must be inventoried separately from that earlier prose. No general interaction catalog for arbitrary ratios, residuals, correlations, betas, ranks or composites was verified in this targeted audit. Their implementation or adoption would require a separate specification.

### Related research and robustness operations — excluded from the operator count

Clipping and winsorization are explicitly excluded from the base transformation catalog and assigned to an explicit robustness protocol in [the legacy library document](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/docs/transformation-library.md:99>). This is a design boundary, not evidence that a reusable clipping or winsorization registry exists. The inspected Research Specs set `feature_preprocessing` to `none`; the empirical engine documentation explicitly says it performs no winsorization, normalization, filling, resampling or feature transformation. [Research Spec bindings](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/research_specification_registry/registry.py:248>) and [empirical engine contract](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/docs/empirical-signal-research.md:61>).

Verified downstream robustness machinery includes three chronological equal-count blocks with remainder observations allocated to earlier blocks, plus validation leave-out estimates, predefined robustness slices and expected-direction orientation of effect metrics. These evaluate a trial or validation record and do not create reusable source transformations. They must remain owned by their Research Spec / validation policies. [Research robustness policy](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/src/research_specification_registry/registry.py:202>), [validation report contract](</Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data/docs/process2-signal-validation.md:39>). Portfolio instrument caps and coverage-window restrictions also use clipping terminology elsewhere, but are outside the transformation-library scope.

## Additional source fingerprints

SHA-256 fingerprints below pin the inspected nonbase canonical sources. These identify the
source evidence for this document, not new scientific registrations or runtime certification.

| Legacy source relative to Data/ | SHA-256 |
| --- | --- |
| `src/point_in_time_data/price_technical_transformations.py` | `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e` |
| `src/point_in_time_data/binary_transformations.py` | `ae66c94267b0df4f09b83ef36cb13b29175b0238b6865d219841841bcd9845f3` |
| `src/point_in_time_data/alfred_release_coherent.py` | `95d5ae51e180da336366809c567a35e91f7675a4a9b25acdd4e47451e94c28c4` |
| `derived/alfred-release-coherent/v1.0.0/transformation-registry.json` | `0cd0d532c63a867f5e2c1b91282197c4112c036c020dd7a423b6ac238891fa5d` |

## What this task establishes

**Verified:** all 68 base definitions match their source declarations and exported registry;
all 16 price registrations, six release registrations, one binary registration and one grid
extension are individually explained. Definitions were inspected statically; legacy scientific
jobs and the legacy numerical test suite were not executed. Source links were checked against
files present on this machine. No legacy data or code was changed.

**Proposed:** use this catalogue as the input to versioned compatibility adapters and operator
registrations, retaining exact source semantics and lineage. Keep interactions and grid-policy
extensions separate from univariate transformations.

**Still unresolved:** the applicability and compatibility gates described above. The new
platform does not yet have an executable transformation library or approved JSON operator
registrations. The next bounded implementation can register and verify one selected operator
against a pinned PIT source view before generating any Feature observations.
