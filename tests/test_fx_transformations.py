"""Independent arithmetic and temporal/lineage acceptance for bounded FX prices."""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import math
import unittest
from unittest.mock import patch

from data.transformations.contracts import ContractError
from data.transformations.identity import digest
from data.transformations import fx


def policy(mode="retrospective_date_label", approval="approved"):
    return {"id": "POL_FX_" + mode.upper(), "version": "1.0.0", "mode": mode,
            "approval_state": approval,
            "approval_evidence": {"id": "EVIDENCE_SYNTHETIC_ALIGNMENT", "version": "1.0.0", "content_sha256": "a" * 64},
            "max_date_gap": 0, "max_valuation_gap_seconds": 0 if mode == "exact_valuation" else None}


def metadata(symbol, *, exact=False, basis="unknown"):
    base, quote = symbol.split("/")
    return {"base_currency": base, "quote_currency": quote, "unit": quote + "_per_" + base,
            "price_basis": basis, "price_field": "close",
            "timing": {"timezone": "America/New_York" if exact else None,
                       "bar_boundary": "16:00 local" if exact else None,
                       "session_convention": "synthetic_expected_close" if exact else None,
                       "synchronization": "exact" if exact else "unverified"}}


def source_row(symbol, day, value, *, available=None, ingest="2026-09-06T21:03:46.000000Z", exact=False):
    row = {"reference_time": day, "value": value, "status": "valid", "reason_code": None,
           "lineage": "FXSOURCE_" + digest({"symbol": symbol, "day": day, "value": value}),
           "available_at": available, "original_ingested_at": ingest, "vintage_id": "LEGACY_CAPTURE_1"}
    if exact:
        offset = "-05:00" if day <= "2026-03-07" else "-04:00"
        hour = "21" if offset == "-05:00" else "20"
        row.update(valuation_time=day + "T" + hour + ":00:00.000000Z", local_time=day + "T16:00:00.000000" + offset)
    return row


def inputs(*, exact=False, basis="unknown"):
    values = {"AUD/USD": "0.65", "EUR/USD": "1.2", "GBP/USD": "1.5", "NZD/USD": "0.6",
              "USD/CNH": "7.2", "CAD/USD": "0.75", "CHF/USD": "1.1", "JPY/USD": "0.00625",
              "CZK/USD": "0.04", "HKD/USD": "0.128", "HUF/USD": "0.0028", "ILS/USD": "0.27",
              "MXN/USD": "0.05", "NOK/USD": "0.095", "PLN/USD": "0.25", "SEK/USD": "0.1",
              "SGD/USD": "0.74", "ZAR/USD": "0.055"}
    sources = {symbol: [source_row(symbol, "2026-03-06", value, exact=exact)] for symbol, value in values.items()}
    metas = {symbol: metadata(symbol, exact=exact, basis=basis) for symbol in sources}
    return sources, metas


def construct(instrument="EURJPY", *, sources=None, metas=None, alignment=None):
    defaults, defaults_meta = inputs()
    return fx.construct_prices(instrument, defaults if sources is None else sources,
                               source_metadata=defaults_meta if metas is None else metas,
                               alignment_policy=alignment or policy())


class FxUniverseAndArithmeticTests(unittest.TestCase):
    def test_exact_requested_source_universe_and_method_counts(self):
        expected_sources = {"AUD/USD", "EUR/USD", "GBP/USD", "NZD/USD", "USD/CNH", "CAD/USD", "CHF/USD", "JPY/USD",
                            "CZK/USD", "HKD/USD", "HUF/USD", "ILS/USD", "MXN/USD", "NOK/USD", "PLN/USD", "SEK/USD", "SGD/USD", "ZAR/USD"}
        expected_crosses = {"AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "CADCHF", "CADJPY", "CHFJPY", "EURAUD", "EURCAD",
                            "EURCHF", "EURGBP", "EURJPY", "EURNZD", "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
                            "NZDCAD", "NZDCHF", "NZDJPY", "EURCZK", "EURHUF", "EURNOK", "EURPLN"}
        self.assertEqual(set(fx.SOURCE_SYMBOLS), expected_sources)
        self.assertEqual(set(fx.CROSS), expected_crosses)
        self.assertEqual((len(fx.DIRECT), len(fx.INVERSE), len(fx.CROSS), len(set(fx.INSTRUMENTS))), (5, 13, 25, 43))
        self.assertEqual(len({item["economic_id"] for item in fx.universe_specs()}), 43)

    def test_all_43_prices_against_independent_rational_formula(self):
        sources, metas = inputs()
        results = fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy())
        normalized = {"USD": Fraction(1)}
        for symbol, rows in sources.items():
            base, quote = symbol.split("/")
            normalized[quote if base == "USD" else base] = 1 / Fraction(rows[0]["value"]) if base == "USD" else Fraction(rows[0]["value"])
        self.assertEqual(set(results), set(fx.INSTRUMENTS))
        for instrument, rows in results.items():
            with self.subTest(instrument=instrument), localcontext() as context:
                context.prec = 70
                rational = normalized[instrument[:3]] / normalized[instrument[3:]]
                expected = Decimal(rational.numerator) / Decimal(rational.denominator)
                actual = Decimal(rows[0]["value"])
                self.assertLess(abs(actual - expected), max(abs(expected), Decimal(1)) * Decimal("1e-48"))
                self.assertEqual(rows[0]["status"], "valid")
                self.assertEqual(rows[0]["unit"], instrument[3:] + "_per_" + instrument[:3])

    def test_known_direct_inverse_and_cross_prices(self):
        for instrument, expected in (("EURUSD", "1.2"), ("USDJPY", "160"), ("EURJPY", "192"), ("EURGBP", "0.8"), ("EURCZK", "30")):
            with self.subTest(instrument=instrument):
                self.assertEqual(construct(instrument)[0]["value"], expected)

    def test_original_usdcnh_never_makes_reciprocal_round_trip(self):
        sources, metas = inputs()
        original = "7." + "123456789" * 8
        sources["USD/CNH"][0]["value"] = original
        row = construct("USDCNH", sources=sources, metas=metas)[0]
        self.assertEqual(row["value"], original)
        self.assertEqual(row["method"], "direct")
        self.assertEqual(row["normalized_leg_dependencies"][1]["currency"], "CNH")
        self.assertNotEqual(row["normalized_leg_dependencies"][1]["value"], original)

    def test_reciprocal_and_triangle_consistency_with_declared_tolerance(self):
        with localcontext() as context:
            context.prec = 70
            self.assertLess(abs(Decimal(construct("USDJPY")[0]["value"]) * Decimal("0.00625") - 1), Decimal("1e-48"))
            eur_gbp = Decimal(construct("EURGBP")[0]["value"])
            gbp_jpy = Decimal(construct("GBPJPY")[0]["value"])
            eur_jpy = Decimal(construct("EURJPY")[0]["value"])
            self.assertLess(abs(eur_gbp * gbp_jpy - eur_jpy), Decimal("1e-46"))

    def test_cross_log_return_is_difference_of_leg_logs(self):
        sources, metas = inputs()
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-09", "1.32"))
        sources["JPY/USD"].append(source_row("JPY/USD", "2026-03-09", "0.0075"))
        rows = construct("EURJPY", sources=sources, metas=metas)
        cross = math.log(float(rows[1]["value"]) / float(rows[0]["value"]))
        independent = math.log(1.32 / 1.2) - math.log(0.0075 / 0.00625)
        self.assertAlmostEqual(cross, independent, places=14)
        simple = Decimal(rows[1]["value"]) / Decimal(rows[0]["value"]) - 1
        self.assertNotAlmostEqual(float(simple), (1.32 / 1.2 - 1) - (0.0075 / 0.00625 - 1), places=7)

    def test_inverse_simple_return_is_not_negated_source_simple_return(self):
        sources, metas = inputs()
        sources["JPY/USD"] = [source_row("JPY/USD", "2026-03-06", "2"), source_row("JPY/USD", "2026-03-09", "4")]
        rows = construct("USDJPY", sources=sources, metas=metas)
        result = Decimal(rows[1]["value"]) / Decimal(rows[0]["value"]) - 1
        self.assertEqual(result, Decimal("-0.5"))
        self.assertNotEqual(result, -(Decimal(4) / Decimal(2) - 1))

    def test_full_universe_normalizes_inputs_once(self):
        sources, metas = inputs()
        with patch.object(fx, "_normalize_prepared", wraps=fx._normalize_prepared) as normalization:
            fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy())
        self.assertEqual(normalization.call_count, 1)
        normalized = fx.normalize_legs(sources, source_metadata=metas)
        self.assertEqual(len(normalized), 18)
        self.assertNotIn("USD", normalized)

    def test_streaming_universe_constructs_only_consumed_instruments(self):
        sources, metas = inputs()
        with patch.object(fx, "_construct", wraps=fx._construct) as construction:
            stream = fx.iter_construct_universe(sources, source_metadata=metas, alignment_policy=policy(),
                                               single_source_policy=policy("single_source_observation"))
            self.assertEqual(construction.call_count, 0)
            instrument, rows = next(stream)
            self.assertEqual(instrument, "AUDUSD")
            self.assertEqual(len(rows), 1)
            self.assertEqual(construction.call_count, 1)
            stream.close()

    def test_cny_or_extra_source_cannot_substitute_for_cnh(self):
        sources, metas = inputs()
        sources["USD/CNY"] = sources.pop("USD/CNH")
        with self.assertRaises(ContractError):
            construct("USDCNH", sources=sources, metas=metas)
        sources, metas = inputs()
        sources["BRL/USD"] = []
        with self.assertRaises(ContractError):
            fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy())
        with self.assertRaises(ContractError):
            fx.instrument_spec("USDCNY")

    def test_currency_metadata_is_checked_independently_of_display_symbol(self):
        for field, value in (("base_currency", "GBP"), ("quote_currency", "EUR"), ("unit", "EUR_per_USD"), ("price_field", "high")):
            sources, metas = inputs()
            metas["EUR/USD"][field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                construct("EURUSD", sources=sources, metas=metas)


class FxQualityAndCoverageTests(unittest.TestCase):
    def test_invalid_nonfinite_nonpositive_prices_retained_as_null(self):
        for value, reason in (("0", "NONPOSITIVE_INPUT"), ("-1", "NONPOSITIVE_INPUT"), ("NaN", "NONFINITE_INPUT"),
                              ("Infinity", "NONFINITE_INPUT"), ("9" * 310, "NONFINITE_INPUT"), (None, "NON_NUMERIC_INPUT"),
                              ("garbage", "NON_NUMERIC_INPUT")):
            sources, metas = inputs()
            sources["JPY/USD"][0]["value"] = value
            with self.subTest(value=value):
                row = construct(sources=sources, metas=metas)[0]
                self.assertEqual((row["value"], row["status"], row["reason_code"]), (None, "invalid", reason))

    def test_inverse_overflow_is_null_not_infinity(self):
        sources, metas = inputs()
        sources["JPY/USD"][0]["value"] = "0." + "0" * 400 + "1"
        row = construct("USDJPY", sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["reason_code"]), (None, "NONFINITE_OUTPUT"))

    def test_conflicting_duplicates_are_not_silently_first_or_last(self):
        sources, metas = inputs()
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-06", "999"))
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["reason_code"]), (None, "CONFLICTING_SOURCE_OBSERVATIONS"))
        self.assertEqual(len(row["input_dependencies"]), 3)

    def test_exact_repeat_duplicate_is_diagnostic_and_not_an_economic_change(self):
        sources, metas = inputs()
        before = construct(sources=sources, metas=metas)[0]
        sources["EUR/USD"].append(deepcopy(sources["EUR/USD"][0]))
        after = construct(sources=sources, metas=metas)[0]
        self.assertEqual((before["id"], before["value"]), (after["id"], after["value"]))
        self.assertEqual(after["duplicate_input_count"], 1)

    def test_missing_dates_keep_union_and_do_not_carry_other_leg(self):
        sources, metas = inputs()
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-09", "1.3"))
        sources["JPY/USD"].append(source_row("JPY/USD", "2026-03-10", "0.007"))
        rows = construct(sources=sources, metas=metas)
        self.assertEqual([row["reference_time"] for row in rows], ["2026-03-06", "2026-03-09", "2026-03-10"])
        self.assertEqual([row["status"] for row in rows], ["valid", "missing", "missing"])
        self.assertTrue(all(row["value"] is None for row in rows[1:]))

    def test_missing_source_history_does_not_truncate_unrelated_instruments(self):
        sources, metas = inputs()
        sources["JPY/USD"] = []
        results = fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy())
        self.assertEqual(results["EURUSD"][0]["value"], "1.2")
        self.assertEqual(results["EURGBP"][0]["value"], "0.8")
        self.assertEqual(results["EURJPY"][0]["reason_code"], "MISSING_REQUIRED_OBSERVATION")
        self.assertEqual(results["USDJPY"], [])

    def test_stale_evidence_rejected_but_unchanged_prices_not_called_stale(self):
        sources, metas = inputs()
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-09", "1.2"))
        self.assertTrue(all(row["status"] == "valid" for row in construct("EURUSD", sources=sources, metas=metas)))
        sources["EUR/USD"][1]["stale"] = True
        rows = construct("EURUSD", sources=sources, metas=metas)
        self.assertEqual(rows[1]["reason_code"], "STALE_SOURCE_OBSERVATION")

    def test_suspicious_change_flags_survive_without_clipping(self):
        sources, metas = inputs()
        sources["EUR/USD"][0]["value"] = "1200"
        sources["EUR/USD"][0]["quality_flags"] = ["SUSPICIOUS_CHANGE_REVIEW"]
        row = construct("EURUSD", sources=sources, metas=metas)[0]
        self.assertEqual(row["value"], "1200")
        self.assertIn("SUSPICIOUS_CHANGE_REVIEW", row["quality_flags"])

    def test_mixed_price_bases_rejected_and_midpoint_label_only_when_evidenced(self):
        sources, metas = inputs()
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual(row["price_description"], "triangulated_unknown_proxy")
        self.assertNotIn("midpoint", row["price_description"])
        metas["EUR/USD"]["price_basis"] = "midpoint"
        self.assertEqual(construct(sources=sources, metas=metas)[0]["reason_code"], "INCOMPATIBLE_PRICE_BASIS")
        metas["JPY/USD"]["price_basis"] = "midpoint"
        self.assertEqual(construct(sources=sources, metas=metas)[0]["price_description"], "triangulated_midpoint_proxy")


class FxTimingAndReuseTests(unittest.TestCase):
    def test_alignment_requires_actual_explicit_approval_reference(self):
        for alignment in (policy(approval="pending"), {**policy(), "approval_evidence": None},
                          {**policy(), "max_date_gap": 1}, {**policy(), "max_valuation_gap_seconds": 0}):
            with self.subTest(policy=alignment), self.assertRaises(ContractError):
                construct(alignment=alignment)

    def test_pending_recipe_can_be_registered_but_does_not_execute(self):
        _, metas = inputs()
        unbound = fx.recipe("EURJPY", metas)
        self.assertIsNone(unbound["body"]["alignment_policy"])
        with self.assertRaises(ContractError):
            construct(alignment=policy(approval="pending"))

    def test_single_source_policy_cannot_claim_or_enable_cross_synchronization(self):
        row = construct("USDCNH", alignment=policy("single_source_observation"))[0]
        self.assertEqual(row["synchronization"], "not_applicable_single_source")
        self.assertEqual(row["value"], "7.2")
        with self.assertRaises(ContractError):
            construct(alignment=policy("single_source_observation"))

    def test_retrospective_date_join_never_claims_exact_synchronization(self):
        row = construct()[0]
        self.assertEqual(row["synchronization"], "unverified")
        self.assertIn("SYNCHRONIZATION_UNVERIFIED", row["quality_flags"])
        self.assertIsNone(row["valuation_time"])
        self.assertFalse(row["historical_eligibility_certified"])

    def test_retrospective_unknown_timing_is_allowed_even_if_one_leg_has_evidence(self):
        sources, metas = inputs()
        metas["EUR/USD"]["timing"].update(timezone="America/New_York", bar_boundary="16:00 local", session_convention="provider_daily_close")
        sources["EUR/USD"][0].update(valuation_time="2026-03-06T21:00:00.000000Z", local_time="2026-03-06T16:00:00.000000-05:00")
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["status"], row["synchronization"]), ("192", "valid", "unverified"))
        self.assertIsNone(row["valuation_time"])
        self.assertIsNone(row["available_at"])
        self.assertFalse(row["historical_eligibility_certified"])

    def test_retrospective_known_incompatible_bar_or_session_is_blocked(self):
        for field in ("bar_boundary", "session_convention"):
            sources, metas = inputs()
            metas["EUR/USD"]["timing"][field] = "provider convention A"
            metas["JPY/USD"]["timing"][field] = "provider convention B"
            with self.subTest(field=field):
                row = construct(sources=sources, metas=metas)[0]
                self.assertEqual((row["value"], row["status"], row["reason_code"]), (None, "invalid", "INCOMPATIBLE_SESSION_CONVENTION"))
                self.assertEqual(row["reference_time"], "2026-03-06")
                self.assertEqual(len(row["input_dependencies"]), 2)

    def test_retrospective_timezone_names_alone_do_not_prove_incompatibility(self):
        sources, metas = inputs()
        metas["EUR/USD"]["timing"]["timezone"] = "America/New_York"
        metas["JPY/USD"]["timing"]["timezone"] = "Asia/Tokyo"
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["status"], row["synchronization"]), ("192", "valid", "unverified"))
        self.assertIsNone(row["valuation_time"])

    def test_retrospective_equivalent_known_timezone_representations_are_not_a_defect(self):
        sources, metas = inputs()
        metas["EUR/USD"]["timing"]["timezone"] = "America/New_York"
        metas["JPY/USD"]["timing"]["timezone"] = "Etc/UTC"
        sources["EUR/USD"][0].update(valuation_time="2026-03-06T21:00:00.000000Z", local_time="2026-03-06T16:00:00.000000-05:00")
        sources["JPY/USD"][0].update(valuation_time="2026-03-06T21:00:00.000000Z", local_time="2026-03-06T21:00:00.000000+00:00")
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["status"], row["synchronization"]), ("192", "valid", "unverified"))
        self.assertIsNone(row["valuation_time"])
        self.assertFalse(row["historical_eligibility_certified"])

    def test_matching_utc_instants_do_not_require_redundant_local_timestamps(self):
        sources, metas = inputs()
        metas["EUR/USD"]["timing"]["timezone"] = "America/New_York"
        metas["JPY/USD"]["timing"]["timezone"] = "Etc/UTC"
        for symbol in ("EUR/USD", "JPY/USD"):
            sources[symbol][0]["valuation_time"] = "2026-03-06T21:00:00.000000Z"
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["status"], row["synchronization"]), ("192", "valid", "unverified"))
        self.assertIsNone(row["valuation_time"])

    def test_known_utc_and_timezone_cannot_contradict_native_date_without_local_stamp(self):
        sources, metas = inputs()
        metas["JPY/USD"]["timing"]["timezone"] = "Asia/Tokyo"
        sources["JPY/USD"][0]["valuation_time"] = "2026-03-06T21:00:00.000000Z"
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["reason_code"]), (None, "INCOMPATIBLE_VALUATION_TIME"))

    def test_retrospective_known_different_valuation_instants_cannot_use_unknown_tolerance(self):
        sources, metas = inputs()
        sources["EUR/USD"][0]["valuation_time"] = "2026-03-06T21:00:00.000000Z"
        sources["JPY/USD"][0]["valuation_time"] = "2026-03-06T21:00:00.000001Z"
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["status"], row["reason_code"]), (None, "invalid", "INCOMPATIBLE_VALUATION_TIME"))
        self.assertIsNone(policy()["max_valuation_gap_seconds"])

    def test_retrospective_conflicting_local_utc_dst_and_native_date_evidence_is_blocked(self):
        invalid_local_times = ("2026-03-06T16:00:00.000000-04:00", "2026-03-09T16:00:00.000000-04:00", "2026-03-06T16:00:00", "invalid")
        for local_time in invalid_local_times:
            sources, metas = inputs(exact=True)
            sources["JPY/USD"][0]["local_time"] = local_time
            with self.subTest(local_time=local_time):
                row = construct(sources=sources, metas=metas)[0]
                self.assertEqual((row["value"], row["reason_code"]), (None, "INCOMPATIBLE_VALUATION_TIME"))

    def test_retrospective_local_offset_alone_cannot_contradict_known_timezone(self):
        sources, metas = inputs()
        metas["JPY/USD"]["timing"]["timezone"] = "America/New_York"
        sources["JPY/USD"][0]["local_time"] = "2026-03-06T16:00:00.000000-04:00"
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual(row["reason_code"], "INCOMPATIBLE_VALUATION_TIME")

    def test_retrospective_evidence_grade_difference_is_not_session_incompatibility(self):
        sources, metas = inputs(exact=True)
        metas["JPY/USD"]["timing"]["synchronization"] = "unverified"
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual((row["value"], row["status"], row["synchronization"]), ("192", "valid", "unverified"))

    def test_known_timing_defect_changes_only_affected_cross_date(self):
        sources, metas = inputs()
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-09", "1.3"))
        sources["JPY/USD"].append(source_row("JPY/USD", "2026-03-09", "0.007"))
        original = construct(sources=sources, metas=metas)
        sources["EUR/USD"][1]["valuation_time"] = "2026-03-09T20:00:00.000000Z"
        sources["JPY/USD"][1]["valuation_time"] = "2026-03-09T19:00:00.000000Z"
        changed = construct(sources=sources, metas=metas)
        self.assertEqual(original[0], changed[0])
        self.assertEqual(changed[1]["reason_code"], "INCOMPATIBLE_VALUATION_TIME")

    def test_exact_mode_rejects_unverified_source_times(self):
        row = construct(alignment=policy("exact_valuation"))[0]
        self.assertIsNone(row["value"])
        self.assertEqual(row["reason_code"], "UNVERIFIED_VALUATION_TIME")
        self.assertNotEqual(row["synchronization"], "exact")

    def test_exact_valuation_checks_timezone_offset_and_dst_changes(self):
        sources, metas = inputs(exact=True)
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-09", "1.32", exact=True))
        sources["JPY/USD"].append(source_row("JPY/USD", "2026-03-09", "0.0075", exact=True))
        rows = construct(sources=sources, metas=metas, alignment=policy("exact_valuation"))
        self.assertEqual([row["valuation_time"] for row in rows], ["2026-03-06T21:00:00.000000Z", "2026-03-09T20:00:00.000000Z"])
        self.assertTrue(all(row["synchronization"] == "exact" and row["status"] == "valid" for row in rows))
        sources["JPY/USD"][1]["local_time"] = "2026-03-09T16:00:00.000000-05:00"
        self.assertEqual(construct(sources=sources, metas=metas, alignment=policy("exact_valuation"))[1]["reason_code"], "INCOMPATIBLE_VALUATION_TIME")

    def test_matching_date_is_insufficient_for_different_actual_closes(self):
        sources, metas = inputs(exact=True)
        sources["JPY/USD"][0].update(valuation_time="2026-03-06T20:00:00.000000Z", local_time="2026-03-06T15:00:00.000000-05:00")
        self.assertEqual(construct(sources=sources, metas=metas, alignment=policy("exact_valuation"))[0]["reason_code"], "INCOMPATIBLE_VALUATION_TIME")
        sources, metas = inputs(exact=True)
        metas["JPY/USD"]["timing"]["bar_boundary"] = "different underlying daily bar"
        self.assertEqual(construct(sources=sources, metas=metas, alignment=policy("exact_valuation"))[0]["reason_code"], "INCOMPATIBLE_SESSION_CONVENTION")

    def test_missing_local_evidence_cannot_be_repaired_by_utc_label(self):
        sources, metas = inputs(exact=True)
        sources["JPY/USD"][0].pop("local_time")
        self.assertEqual(construct(sources=sources, metas=metas, alignment=policy("exact_valuation"))[0]["reason_code"], "UNVERIFIED_VALUATION_TIME")

    def test_future_valuation_cannot_be_backdated_to_an_earlier_native_date(self):
        sources, metas = inputs(exact=True)
        for symbol in ("EUR/USD", "JPY/USD"):
            sources[symbol][0].update(valuation_time="2026-03-09T20:00:00.000000Z", local_time="2026-03-09T16:00:00.000000-04:00")
        row = construct(sources=sources, metas=metas, alignment=policy("exact_valuation"))[0]
        self.assertEqual(row["reason_code"], "INCOMPATIBLE_VALUATION_TIME")
        self.assertIsNone(row["value"])

    def test_source_availability_cannot_precede_its_evidenced_valuation(self):
        sources, metas = inputs(exact=True)
        sources["EUR/USD"][0]["available_at"] = "2026-03-06T20:00:00.000000Z"
        row = construct(sources=sources, metas=metas, alignment=policy("exact_valuation"))[0]
        self.assertEqual(row["reason_code"], "AVAILABILITY_PRECEDES_VALUATION")
        sources["EUR/USD"][0]["available_at"] = "2026-03-05"
        self.assertEqual(construct(sources=sources, metas=metas)[0]["reason_code"], "AVAILABILITY_PRECEDES_VALUATION")

    def test_availability_maximum_and_unknown_propagate_separately_from_ingestion(self):
        sources, metas = inputs()
        sources["EUR/USD"][0]["available_at"] = "2026-03-07"
        sources["JPY/USD"][0]["available_at"] = "2026-03-08"
        sources["JPY/USD"][0]["original_ingested_at"] = "2026-09-07T01:00:00.000000Z"
        row = construct(sources=sources, metas=metas)[0]
        self.assertEqual(row["available_at"], "2026-03-08")
        self.assertEqual(row["original_ingested_at"], "2026-09-07T01:00:00.000000Z")
        sources["JPY/USD"][0]["available_at"] = None
        row = construct(sources=sources, metas=metas)[0]
        self.assertIsNone(row["available_at"])
        self.assertEqual(row["original_ingested_at"], "2026-09-07T01:00:00.000000Z")
        self.assertFalse(row["historical_eligibility_certified"])

    def test_mixed_availability_precision_remains_uncertified(self):
        sources, metas = inputs()
        sources["EUR/USD"][0]["available_at"] = "2026-03-07"
        sources["JPY/USD"][0]["available_at"] = "2026-03-08T00:00:00.000000Z"
        self.assertIsNone(construct(sources=sources, metas=metas)[0]["available_at"])

    def test_unrelated_future_rows_do_not_change_prior_price_identity(self):
        sources, metas = inputs()
        before = construct(sources=sources, metas=metas)[0]
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-09", "9876"))
        after = construct(sources=sources, metas=metas)[0]
        self.assertEqual(before, after)

    def test_revision_invalidates_only_dependent_date_and_instrument(self):
        sources, metas = inputs()
        sources["EUR/USD"].append(source_row("EUR/USD", "2026-03-09", "1.32"))
        sources["JPY/USD"].append(source_row("JPY/USD", "2026-03-09", "0.0075"))
        old = fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy())
        old_input = next(item["id"] for item in old["EURJPY"][0]["input_dependencies"] if item["source_symbol"] == "EUR/USD")
        sources["EUR/USD"][0] = source_row("EUR/USD", "2026-03-06", "1.21")
        new = fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy())
        self.assertEqual(fx.affected_price_rows(old["EURJPY"], {old_input}), [old["EURJPY"][0]["id"]])
        self.assertEqual(fx.affected_price_rows(old["GBPJPY"], {old_input}), [])
        self.assertNotEqual(old["EURJPY"][0]["id"], new["EURJPY"][0]["id"])
        self.assertEqual(old["EURJPY"][1], new["EURJPY"][1])
        self.assertEqual(old["GBPJPY"], new["GBPJPY"])

    def test_economic_identity_independent_of_source_and_recipe_purpose(self):
        sources, metas = inputs()
        identity = fx.instrument_spec("EURJPY")["economic_id"]
        old = fx.recipe("EURJPY", metas, policy())
        metas["EUR/USD"]["source_view"] = {"id": "SVIEW_OTHER_PROVIDER", "version": "1.0.0", "content_sha256": "f" * 64}
        new = fx.recipe("EURJPY", metas, policy())
        self.assertEqual(identity, "FX_EUR_JPY")
        self.assertNotEqual(old["id"], new["id"])
        self.assertFalse(any(key in old["body"] for key in ("target_id", "signal_id", "feature_id", "horizon")))

    def test_full_universe_can_reuse_previously_built_single_source_prices(self):
        sources, metas = inputs()
        single = policy("single_source_observation")
        original = construct("USDCNH", sources=sources, metas=metas, alignment=single)
        all_rows = fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy(), single_source_policy=single)
        self.assertEqual(original, all_rows["USDCNH"])

    def test_existing_18_direct_inverse_recipe_and_row_identities_are_unchanged(self):
        sources, metas = inputs()
        single = policy("single_source_observation")
        actual = {instrument: {"recipe": fx.recipe(instrument, metas, single),
                              "rows": fx.construct_prices(instrument, sources, alignment_policy=single, source_metadata=metas)}
                  for instrument in fx.DIRECT + fx.INVERSE}
        # Baseline recorded before adding retrospective cross timing checks.
        self.assertEqual(digest(actual), "e9d738702229b90a0e260c4e9327ee317d41628d2162ed688b120e30ecc79f80")
        all_rows = fx.construct_universe(sources, source_metadata=metas, alignment_policy=policy(), single_source_policy=single)
        for instrument in fx.DIRECT + fx.INVERSE:
            self.assertEqual(actual[instrument]["rows"], all_rows[instrument])


if __name__ == "__main__":
    unittest.main()
