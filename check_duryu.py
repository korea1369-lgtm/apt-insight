import sqlite3

conn = sqlite3.connect("apt_data_render_master.db")
c = conn.cursor()

print("=== 1. '스타힐스' 포함 단지 거래 검색 ===")
rows = c.execute("SELECT apt_name, deal_date, deal_amount, exclu_use_ar, floor, deal_type FROM apt_trades WHERE apt_name LIKE '%스타힐스%' ORDER BY deal_date DESC LIMIT 10").fetchall()
for r in rows:
    print(r)

print("\n=== 2. '두류' 포함 8억 이상 2026년 거래 검색 ===")
rows2 = c.execute("SELECT apt_name, deal_date, deal_amount, exclu_use_ar, floor FROM apt_trades WHERE apt_name LIKE '%두류%' AND deal_amount >= 80000 AND deal_date >= '2026-01-01' ORDER BY deal_date DESC LIMIT 10").fetchall()
for r in rows2:
    print(r)

conn.close()
