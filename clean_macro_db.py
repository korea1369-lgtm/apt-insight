import sqlite3

conn = sqlite3.connect("apt_data_render_master.db")
c = conn.cursor()

# 4자리 연도 데이터('2016', '2017' 등) 삭제 (하이픈 '-'이 없는 행)
deleted = c.execute("DELETE FROM macro_regional_indicators WHERE deal_ym NOT LIKE '%-%'").rowcount
conn.commit()

remaining = c.execute("SELECT COUNT(*) FROM macro_regional_indicators").fetchone()[0]
conn.close()

print(f"✔ 연간 중복 찌꺼기 {deleted}건 삭제 완료!")
print(f"✔ 남은 순수 월별(YYYY-MM) 행: {remaining:,}건")
