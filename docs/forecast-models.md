# Forecast Models readout

The owner-only Forecast Models page uses the existing Gambit session, workspace navigation, and rate limits. It reads a detached, checksummed view of the frozen P3 fit, archived forecast replay, and saved P4 portfolio results. A read cannot construct research services, run a model, or write to the research catalog.

The build tool verifies the archived replay manifest against an operator-reviewed SHA-256. It verifies the frozen fit, forecasts, and matching price panel against that manifest before publishing a readout to a new directory. Supply the original P4 results summary and its reviewed SHA-256 with `--portfolio-report` and `--portfolio-report-sha256`. The web service expects the installed readout under `/var/lib/gambit-forecast-models/v2`. Keep that directory operator-owned and readable by the web service, outside the source tree and research catalog. Install a complete verified readout together rather than replacing files individually.

## Saved identities and coverage

- Each saved `P3GROUP_` is the task identity. Grouping requires exact agreement on scope and membership, target references, horizon, view, and return basis. The three saved variants retain their `P3MODEL_` IDs and their frozen `P3FIT_` evidence.
- The archived `ridge_reg_weight` is a regression on calibrated component forecasts. Display its coefficients in that basis. Distinct model-version, point-in-time forecast availability, and forecast-run IDs were not retained. Show the original archive and content digests. Do not assign replacement scientific IDs.
- The detail page opens on Evaluation. Supporting evidence retains the original fit window and fit counts. Older links containing a period still open the same model.
- Forecast diagnostics use the archived 1D, 7D, and 21D forecasts. The archive ends on 2026-11-10. A pending row is pending relative to this archive. The 63D records show unavailable evaluation and portfolio returns.
- Net portfolio return uses the same saved one-net-portfolio policy for every model. It uses cost-aware sizing, a 2× gross cap, and a 1 bp one-way trading cost. The report's `net` variant has no dead zone. The metric is simulated P4 P&L divided by starting capital without reinvestment. Financing and swaps are excluded. The adapter verifies the report against the exact model identities, dates, fit, snapshot, forecasts, and close panel, and checks the net P&L against gross P&L and turnover. Forecast quality and P5 paper trading remain separate measures.
- Per-component forecast error, per-component realized contribution, and a canonical model comparison record are unavailable in this archived readout.

## Evaluation population

Forecasts join the exact saved instrument, frozen cross-sectional membership, scheduled-weekday origin and endpoint, and quote-oriented price snapshot. Realized simple return is the target close divided by the origin close minus one, centered by the mean of the full saved scope for the same interval. Use the completed full-scope rows for all metrics. Exclude incomplete, missing, and pending rows, and show their counts alongside the completed population.

Signed error is realized minus forecast in basis points. Mean rank IC is the equally weighted mean of valid date-level Spearman correlations. Report RMSE, MAE, and the calibration slope on pooled matched rows. The rolling chart uses 21 valid date observations and omits undefined or missing date ranks. Calibration uses up to six approximately equal-count forecast bins with ties kept together. The error histogram uses nine equal-width bins symmetric about zero when errors vary. Undefined statistics remain unavailable.
