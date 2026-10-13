import sqlite3
import re

conn = sqlite3.connect("apt_data_render_master.db", timeout=5.0)
c = conn.cursor()

rows = c.execute("SELECT apt_name, units_str, units_84_str, type_info FROM apt_meta_master").fetchall()

anomalies = []

for apt_name, u_str, u84_str, t_info in rows:
    if not t_info or t_info == "전용 정보 확인중":
        continue
    
    matches = re.findall(r'(8[45]㎡)\((\d+)세대\)', t_info)
    if len(matches) >= 2:
        try:
            total_u = int(re.sub(r'[^\d]', '', u_str))
            u84 = int(re.sub(r'[^\d]', '', u84_str))
        except:
            continue
            
        ratio = (u84 / total_u) * 100 if total_u > 0 else 0
        
        # 1. 국평 비율이 90%가 넘는데 분할 타입이 3개 이상인 경우 (범어에일린의뜰 유형)
        # 2. 또는 type_info에 59/60㎡가 없는데 85㎡가 여러 개 쪼개져 있는 경우 (공급 85=전용 59 의심)
        has_59 = bool(re.search(r'(59|60)㎡', t_info))
        
        if not has_59 and len(matches) >= 2:
            anomalies.append((apt_name, total_u, u84, f"{ratio:.1f}%", "소형(59) 부재 및 85 중복(공급혼선 의심)", t_info[:100]))
        elif ratio > 95 and total_u > 300:
            anomalies.append((apt_name, total_u, u84, f"{ratio:.1f}%", "국평 비율 95% 초과 이상치", t_info[:100]))

conn.close()

print(f"=== 정밀 점검 대상 의심 단지: {len(anomalies)}개 ===")
for a in anomalies[:20]:
    print(f"단지명: {a[0]} | 전체: {a[1]}세대 | 국평: {a[2]}세대 ({a[3]}) | 사유: {a[4]}")
    print(f"  원본: {a[5]}")
    print("-" * 50)
