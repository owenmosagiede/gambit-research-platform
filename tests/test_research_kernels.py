"""Isolated synthetic fixtures only; never open application observation stores."""
from __future__ import annotations

import ast
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import unittest

from research.legacy import p1 as frozen_p1, p2 as frozen_p2
from research.p1_discovery import ResearchContractError, run_p1
from research.p1_discovery.contract import legacy_rows
from research.p2_validation import run_p2
from research.p2_validation.engine import _gate, select_non_overlapping_intervals


def profile(**overrides):
    return {"kernel_policy": "retained_legacy_v1", "spacing": 1,
            "horizon_unit": "scheduled_weekdays", "clock_compatibility": "approved",
            "missing_evidence": "legacy_failed_v1", "window_start": "2000-01-01",
            "window_end_exclusive": "2040-01-01", "structural_common_start": "2000-01-01",
            **overrides}


def weekdays(count):
    result, current = [], date(2001, 1, 1)
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def ts_rows(count=400, horizon=7, scale=0.7):
    dates = weekdays(count + horizon)
    result = []
    for index in range(count):
        x = math.sin(index * 0.3) + index * 0.01
        result.append({"date": dates[index], "instrument": "A", "feature": x,
                       "target": scale * x + math.sin(index * 1.1) * 0.3,
                       "target_end": dates[index + horizon], "valid": True,
                       "lineage": {"fixture": "synthetic", "row": index},
                       "available_at": None})
    return result


def cs_rows(count=100, horizon=7, members=("A", "B", "C", "D", "E", "F", "G")):
    dates = weekdays(count + horizon)
    result = []
    for index in range(count):
        for position, member in enumerate(members):
            x = position + math.sin(index * 0.23 + position) * 1.1
            y = x * 0.2 + math.cos(index * 0.91 + position * 0.31) * 1.7
            result.append({"date": dates[index], "instrument": member,
                           "feature": x, "target": y, "target_end": dates[index + horizon],
                           "lineage": {"fixture": "synthetic", "member": member, "row": index}})
    return result


class RetainedResearchKernels(unittest.TestCase):
    def ts(self, rows=None, **kwargs):
        return run_p1(ts_rows() if rows is None else rows, mode="TS", horizon=7,
                      members=["A"], expected_direction=kwargs.pop("expected_direction", "positive"),
                      profile=kwargs.pop("profile", profile()), **kwargs)

    def p2(self, rows=None, **kwargs):
        return run_p2(ts_rows() if rows is None else rows, mode="TS", horizon=kwargs.pop("horizon", 7),
                      members=["A"], expected_direction=kwargs.pop("expected_direction", "positive"),
                      discovery_effect=kwargs.pop("discovery_effect", 0.7),
                      profile=kwargs.pop("profile", profile()), **kwargs)

    def test_frozen_function_bytes_match_imported_source_provenance(self):
        directory = Path(frozen_p1.__file__).parent
        evidence = json.loads((directory / "provenance.json").read_text())
        self.assertGreaterEqual(len(evidence["files"]), 20)
        for entry in evidence["files"]:
            source = (directory / entry["destination"]).read_text()
            node = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == entry["function"])
            segment = "".join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
            self.assertEqual(hashlib.sha256(segment.encode()).hexdigest(), entry["function_sha256"])

    def test_p1_numerical_parity_with_frozen_helpers_and_golden(self):
        rows = ts_rows()
        result = self.ts(rows)
        x, y = [row["feature"] for row in rows], [row["target"] for row in rows]
        alpha, effect, se, statistic = frozen_p1._ols_with_hac(x, y, 6)
        for key, value in (("alpha", alpha), ("primary_effect", effect),
                           ("hac_standard_error", se), ("hac_t_statistic", statistic)):
            self.assertEqual(result["metrics"][key], value)
        self.assertAlmostEqual(effect, 0.6983341373908402, places=14)
        self.assertAlmostEqual(se, 0.003930023852264667, places=14)
        self.assertAlmostEqual(statistic, 177.69208626772755, places=10)
        self.assertEqual(result["admission"], "admitted")

    def test_p2_numerical_and_stability_parity_with_frozen_helpers(self):
        rows = ts_rows()
        result = self.p2(rows)
        legacy = legacy_rows(rows)
        expected = frozen_p2._raw_estimate(legacy, "time_series", 6)
        self.assertEqual(result["metrics"]["primary_effect"], expected["effect"])
        self.assertEqual(result["metrics"]["hac_t_statistic"], expected["t_statistic"])
        for actual, block in zip(result["artifacts"]["blocks"], frozen_p2._blocks(legacy)):
            self.assertEqual(actual["raw_effect"], frozen_p2._raw_estimate(block, "time_series", 0)["effect"])
        self.assertEqual(result["decision"], "VALIDATED")
        self.assertEqual(result["sample"]["effective_observation_count"], 58)

    def test_p1_admission_remains_absolute_and_does_not_flip_user_direction(self):
        positive = self.ts()
        negative = self.ts(expected_direction="negative")
        self.assertEqual(positive["admission"], negative["admission"])
        self.assertEqual(positive["metrics"], negative["metrics"])
        self.assertEqual(negative["expected_direction"], "negative")

    def test_direction_precheck_never_consumes_validation_rows(self):
        def forbidden():
            raise AssertionError("validation data was read")
            yield
        result = self.p2(forbidden(), expected_direction="negative")
        self.assertEqual(result["decision"], "FAILED")
        self.assertFalse(result["sample"]["validation_data_accessed"])
        self.assertEqual(result["reason_codes"], ["DISCOVERY_EFFECT_CONTRADICTS_EXPECTED_DIRECTION"])

    def test_uppercase_direction_preserves_frozen_choice_and_statistical_meaning(self):
        self.assertEqual(self.ts(expected_direction="POSITIVE")["expected_direction"], "POSITIVE")
        upper = self.p2(expected_direction="POSITIVE")
        lower = self.p2(expected_direction="positive")
        self.assertEqual(upper["metrics"], lower["metrics"])
        self.assertEqual(upper["expected_direction"], "POSITIVE")
        self.assertEqual(self.p2(expected_direction="NEGATIVE")["decision"], "FAILED")

    def test_profile_approval_and_explicit_discrepancy_disposition_required(self):
        for change in ({"clock_compatibility": "pending"}, {"missing_evidence": "unresolved"},
                       {"horizon_unit": "calendar_days"}, {"spacing": 2}, {"spacing": True}):
            with self.subTest(change=change), self.assertRaises(ResearchContractError):
                self.ts(profile=profile(**change))

    def test_exact_modes_and_frozen_members_are_required(self):
        for mode, members in (("TS", ["A", "B"]), ("CS", ["A"]), ("CS", ["A", "A"]), ("both", ["A"])):
            with self.subTest(mode=mode, members=members), self.assertRaises(ResearchContractError):
                run_p1([], mode=mode, members=members, horizon=1, expected_direction="positive", profile=profile())

    def test_cs_counts_one_ic_per_date_and_preserves_complete_member_set(self):
        members = ["A", "B", "C", "D", "E", "F", "G"]
        rows = cs_rows(members=members)
        result = run_p1(rows, mode="CS", horizon=7, members=members, expected_direction="positive", profile=profile())
        self.assertEqual(result["sample"]["inference_observation_count"], 100)
        self.assertEqual(result["sample"]["usable_pair_count"], 700)
        self.assertEqual(result["sample"]["required_members"], members)
        self.assertEqual(len(result["artifacts"]["cross_sectional_ic_history"]), 100)
        expected = frozen_p2._raw_estimate(legacy_rows(rows), "cross_sectional", 6)
        self.assertAlmostEqual(result["metrics"]["primary_effect"], expected["effect"], places=14)
        self.assertEqual(result["metrics"]["hac_t_statistic"], expected["t_statistic"])

    def test_cs_missing_member_excludes_entire_date_not_universe_member(self):
        members = ["A", "B", "C"]
        rows = cs_rows(members=members)
        missing_date = rows[0]["date"]
        rows = [row for row in rows if not (row["date"] == missing_date and row["instrument"] == "B")]
        result = run_p1(rows, mode="CS", horizon=7, members=members, expected_direction="positive", profile=profile())
        self.assertEqual(result["sample"]["required_members"], members)
        self.assertEqual(result["sample"]["incomplete_dates"][0]["missing_or_invalid_members"], ["B"])
        self.assertEqual(result["sample"]["usable_date_count"], 99)
        self.assertEqual(sum(row["date"] == missing_date for row in result["artifacts"]["aligned_sample"]), 0)

    def test_absent_cs_member_is_reported_and_never_silently_removed(self):
        result = run_p1(cs_rows(members=["A", "B"]), mode="CS", horizon=7, members=["A", "B", "C"],
                        expected_direction="positive", profile=profile())
        self.assertEqual(result["admission"], "unresolved")
        self.assertEqual(result["sample"]["members"][-1], {"instrument": "C", "supplied_rows": 0, "usable_rows": 0})
        self.assertEqual(result["sample"]["usable_date_count"], 0)

    def test_cs_structural_common_start_is_explicit(self):
        policy = profile()
        del policy["structural_common_start"]
        with self.assertRaises(ResearchContractError):
            run_p1([], mode="CS", horizon=1, members=["A", "B"], expected_direction="positive", profile=policy)
        rows = cs_rows(members=["A", "B", "C"])
        start = weekdays(20)[10]
        result = run_p1(rows, mode="CS", horizon=7, members=["A", "B", "C"], expected_direction="positive",
                        profile=profile(structural_common_start=start))
        self.assertEqual(result["sample"]["exclusion_counts"]["BEFORE_STRUCTURAL_COMMON_START"], 30)

    def test_cs_constant_date_is_excluded_from_p1_inference(self):
        rows = cs_rows(members=["A", "B", "C"])
        for row in rows[:3]:
            row["feature"] = 1.0
        result = run_p1(rows, mode="CS", horizon=7, members=["A", "B", "C"], expected_direction="positive", profile=profile())
        self.assertEqual(result["sample"]["usable_date_count"], 99)
        self.assertEqual(result["sample"]["exclusion_counts"]["CONSTANT_FEATURE"], 3)

    def test_p2_cs_blocks_are_date_atomic_and_effective_n_not_pooled(self):
        members = ["A", "B", "C", "D", "E", "F", "G"]
        result = run_p2(cs_rows(120, members=members), mode="CS", horizon=7, members=members,
                        expected_direction="positive", discovery_effect=0.3, profile=profile())
        self.assertEqual(result["sample"]["effective_observation_count"], 18)
        self.assertEqual(result["sample"]["inference_observation_count"], 120)
        self.assertEqual([row["date_count"] for row in result["artifacts"]["blocks"]], [40, 40, 40])
        self.assertEqual([row["observation_count"] for row in result["artifacts"]["blocks"]], [280, 280, 280])

    def test_actual_interval_effective_n_handles_gaps_and_shared_boundary(self):
        rows = [{"date": "2001-01-01", "target_end": "2001-01-10", "instrument": "A"},
                {"date": "2001-01-02", "target_end": "2001-01-03", "instrument": "A"},
                {"date": "2001-01-03", "target_end": "2001-01-04", "instrument": "A"},
                {"date": "2001-02-01", "target_end": "2001-02-02", "instrument": "A"}]
        selected = select_non_overlapping_intervals(rows)
        self.assertEqual([row["date"] for row in selected], ["2001-01-02", "2001-01-03", "2001-02-01"])

    def test_target_endpoints_and_observations_strictly_within_partition(self):
        rows = ts_rows(40)
        boundary = rows[20]["date"]
        result = self.ts(rows, profile=profile(window_end_exclusive=boundary))
        self.assertTrue(all(row["date"] < boundary and row["target_end"] < boundary for row in result["artifacts"]["aligned_sample"]))
        self.assertIn("TARGET_ENDPOINT_OUTSIDE_FROZEN_WINDOW", result["sample"]["exclusion_counts"])
        self.assertIn("OUTSIDE_FROZEN_WINDOW", result["sample"]["exclusion_counts"])

    def test_missing_and_duplicate_pairs_retained_as_exclusions_without_imputation(self):
        rows = ts_rows(40)
        rows[3]["target"] = None
        rows.append(deepcopy(rows[5]))
        result = self.ts(rows)
        self.assertEqual(result["sample"]["exclusion_counts"]["TARGET_MISSING_OR_INVALID"], 1)
        self.assertEqual(result["sample"]["exclusion_counts"]["DUPLICATE_OBSERVATION"], 2)
        self.assertEqual(result["sample"]["usable_pair_count"], 38)

    def test_nonfinite_values_are_excluded_with_serializable_original_evidence(self):
        rows = ts_rows(40)
        rows[2]["feature"] = float("nan")
        rows[3]["target"] = float("inf")
        result = self.ts(rows)
        self.assertEqual(result["sample"]["usable_pair_count"], 38)
        self.assertEqual(result["artifacts"]["observation_exclusions"][0]["invalid_numeric_inputs"], {"feature": "nan"})
        json.dumps(result, allow_nan=False)

    def test_canonical_decimal_strings_match_floats_at_numeric_boundary(self):
        floats = ts_rows()
        strings = deepcopy(floats)
        for row in strings:
            for field in ("feature", "target"):
                row[field] = format(row[field], ".17g")
        before = deepcopy(strings)
        self.assertEqual(self.ts(strings)["metrics"], self.ts(floats)["metrics"])
        self.assertEqual(self.p2(strings, discovery_effect="0.7")["metrics"], self.p2(floats)["metrics"])
        self.assertEqual(strings, before)

    def test_malformed_nonfinite_and_overflow_decimal_strings_are_excluded(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e9999", "1,000", " 1.2", "1.2 ", "+1.2", "01.2", "1.0.0"):
            with self.subTest(value=value):
                rows = ts_rows(40)
                rows[1]["feature"] = value
                result = self.ts(rows)
                self.assertEqual(result["sample"]["usable_pair_count"], 39)
                self.assertEqual(result["artifacts"]["observation_exclusions"][0]["feature"], value)

    def test_unexpected_member_and_invalid_endpoints_are_rejected(self):
        for changes in ({"instrument": "OUTSIDE"}, {"target_end": "2000-01-01"}, {"target_end": "2001-01-10T00:00:00Z"}):
            rows = ts_rows(20)
            rows[0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ResearchContractError):
                self.ts(rows)

    def test_input_rows_and_lineage_are_unchanged_and_no_availability_invented(self):
        rows = ts_rows(40)
        before = deepcopy(rows)
        result = self.ts(rows)
        self.assertEqual(rows, before)
        self.assertEqual(result["artifacts"]["aligned_sample"][0]["lineage"], rows[0]["lineage"])
        self.assertIsNone(result["artifacts"]["aligned_sample"][0]["available_at"])
        json.dumps(result, allow_nan=False)

    def test_p1_constant_or_insufficient_data_is_unresolved(self):
        for kind in ("constant_feature", "constant_target", "insufficient"):
            rows = ts_rows(2 if kind == "insufficient" else 40)
            if kind.startswith("constant"):
                for row in rows:
                    row[kind.removeprefix("constant_")] = 1.0
            result = self.ts(rows)
            self.assertEqual(result["admission"], "unresolved")

    def test_p1_zero_sign_inconsistent_legacy_stability_is_unresolved(self):
        rows = ts_rows(90, horizon=1)
        for index, row in enumerate(rows):
            row["feature"] = [-1.0, 0.0, 1.0][index % 3]
            row["target"] = [-1.0, 2.0, -1.0][index % 3]
        result = run_p1(rows, mode="TS", horizon=1, members=["A"], expected_direction="positive", profile=profile())
        self.assertEqual(result["metrics"]["primary_effect"], 0.0)
        self.assertEqual(result["admission"], "unresolved")

    def test_p2_insufficient_effective_n_is_unresolved(self):
        result = self.p2(ts_rows(40))
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["reason_codes"], ["INSUFFICIENT_EFFECTIVE_SAMPLE"])

    def test_p2_missing_statistic_discrepancy_is_explicit_legacy_failure(self):
        rows = ts_rows()
        for row in rows:
            row["feature"] = 1.0
        result = self.p2(rows)
        self.assertEqual(result["missing_evidence_policy"], "legacy_failed_v1")
        self.assertEqual(result["decision"], "FAILED")
        self.assertEqual(result["evidence"]["direction"]["status"], "fail")
        self.assertIsNone(result["metrics"]["primary_effect"])

    def test_252_keeps_low_sample_flag_and_diagnostic_inference(self):
        result = self.p2(ts_rows(1100, horizon=252), horizon=252)
        self.assertEqual(result["sample"]["minimum_effective_observations"], 4)
        self.assertEqual(result["sample"]["effective_observation_count"], 5)
        self.assertEqual(result["evidence"]["inference"]["status"], "diagnostic")
        self.assertEqual(result["confidence_flags"], ["LONG_HORIZON_LOW_SAMPLE_CONFIDENCE"])

    def test_singleton_fdr_is_diagnostic_only(self):
        result = self.p2()
        fdr = result["fdr_diagnostics"]
        self.assertTrue(fdr["diagnostic_only"])
        self.assertEqual(fdr["family_scope"], "singleton_relationship_horizon")
        self.assertEqual(fdr["family_size"], 1)
        self.assertEqual(fdr["raw_p_value"], fdr["adjusted_p_value"])

    def test_gate_boundary_and_missing_evidence_parity(self):
        evidence = {key: {"status": "pass"} for key in ("discovery_direction", "sample_sufficiency", "direction", "magnitude", "inference", "stability")}
        self.assertEqual(_gate(evidence, 1)[0], "VALIDATED")
        evidence["inference"]["status"] = "diagnostic"
        self.assertEqual(_gate(evidence, 1)[0], "UNRESOLVED")
        self.assertEqual(_gate(evidence, 252)[0], "VALIDATED")
        evidence["stability"]["status"] = "fail"
        self.assertEqual(_gate(evidence, 252)[0], "FAILED")


if __name__ == "__main__":
    unittest.main()
