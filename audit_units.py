import sqlite3
import re

conn = sqlite3.connect("apt_data_render_master.db", timeout=5.0)
c = conn.cursor()

# 1. apt_meta_master 전체 단지 조회
rows = c.execute("SELECT apt_name, units_str, units_84_str, type_info FROM apt_meta_master").fetchall()

suspicious_cases = []

for apt_name, u_str, u84_str, t_info in rows:
    if not t_info or t_info == "전용 정보 확인중":
        continue
    
    # type_info에서 (84|85)㎡ 패턴 추출: 예: 85㎡(127세대)
    matches = re.findall(r'(8[45]㎡)\((\d+)세대\)', t_info)
    
    # 84~85㎡ 항목이 2개 이상 쪼개져 있는 단지들 중 의심 사례 수집
    if len(matches) >= 2:
        total_matched_units = sum(int(m[1]) for m in matches)
        current_84_val = int(re.sub(r'[^\d]', '', u84_str)) if (u84_str and re.search(r'\d+', u84_str)) else 0
        total_units = int(re.sub(r'[^\d]', '', u_str)) if (u_str and re.search(r'\d+', u_str)) else 0
        
        # 합산 세대수가 전체 세대수의 80%를 넘거나, 개별 타입 간 격차가 큰 경우 등
        detail_breakdown = " + ".join([f"{m[1]}세대" for m in matches])
        suspicious_cases.append({
            "name": apt_name,
            "total": u_str,
            "current_84": u84_str,
            "detail": detail_breakdown,
            "sum": total_matched_units,
            "raw": t_info
        })

conn.close()

print(f"=== 전용 84/85㎡ 타입이 2개 이상 나뉘어 합산된 의심 단지: 총 {len(suspicious_cases)}개 ===")
for idx, item in enumerate(suspicious_cases[:30], 1):  # 우선 상위 30개 출력
    print(f"[{idx}] {item['name']}")
    print(f"    - 전체: {item['total']} | 현재 국평표기: {item['current_84']}")
    print(f"    - 분할 구성: {item['detail']} = 합계 {item['sum']}세대")
    print(f"    - 원본: {item['raw'][:80]}...")
    print("-" * 50)
