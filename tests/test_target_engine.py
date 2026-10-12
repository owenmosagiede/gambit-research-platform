"""Independent numerical, source-semantic, identity and leakage acceptance tests."""
from copy import deepcopy
from decimal import Decimal
import math
import unittest

from data.targets.contracts import (create_definition, create_policy, validate_definition,
    validate_observation, validate_policy, SourceIneligible, DefinitionError)
from data.targets.engine import construct, historical_rows, preflight
from data.transformations.contracts import ContractError
from data.transformations.identity import reference
from target_fixtures import fixture, fixture_ref, rebind, refresh_source_policy


def result(case):
    return construct(**case)['observations'][0]


def change_definition(case, **changes):
    body = deepcopy(case['definition']['body']); body.update(changes)
    case['definition'] = create_definition(body)
    return case


class TargetNumericalTests(unittest.TestCase):
    def test_price_simple_independent_fraction(self):
        row = result(fixture())
        self.assertEqual(Decimal(row['value']), Decimal(21) / Decimal(100))
        self.assertEqual(row['unit'], 'dimensionless_fraction')

    def test_price_log_independent_math_log(self):
        row = result(fixture(representation='log'))
        self.assertAlmostEqual(float(row['value']), math.log(121 / 100), places=14)
        self.assertEqual(row['unit'], 'natural_log_return')

    def test_total_wealth_simple_includes_income_once(self):
        row = result(fixture(basis='total_return', values=['100','111','123.21','130','140','150']))
        self.assertEqual(Decimal(row['value']), Decimal('0.2321'))

    def test_total_wealth_log(self):
        row = result(fixture(basis='total_return',representation='log'))
        self.assertAlmostEqual(float(row['value']), math.log(1.21), places=14)

    def test_total_period_simple_compounds_not_sums(self):
        row = result(fixture(basis='total_return',kind='period_returns',values=['0','0.1','0.2','0','0','0']))
        self.assertEqual(Decimal(row['value']), Decimal('0.32'))
        self.assertNotEqual(Decimal(row['value']), Decimal('0.1') + Decimal('0.2'))
        self.assertEqual(len(row['selected_sources'][0]['operands']), 2)

    def test_total_period_log_sums(self):
        row = result(fixture(basis='total_return',kind='period_returns',representation='log', values=['0','0.09','0.18','0','0','0']))
        self.assertEqual(Decimal(row['value']), Decimal('0.27'))

    def test_arithmetic_excess_distinct_from_log_excess(self):
        simple = fixture(basis='benchmark_excess',benchmark_values=['100','105','110','120','130','140'])
        log = fixture(basis='benchmark_excess',representation='log',benchmark_values=['100','105','110','120','130','140'])
        self.assertEqual(Decimal(result(simple)['value']), Decimal('0.11'))
        self.assertAlmostEqual(float(result(log)['value']), math.log(1.21) - math.log(1.1), places=14)
        self.assertNotAlmostEqual(float(result(log)['value']), math.log1p(0.11), places=8)

    def test_arithmetic_excess_can_be_less_than_minus_one(self):
        case = fixture(basis='benchmark_excess',values=['100','100','0','1','1','1'],benchmark_values=['100','100','300','300','300','300'])
        self.assertEqual(Decimal(result(case)['value']), Decimal(-3))

    def test_total_return_excess_wealth_and_period(self):
        for kind, values, benchmark_values, expected in [
                ('wealth_index',['100','110','121','130','140','150'],['100','105','110','120','130','140'],'0.11'),
                ('period_returns',['0','0.1','0.1','0','0','0'],['0','0.05','0.05','0','0','0'],'0.1075')]:
            case = fixture(basis='benchmark_excess',kind=kind,values=values,benchmark_values=benchmark_values)
            self.assertEqual(Decimal(result(case)['value']), Decimal(expected))

    def test_zero_terminal_simple_and_log(self):
        for basis in ['price','total_return']:
            case = fixture(basis=basis,values=['100','50','0','0','0','0'])
            self.assertEqual(result(case)['value'], '-1')
            case = fixture(basis=basis,representation='log',values=['100','50','0','0','0','0'])
            self.assertEqual(result(case)['reason_code'], 'NONPOSITIVE_LOG_INPUT')

    def test_zero_terminal_requires_source_permission(self):
        case = fixture(values=['100','50','0','1','1','1'])
        refresh_source_policy(case['sources']['instrument'],zero_terminal_allowed=False); rebind(case)
        self.assertEqual(result(case)['reason_code'],'ZERO_TERMINAL_NOT_CERTIFIED')

    def test_nonpositive_start_negative_end(self):
        for values, reason in [(['0','1','2'],'NONPOSITIVE_START'), (['-1','1','2'],'NONPOSITIVE_START'),(['1','1','-2'],'NEGATIVE_END')]:
            self.assertEqual(result(fixture(values=values))['reason_code'],reason)

    def test_nonfinite_input_is_contract_rejection(self):
        for value in ['NaN','Infinity','-Infinity']:
            with self.subTest(value=value), self.assertRaises(ContractError):
                result(fixture(values=['100','110',value]))

    def test_overflow_is_retained_invalid_not_infinity(self):
        huge = '1' + '0' * 400
        row = result(fixture(values=['1','1',huge]))
        self.assertIsNone(row['value']); self.assertEqual(row['reason_code'],'NONFINITE_OUTPUT')

    def test_period_loss_and_invalid_component(self):
        self.assertEqual(result(fixture(basis='total_return',kind='period_returns',values=['0','-1','0.2']))['value'],'-1')
        self.assertEqual(result(fixture(basis='total_return',kind='period_returns',values=['0','-1.1','0.2']))['reason_code'],'INVALID_PERIOD_RETURN')

    def test_log_excess_from_period_components(self):
        case=fixture(basis='benchmark_excess',kind='period_returns',representation='log',
                     values=['0','0.1','0.2'],benchmark_values=['0','0.02','0.03'])
        self.assertEqual(Decimal(result(case)['value']),Decimal('0.25'))

    def test_period_zero_loss_requires_source_certification(self):
        case=fixture(basis='total_return',kind='period_returns',values=['0','-1','0.1'])
        refresh_source_policy(case['sources']['instrument'],zero_terminal_allowed=False); rebind(case)
        self.assertEqual(result(case)['reason_code'],'ZERO_TERMINAL_NOT_CERTIFIED')

    def test_source_missing_and_invalid_are_retained(self):
        for status,reason in [('missing','SOURCE_MISSING'),('invalid','SOURCE_INVALID')]:
            case=fixture(); case['sources']['instrument']['series']['observations'][2].update(value=None,status=status,reason_code=reason)
            row=result(case); self.assertIsNone(row['value']); self.assertEqual(row['reason_code'],reason)

    def test_timestamp_engine_horizon_entry_representation_cross_product(self):
        # Independent fixed civil/UTC marks: both entries are two days from their
        # intended endpoints; session/bar counting must match those exact marks.
        for basis in ['price','total_return']:
            for representation in ['simple','log']:
                for unit in ['trading_sessions','scheduled_bars','calendar_days','elapsed_seconds']:
                    for rule in ['anchor_mark','next_scheduled']:
                        with self.subTest(basis=basis,representation=representation,unit=unit,rule=rule):
                            case=fixture(basis=basis,representation=representation)
                            source=case['sources']['instrument']; series=source['series']
                            series['temporal_precision']='utc_timestamp'
                            for row in series['observations']:
                                row['reference_time']+='T21:00:00.000000Z'; row['available_at']+='T21:00:00.000000Z'
                            refresh_source_policy(source,temporal_precision='utc_timestamp')
                            for field in ('coverage_start','coverage_end'):
                                case['schedule'][field]+='T21:00:00.000000Z'
                            case['schedule']['temporal_precision']='utc_timestamp'
                            for mark in case['schedule']['marks']:
                                mark['local_time']=mark['time']+'T16:00:00.000000-05:00'; mark['time']+='T21:00:00.000000Z'
                            schedule_policy=deepcopy(case['schedule_policy']['body']); schedule_policy['temporal_precision']='utc_timestamp'
                            case['schedule_policy']=create_policy(schedule_policy)
                            outcome=deepcopy(case['outcome_policy']['body']); outcome['label_precision_policy']='exact_timestamp'
                            case['outcome_policy']=create_policy(outcome)
                            case['knowledge_cutoff']+='T21:00:00.000000Z'; rebind(case)
                            body=deepcopy(case['definition']['body']); body['entry']['rule']=rule
                            body['horizon'].update(unit=unit,amount=172800 if unit=='elapsed_seconds' else 2)
                            case['definition']=create_definition(body)
                            row=result(case)
                            expected_ratio=121/100 if rule=='anchor_mark' else 133.1/110
                            expected=expected_ratio-1 if representation=='simple' else math.log(expected_ratio)
                            self.assertAlmostEqual(float(row['value']),expected,places=14)
                            self.assertEqual(row['exit_time'],'2024-01-04T21:00:00.000000Z' if rule=='anchor_mark' else '2024-01-05T21:00:00.000000Z')
                            self.assertEqual(historical_rows([row],row['label_available_at']),[row])

    def test_period_gap_overlap_and_boundary(self):
        for mutation, reason in [('gap','PERIOD_GAP'),('overlap','PERIOD_OVERLAP'),('boundary','PERIOD_BOUNDARY_MISMATCH')]:
            case = fixture(basis='total_return',kind='period_returns',values=['0','0.1','0.2','0','0','0'])
            source = case['sources']['instrument']; rows = source['series']['observations']
            if mutation == 'gap':
                removed = rows.pop(0); del source['periods'][removed['lineage']['id']]
            elif mutation == 'overlap':
                source['periods'][rows[1]['lineage']['id']]['interval_start'] = '2024-01-02'
            else:
                source['periods'][rows[0]['lineage']['id']]['interval_start'] = '2024-01-01'
            self.assertEqual(result(case)['reason_code'],reason)

    def test_endpoint_ratio_needs_no_interior_price(self):
        case = fixture(); case['sources']['instrument']['series']['observations'].pop(1)
        self.assertEqual(result(case)['value'],'0.21')

    def test_duplicate_period_intervals_rejected_before_arithmetic(self):
        case = fixture(basis='total_return',kind='period_returns',values=['0','0.1','0.2'])
        source = case['sources']['instrument']
        duplicate = deepcopy(source['series']['observations'][0]); duplicate['lineage'] = fixture_ref('LINEAGE_DUPLICATE')
        source['series']['observations'].append(duplicate)
        source['periods'][duplicate['lineage']['id']] = deepcopy(next(iter(source['periods'].values())))
        with self.assertRaises(ContractError): result(case)


class TargetEconomicEligibilityTests(unittest.TestCase):
    def test_macro_ces_yields_and_futures_are_not_price_return_sources(self):
        for kind in ['macro','yield','spread','rate','futures']:
            case = fixture(); refresh_source_policy(case['sources']['instrument'],instrument_class=kind); rebind(case)
            with self.subTest(kind=kind), self.assertRaises(SourceIneligible): result(case)

    def test_price_cannot_claim_total_return(self):
        case = fixture(); body = deepcopy(case['definition']['body'])
        body['construction'].update(basis='total_return',instrument_basis='total_return')
        case['definition'] = create_definition(body)
        with self.assertRaises(SourceIneligible): result(case)

    def test_ambiguous_adjusted_price_is_rejected(self):
        for basis in ['price','total_return']:
            case = fixture(basis=basis); refresh_source_policy(case['sources']['instrument'],adjustment_convention='ambiguous'); rebind(case)
            with self.assertRaises(SourceIneligible): result(case)

    def test_total_return_missing_income_or_action_evidence_is_rejected(self):
        for field in ['includes_income','includes_corporate_actions']:
            case = fixture(basis='total_return'); refresh_source_policy(case['sources']['instrument'],**{field:False}); rebind(case)
            with self.assertRaises(SourceIneligible): result(case)

    def test_period_representation_cannot_be_silently_converted(self):
        case = fixture(basis='total_return',kind='period_returns',values=['0','0.1','0.2'])
        body = deepcopy(case['definition']['body']); body['construction']['representation']='log'; body['unit']='natural_log_return'
        case['definition'] = create_definition(body)
        with self.assertRaises(SourceIneligible): result(case)

    def test_period_percent_units_are_not_silently_treated_as_fractions(self):
        case=fixture(basis='total_return',kind='period_returns',values=['0','10','20'])
        source=case['sources']['instrument']; source['series']['unit']='percent'
        refresh_source_policy(source,unit='percent'); rebind(case)
        with self.assertRaises(SourceIneligible): result(case)

    def test_benchmark_currency_and_coverage_must_match(self):
        for update in [{'currency':'EUR'},{'economic_coverage':'net_total_return'}]:
            case = fixture(basis='benchmark_excess'); refresh_source_policy(case['sources']['benchmark'],**update); rebind(case)
            with self.assertRaises(SourceIneligible): result(case)

    def test_calendar_timezone_certification_is_not_inferred_from_dates(self):
        for update in [{'timezone':'UTC'},{'calendar_id':'DIFFERENT_MARKET'},{'calendar_version':'2.0.0'}]:
            case=fixture(); refresh_source_policy(case['sources']['instrument'],**update); rebind(case)
            with self.assertRaises(SourceIneligible): result(case)

    def test_fx_quote_inverse_not_negative_simple_return(self):
        direct = fixture(values=['1','1.1','1.25'])
        inverse = fixture(values=['1','0.9','0.8'])
        for case, direction, currency in [(direct,'quote_per_base','USD'),(inverse,'base_per_quote','EUR')]:
            refresh_source_policy(case['sources']['instrument'],instrument_class='spot_fx',base_currency='EUR',quote_currency='USD',quotation_direction=direction,currency=currency)
            rebind(case); change_definition(case,currency=currency)
        self.assertEqual(result(direct)['value'],'0.25')
        self.assertEqual(result(inverse)['value'],'-0.2')
        self.assertNotEqual(Decimal(result(direct)['value']), -Decimal(result(inverse)['value']))

    def test_fx_quote_return_currency_mismatch_rejected(self):
        case = fixture(); refresh_source_policy(case['sources']['instrument'],instrument_class='spot_fx',base_currency='EUR',quote_currency='USD',quotation_direction='base_per_quote'); rebind(case)
        with self.assertRaises(SourceIneligible): result(case)

    def test_provider_name_does_not_select_formula(self):
        case = fixture(); original = result(case)['value']
        case['sources']['instrument']['series']['provenance']['provider']='ANOTHER_PROVIDER'
        self.assertEqual(result(case)['value'],original)

    def test_specialized_instrument_enters_only_certified_returns(self):
        case = fixture(); refresh_source_policy(case['sources']['instrument'],instrument_class='certified_investment_series'); rebind(case)
        with self.assertRaises(SourceIneligible): result(case)
        case = fixture(basis='total_return'); refresh_source_policy(case['sources']['instrument'],instrument_class='certified_investment_series'); rebind(case)
        self.assertEqual(result(case)['value'],'0.21')


class TargetVintageAndLeakageTests(unittest.TestCase):
    def corrected(self, selection='pinned_later'):
        case = fixture(selection=selection)
        revised = deepcopy(case['sources']['instrument']['series']['observations'][2])
        revised.update(available_at='2024-01-08',value='125',vintage_id='REVISION_1',lineage=fixture_ref('LINEAGE_CORRECTION'))
        case['sources']['instrument']['series']['observations'].append(revised)
        return case

    def test_future_endpoint_differs_from_missing_historical_endpoint(self):
        case = fixture(); case['knowledge_cutoff']='2024-01-03'
        self.assertEqual(result(case)['reason_code'],'FUTURE_ENDPOINT')
        case['knowledge_cutoff']='2024-01-10'; case['sources']['instrument']['series']['observations'].pop(2)
        self.assertEqual(result(case)['reason_code'],'MISSING_ENDPOINT')

    def test_missing_scheduled_session_does_not_compress_horizon(self):
        case = fixture(); case['sources']['instrument']['series']['observations'].pop(2)
        row=result(case); self.assertEqual(row['exit_time'],'2024-01-04')
        self.assertIsNone(row['value']); self.assertEqual(row['status'],'missing')

    def test_future_target_outcome_not_required_known_at_prediction_anchor(self):
        row=result(fixture())
        self.assertEqual(row['status'],'valid')
        self.assertLess(row['prediction_anchor'],row['source_availability'])

    def test_first_defensible_retains_original_after_correction(self):
        row=result(self.corrected('first_defensible'))
        self.assertEqual(row['value'],'0.21'); self.assertEqual(row['label_available_at'],'2024-01-04')

    def test_pinned_later_selects_correction_only_after_evidence(self):
        case=self.corrected(); case['knowledge_cutoff']='2024-01-05'
        earlier=result(case)
        case['knowledge_cutoff']='2024-01-09'; corrected=result(case)
        self.assertEqual(earlier['value'],'0.21'); self.assertEqual(corrected['value'],'0.25')
        self.assertEqual(corrected['label_available_at'],'2024-01-08')
        self.assertEqual(historical_rows([corrected],'2024-01-07'),[])
        self.assertEqual(historical_rows([corrected],'2024-01-09'),[corrected])
        self.assertEqual(historical_rows([earlier],'2024-01-06')[0]['value'],'0.21')

    def test_date_only_same_day_availability_cannot_enter_training(self):
        row=result(fixture())
        self.assertEqual(historical_rows([row],'2024-01-04'),[])
        self.assertEqual(historical_rows([row],'2024-01-05'),[row])
        self.assertEqual(historical_rows([row],'2024-01-04T23:59:59.000000Z',cutoff_precision='utc_timestamp'),[])

    def test_delayed_source_evidence_waits_beyond_economic_end(self):
        case=fixture(); case['sources']['instrument']['series']['observations'][2]['available_at']='2024-01-06'
        row=result(case); self.assertEqual(row['exit_time'],'2024-01-04'); self.assertEqual(row['label_available_at'],'2024-01-06')
        self.assertEqual(historical_rows([row],'2024-01-06'),[])

    def test_finalization_wait_is_label_time_not_execution_time(self):
        case=fixture(); policy=deepcopy(case['outcome_policy']['body']); policy['finalization_wait']['amount']=3
        case['outcome_policy']=create_policy(policy); rebind(case)
        case['knowledge_cutoff']='2024-01-06'; row=result(case)
        self.assertEqual(row['reason_code'],'FINALIZATION_PENDING'); self.assertEqual(row['label_available_at'],'2024-01-07')
        case['knowledge_cutoff']='2024-01-10'; row=result(case)
        self.assertEqual(row['value'],'0.21'); self.assertEqual(row['label_available_at'],'2024-01-07')

    def test_unknown_availability_numerical_only(self):
        case=fixture(selection='pinned_later',availability_basis='unknown'); row=result(case)
        self.assertEqual(row['value'],'0.21'); self.assertIsNone(row['label_available_at'])
        self.assertFalse(row['historical_eligibility_certified']); self.assertEqual(historical_rows([row],'2024-02-01'),[])

    def test_unknown_availability_rejection_is_explicit_policy(self):
        case=fixture(selection='pinned_later',availability_basis='unknown')
        outcome=deepcopy(case['outcome_policy']['body']); outcome['unknown_availability']='reject'
        case['outcome_policy']=create_policy(outcome); rebind(case)
        with self.assertRaises(SourceIneligible): result(case)

    def test_first_defensible_needs_complete_vintage_and_availability_evidence(self):
        for changes in [{'vintage_capability':'pinned_state'},{'availability_evidence_complete':False}]:
            case=fixture(); refresh_source_policy(case['sources']['instrument'],**changes); rebind(case)
            with self.assertRaises(SourceIneligible): result(case)

    def test_first_published_archived_ingested_are_distinct(self):
        identities=[]
        for basis in ['first_published','first_archived','first_ingested']:
            case=fixture(availability_basis=basis); row=result(case)
            self.assertEqual(row['availability_basis'],basis); identities.append(case['definition']['id'])
        self.assertEqual(len(set(identities)),3)
        case=fixture(); refresh_source_policy(case['sources']['instrument'],availability_basis='first_archived'); rebind(case)
        with self.assertRaises(SourceIneligible): result(case)

    def test_unrelated_future_values_cannot_change_completed_label(self):
        case=fixture(); before=result(case)
        case['sources']['instrument']['series']['observations'][-1]['value']='999999'
        after=result(case)
        self.assertEqual(before,after)

    def test_missing_later_available_endpoint_remains_pending(self):
        case=fixture(); case['sources']['instrument']['series']['observations'][2]['available_at']='2024-01-09'
        case['knowledge_cutoff']='2024-01-08'; row=result(case)
        self.assertEqual(row['status'],'pending'); self.assertEqual(row['reason_code'],'ENDPOINT_NOT_AVAILABLE')

    def test_period_component_with_later_evidence_is_pending_not_missing(self):
        case=fixture(basis='total_return',kind='period_returns',values=['0','0.1','0.2'])
        case['sources']['instrument']['series']['observations'][1]['available_at']='2024-01-09'
        case['knowledge_cutoff']='2024-01-08'
        self.assertEqual(result(case)['reason_code'],'ENDPOINT_NOT_AVAILABLE')
        case['knowledge_cutoff']='2024-01-10'
        self.assertEqual(result(case)['value'],'0.32')


class TargetIdentityAndContractTests(unittest.TestCase):
    def test_display_labels_not_logical_identity(self):
        case=fixture(); definition=create_definition(case['definition']['body'],'Another display label')
        self.assertEqual(definition['id'],case['definition']['id'])
        self.assertEqual(reference(definition),reference(case['definition']))

    def test_scientific_interpretation_changes_identity(self):
        case=fixture(); initial=case['definition']['id']
        for field, value in [('horizon',{'amount':3,'unit':'trading_sessions','counting':'exclusive_entry'}),
                             ('entry',{'rule':'next_scheduled','delay':{'amount':0,'unit':'calendar_days'}})]:
            changed=deepcopy(case); change_definition(changed,**{field:value})
            self.assertNotEqual(changed['definition']['id'],initial)
        self.assertNotEqual(fixture(representation='log')['definition']['id'],initial)

    def test_observation_values_and_runtime_coverage_not_target_identity(self):
        a=fixture(); b=fixture(values=['100','101','102'])
        self.assertEqual(a['definition']['id'],b['definition']['id'])
        b['anchors']['mark_ids']=['MARK_1']
        self.assertEqual(a['definition']['id'],b['definition']['id'])

    def test_research_feature_and_signal_are_not_definition_fields(self):
        for field in ['signal_id','feature_id','expected_direction','research_spec']:
            body=deepcopy(fixture()['definition']['body']); body[field]='UNRELATED'
            with self.assertRaises(ContractError): create_definition(body)

    def test_unresolved_policy_and_tampered_identity_rejected(self):
        case=fixture(); case['definition']['body']['horizon']['amount']='one day'
        with self.assertRaises(ContractError): validate_definition(case['definition'])
        case=fixture(); case['definition']['id']='TARGET_'+'0'*64
        with self.assertRaises(DefinitionError): validate_definition(case['definition'])

    def test_observation_lineage_and_upstream_provenance_preserved(self):
        case=fixture(); row=result(case); source=row['selected_sources'][0]
        self.assertEqual(source['source_view'],case['sources']['instrument']['series']['source_view'])
        self.assertEqual(source['source_snapshots'],case['sources']['instrument']['series']['source_snapshots'])
        self.assertEqual(source['provenance']['provider'],'ISOLATED_FIXTURE')
        self.assertEqual([o['role'] for o in source['operands']],['entry','exit'])
        self.assertEqual(source['operands'][1]['lineage'],case['sources']['instrument']['series']['observations'][2]['lineage'])

    def test_tampered_observation_integrity_is_rejected(self):
        row=result(fixture()); row['value']='0.5'
        with self.assertRaises(ContractError): validate_observation(row)

    def test_preflight_matches_all_registered_policy_bindings(self):
        case=fixture(); expected=preflight(**case)
        self.assertEqual(expected['intervals'][0]['exit_time'],'2024-01-04')
        case['schedule']['observation_convention']='uncertified_mark'
        with self.assertRaises(DefinitionError): preflight(**case)

    def test_explicit_anchor_set_identity_must_match_definition(self):
        case=fixture(); change_definition(case,anchor_policy={'mode':'explicit','anchor_set_id':'ANCHORSET_APPROVED'})
        case['anchors']={'mode':'explicit','anchor_set_id':'ANCHORSET_APPROVED','times':['2024-01-02']}
        self.assertEqual(result(case)['value'],'0.21')
        case['anchors']['anchor_set_id']='ANCHORSET_DIFFERENT'
        with self.assertRaises(DefinitionError): result(case)

    def test_structural_schema_rejects_unknown_envelope_fields(self):
        case=fixture(); case['definition']['created_at']='2024-01-01'
        with self.assertRaisesRegex(ContractError,'structural schema'): validate_definition(case['definition'])

    def test_repeated_execution_is_deterministic(self):
        case=fixture(); self.assertEqual(construct(**case),construct(**deepcopy(case)))


if __name__ == '__main__': unittest.main()
