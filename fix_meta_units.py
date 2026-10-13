import sqlite3
import re

conn = sqlite3.connect("apt_data_render_master.db", timeout=10.0)
c = conn.cursor()

# 1. 대상 단지 조회
rows = c.execute("SELECT rowid, apt_name, units_str, units_84_str, type_info FROM apt_meta_master WHERE type_info IS NOT NULL AND type_info != '전용 정보 확인중'").fetchall()

fixed_count = 0

for rowid, apt_name, u_str, u84_str, t_info in rows:
    try:
        curr_total = int(re.sub(r'[^\d]', '', u_str)) if (u_str and re.search(r'\d+', u_str)) else 0
    except:
        curr_total = 0
        
    # type_info 내 모든 타입별 세대수 합산
    type_units = [int(num) for num in re.findall(r'\((\d+)세대\)', t_info)]
    if not type_units:
        continue
    sum_types = sum(type_units)
    
    # 84/85타입 세대수 정밀 재추출
    matches_84 = re.findall(r'(8[45]㎡)\((\d+)세대\)', t_info)
    calc_84 = sum(int(m[1]) for m in matches_84) if matches_84 else 0
    
    # 전체 세대수가 50세대 미만(동 수 오류)인데 타입 합계가 100세대 이상이거나,
    # 국평이 전체 세대수를 초과하는 경우
    if (curr_total < 50 and sum_types >= 100) or (curr_total > 0 and sum_types > curr_total * 1.5):
        new_total_str = f"{sum_types:,}세대"
        new_84_str = f"{calc_84:,}세대" if calc_84 > 0 else "-"
        
        c.execute("""
            UPDATE apt_meta_master 
            SET units_str = ?, units_84_str = ?
            WHERE rowid = ?
        """, (new_total_str, new_84_str, rowid))
        fixed_count += 1
        print(f"[{fixed_count}] {apt_name}: 전체 {u_str} -> {new_total_str} | 국평 {u84_str} -> {new_84_str}")

conn.commit()
conn.close()

print(f"\n 총 {fixed_count}개 단지의 전체 세대수 및 국평 세대수 정상 보정 완료!")
