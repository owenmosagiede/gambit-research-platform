"""Small synthetic records prove the benchmark compares persisted authority."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from research_benchmark_closure import capture_closure, compare_closures, validate_capture
from research.contracts import HORIZONS, digest, ref
from research.store import ResearchStore


def implementation(label):
    files={'research/synthetic.py':digest(label)}
    return {'profile':'synthetic','files':files,'fingerprint':digest(files),
            'numeric_environment':{'python':'isolated fixture'}}


def reference(label):
    return {'id':label,'version':'1.0.0','content_sha256':digest(label)}


def fixture(root,label,mutation=None):
    store=ResearchStore(root); impl=implementation(label); executor=store.put('implementation',impl,impl)
    links=[]; statuses=[]
    for h in HORIZONS:
        relation={'recipe':reference('RECIPE'),'scope':reference('SCOPE'),'mode':'CS','horizon':h,
                  'members':['AAA'],'targets':[reference('TARGET_'+str(h))]}
        relationship=store.put('relationship',relation,relation)
        period={'start_inclusive':'2017-01-01','end_exclusive':'2022-01-01'}
        trial_refs=[]
        def trial(phase,p1=None):
            rows=[{'feature':'1.25','target':'0.02','lineage':[reference('FIXED_LINEAGE')]}]
            key={'relationship':ref(relationship),'stage':phase,'horizon':h,
                 'research_spec':reference('RSPEC'),'period':period,
                 'prepared':{'phase':phase,'period':period,'members':[
                     {'instrument_id':'AAA','materializations':[reference('FEATURE_MATERIALIZATION')]}]},
                 'targets':[{'instrument':'AAA','binding':reference('TARGET_MATERIALIZATION_'+str(h))}],
                 'implementation':ref(executor),'input_digest':digest(rows),
                 'discovery_trial':ref(p1) if p1 else None,
                 'discovery_effect':p1['body']['metrics']['primary_effect'] if p1 else None}
            if h==1 and phase=='P1':
                if mutation=='target':key['targets'][0]['binding']=reference('OTHER_TARGET')
                elif mutation=='input_digest':key['input_digest']=digest('different aligned sample')
                elif mutation=='prepared_reference':key['prepared']['members'][0]['materializations']=[reference('OTHER_FEATURE_MATERIALIZATION')]
            exposure=store.put('exposure',{'trial_key':digest(key)},
                {'stage':phase,'period':period,'classification':'ISOLATED_SYNTHETIC',
                 'sample_digest':digest(rows),'relationship':ref(relationship)})
            saved_rows=deepcopy(rows)
            if mutation=='payload' and h==1 and phase=='P1':saved_rows[0]['feature']='999'
            if mutation=='lineage' and h==1 and phase=='P1':saved_rows[0]['lineage']=[reference('OTHER_LINEAGE')]
            artifact=store.artifact(key,{'rows':saved_rows,'coverage':{'count':1},'lineage':[reference('FIXED_LINEAGE')]})
            effect=None if h==63 and phase=='P1' else -1 if h==21 and phase=='P1' else 1
            body={'stage':phase,'metrics':{'primary_effect':effect},'sample':{'count':1},
                  'evidence':{'all_values':'retained','nested':{'id':'SCIENTIFIC_INPUT_ID',
                    'content_sha256':digest('scientific input'),'date':'2017-01-02',
                    'record_sha256':digest('scientific record')}},'reason_codes':['SYNTHETIC'],
                  'exposure':ref(exposure),'artifact_manifests':[ref(artifact)]}
            body['admission' if phase=='P1' else 'decision']='not_admitted' if h==7 else 'admitted' if phase=='P1' else 'VALIDATED'
            if h==1 and phase=='P1':
                if mutation=='metric':body['metrics']['primary_effect']=2
                elif mutation=='sample':body['sample']['count']=2
                elif mutation=='evidence':body['evidence']['all_values']='changed'
                elif mutation=='unknown_field':body['new_scientific_field']={'must_not_drop':True}
                elif mutation=='evidence_id':body['evidence']['nested']['id']='OTHER_SCIENTIFIC_ID'
                elif mutation=='evidence_hash':body['evidence']['nested']['content_sha256']=digest('different scientific input')
                elif mutation=='evidence_date':body['evidence']['nested']['date']='2017-01-03'
                elif mutation=='evidence_record_checksum':body['evidence']['nested']['record_sha256']=digest('different scientific record')
                elif mutation=='embedded_executor':body['evidence']['must_not_normalize']=ref(executor)
            return store.put('trial',key,body)
        p1=trial('P1'); trial_refs.append(ref(p1))
        admission=store.put('admission',{'trial':ref(p1)},
            {'trial':ref(p1),'relationship':ref(relationship),'decision':p1['body']['admission'],
             'reason_codes':p1['body']['reason_codes'],'evidence':p1['body']['evidence']})
        validations=[]; p2status='not_admitted'
        if h not in (7,21,63):
            p2=trial('P2',p1); trial_refs.append(ref(p2)); p2status='VALIDATED'
            validation=store.put('validation',{'discovery':ref(p1),'evaluation':ref(p2)},
                {'relationship':ref(relationship),'decision':'VALIDATED','discovery_trial':ref(p1),
                 'evaluation_trial':ref(p2),'reason_codes':['CHANGED' if mutation=='validation' and h==1 else 'SYNTHETIC'],
                 'evidence':{'saved':True}})
            validations=[ref(validation)]
        elif h in (21,63):
            p2status='FAILED' if h==21 else 'UNRESOLVED'
            validation=store.put('validation',{'discovery':ref(p1),'precheck':'direction' if h==21 else 'missing_effect','profile':digest('profile')},
                {'relationship':ref(relationship),'decision':p2status,'discovery_trial':ref(p1),
                 'evaluation_trial':None,'period':period,'research_spec':reference('RSPEC'),'reason_codes':['SYNTHETIC']})
            validations=[ref(validation)]
        link={'relationship':ref(relationship),'trial_results':trial_refs,'admission_results':[ref(admission)],'validation_results':validations}
        links.append(ref(store.put('link',link,link)))
        statuses.append({'horizon':h,'p1_status':p1['body']['admission'],'p2_status':p2status})
    job={'status':'succeeded','mode':'CS','horizons':statuses,'results':links}
    return store,job,impl


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
    def capture(self,name,label,mutation=None):
        return capture_closure(*fixture(self.root/name,label,mutation)[:2],
                               expected_implementation=implementation(label))
    def test_only_explicit_executor_and_derived_references_map(self):
        old=self.capture('old','old'); new=self.capture('new','new')
        self.assertNotEqual(old['provenance'],new['provenance'])
        self.assertTrue(compare_closures(old,new)['exact_saved_scientific_equality'])
        self.assertEqual(len(old['scientific']['horizons']),5)
        # Even a value equal to an executor reference stays exact outside the
        # explicitly declared implementation edge; no recursive ID stripping.
        old=self.capture('old-embedded','old','embedded_executor')
        new=self.capture('new-embedded','new','embedded_executor')
        self.assertFalse(compare_closures(old,new)['exact_saved_scientific_equality'])
    def test_validly_published_post_kernel_changes_cannot_pass(self):
        old=self.capture('baseline','old')
        for mutation in ('metric','sample','evidence','unknown_field','payload','lineage','target','validation',
                         'input_digest','prepared_reference','evidence_id','evidence_hash','evidence_date','evidence_record_checksum'):
            with self.subTest(mutation=mutation):
                changed=self.capture(mutation,'new',mutation)
                self.assertFalse(compare_closures(old,changed)['exact_saved_scientific_equality'])
    def test_capture_validates_actual_executor_and_payload_bytes(self):
        store,job,impl=fixture(self.root/'fixture','old')
        with self.assertRaisesRegex(ValueError,'actual benchmark implementation'):
            capture_closure(store,job,expected_implementation=implementation('different'))
        payload=next((self.root/'fixture/storage/payloads').rglob('*.json'))
        payload.write_text('tampered fixture payload')
        with self.assertRaisesRegex(ValueError,'Artifact corruption'):
            capture_closure(store,job,expected_implementation=impl)
    def test_forged_projection_or_raw_provenance_rejected(self):
        original=self.capture('original','old')
        altered=deepcopy(original); altered['scientific']['job']['mode']='TS'
        altered['scientific_sha256']=digest(altered['scientific'])
        with self.assertRaisesRegex(ValueError,'projection/checksum'):validate_capture(altered)
        altered=deepcopy(original); altered['provenance']['horizons'][0]['trials'][0]['record']['body']['metrics']['primary_effect']='999'
        with self.assertRaisesRegex(ValueError,'trial link closure differs'):validate_capture(altered)
    def test_missing_horizon_or_broken_reference_never_passes(self):
        store,job,impl=fixture(self.root/'fixture','old')
        missing=deepcopy(job); missing['results'].pop()
        with self.assertRaisesRegex(ValueError,'horizon population'):capture_closure(store,missing,expected_implementation=impl)
        altered=self.capture('original','old')
        altered['provenance']['horizons'][0]['trials'][0]['artifacts'][0]['scientific_key_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'artifact derivation'):validate_capture(altered)


if __name__=='__main__':unittest.main()
