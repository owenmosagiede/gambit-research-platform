"""Synthetic funding sources and independently calculated financed FX outcomes."""
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal,localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import csv,gzip,io,json
from zipfile import ZipFile,ZIP_DEFLATED

from data import fx_funding as funding
from data.targets import fx_total
from data.transformations.identity import digest,reference

def captures(start='2024-01-01',end='2024-05-06'):
    start=date.fromisoformat(start);end=date.fromisoformat(end)
    days=[start+timedelta(days=i) for i in range((end-start).days+1)]
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['FREQ:Frequency','REF_AREA:Reference area','TIME_PERIOD:Time period or range',
        'OBS_VALUE:Observation Value','UNIT_MEASURE:Unit of measure','UNIT_MULT:Unit Multiplier','OBS_STATUS:Observation Status'])
    for currency,area in funding.CURRENCIES.items():
        for day in days:
            writer.writerow(['D: Daily',area+': Test',day.isoformat(),4 if currency=='EUR' else 5,
                             '368: Per cent per year','0: Units','A: Normal value'])
    zipped=io.BytesIO()
    with ZipFile(zipped,'w',ZIP_DEFLATED) as archive:archive.writestr('WS_CBPOL_csv_flat.csv',stream.getvalue())
    sora=io.StringIO();writer=csv.writer(sora,lineterminator='\n')
    writer.writerow(['MAS: Financial Database - Domestic Interest Rates']);writer.writerow([])
    writer.writerow(['SORA Value Date','','','SORA Publication Date','SORA'])
    year=month=None
    for day in days:
        if day.weekday()>=5:continue
        published=day+timedelta(days=1)
        while published.weekday()>=5:published+=timedelta(days=1)
        writer.writerow([day.year if day.year!=year else '',day.strftime('%b') if day.month!=month else '',
                         day.day,published.strftime('%d %b %Y'),3])
        year,month=day.year,day.month
        if day.month==12 and day.day>=29:writer.writerow([])
    writer.writerow([]);writer.writerow([' After a review of the market demand and usage of MAS-administered financial benchmarks'])
    return zipped.getvalue(),sora.getvalue().encode()

def rate(day,value='0',status='A: Normal value'):
    return {'date':day,'rate_pct':value,'source_row_sha256':digest([day,value]),'observation_status':status}

class FundingTests(TestCase):
    def test_mas_blank_year_boundaries_and_publication_are_not_truncated(self):
        _,raw=captures('2023-12-27','2024-01-05');rows=funding.parse_sora(raw)
        self.assertEqual(rows[-1]['date'],'2024-01-05')
        self.assertEqual(rows[-1]['publication_date'],'2024-01-08')
        self.assertEqual(len(rows),8)
        with self.assertRaises(ValueError):funding.parse_sora(b'<!DOCTYPE html>maintenance')

    def test_primary_capture_roundtrip_and_forged_normalization_rejected(self):
        from data.feature_store import FeatureStore
        with TemporaryDirectory() as root:
            binding=funding.install(root,*captures());snapshot,rows=funding.load(root,binding)
            self.assertEqual(len(rows),18);self.assertNotIn('CNH',rows)
            store=FeatureStore(root);values=[]
            for currency,entries in rows.items():values.extend(entries)
            values[0]['rate_pct']='99'
            body=deepcopy(snapshot['body'])
            body['observations']=store.io.blob(gzip.compress(b'\n'.join(json.dumps(r).encode() for r in values)),
                'bin','forged_normalization',len(values))
            forged=funding.record('snapshot_manifest',body,snapshot['display_name']);store.install_record(forged)
            with self.assertRaisesRegex(ValueError,'primary captures'):funding.load(root,reference(forged))

    def test_actual_calendar_days_weekends_and_negative_interest(self):
        days=[rate('2024-01-05','-1'),rate('2024-01-06','-1'),rate('2024-01-07','-1')]
        factor,_=fx_total.Rates({'EUR':days}).factor('EUR','2024-01-05','2024-01-08')
        with localcontext() as ctx:
            ctx.prec=50;expected=(1-Decimal('0.01')/365)**3
        self.assertEqual(factor,expected)
        a=[rate('2024-01-05','5'),rate('2024-01-06',None,'M: Missing value; data cannot exist'),
           rate('2024-01-07',None,'M: Missing value; data cannot exist')]
        factor,_=fx_total.Rates({'EUR':a}).factor('EUR','2024-01-05','2024-01-08')
        self.assertGreater(factor,Decimal(1))
        a[1]['observation_status']='L: Missing value; not collected'
        self.assertEqual(fx_total.Rates({'EUR':a}).factor('EUR','2024-01-05','2024-01-08'),(None,None))

    def test_sora_fixing_spans_weekend_but_missing_or_long_gap_stays_unavailable(self):
        rows={'SGD':[rate('2024-01-05','3'),rate('2024-01-08','3')]}
        factor,_=fx_total.Rates(rows).factor('SGD','2024-01-05','2024-01-08')
        self.assertGreater(factor,1)
        self.assertEqual(fx_total.Rates(rows).factor('SGD','2024-01-04','2024-01-05'),(None,None))
        rows['SGD'][1]['date']='2024-01-16'
        self.assertEqual(fx_total.Rates(rows).factor('SGD','2024-01-05','2024-01-08'),(None,None))

    def test_bis_omitted_weekend_rows_accrue_but_an_ordinary_missing_weekday_blocks(self):
        rows={'GBP':[rate('2024-01-05','5'),rate('2024-01-08',None,'M: Missing value; data cannot exist'),
                     rate('2024-01-09','5')]}
        factor,_=fx_total.Rates(rows).factor('GBP','2024-01-05','2024-01-09')
        with localcontext() as ctx:
            ctx.prec=50;expected=(1+Decimal('.05')/365)**4
        self.assertLess(abs(factor-expected),Decimal('1e-45'))
        rows['GBP'].pop(1)
        self.assertEqual(fx_total.Rates(rows).factor('GBP','2024-01-05','2024-01-09'),(None,None))

    def test_financed_notional_pnl_formula_and_zero_rate_identity(self):
        source={'id':'TARGET_'+digest('spot'),'version':'1.0.0','body':{
            'instrument_id':'EURUSD','horizon':{'amount':1,'unit':'scheduled_bars'}}}
        definition=fx_total._definition(source,reference(fx_total.policy()))
        spot={'id':'spotrow','prediction_anchor':'2024-01-05','entry_time':'2024-01-05',
            'exit_time':'2024-01-08','status':'valid','reason_code':None,'value':'0.01','operands':[]}
        rows={c:[rate('2024-01-0'+str(n),'0') for n in (5,6,7)] for c in ('EUR','USD')}
        binding={'id':'SNAPSHOT_'+digest('rates'),'version':'1.0.0','content_sha256':digest('ratesref')}
        self.assertEqual(fx_total.construct(definition,[spot],rows,binding)[0]['value'],'0.01')
        for r in rows['EUR']:r['rate_pct']='4'
        for r in rows['USD']:r['rate_pct']='5'
        actual=fx_total.construct(definition,[spot],rows,binding)[0]
        with localcontext() as ctx:
            ctx.prec=50;expected=Decimal('1.01')*(1+Decimal('.04')/365)**3-(1+Decimal('.05')/365)**3
        self.assertAlmostEqual(float(actual['value']),float(expected),places=15)
        rows['EUR'][1]['rate_pct']=None
        missing=fx_total.construct(definition,[spot],rows,binding)[0]
        self.assertIsNone(missing['value']);self.assertEqual(missing['reason_code'],'FUNDING_NOT_AVAILABLE')

    def test_cnh_is_excluded_instead_of_using_onshore_cny(self):
        source={'id':'TARGET_'+digest('spot'),'version':'1.0.0','body':{
            'instrument_id':'USDCNH','horizon':{'amount':1,'unit':'scheduled_bars'}}}
        with self.assertRaisesRegex(ValueError,'CNH'):fx_total._definition(source,reference(fx_total.policy()))
