import sqlite3

conn = sqlite3.connect("apt_data_render_master.db", timeout=10.0)
c = conn.cursor()

# 범어에일린의뜰 국평 세대수를 정확한 174세대로 보정
c.execute("""
    UPDATE apt_meta_master 
    SET units_84_str = '174세대' 
    WHERE norm_name LIKE '%범어에일린%' OR apt_name LIKE '%범어에일린%'
""")
conn.commit()
print("수정 완료! 반영된 행 수:", c.rowcount)

# 수정 결과 확인
row = c.execute("SELECT apt_name, units_str, units_84_str FROM apt_meta_master WHERE norm_name LIKE '%범어에일린%'").fetchone()
print("보정된 결과 -> 단지명:", row[0], "/ 전체:", row[1], "/ 국평(84):", row[2])

conn.close()
