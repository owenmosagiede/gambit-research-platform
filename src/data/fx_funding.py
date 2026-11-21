"""Immutable benchmark funding inputs for retrospective modelled FX returns.

BIS policy rates are proxies, not executable funding quotes. SORA value dates
are distinct from publication dates. No source is certified point-in-time.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import csv
import io
from zipfile import ZipFile

from data.feature_store import FeatureStore
from data.transformations.identity import digest, reference
from data.transformations.contracts import decimal_text, normalize_reference

SCHEMA = '0.10.0'
CURRENCIES = dict(zip('AUD CAD CHF CZK EUR GBP HKD HUF ILS JPY MXN NOK NZD PLN SEK USD ZAR'.split(),
                      'AU CA CH CZ XM GB HK HU IL JP MX NO NZ PL SE US ZA'.split()))
SUPPORTED = frozenset((*CURRENCIES, 'SGD'))
BIS_URL = 'https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip'
SORA_URL = 'https://eservices.mas.gov.sg/statistics/dir/'
PREFIXES = {'snapshot_manifest':'SNAPSHOT_', 'policy_definition':'POLICY_'}

def record(kind, body, display_name):
    value={'schema_version':SCHEMA,'record_type':kind,'version':'1.0.0','body':body}
    value['id']=PREFIXES[kind]+digest(value)
    value['display_name']=display_name
    return value

def _decimal(value):
    if value in ('', 'na', 'NA', 'NaN', '-', '.', None):return None
    number=Decimal(value)
    if not number.is_finite() or number<=-36500 or number>100000:
        raise ValueError('Invalid annual percentage funding rate')
    return decimal_text(number)

def parse_bis(raw):
    """Stream the official 450+ MB flat member; never expand it onto disk."""
    by_area={v:k for k,v in CURRENCIES.items()}; rows=defaultdict(list); seen=set()
    with ZipFile(io.BytesIO(raw)) as archive:
        files=[i for i in archive.infolist() if i.filename=='WS_CBPOL_csv_flat.csv']
        if len(files)!=1 or files[0].file_size>800_000_000:
            raise ValueError('Unexpected BIS policy-rate archive')
        with archive.open(files[0]) as stream:
            reader=csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig'))
            for index,item in enumerate(reader,2):
                if item['FREQ:Frequency'].split(':')[0]!='D':continue
                currency=by_area.get(item['REF_AREA:Reference area'].split(':')[0])
                if currency is None:continue
                if (item['UNIT_MEASURE:Unit of measure'].split(':')[0]!='368' or
                        item['UNIT_MULT:Unit Multiplier'].split(':')[0]!='0'):
                    raise ValueError('BIS rate must be percent per year, unscaled')
                when=date.fromisoformat(item['TIME_PERIOD:Time period or range']).isoformat()
                if (currency,when) in seen:raise ValueError('Duplicate BIS currency/date')
                seen.add((currency,when))
                rows[currency].append({'date':when,'rate_pct':_decimal(item['OBS_VALUE:Observation Value']),
                    'publication_date':None,'source_row':index,'source':'BIS_CBPOL',
                    'observation_status':item['OBS_STATUS:Observation Status'],
                    'source_row_sha256':digest(item)})
    if set(rows)!=set(CURRENCIES):raise ValueError('BIS archive does not cover all 17 approved currencies')
    return {c:sorted(v,key=lambda r:r['date']) for c,v in rows.items()}

def parse_sora(raw):
    """Parse MAS's selected daily CSV, including its compressed year/month cells."""
    text=raw.decode('utf-8-sig')
    if not text.startswith('MAS: Financial Database - Domestic Interest Rates'):
        raise ValueError('Expected official MAS daily-rate CSV, not HTML or a workbook')
    reader=csv.reader(io.StringIO(text)); active=False; year=month=None; rows=[]; seen=set()
    months={name:i+1 for i,name in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split())}
    for index,item in enumerate(reader,1):
        if item==['SORA Value Date','','','SORA Publication Date','SORA']:
            active=True;continue
        if not active:continue
        if not item:
            continue
        if len(item)==1 and rows and item[0].lstrip().startswith('After a review of the market demand'):
            break
        if len(item)!=5:raise ValueError('Unexpected SORA columns or row boundary')
        if item[0]:year=int(item[0])
        if item[1]:month=months[item[1]]
        when=date(year,month,int(item[2])).isoformat()
        day,name,y=item[3].split(); published=date(int(y),months[name],int(day)).isoformat()
        if when in seen or published<=when:raise ValueError('Duplicate SORA date or invalid publication order')
        seen.add(when)
        rows.append({'date':when,'rate_pct':_decimal(item[4]),'publication_date':published,
                     'source_row':index,'source':'MAS_SORA','observation_status':'published',
                     'source_row_sha256':digest(item)})
    if not rows or rows!=sorted(rows,key=lambda r:r['date']):raise ValueError('SORA history is empty or unordered')
    return rows

def validate_record(value):
    if value.get('record_type')=='target_definition' or value.get('record_type')=='target_materialization_manifest':
        from data.targets.fx_total import validate_record as validate_target
        return validate_target(value)
    if value.get('schema_version')!=SCHEMA or value.get('record_type') not in PREFIXES:
        raise ValueError('Unsupported benchmark funding record')
    if record(value['record_type'],value['body'],value['display_name'])!=value:
        raise ValueError('Benchmark funding identity differs')
    body=value['body']
    if value['record_type']=='policy_definition':
        from data.targets.fx_total import policy
        if value!=policy():raise ValueError('Unsupported benchmark funding model')
    else:
        if set(body)!={'kind','sources','observations','currencies','coverage','row_count','historical_pit_certified'}:
            raise ValueError('Invalid funding snapshot fields')
        if body['kind']!='fx_benchmark_funding_snapshot_v1' or body['currencies']!=sorted(SUPPORTED) or body['historical_pit_certified'] is not False:
            raise ValueError('Unsupported funding scope or certification')
        if set(body['sources'])!={'BIS_CBPOL','MAS_SORA'}:raise ValueError('Missing exact funding source')
        if body['row_count']<=0:raise ValueError('Empty funding snapshot')
    return value

def install(root, bis_raw, sora_raw):
    """Publish the primary captures and one content-addressed normalized snapshot."""
    store=FeatureStore(root); rows=parse_bis(bis_raw);rows['SGD']=parse_sora(sora_raw)
    observations=[dict(row,currency=c) for c,values in sorted(rows.items()) for row in values]
    with store.writer():
        sources={key:{'url':url,'raw':store.io.blob(raw,'bin',key.lower()+'_primary_capture',None),
                      'raw_sha256':sha256(raw).hexdigest()}
                 for key,url,raw in [('BIS_CBPOL',BIS_URL,bis_raw),('MAS_SORA',SORA_URL,sora_raw)]}
        payload=store.io.blob(__import__('gzip').compress(
            b'\n'.join(__import__('json').dumps(r,sort_keys=True,separators=(',',':')).encode() for r in observations)+b'\n',mtime=0),
            'bin','fx_benchmark_funding_observations',len(observations))
        snapshot=record('snapshot_manifest',{'kind':'fx_benchmark_funding_snapshot_v1',
            'sources':sources,'observations':payload,'currencies':sorted(rows),
            'coverage':{c:{'start':v[0]['date'],'end':v[-1]['date']} for c,v in rows.items()},
            'row_count':len(observations),'historical_pit_certified':False},'BIS policy rates and MAS SORA funding inputs')
        store.install_record(snapshot)
    return reference(snapshot)

def load(root,binding):
    from data.verified_inputs import memo
    return memo(root,'fx_benchmark_funding',binding,lambda:_load(root,binding))

def _load(root,binding):
    normalize_reference(binding);store=FeatureStore(root);snapshot=store.resolve(binding)
    validate_record(snapshot);store.verify_closure([snapshot])
    import gzip,json
    rows=[json.loads(line) for line in gzip.decompress(store.payload(snapshot['body']['observations'])).splitlines()]
    if len(rows)!=snapshot['body']['row_count']:raise ValueError('Funding observation count differs')
    result=defaultdict(list);seen=set()
    for row in rows:
        if set(row)!={'currency','date','rate_pct','publication_date','source_row','source','observation_status','source_row_sha256'}:
            raise ValueError('Invalid funding observation fields')
        c=row['currency'];when=date.fromisoformat(row['date']).isoformat()
        if c not in SUPPORTED or (c,when) in seen:raise ValueError('Unsupported or duplicate funding currency/date')
        seen.add((c,when));_decimal(row['rate_pct']);result[c].append(row)
    if sorted(result)!=snapshot['body']['currencies']:raise ValueError('Funding currency population differs')
    for c,values in result.items():
        if values!=sorted(values,key=lambda r:r['date']) or snapshot['body']['coverage'][c]!={'start':values[0]['date'],'end':values[-1]['date']}:
            raise ValueError('Funding ordering or coverage differs')
    # A valid payload hash is not proof that its normalized values reproduce
    # the declared primary captures. Reparse once per verified execution scope.
    primary=snapshot['body']['sources']
    for source in primary.values():
        if sha256(store.payload(source['raw'])).hexdigest()!=source['raw_sha256']:
            raise ValueError('Funding primary capture digest differs')
    expected=parse_bis(store.payload(primary['BIS_CBPOL']['raw']))
    expected['SGD']=parse_sora(store.payload(primary['MAS_SORA']['raw']))
    if {c:[{k:v for k,v in r.items() if k!='currency'} for r in values] for c,values in result.items()}!=expected:
        raise ValueError('Funding observations do not reproduce their primary captures')
    return snapshot,dict(result)
