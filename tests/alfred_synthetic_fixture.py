"""Generate temporary fictional onboarding inputs; never retain a real pilot copy.

The fixed January acceptance-probe values are required by the legacy bounded
writer. Every other cell and all transport metadata here are synthetic. Nothing
is fetched, and no path in the legacy Data directory is opened.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

from data.alfred_onboarding import BASE_URL, SERIES, canonical, sha


SYNTHETIC_EVENT_COUNT = 13
STAMP = '2020-01-10T00:00:00.000000Z'


def make_bounded_fixture(root, scratch):
    """Run the real bounded importer on fictional files under scratch; return run path."""
    root, scratch = Path(root), Path(scratch)
    legacy, acquisition = scratch/'synthetic_legacy', scratch/'synthetic_acquisition'
    legacy.mkdir(); acquisition.mkdir()
    observations = [{'date':f'2018-{month:02d}-01', SERIES+'_20190104':str(100+month)}
                    for month in range(2,13)]
    observations.insert(0, {'date':'2018-01-01', SERIES+'_20180202':'26.74', SERIES+'_20180309':'26.71'})
    vintages = {'output_type':3, 'units':'lin', 'offset':0, 'count':12, 'observations':observations}
    raw = canonical(vintages)+b'\n'
    raw_relative = 'synthetic/raw.json'
    path = legacy/raw_relative; path.parent.mkdir(); path.write_bytes(raw)
    digest = sha(raw)
    old_receipt = {'checksum':{'value':digest}, 'retrieved_at':STAMP,
                   'request':{'parameters':{'series_id':SERIES, 'output_type':'3'}},
                   'response':{'stored_content_transform':'none', 'http_status':200,
                               'headers':{'content-type':'application/json'}}}
    metadata = legacy/f'production/alfred/series={SERIES}'; metadata.mkdir(parents=True)
    for name in ['raw-ingestion-manifest.json','series-manifest.json','dataset-registry.json','source-registry.json']:
        value = {'ingestions':[old_receipt]} if name=='raw-ingestion-manifest.json' else {'synthetic_fixture':True}
        (metadata/name).write_bytes(canonical(value)+b'\n')
    payloads = {
        'metadata':{'seriess':[{'id':SERIES,'title':'Synthetic bounded test series',
                    'frequency':'Monthly','units':'Dollars per Hour','seasonal_adjustment':'Seasonally Adjusted'}]},
        'latest':{'sort_order':'desc','observations':[{'date':f'2019-{month:02d}-01','value':str(200+month)} for month in range(12,7,-1)]},
        'vintages_2018':vintages,
        'asof_2018-02-02':{'count':1,'offset':0,'observations':[{'date':'2018-01-01','value':'26.74'}]},
        'asof_2018-03-09':{'count':1,'offset':0,'observations':[{'date':'2018-01-01','value':'26.71'}]},
    }
    for name, value in payloads.items():
        content = canonical(value)+b'\n'; (acquisition/(name+'.json')).write_bytes(content)
        endpoint = BASE_URL+('series' if name=='metadata' else 'series/observations')
        receipt = {'endpoint':endpoint,'parameters':{'series_id':SERIES},'started_at':STAMP,'finished_at':STAMP,
                   'http_status':200,'error':None,'headers':{'content-type':'application/json'},
                   'sha256':sha(content),'byte_count':len(content)}
        (acquisition/(name+'.receipt.json')).write_bytes(canonical(receipt)+b'\n')
    spec = spec_from_file_location('synthetic_onboard_tool',root/'tools/onboard_alfred.py')
    tool = module_from_spec(spec); spec.loader.exec_module(tool)
    with patch.object(tool,'RAW',raw_relative), patch.object(tool,'RAW_HASH',digest), patch.object(tool,'now',return_value=STAMP):
        result = tool.onboard(root,legacy,acquisition)
    if result['counts']['current_vintage_values']!=SYNTHETIC_EVENT_COUNT:
        raise AssertionError('Unexpected synthetic event count')
    return result['run_path']
