import sqlite3

conn = sqlite3.connect('apt_data_render_master.db')
cur = conn.cursor()

print("🔍 로컬 DB(apt_data_render_master.db)에서 범어W 2025-12-30 거래 확인 중...")
cur.execute("""
    SELECT deal_date, apt_name, deal_amount, exclu_use_ar, floor 
    FROM apt_trades 
    WHERE deal_date = '2025-12-30' AND (apt_name LIKE '%범어W%' OR apt_name LIKE '%수성범어W%');
""")
rows = cur.fetchall()
print(f"발견된 거래: {rows}")

if rows:
    print("🗑️ 해당 거래 즉시 강제 삭제 실행...")
    cur.execute("""
        DELETE FROM apt_trades 
        WHERE deal_date = '2025-12-30' AND (apt_name LIKE '%범어W%' OR apt_name LIKE '%수성범어W%');
    """)
    conn.commit()
    print(f"✅ 로컬 DB에서 {cur.rowcount}건 삭제 완료!")
    cur.execute("VACUUM;")
else:
    print("✨ 로컬 DB에는 해당 거래가 이미 없습니다! (GitHub 푸시 또는 Render 캐시 문제)")

conn.close()
