import sqlite3
import os
import sys

print("1. 스크립트 시작됨...")
db_path = os.path.abspath("apt_data_render_master.db")
print("DB 경로:", db_path)

if not os.path.exists(db_path):
    print("❌ 오류: apt_data_render_master.db 파일이 현재 폴더에 없습니다!")
    sys.exit()

# timeout 3초 설정 및 읽기 전용 모드
try:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=3.0)
    c = conn.cursor()
    print("2. DB 연결 성공!")

    # apt_meta_master 검색
    c.execute("SELECT apt_name, units_str, units_84_str, type_info FROM apt_meta_master WHERE apt_name LIKE '%에일린%' OR norm_name LIKE '%에일린%'")
    rows = c.fetchall()
    print(f"3. apt_meta_master 검색 건수: {len(rows)}")
    for r in rows:
        print("  - 단지명:", r[0])
        print("  - 전체세대:", r[1])
        print("  - 국평세대(84):", r[2])
        print("  - 타입정보:", r[3])

    # apt_rank_yearly_summary 검색
    c.execute("SELECT apt_name, deal_year, max_84_price FROM apt_rank_yearly_summary WHERE apt_name LIKE '%에일린%' LIMIT 5")
    rank_rows = c.fetchall()
    print(f"4. 랭킹 요약 건수: {len(rank_rows)}")
    for r in rank_rows:
        print("  -", r)

    conn.close()
    print("5. 조회 완료!")
except Exception as e:
    print("❌ 에러 발생:", e)
