import sqlite3
import json
import urllib.request
import urllib.parse
from collections import defaultdict

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
    print("--- KOSIS 총계 기준 월별 인허가실적 전수 수집 시작 ---")
    
    # 총계 코드 고정으로 셀 낭비 없이 2015년부터 2026년까지 1회 호출
    base_url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    params = {
        "method": "getList",
        "apiKey": KOSIS_KEY,
        "itmId": "13103871089T1",          # 인허가실적
        "objL1": "13102871089A.0001",       # 총 계
        "objL2": "13102871089B.0001",       # 총 계
        "objL3": "ALL",                     # 17개 시도 전체
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "M",
        "startPrdDe": "201501",
        "endPrdDe": "202608",
        "orgId": "116",
        "tblId": "DT_MLTM_1946"
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print("❌ KOSIS 호출 오류:", e)
        return []
        
    if not isinstance(data, list) or len(data) == 0 or "err" in data[0]:
        print("⚠ 응답 오류:", data)
        return []
        
    print(f"✔ KOSIS 원본 데이터 수신 성공: {len(data):,}건")
    
    # 통계표가 '월별 누계'이므로, 지역별로 (연도, 월) 정렬 후 당월 순수인허가 호수 산출
    # region -> year -> month -> cumulative_val
    cum_data = defaultdict(lambda: defaultdict(dict))
    
    for r in data:
        reg = clean_region(r.get("C3_NM", ""))
        ym = r.get("PRD_DE", "")
        val = r.get("DT", "")
        if reg and len(ym) == 6 and val:
            try:
                year = ym[:4]
                month = int(ym[4:6])
                cum_data[reg][year][month] = int(float(val))
            except:
                continue
                
    monthly_records = []
    for reg, years in cum_data.items():
        for year, months in years.items():
            sorted_months = sorted(months.keys())
            prev_cum = 0
            for m in sorted_months:
                curr_cum = months[m]
                # 1월은 당월치 그대로, 2~12월은 (당월누계 - 전월누계)
                if m == 1:
                    monthly_val = curr_cum
                else:
                    monthly_val = max(0, curr_cum - prev_cum)
                
                prev_cum = curr_cum
                deal_ym = f"{year}-{m:02d}"
                monthly_records.append((deal_ym, reg, monthly_val))
                
    print(f"✔ 월별 순수 인허가 호수 변환 완료: 총 {len(monthly_records):,}건")
    return monthly_records

def save_and_verify(records):
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
    
    print("\n================ 최종 적재 현황 (최근 4개월) ================")
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
        print(f"[{ym}] {reg}  |  월간 인허가: {p_str:>8}  |  전세가율: {j_str:>7}")
        
    p_cnt = c.execute("SELECT COUNT(*) FROM macro_regional_indicators WHERE permit_count IS NOT NULL").fetchone()[0]
    j_cnt = c.execute("SELECT COUNT(*) FROM macro_regional_indicators WHERE jeonse_ratio IS NOT NULL").fetchone()[0]
    print(f"\n✔ 인허가 데이터 보유 건수: {p_cnt:,}건")
    print(f"✔ 전세가율 데이터 보유 건수: {j_cnt:,}건")
    conn.close()

if __name__ == "__main__":
    recs = fetch_monthly_permits()
    if recs:
        save_and_verify(recs)
