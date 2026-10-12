"""Independent dense-calendar HAC oracles; synthetic observations only."""
from copy import deepcopy
from datetime import date, timedelta
import math
import unittest

from research import scheduled_statistics as scheduled
from research.legacy import p1 as legacy_p1, p2 as legacy_p2
from research.p1_discovery import ResearchContractError, run_p1
from test_research_kernels import profile


HORIZONS = (1, 7, 21, 63, 252)


def calendar(count, start="2023-01-02"):
    result, current = [], date.fromisoformat(start)
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def dense_slots(dates, scores):
    """Independently enumerate calendar dates; missing slots hold no observation."""
    if not dates:
        return []
    known = dict(zip(dates, scores))
    current, end = date.fromisoformat(min(dates)), date.fromisoformat(max(dates))
    result = []
    while current <= end:
        if current.weekday() < 5:
            result.append(known.get(current.isoformat()))
        current += timedelta(days=1)
    return result


def score_matrix(slots, maxlags, width):
    # Full dense-calendar pair matrix, independent of production sparse lag lookup.
    result = [[0.0] * width for _ in range(width)]
    for i, left in enumerate(slots):
        for j, right in enumerate(slots):
            distance = abs(i - j)
            if left is None or right is None or distance > maxlags:
                continue
            weight = 1.0 - distance / (maxlags + 1)
            for a in range(width):
                for b in range(width):
                    result[a][b] += weight * left[a] * right[b]
    return result


def ols_oracle(dates, x, y, maxlags):
    present = [(when, a, b) for when, a, b in zip(dates, x, y) if a is not None and b is not None]
    n = len(present)
    mx, my = sum(row[1] for row in present) / n, sum(row[2] for row in present) / n
    xx = sum((row[1] - mx) ** 2 for row in present)
    beta = sum((row[1] - mx) * (row[2] - my) for row in present) / xx
    alpha = my - beta * mx
    # Centered-design OLS: the slope's inverse-normal coefficient is 1 / sum(x-xbar)^2.
    scores = [(row[2] - alpha - beta * row[1],
               (row[1] - mx) * (row[2] - alpha - beta * row[1])) for row in present]
    meat = score_matrix(dense_slots([row[0] for row in present], scores), maxlags, 2)
    variance = meat[1][1] / (xx * xx)
    return alpha, beta, math.sqrt(variance) if variance > 0 else None


def mean_oracle(dates, values, maxlags):
    present = [(when, value) for when, value in zip(dates, values) if value is not None]
    average = sum(row[1] for row in present) / len(present)
    scores = [(row[1] - average,) for row in present]
    meat = score_matrix(dense_slots([row[0] for row in present], scores), maxlags, 1)
    variance = meat[0][0] / len(present) ** 2
    return average, math.sqrt(variance) if variance > 0 else None


def rank_ic(x, y):
    def rank(values):
        return [1 + sum(other < value for other in values) + (sum(other == value for other in values) - 1) / 2 for value in values]
    a, b = rank(x), rank(y)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    av, bv = [value - ma for value in a], [value - mb for value in b]
    scale = math.sqrt(sum(value * value for value in av) * sum(value * value for value in bv))
    return sum(left * right for left, right in zip(av, bv)) / scale if scale else None


def ts_fixture(count=330):
    all_dates = calendar(count + 100)
    selected = [i for i in range(count + 70) if i % 7 not in (2,) and i % 31 not in (3, 4)][:count]
    dates = [all_dates[i] for i in selected]
    x = [math.sin(i * .23) + i * .002 for i in selected]
    y = [.43 * value + .6 * math.sin(i * .73) for i, value in zip(selected, x)]
    return dates, x, y


def new_profile():
    return profile(kernel_policy="scheduled_weekday_hac_v2", missing_evidence="unresolved_required_v1")


class ScheduledHacTests(unittest.TestCase):
    def assert_nullable_close(self, actual, expected, places=11):
        if actual is None or expected is None:
            self.assertEqual(actual, expected)
        else:
            self.assertAlmostEqual(actual, expected, places=places)

    def test_ts_all_five_horizons_match_independent_dense_score_matrix(self):
        dates, x, y = ts_fixture()
        for horizon in HORIZONS:
            with self.subTest(horizon=horizon):
                actual = scheduled.ols_hac(dates, x, y, horizon - 1)
                alpha, beta, se = ols_oracle(dates, x, y, horizon - 1)
                self.assertAlmostEqual(actual["alpha"], alpha, places=13)
                self.assertAlmostEqual(actual["effect"], beta, places=13)
                self.assert_nullable_close(actual["standard_error"], se)
                self.assert_nullable_close(actual["t_statistic"], beta / se if se else None, places=9)
                self.assertEqual(actual["scheduled_hac"]["usable_observation_count"], len(dates))

    def test_mean_all_five_horizons_match_independent_dense_score_matrix(self):
        dates, values, _ = ts_fixture()
        values = [value + .1 for value in values]
        for horizon in HORIZONS:
            with self.subTest(horizon=horizon):
                actual = scheduled.mean_hac(dates, values, horizon - 1)
                mean, se = mean_oracle(dates, values, horizon - 1)
                self.assertEqual(actual["effect"], mean)
                self.assert_nullable_close(actual["standard_error"], se)

    def test_consecutive_scheduled_dates_match_original_legacy_hac(self):
        dates = calendar(330)
        x = [math.sin(i * .33) + i * .001 for i in range(len(dates))]
        y = [.73 * value + .8 * math.sin(i * .13) for i, value in enumerate(x)]
        for horizon in HORIZONS:
            with self.subTest(horizon=horizon):
                actual = scheduled.ols_hac(dates, x, y, horizon - 1)
                alpha, beta, se, statistic = legacy_p1._ols_with_hac(x, y, horizon - 1)
                self.assertEqual((actual["alpha"], actual["effect"], actual["standard_error"], actual["t_statistic"]),
                                 (alpha, beta, se, statistic))
                mean = scheduled.mean_hac(dates, y, horizon - 1)
                expected = legacy_p2._mean_hac(y, horizon - 1)
                self.assertEqual((mean["effect"], mean["standard_error"], mean["t_statistic"]),
                                 (expected["effect"], expected["standard_error"], expected["t_statistic"]))

    def test_gaps_change_hac_not_fitted_effect(self):
        dates, x, y = ts_fixture(60)
        current = scheduled.ols_hac(dates, x, y, 6)
        legacy = legacy_p2._ols_hac(x, y, 6)
        self.assertEqual(current["effect"], legacy["effect"])
        self.assertEqual(current["alpha"], legacy["alpha"])
        self.assertGreater(abs(current["standard_error"] - legacy["standard_error"]), 1e-6)
        self.assertGreater(current["scheduled_hac"]["missing_scheduled_period_count"], 0)

    def test_friday_to_monday_is_one_period_and_holidays_are_not_removed(self):
        self.assertEqual(scheduled.weekday_position("2024-01-08") - scheduled.weekday_position("2024-01-05"), 1)
        self.assertEqual(scheduled.weekday_position("2024-01-01") - scheduled.weekday_position("2023-12-29"), 1)
        self.assertEqual(scheduled.weekday_position("2024-03-04") - scheduled.weekday_position("2024-02-28"), 3)
        values = scheduled.mean_hac(["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-10"], [1., 2., -1., 3.], 2)
        self.assertEqual(values["scheduled_hac"]["lag_pair_counts"], [{"lag": 1, "pair_count": 2}, {"lag": 2, "pair_count": 2}])

    def test_explicit_nulls_are_absent_pairs_not_zero_observations(self):
        dates = calendar(9)
        x = [1., None, 2., 3., 0., -1., None, 2., 4.]
        y = [2., 8., 1., None, 3., 0., 2., 4., 1.]
        actual = scheduled.ols_hac(dates, x, y, 6)
        _, beta, se = ols_oracle(dates, x, y, 6)
        self.assertEqual(actual["effect"], beta)
        self.assert_nullable_close(actual["standard_error"], se)
        self.assertEqual(actual["scheduled_hac"]["usable_observation_count"], 6)
        mean = scheduled.mean_hac(dates, x, 6)
        expected, expected_se = mean_oracle(dates, x, 6)
        self.assertEqual(mean["effect"], expected)
        self.assert_nullable_close(mean["standard_error"], expected_se)
        self.assertEqual(mean["scheduled_hac"]["usable_observation_count"], 7)

    def test_cs_null_and_constant_ic_dates_retain_calendar_gaps(self):
        dates = calendar(12)
        rows, effects = [], []
        for i, when in enumerate(dates):
            x = [0., 1., 2., 3.]
            y = [math.sin(i + j * 1.37) for j in range(4)]
            if i == 3:
                x = [1.] * 4
            if i == 7:
                y[1] = None
            expected = None if i == 7 else rank_ic(x, y)
            effects.append(expected)
            for member, (left, right) in enumerate(zip(x, y)):
                rows.append({"observation_time": when, "instrument": str(member), "feature_value": left, "target_value": right})
        actual = scheduled.raw_estimate(rows, "cross_sectional", 6)
        mean, se = mean_oracle(dates, effects, 6)
        self.assertEqual(actual["effect"], mean)
        self.assert_nullable_close(actual["standard_error"], se)
        self.assertEqual(actual["period_dates"], [when for when, value in zip(dates, effects) if value is not None])
        self.assertEqual(actual["period_history"][3]["reason"], "UNAVAILABLE_RANK_IC")
        self.assertEqual(actual["period_history"][7]["reason"], "MISSING_OPERAND")
        self.assertEqual(actual["scheduled_hac"]["missing_scheduled_period_count"], 2)

    def test_cs_all_five_horizons_match_independent_rank_ic_calendar_oracle(self):
        dates, _, _ = ts_fixture()
        rows, values = [], []
        for i, when in enumerate(dates):
            x = [j + math.sin(i * .1 + j) for j in range(6)]
            y = [j * .1 + math.cos(i * .27 + j * .9) for j in range(6)]
            values.append(rank_ic(x, y))
            rows.extend({"observation_time": when, "feature_value": a, "target_value": b} for a, b in zip(x, y))
        for horizon in HORIZONS:
            with self.subTest(horizon=horizon):
                actual = scheduled.raw_estimate(rows, "cross_sectional", horizon - 1)
                mean, se = mean_oracle(dates, values, horizon - 1)
                self.assertEqual(actual["effect"], mean)
                self.assert_nullable_close(actual["standard_error"], se)
                self.assertEqual(actual["period_effects"], values)

    def test_p1_new_policy_uses_calendar_hac_without_changing_old_policy(self):
        dates, x, y = ts_fixture()
        all_dates = calendar(1000)
        positions = {when: i for i, when in enumerate(all_dates)}
        for horizon in HORIZONS:
            with self.subTest(horizon=horizon):
                rows = [{"date": when, "instrument": "A", "feature": left, "target": right,
                         "target_end": all_dates[positions[when] + horizon]} for when, left, right in zip(dates, x, y)]
                current = run_p1(rows, mode="TS", horizon=horizon, members=["A"], expected_direction="POSITIVE", profile=new_profile())
                legacy = run_p1(rows, mode="TS", horizon=horizon, members=["A"], expected_direction="POSITIVE", profile=profile())
                _, beta, se = ols_oracle(dates, x, y, horizon - 1)
                self.assertEqual(current["metrics"]["primary_effect"], beta)
                self.assert_nullable_close(current["metrics"]["hac_standard_error"], se)
                self.assertEqual(current["metrics"]["hac_clock"], scheduled.POLICY)
                self.assertNotIn("hac_clock", legacy["metrics"])
                self.assertEqual(legacy["metrics"]["hac_standard_error"], legacy_p1._ols_with_hac(x, y, horizon - 1)[2])
                self.assertEqual(current["artifacts"]["stability"], legacy["artifacts"]["stability"])

    def test_p1_cs_preserves_missing_and_constant_date_gaps(self):
        dates = calendar(70)
        rows, usable_dates, effects = [], [], []
        for i, when in enumerate(dates[:40]):
            x = [float(j) for j in range(5)] if i != 6 else [1.] * 5
            y = [.3 * j + math.sin(i * .43 + j) for j in range(5)]
            if i not in (6, 11):
                usable_dates.append(when)
                effects.append(rank_ic(x, y))
            for j, (left, right) in enumerate(zip(x, y)):
                if i == 11 and j == 1:
                    continue
                rows.append({"date": when, "instrument": str(j), "feature": left, "target": right, "target_end": dates[i + 7]})
        result = run_p1(rows, mode="CS", horizon=7, members=[str(j) for j in range(5)], expected_direction="positive", profile=new_profile())
        mean, se = mean_oracle(usable_dates, effects, 6)
        self.assertEqual(result["metrics"]["primary_effect"], mean)
        self.assert_nullable_close(result["metrics"]["hac_standard_error"], se)
        self.assertEqual(result["sample"]["inference_observation_count"], 38)
        self.assertEqual(result["artifacts"]["scheduled_hac"]["missing_scheduled_period_count"], 2)

    def test_bad_dates_order_duplicates_and_lag_types_rejected(self):
        for dates in (["2024-01-06"], ["2024-01-08T00:00:00Z"], ["2024-1-8"],
                      ["2024-01-08", "2024-01-08"], ["2024-01-09", "2024-01-08"], ["2024-02-30"]):
            with self.subTest(dates=dates), self.assertRaises(ResearchContractError):
                scheduled.mean_hac(dates, [1.] * len(dates), 1)
        for lag in (-1, True, 1.0):
            with self.subTest(lag=lag), self.assertRaises(ResearchContractError):
                scheduled.mean_hac([], [], lag)
        with self.assertRaises(ResearchContractError):
            scheduled.ols_hac(calendar(2), [1.], [1., 2.], 1)

    def test_empty_constant_and_malformed_values_are_explicit(self):
        self.assertIsNone(scheduled.ols_hac([], [], [], 0)["effect"])
        self.assertIsNone(scheduled.mean_hac([], [], 0)["effect"])
        self.assertIsNone(scheduled.ols_hac(calendar(3), [1.] * 3, [1., 2., 3.], 1)["effect"])
        self.assertIsNone(scheduled.mean_hac(calendar(3), [1.] * 3, 1)["standard_error"])
        for value in (float("nan"), float("inf"), "NaN", "1,000", True):
            with self.subTest(value=value), self.assertRaises(ResearchContractError):
                scheduled.mean_hac(calendar(2), [1., value], 1)

    def test_input_values_remain_unchanged_and_decimal_strings_match(self):
        dates, x, y = ts_fixture(20)
        snapshot = deepcopy((dates, x, y))
        float_result = scheduled.ols_hac(dates, x, y, 6)
        string_result = scheduled.ols_hac(dates, [format(v, ".17g") for v in x], [format(v, ".17g") for v in y], 6)
        self.assertEqual(float_result, string_result)
        self.assertEqual((dates, x, y), snapshot)


if __name__ == "__main__":
    unittest.main()
