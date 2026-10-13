import sqlite3
import json
import urllib.request
import urllib.parse
import time

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

def fetch_chunked_permits():
    print("--- KOSIS 월별 주택인허가 실적 수집 (기간별 분할 호출) ---")
    
    # 40,000셀 제한 우회를 위해 기간 분할 (2년 단위)
    date_ranges = [
        ("201801", "201912"),
        ("202001", "202112"),
        ("202201", "202312"),
        ("202401", "202608")
    ]
    
    base_url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    all_records = []
    
    for start_de, end_de in date_ranges:
        print(f"  ▶ 구간 조회 중: {start_de[:4]}년 ~ {end_de[:4]}년 ...")
        url = (
            f"{base_url}?method=getList&apiKey={KOSIS_KEY}"
            f"&itmId=ALL&objL1=ALL&objL2=ALL&objL3=ALL&format=json&jsonVD=Y"
            f"&prdSe=M&startPrdDe={start_de}&endPrdDe={end_de}"
            f"&orgId=116&tblId=DT_MLTM_1946"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                    chunk_cnt = 0
                    for r in data:
                        c1 = r.get("C1_NM", "").strip()
                        c2 = r.get("C2_NM", "").strip()
                        c3 = r.get("C3_NM", "").strip()
                        ym = r.get("PRD_DE", "")
                        val = r.get("DT", "")
                        
                        reg = clean_region(c1)
                        # 부문(C2) '계' 및 규모(C3) '계'만 선택하여 중복 없는 총 인허가 호수만 발췌
                        is_total = ("계" in c2 or not c2) and ("계" in c3 or not c3)
                        
                        if reg and ym and val and is_total:
                            try:
                                cnt = int(float(val))
                                formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                                all_records.append((formatted_ym, reg, cnt))
                                chunk_cnt += 1
                            except:
                                continue
                    print(f"    ✔ {start_de[:4]}~{end_de[:4]} 수신 성공: 총계 기준 {chunk_cnt:,}건 추출")
                else:
                    print(f"    ⚠ 수신 오류:", str(data)[:100])
        except Exception as e:
            print(f"    ❌ 호출 실패 ({start_de}~{end_de}):", e)
        time.sleep(0.3)
        
    print(f"\n✔ 전체 기간 정제된 월별 인허가 데이터: 총 {len(all_records):,}건")
    return all_records

def save_to_db(records):
    if not records:
        print("⚠ 적재할 데이터가 없습니다.")
        return
        
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
    
    print("\n================ 최종 적재 결과 확인 ================")
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
        
    cnt_permits = c.execute("SELECT COUNT(*) FROM macro_regional_indicators WHERE permit_count IS NOT NULL").fetchone()[0]
    cnt_jeonse = c.execute("SELECT COUNT(*) FROM macro_regional_indicators WHERE jeonse_ratio IS NOT NULL").fetchone()[0]
    print(f"\n✔ 인허가 데이터 보유 행 수: {cnt_permits:,}건")
    print(f"✔ 전세가율 데이터 보유 행 수: {cnt_jeonse:,}건")
    conn.close()

if __name__ == "__main__":
    recs = fetch_chunked_permits()
    save_to_db(recs)
