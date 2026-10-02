"""Synthetic safety/regression tests. No production DB is used or changed."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from db_tools import snapshot, ro, compare_tables, extract_serving, drop_indexes
from verify_db import verify, load_app

ROOT=Path(__file__).resolve().parent

def fixture(path):
    c=sqlite3.connect(path)
    c.executescript((ROOT/'schema_reference.sql').read_text(encoding='utf-8'))
    names=['테스트자이','테스트 자이','한빛59','다른단지','NULL거래']
    for i,name in enumerate(names):
        for n in range(30):
            row=(name,'27110' if i%2 else '27260',f'2026-{1+n//28:02d}-{n%28+1:02d}',
                 40000+(n%5)*1000,84.0 if n%2 else 59.99,n%20+1,
                 [None,'직거래','중개거래'][n%3],None if n%2 else '대구 수성구')
            c.execute('INSERT INTO apt_trades VALUES (?,?,?,?,?,?,?,?)',row)
            if n==0: c.execute('INSERT INTO apt_trades VALUES (?,?,?,?,?,?,?,?)',row)
        c.execute('INSERT INTO apt_meta_master VALUES (?,?,?,?,?,?,?,?)',
                  (name,name.replace(' ',''),2010,'2010년','100세대','60세대','40세대','59/84'))
    # Sparse rowids must preserve traversal order across VACUUM, not renumber semantics.
    c.execute("INSERT INTO apt_trades(rowid,apt_name,lawd_cd,deal_date,deal_amount,exclu_use_ar,floor,deal_type) VALUES (9999,'테스트자이','27260','2026-02-01',12345,84,2,'직거래')")
    c.execute("INSERT INTO apt_cancelled_trades VALUES ('테스트자이','2026-01-01',40000,59.99,1)")
    # SQLite composite PRIMARY KEY permits NULLs here; preserve duplicates too.
    c.executemany('INSERT INTO apt_cancelled_trades VALUES (?,?,?,?,?)',[(None,None,None,None,None)]*2)
    for i in range(61):
        c.execute('INSERT INTO apt_rank_yearly_summary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (2026,f'랭킹{i:03d}','27260' if i%2 else '27110',30,15,15,
             5,4,2000,1500,5,4,3,2,'2026-01-01',84,34,10,5))
    c.execute("INSERT INTO _db_sync_touch VALUES (1,'2026-09-27')")
    c.commit(); c.close()

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
        self.source=self.base/'original.db'; fixture(self.source)
        self.digest=hashlib.sha256(self.source.read_bytes()).hexdigest()
    def tearDown(self):
        self.assertEqual(self.digest,hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.tmp.cleanup()
    def run_cli(self,script,output,*extra):
        return subprocess.run([sys.executable,str(ROOT/script),'--source',str(self.source),
            '--output',str(output),'--main',str(ROOT/'main.py'),*extra],capture_output=True,text=True)
    def test_compact_and_serving_publish(self):
        for script in ('optimize_db.py','build_serving_db.py'):
            target=self.base/(script+'.db')
            r=self.run_cli(script,target)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertTrue(target.exists())
            report=json.loads(Path(str(target)+'.run/report.json').read_text(encoding='utf-8'))
            self.assertTrue(report['verification']['passed'])
            if script=='build_serving_db.py':
                self.assertFalse(report['attempts'][0]['verification']['passed'])
                self.assertIn(report['selected_profile'],('compact','preserve'))
            c=ro(target)
            self.assertEqual(c.execute('SELECT count(*) FROM apt_cancelled_trades').fetchone()[0],3)
            self.assertEqual(c.execute("SELECT count(*) FROM apt_trades WHERE deal_type='직거래'").fetchone()[0],51)
            c.close()
    def test_original_bug_is_not_a_false_pass(self):
        app=load_app(ROOT/'main_original.py',self.source)
        with self.assertRaises(KeyError): app['get_rankings'](2026,'pyeong_avg','대구전체')
        patched=load_app(ROOT/'main.py',self.source)
        self.assertEqual(len(patched['get_rankings'](2026,'pyeong_avg','대구전체')),50)
        # Existing successful endpoint branches retain identical values.
        for rank in ('price_max','84_max','84_avg','59_max','59_avg','trade_cnt'):
            self.assertEqual(app['get_rankings'](2026,rank,'대구전체'),patched['get_rankings'](2026,rank,'대구전체'))
    def test_budget_failure_not_published(self):
        target=self.base/'small.db'
        r=self.run_cli('build_serving_db.py',target,'--max-mb','0.001')
        self.assertNotEqual(r.returncode,0); self.assertFalse(target.exists())
        self.assertIn('File exceeds requested --max-mb',r.stdout)
        self.assertTrue(Path(str(target)+'.run/baseline.db').exists())
    def test_value_mutation_detected(self):
        target=self.base/'mutated.db'; snapshot(self.source,target)
        c=sqlite3.connect(target); c.execute('UPDATE apt_trades SET deal_amount=deal_amount+1 WHERE rowid=1'); c.commit(); c.close()
        a,b=ro(self.source),ro(target)
        try:
            with self.assertRaises(AssertionError): compare_tables(a,b,['apt_trades'])
        finally: a.close(); b.close()
    def test_cancelled_value_mutation_detected(self):
        target=self.base/'cancelled_mutated.db'; snapshot(self.source,target)
        c=sqlite3.connect(target); c.execute("UPDATE apt_cancelled_trades SET deal_amount=98765 WHERE apt_name IS NOT NULL"); c.commit(); c.close()
        a,b=ro(self.source),ro(target)
        try:
            with self.assertRaises(AssertionError): compare_tables(a,b,['apt_cancelled_trades'])
        finally: a.close(); b.close()
    def test_existing_output_never_overwritten(self):
        target=self.base/'keep.db'; target.write_bytes(b'DO NOT OVERWRITE')
        r=self.run_cli('optimize_db.py',target)
        self.assertNotEqual(r.returncode,0); self.assertEqual(target.read_bytes(),b'DO NOT OVERWRITE')
    def test_unknown_tables_fail_closed(self):
        expanded=self.base/'expanded.db'; snapshot(self.source,expanded)
        c=sqlite3.connect(expanded); c.execute('CREATE TABLE apt_rents(id INTEGER PRIMARY KEY AUTOINCREMENT, deposit, cancel_date TEXT)'); c.execute("INSERT INTO apt_rents VALUES (1,'10000','2026-01-01')"); c.execute("UPDATE sqlite_sequence SET seq=100 WHERE name='apt_rents'"); c.commit(); c.close()
        with self.assertRaises(RuntimeError): extract_serving(expanded,self.base/'refused.db',[])
        target=self.base/'expanded_serving.db'; extract_serving(expanded,target,['apt_rents'])
        a,b=ro(expanded),ro(target)
        try:
            compare_tables(a,b,['apt_rents'])
            self.assertEqual(b.execute("SELECT seq FROM sqlite_sequence WHERE name='apt_rents'").fetchone()[0],100)
        finally: a.close(); b.close()
    def test_unique_named_index_never_dropped(self):
        target=self.base/'index.db'; snapshot(self.source,target)
        c=sqlite3.connect(target)
        c.execute('DROP INDEX idx_apt_trades_agent')
        c.execute('CREATE UNIQUE INDEX idx_apt_trades_agent ON apt_meta_master(apt_name)')
        with self.assertRaises(RuntimeError): drop_indexes(c,'serving')
        c.close()
    def test_backup_wal_and_statistics(self):
        live=self.base/'wal.db'; snapshot(self.source,live)
        c=sqlite3.connect(live); c.execute('PRAGMA journal_mode=WAL'); c.execute('ANALYZE')
        c.execute("INSERT INTO _db_sync_touch VALUES (2,'WAL committed')"); c.commit()
        frozen=self.base/'frozen.db'; snapshot(live,frozen); c.close()
        served=self.base/'stats.db'; extract_serving(frozen,served,[])
        a,b=ro(frozen),ro(served)
        try:
            compare_tables(a,b,['_db_sync_touch'])
            self.assertEqual(a.execute('SELECT * FROM sqlite_stat1 ORDER BY 1,2').fetchall(),b.execute('SELECT * FROM sqlite_stat1 ORDER BY 1,2').fetchall())
        finally: a.close(); b.close()

if __name__=='__main__': unittest.main(verbosity=2)
