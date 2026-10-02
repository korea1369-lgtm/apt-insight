import sqlite3

conn = sqlite3.connect("apt_data_render_master.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("\n📦 현재 DB에 존재하는 테이블 목록:")
for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cur.fetchone()[0]
    print(f" - {t} (데이터: {cnt:,}건)")
conn.close()
