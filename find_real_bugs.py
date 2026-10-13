import sqlite3
import re

conn = sqlite3.connect("apt_data_render_master.db", timeout=5.0)
c = conn.cursor()

rows = c.execute("SELECT apt_name, units_str, units_84_str, type_info FROM apt_meta_master").fetchall()

real_bugs = []

for apt_name, u_str, u84_str, t_info in rows:
    if not t_info or t_info == "전용 정보 확인중":
        continue
    
    try:
        total_u = int(re.sub(r'[^\d]', '', u_str))
        u84 = int(re.sub(r'[^\d]', '', u84_str)) if (u84_str and re.search(r'\d+', u84_str)) else 0
    except:
        continue
        
    if total_u == 0:
        continue

    # type_info 내 모든 세대수 합산
    all_type_units = sum(int(num) for num in re.findall(r'\((\d+)세대\)', t_info))
    
    # 1. 국평 세대수가 전체 세대수보다 큰 명백한 버그
    # 2. type_info 전체 합산이 단지 총 세대수보다 15% 이상 크게 부풀려진 경우
    if u84 > total_u or (all_type_units > total_u * 1.15 and all_type_units - total_u > 50):
        real_bugs.append((apt_name, total_u, u84, all_type_units, t_info))

conn.close()

print(f"=== 진짜 데이터 오류 의심 단지: 총 {len(real_bugs)}개 ===")
for b in real_bugs[:30]:
    print(f"단지명: {b[0]} | 전체 세대: {b[1]} | 국평 표기: {b[2]} | 타입합계: {b[3]}")
    print(f"  원본: {b[4][:100]}...")
    print("-" * 50)
