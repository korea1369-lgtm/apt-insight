"""Lossless SQLite tooling. Source connections are read-only. Python 3.10+."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import time

CORE = ('apt_trades', 'apt_cancelled_trades', 'apt_meta_master',
        'apt_rank_yearly_summary', '_db_sync_touch')
EXPECTED = {
 'idx_trade_name': ('apt_trades', ['apt_name']),
 'idx_trades_lookup': ('apt_trades', ['apt_name','deal_date','deal_amount','exclu_use_ar','floor']),
 'idx_apt_trades_deal_type': ('apt_trades', ['deal_type']),
 'idx_apt_trades_agent': ('apt_trades', ['estate_agent_sgg_nm']),
}
PROFILES = {
 'preserve': (),
 'compact': ('idx_trade_name','idx_apt_trades_deal_type','idx_apt_trades_agent'),
 'serving': ('idx_trades_lookup','idx_apt_trades_deal_type','idx_apt_trades_agent'),
}

def qi(name):
    return '"' + name.replace('"', '""') + '"'

def ro(path):
    p = Path(path).resolve(strict=True)
    c = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True, timeout=30)
    c.execute('PRAGMA query_only=ON')
    c.execute('PRAGMA cache_size=-8192')
    c.execute('PRAGMA temp_store=FILE')
    return c

def user_tables(c):
    return [r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

def integrity(c):
    result = [r[0] for r in c.execute('PRAGMA integrity_check')]
    if result != ['ok']:
        raise RuntimeError('integrity_check failed: ' + repr(result[:10]))
    violations = c.execute('PRAGMA foreign_key_check').fetchmany(10)
    if violations:
        raise RuntimeError('Foreign key violations: ' + repr(violations))

def snapshot(source, target, seconds=3600):
    target = Path(target)
    with target.open('xb'):
        pass
    a, b = ro(source), sqlite3.connect(target)
    started = time.monotonic()
    def progress(status, remaining, total):
        if time.monotonic() - started > seconds:
            raise TimeoutError('Backup exceeded time limit; stop the collector and retry.')
    try:
        a.backup(b, pages=2048, progress=progress, sleep=0.05)
        b.execute('PRAGMA journal_mode=DELETE')
        integrity(b)
    finally:
        a.close()
        b.close()

def row_stream(c, table):
    info = list(c.execute(f'PRAGMA table_xinfo({qi(table)})'))
    ddl = c.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone()[0]
    names = [r[1].lower() for r in info]
    if 'WITHOUT ROWID' in ddl.upper():
        order = ','.join(qi(r[1]) for r in sorted(info, key=lambda r:r[5]) if r[5])
    else:
        order = next((x for x in ('_rowid_', 'rowid', 'oid') if x not in names), None)
        if order is None:
            raise RuntimeError(f'{table}: all hidden rowid aliases shadowed; explicit support needed.')
    # Hidden rowid numbers may change under VACUUM; declared column values and
    # their rowid traversal order must stay identical, including duplicates.
    return c.execute(f'SELECT * FROM {qi(table)} ORDER BY {order}')

def encode_row(row):
    out = bytearray()
    for v in row:
        if v is None: tag, payload = b'N', b''
        elif isinstance(v, int): tag, payload = b'I', str(v).encode()
        elif isinstance(v, float): tag, payload = b'F', struct.pack('>d', v)
        elif isinstance(v, str): tag, payload = b'T', v.encode('utf-8')
        elif isinstance(v, bytes): tag, payload = b'B', v
        else: raise TypeError(type(v))
        out += tag + len(payload).to_bytes(8, 'big') + payload
    return bytes(out)

def compare_tables(a, b, tables):
    result = {}
    for table in tables:
        sa = list(a.execute(f'PRAGMA table_xinfo({qi(table)})'))
        sb = list(b.execute(f'PRAGMA table_xinfo({qi(table)})'))
        if sa != sb:
            raise AssertionError(f'{table}: column/type/default/PK schema differs')
        ca, cb = row_stream(a, table), row_stream(b, table)
        count, digest = 0, hashlib.sha256()
        while True:
            ra, rb = ca.fetchmany(2048), cb.fetchmany(2048)
            if len(ra) != len(rb):
                raise AssertionError(f'{table}: row count differs near {count}')
            if not ra: break
            for x, y in zip(ra, rb):
                bx, by = encode_row(x), encode_row(y)
                if bx != by:
                    raise AssertionError(f'{table}: value/type/order differs at row {count + 1}')
                digest.update(len(bx).to_bytes(8,'big')); digest.update(bx)
                count += 1
        result[table] = {'rows':count, 'sha256':digest.hexdigest(), 'exact_stream_equal':True}
        print(f'  DATA OK {table}: {count:,} rows', flush=True)
    return result

def inspect_db(path):
    c = ro(path)
    try:
        page_size = c.execute('PRAGMA page_size').fetchone()[0]
        pages = c.execute('PRAGMA page_count').fetchone()[0]
        free = c.execute('PRAGMA freelist_count').fetchone()[0]
        result = {'file_bytes':Path(path).stat().st_size, 'logical_bytes':page_size*pages,
                  'page_size':page_size, 'page_count':pages, 'freelist_bytes':page_size*free,
                  'sqlite_version':sqlite3.sqlite_version}
        try:
            result['objects'] = {r[0]:{'bytes':r[1], 'unused_bytes':r[2], 'payload_bytes':r[3]}
                for r in c.execute('SELECT name,SUM(pgsize),SUM(unused),SUM(payload) FROM dbstat GROUP BY name')}
            result['dbstat_available'] = True
        except sqlite3.OperationalError as e:
            result['dbstat_available'] = False
            result['dbstat_note'] = str(e)
        result['tables'] = {}
        for table in user_tables(c):
            result['tables'][table] = {
                'rows':c.execute(f'SELECT count(*) FROM {qi(table)}').fetchone()[0],
                'columns':list(c.execute(f'PRAGMA table_xinfo({qi(table)})')),
                'indexes':list(c.execute(f'PRAGMA index_list({qi(table)})'))}
        if 'apt_trades' in result['tables']:
            result['storage_types'] = {col:list(c.execute(f'SELECT typeof({qi(col)}),count(*) FROM apt_trades GROUP BY typeof({qi(col)})')) for col in ('deal_amount','exclu_use_ar','floor','deal_date')}
            result['deal_type_counts'] = list(c.execute('SELECT deal_type,typeof(deal_type),count(*) FROM apt_trades GROUP BY deal_type,typeof(deal_type)'))
            result['apt_name_whitespace_rows'] = c.execute("SELECT count(*) FROM apt_trades WHERE apt_name != trim(apt_name)").fetchone()[0]
        return result
    finally: c.close()

def validate_index(c, name):
    row = c.execute("SELECT tbl_name FROM sqlite_schema WHERE type='index' AND name=?", (name,)).fetchone()
    if row is None: return False
    table, columns = EXPECTED[name]
    metadata = next(r for r in c.execute(f'PRAGMA index_list({qi(row[0])})') if r[1] == name)
    xinfo = list(c.execute(f'PRAGMA index_xinfo({qi(name)})'))
    keys = [r for r in xinfo if r[5]]
    if (row[0] != table or metadata[2] or metadata[3] != 'c' or metadata[4]
        or [r[2] for r in keys] != columns
        or any(r[3] != 0 or r[4] != 'BINARY' for r in keys)):
        raise RuntimeError(f'Unexpected index definition; refusing to change {name}')
    return True

def drop_indexes(c, profile):
    if profile == 'compact' and not validate_index(c, 'idx_trades_lookup'):
        raise RuntimeError('compact requires the original idx_trades_lookup')
    if profile == 'serving' and not validate_index(c, 'idx_trade_name'):
        raise RuntimeError('serving requires the original idx_trade_name')
    dropped = []
    for name in PROFILES[profile]:
        if validate_index(c, name):
            c.execute(f'DROP INDEX {qi(name)}')
            dropped.append(name)
    c.commit()
    return dropped

def extract_serving(source, target, extras):
    a = ro(source)
    b = None
    try:
        tables = user_tables(a)
        missing = set(CORE) - set(tables)
        if missing: raise RuntimeError('Missing required tables: ' + repr(sorted(missing)))
        unknown = set(tables) - set(CORE) - set(extras)
        if unknown:
            raise RuntimeError('Unclassified tables: ' + repr(sorted(unknown)) +
                '. Preserve them explicitly with repeated --extra-table NAME; no silent omissions.')
        if set(extras) - set(tables): raise RuntimeError('Unknown --extra-table name')
        # Retain every classified table. No geographic/date filters, no projection,
        # no deduplication. New raw tables must never disappear silently.
        with Path(target).open('xb'): pass
        b = sqlite3.connect(target)
        b.execute('PRAGMA journal_mode=DELETE')
        b.execute('PRAGMA temp_store=FILE')
        b.execute('PRAGMA cache_size=-8192')
        b.execute(f'PRAGMA page_size={a.execute("PRAGMA page_size").fetchone()[0]}')
        encoding = a.execute('PRAGMA encoding').fetchone()[0]
        b.execute("PRAGMA encoding='" + encoding + "'")
        for pragma in ('application_id','user_version'):
            b.execute(f'PRAGMA {pragma}={a.execute("PRAGMA "+pragma).fetchone()[0]}')
        for table in tables:
            ddl = a.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name=?",(table,)).fetchone()[0]
            if 'VIRTUAL TABLE' in ddl.upper():
                raise RuntimeError('Virtual table needs a specialized exporter: ' + table)
            b.execute(ddl)
            info = list(a.execute(f'PRAGMA table_xinfo({qi(table)})'))
            columns = [r[1] for r in info if r[6] == 0]
            selected = ','.join(map(qi,columns))
            if 'WITHOUT ROWID' not in ddl.upper():
                alias = next((x for x in ('_rowid_','rowid','oid') if x not in [n.lower() for n in columns]), None)
                if alias is None: raise RuntimeError('Shadowed rowid aliases: ' + table)
                selected = alias + ',' + selected
            cursor = a.execute(f'SELECT {selected} FROM {qi(table)}')
            insert = f'INSERT INTO {qi(table)} ({selected}) VALUES ({",".join("?" for _ in cursor.description)})'
            while True:
                batch = cursor.fetchmany(2048)
                if not batch: break
                b.executemany(insert, batch)
            b.commit()
        # Unknown custom indexes, triggers and views are preserved conservatively.
        # Built-in PK/UNIQUE indexes are already created by the original table DDL.
        for kind in ('index','view','trigger'):
            for (ddl,) in a.execute('SELECT sql FROM sqlite_schema WHERE type=? AND sql IS NOT NULL ORDER BY rowid',(kind,)):
                b.execute(ddl)
        # Preserve AUTOINCREMENT high watermarks, including values above max(id).
        if a.execute("SELECT 1 FROM sqlite_schema WHERE name='sqlite_sequence'").fetchone():
            for name, seq in a.execute('SELECT name,seq FROM sqlite_sequence'):
                if b.execute('SELECT 1 FROM sqlite_sequence WHERE name=?',(name,)).fetchone():
                    b.execute('UPDATE sqlite_sequence SET seq=? WHERE name=?',(seq,name))
                else: b.execute('INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)',(name,seq))
        # Preserve planner statistics until explicit future tuning; ANALYZE can
        # change tie ordering even when column values are unchanged.
        stats = [r[0] for r in a.execute("SELECT name FROM sqlite_schema WHERE name IN ('sqlite_stat1','sqlite_stat4')")]
        if stats:
            b.execute('ANALYZE sqlite_schema')
            for table in stats:
                if not b.execute('SELECT 1 FROM sqlite_schema WHERE name=?',(table,)).fetchone():
                    raise RuntimeError('Source planner stats unsupported by this SQLite build: '+table)
                if b.execute(f'SELECT count(*) FROM {qi(table)}').fetchone()[0]:
                    raise RuntimeError('Expected empty statistics before copy')
                cursor=a.execute(f'SELECT * FROM {qi(table)}')
                insert=f'INSERT INTO {qi(table)} VALUES ({",".join("?" for _ in cursor.description)})'
                while True:
                    batch=cursor.fetchmany(2048)
                    if not batch: break
                    b.executemany(insert,batch)
        b.commit()
    finally:
        a.close()
        if b is not None: b.close()

def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

def publish(stage, output):
    # Atomic, no-clobber publication on the same filesystem (NTFS/ext4).
    with Path(stage).open('r+b') as f: os.fsync(f.fileno())
    os.link(stage, output)
    Path(stage).unlink()

def pipeline(kind):
    p = argparse.ArgumentParser(description='Read-only source -> verified, new SQLite file (never overwrite).')
    p.add_argument('--source',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--main',help='main.py used to execute real DB endpoint functions')
    p.add_argument('--profile',choices=PROFILES,default='compact' if kind=='optimize' else 'serving')
    p.add_argument('--extra-table',action='append',default=[])
    p.add_argument('--backup-only',action='store_true')
    p.add_argument('--inspect-only',action='store_true')
    p.add_argument('--full',action='store_true',help='Every cached name and every UI period/region combination; potentially very slow')
    p.add_argument('--max-mb',type=float,default=None,help='Optional hard file-size budget, decimal MB; NOT Render RAM')
    args = p.parse_args()
    source, output = Path(args.source).resolve(strict=True), Path(args.output).resolve()
    if source == output or output.exists(): p.error('Output must be a NEW path, different from source.')
    if args.max_mb is not None and args.max_mb <= 0: p.error('--max-mb must be positive')
    if not (args.backup_only or args.inspect_only) and not args.main: p.error('--main is required for endpoint verification')
    output.parent.mkdir(parents=True,exist_ok=True)
    run = Path(str(output)+'.run')
    run.mkdir()  # fail on existing evidence; never overwrite a previous run
    baseline, stage = run/'baseline.db', run/'candidate.db'
    report = {'status':'RUNNING', 'source':str(source), 'output':str(output),
              'kind':kind, 'profile':args.profile, 'baseline':str(baseline)}
    try:
        print('Creating a consistent backup (source is read-only)...',flush=True)
        snapshot(source,baseline)
        report['before'] = inspect_db(baseline)
        objects = report['before'].get('objects',{})
        estimated = sum(objects.get(n,{}).get('bytes',0) for n in PROFILES[args.profile])
        report['capacity_estimate'] = {
            'freelist_bytes':report['before']['freelist_bytes'],
            'candidate_index_bytes':estimated if objects else None,
            'formula':'freelist + measured removable index pages + reclaimable slack; final size must be measured',
            'no_fixed_reduction_guarantee':True,
            'estimated_MB_before_slack_repack':
                (report['before']['file_bytes']-report['before']['freelist_bytes']-estimated)/1e6 if objects else None,
            'user_table_payload_lower_bound_MB':
                sum(objects.get(n,{}).get('payload_bytes',0) for n in report['before']['tables'])/1e6 if objects else None}

        if args.inspect_only:
            report['status']='INSPECTED'; write_json(run/'report.json',report)
            print('Inspection saved to '+str(run/'report.json')); return
        if args.backup_only:
            publish(baseline,output)
            report['status']='BACKUP_CREATED'; report['baseline']=str(output)
            write_json(run/'report.json',report); print('Backup: '+str(output)); return
        from verify_db import verify
        profiles = {'serving':['serving','compact','preserve'],
                    'compact':['compact','preserve'], 'preserve':['preserve']}[args.profile]
        report['attempts']=[]
        for profile in profiles:
            print('Building index profile: '+profile,flush=True)
            if kind=='serving': extract_serving(baseline,stage,args.extra_table)
            else: snapshot(baseline,stage)
            c = sqlite3.connect(stage)
            try:
                c.execute('PRAGMA cache_size=-8192'); c.execute('PRAGMA temp_store=FILE')
                dropped=drop_indexes(c,profile)
                c.execute('VACUUM')
                integrity(c)
            finally: c.close()
            verification=verify(baseline,stage,args.main,full=args.full)
            report['attempts'].append({'profile':profile, 'dropped_indexes':dropped,
                                       'verification':verification, 'file_bytes':stage.stat().st_size})
            if verification['passed']:
                report['selected_profile']=profile
                report['dropped_indexes']=dropped
                report['verification']=verification
                break
            rejected=run/('rejected_'+profile+'.db')
            stage.rename(rejected)
            print('Candidate rejected; retained as '+str(rejected),flush=True)
        else:
            raise RuntimeError('All profiles failed verification. No candidate published.')
        report['after']=inspect_db(stage)
        report['saved_MB']=(report['before']['file_bytes']-report['after']['file_bytes'])/1e6
        report['output_MB']=report['after']['file_bytes']/1e6
        if args.max_mb is not None and report['output_MB'] > args.max_mb:
            raise RuntimeError('File exceeds requested --max-mb. No rows will be removed to force the budget.')
        publish(stage,output)
        report['status']='PASS_FOR_TESTED_CASES'
        write_json(run/'report.json',report)
        print(f'Published {output}: {report["output_MB"]:.2f} MB; saved {report["saved_MB"]:.2f} MB',flush=True)
    except Exception as e:
        report['status']='FAILED'; report['error']=f'{type(e).__name__}: {e}'
        write_json(run/'report.json',report)
        print('FAILED: '+report['error']+'\nEvidence: '+str(run),flush=True)
        raise SystemExit(1)
