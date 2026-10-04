import os,sys,unittest
from datetime import date
import pandas as pd
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","src"))
from fetcher import FreeDataFetcher
from mtf_index_sweep_engine import _weekly_levels, _current_week, _swing_highs
from index_universe import INDEX_UNIVERSE

class CoreTests(unittest.TestCase):
    def test_official_oi_parser(self):
        header='Client Type,'+','.join('field'+str(i) for i in range(1,15))
        text='title,,,,\n'+header+'\nClient,'+','.join(str(i) for i in range(1,15))+'\nFII,'+','.join(str(i) for i in range(15,29))+'\n'
        rows=FreeDataFetcher()._parse_participant_csv(text,'2026-01-01')
        self.assertEqual(rows[0]['client_type'],'Client');self.assertEqual(rows[1]['future_index_long'],15)

    def test_no_constituent_stock_symbols(self):
        banned={'RELIANCE.NS','TATASTEEL.NS','ONGC.NS','DLF.NS','HDFCBANK.NS','TITAN.NS','JSWSTEEL.NS'}
        used={x.get('index_symbol') for x in INDEX_UNIVERSE}|{x.get('history_proxy') for x in INDEX_UNIVERSE}
        self.assertFalse(banned & used)

    def test_previous_week_levels_are_not_current_week(self):
        idx=pd.bdate_range('2026-01-05','2026-01-16')
        d=pd.DataFrame({'Open':100,'High':range(101,111),'Low':range(90,100),'Close':100,'Volume':1000},index=idx)
        pwh,pwl=_weekly_levels(d,date(2026,1,16))
        self.assertEqual(pwh,105);self.assertEqual(pwl,90)

    def test_swing_high_is_causal_fractal(self):
        x=pd.DataFrame({'High':[1,2,5,2,1,3,2],'Low':[0]*7})
        self.assertEqual(_swing_highs(x,2),[2])

if __name__=='__main__':unittest.main()
