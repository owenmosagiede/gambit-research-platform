"""Library pages: filtering, inline expansion, static queue and read-only browsing."""
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import json,shutil,subprocess,unittest
import test_signal_recipe_ui as signals
ROOT=Path(__file__).resolve().parents[1]

class SignalFilterTests(unittest.TestCase):
    def test_search_provider_status_and_dates_without_requests(self):
        a=signals.group();b=signals.ces()
        steps=[{'action':'filter','key':'search','value':'momentum'}, {'action':'clear'},
               {'action':'filter','key':'provider','value':'FRED_ALFRED'}, {'action':'clear'},
               {'action':'filter','key':'state','value':'Research results linked'}, {'action':'clear'},
               {'action':'filter','key':'from','value':'2030-01-01'}, {'action':'clear'}]
        views=signals.ui([a,b],steps)
        self.assertEqual([len(signals.rows(v['table'])) for v in views],[2,1,2,1,2,0,2,0,2])
        self.assertTrue(all(len(v['requests'])==1 for v in views))
    def test_provider_and_date_must_match_same_output(self):
        a=signals.group(outputs=[signals.output(),signals.output(2,'EURUSD')])
        a['outputs'][1]['source']['provider']='Other provider'
        a['outputs'][1]['materializations'][0]['coverage'].update(reference_start='2020-01-01',reference_end='2020-12-31')
        v=signals.ui([a],[{'action':'filter','key':'provider','value':'Other provider'},
                         {'action':'filter','key':'from','value':'2024-01-01'}])
        self.assertEqual(len(signals.rows(v[1]['table'])),1)
        self.assertEqual(len(signals.rows(v[2]['table'])),0)
    def test_date_overlap_is_inclusive_and_reversed_range_explained(self):
        v=signals.ui([signals.group()],[{'action':'filter','key':'from','value':'2024-01-03'},
                {'action':'filter','key':'to','value':'2024-01-03'}, {'action':'filter','key':'from','value':'2024-01-04'}])
        self.assertEqual(len(signals.rows(v[2]['table'])),1)
        self.assertEqual(len(signals.rows(v[3]['table'])),0)
        self.assertIn('must be on or before',v[3]['catalogStatus'])
    def test_card_collapses_and_filter_hides_expanded_detail(self):
        a=signals.group();v=signals.ui([a],[{'action':'select','id':a['id']},{'action':'select','id':a['id']},
              {'action':'select','id':a['id']},{'action':'filter','key':'search','value':'not-present'}])
        self.assertFalse(v[1]['detailHidden']);self.assertTrue(v[2]['detailHidden'])
        self.assertFalse(v[3]['detailHidden']);self.assertTrue(v[4]['detailHidden'])
        self.assertEqual(len(signals.rows(v[4]['table'])),0)
    def test_filtering_aborts_stale_output_detail(self):
        a=signals.group();href=a['outputs'][0]['materializations'][0]['href']
        v=signals.ui([a],[{'action':'open','id':signals.sid(),'mid':signals.mid()},
             {'action':'filter','key':'search','value':'absent'}, {'action':'settle','index':0}],hold=[href])
        self.assertTrue(v[-1]['detailHidden']);self.assertTrue(v[-1]['aborted'][1])
        self.assertEqual(signals.flatten(v[-1]['detail']),'')
    def test_exact_output_link_reveals_filtered_recipe(self):
        a=signals.group();v=signals.ui([a],[{'action':'filter','key':'search','value':'absent'},
             {'action':'open','id':signals.sid(),'mid':signals.mid()}])
        self.assertEqual(len(signals.rows(v[-1]['table'])),1);self.assertFalse(v[-1]['detailHidden'])


def pit_catalog():
    records=[]
    for i,(name,provider,frequency,start,end) in enumerate([
        ('Wage history','FRED_ALFRED','monthly','2006-03-01','2026-09-01'),
        ('AUD/USD closes','Twelve Data','daily','1979-12-24','2026-09-05')],1):
        retro=i==2
        records.append({'id':f'DATASET_{i}','name':name,'series_id':'CES0500000003' if i==1 else 'AUD/USD',
          'provider':provider,'frequency':frequency,'units':'USD','snapshots':[{'id':'SNAPSHOT_'+f'{i:064x}',
          'label':'Stored history','source_view_version':'1.0.0','observation_start':start,'observation_end':end,
          'vintage_start':None if retro else '2011-03-04','vintage_end':None if retro else '2026-10-02',
          'observation_count':64,'event_count':64,'timing_precision':'date','scope':'retrospective_snapshot' if retro else 'full_history',
          'vintage_count':0 if retro else 2,'captured_at':'2026-10-09T00:00:00Z','missing_event_count':0}]})
    return {'schema_version':'1.0.0','datasets':records,'issues':[],'dataset_count':2,'snapshot_count':2}


def pit_ui(steps=(),catalog=None,fail=False,hash="#pit"):
    harness=r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.listeners={};this.attributes={};this.textContent='';this.value='';this.hidden=false;this.parentElement=null;}
 append(...items){for(const item of items){if(item.parentElement)item.parentElement.children=item.parentElement.children.filter(c=>c!==item);item.parentElement=this;this.children.push(item);}}
 replaceChildren(...items){for(const c of this.children)c.parentElement=null;this.children=[];this.append(...items);}
 setAttribute(k,v){this.attributes[k]=v;} addEventListener(k,v){this.listeners[k]=v;} focus(){}
 querySelectorAll(){return walk(this).filter(n=>n.tag==='button'&&n.dataset.snapshotId);}
}
const walk=n=>[n,...n.children.flatMap(walk)];
const ids=Object.fromEntries([...fs.readFileSync(input.html,'utf8').matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element(m[1])]));
const events={},requests=[],context={document:{getElementById:id=>ids[id],createElement:t=>new Element(t),activeElement:null},
 window:{location:{protocol:'http:',hash:input.hash},addEventListener:(n,f)=>events[n]=f,setTimeout:()=>1,clearTimeout:()=>{}},AbortController,
 fetch:async(url,options)=>{requests.push({url,method:options.method});if(input.fail)throw Error('unavailable');return {ok:true,json:async()=>input.catalog};}};
const views=[];const read=n=>({text:n.textContent,tag:n.tag,hidden:n.hidden,attributes:n.attributes,children:n.children.map(read)});
function snapshot(){views.push({names:walk(ids['library-items']).filter(n=>n.className==='dataset-name').map(n=>n.textContent),status:ids['library-status'].textContent,
 panelHidden:ids['dataset-details'].hidden,title:ids['details-title'].textContent,details:read(ids['details-body']),retryHidden:ids['library-retry'].hidden,
 expanded:walk(ids['library-items']).filter(n=>n.tag==='button').map(n=>n.attributes['aria-expanded']),requests:[...requests]});}
(async()=>{vm.runInNewContext(fs.readFileSync(input.script,'utf8'),context);await new Promise(r=>setImmediate(r));snapshot();
 for(const step of input.steps){if(step.action==='filter'){ids['pit-'+step.key].value=step.value;ids['pit-'+step.key].listeners.input();}
 else if(step.action==='navigate'){context.window.location.hash=step.hash;events.hashchange();}
 else if(step.action==='clear')ids['pit-clear'].listeners.click();
 else if(step.action==='select')walk(ids['library-items']).find(n=>n.dataset.snapshotId===step.id).listeners.click();
 await new Promise(r=>setImmediate(r));snapshot();}process.stdout.write(JSON.stringify(views));})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    node=shutil.which('node')
    if not node:raise unittest.SkipTest('Node.js required')
    value={'script':str(ROOT/'ui/library.js'),'html':str(ROOT/'ui/index.html'),'catalog':catalog or pit_catalog(),'steps':list(steps),'fail':fail,'hash':hash}
    result=subprocess.run([node,'-e',harness],input=json.dumps(value),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)

class PitFilterTests(unittest.TestCase):
    def test_hidden_page_does_not_load_and_navigation_loads_once(self):
        v=pit_ui([{'action':'navigate','hash':'#pit'},{'action':'navigate','hash':'#experiment'},
                  {'action':'navigate','hash':'#pit'}],hash='#experiment')
        self.assertEqual([len(x['requests']) for x in v],[0,1,1,1])

    def test_attributes_filter_and_clear(self):
        v=pit_ui([{'action':'filter','key':'search','value':'CES050'}, {'action':'clear'},
          {'action':'filter','key':'provider','value':'Twelve Data'}, {'action':'clear'},
          {'action':'filter','key':'frequency','value':'monthly'}, {'action':'clear'},
          {'action':'filter','key':'to','value':'1980-01-01'}, {'action':'clear'}])
        self.assertEqual([len(x['names']) for x in v],[2,1,2,1,2,1,2,1,2])
        self.assertTrue(all(len(x['requests'])==1 and x['requests'][0]['method']=='GET' for x in v))
    def test_expand_switch_collapse_and_filter(self):
        a='SNAPSHOT_'+f'{1:064x}';b='SNAPSHOT_'+f'{2:064x}'
        v=pit_ui([{'action':'select','id':a},{'action':'select','id':b},{'action':'select','id':b},
                 {'action':'select','id':a},{'action':'filter','key':'search','value':'absent'}])
        self.assertFalse(v[1]['panelHidden']);self.assertEqual(v[2]['title'],'AUD/USD closes')
        self.assertEqual(v[2]['expanded'],['false','true']);self.assertTrue(v[3]['panelHidden'])
        self.assertTrue(v[-1]['panelHidden']);self.assertEqual(v[-1]['names'],[])
    def test_date_overlap_boundary_and_bad_range(self):
        v=pit_ui([{'action':'filter','key':'from','value':'2026-09-05'}, {'action':'filter','key':'to','value':'2026-09-05'},
                 {'action':'filter','key':'from','value':'2026-09-06'}])
        self.assertEqual(v[2]['names'],['AUD/USD closes']);self.assertEqual(v[3]['names'],[])
        self.assertIn('must be on or before',v[3]['status'])
    def test_api_failure_and_invalid_catalog_do_not_show_fake_data(self):
        self.assertEqual(pit_ui(fail=True)[0]['names'],[])
        bad=pit_catalog();bad['snapshot_count']=9;v=pit_ui(catalog=bad)[0]
        self.assertEqual(v['names'],[]);self.assertFalse(v['retryHidden'])

class PageStructureTests(unittest.TestCase):
    def test_sidebar_only_navigation_and_queue_is_live(self):
        html=(ROOT/'ui/index.html').read_text()
        aside=html.split('<aside',1)[1].split('</aside>',1)[0]
        for page in ('experiment','pit','signals'):self.assertIn('data-page="'+page+'"',aside)
        self.assertNotIn('<section',aside);self.assertNotIn('library-items',aside)
        self.assertNotIn('sidebar-signal',html);self.assertNotIn('pit-sidebar',html)
        experiment=html.split('<main id="experiment-inputs"',1)[1].split('</main>',1)[0]
        self.assertNotIn('id="dataset-details"',experiment)
        for label in ('Trial queue','Sequential execution','queue-board','queue-status'):self.assertIn(label,experiment)
        self.assertNotIn('Mock preview',experiment)
        self.assertNotIn('DEMO 01',experiment)
        self.assertIn('/queue.js',html)
    def test_unique_ids_and_all_controls_are_labelled(self):
        class Parser(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.controls=[];self.labels=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if 'id' in a:self.ids.append(a['id'])
                if tag in ('input','select'):self.controls.append(a['id'])
                if tag=='label':self.labels.append(a['for'])
        p=Parser();p.feed((ROOT/'ui/index.html').read_text())
        self.assertEqual(len(p.ids),len(set(p.ids)))
        self.assertTrue(set(p.controls)<=set(p.labels))

if __name__=='__main__':unittest.main()
