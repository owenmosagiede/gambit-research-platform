"""Run the shipped selector against explicit external compatibility responses."""
import unittest
import test_reusable_feature_ui as fixture

class ExternalFeatureUITests(unittest.TestCase):
    def response(self, compatible):
        feature=fixture.feature(kind='stored_feature')
        value=fixture.resolution(feature)
        value.update(submission_compatible=compatible,alignment_policy=fixture.ref('POL_EXTERNAL_STORED_DAILY_STATE') if compatible else None,
                     source_materializations=[],source_application_note='Daily state; next weekday; timing unverified.' if compatible else 'External Features require individual Scope.')
        if compatible:
            value['members'][0]['state']='missing';value['members'][0]['reason']='Alignment prepared after Submit.'
            value['summary'].update(missing_member_count=1,blocked_member_count=0)
        return feature,value

    def test_pending_preflight_prevents_submit_and_compatible_response_enables_it(self):
        feature,response=self.response(True)
        views=fixture.ui([feature],[fixture.choose_feature(feature),fixture.choose_scope('AUDUSD'),{'action':'settle','index':0}],
                         responses={fixture.path(feature):response},hold=[fixture.path(feature)])
        self.assertTrue(views[-2]['validity']);self.assertEqual(views[-1]['validity'],'')
        self.assertIn('Daily state',views[-1]['status']);self.assertIn('POL_EXTERNAL_STORED_DAILY_STATE',views[-1]['status'])
        self.assertTrue(all(r['method']=='GET' for r in views[-1]['requests']))
        self.assertTrue(any(e['type']=='feature-state-change' for e in views[-1]['events']))

    def test_incompatible_response_blocks_submit_with_reason(self):
        feature,response=self.response(False)
        view=fixture.ui([feature],[fixture.choose_feature(feature),fixture.choose_scope('AUDUSD')],responses={fixture.path(feature):response})[-1]
        self.assertEqual(view['validity'],'External Features require individual Scope.')
        self.assertIn('individual Scope',view['status'])

    def test_scope_change_revokes_prior_compatibility_while_pending(self):
        feature,response=self.response(True)
        next_response=fixture.resolution(feature,'FTMO_UNIVERSE',('AUDUSD','EURUSD'))
        next_response.update(submission_compatible=False,source_application_note='Universe broadcasting unsupported.',source_materializations=[])
        views=fixture.ui([feature],[fixture.choose_feature(feature),fixture.choose_scope('AUDUSD'),fixture.choose_scope('FTMO_UNIVERSE')],
                         responses={fixture.path(feature):response,fixture.path(feature,'FTMO_UNIVERSE'):next_response},hold=[fixture.path(feature,'FTMO_UNIVERSE')])
        self.assertEqual(views[-2]['validity'],'');self.assertTrue(views[-1]['validity'])
        self.assertNotIn('featureResolution',views[-1]['dataset'])

    def test_backend_explicit_rejection_is_not_reported_as_unknown_submission(self):
        import test_research_ui as submission
        rejection={'http':422,'recorded':False,'error':{'code':'EXTERNAL_ALIGNMENT_BLOCKED'},
                   'blockers':[{'code':'EXTERNAL_ALIGNMENT_BLOCKED','message':'Universe broadcasting unsupported.'}]}
        view=submission.ui([{'action':'submit'}],routes={'POST /api/experiments':[rejection]})[-1]
        self.assertEqual(view['status'],'Not submitted')
        self.assertIn('No research job was recorded',view['message'])
        self.assertIn('Universe broadcasting',submission.all_text(view['blockers']))
        self.assertTrue(view['retryHidden']);self.assertEqual(view['saved'],{})
        self.assertFalse(view['submitDisabled'])


if __name__=='__main__':unittest.main()
