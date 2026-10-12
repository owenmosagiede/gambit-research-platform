"""Synthetic P2 evidence policy and dated-kernel integration; no stored data reads."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from research import scheduled_statistics
from research.legacy import p2 as frozen_p2
from research.p1_discovery.contract import legacy_rows
from research.p2_validation import run_p2
from research.p2_validation.engine import _gate
from test_research_kernels import cs_rows, profile, ts_rows


def approved_profile():
    return profile(kernel_policy="scheduled_weekday_hac_v2",
                   missing_evidence="unresolved_required_v1")


def estimates():
    # Full sample, three blocks, three leave-outs, two chronological halves.
    return [{"effect": 0.7, "alpha": 0.0, "t_statistic": 3.0,
             "standard_error": 0.7 / 3.0} for _ in range(9)]


class RequiredP2EvidencePolicy(unittest.TestCase):
    def execute(self, rows=None, *, horizon=7, policy=None, **kwargs):
        return run_p2(ts_rows(1100 if horizon == 252 else 120, horizon=horizon)
                      if rows is None else rows,
                      mode="TS", horizon=horizon, members=["A"],
                      expected_direction=kwargs.pop("expected_direction", "positive"),
                      discovery_effect=kwargs.pop("discovery_effect", 0.7),
                      profile=approved_profile() if policy is None else policy, **kwargs)

    def controlled(self, values=None, **kwargs):
        with patch.object(scheduled_statistics, "raw_estimate",
                          side_effect=estimates() if values is None else values) as calculate:
            result = self.execute(**kwargs)
        self.assertEqual(calculate.call_count, 9)
        return result

    def test_available_passing_evidence_validates(self):
        result = self.controlled()
        self.assertEqual(result["decision"], "VALIDATED")
        self.assertEqual(result["missing_evidence_policy"], "unresolved_required_v1")
        self.assertEqual(result["sample"]["effective_observation_count"], 18)
        self.assertEqual(result["evidence"]["stability"]["missing_required_evidence"], [])

    def test_missing_full_effect_or_inference_is_unresolved(self):
        for field, reasons in (("effect", ["DIRECTION_EVIDENCE_UNAVAILABLE", "MAGNITUDE_EVIDENCE_UNAVAILABLE"]),
                               ("t_statistic", ["INFERENCE_EVIDENCE_UNAVAILABLE"])):
            with self.subTest(field=field):
                values = estimates()
                values[0][field] = None
                result = self.controlled(values)
                self.assertEqual(result["decision"], "UNRESOLVED")
                self.assertEqual(result["reason_codes"], reasons)

    def test_missing_each_required_stability_statistic_is_unresolved(self):
        cases = [(index, field, f"block_{index}_{suffix}")
                 for index in range(1, 4)
                 for field, suffix in (("effect", "effect"), ("t_statistic", "directional_t"))]
        cases += [(index, "effect", f"leave_out_{index - 3}_effect") for index in range(4, 7)]
        for index, field, missing_code in cases:
            with self.subTest(index=index, field=field):
                values = estimates()
                values[index][field] = None
                result = self.controlled(values)
                self.assertEqual(result["decision"], "UNRESOLVED")
                self.assertEqual(result["reason_codes"], ["STABILITY_EVIDENCE_UNAVAILABLE"])
                self.assertEqual(result["evidence"]["stability"]["missing_required_evidence"], [missing_code])
                if index <= 3 and field == "effect":
                    self.assertIsNone(result["artifacts"]["blocks"][index - 1]["expected_sign"])

    def test_missing_half_effect_is_diagnostic_for_standard_horizons(self):
        values = estimates()
        values[7]["effect"] = values[8]["effect"] = None
        result = self.controlled(values)
        self.assertEqual(result["decision"], "VALIDATED")
        self.assertIsNone(result["evidence"]["stability"]["observed"]["all_robustness_slices_expected_sign"])

    def test_zero_is_available_failing_evidence_not_missing(self):
        values = estimates()
        values[0]["effect"] = 0.0
        result = self.controlled(values)
        self.assertEqual(result["decision"], "FAILED")
        self.assertEqual(result["reason_codes"], ["DIRECTION_GATE_FAILED", "MAGNITUDE_GATE_FAILED"])
        self.assertEqual(result["evidence"]["direction"]["observed"], 0.0)

    def test_available_failed_criteria_are_failed(self):
        cases = [(0, "effect", 0.1, "MAGNITUDE_GATE_FAILED"),
                 (0, "t_statistic", 1.6449, "INFERENCE_GATE_FAILED"),
                 (4, "effect", 0.0, "STABILITY_GATE_FAILED"),
                 (5, "effect", -0.1, "STABILITY_GATE_FAILED")]
        for index, field, value, reason in cases:
            with self.subTest(index=index, field=field):
                values = estimates()
                values[index][field] = value
                result = self.controlled(values)
                self.assertEqual(result["decision"], "FAILED")
                self.assertIn(reason, result["reason_codes"])

    def test_retained_threshold_boundaries(self):
        values = estimates()
        values[0].update(effect=0.175, t_statistic=1.645)
        self.assertEqual(self.controlled(values)["decision"], "VALIDATED")
        values[1].update(effect=-0.1, t_statistic=-1.645)
        result = self.controlled(values)
        self.assertEqual(result["decision"], "FAILED")
        self.assertEqual(result["reason_codes"], ["STABILITY_GATE_FAILED"])
        values[1]["t_statistic"] = -1.6449
        self.assertEqual(self.controlled(values)["decision"], "VALIDATED")

    def test_available_block_sign_failure_is_failed(self):
        values = estimates()
        values[1]["effect"] = values[2]["effect"] = 0.0
        result = self.controlled(values)
        self.assertEqual(result["decision"], "FAILED")
        self.assertEqual(result["evidence"]["stability"]["observed"]["expected_sign_blocks"], 1)

    def test_missing_evidence_precedes_other_available_failure(self):
        values = estimates()
        values[0]["effect"] = -0.1
        values[4]["effect"] = None
        result = self.controlled(values)
        self.assertEqual(result["evidence"]["direction"]["status"], "fail")
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["reason_codes"], ["STABILITY_EVIDENCE_UNAVAILABLE"])

    def test_missing_evidence_precedes_failure_inside_compound_stability(self):
        values = estimates()
        values[1]["effect"] = values[2]["effect"] = -0.1
        values[4]["effect"] = None
        result = self.controlled(values)
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["evidence"]["stability"]["observed"]["expected_sign_blocks"], 1)
        self.assertEqual(result["evidence"]["stability"]["status"], "unresolved")

    def test_known_insufficient_sample_is_failed_when_required_stats_available(self):
        result = self.controlled(rows=ts_rows(40))
        self.assertEqual(result["sample"]["effective_observation_count"], 6)
        self.assertEqual(result["decision"], "FAILED")
        self.assertEqual(result["reason_codes"], ["SAMPLE_SUFFICIENCY_GATE_FAILED"])

    def test_known_sample_failure_and_unknown_statistic_is_unresolved(self):
        values = estimates()
        values[0]["t_statistic"] = None
        result = self.controlled(values, rows=ts_rows(40))
        self.assertEqual(result["evidence"]["sample_sufficiency"]["status"], "fail")
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["reason_codes"], ["INFERENCE_EVIDENCE_UNAVAILABLE"])

    def test_nonfinite_statistical_values_are_missing_not_failed_or_serialized_nan(self):
        values = estimates()
        values[0]["effect"] = float("nan")
        values[1]["t_statistic"] = float("inf")
        result = self.controlled(values)
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertIsNone(result["metrics"]["primary_effect"])
        json.dumps(result, allow_nan=False)

    def test_negative_direction_orients_available_statistics_without_changing_raw_effect(self):
        values = estimates()
        for value in values:
            value.update(effect=-0.7, t_statistic=-3.0)
        result = self.controlled(values, expected_direction="NEGATIVE", discovery_effect=-0.7)
        self.assertEqual(result["decision"], "VALIDATED")
        self.assertEqual(result["metrics"]["primary_effect"], -0.7)
        self.assertEqual(result["metrics"]["oriented_validation_effect"], 0.7)
        self.assertEqual(result["metrics"]["directional_hac_t_statistic"], 3.0)

    def test_discovery_conflict_precedes_validation_access_and_statistics(self):
        def forbidden():
            raise AssertionError("validation data accessed")
            yield
        with patch.object(scheduled_statistics, "raw_estimate", side_effect=AssertionError("statistics ran")):
            result = self.execute(forbidden(), expected_direction="negative")
        self.assertEqual(result["decision"], "FAILED")
        self.assertFalse(result["sample"]["validation_data_accessed"])

    def test_252_t_values_are_diagnostic_and_never_required(self):
        values = estimates()
        for value in values:
            value["t_statistic"] = value["standard_error"] = None
        result = self.controlled(values, horizon=252)
        self.assertEqual(result["decision"], "VALIDATED")
        self.assertEqual(result["evidence"]["inference"]["status"], "diagnostic")
        self.assertEqual(result["fdr_diagnostics"]["family_size"], 0)
        self.assertEqual(result["confidence_flags"], ["LONG_HORIZON_LOW_SAMPLE_CONFIDENCE"])
        self.assertIsNone(result["evidence"]["stability"]["observed"]["no_significant_opposite_block"])

    def test_252_each_required_effect_missing_is_unresolved(self):
        for index in range(9):
            with self.subTest(index=index):
                values = estimates()
                values[index]["effect"] = None
                result = self.controlled(values, horizon=252)
                self.assertEqual(result["decision"], "UNRESOLVED")
                self.assertTrue(any("EVIDENCE_UNAVAILABLE" in reason for reason in result["reason_codes"]))

    def test_252_each_stability_effect_zero_is_available_and_fails(self):
        for index in range(1, 9):
            with self.subTest(index=index):
                values = estimates()
                values[index]["effect"] = 0.0
                result = self.controlled(values, horizon=252)
                self.assertEqual(result["decision"], "FAILED")
                self.assertEqual(result["reason_codes"], ["STABILITY_GATE_FAILED"])

    def test_252_sample_failure_with_available_statistics_is_failed(self):
        result = self.controlled(horizon=252, rows=ts_rows(600, horizon=252))
        self.assertEqual(result["sample"]["effective_observation_count"], 3)
        self.assertEqual(result["decision"], "FAILED")
        self.assertEqual(result["reason_codes"], ["SAMPLE_SUFFICIENCY_GATE_FAILED"])

    def test_historical_missing_and_sample_policy_remains_unchanged(self):
        values = estimates()
        values[0]["effect"] = None
        with patch.object(frozen_p2, "_raw_estimate", side_effect=values):
            result = self.execute(policy=profile())
        self.assertEqual(result["decision"], "FAILED")
        self.assertEqual(result["missing_evidence_policy"], "legacy_failed_v1")
        self.assertNotIn("scheduled_hac", result["metrics"])
        self.assertNotIn("missing_required_evidence", result["evidence"]["stability"])
        self.assertEqual(self.execute(ts_rows(40), policy=profile())["reason_codes"],
                         ["INSUFFICIENT_EFFECTIVE_SAMPLE"])

    def test_gate_legacy_default_and_explicit_new_policy_have_distinct_sample_meaning(self):
        evidence = {key: {"status": "pass"} for key in
                    ("discovery_direction", "sample_sufficiency", "direction", "magnitude", "inference", "stability")}
        evidence["sample_sufficiency"]["status"] = "fail"
        self.assertEqual(_gate(evidence, 7), ("UNRESOLVED", ["INSUFFICIENT_EFFECTIVE_SAMPLE"]))
        self.assertEqual(_gate(evidence, 7, missing_evidence="unresolved_required_v1"),
                         ("FAILED", ["SAMPLE_SUFFICIENCY_GATE_FAILED"]))

    def test_actual_constant_predictor_is_unresolved_new_and_failed_historical(self):
        rows = ts_rows(120)
        for row in rows:
            row["feature"] = 1.0
        result = self.execute(rows)
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["evidence"]["sample_sufficiency"]["status"], "pass")
        self.assertEqual(self.execute(rows, policy=profile())["decision"], "FAILED")

    def test_constant_cs_dates_do_not_inflate_v2_effective_sample(self):
        from test_research_kernels import weekdays
        dates=weekdays(61); members=["A","B","C","D"]; rows=[]
        for i in range(60):
            ranks=[0,1,3,2] if (i//5)%2 else [0,1,2,3]
            for j,member in enumerate(members):
                rows.append({"date":dates[i],"target_end":dates[i+1],"instrument":member,
                             "feature":j if i%5==0 else 1,"target":ranks[j]})
        kwargs=dict(mode="CS",horizon=1,members=members,expected_direction="positive",discovery_effect=0.9)
        result=run_p2(rows,profile=approved_profile(),**kwargs)
        self.assertEqual(result["sample"]["inference_observation_count"],12)
        self.assertEqual(result["sample"]["effective_observation_count"],12)
        self.assertEqual(result["decision"],"FAILED")
        self.assertEqual(result["reason_codes"],["SAMPLE_SUFFICIENCY_GATE_FAILED"])
        for key in ("direction","magnitude","inference","stability"):
            self.assertEqual(result["evidence"][key]["status"],"pass")
        legacy=run_p2(rows,profile=profile(),**kwargs)
        self.assertEqual(legacy["sample"]["effective_observation_count"],60)
        self.assertEqual(legacy["decision"],"VALIDATED")

    def test_empty_sample_has_unavailable_statistics_and_is_unresolved(self):
        result = self.execute([])
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["sample"]["effective_observation_count"], 0)
        self.assertIn("DIRECTION_EVIDENCE_UNAVAILABLE", result["reason_codes"])

    def test_actual_exact_linear_relation_keeps_missing_standard_horizon_t_unresolved(self):
        rows = ts_rows(120)
        for index, row in enumerate(rows):
            row.update(feature=index, target=2 * index)
        result = self.execute(rows, discovery_effect=2.0)
        self.assertEqual(result["metrics"]["primary_effect"], 2.0)
        self.assertIsNone(result["metrics"]["hac_t_statistic"])
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertIn("INFERENCE_EVIDENCE_UNAVAILABLE", result["reason_codes"])

    def test_all_nine_estimates_use_dated_kernel_preserving_leaveout_gaps_and_lineage(self):
        rows = ts_rows(140)
        rows = [row for index, row in enumerate(rows) if index not in {8, 9, 14, 41}]
        before = deepcopy(rows)
        with patch.object(scheduled_statistics, "raw_estimate", wraps=scheduled_statistics.raw_estimate) as calculate, \
                patch.object(frozen_p2, "_raw_estimate", side_effect=AssertionError("legacy estimator used")):
            result = self.execute(rows)
        self.assertEqual(calculate.call_count, 9)
        self.assertEqual([call.args[2] for call in calculate.call_args_list], [6] + [0] * 8)
        self.assertEqual([row["observation_time"] for row in calculate.call_args_list[0].args[0]],
                         [row["date"] for row in rows])
        blocks = frozen_p2._blocks(legacy_rows(rows), 3, research_type="time_series")
        self.assertEqual(list(calculate.call_args_list[5].args[0]), list(blocks[0]) + list(blocks[2]))
        self.assertGreater(result["artifacts"]["leaveouts"][1]["scheduled_hac"]["missing_scheduled_period_count"], 4)
        self.assertEqual(result["metrics"]["scheduled_hac"]["missing_scheduled_period_count"], 4)
        direct = scheduled_statistics.raw_estimate(legacy_rows(rows), "time_series", 6)
        self.assertEqual(result["metrics"]["hac_standard_error"], direct["standard_error"])
        self.assertEqual(rows, before)
        self.assertEqual(result["artifacts"]["aligned_sample"][0]["lineage"], rows[0]["lineage"])

    def test_cs_constant_date_retains_gap_and_incomplete_members_are_not_dropped(self):
        members = ["A", "B", "C"]
        rows = cs_rows(120, members=members)
        for row in rows[24:27]:
            row["feature"] = 1.0
        missing = rows[30]["date"]
        rows = [row for row in rows if not (row["date"] == missing and row["instrument"] == "B")]
        result = run_p2(rows, mode="CS", horizon=7, members=members, expected_direction="positive",
                        discovery_effect=0.3, profile=approved_profile())
        self.assertEqual(result["sample"]["required_members"], members)
        self.assertEqual(result["sample"]["inference_observation_count"], 118)
        self.assertEqual(result["metrics"]["scheduled_hac"]["missing_scheduled_period_count"], 2)
        self.assertEqual(result["sample"]["incomplete_dates"][0]["missing_or_invalid_members"], ["B"])
        self.assertEqual(result["artifacts"]["cross_sectional_ic_history"][8]["status"], "constant_cross_section")
        self.assertTrue(all(block["observation_count"] % len(members) == 0 for block in result["artifacts"]["blocks"]))
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
