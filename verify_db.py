"""Exact data comparison + actual main.py DB endpoint function replay.
No application startup, macro_router import, Supabase/network requests or writes.
The supplied main.py is trusted local Python; this is NOT a security sandbox.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import itertools
import json
from pathlib import Path
import re
import time
from types import SimpleNamespace
import numpy as np
import pandas as pd
from db_tools import ro, user_tables, compare_tables, integrity, write_json

FUNCTIONS = {'clean_apt_name','search_apt','query_chart_from_db','get_chart_data','get_rankings'}
RANKS = ('price_max','84_max','84_avg','59_max','59_avg','trade_cnt','pyeong_avg')
UI_MONTHS = list(range(3,37)) + list(range(48,241,12))

def load_app(main, database):
    source = Path(main).read_text(encoding='utf-8-sig')
    tree = ast.parse(source,filename=str(main))
    nodes = []
    found = set()
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in FUNCTIONS:
            node.decorator_list = []  # no routing or LRU cache contamination
            nodes.append(node); found.add(node.name)
        elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='LAWD_CD_MAP' for t in node.targets):
            nodes.append(node)
    if found != FUNCTIONS: raise RuntimeError('Missing endpoint functions: '+repr(FUNCTIONS-found))
    env = {'__builtins__':__builtins__, 're':re,'np':np,'pd':pd,'DB_FILE':str(database),
           'sqlite3':SimpleNamespace(connect=lambda *a,**kw:ro(database)),
           'Query':lambda value=None,**kw:value,
           'get_real_top10_compared':lambda name:[]}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(main),'exec'),env)
    # Reproduce the original startup block exactly, without importing the app.
    c = ro(database)
    try:
        rows = c.execute('SELECT DISTINCT apt_name FROM apt_trades ORDER BY apt_name ASC').fetchall()
    finally: c.close()
    names = []
    for r in rows:
        n = env['clean_apt_name'](str(r[0]))
        if n and not re.match(r'^[\d\-\(\)]+$',n) and n not in names: names.append(n)
    env['CACHED_APT_NAMES']=names
    return env

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),
        allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))

def verify(before, after, main, full=False, names_limit=20, months=None, rank_types=None):
    a,b = ro(before),ro(after)
    result = {'passed':False,'scope':'full UI matrix' if full else 'sampled endpoint inputs',
        'main_sha256':hashlib.sha256(Path(main).read_bytes()).hexdigest(),
        'network_top10':'stubbed to []; excluded from DB parity',
        'http_macro_auth_frontend':'not tested; endpoint Python bodies only',
        'hidden_rowid_numbers':'not compared; declared values and row traversal order compared',
        'errors':[], 'counts':{}, 'timing_seconds':{}, 'plans':{}}
    try:
        integrity(a); integrity(b)
        tables = user_tables(a)
        if tables != user_tables(b): raise AssertionError('User table set differs')
        result['tables']=compare_tables(a,b,tables)
        for kind in ('table','view','trigger'):
            q = "SELECT name,sql FROM sqlite_schema WHERE type=? AND name NOT LIKE 'sqlite_%' ORDER BY name"
            if a.execute(q,(kind,)).fetchall() != b.execute(q,(kind,)).fetchall():
                raise AssertionError(kind+' definitions differ')
        # Constraint indexes and AUTOINCREMENT sequence are semantic, not optional.
        for t in tables:
            def constraints(c):
                return sorted((r[1],r[2],r[3],r[4],tuple(c.execute('PRAGMA index_xinfo("'+r[1].replace('"','""')+'")')))
                    for r in c.execute('PRAGMA index_list("'+t.replace('"','""')+'")') if r[2] or r[3]!='c')
            if constraints(a) != constraints(b): raise AssertionError('Constraint indexes differ: '+t)
        for pragma in ('user_version','application_id','encoding'):
            if a.execute('PRAGMA '+pragma).fetchone()!=b.execute('PRAGMA '+pragma).fetchone():
                raise AssertionError(pragma+' differs')
        has_seq = a.execute("SELECT 1 FROM sqlite_schema WHERE name='sqlite_sequence'").fetchone()
        if has_seq and a.execute('SELECT * FROM sqlite_sequence ORDER BY name').fetchall()!=b.execute('SELECT * FROM sqlite_sequence ORDER BY name').fetchall():
            raise AssertionError('AUTOINCREMENT sequence differs')
        old,new = load_app(main,before),load_app(main,after)
        if old['CACHED_APT_NAMES'] != new['CACHED_APT_NAMES']: raise AssertionError('Startup autocomplete cache differs')
        names = old['CACHED_APT_NAMES']
        if not full and len(names)>names_limit:
            # Spread deterministic samples across the name space; add direct-trade
            # and whitespace examples so first-20 bias does not mask those cases.
            names = [names[i*(len(names)-1)//(names_limit-1)] for i in range(names_limit)]
            for (raw,) in a.execute("SELECT apt_name FROM apt_trades WHERE deal_type='직거래' OR apt_name LIKE '% %' LIMIT 20"):
                n=old['clean_apt_name'](str(raw))
                if n and n not in names: names.append(n)
        names = list(dict.fromkeys(names+['__NO_SUCH_APARTMENT__']))
        periods = months or (UI_MONTHS if full else [3,12,24,240])
        result['tested_names']=names
        result['tested_months']=periods
        def check(kind,fn,args):
            outcomes=[]
            times=[]
            for app in (old,new):
                t=time.perf_counter()
                try: outcomes.append(('ok',canonical(app[fn](*args))))
                except Exception as e: outcomes.append(('error',type(e).__name__+': '+str(e)))
                times.append(time.perf_counter()-t)
            result['counts'][kind]=result['counts'].get(kind,0)+1
            aggregate=result['timing_seconds'].setdefault(kind,{'before':0.0,'after':0.0,'max_before':0.0,'max_after':0.0})
            aggregate['before']+=times[0]; aggregate['after']+=times[1]
            aggregate['max_before']=max(aggregate['max_before'],times[0]); aggregate['max_after']=max(aggregate['max_after'],times[1])
            if outcomes[0][0]!='ok' or outcomes[1][0]!='ok' or outcomes[0]!=outcomes[1]:
                result['failure_count']=result.get('failure_count',0)+1
                if len(result['errors'])<50:
                    result['errors'].append({'kind':kind,'args':args,
                        'before_status':outcomes[0][0],'after_status':outcomes[1][0],
                        'before_error':outcomes[0][1] if outcomes[0][0]=='error' else None,
                        'after_error':outcomes[1][1] if outcomes[1][0]=='error' else None,
                        'reason':'exception or exact ordered response differs'})
            total=sum(result['counts'].values())
            if total%100==0: print(f'  ENDPOINT cases {total:,}; failures {result.get("failure_count",0)}',flush=True)
        search_terms=['',' ','자이','없는단지zz']
        for name in names:
            search_terms.extend([name,name[:1],name[:2],name[:3],name.replace(' ',''),name.upper(),' '+name+' '])
            if len(name)>1: search_terms.append(name[0]+' '+name[1:])
        for term in dict.fromkeys(search_terms): check('autocomplete','search_apt',(term,))
        for name,period,area,direct in itertools.product(names,periods,('84','59','all'),(False,True)):
            check('chart_raw','query_chart_from_db',(name,period,area,direct))
            check('chart_response','get_chart_data',(name,period,area,direct))
        years=sorted(set(range(2010,2027)) | {int(r[0]) for r in a.execute('SELECT DISTINCT deal_year FROM apt_rank_yearly_summary') if r[0] is not None})
        districts=[k for k in old['LAWD_CD_MAP'] if k!='대구전체']
        regions=list(old['LAWD_CD_MAP'])+['중구,수성구','','unknown']
        if full:
            regions+= [','.join(group) for k in range(2,len(districts)+1) for group in itertools.combinations(districts,k)]
        regions=list(dict.fromkeys(regions))
        result['ranking_years']=years; result['ranking_regions']=regions
        result['ranking_types']=list(rank_types or RANKS)
        for year,rank,region in itertools.product(years,rank_types or RANKS,regions):
            check('rankings_top50','get_rankings',(year,rank,region))
        # Representative real predicates: no assumption that OR/REPLACE uses name index.
        for label,c in (('before',a),('after',b)):
            result['plans'][label]={
             'max_date':c.execute('EXPLAIN QUERY PLAN SELECT MAX(deal_date) FROM apt_trades').fetchall(),
             'chart':c.execute("EXPLAIN QUERY PLAN SELECT deal_date,deal_amount,exclu_use_ar,floor FROM apt_trades WHERE (apt_name=? OR REPLACE(apt_name,' ','')=REPLACE(?,' ','')) AND deal_date>=? ORDER BY deal_date ASC",(names[0],names[0],'2020-01-01')).fetchall()}
        result['passed']=result.get('failure_count',0)==0
    except Exception as e:
        result['errors'].append({'kind':'structural/data/runner','error':type(e).__name__+': '+str(e)})
        result['passed']=False
    finally: a.close(); b.close()
    return result

def main_cli():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',required=True); p.add_argument('--after',required=True)
    p.add_argument('--main',required=True); p.add_argument('--report',required=True)
    p.add_argument('--full',action='store_true')
    p.add_argument('--names-limit',type=int,default=20)
    p.add_argument('--months',help='Comma-separated months; overrides default period matrix')
    p.add_argument('--rank-types',help='Optional subset. Excluded branches are NOT verified.')
    args=p.parse_args()
    if args.names_limit<2: p.error('--names-limit must be >= 2')
    if Path(args.report).exists(): p.error('Report already exists; use a new filename')
    periods=[int(x) for x in args.months.split(',')] if args.months else None
    if periods and any(x<=0 for x in periods): p.error('months must be positive')
    ranks=args.rank_types.split(',') if args.rank_types else None
    if ranks and set(ranks)-set(RANKS): p.error('Unknown rank type')
    r=verify(args.before,args.after,args.main,args.full,args.names_limit,periods,ranks)
    write_json(args.report,r)
    print(('PASS (tested inputs only)' if r['passed'] else 'FAIL')+' -> '+args.report)
    raise SystemExit(0 if r['passed'] else 1)

if __name__=='__main__': main_cli()
