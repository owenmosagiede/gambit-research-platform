"""Pure generic selector tests; no real input stores, adapters or API calls."""
import unittest
from data.pit_selection import select_asof
from data.alfred_pit import select_rows


class GenericPITSelectionTests(unittest.TestCase):
    def test_latest_available_per_reference_and_order(self):
        rows=[{'reference_time':'2020-02-01','available_at':'2020-03-01','value':'2'},
              {'reference_time':'2020-01-01','available_at':'2020-02-01','value':'1'},
              {'reference_time':'2020-01-01','available_at':'2020-04-01','value':'9'}]
        self.assertEqual([r['value'] for r in select_asof(rows,'2020-03-01')],['1','2'])
        self.assertEqual([r['value'] for r in select_asof(rows,'2020-04-01')],['9','2'])
        self.assertEqual([r['value'] for r in select_asof(rows,'2020-04-01',reference='2020-01-01')],['9'])
        self.assertEqual([r['value'] for r in select_asof(rows,'2020-04-01',reference_cutoff='2020-01-01')],['9'])
        self.assertEqual([r['value'] for r in select_asof(rows,'2020-03-01',sort=False)],['2','1'])
    def test_future_data_and_revisions_do_not_change_prior_selection(self):
        known=[{'reference_time':'2020-01-01','available_at':'2020-02-01','value':'1'}]
        appended=known+[{'reference_time':'2020-01-01','available_at':'2020-04-01','value':'9'},
                        {'reference_time':'2020-03-01','available_at':'2020-04-01','value':'3'}]
        self.assertEqual(select_asof(known,'2020-03-01'),select_asof(appended,'2020-03-01'))
    def test_reference_and_availability_cutoffs_are_independent(self):
        rows=[{'reference_time':'2021-01-01','available_at':'2020-01-01','value':'10'}]
        self.assertEqual(len(select_asof(rows,'2020-02-01')),1)
        self.assertEqual(select_asof(rows,'2020-02-01',reference_cutoff='2020-02-01'),[])
    def test_ambiguous_ties_fail_and_exact_duplicates_collapse(self):
        row={'reference_time':'2020-01-01','available_at':'2020-02-01','value':'1'}
        self.assertEqual(select_asof([row,dict(row)],'2020-02-01'),[row])
        with self.assertRaises(ValueError):select_asof([row,dict(row,value='2')],'2020-02-01')
        # Future ambiguity is not evidence available at the earlier cutoff.
        self.assertEqual(select_asof([row,dict(row,value='2')],'2020-01-01'),[])
    def test_missing_revisions_are_preserved_and_rows_not_mutated(self):
        rows=[{'reference_time':'2020-01-01','available_at':'2020-02-01','value':'1','status':'valid'},
              {'reference_time':'2020-01-01','available_at':'2020-03-01','value':None,'status':'missing'}]
        out=select_asof(rows,'2020-03-01')
        self.assertIsNone(out[0]['value'])
        out[0]['value']='changed'
        self.assertIsNone(rows[-1]['value'])
    def test_interval_mode_preserves_exclusive_successor_and_hides_future(self):
        rows=[{'obs':'2020-01-01','avail':'2020-02-01','next':'2020-03-01','value':1},
              {'obs':'2020-01-01','avail':'2020-03-01','next':None,'value':2}]
        kwargs={'reference_key':'obs','availability_key':'avail','successor_key':'next'}
        self.assertEqual(select_asof(rows,'2020-02-29',**kwargs),[{'obs':'2020-01-01','avail':'2020-02-01','value':1}])
        self.assertEqual(select_asof(rows,'2020-03-01',**kwargs),[{'obs':'2020-01-01','avail':'2020-03-01','value':2}])
        self.assertEqual(rows[0]['next'],'2020-03-01')
    def test_established_alfred_selector_matches_independent_original_rule(self):
        rows=[{'observation_date':'2018-02-01','vintage_date':'2018-03-09','next_vintage_date':None,'value':'27'},
              {'observation_date':'2018-01-01','vintage_date':'2018-02-02','next_vintage_date':'2018-03-09','value':'26.74'},
              {'observation_date':'2018-01-01','vintage_date':'2018-03-09','next_vintage_date':None,'value':'26.71'}]
        for cutoff in ['2018-02-01','2018-02-02','2018-03-08','2018-03-09','2018-03-10']:
            for observation in [None,'2018-01-01','2018-02-01','2017-12-01']:
                with self.subTest(cutoff=cutoff,observation=observation):
                    expected=[{k:v for k,v in r.items() if k!='next_vintage_date'} for r in rows if (observation is None or r['observation_date']==observation) and r['vintage_date']<=cutoff and (r['next_vintage_date'] is None or cutoff<r['next_vintage_date'])]
                    self.assertEqual(select_rows(rows,cutoff,observation),expected)
        with self.assertRaises(ValueError):select_rows(rows,'2018-03-09T08:30:00Z')
        with self.assertRaises(ValueError):select_rows(rows,'2018-03-09','not-a-date')

if __name__=='__main__':unittest.main()
