import sqlite3
import json
import urllib.request
import urllib.parse

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="

def clean_region(raw_name):
    if not raw_name: return ""
    name = raw_name.strip()
    for reg in ["서울", "경기", "인천", "대구", "부산", "광주", "대전", "울산", "세종", 
                "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "전국"]:
        if name.startswith(reg):
            return reg
    return ""

def fetch_monthly_permits():
    print("\n--- KOSIS 월별 주택건설 인허가실적(DT_MLTM_1946) 수집 ---")
    url = (
        "https://kosis.kr/openapi/Param/statisticsParameterData.do?"
        f"method=getList&apiKey={KOSIS_KEY}"
        "&itmId=ALL&objL1=ALL&objL2=ALL&format=json&jsonVD=Y"
        "&prdSe=M&startPrdDe=201801&endPrdDe=202608"
        "&orgId=116&tblId=DT_MLTM_1946"
    )
    records = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                print(f"✔ 월별 인허가 원시 데이터 수신 성공: {len(data):,}건")
                for r in data:
                    reg = clean_region(r.get("C1_NM", ""))
                    gubun = r.get("C2_NM", "").strip()
                    ym = r.get("PRD_DE", "")
                    val = r.get("DT", "")
                    
                    # '계' 또는 '총계' 부문 데이터만 선택 (민간/공공 중복 방지)
                    if reg and ym and val and ("계" in gubun or not gubun):
                        try:
                            cnt = int(float(val))
                            formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                            records.append((formatted_ym, reg, cnt))
                        except:
                            continue
            else:
                print("⚠ KOSIS 응답 내용:", data)
    except Exception as e:
        print("❌ KOSIS 호출 오류:", e)
        
    print(f"✔ 유효 월간 인허가 데이터 정제 완료: {len(records):,}건")
    return records

def update_db(records):
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    c = conn.cursor()
    c.executemany("""
        INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
        VALUES (?, ?, ?)
        ON CONFLICT(deal_ym, region_name) DO UPDATE SET
            permit_count = excluded.permit_count,
            updated_at = CURRENT_TIMESTAMP
    """, records)
    conn.commit()
    
    print("\n=== 최근 3개월 대구, 부산, 서울, 경기, 세종 최종 현황 ===")
    sample = c.execute("""
        SELECT deal_ym, region_name, permit_count, jeonse_ratio 
        FROM macro_regional_indicators 
        WHERE region_name IN ('대구', '부산', '서울', '경기', '세종')
          AND deal_ym >= '2026-05'
        ORDER BY deal_ym DESC, region_name ASC
    """).fetchall()
    
    for row in sample:
        ym, reg, p_cnt, j_rat = row
        p_str = f"{p_cnt:,}호" if p_cnt is not None else "집계중"
        j_str = f"{j_rat:.2f}%" if j_rat is not None else "집계중"
        print(f"[{ym}] {reg}  |  월간 인허가: {p_str:>10}  |  전세가율: {j_str:>8}")
        
    conn.close()

if __name__ == "__main__":
    recs = fetch_monthly_permits()
    if recs:
        update_db(recs)
