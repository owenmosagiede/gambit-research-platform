"""Independent interval/calendar and leakage acceptance for Target schedules."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from zoneinfo import ZoneInfo

from data.transformations.contracts import ContractError
from data.targets.scheduling import (
    add_duration, align_feature, normalize_anchors, normalize_endpoint, normalize_entry,
    normalize_horizon, resolve_intervals, schedule_semantics, select_feature_at_anchor,
    temporal_eligible, validate_schedule,
)


def date_schedule():
    # July 3 is the declared exchange holiday. July 4/5 and 11/12 are weekends.
    dates = ["2026-07-01", "2026-07-02", "2026-07-06", "2026-07-07", "2026-07-08",
             "2026-07-09", "2026-07-10", "2026-07-13"]
    return {"policy_id": "TP_MARKET_SCHEDULE", "version": "1.0.0", "temporal_precision": "date",
            "calendar_id": "CAL_SYNTHETIC", "calendar_version": "1.0.0", "timezone": "America/New_York",
            "observation_convention": "session_close", "coverage_start": "2026-07-01",
            "coverage_end": "2026-07-14", "marks": [
                {"mark_id": "M" + str(i), "time": day, "session_id": "S" + str(i)}
                for i, day in enumerate(dates)],
            "evidence": {"id": "EVIDENCE_EXPECTED_CALENDAR", "version": "1.0.0", "content_sha256": "a" * 64}}


def timestamp_schedule(local_times=None, *, zone="America/New_York", session_ids=None):
    local_times = local_times or ["2026-03-06T16:00:00.000000-05:00", "2026-03-09T16:00:00.000000-04:00",
                                "2026-03-10T16:00:00.000000-04:00", "2026-03-11T13:00:00.000000-04:00",
                                "2026-03-12T16:00:00.000000-04:00"]
    result = date_schedule()
    marks = []
    for i, local in enumerate(local_times):
        instant = datetime.fromisoformat(local).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        marks.append({"mark_id": "M" + str(i), "time": instant, "session_id": session_ids[i] if session_ids else "S" + str(i),
                      "local_time": local})
    result.update(temporal_precision="utc_timestamp", timezone=zone, marks=marks,
                  coverage_start=marks[0]["time"], coverage_end=marks[-1]["time"])
    return result


def entry(rule="anchor_mark", amount=0, unit="calendar_days"):
    return {"rule": rule, "delay": {"amount": amount, "unit": unit}}


def horizon(amount=1, unit="trading_sessions"):
    return {"amount": amount, "unit": unit, "counting": "exclusive_entry"}


def endpoint(rule="exact", amount=0, unit="calendar_days"):
    return {"rule": rule, "tolerance": {"amount": amount, "unit": unit}}


def intervals(schedule=None, *, anchors=None, entry_policy=None, horizon_policy=None, endpoint_policy=None):
    return resolve_intervals(schedule or date_schedule(), anchors or {"mode": "market_schedule", "mark_ids": ["M0"]},
                             entry_policy or entry(), horizon_policy or horizon(), endpoint_policy or endpoint())


class TargetScheduleTests(unittest.TestCase):
    def test_session_count_excludes_entry_and_preserves_holiday_weekend(self):
        row = intervals(anchors={"mode": "market_schedule", "mark_ids": ["M1"]}, horizon_policy=horizon(5))[0]
        self.assertEqual(row["entry_time"], "2026-07-02")
        self.assertEqual(row["exit_time"], "2026-07-10")
        self.assertEqual(row["exit_mark_id"], "M6")
        self.assertNotIn("T", row["entry_time"])

    def test_expected_schedule_has_no_dependency_on_observed_prices(self):
        # A missing July 6 price cannot make the expected second endpoint July 7.
        row = intervals(horizon_policy=horizon(2))[0]
        self.assertEqual(row["exit_time"], "2026-07-06")
        schedule = date_schedule()
        schedule["observations"] = [{"time": "2026-07-01", "price": "100"}]
        with self.assertRaises(ContractError):
            validate_schedule(schedule)

    def test_anchor_mark_and_strict_subsequent_entry_have_distinct_meaning(self):
        exact = intervals()[0]
        subsequent = intervals(entry_policy=entry("next_scheduled"))[0]
        self.assertEqual((exact["entry_time"], exact["exit_time"]), ("2026-07-01", "2026-07-02"))
        self.assertEqual((subsequent["entry_time"], subsequent["exit_time"]), ("2026-07-02", "2026-07-06"))
        self.assertEqual(exact["anchor_id"], subsequent["anchor_id"])

    def test_delay_is_applied_before_strict_subsequent_matching(self):
        row = intervals(entry_policy=entry("next_scheduled", 1))[0]
        self.assertEqual(row["entry_time"], "2026-07-06")
        self.assertEqual(row["exit_time"], "2026-07-07")

    def test_delayed_anchor_mark_requires_exact_expected_mark(self):
        row = intervals(entry_policy=entry("anchor_mark", 1))[0]
        self.assertEqual(row["entry_time"], "2026-07-02")
        with self.assertRaisesRegex(ContractError, "exact expected mark"):
            intervals(entry_policy=entry("anchor_mark", 2))

    def test_calendar_horizon_is_not_session_horizon(self):
        session_row = intervals(horizon_policy=horizon(5))[0]
        calendar_row = intervals(horizon_policy=horizon(5, "calendar_days"))[0]
        self.assertEqual(session_row["exit_time"], "2026-07-09")
        self.assertEqual(calendar_row["exit_time"], "2026-07-06")

    def test_calendar_endpoint_explicit_next_schedule_and_bounded_tolerance(self):
        row = intervals(horizon_policy=horizon(2, "calendar_days"),
                        endpoint_policy=endpoint("next_scheduled", 3))[0]
        self.assertEqual(row["intended_end"], "2026-07-03")
        self.assertEqual(row["exit_time"], "2026-07-06")
        with self.assertRaisesRegex(ContractError, "bounded tolerance"):
            intervals(horizon_policy=horizon(2, "calendar_days"), endpoint_policy=endpoint("next_scheduled", 2))
        with self.assertRaisesRegex(ContractError, "not an expected calendar mark"):
            intervals(horizon_policy=horizon(2, "calendar_days"))

    def test_next_endpoint_keeps_exact_match(self):
        row = intervals(endpoint_policy=endpoint("next_scheduled", 2))[0]
        self.assertEqual(row["intended_end"], row["exit_time"])

    def test_all_anchors_preflight_rejects_insufficient_future_calendar(self):
        for horizon_policy in (horizon(1), horizon(100, "calendar_days")):
            with self.subTest(horizon=horizon_policy), self.assertRaisesRegex(ContractError, "coverage"):
                intervals(anchors={"mode": "market_schedule", "mark_ids": ["M0", "M7"]}, horizon_policy=horizon_policy)
        with self.assertRaisesRegex(ContractError, "coverage"):
            intervals(anchors={"mode": "market_schedule", "mark_ids": ["M7"]}, entry_policy=entry("next_scheduled"))

    def test_explicit_anchor_can_be_between_marks_and_remains_date(self):
        row = intervals(anchors={"mode": "explicit", "anchor_set_id": "ANCHORSET_EXAMPLE", "times": ["2026-07-04"]}, entry_policy=entry("next_scheduled"))[0]
        self.assertEqual((row["prediction_anchor"], row["entry_time"], row["exit_time"]),
                         ("2026-07-04", "2026-07-06", "2026-07-07"))
        self.assertEqual(row["temporal_precision"], "date")

    def test_anchor_identity_stable_across_order_and_added_calendar_coverage(self):
        original = normalize_anchors(date_schedule(), {"mode": "market_schedule", "mark_ids": ["M1", "M0"]})
        explicit = normalize_anchors(date_schedule(), {"mode": "explicit", "anchor_set_id": "ANCHORSET_EXAMPLE", "times": ["2026-07-01", "2026-07-02"]})
        expanded = date_schedule()
        expanded["marks"].append({"mark_id": "M8", "time": "2026-07-14", "session_id": "S8"})
        expanded["coverage_end"] = "2026-07-15"
        expanded["evidence"]["content_sha256"] = "b" * 64
        refreshed = normalize_anchors(expanded, {"mode": "market_schedule", "mark_ids": ["M0", "M1"]})
        self.assertNotEqual(original[0]["anchor_id"], explicit[0]["anchor_id"])
        self.assertEqual(original, refreshed)
        self.assertEqual(schedule_semantics(date_schedule()), schedule_semantics(expanded))

    def test_anchor_semantic_timezone_change_changes_identity(self):
        first = normalize_anchors(date_schedule(), {"mode": "market_schedule", "mark_ids": ["M0"]})
        changed = date_schedule()
        changed["timezone"] = "UTC"
        second = normalize_anchors(changed, {"mode": "market_schedule", "mark_ids": ["M0"]})
        self.assertNotEqual(first[0]["anchor_id"], second[0]["anchor_id"])

    def test_explicit_anchor_identity_binds_declared_anchor_set(self):
        request = {"mode": "explicit", "anchor_set_id": "ANCHORSET_A", "times": ["2026-07-01"]}
        first = normalize_anchors(date_schedule(), request)
        second = normalize_anchors(date_schedule(), {**request, "anchor_set_id": "ANCHORSET_B"})
        self.assertNotEqual(first[0]["anchor_id"], second[0]["anchor_id"])
        request.pop("anchor_set_id")
        with self.assertRaises(ContractError):
            normalize_anchors(date_schedule(), request)

    def test_explicit_anchor_validation(self):
        requests = [{"mode": "explicit", "anchor_set_id": "ANCHORSET_EXAMPLE", "times": []}, {"mode": "explicit", "anchor_set_id": "ANCHORSET_EXAMPLE", "times": ["2026-07-01"] * 2},
                    {"mode": "market_schedule", "mark_ids": ["UNKNOWN"]},
                    {"mode": "market_schedule", "mark_ids": ["M0", "M0"]},
                    {"mode": "explicit", "anchor_set_id": "ANCHORSET_EXAMPLE", "times": ["2026-06-01"]},
                    {"mode": "explicit", "anchor_set_id": "ANCHORSET_EXAMPLE", "times": ["2026-07-01T00:00:00.000000Z"]}]
        for anchors in requests:
            with self.subTest(anchors=anchors), self.assertRaises(ContractError):
                normalize_anchors(date_schedule(), anchors)

    def test_strict_structural_policy_validation(self):
        invalid = [(normalize_entry, {"rule": "latest_price", "delay": {"amount": 0, "unit": "calendar_days"}}),
                   (normalize_horizon, horizon(0)), (normalize_horizon, horizon(True)),
                   (normalize_horizon, {**horizon(), "counting": "inclusive_entry"}),
                   (normalize_endpoint, endpoint("exact", 1)), (normalize_endpoint, endpoint("next_scheduled", 0)),
                   (normalize_entry, entry(amount=-1)), (normalize_horizon, horizon(1, "available_rows"))]
        for normalizer, value in invalid:
            with self.subTest(value=value), self.assertRaises(ContractError):
                normalizer(value)

    def test_reject_unknown_timezone_missing_evidence_duplicates_and_bad_version(self):
        mutations = [lambda c: c.update(timezone="Mars/Olympus"), lambda c: c.pop("evidence"),
                     lambda c: c.update(version="2.0.0"), lambda c: c["marks"].append(deepcopy(c["marks"][0])),
                     lambda c: c.update(coverage_end=c["coverage_start"])]
        for mutate in mutations:
            config = date_schedule()
            mutate(config)
            with self.subTest(config=config), self.assertRaises(ContractError):
                validate_schedule(config)

    def test_dst_and_shortened_session_through_declared_marks(self):
        schedule = timestamp_schedule()
        rows = intervals(schedule, anchors={"mode": "market_schedule", "mark_ids": ["M0", "M2"]})
        self.assertEqual((rows[0]["entry_time"], rows[0]["exit_time"]),
                         ("2026-03-06T21:00:00.000000Z", "2026-03-09T20:00:00.000000Z"))
        self.assertEqual(rows[1]["exit_time"], "2026-03-11T17:00:00.000000Z")
        self.assertEqual(schedule["marks"][3]["local_time"], "2026-03-11T13:00:00.000000-04:00")

    def test_timestamp_marks_require_correct_local_offset_evidence(self):
        for bad in (None, "2026-03-09T16:00:00.000000", "2026-03-09T16:00:00.000000-05:00",
                    "2026-03-09T15:00:00.000000-04:00"):
            schedule = timestamp_schedule()
            if bad is None:
                schedule["marks"][1].pop("local_time")
            else:
                schedule["marks"][1]["local_time"] = bad
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                validate_schedule(schedule)

    def test_scheduled_bars_count_independently_of_sessions(self):
        schedule = timestamp_schedule(["2026-03-09T10:00:00.000000-04:00", "2026-03-09T11:00:00.000000-04:00",
                                       "2026-03-10T10:00:00.000000-04:00", "2026-03-10T11:00:00.000000-04:00"],
                                      session_ids=["S0", "S0", "S1", "S1"])
        row = intervals(schedule, horizon_policy=horizon(2, "scheduled_bars"))[0]
        self.assertEqual(row["exit_time"], "2026-03-10T14:00:00.000000Z")
        with self.assertRaisesRegex(ContractError, "one declared observation mark"):
            intervals(schedule)

    def test_elapsed_seconds_and_calendar_days_diverge_at_dst(self):
        schedule = timestamp_schedule(["2026-03-07T16:00:00.000000-05:00", "2026-03-08T16:00:00.000000-04:00",
                                       "2026-03-08T17:00:00.000000-04:00"])
        daily = intervals(schedule, horizon_policy=horizon(1, "calendar_days"))[0]
        elapsed = intervals(schedule, horizon_policy=horizon(86400, "elapsed_seconds"))[0]
        self.assertEqual(daily["exit_time"], "2026-03-08T20:00:00.000000Z")
        self.assertEqual(elapsed["exit_time"], "2026-03-08T21:00:00.000000Z")

    def test_elapsed_entry_delay_and_bounded_second_tolerance(self):
        schedule = timestamp_schedule(["2026-03-09T10:00:00.000000-04:00", "2026-03-09T11:00:00.000000-04:00",
                                       "2026-03-09T12:00:00.000000-04:00", "2026-03-09T13:00:00.000000-04:00"])
        row = intervals(schedule, entry_policy=entry("next_scheduled", 3600, "elapsed_seconds"),
                        horizon_policy=horizon(1800, "elapsed_seconds"),
                        endpoint_policy=endpoint("next_scheduled", 1800, "elapsed_seconds"))[0]
        self.assertEqual(row["entry_time"], "2026-03-09T16:00:00.000000Z")
        self.assertEqual(row["intended_end"], "2026-03-09T16:30:00.000000Z")
        self.assertEqual(row["exit_time"], "2026-03-09T17:00:00.000000Z")

    def test_calendar_interval_rejects_dst_gap_or_ambiguous_endpoint(self):
        for start in ("2026-03-07T07:30:00.000000Z", "2026-10-31T05:30:00.000000Z"):
            with self.subTest(start=start), self.assertRaisesRegex(ContractError, "ambiguous or nonexistent"):
                add_duration(start, {"amount": 1, "unit": "calendar_days"}, "utc_timestamp", "America/New_York")

    def test_zero_delay_does_not_lose_existing_dst_fold_evidence(self):
        start = "2026-11-01T06:30:00.000000Z"
        self.assertEqual(add_duration(start, {"amount": 0, "unit": "calendar_days"},
                                      "utc_timestamp", "America/New_York"), start)

    def test_date_precision_rejects_all_elapsed_seconds_policy_fields(self):
        for args in ({"entry_policy": entry(unit="elapsed_seconds")},
                     {"horizon_policy": horizon(86400, "elapsed_seconds")},
                     {"endpoint_policy": endpoint(unit="elapsed_seconds")}):
            with self.subTest(args=args), self.assertRaisesRegex(ContractError, "timestamp precision"):
                intervals(**args)
        with self.assertRaises(ContractError):
            add_duration("2026-07-01", {"amount": 1, "unit": "elapsed_seconds"}, "date", "UTC")

    def test_local_date_boundary_not_utc_date_used_for_calendar_interval(self):
        start = "2026-03-08T04:30:00.000000Z"  # March 7 23:30 local.
        self.assertEqual(add_duration(start, {"amount": 1, "unit": "calendar_days"},
                                      "utc_timestamp", "America/New_York"), "2026-03-09T03:30:00.000000Z")

    def test_supported_horizon_entry_endpoint_anchor_mode_combinations(self):
        dates = date_schedule()
        dates["marks"] = [{"mark_id": "M" + str(i), "time": "2026-07-" + str(6+i).zfill(2),
                           "session_id": "S" + str(i)} for i in range(5)]
        dates.update(coverage_start="2026-07-06", coverage_end="2026-07-10")
        stamps = timestamp_schedule(["2026-07-" + str(6+i).zfill(2) + "T16:00:00.000000-04:00" for i in range(5)])
        tested = 0
        for schedule in (dates, stamps):
            for unit in ("trading_sessions", "scheduled_bars", "calendar_days", "elapsed_seconds"):
                if unit == "elapsed_seconds" and schedule["temporal_precision"] == "date":
                    continue
                for entry_rule in ("anchor_mark", "next_scheduled"):
                    for endpoint_rule in ("exact", "next_scheduled"):
                        for anchor_mode in ("market_schedule", "explicit"):
                            request = ({"mode": anchor_mode, "mark_ids": ["M0"]} if anchor_mode == "market_schedule"
                                       else {"mode": anchor_mode, "anchor_set_id": "ANCHORSET_EXAMPLE", "times": [schedule["marks"][0]["time"]]})
                            with self.subTest(precision=schedule["temporal_precision"], unit=unit,
                                              entry_rule=entry_rule, endpoint_rule=endpoint_rule, anchor_mode=anchor_mode):
                                row = intervals(schedule, anchors=request, entry_policy=entry(entry_rule),
                                                horizon_policy=horizon(86400 if unit == "elapsed_seconds" else 1, unit),
                                                endpoint_policy=endpoint(endpoint_rule, int(endpoint_rule == "next_scheduled")))[0]
                                expected_index = 1 if entry_rule == "anchor_mark" else 2
                                self.assertEqual(row["exit_time"], schedule["marks"][expected_index]["time"])
                                tested += 1
        self.assertEqual(tested, 56)

    def test_next_endpoint_requires_actual_expected_mark_within_coverage(self):
        with self.assertRaisesRegex(ContractError, "coverage"):
            intervals(anchors={"mode": "market_schedule", "mark_ids": ["M7"]},
                      horizon_policy=horizon(1, "calendar_days"), endpoint_policy=endpoint("next_scheduled", 3))

    def test_calendar_session_membership_cannot_reappear_after_later_session(self):
        schedule = timestamp_schedule()
        schedule["marks"][2]["session_id"] = schedule["marks"][0]["session_id"]
        with self.assertRaisesRegex(ContractError, "contiguous"):
            validate_schedule(schedule)


class TargetTemporalAlignmentTests(unittest.TestCase):
    def test_exact_timestamp_availability_including_equal(self):
        at = "2026-07-01T14:00:00.000000Z"
        self.assertTrue(temporal_eligible(at, "utc_timestamp", at, "utc_timestamp")["eligible"])
        self.assertEqual(temporal_eligible("2026-07-01T14:00:00.000001Z", "utc_timestamp", at,
                                           "utc_timestamp")["reason"], "NOT_YET_AVAILABLE")

    def test_date_same_day_never_implies_ordering(self):
        self.assertEqual(temporal_eligible("2026-07-01", "date", "2026-07-01", "date"),
                         {"eligible": False, "reason": "AMBIGUOUS_SAME_DAY"})
        self.assertTrue(temporal_eligible("2026-07-01", "date", "2026-07-02", "date")["eligible"])

    def test_missing_availability_uncertified(self):
        self.assertEqual(temporal_eligible(None, "date", "2026-07-02", "date")["reason"], "AVAILABILITY_UNKNOWN")

    def test_mixed_precision_requires_declared_conservative_policy_and_timezone(self):
        args = ("2026-07-01", "date", "2026-07-02T01:00:00.000000Z", "utc_timestamp")
        self.assertEqual(temporal_eligible(*args)["reason"], "TEMPORAL_PRECISION_INCOMPATIBLE")
        self.assertEqual(temporal_eligible(*args, policy="conservative_next_day")["reason"], "TEMPORAL_PRECISION_INCOMPATIBLE")
        self.assertTrue(temporal_eligible(*args, policy="conservative_next_day", timezone="UTC")["eligible"])
        self.assertEqual(temporal_eligible(*args, policy="conservative_next_day", timezone="America/New_York")["reason"],
                         "AMBIGUOUS_SAME_DAY")

    def test_timestamp_to_date_conservative_never_assumes_start_or_end_of_day(self):
        self.assertFalse(temporal_eligible("2026-07-01T00:01:00.000000Z", "utc_timestamp", "2026-07-01", "date",
                                           policy="conservative_next_day", timezone="UTC")["eligible"])
        self.assertTrue(temporal_eligible("2026-07-01T23:59:59.000000Z", "utc_timestamp", "2026-07-02", "date",
                                          policy="conservative_next_day", timezone="UTC")["eligible"])

    def test_feature_alignment_separates_feature_cutoff_from_future_target_exit(self):
        interval = intervals(anchors={"mode": "market_schedule", "mark_ids": ["M1"]})[0]
        feature = {"reference_time": "2026-06-01", "evaluation_cutoff": "2026-07-01", "available_at": "2026-07-01",
                   "value": "10", "status": "valid"}
        self.assertTrue(align_feature(feature, "date", interval)["eligible"])
        feature["available_at"] = interval["exit_time"]
        self.assertFalse(align_feature(feature, "date", interval)["eligible"])

    def test_falsified_early_availability_cannot_hide_late_feature_evaluation(self):
        interval = intervals(anchors={"mode": "market_schedule", "mark_ids": ["M1"]})[0]
        feature = {"available_at": "2026-07-01", "evaluation_cutoff": "2026-07-06", "status": "valid"}
        self.assertEqual(align_feature(feature, "date", interval)["reason"], "FEATURE_EVALUATION_CUTOFF_AFTER_ANCHOR")
        feature = {"available_at": "2026-07-01", "reference_time": "2026-07-06", "status": "valid"}
        self.assertEqual(align_feature(feature, "date", interval)["reason"], "FEATURE_REFERENCE_TIME_AFTER_ANCHOR")

    def test_future_source_feature_rows_cannot_change_earlier_selection(self):
        interval = intervals(anchors={"mode": "market_schedule", "mark_ids": ["M1"]})[0]
        rows = [{"entity_id": "E", "measure": "M", "dimensions": [], "reference_time": "2026-06-01",
                 "evaluation_cutoff": "2026-07-01", "available_at": "2026-07-01", "value": "10", "status": "valid"}]
        first = select_feature_at_anchor(rows, "date", interval)
        rows.append({**rows[0], "evaluation_cutoff": "2026-07-06", "available_at": "2026-07-06", "value": "999"})
        self.assertEqual(first, select_feature_at_anchor(rows, "date", interval))
        self.assertEqual(first["value"], "10")

    def test_invalid_or_ambiguous_feature_selection_not_silently_chosen(self):
        interval = intervals(anchors={"mode": "market_schedule", "mark_ids": ["M1"]})[0]
        row = {"entity_id": "E", "available_at": "2026-07-01", "status": "valid"}
        self.assertIsNone(select_feature_at_anchor([{**row, "status": "invalid"}], "date", interval))
        with self.assertRaises(ContractError):
            select_feature_at_anchor([row, deepcopy(row)], "date", interval)
        with self.assertRaises(ContractError):
            select_feature_at_anchor([row, {**row, "entity_id": "OTHER", "available_at": "2026-07-06"}], "date", interval)


if __name__ == "__main__":
    unittest.main()
