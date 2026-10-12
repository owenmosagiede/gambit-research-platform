# Transformation library and feature engineering foundation

This is the executable version 2 library: **98 registrations, 98 approved**, with **79 numerical kernels and 1 generic release-event-history operation**. Registrations, mathematical operations and parameterized recipes are different counts. No production Features or Signals are created by these definitions.

The [historical legacy audit](transformation_library_catalogue.md) is preserved unchanged. This document is generated from authoritative `definitions/transformations/<id>/2.0.0.json` records by `src/data/transformations/documentation.py`; the registry test rejects documentation drift.

The authoritative execution specification is [Specification16](../specs/16_transformation_execution.md).

## Scope and location

The registrations comprise 68 base aliases across the original 15 families, 16 distinct price aliases, 6 generic release aliases and 8 new direct-input primitives. Repeated price names retain separate identities and parameter policies. The release aliases describe capabilities and temporal behavior rather than provider names.

- Definitions: `definitions/transformations/`; approved execution, history, units, missing-data and grid policies: `definitions/policies/`.
- Code: `src/data/transformations/{numeric,registry,contracts,identity,engine}.py`.
- Recipes will use the existing `predictor_recipe` inside Feature definitions. Calculated observations belong in the existing Feature catalog and payload store, not this definition directory.
- Interactions, targets, research, UI changes, downloads, production transformations and production Signal registration are excluded. `combine.difference` is deliberately not registered.

## Shared execution contract

Each recipe consumes one explicitly selected SourceView, measure, entity and dimension partition. Reference time, native historical availability, evaluation cutoff and execution time remain distinct. Provider identity is provenance; it does not choose formulas. A source must separately satisfy the declared capabilities and history policy. Successful mathematical tests do not certify any particular real dataset for release timing or live use.

All windows and lags count observations. Regular cadence uses the declared gap policy; missing periods are never silently dropped. Irregular/event inputs require explicit observation ordering. Required windows are complete, with no filling or adaptive shortening. The documented seasonal filtering and capped-streak exceptions are explicit. Output preserves requested indexes, controlled null reasons, semantics, units and lineage. An all-null result is not reported as a successful scientific calculation. Unexpected implementation failures remain exceptions.

Reference-state recipes resolve only information known at each evaluation cutoff. Emitted-history recipes compose values emitted at their own earlier cutoffs. A release shock is special: each past change is computed from its own anchored release state, then the current change is standardized against those earlier emitted changes. Recomputing old changes using the latest revisions is prohibited. Undeclared temporal switches are rejected.

Units are explicit: `preserve` retains input units; `per_observation` divides them by one observation index; `change_basis` retains units for differences and produces dimensionless values for fractional/log changes; `dimensionless` produces unit1; `observation_count` counts observations; `log_input` labels natural-log input units. Fractional changes are not multiplied by 100. Output semantics are declared separately from units.

## Numerical conventions and deliberate version 2 changes

`W_w` contains the last w values including the current one; `W^-_w` contains the w preceding values. `delta_k x_t=x_t-x_(t-k)`. `sd` is sample deviation with denominator n-1. Descriptive SD may equal zero in version 2; division by zero SD remains undefined. This deliberately differs from legacy descriptive volatility. Price aliases now enforce their explicitly declared positive-price domain. Invalid parameter sizes and relationships reject the request before execution. These changes never redefine an old version.

Type 7 quantiles interpolate linearly at index `(n-1)q`. Ranks use `(count_less+0.5*count_equal)/n`. Adjusted sample skewness is `n/((n-1)(n-2))*sum(((x-mean)/s)^3)`. Bias-adjusted excess kurtosis is `n(n+1)/((n-1)(n-2)(n-3))*sum(((x-mean)/s)^4)-3(n-1)^2/((n-2)(n-3))`, where s uses n-1. Skewness needs n>=3 and kurtosis n>=4. Distribution operators retain the documented distinction between differences and direct supplied values.

Exponential weights use `alpha=1-exp(log(0.5)/h)`, seed with the first valid value of a run, reset on missing/invalid input and emit after h consecutive valid inputs. EW z-score uses h prior valid observations and pre-current exponential mean/variance. Version2 computes variance through a stable centered recurrence, algebraically equivalent to the uncorrected second moment minus squared mean; it avoids cancellation in the old raw-moment subtraction. EW volatility is root mean square of changes, not centered SD.

Seasonal buckets are weekday for daily, ISO week for weekly, month for monthly, quarter for quarterly, half-year for semiannual, and weekday/hour/minute/second for tick/intraday. Intraday buckets require timestamp precision. Annual, irregular and event seasonal configurations reject. Only strictly earlier calendar dates within `current_year-history_years` through the current year enter the same bucket; both seasonal methods require at least 2 nonmissing prior bucket observations.

## Parameter validation and finite grids

Mathematical domains and optional grid permission are separate. `Registry.validate_parameters` validates exact names, types, minimum sizes and relationships. Supplying an explicit grid policy additionally checks membership. `Registry.enumerate_grid(entry,frequency,policy,max_combinations=...)` requires a finite bound; no default candidate generation occurs. Invalid legacy-axis configurations are excluded rather than repaired. Finite coverage tests do not exhaust arbitrary parameter values.

Base/Core horizon aliases use the frequency horizon policy. H1...H5 resolve as follows:

| Frequency | H1...H5 |
| --- | --- |
| tick | 5, 20, 60, 120, 240 |
| intraday | 5, 20, 60, 120, 240 |
| daily | 5, 21, 63, 126, 252 |
| weekly | 4, 13, 26, 52, 104 |
| monthly | 3, 6, 12, 24, 60 |
| quarterly | 2, 4, 8, 12, 20 |
| semiannual | 2, 4, 6, 10, 20 |
| annual | 1, 2, 3, 5, 10 |
| irregular | 5, 10, 20, 40, 80 |
| event | 5, 10, 20, 40, 80 |

Aliases: `K=unique(1,H1...H5)`, `W=H1...H5`, `W_STAT=H2...H5`, `HALF_LIFE=H1...H4`, `K_SHORT=unique(1,H1,H2)`, `K_SKIP=H2...H5`, `S_SKIP=unique(1,H1)`, `K_ACCEL=unique(1,H1,H2,H3)`, `SLOPE_W=VOL_W=H2,H3,H4`, `TREND_W=H1,H2,H3`, `K_SLOPE_CHANGE=AUTOCORR_LAG=unique(1,H1)`, `VARIANCE_RATIO_K=H1,H2`, `VARIANCE_RATIO_W=H3,H4,H5`.

Base crossovers and volatility ratios retain horizon-position pairs (H1,H2),(H2,H3),(H3,H4),(H4,H5),(H1,H3),(H2,H4),(H3,H5). Finite quantile-range grids retain only (0.10,0.90) or (0.05,0.95). Price grids preserve the audited Technical+Momentum lookback profile; release grids retain their fixed audited choices. Metadata axes and numerical parameter relationships are both enforced.

`POL_TRANSFORM_GRID_WEEKLY_156` is a separate versioned parameter permission for the base weekly z-score. It extends, rather than replaces, the base profile; it is not a 99th transformation. Its full immutable reference is bound to the recipe step, preserving the extension fingerprint in recipe identity.

Legacy weekly156 extension fingerprint: `sha256_7e3e940b7b7d659b97330e4962b6b54003844be5102c08ff747b54b56e3e5d04`. It is retained inside the new grid-policy reference.

## Family index

| Family | Registrations | Meaning |
| --- | ---: | --- |
| acceleration | 6 | Changes of changes or slopes. |
| change | 7 | Lagged arithmetic, fractional and log changes. |
| distribution | 5 | Shape and quantiles of one-observation differences. |
| extremes | 7 | Ranges, breakouts, recency and drawdown. |
| input_distribution | 5 | New direct-input shape and quantiles, without differencing. |
| level | 4 | Raw/log levels and causal lag. |
| momentum | 4 | Skipped recent changes and direction balance. |
| persistence | 4 | Serial dependence, streaks and variance ratios within one series. |
| price | 3 | Additional explicitly price-semantic operations. |
| seasonality | 2 | Comparisons with earlier calendar buckets. |
| shock | 4 | Changes compared with preceding change histories. |
| smoothing | 5 | Moving averages and rolling sums. |
| standardization | 6 | Prior-window standardized positions. |
| threshold | 6 | Strict indicators against levels or prior thresholds. |
| trend | 17 | Within-series direction, slopes and moving-average comparisons. |
| volatility | 11 | Change-based or direct-input dispersion. |
| volatility_scaling | 2 | Differences or trends scaled by change volatility. |

## Registration, implementation and coverage index

Every row below has a separately pinned operator identity. The numerical tests independently specify defined expected outputs, and cover boundaries, missingness, constant/extreme inputs and causal future-appending behavior. Engine acceptance tests supply full input schemas, selection, composition, historical revisions and generic release-state certification fixtures.

| Registration | Legacy ID/version or new primitive | Kernel | Temporal mode | Grid policy |
| --- | --- | --- | --- | --- |
| [TR_BASE_accel_log_change](#tr_base_accel_log_change) | `base:accel.log_change@0.1.0` | `accel.log_change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_accel_pct_change](#tr_base_accel_pct_change) | `base:accel.pct_change@0.1.0` | `accel.pct_change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_accel_second_diff](#tr_base_accel_second_diff) | `base:accel.second_diff@0.1.0` | `accel.second_diff` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_accel_slope_change](#tr_base_accel_slope_change) | `base:accel.slope_change@0.1.0` | `accel.slope_change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_change_diff](#tr_base_change_diff) | `base:change.diff@0.1.0` | `change.diff` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_change_log](#tr_base_change_log) | `base:change.log@0.1.0` | `change.log` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_change_pct](#tr_base_change_pct) | `base:change.pct@0.1.0` | `change.pct` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_distribution_iqr](#tr_base_distribution_iqr) | `base:distribution.iqr@0.1.0` | `distribution.iqr` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_distribution_kurtosis](#tr_base_distribution_kurtosis) | `base:distribution.kurtosis@0.1.0` | `distribution.kurtosis` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_distribution_quantile_range](#tr_base_distribution_quantile_range) | `base:distribution.quantile_range@0.1.0` | `distribution.quantile_range` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_distribution_quantile_skew](#tr_base_distribution_quantile_skew) | `base:distribution.quantile_skew@0.1.0` | `distribution.quantile_skew` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_distribution_skew](#tr_base_distribution_skew) | `base:distribution.skew@0.1.0` | `distribution.skew` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_extreme_max_drawdown](#tr_base_extreme_max_drawdown) | `base:extreme.max_drawdown@0.1.0` | `extreme.max_drawdown` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_extreme_new_high](#tr_base_extreme_new_high) | `base:extreme.new_high@0.1.0` | `extreme.new_high` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_extreme_new_low](#tr_base_extreme_new_low) | `base:extreme.new_low@0.1.0` | `extreme.new_low` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_extreme_range](#tr_base_extreme_range) | `base:extreme.range@0.1.0` | `extreme.range` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_extreme_time_since_high](#tr_base_extreme_time_since_high) | `base:extreme.time_since_high@0.1.0` | `extreme.time_since_high` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_extreme_time_since_low](#tr_base_extreme_time_since_low) | `base:extreme.time_since_low@0.1.0` | `extreme.time_since_low` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_level_log](#tr_base_level_log) | `base:level.log@0.1.0` | `level.log` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_level_raw](#tr_base_level_raw) | `base:level.raw@0.1.0` | `level.raw` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_momentum_sign_balance](#tr_base_momentum_sign_balance) | `base:momentum.sign_balance@0.1.0` | `momentum.sign_balance` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_momentum_skip_diff](#tr_base_momentum_skip_diff) | `base:momentum.skip_diff@0.1.0` | `momentum.skip_diff` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_momentum_skip_return](#tr_base_momentum_skip_return) | `base:momentum.skip_return@0.1.0` | `momentum.skip_return` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_persistence_diff_autocorr](#tr_base_persistence_diff_autocorr) | `base:persistence.diff_autocorr@0.1.0` | `persistence.diff_autocorr` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_persistence_sign](#tr_base_persistence_sign) | `base:persistence.sign@0.1.0` | `persistence.sign` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_persistence_sign_streak](#tr_base_persistence_sign_streak) | `base:persistence.sign_streak@0.1.0` | `persistence.sign_streak` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_persistence_variance_ratio](#tr_base_persistence_variance_ratio) | `base:persistence.variance_ratio@0.1.0` | `persistence.variance_ratio` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_seasonal_bucket_deviation](#tr_base_seasonal_bucket_deviation) | `base:seasonal.bucket_deviation@0.1.0` | `seasonal.bucket_deviation` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_seasonal_bucket_zscore](#tr_base_seasonal_bucket_zscore) | `base:seasonal.bucket_zscore@0.1.0` | `seasonal.bucket_zscore` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_shock_change_percentile](#tr_base_shock_change_percentile) | `base:shock.change_percentile@0.1.0` | `shock.change_percentile` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_shock_change_zscore](#tr_base_shock_change_zscore) | `base:shock.change_zscore@0.1.0` | `shock.change_zscore` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_shock_standardized_change](#tr_base_shock_standardized_change) | `base:shock.standardized_change@0.1.0` | `shock.standardized_change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_smooth_ema](#tr_base_smooth_ema) | `base:smooth.ema@0.1.0` | `smooth.ema` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_smooth_ew_change](#tr_base_smooth_ew_change) | `base:smooth.ew_change@0.1.0` | `smooth.ew_change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_smooth_median](#tr_base_smooth_median) | `base:smooth.median@0.1.0` | `smooth.median` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_smooth_sma](#tr_base_smooth_sma) | `base:smooth.sma@0.1.0` | `smooth.sma` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_standard_ew_zscore](#tr_base_standard_ew_zscore) | `base:standard.ew_zscore@0.1.0` | `standard.ew_zscore` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_standard_rank_centered](#tr_base_standard_rank_centered) | `base:standard.rank_centered@0.1.0` | `standard.rank_centered` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_standard_robust_z](#tr_base_standard_robust_z) | `base:standard.robust_z@0.1.0` | `standard.robust_z` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_standard_zscore](#tr_base_standard_zscore) | `base:standard.zscore@0.1.0` | `standard.zscore` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_threshold_above_mean](#tr_base_threshold_above_mean) | `base:threshold.above_mean@0.1.0` | `threshold.above_mean` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_threshold_above_median](#tr_base_threshold_above_median) | `base:threshold.above_median@0.1.0` | `threshold.above_median` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_threshold_above_quantile](#tr_base_threshold_above_quantile) | `base:threshold.above_quantile@0.1.0` | `threshold.above_quantile` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_threshold_below_quantile](#tr_base_threshold_below_quantile) | `base:threshold.below_quantile@0.1.0` | `threshold.below_quantile` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_threshold_positive_change](#tr_base_threshold_positive_change) | `base:threshold.positive_change@0.1.0` | `threshold.positive_change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_threshold_positive_level](#tr_base_threshold_positive_level) | `base:threshold.positive_level@0.1.0` | `threshold.positive_level` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_breakout_position](#tr_base_trend_breakout_position) | `base:trend.breakout_position@0.1.0` | `trend.breakout_position` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_efficiency_ratio](#tr_base_trend_efficiency_ratio) | `base:trend.efficiency_ratio@0.1.0` | `trend.efficiency_ratio` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_ema_crossover](#tr_base_trend_ema_crossover) | `base:trend.ema_crossover@0.1.0` | `trend.ema_crossover` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_ema_distance](#tr_base_trend_ema_distance) | `base:trend.ema_distance@0.1.0` | `trend.ema_distance` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_ema_relative](#tr_base_trend_ema_relative) | `base:trend.ema_relative@0.1.0` | `trend.ema_relative` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_ma_crossover](#tr_base_trend_ma_crossover) | `base:trend.ma_crossover@0.1.0` | `trend.ma_crossover` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_ma_distance](#tr_base_trend_ma_distance) | `base:trend.ma_distance@0.1.0` | `trend.ma_distance` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_ma_relative](#tr_base_trend_ma_relative) | `base:trend.ma_relative@0.1.0` | `trend.ma_relative` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_slope](#tr_base_trend_slope) | `base:trend.slope@0.1.0` | `trend.slope` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_trend_slope_tstat](#tr_base_trend_slope_tstat) | `base:trend.slope_tstat@0.1.0` | `trend.slope_tstat` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_abs_change](#tr_base_vol_abs_change) | `base:vol.abs_change@0.1.0` | `vol.abs_change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_asymmetry](#tr_base_vol_asymmetry) | `base:vol.asymmetry@0.1.0` | `vol.asymmetry` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_change](#tr_base_vol_change) | `base:vol.change@0.1.0` | `vol.change` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_diff_sd](#tr_base_vol_diff_sd) | `base:vol.diff_sd@0.1.0` | `vol.diff_sd` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_downside](#tr_base_vol_downside) | `base:vol.downside@0.1.0` | `vol.downside` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_ewma](#tr_base_vol_ewma) | `base:vol.ewma@0.1.0` | `vol.ewma` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_log_sd](#tr_base_vol_log_sd) | `base:vol.log_sd@0.1.0` | `vol.log_sd` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_pct_sd](#tr_base_vol_pct_sd) | `base:vol.pct_sd@0.1.0` | `vol.pct_sd` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_ratio](#tr_base_vol_ratio) | `base:vol.ratio@0.1.0` | `vol.ratio` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_vol_upside](#tr_base_vol_upside) | `base:vol.upside@0.1.0` | `vol.upside` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_volscale_diff](#tr_base_volscale_diff) | `base:volscale.diff@0.1.0` | `volscale.diff` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_BASE_volscale_trend](#tr_base_volscale_trend) | `base:volscale.trend@0.1.0` | `volscale.trend` | `reference_state` | `POL_TRANSFORM_GRID_BASE` |
| [TR_CORE_core_lag](#tr_core_core_lag) | `New direct-input primitive` | `core.lag` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_CORE_core_rolling_sum](#tr_core_core_rolling_sum) | `New direct-input primitive` | `core.rolling_sum` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_CORE_core_sample_sd](#tr_core_core_sample_sd) | `New direct-input primitive` | `core.sample_sd` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_CORE_input_distribution_iqr](#tr_core_input_distribution_iqr) | `New direct-input primitive` | `input_distribution.iqr` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_CORE_input_distribution_kurtosis](#tr_core_input_distribution_kurtosis) | `New direct-input primitive` | `input_distribution.kurtosis` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_CORE_input_distribution_quantile_range](#tr_core_input_distribution_quantile_range) | `New direct-input primitive` | `input_distribution.quantile_range` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_CORE_input_distribution_quantile_skew](#tr_core_input_distribution_quantile_skew) | `New direct-input primitive` | `input_distribution.quantile_skew` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_CORE_input_distribution_skew](#tr_core_input_distribution_skew) | `New direct-input primitive` | `input_distribution.skew` | `reference_state` | `POL_TRANSFORM_GRID_CORE` |
| [TR_PRICE_accel_log_change](#tr_price_accel_log_change) | `price:accel.log_change@1.0.0` | `accel.log_change` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_accel_pct_change](#tr_price_accel_pct_change) | `price:accel.pct_change@1.0.0` | `accel.pct_change` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_change_log](#tr_price_change_log) | `price:change.log@1.0.0` | `change.log` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_change_pct](#tr_price_change_pct) | `price:change.pct@1.0.0` | `change.pct` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_extreme_new_high](#tr_price_extreme_new_high) | `price:extreme.new_high@1.0.0` | `extreme.new_high` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_momentum_sign_balance](#tr_price_momentum_sign_balance) | `price:momentum.sign_balance@1.0.0` | `momentum.sign_balance` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_price_log_return_shape](#tr_price_price_log_return_shape) | `price:price.log_return_shape@1.0.0` | `price.log_return_shape` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_price_oriented_new_low](#tr_price_price_oriented_new_low) | `price:price.oriented_new_low@1.0.0` | `price.oriented_new_low` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_price_vol_normalized_log_return](#tr_price_price_vol_normalized_log_return) | `price:price.vol_normalized_log_return@1.0.0` | `price.vol_normalized_log_return` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_standard_zscore](#tr_price_standard_zscore) | `price:standard.zscore@1.0.0` | `standard.zscore` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_trend_breakout_position](#tr_price_trend_breakout_position) | `price:trend.breakout_position@1.0.0` | `trend.breakout_position` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_trend_ema_crossover](#tr_price_trend_ema_crossover) | `price:trend.ema_crossover@1.0.0` | `trend.ema_crossover` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_trend_ema_relative](#tr_price_trend_ema_relative) | `price:trend.ema_relative@1.0.0` | `trend.ema_relative` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_trend_ma_crossover](#tr_price_trend_ma_crossover) | `price:trend.ma_crossover@1.0.0` | `trend.ma_crossover` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_trend_ma_relative](#tr_price_trend_ma_relative) | `price:trend.ma_relative@1.0.0` | `trend.ma_relative` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_PRICE_trend_slope_tstat](#tr_price_trend_slope_tstat) | `price:trend.slope_tstat@1.0.0` | `trend.slope_tstat` | `reference_state` | `POL_TRANSFORM_GRID_PRICE` |
| [TR_RELEASE_change_diff](#tr_release_change_diff) | `release:release.change_diff@1.0.0` | `change.diff` | `release_state` | `POL_TRANSFORM_GRID_RELEASE` |
| [TR_RELEASE_change_pct](#tr_release_change_pct) | `release:release.change_pct@1.0.0` | `change.pct` | `release_state` | `POL_TRANSFORM_GRID_RELEASE` |
| [TR_RELEASE_level](#tr_release_level) | `release:release.level@1.0.0` | `level.raw` | `release_state` | `POL_TRANSFORM_GRID_RELEASE` |
| [TR_RELEASE_shock_change_zscore](#tr_release_shock_change_zscore) | `release:release.shock_change_zscore@1.0.0` | `release.shock_change_zscore` | `release_event_history` | `POL_TRANSFORM_GRID_RELEASE` |
| [TR_RELEASE_standard_zscore](#tr_release_standard_zscore) | `release:release.standard_zscore@1.0.0` | `standard.zscore` | `release_state` | `POL_TRANSFORM_GRID_RELEASE` |
| [TR_RELEASE_trend_ma_relative](#tr_release_trend_ma_relative) | `release:release.trend_ma_relative@1.0.0` | `trend.ma_relative` | `release_state` | `POL_TRANSFORM_GRID_RELEASE` |

## Exhaustive operator definitions

### TR_BASE_accel_log_change

**Log-Change Acceleration** — version `2.0.0`, family `acceleration`, certification `approved`.

Subtracts the log change ending k observations ago from the current k-observation log change. All required endpoints must be positive.

Formula: `log_change_k(t)-log_change_k(t-k)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_ACCEL"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `log_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **-0.133361541244**. Values are a single ordered numeric input series.

Legacy mapping: `base:accel.log_change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:100`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `accel.log_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_accel_pct_change

**Percent-Change Acceleration** — version `2.0.0`, family `acceleration`, certification `approved`.

Subtracts the fractional return ending k observations ago from the current k-observation fractional return. Required denominators must be nonzero.

Formula: `pct_change_k(t)-pct_change_k(t-k)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_ACCEL"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `fractional_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **-0.226293103448**. Values are a single ordered numeric input series.

Legacy mapping: `base:accel.pct_change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:99`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `accel.pct_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_accel_second_diff

**Second Difference** — version `2.0.0`, family `acceleration`, certification `approved`.

Subtracts the previous k-observation arithmetic change from the current one. Uses levels at t, t-k and t-2k.

Formula: `(x_t-x_(t-k))-(x_(t-k)-x_(t-2k))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_ACCEL"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **4**. Values are a single ordered numeric input series.

Legacy mapping: `base:accel.second_diff@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:98`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `accel.second_diff`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_accel_slope_change

**Slope Change** — version `2.0.0`, family `acceleration`, certification `approved`.

Subtracts the w-observation OLS slope ending k observations ago from the current w-observation OLS slope.

Formula: `slope_w(t)-slope_w(t-k)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SLOPE_CHANGE"`.
- `w` (observations): integer; minimum 3; maximum None; grid axis `"SLOPE_W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `per_observation`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2,"w":4}`, frequency `irregular` give final value **2**. Values are a single ordered numeric input series.

Legacy mapping: `base:accel.slope_change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:101`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `accel.slope_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_change_diff

**Difference** — version `2.0.0`, family `change`, certification `approved`.

Subtracts the level k observations earlier; the result remains in the original units.

Formula: `x_t - x_(t-k)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **17**. Values are a single ordered numeric input series.

Legacy mapping: `base:change.diff@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:71`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `change.diff`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_change_log

**Log Change** — version `2.0.0`, family `change`, certification `approved`.

Subtracts two natural-log levels k observations apart. Both endpoints must be strictly positive.

Formula: `log(x_t) - log(x_(t-k))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `log_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **0.461345566503**. Values are a single ordered numeric input series.

Legacy mapping: `base:change.log@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:73`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `change.log`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_change_pct

**Percent Change** — version `2.0.0`, family `change`, certification `approved`.

Divides the current level by the level k observations earlier and subtracts one. The output is a fraction (0.01 means 1%), not a value multiplied by 100. A zero old level fails; negative levels are not categorically rejected.

Formula: `x_t / x_(t-k) - 1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `fractional_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **0.586206896552**. Values are a single ordered numeric input series.

Legacy mapping: `base:change.pct@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:72`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `change.pct`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_distribution_iqr

**Interquartile Range** — version `2.0.0`, family `distribution`, certification `approved`.

Computes the 75th percentile minus the 25th percentile of the last w one-observation arithmetic differences, using linearly interpolated type-7 quantiles.

Formula: `Q75(W_w(delta_1 x))-Q25(W_w(delta_1 x))`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `preserve`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1.5**. Values are a single ordered numeric input series.

Legacy mapping: `base:distribution.iqr@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:116`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `distribution.iqr`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_distribution_kurtosis

**Rolling Excess Kurtosis** — version `2.0.0`, family `distribution`, certification `approved`.

Computes bias-adjusted sample excess kurtosis of one-observation arithmetic differences; the normal-reference excess is zero. It needs at least four changes and nonzero variance.

Formula: `n*(n+1)/((n-1)*(n-2)*(n-3))*sum(((y-mean(y))/sample_sd(y))^4)-3*(n-1)^2/((n-2)*(n-3)); y=W_w(delta_1 x), n=w`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 4; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **-1.2**. Values are a single ordered numeric input series.

Legacy mapping: `base:distribution.kurtosis@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:115`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `distribution.kurtosis`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_distribution_quantile_range

**Quantile Range** — version `2.0.0`, family `distribution`, certification `approved`.

Computes the high-minus-low type-7 quantile span of the last w arithmetic differences. Mathematical domain is 0<=low<high<=1; the approved finite legacy grid permits only (0.10,0.90) and (0.05,0.95).

Formula: `Q_high(W_w(delta_1 x))-Q_low(W_w(delta_1 x))`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `high` (probability): decimal; minimum 0; maximum 1; grid axis `["0.9","0.95"]`.
- `low` (probability): decimal; minimum 0; maximum 1; grid axis `["0.1","0.05"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.
- Relationships: 0 <= low < high <= 1.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `preserve`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"high":"0.9","low":"0.1","w":4}`, frequency `irregular` give final value **2.4**. Values are a single ordered numeric input series.

Legacy mapping: `base:distribution.quantile_range@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:117`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `distribution.quantile_range`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_distribution_quantile_skew

**Quantile Skewness** — version `2.0.0`, family `distribution`, certification `approved`.

Computes quartile-based skewness of one-observation arithmetic differences: the asymmetry of the median within the interquartile range. A zero IQR produces ZERO_RANGE.

Formula: `(Q75+Q25-2*Q50)/(Q75-Q25)`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_iqr`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **0**. Values are a single ordered numeric input series.

Legacy mapping: `base:distribution.quantile_skew@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:118`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `distribution.quantile_skew`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_distribution_skew

**Rolling Skewness** — version `2.0.0`, family `distribution`, certification `approved`.

Computes the adjusted sample skewness of one-observation arithmetic differences over w observations. It needs at least three changes and nonzero variance.

Formula: `n/((n-1)*(n-2))*sum(((y-mean(y))/sample_sd(y))^3); y=W_w(delta_1 x), n=w`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 3; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **0**. Values are a single ordered numeric input series.

Legacy mapping: `base:distribution.skew@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:114`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `distribution.skew`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_extreme_max_drawdown

**Maximum Relative Drawdown** — version `2.0.0`, family `extremes`, certification `approved`.

Tracks the running peak within the last w levels and returns the most negative relative decline from it. All levels in that window must be positive. The result is nonpositive and the peak does not predate the window.

Formula: `min_v(x_v/running_peak_v-1) over W_w`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range (-1,0] for finite strictly positive levels.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[10,8,12,6]`, parameters `{"w":4}`, frequency `irregular` give final value **-0.5**. Values are a single ordered numeric input series.

Legacy mapping: `base:extreme.max_drawdown@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:124`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `extreme.max_drawdown`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_extreme_new_high

**New High Indicator** — version `2.0.0`, family `extremes`, certification `approved`.

Returns 1 only when the current level is strictly greater than all preceding w levels, otherwise 0. Ties are not new highs.

Formula: `1[x_t>max(W^-_w)]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:extreme.new_high@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:120`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `extreme.new_high`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_extreme_new_low

**New Low Indicator** — version `2.0.0`, family `extremes`, certification `approved`.

Returns 1 only when the current level is strictly smaller than all preceding w levels, otherwise 0. Ties are not new lows.

Formula: `1[x_t<min(W^-_w)]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[4,3,2,1,0]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:extreme.new_low@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:121`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `extreme.new_low`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_extreme_range

**Rolling Range** — version `2.0.0`, family `extremes`, certification `approved`.

Subtracts the minimum from the maximum of the last w levels, including the current level. A zero range is a valid result here.

Formula: `max(W_w)-min(W_w)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `preserve`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **24**. Values are a single ordered numeric input series.

Legacy mapping: `base:extreme.range@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:119`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `extreme.range`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_extreme_time_since_high

**Time Since High** — version `2.0.0`, family `extremes`, certification `approved`.

Counts observations since the most recent occurrence of the maximum in the current-inclusive w-level window. A maximum at the current point gives 0; tied highs use the latest tie.

Formula: `observations since most recent max(W_w)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `count`; units rule `observation_count`; type `integer`; range Integer from0 throughw-1.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[5,4,5,3]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:extreme.time_since_high@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:122`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `extreme.time_since_high`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_extreme_time_since_low

**Time Since Low** — version `2.0.0`, family `extremes`, certification `approved`.

Counts observations since the most recent occurrence of the minimum in the current-inclusive w-level window. A current low gives 0; tied lows use the latest tie.

Formula: `observations since most recent min(W_w)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `count`; units rule `observation_count`; type `integer`; range Integer from0 throughw-1.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,1,3]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:extreme.time_since_low@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:123`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `extreme.time_since_low`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_level_log

**Log Level** — version `2.0.0`, family `level`, certification `approved`.

Takes the natural logarithm of the current level. Values at or below zero fail explicitly.

Formula: `log(x_t)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_only`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- None.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `log_level`; units rule `log_input`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{}`, frequency `irregular` give final value **3.82864139649**. Values are a single ordered numeric input series.

Legacy mapping: `base:level.log@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:70`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `level.log`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_level_raw

**Raw Level** — version `2.0.0`, family `level`, certification `approved`.

Passes the current numeric level through unchanged. This is the identity transformation, not a return or normalized score.

Formula: `x_t`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_only`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- None.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `preserve`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{}`, frequency `irregular` give final value **46**. Values are a single ordered numeric input series.

Legacy mapping: `base:level.raw@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:69`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `level.raw`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_momentum_sign_balance

**Direction Balance** — version `2.0.0`, family `momentum`, certification `approved`.

Averages the signs (-1, 0, +1) of the last w one-observation differences. Positive values indicate more positive than negative changes.

Formula: `mean(sign(delta_1 x)) over W_w`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:momentum.sign_balance@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:94`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `momentum.sign_balance`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_momentum_skip_diff

**Skip-Recent Difference** — version `2.0.0`, family `momentum`, certification `approved`.

Measures the arithmetic change from k observations ago to s observations ago, deliberately omitting the most recent s observations. Requires s < k.

Formula: `x_(t-s)-x_(t-k)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SKIP"`.
- `s` (observations): integer; minimum 1; maximum None; grid axis `"S_SKIP"`.
- Relationships: s < k.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":4,"s":1}`, frequency `irregular` give final value **21**. Values are a single ordered numeric input series.

Legacy mapping: `base:momentum.skip_diff@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:92`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `momentum.skip_diff`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_momentum_skip_return

**Skip-Recent Return** — version `2.0.0`, family `momentum`, certification `approved`.

Measures the fractional return from k observations ago to s observations ago. Requires s < k and a nonzero old endpoint.

Formula: `x_(t-s)/x_(t-k)-1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SKIP"`.
- `s` (observations): integer; minimum 1; maximum None; grid axis `"S_SKIP"`.
- Relationships: s < k.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `fractional_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":4,"s":1}`, frequency `irregular` give final value **1.3125**. Values are a single ordered numeric input series.

Legacy mapping: `base:momentum.skip_return@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:93`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `momentum.skip_return`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_persistence_diff_autocorr

**Difference Autocorrelation** — version `2.0.0`, family `persistence`, certification `approved`.

Computes Pearson correlation between two w-length sequences of one-observation differences separated by lag a. Uses w+a changes; a constant sequence fails.

Formula: `corr(delta_1 x_t, delta_1 x_(t-a)) over W_w`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `a` (observations): integer; minimum 1; maximum None; grid axis `"AUTOCORR_LAG"`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.
- Relationships: w >= 4*a.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"a":1,"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:persistence.diff_autocorr@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:125`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `persistence.diff_autocorr`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_persistence_sign

**Sign Persistence** — version `2.0.0`, family `persistence`, certification `approved`.

Averages products of consecutive change signs over w adjacent pairs. Positive values indicate persistent direction, negative values indicate reversals, and zero changes contribute zero.

Formula: `mean(sign(delta_1 x_t)*sign(delta_1 x_(t-1))) over W_w`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:persistence.sign@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:126`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `persistence.sign`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_persistence_sign_streak

**Signed Streak Length** — version `2.0.0`, family `persistence`, certification `approved`.

Counts the current uninterrupted run of same-sign one-observation changes, capped at w, and attaches that sign. A zero current change returns 0. It can return a shorter streak before a full w changes exist.

Formula: `current same-sign change streak capped at w`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive_capped_streak`. At least one valid change; walk backwards through same nonzero sign up to w; stop at opposite sign, zero or missing.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `count`; units rule `observation_count`; type `integer`; range Integer from-w throughw.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **4**. Values are a single ordered numeric input series.

Legacy mapping: `base:persistence.sign_streak@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:127`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `persistence.sign_streak`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_persistence_variance_ratio

**Variance Ratio** — version `2.0.0`, family `persistence`, certification `approved`.

Divides sample variance of overlapping k-observation arithmetic differences by k times sample variance of one-observation differences. The denominator uses w changes; the numerator uses w-k+1 overlapping changes within that span.

Formula: `var(delta_k x)/(k*var(delta_1 x))`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"VARIANCE_RATIO_K"`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"VARIANCE_RATIO_W"`.
- Relationships: w >= 4*k.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2,"w":8}`, frequency `irregular` give final value **1.55555555556**. Values are a single ordered numeric input series.

Legacy mapping: `base:persistence.variance_ratio@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:128`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. A zero long-change variance over a positive one-change variance now returns zero; only the denominator is required to be positive. This intentional version2 behavior differs from legacy zero-SD rejection.
Implementation: `data.transformations.numeric:calculate`, operation `persistence.variance_ratio`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_seasonal_bucket_deviation

**Calendar-Bucket Deviation** — version `2.0.0`, family `seasonality`, certification `approved`.

Subtracts the mean of prior nonmissing observations in the same calendar bucket from the current level. The history-year bound and bucket selection follow the implementation described below; this is not a general seasonal-adjustment model.

Formula: `x_t-mean(prior same-calendar-bucket observations)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `defined_seasonal_bucket`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `prior_same_calendar_bucket`. Prior same calendar bucket, year>=currentyear-history_years; filter missing values; both seasonal methods need at least2 prior; zscore also needs positive sample SD.

Parameters:
- `history_years` (calendar_years): integer; minimum 1; maximum None; grid axis `[3,5,10]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,7]`, parameters `{"history_years":3}`, frequency `monthly` give final value **5**. Values are a single ordered numeric input series.
Example reference times: `["2020-01-01","2021-01-01","2022-01-01"]`.

Legacy mapping: `base:seasonal.bucket_deviation@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:135`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `seasonal.bucket_deviation`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_seasonal_bucket_zscore

**Calendar-Bucket Z-Score** — version `2.0.0`, family `seasonality`, certification `approved`.

Divides that same-calendar-bucket deviation by the sample SD of the selected bucket history. Requires at least two matching historical observations and nonzero variance.

Formula: `same-bucket deviation/sd(prior same-bucket observations)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `defined_seasonal_bucket`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `prior_same_calendar_bucket`. Prior same calendar bucket, year>=currentyear-history_years; filter missing values; both seasonal methods need at least2 prior; zscore also needs positive sample SD.

Parameters:
- `history_years` (calendar_years): integer; minimum 1; maximum None; grid axis `[5,10]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,7]`, parameters `{"history_years":3}`, frequency `monthly` give final value **3.53553390593**. Values are a single ordered numeric input series.
Example reference times: `["2020-01-01","2021-01-01","2022-01-01"]`.

Legacy mapping: `base:seasonal.bucket_zscore@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:136`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `seasonal.bucket_zscore`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_shock_change_percentile

**Change Percentile** — version `2.0.0`, family `shock`, certification `approved`.

Ranks the current k-observation arithmetic difference against the preceding w such differences, with half weight for ties, then maps the percentile to [-1, 1].

Formula: `2*percentile_rank(delta_k x_t; W^-_w(delta_k x))-1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SHORT"`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.
- Relationships: k < w.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":1,"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:shock.change_percentile@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:97`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `shock.change_percentile`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_shock_change_zscore

**Change Z-Score** — version `2.0.0`, family `shock`, certification `approved`.

Subtracts the mean of the preceding w k-observation arithmetic differences from the current such difference, then divides by their sample SD.

Formula: `(delta_k x_t-mean(W^-_w(delta_k x))) / sd(W^-_w(delta_k x))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SHORT"`.
- `w` (observations): integer; minimum 2; maximum None; grid axis `"W_STAT"`.
- Relationships: k < w.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":1,"w":4}`, frequency `irregular` give final value **1.9364916731**. Values are a single ordered numeric input series.

Legacy mapping: `base:shock.change_zscore@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:96`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `shock.change_zscore`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_shock_standardized_change

**Standardized Change** — version `2.0.0`, family `shock`, certification `approved`.

Scales the current k-observation arithmetic difference by the sample SD of the preceding w k-observation differences. Does not subtract their mean.

Formula: `delta_k x_t / sd(W^-_w(delta_k x))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SHORT"`.
- `w` (observations): integer; minimum 2; maximum None; grid axis `"W_STAT"`.
- Relationships: k < w.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":1,"w":4}`, frequency `irregular` give final value **6.97137002317**. Values are a single ordered numeric input series.

Legacy mapping: `base:shock.standardized_change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:95`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `shock.standardized_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_smooth_ema

**Exponential Moving Average** — version `2.0.0`, family `smoothing`, certification `approved`.

Smooths levels using exponential weights with half-life h. Seeds the state with the first value of a consecutive nonmissing run and first emits after h observations.

Formula: `EMA_h(x)_t`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `h` (observations): integer; minimum 1; maximum None; grid axis `"HALF_LIFE"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `preserve`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,5]`, parameters `{"h":1}`, frequency `irregular` give final value **3.5**. Values are a single ordered numeric input series.

Legacy mapping: `base:smooth.ema@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:80`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `smooth.ema`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_smooth_ew_change

**EW Change** — version `2.0.0`, family `smoothing`, certification `approved`.

Applies the same exponentially weighted smoother to one-observation arithmetic differences. This is a smoothed change, not a return.

Formula: `EMA_h(delta_1 x)_t`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `h` (observations): integer; minimum 1; maximum None; grid axis `"HALF_LIFE"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,3]`, parameters `{"h":1}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:smooth.ew_change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:81`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `smooth.ew_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_smooth_median

**Rolling Median** — version `2.0.0`, family `smoothing`, certification `approved`.

Takes the median of the last w levels, including the current level.

Formula: `median(W_w)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `preserve`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **33**. Values are a single ordered numeric input series.

Legacy mapping: `base:smooth.median@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:79`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `smooth.median`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_smooth_sma

**Simple Moving Average** — version `2.0.0`, family `smoothing`, certification `approved`.

Averages the last w levels, including the current level.

Formula: `mean(W_w)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `preserve`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **33.5**. Values are a single ordered numeric input series.

Legacy mapping: `base:smooth.sma@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:78`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `smooth.sma`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_standard_ew_zscore

**EW Z-Score** — version `2.0.0`, family `standardization`, certification `approved`.

Compares the current value with exponentially weighted first and second moments calculated through the previous observation. Uses sqrt(EW[x²] - EW[x]²), without the sample-SD correction. Requires h prior consecutive nonmissing observations and positive variance.

Formula: `(x_t - EWMean_(t-1,h)) / sqrt(EWVar_(t-1,h))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `h` (observations): integer; minimum 1; maximum None; grid axis `"HALF_LIFE"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,5]`, parameters `{"h":1}`, frequency `irregular` give final value **3**. Values are a single ordered numeric input series.

Legacy mapping: `base:standard.ew_zscore@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:77`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Version2 uses the algebraically equivalent stable centered exponential-variance recurrence. This avoids cancellation for large offsets where legacy raw second-moment subtraction could lose variance; a 1e12-offset independent fixture verifies the behavior.
Implementation: `data.transformations.numeric:calculate`, operation `standard.ew_zscore`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_standard_rank_centered

**Centered Rolling Rank** — version `2.0.0`, family `standardization`, certification `approved`.

Ranks the current level against the preceding w levels, gives tied values half weight, and rescales the percentile to [-1, 1]. The current level is excluded from the reference sample.

Formula: `2 * percentile_rank(x_t; W^-_w) - 1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:standard.rank_centered@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:76`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `standard.rank_centered`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_standard_robust_z

**Robust Z-Score** — version `2.0.0`, family `standardization`, certification `approved`.

Compares the current level with the preceding-window median, scaled by 1.4826 times the median absolute deviation around that median. A zero MAD fails.

Formula: `(x_t - median(W^-_w)) / (1.4826 * MAD(W^-_w))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_mad`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **2.12724008758**. Values are a single ordered numeric input series.

Legacy mapping: `base:standard.robust_z@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:75`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `standard.robust_z`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_standard_zscore

**Rolling Z-Score** — version `2.0.0`, family `standardization`, certification `approved`.

Compares the current level with the mean and sample standard deviation of the preceding w levels. The reference window excludes the current observation.

Formula: `(x_t - mean(W^-_w)) / sd(W^-_w)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 2; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **2.2086305215**. Values are a single ordered numeric input series.

Legacy mapping: `base:standard.zscore@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:74`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `standard.zscore`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_threshold_above_mean

**Above Historical Mean** — version `2.0.0`, family `threshold`, certification `approved`.

Returns 1 if the current level is strictly above the mean of the preceding w levels. The current level is excluded from the threshold.

Formula: `1[x_t>mean(W^-_w)]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:threshold.above_mean@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:131`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `threshold.above_mean`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_threshold_above_median

**Above Historical Median** — version `2.0.0`, family `threshold`, certification `approved`.

Returns 1 if the current level is strictly above the median of the preceding w levels.

Formula: `1[x_t>median(W^-_w)]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:threshold.above_median@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:132`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `threshold.above_median`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_threshold_above_quantile

**Above Historical Quantile** — version `2.0.0`, family `threshold`, certification `approved`.

Returns 1 if the current level strictly exceeds a chosen upper quantile of the preceding w levels: 0.75, 0.90 or 0.95.

Formula: `1[x_t>Q_q(W^-_w)]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `q` (probability): decimal; minimum 0; maximum 1; grid axis `["0.75","0.9","0.95"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.
- Relationships: 0 <= q <= 1.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"q":"0.75","w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:threshold.above_quantile@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:133`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `threshold.above_quantile`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_threshold_below_quantile

**Below Historical Quantile** — version `2.0.0`, family `threshold`, certification `approved`.

Returns 1 if the current level is strictly below a chosen lower quantile of the preceding w levels: 0.25, 0.10 or 0.05.

Formula: `1[x_t<Q_q(W^-_w)]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `q` (probability): decimal; minimum 0; maximum 1; grid axis `["0.25","0.1","0.05"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.
- Relationships: 0 <= q <= 1.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,3,4,0]`, parameters `{"q":"0.25","w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:threshold.below_quantile@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:134`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `threshold.below_quantile`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_threshold_positive_change

**Positive Change** — version `2.0.0`, family `threshold`, certification `approved`.

Returns 1 if the current k-observation arithmetic difference is strictly positive, otherwise 0.

Formula: `1[delta_k x_t>0]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_ACCEL"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:threshold.positive_change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:130`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `threshold.positive_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_threshold_positive_level

**Positive Level** — version `2.0.0`, family `threshold`, certification `approved`.

Returns 1 if the current level is strictly above zero, otherwise 0.

Formula: `1[x_t>0]`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_only`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- None.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:threshold.positive_level@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:129`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `threshold.positive_level`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_breakout_position

**Breakout Position** — version `2.0.0`, family `trend`, certification `approved`.

Locates the current level relative to the minimum and maximum of the preceding w levels. It can be below 0 or above 1 because the current observation is excluded from the range.

Formula: `(x_t-min(W^-_w)) / (max(W^-_w)-min(W^-_w))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_range`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1.42857142857**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.breakout_position@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:91`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.breakout_position`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_efficiency_ratio

**Trend Efficiency Ratio** — version `2.0.0`, family `trend`, certification `approved`.

Divides the signed net displacement over w changes by the sum of their absolute changes. Requires w+1 consecutive levels; returns between -1 and 1 and fails on a zero-length path.

Formula: `(x_t-x_(t-w)) / sum_i(abs(delta_1 x_i))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_path_length`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.efficiency_ratio@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:90`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.efficiency_ratio`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_ema_crossover

**EMA Crossover** — version `2.0.0`, family `trend`, certification `approved`.

Divides the fast current-inclusive exponential moving average by the slow one and subtracts one. The parameters named fast and slow are EMA half-lives even though their grid alias is W.

Formula: `EMA_fast(x)_t / EMA_slow(x)_t - 1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `fast` (observations): integer; minimum 1; maximum None; grid axis `"W"`.
- `slow` (observations): integer; minimum 1; maximum None; grid axis `"W"`.
- Relationships: fast < slow.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,5]`, parameters `{"fast":1,"slow":2}`, frequency `irregular` give final value **0.353553390593**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.ema_crossover@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:87`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ema_crossover`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_ema_distance

**EMA Distance** — version `2.0.0`, family `trend`, certification `approved`.

Subtracts the current-inclusive exponential moving average from the current level.

Formula: `x_t - EMA_h(x)_t`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `h` (observations): integer; minimum 1; maximum None; grid axis `"HALF_LIFE"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,5]`, parameters `{"h":1}`, frequency `irregular` give final value **1.5**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.ema_distance@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:84`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ema_distance`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_ema_relative

**Relative EMA Distance** — version `2.0.0`, family `trend`, certification `approved`.

Divides the current level by its current-inclusive exponential moving average and subtracts one. A zero EMA fails.

Formula: `x_t / EMA_h(x)_t - 1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `h` (observations): integer; minimum 1; maximum None; grid axis `"HALF_LIFE"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,5]`, parameters `{"h":1}`, frequency `irregular` give final value **0.428571428571**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.ema_relative@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:85`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ema_relative`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_ma_crossover

**MA Crossover** — version `2.0.0`, family `trend`, certification `approved`.

Divides the fast current-inclusive simple moving average by the slow one and subtracts one. Only seven specified fast/slow horizon pairings are in the grid.

Formula: `MA_fast(x)_t / MA_slow(x)_t - 1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `fast` (observations): integer; minimum 1; maximum None; grid axis `"W"`.
- `slow` (observations): integer; minimum 1; maximum None; grid axis `"W"`.
- Relationships: fast < slow.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"fast":2,"slow":4}`, frequency `irregular` give final value **0.238805970149**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.ma_crossover@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:86`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ma_crossover`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_ma_distance

**Moving-Average Distance** — version `2.0.0`, family `trend`, certification `approved`.

Subtracts the current-inclusive simple moving average from the current level; the distance is in original units.

Formula: `x_t - MA_w(x)_t`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **12.5**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.ma_distance@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:82`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ma_distance`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_ma_relative

**Relative MA Distance** — version `2.0.0`, family `trend`, certification `approved`.

Divides the current level by its current-inclusive simple moving average and subtracts one. A zero moving average fails.

Formula: `x_t / MA_w(x)_t - 1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **0.373134328358**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.ma_relative@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:83`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ma_relative`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_slope

**Rolling Linear Slope** — version `2.0.0`, family `trend`, certification `approved`.

Fits ordinary least squares to the last w levels against indices 0 through w-1. The result is a change in level per observation, not per calendar day. Requires at least three points.

Formula: `OLS slope of x against observation index over W_w`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 3; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `per_observation`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **8**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.slope@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:88`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.slope`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_trend_slope_tstat

**Slope T-Statistic** — version `2.0.0`, family `trend`, certification `approved`.

Divides that OLS slope by its residual-based standard error, using n-2 degrees of freedom. A zero standard error fails rather than producing infinity.

Formula: `rolling OLS slope / standard error(slope)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `defined_standard_error`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 3; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **25.2982212813**. Values are a single ordered numeric input series.

Legacy mapping: `base:trend.slope_tstat@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:89`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.slope_tstat`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_abs_change

**Mean Absolute Change** — version `2.0.0`, family `volatility`, certification `approved`.

Averages the absolute last w one-observation changes on the selected diff, pct or log basis. Zero is a valid output for a constant series.

Formula: `mean(W_w(abs(y)))`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `change_basis`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"basis":"diff","w":4}`, frequency `irregular` give final value **7.5**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.abs_change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:106`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.abs_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_asymmetry

**Volatility Asymmetry** — version `2.0.0`, family `volatility`, certification `approved`.

Divides downside semivolatility by upside semivolatility over the same window; zero upside fails.

Formula: `downside_vol_w/upside_vol_w`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[10,8,11,7,9]`, parameters `{"basis":"diff","w":4}`, frequency `irregular` give final value **1.24034734589**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.asymmetry@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:111`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.asymmetry`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_change

**Volatility Change** — version `2.0.0`, family `volatility`, certification `approved`.

Subtracts the rolling sample-SD volatility ending k observations ago from the current rolling volatility, using the same w and change basis.

Formula: `vol_w(t)-vol_w(t-k)`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SLOPE_CHANGE"`.
- `w` (observations): integer; minimum 2; maximum None; grid axis `"VOL_W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `change_basis`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"basis":"diff","k":2,"w":4}`, frequency `irregular` give final value **0**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.change@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:107`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_diff_sd

**Difference Volatility** — version `2.0.0`, family `volatility`, certification `approved`.

Computes sample standard deviation of the last w one-observation arithmetic differences. A complete constant change window returns zero descriptive volatility. Fractional changes require nonzero denominators and log changes require positive operands.

Formula: `sd(W_w(delta_1 x))`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 2; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `preserve`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1.29099444874**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.diff_sd@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:102`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.diff_sd`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_downside

**Downside Semivolatility** — version `2.0.0`, family `volatility`, certification `approved`.

Takes the root mean square of the negative parts of the last w changes, treating positive changes as zero. The denominator counts the whole window, not only negative observations.

Formula: `sqrt(mean(W_w(min(y,0)^2)))`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `change_basis`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[10,8,11,7,9]`, parameters `{"basis":"diff","w":4}`, frequency `irregular` give final value **2.2360679775**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.downside@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:109`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.downside`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_ewma

**EW Volatility** — version `2.0.0`, family `volatility`, certification `approved`.

Computes the square root of the exponentially weighted mean of squared one-observation changes on the chosen basis. This is an uncentered root-mean-square, not an EW sample SD.

Formula: `sqrt(EWMean_h(y^2))`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `h` (observations): integer; minimum 1; maximum None; grid axis `"HALF_LIFE"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `change_basis`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,2]`, parameters `{"basis":"diff","h":1}`, frequency `irregular` give final value **1.58113883008**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.ewma@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:105`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.ewma`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_log_sd

**Log-Change Volatility** — version `2.0.0`, family `volatility`, certification `approved`.

Computes sample standard deviation of the last w one-observation logarithmic changes. A complete constant change window returns zero descriptive volatility. Fractional changes require nonzero denominators and log changes require positive operands.

Formula: `sd(W_w(log_change_1))`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 2; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `dimensionless`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **0.0434822908034**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.log_sd@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:104`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.log_sd`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_pct_sd

**Percent-Change Volatility** — version `2.0.0`, family `volatility`, certification `approved`.

Computes sample standard deviation of the last w one-observation fractional changes. A complete constant change window returns zero descriptive volatility. Fractional changes require nonzero denominators and log changes require positive operands.

Formula: `sd(W_w(pct_change_1))`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 2; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `dimensionless`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **0.0569262806071**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.pct_sd@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:103`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.pct_sd`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_ratio

**Volatility Ratio** — version `2.0.0`, family `volatility`, certification `approved`.

Divides short-window rolling sample standard deviation by long-window deviation on the selected change basis. It does not subtract one. Zero long-window deviation is undefined; a zero numerator over a positive denominator is valid.

Formula: `vol_fast(t)/vol_slow(t)`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_denominator`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `fast` (observations): integer; minimum 2; maximum None; grid axis `"W"`.
- `slow` (observations): integer; minimum 2; maximum None; grid axis `"W"`.
- Relationships: fast < slow.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"basis":"diff","fast":2,"slow":4}`, frequency `irregular` give final value **0.547722557505**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.ratio@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:108`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.ratio`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_vol_upside

**Upside Semivolatility** — version `2.0.0`, family `volatility`, certification `approved`.

Takes the root mean square of the positive parts of the last w changes, treating negative changes as zero. The denominator counts the whole window.

Formula: `sqrt(mean(W_w(max(y,0)^2)))`.

Input treatment: `change_basis`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `change_basis`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[10,8,11,7,9]`, parameters `{"basis":"diff","w":4}`, frequency `irregular` give final value **1.80277563773**. Values are a single ordered numeric input series.

Legacy mapping: `base:vol.upside@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:110`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `vol.upside`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_volscale_diff

**Volatility-Scaled Difference** — version `2.0.0`, family `volatility_scaling`, certification `approved`.

Divides the current k-observation arithmetic difference by the sample SD of the most recent w one-observation arithmetic differences, including the current difference.

Formula: `delta_k x_t / sd(W_w(delta_1 x))`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K_SHORT"`.
- `w` (observations): integer; minimum 2; maximum None; grid axis `"VOL_W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2,"w":4}`, frequency `irregular` give final value **13.1681433771**. Values are a single ordered numeric input series.

Legacy mapping: `base:volscale.diff@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:112`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `volscale.diff`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_BASE_volscale_trend

**Volatility-Scaled Trend** — version `2.0.0`, family `volatility_scaling`, certification `approved`.

Divides the current level’s distance from its w-observation moving average by the sample SD of the last v one-observation arithmetic differences. Both reference windows include the current observation.

Formula: `(x_t-MA_w(x)_t) / sd(W_v(delta_1 x))`.

Input treatment: `difference`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `v` (observations): integer; minimum 2; maximum None; grid axis `"VOL_W"`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"TREND_W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_BASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"v":4,"w":4}`, frequency `irregular` give final value **9.68245836552**. Values are a single ordered numeric input series.

Legacy mapping: `base:volscale.trend@0.1.0`, status `versioned_adaptation`.
Source evidence: `Data/src/point_in_time_data/transformation_catalog.py:113`, SHA-256 `49357fdb19acf85505f939b07630bc1c2ce86412e14fe0268360ae07600a4d6b`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `volscale.trend`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_core_lag

**Causal Lag** — version `2.0.0`, family `level`, certification `approved`.

Causal Lag applies directly to supplied values. No hidden differencing or return conversion.

Formula: `x_(t-k)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `"K"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `preserve`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **29**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused.
Implementation: `data.transformations.numeric:calculate`, operation `core.lag`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_core_rolling_sum

**Rolling Sum** — version `2.0.0`, family `smoothing`, certification `approved`.

Rolling Sum applies directly to supplied values. No hidden differencing or return conversion.

Formula: `sum(W_w(x))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **134**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused.
Implementation: `data.transformations.numeric:calculate`, operation `core.rolling_sum`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_core_sample_sd

**Direct Sample Standard Deviation** — version `2.0.0`, family `volatility`, certification `approved`.

Direct Sample Standard Deviation applies directly to supplied values. No hidden differencing or return conversion.

Formula: `sqrt(sum((x-mean(W_w))^2)/(w-1))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 2; maximum None; grid axis `"W"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `volatility`; units rule `preserve`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **10.3440804328**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused. Descriptive sample standard deviation may equal zero; division by zero deviation remains undefined. This is an intentional version2 semantic change.
Implementation: `data.transformations.numeric:calculate`, operation `core.sample_sd`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_input_distribution_iqr

**Direct Input Interquartile Range** — version `2.0.0`, family `input_distribution`, certification `approved`.

Direct Input Interquartile Range applies directly to supplied values. No hidden differencing or return conversion.

Formula: `Q75(W_w(x))-Q25(W_w(x))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `preserve`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,8]`, parameters `{"w":4}`, frequency `irregular` give final value **3.25**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused.
Implementation: `data.transformations.numeric:calculate`, operation `input_distribution.iqr`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_input_distribution_kurtosis

**Direct Input Excess Kurtosis** — version `2.0.0`, family `input_distribution`, certification `approved`.

Direct Input Excess Kurtosis applies directly to supplied values. No hidden differencing or return conversion.

Formula: `n*(n+1)/((n-1)*(n-2)*(n-3))*sum(((x-mean)/sample_sd)^4)-3*(n-1)^2/((n-2)*(n-3)) on W_w(x)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 4; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,8]`, parameters `{"w":4}`, frequency `irregular` give final value **0.757655954631**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused.
Implementation: `data.transformations.numeric:calculate`, operation `input_distribution.kurtosis`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_input_distribution_quantile_range

**Direct Input Quantile Range** — version `2.0.0`, family `input_distribution`, certification `approved`.

Direct Input Quantile Range applies directly to supplied values. No hidden differencing or return conversion.

Formula: `Q_high(W_w(x))-Q_low(W_w(x))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `high` (probability): decimal; minimum 0; maximum 1; grid axis `["0.9","0.95"]`.
- `low` (probability): decimal; minimum 0; maximum 1; grid axis `["0.1","0.05"]`.
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.
- Relationships: 0 <= low < high <= 1.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `preserve`; type `number`; range [0,infinity) finite values only.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,8]`, parameters `{"high":"0.9","low":"0.1","w":4}`, frequency `irregular` give final value **5.5**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused.
Implementation: `data.transformations.numeric:calculate`, operation `input_distribution.quantile_range`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_input_distribution_quantile_skew

**Direct Input Quantile Skewness** — version `2.0.0`, family `input_distribution`, certification `approved`.

Direct Input Quantile Skewness applies directly to supplied values. No hidden differencing or return conversion.

Formula: `(Q75+Q25-2*Q50)/(Q75-Q25) on W_w(x)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,8]`, parameters `{"w":4}`, frequency `irregular` give final value **0.230769230769**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused.
Implementation: `data.transformations.numeric:calculate`, operation `input_distribution.quantile_skew`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_CORE_input_distribution_skew

**Direct Input Skewness** — version `2.0.0`, family `input_distribution`, certification `approved`.

Direct Input Skewness applies directly to supplied values. No hidden differencing or return conversion.

Formula: `n/((n-1)*(n-2))*sum(((x-mean)/sample_sd)^3) on W_w(x)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 3; maximum None; grid axis `"W_STAT"`.

Approved finite grid policy: `POL_TRANSFORM_GRID_CORE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,8]`, parameters `{"w":4}`, frequency `irregular` give final value **1.13762436696**. Values are a single ordered numeric input series.

New primitive from the bounded gap check. It does not replace or rename a difference-based operator.

Versioned differences: New explicit direct-input primitive; no legacy identity is reused.
Implementation: `data.transformations.numeric:calculate`, operation `input_distribution.skew`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_accel_log_change

**Price Log-Change Acceleration** — version `2.0.0`, family `acceleration`, certification `approved`.

Subtracts the log change ending k observations ago from the current k-observation log change. All required endpoints must be positive.

Formula: `log_change_k(t)-log_change_k(t-k)`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `log_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **-0.133361541244**. Values are a single ordered numeric input series.

Legacy mapping: `price:accel.log_change@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `7fa652c8139bd63bfb659b4e9b205436505676fe11d771d41ae8faf718977154`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `accel.log_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_accel_pct_change

**Price Percent-Change Acceleration** — version `2.0.0`, family `acceleration`, certification `approved`.

Subtracts the fractional return ending k observations ago from the current k-observation fractional return. Required denominators must be nonzero.

Formula: `pct_change_k(t)-pct_change_k(t-k)`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `fractional_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **-0.226293103448**. Values are a single ordered numeric input series.

Legacy mapping: `price:accel.pct_change@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `d642864752d06f068f41d6a9fa4b7706cf3830710eac1e5d0498e09ccdf83ea8`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `accel.pct_change`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_change_log

**Price Log Change** — version `2.0.0`, family `change`, certification `approved`.

Subtracts two natural-log levels k observations apart. Both endpoints must be strictly positive.

Formula: `log(P_t/P_(t-k))`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `log_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **0.461345566503**. Values are a single ordered numeric input series.

Legacy mapping: `price:change.log@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `901db808b001f6042f7d29f2e7e38f9220cb10e04c181e0b8868709b020e0fd6`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `change.log`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_change_pct

**Price Percent Change** — version `2.0.0`, family `change`, certification `approved`.

Divides the current level by the level k observations earlier and subtracts one. The output is a fraction (0.01 means 1%), not a value multiplied by 100. A zero old level fails; negative levels are not categorically rejected.

Formula: `P_t/P_(t-k)-1`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `fractional_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **0.586206896552**. Values are a single ordered numeric input series.

Legacy mapping: `price:change.pct@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `5411a14296b5aac90f6e5d190f1d355c67097aef3228dc0724e87aa0f513187f`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `change.pct`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_extreme_new_high

**Price New High Indicator** — version `2.0.0`, family `extremes`, certification `approved`.

Returns 1 only when the current level is strictly greater than all preceding w levels, otherwise 0. Ties are not new highs.

Formula: `1[P_t>max(P_(t-w)..P_(t-1))]`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `[2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `binary`; range {0,1}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `price:extreme.new_high@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `0a76b79456d21197892a7bd61b8e6269887fe98c6f2200c5c41ec48022c51b79`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `extreme.new_high`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_momentum_sign_balance

**Price Direction Balance** — version `2.0.0`, family `momentum`, certification `approved`.

Averages the signs (-1, 0, +1) of the last w one-observation differences. Positive values indicate more positive than negative changes.

Formula: `mean(sign(P_i-P_(i-1)), i=t-w+1..t)`.

Input treatment: `difference`. Accepted value semantics: `price`.
Input domain requirements: `numeric_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range [-1,1] when defined.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1**. Values are a single ordered numeric input series.

Legacy mapping: `price:momentum.sign_balance@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `abbbc4a7ac87feb3aa907d01d6274f19a1b4f146a9aac67251656381200368a9`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `momentum.sign_balance`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_price_log_return_shape

**Price Log Return Shape** — version `2.0.0`, family `price`, certification `approved`.

Price Log Return Shape. log(P_t/P_(t-short)) - log(P_t/P_(t-long)).

Formula: `log(P_t/P_(t-short)) - log(P_t/P_(t-long))`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`, `short_less_than_long`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `long` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.
- `short` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.
- Relationships: short < long.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `log_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"long":2,"short":1}`, frequency `irregular` give final value **-0.243622082658**. Values are a single ordered numeric input series.

Legacy mapping: `price:price.log_return_shape@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `7d491bcb9054ecd051a4756e0f4443142524b0a6bed74bac02977e773dd5d408`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `price.log_return_shape`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_price_oriented_new_low

**Price Oriented New Low** — version `2.0.0`, family `price`, certification `approved`.

Price Oriented New Low. -1[P_t < min(P_(t-w)..P_(t-1))].

Formula: `-1[P_t < min(P_(t-w)..P_(t-1))]`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `numeric_input`, `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `[2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `indicator`; units rule `dimensionless`; type `integer`; range {-1,0}.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[4,3,2,1]`, parameters `{"w":3}`, frequency `irregular` give final value **-1**. Values are a single ordered numeric input series.

Legacy mapping: `price:price.oriented_new_low@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `ffc0b03fc25d8c71e82b05720ae3b78644783eb52dc374e64b6bc001e9301f60`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `price.oriented_new_low`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_price_vol_normalized_log_return

**Price Vol Normalized Log Return** — version `2.0.0`, family `price`, certification `approved`.

Price Vol Normalized Log Return. log(P_t/P_(t-k)) / sd(log(P_i/P_(i-1)), i=t-w+1..t).

Formula: `log(P_t/P_(t-k)) / sd(log(P_i/P_(i-1)), i=t-w+1..t)`.

Input treatment: `change_basis`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.
- `w` (observations): integer; minimum 2; maximum None; grid axis `[21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2,"w":4}`, frequency `irregular` give final value **10.6099646081**. Values are a single ordered numeric input series.

Legacy mapping: `price:price.vol_normalized_log_return@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `b20569d963b62c87c5ade63c159b83aeda6ab1f2a74c63b826af26ab3abfd08c`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `price.vol_normalized_log_return`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_standard_zscore

**Price Rolling Z-Score** — version `2.0.0`, family `standardization`, certification `approved`.

Compares the current level with the mean and sample standard deviation of the preceding w levels. The reference window excludes the current observation.

Formula: `(P_t-mean(P_(t-w)..P_(t-1)))/sd(history)`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `numeric_input`, `nonzero_variance`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 2; maximum None; grid axis `[2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **2.2086305215**. Values are a single ordered numeric input series.

Legacy mapping: `price:standard.zscore@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `8e333c69fc70ed9a58d6af37cb9dc098e3cd27f8e7fe5649a481f58a5b99ecf5`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `standard.zscore`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_trend_breakout_position

**Price Breakout Position** — version `2.0.0`, family `trend`, certification `approved`.

Locates the current level relative to the minimum and maximum of the preceding w levels. It can be below 0 or above 1 because the current observation is excluded from the range.

Formula: `(P_t-min(P_(t-w)..P_(t-1)))/(max-min)`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `numeric_input`, `nonzero_range`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `[2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **1.42857142857**. Values are a single ordered numeric input series.

Legacy mapping: `price:trend.breakout_position@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `4f3afa7e6b0b6ee0b722e7f0802806de5e45a144782323ced4cf49b60bb122de`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.breakout_position`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_trend_ema_crossover

**Price EMA Crossover** — version `2.0.0`, family `trend`, certification `approved`.

Divides the fast current-inclusive exponential moving average by the slow one and subtracts one. The parameters named fast and slow are EMA half-lives even though their grid alias is W.

Formula: `EMA_fast(P)_t/EMA_slow(P)_t-1`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`, `fast_less_than_slow`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `fast` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.
- `slow` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.
- Relationships: fast < slow.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,5]`, parameters `{"fast":1,"slow":2}`, frequency `irregular` give final value **0.353553390593**. Values are a single ordered numeric input series.

Legacy mapping: `price:trend.ema_crossover@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `ca294354e244856ef940103f4b5719dd47cf60f03c8bd972daf3eb4eb5d14aab`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ema_crossover`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_trend_ema_relative

**Price Relative EMA Distance** — version `2.0.0`, family `trend`, certification `approved`.

Divides the current level by its current-inclusive exponential moving average and subtracts one. A zero EMA fails.

Formula: `P_t/EMA_h(P)_t-1`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Exponential first-value seed, half-life h (or fast/slow), resets on invalid/missing; emit after h consecutive inputs; EW zscore needs h prior valid moments. Change inputs need their extra preceding level.

Parameters:
- `h` (observations): integer; minimum 1; maximum None; grid axis `[2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,3,5]`, parameters `{"h":1}`, frequency `irregular` give final value **0.428571428571**. Values are a single ordered numeric input series.

Legacy mapping: `price:trend.ema_relative@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `12b88f3630e55b3dd2dbe262128ac317b95ed0fa2423d4b6cec6160357a66b65`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ema_relative`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_trend_ma_crossover

**Price MA Crossover** — version `2.0.0`, family `trend`, certification `approved`.

Divides the fast current-inclusive simple moving average by the slow one and subtracts one. Only seven specified fast/slow horizon pairings are in the grid.

Formula: `MA_fast(P)_t/MA_slow(P)_t-1`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`, `fast_less_than_slow`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `fast` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.
- `slow` (observations): integer; minimum 1; maximum None; grid axis `[1,2,5,10,21,42,63,126,252]`.
- Relationships: fast < slow.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"fast":2,"slow":4}`, frequency `irregular` give final value **0.238805970149**. Values are a single ordered numeric input series.

Legacy mapping: `price:trend.ma_crossover@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `879bba8d2e8fb2dcc798bc483dc6950732d849aa0cbea34be9759c692d588a2b`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ma_crossover`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_trend_ma_relative

**Price Relative MA Distance** — version `2.0.0`, family `trend`, certification `approved`.

Divides the current level by its current-inclusive simple moving average and subtracts one. A zero moving average fails.

Formula: `P_t/MA_w(P)_t-1`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `positive_input`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `[2,5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **0.373134328358**. Values are a single ordered numeric input series.

Legacy mapping: `price:trend.ma_relative@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `6c58b9fb362dbdb9c82e7757ede9721c25bebfc75d8816e16b5283300b0fb2c4`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Positive-price requirements are enforced for required operands; version1 delegated aliases did not consistently enforce their declared price domain.
Implementation: `data.transformations.numeric:calculate`, operation `trend.ma_relative`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_PRICE_trend_slope_tstat

**Price Slope T-Statistic** — version `2.0.0`, family `trend`, certification `approved`.

Divides that OLS slope by its residual-based standard error, using n-2 degrees of freedom. A zero standard error fails rather than producing infinity.

Formula: `trailing OLS price slope / standard error`.

Input treatment: `direct`. Accepted value semantics: `price`.
Input domain requirements: `numeric_input`, `defined_standard_error`.
Temporal mode: `reference_state`; required capabilities: canonical single-series history.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 3; maximum None; grid axis `[5,10,21,42,63,126,252]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_PRICE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **25.2982212813**. Values are a single ordered numeric input series.

Legacy mapping: `price:trend.slope_tstat@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `52c5a71777095a52ee853cdcb7b71fcab0d999e440ea4041d48205252fa18701`.
Source evidence: `Data/src/point_in_time_data/price_technical_transformations.py:1`, SHA-256 `1bfc8106da42def2df6552200883af3e6b227e503038257fda3558c9e4e2962e`.
Source evidence: `Data/src/point_in_time_data/transformations.py:1`, SHA-256 `dce46b09527b55886389f6b3b57e71e85a35e4cc31ba31f4e58f84823b1bdc36`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped.
Implementation: `data.transformations.numeric:calculate`, operation `trend.slope_tstat`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_92_nonrelease_registrations_have_defined_independent_fixture`.

### TR_RELEASE_change_diff

**Release Change Diff** — version `2.0.0`, family `change`, certification `approved`.

both operands come from the state knowable at the same release event

Formula: `x_t^(v_t)-x_(t-k)^(v_t)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `release_state`; required capabilities: revision_history, release_events.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_RELEASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `difference`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **17**. Values represent reference history selected from one explicitly anchored release state; earlier operands include only revisions known at that event.

Legacy mapping: `release:release.change_diff@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `fae7aedd5c67d7e16464eb0be80dde0a4503692b07d8edf84e9e2fa8a4a3ab1c`.
Source evidence: `Data/src/point_in_time_data/alfred_release_coherent.py:1`, SHA-256 `95d5ae51e180da336366809c567a35e91f7675a4a9b25acdd4e47451e94c28c4`.
Source evidence: `Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json:1`, SHA-256 `0cd0d532c63a867f5e2c1b91282197c4112c036c020dd7a423b6ac238891fa5d`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Provider-named eligibility is replaced by explicit generic release-state and revision-history capabilities; source certification is separate.
Implementation: `data.transformations.engine:execute_recipe`, operation `change.diff`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_six_release_registrations`.

### TR_RELEASE_change_pct

**Release Change Pct** — version `2.0.0`, family `change`, certification `approved`.

both operands come from the state knowable at the same release event

Formula: `x_t^(v_t)/x_(t-k)^(v_t)-1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `release_state`; required capabilities: revision_history, release_events.
Window: `causal_endpoints`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1,12]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_RELEASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `fractional_change`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"k":2}`, frequency `irregular` give final value **0.586206896552**. Values represent reference history selected from one explicitly anchored release state; earlier operands include only revisions known at that event.

Legacy mapping: `release:release.change_pct@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `3a9fe3567bcb557ec91d1f3cb0f6fa0f3295ce0e294e508b797f3765927c3270`.
Source evidence: `Data/src/point_in_time_data/alfred_release_coherent.py:1`, SHA-256 `95d5ae51e180da336366809c567a35e91f7675a4a9b25acdd4e47451e94c28c4`.
Source evidence: `Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json:1`, SHA-256 `0cd0d532c63a867f5e2c1b91282197c4112c036c020dd7a423b6ac238891fa5d`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Provider-named eligibility is replaced by explicit generic release-state and revision-history capabilities; source certification is separate.
Implementation: `data.transformations.engine:execute_recipe`, operation `change.pct`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_six_release_registrations`.

### TR_RELEASE_level

**Release Level** — version `2.0.0`, family `level`, certification `approved`.

current published level at the anchored release event

Formula: `x_t^(v_t)`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `release_state`; required capabilities: revision_history, release_events.
Window: `current_only`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- None.

Approved finite grid policy: `POL_TRANSFORM_GRID_RELEASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `preserve`; units rule `preserve`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{}`, frequency `irregular` give final value **46**. Values represent reference history selected from one explicitly anchored release state; earlier operands include only revisions known at that event.

Legacy mapping: `release:release.level@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `d3c215df26ecedb89a3d616a4b43f1223b6eff94d3cc1b5feb9247e614cd6e36`.
Source evidence: `Data/src/point_in_time_data/alfred_release_coherent.py:1`, SHA-256 `95d5ae51e180da336366809c567a35e91f7675a4a9b25acdd4e47451e94c28c4`.
Source evidence: `Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json:1`, SHA-256 `0cd0d532c63a867f5e2c1b91282197c4112c036c020dd7a423b6ac238891fa5d`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Provider-named eligibility is replaced by explicit generic release-state and revision-history capabilities; source certification is separate.
Implementation: `data.transformations.engine:execute_recipe`, operation `level.raw`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_six_release_registrations`.

### TR_RELEASE_shock_change_zscore

**Release Shock Change Zscore** — version `2.0.0`, family `shock`, certification `approved`.

g_s is the release-coherent k-period change computed from the information state at historical release event s; the current event uses only prior causally available g_s

Formula: `(g_t-mean(g_(t-w:t-1)))/sd(g_(t-w:t-1))`.

Input treatment: `release_event_changes`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `release_event_history`; required capabilities: revision_history, release_events.
Window: `current_exclusive_baseline`. Current coherent k-change and preceding w changes computed at their own certified release events; each event requires its complete k-state operands; w>=2 and nonzero sample SD.

Parameters:
- `basis` (change_basis): token; minimum None; maximum None; values diff,pct,log; grid axis `["diff","pct","log"]`.
- `k` (observations): integer; minimum 1; maximum None; grid axis `[1]`.
- `w` (observations): integer; minimum 2; maximum None; grid axis `[20,52,60]`.
- Relationships: k < w.

Approved finite grid policy: `POL_TRANSFORM_GRID_RELEASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,8]`, parameters `{"basis":"diff","k":1,"w":3}`, frequency `event` give final value **3.70970413401**. Values are already emitted coherent changes at four distinct certified release events, not four levels from one later state. Each historical change retains its own event-state lineage.

Legacy mapping: `release:release.shock_change_zscore@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `270340fc6ccc1b0a418c94893418fb88d5eccdbd65bebfe9b8cf97d2e5abee95`.
Source evidence: `Data/src/point_in_time_data/alfred_release_coherent.py:1`, SHA-256 `95d5ae51e180da336366809c567a35e91f7675a4a9b25acdd4e47451e94c28c4`.
Source evidence: `Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json:1`, SHA-256 `0cd0d532c63a867f5e2c1b91282197c4112c036c020dd7a423b6ac238891fa5d`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Provider-named eligibility is replaced by explicit generic release-state and revision-history capabilities; source certification is separate.
Implementation: `data.transformations.engine:execute_recipe`, operation `release.shock_change_zscore`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_six_release_registrations`.

### TR_RELEASE_standard_zscore

**Release Standard Zscore** — version `2.0.0`, family `standardization`, certification `approved`.

current level is standardized against prior levels in the current release state

Formula: `(x_t^(v_t)-mean(x_(t-w:t-1)^(v_t)))/sd(x_(t-w:t-1)^(v_t))`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `release_state`; required capabilities: revision_history, release_events.
Window: `current_exclusive_baseline`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 2; maximum None; grid axis `[52,60]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_RELEASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `score`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **2.2086305215**. Values represent reference history selected from one explicitly anchored release state; earlier operands include only revisions known at that event.

Legacy mapping: `release:release.standard_zscore@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `798e857fb9daeef7dd3d8b22f771aad4b3ee3d0e5701fb8f4ad487b00dc0a343`.
Source evidence: `Data/src/point_in_time_data/alfred_release_coherent.py:1`, SHA-256 `95d5ae51e180da336366809c567a35e91f7675a4a9b25acdd4e47451e94c28c4`.
Source evidence: `Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json:1`, SHA-256 `0cd0d532c63a867f5e2c1b91282197c4112c036c020dd7a423b6ac238891fa5d`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Provider-named eligibility is replaced by explicit generic release-state and revision-history capabilities; source certification is separate.
Implementation: `data.transformations.engine:execute_recipe`, operation `standard.zscore`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_six_release_registrations`.

### TR_RELEASE_trend_ma_relative

**Release Trend Ma Relative** — version `2.0.0`, family `trend`, certification `approved`.

current and moving-average operands come from the current release state

Formula: `x_t^(v_t)/mean(x_(t-w+1:t)^(v_t))-1`.

Input treatment: `direct`. Accepted value semantics: `numeric_level`, `price`, `difference`, `fractional_change`, `log_change`, `log_level`, `score`, `volatility`, `indicator`, `count`, `statistic`.
Input domain requirements: `numeric_input`.
Temporal mode: `release_state`; required capabilities: revision_history, release_events.
Window: `current_inclusive`. Complete required operands; exact minimum is numeric.required_history(kernel, parameters). No imputation, adaptive shortening or skipping missing periods.

Parameters:
- `w` (observations): integer; minimum 1; maximum None; grid axis `[12]`.

Approved finite grid policy: `POL_TRANSFORM_GRID_RELEASE@2.0.0`. Frequencies: tick, intraday, daily, weekly, monthly, quarterly, semiannual, annual, irregular, event.
Output: `statistic`; units rule `dimensionless`; type `number`; range Finite real values; no additional universal bound.

Failure behavior: request/domain incompatibility rejects; expected pointwise failures preserve the index with null and a controlled reason; unexpected failures remain exceptions. Controlled vocabulary: `INAPPLICABLE`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_SEASONAL_HISTORY`, `MISSING_PERIOD`, `MISSING_REQUIRED_OBSERVATION`, `NONFINITE_OUTPUT`, `NONPOSITIVE_INPUT`, `NONPOSITIVE_LOG_INPUT`, `NON_NUMERIC_INPUT`, `NUMERICAL_FAILURE`, `SOURCE_INVALID`, `SOURCE_MISSING`, `UNDECLARED_HISTORY_MODE`, `UNDEFINED_SEASONAL_BUCKET`, `UNSUPPORTED_CADENCE`, `UNSUPPORTED_DOMAIN`, `ZERO_DENOMINATOR`, `ZERO_MAD`, `ZERO_PATH_LENGTH`, `ZERO_RANGE`, `ZERO_VARIANCE`.

Example: values `[1,2,4,7,11,16,22,29,37,46]`, parameters `{"w":4}`, frequency `irregular` give final value **0.373134328358**. Values represent reference history selected from one explicitly anchored release state; earlier operands include only revisions known at that event.

Legacy mapping: `release:release.trend_ma_relative@1.0.0`, status `versioned_adaptation`.
Legacy definition fingerprint: `2dd8aaf862176717c92553809fb2dbb4f7d5580cf4e21774f3899c708e61507d`.
Source evidence: `Data/src/point_in_time_data/alfred_release_coherent.py:1`, SHA-256 `95d5ae51e180da336366809c567a35e91f7675a4a9b25acdd4e47451e94c28c4`.
Source evidence: `Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json:1`, SHA-256 `0cd0d532c63a867f5e2c1b91282197c4112c036c020dd7a423b6ac238891fa5d`.

Versioned differences: Version2 enforces explicit mathematical parameter minima and finite pointwise results with controlled reasons; legacy version remains separately mapped. Provider-named eligibility is replaced by explicit generic release-state and revision-history capabilities; source certification is separate.
Implementation: `data.transformations.engine:execute_recipe`, operation `trend.ma_relative`.
Acceptance references: `tests/test_transformation_registry.py::TransformationRegistryTests.test_every_registration_has_defined_independent_example`, `tests/test_transformation_numeric.py::NumericalAcceptanceTests.test_every_kernel_has_independent_defined_reference`, `tests/test_transformation_engine.py::TransformationEngineTests.test_all_six_release_registrations`.

## Foundation boundary and source eligibility

The executable foundation supports fixture recipes and deterministic logical/materialization identities. SourceView identity, ordered versioned operators, exact parameters, history/execution/grid policies and source selection bind the logical recipe. Input evidence, evaluation coverage and implementation dependencies distinguish computed materializations; execution timestamps, paths, labels, target/horizon choices and research outcomes do not redefine an unchanged logical feature recipe.

The separate next task is to certify a concrete real SourceView and explicitly selected recipe, then create production Features and their parent Signal IDs. No such production definitions or observations are populated here. Further formula suggestions, cross-series interactions, targets and research remain future scope.
