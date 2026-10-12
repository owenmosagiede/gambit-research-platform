"""Isolated canonical source fixtures used by the actual Target engine/service."""
from copy import deepcopy

from data.targets.contracts import create_definition, create_policy
from data.transformations.identity import digest, reference


def fixture_ref(identity):
    return {'id':identity, 'version':'1.0.0', 'content_sha256':digest({'fixture':identity})}


def source_fixture(*, role='instrument', kind='price', representation='simple',
                   values=None, currency='USD', availability_basis='first_published'):
    entity = 'FIXTURE_BENCHMARK' if role == 'benchmark' else 'FIXTURE_INSTRUMENT'
    dates = ['2024-01-02','2024-01-03','2024-01-04','2024-01-05','2024-01-08','2024-01-09']
    values = values or ['100','110','121','133.1','146.41','161.051']
    view = fixture_ref('SVIEW_' + entity)
    history = fixture_ref('POLICY_FIXTURE_HISTORY')
    selection = {'entity_id':entity,'measure':'close' if kind != 'period_returns' else 'period_return','dimensions':[]}
    economics = {'kind':'economic_source','source_view':view,'selection':selection,
                 'instrument_id':entity,'investment_series_id':entity+'_INVESTMENT',
                 'instrument_class':'equity','input_kind':kind,
                 'unit':'usd_per_share' if kind == 'price' else 'index_points' if kind == 'wealth_index' else 'fraction' if representation == 'simple' else 'natural_log',
                 'value_semantics':'price' if kind == 'price' else 'numeric_level' if kind == 'wealth_index' else 'fractional_change' if representation == 'simple' else 'log_change',
                 'temporal_precision':'date',
                 'cadence':{'frequency':'daily','ordering':'reference_time','gap_policy':'explicit_missing','calendar':'gregorian'},
                 'history_policy':history,'currency':currency,
                 'base_currency':None,'quote_currency':None,'quotation_direction':'not_applicable',
                 'observation_convention':'certified_close','calendar_id':'FIXTURE_US_SESSIONS','calendar_version':'1.0.0','timezone':'America/New_York',
                 'economic_coverage':'gross_price' if kind == 'price' else 'gross_total_return',
                 'adjustment_convention':'unadjusted_price' if kind == 'price' else 'certified_total_return' if kind == 'wealth_index' else 'certified_period_returns',
                 'includes_income':kind != 'price','includes_corporate_actions':kind != 'price',
                 'period_representation':representation if kind == 'period_returns' else None,
                 'availability_basis':availability_basis,'vintage_capability':'complete_history',
                 'availability_evidence_complete':availability_basis != 'unknown',
                 'zero_terminal_allowed':True,'evidence':[fixture_ref('EVIDENCE_FIXTURE_ECONOMIC')]}
    policy = create_policy(economics,'Fixture canonical economic certification')
    rows, periods = [], {}
    for index, (date,value) in enumerate(zip(dates,values)):
        row = {'reference_time':date,'available_at':date,'vintage_id':f'VINTAGE_{index}',
               'value':value,'status':'valid','reason_code':None,
               'lineage':fixture_ref(f'LINEAGE_{entity}_{index}'), **selection}
        if kind == 'period_returns':
            if index == 0: continue
            periods[row['lineage']['id']] = {'interval_start':dates[index-1],'interval_end':date}
        rows.append(row)
    series = {'contract_version':'1.0.0','source_view':view,'source_snapshots':[fixture_ref('SNAPSHOT_'+entity)],
              'selection':selection,'unit':economics['unit'],'value_semantics':economics['value_semantics'],
              'cadence':economics['cadence'],'history_policy':history,'capabilities':['revision_history'],
              'temporal_precision':'date','provenance':{'provider':'ISOLATED_FIXTURE','instrument':entity},'observations':rows}
    return {'series':series,'economics':policy,'periods':periods}


def refresh_source_policy(source, **updates):
    body = deepcopy(source['economics']['body'])
    body.update(updates)
    source['economics'] = create_policy(body)
    return source


def fixture(*, basis='price', representation='simple', kind=None, values=None,
            benchmark_values=None, selection='first_defensible', availability_basis='first_published'):
    kind = kind or ('price' if basis in {'price','benchmark_excess'} else 'wealth_index')
    sources = {'instrument':source_fixture(kind=kind,representation=representation,values=values,availability_basis=availability_basis)}
    instrument_basis = 'price' if kind == 'price' else 'total_return'
    if basis == 'benchmark_excess':
        sources['benchmark'] = source_fixture(role='benchmark',kind=kind,representation=representation,values=benchmark_values,availability_basis=availability_basis)
    schedule_policy = create_policy({'kind':'target_schedule','calendar_id':'FIXTURE_US_SESSIONS','calendar_version':'1.0.0',
                                    'timezone':'America/New_York','observation_convention':'certified_close',
                                    'temporal_precision':'date','anchor_convention':'declared_marks'})
    outcome_policy = create_policy({'kind':'outcome_selection','selection':selection,
                                   'availability_basis':availability_basis,'finalization_wait':{'amount':0,'unit':'calendar_days'},
                                   'label_precision_policy':'conservative_date_boundary','unknown_availability':'allow_uncertified'})
    validity_policy = create_policy({'kind':'mathematical_validity','missing':'retain_null','stale':'reject',
                                    'nonpositive_start':'retain_null','nonfinite':'reject_source',
                                    'negative_end':'retain_null','zero_terminal':'source_contract','period_coverage':'exact_complete'})
    calculation = create_policy({'kind':'return_calculation','calculation_version':'1.0.0','arithmetic':'decimal_50_then_binary64_guard'})
    dates = ['2024-01-02','2024-01-03','2024-01-04','2024-01-05','2024-01-08','2024-01-09']
    schedule = {'policy_id':schedule_policy['id'],'version':'1.0.0','temporal_precision':'date',
                'calendar_id':'FIXTURE_US_SESSIONS','calendar_version':'1.0.0','timezone':'America/New_York',
                'observation_convention':'certified_close','coverage_start':dates[0],'coverage_end':dates[-1],
                'marks':[{'mark_id':f'MARK_{i}','time':date,'session_id':f'SESSION_{i}'} for i,date in enumerate(dates)],
                'evidence':fixture_ref('EVIDENCE_FIXTURE_SCHEDULE')}
    body = {'sources':[{'role':role,'source_view':source['series']['source_view'],
                        'selection':source['series']['selection'],'economic_policy':reference(source['economics'])}
                       for role,source in sources.items()],
            'construction':{'basis':basis,'representation':representation,
                            'comparison':'none' if basis != 'benchmark_excess' else 'arithmetic_difference' if representation == 'simple' else 'log_difference',
                            'instrument_basis':instrument_basis,'benchmark_basis':instrument_basis if basis == 'benchmark_excess' else None},
            'unit':'dimensionless_fraction' if representation == 'simple' else 'natural_log_return',
            'currency':'USD','economic_coverage':sources['instrument']['economics']['body']['economic_coverage'],
            'schedule_policy':reference(schedule_policy),'anchor_policy':{'mode':'market_schedule','anchor_set_id':None},
            'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
            'horizon':{'amount':2,'unit':'trading_sessions','counting':'exclusive_entry'},
            'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}},
            'outcome_policy':reference(outcome_policy),'validity_policy':reference(validity_policy),
            'calculation':reference(calculation),'dependencies':[]}
    return {'definition':create_definition(body,'Fixture investment return'), 'sources':sources, 'schedule':schedule,
            'anchors':{'mode':'market_schedule','mark_ids':['MARK_0']},'knowledge_cutoff':'2024-01-10',
            'outcome_policy':outcome_policy,'validity_policy':validity_policy,
            'schedule_policy':schedule_policy,'calculation':calculation}


def rebind(value):
    """Recompute fixture semantic references after an intentional test mutation."""
    body = deepcopy(value['definition']['body'])
    for binding in body['sources']:
        source = value['sources'][binding['role']]
        binding['economic_policy'] = reference(source['economics'])
        binding['source_view'] = source['series']['source_view']
        binding['selection'] = source['series']['selection']
    for field in ('outcome_policy','validity_policy','schedule_policy','calculation'):
        body[field] = reference(value[field])
    value['schedule']['policy_id'] = value['schedule_policy']['id']
    value['definition'] = create_definition(body,value['definition']['display_name'])
    return value
