"""Pre-deployment deep diagnostics. Exits non-zero on critical data/logic failures."""
import os,sys,time,sqlite3
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"src"))
from fetcher import FreeDataFetcher
from index_universe import INDEX_UNIVERSE
from index_sweep_engine import IndexSweepEngine
from weekly_index_sweep_engine import WeeklyIndexSweepEngine
from mtf_index_sweep_engine import MTFIndexSweepEngine

def main():
    failures=[]; f=FreeDataFetcher(); t=time.time()
    oi=f.fetch_latest_participant_oi(); types={r['client_type'] for r in oi['raw_data']}
    print('OI',oi['date'],oi['source'],types)
    if not {'Client','DII','FII','Pro'}<=types:failures.append('OI participant rows incomplete')
    hist=f.fetch_recent_history(10)
    if hist.date.nunique()<3:failures.append('OI history fewer than 3 days')
    macro=f.fetch_global_macro(); good=[k for k,v in macro.items() if v.get('current',0)>0]
    print('MACRO',len(good),'/',len(macro),good)
    if len(good)<5:failures.append('fewer than 5 macro feeds')
    sectors=f.fetch_sector_strength();print('SECTORS',len(sectors),'sources',sorted({x['data_source'] for x in sectors}))
    if len(sectors)<12:failures.append(f'only {len(sectors)} sector feeds')
    daily=IndexSweepEngine().scan_all_indices();print('DAILY engine OK hits',len(daily))
    weekly=WeeklyIndexSweepEngine().scan_weekly_indices();print('WEEKLY scanned',weekly['total_scanned'],'failed',weekly['failed_indices'],'hits',len(weekly['weekly_hits']))
    if len(weekly['failed_indices'])>3:failures.append('too many weekly feed failures')
    mtf=MTFIndexSweepEngine().scan_all_indices();print('MTF total',mtf['total_indices'],'errors',len(mtf['errors']),'setups',len(mtf['setups']))
    if len(mtf['errors'])>3:failures.append('too many MTF errors')
    print('ELAPSED',round(time.time()-t,2),'sec')
    if failures:
        print('FAIL:',*failures,sep='\n - ');return 1
    print('ALL CRITICAL DIAGNOSTICS PASSED');return 0
if __name__=='__main__':raise SystemExit(main())
