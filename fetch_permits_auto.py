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

def fetch_permits():
    print("--- 1. KOSIS 인허가 월별 실적 수집 시도 ---")
    
    # objL 단계별(2단계, 3단계, 4단계)로 자동 fallback 시도
    attempts = [
        # 시도 1: objL1 ~ objL3 포괄
        {
            "tblId": "DT_MLTM_1946",
            "params": "&itmId=ALL&objL1=ALL&objL2=ALL&objL3=ALL&prdSe=M&startPrdDe=201801&endPrdDe=202608"
        },
        # 시도 2: objL1 ~ objL4 포괄
        {
            "tblId": "DT_MLTM_1946",
            "params": "&itmId=ALL&objL1=ALL&objL2=ALL&objL3=ALL&objL4=ALL&prdSe=M&startPrdDe=201801&endPrdDe=202608"
        }
    ]
    
    records = []
    base_url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    
    for att in attempts:
        url = f"{base_url}?method=getList&apiKey={KOSIS_KEY}{att['params']}&format=json&jsonVD=Y&orgId=116&tblId={att['tblId']}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                    print(f"✔ 호출 성공! {att['tblId']} 데이터 {len(data):,}건 수신")
                    for r in data:
                        # 지역명 추출 (C1, C2, C3 중 지역명이 있는 컬럼 탐색)
                        c1 = r.get("C1_NM", "")
                        c2 = r.get("C2_NM", "")
                        c3 = r.get("C3_NM", "")
                        
                        reg = clean_region(c1) or clean_region(c2) or clean_region(c3)
                        ym = r.get("PRD_DE", "")
                        val = r.get("DT", "")
                        
                        # 합계/계 항목 필터링 (중복 방지)
                        is_total = any("계" in s or "총" in s for s in [c1, c2, c3] if s != reg)
                        
                        if reg and ym and val and (is_total or not c2):
                            try:
                                cnt = int(float(val))
                                formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                                records.append((formatted_ym, reg, cnt))
                            except:
                                continue
                    break
                else:
                    print(f"  응답 확인 ({att['tblId']}):", str(data)[:100])
        except Exception as e:
            print("  호출 에러:", e)
            continue
            
    print(f"✔ 정제된 인허가 레코드: {len(records):,}건")
    return records

def update_db(records):
    if not records:
        print("⚠ 적재할 인허가 데이터가 없습니다.")
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
    
    print("\n=== 최근 3개월 대구, 부산, 서울, 경기 적재 결과 ===")
    sample = c.execute("""
        SELECT deal_ym, region_name, permit_count, jeonse_ratio 
        FROM macro_regional_indicators 
        WHERE region_name IN ('대구', '부산', '서울', '경기')
          AND deal_ym >= '2026-05'
        ORDER BY deal_ym DESC, region_name ASC
    """).fetchall()
    
    for row in sample:
        ym, reg, p_cnt, j_rat = row
        p_str = f"{p_cnt:,}호" if p_cnt is not None else "집계중"
        j_str = f"{j_rat:.2f}%" if j_rat is not None else "집계중"
        print(f"[{ym}] {reg}  |  인허가: {p_str:>10}  |  전세가율: {j_str:>8}")
        
    conn.close()

if __name__ == "__main__":
    recs = fetch_permits()
    update_db(recs)
