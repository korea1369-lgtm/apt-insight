import sqlite3
import json
import urllib.request
import urllib.parse
import time

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

TARGET_REGIONS = ["전국", "서울", "대구", "부산", "경기", "인천", "광주", "대전", "울산", "세종"]

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS macro_regional_indicators (
            deal_ym TEXT,
            region_name TEXT,
            permit_count INTEGER,
            jeonse_ratio REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (deal_ym, region_name)
        )
    """)
    conn.commit()
    conn.close()

def fetch_rone_jeonse_ratios():
    """R-ONE 아파트 전세가율 월간 시계열 수집"""
    print("\n--- 1. R-ONE 전세가율 시계열 수집 시작 ---")
    records = []
    
    # 총 39,519건 중 주요 시도 월간 데이터 수집 (1회당 1000건, 상위 10페이지 조회)
    for pIndex in range(1, 15):
        url = (
            "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?"
            f"KEY={RONE_KEY}&Type=json&STATBL_ID=A_2024_00072"
            f"&DTACYCLE_CD=MM&pIndex={pIndex}&pSize=1000"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("SttsApiTblData", [{}, {}])[1].get("row", [])
                if not rows:
                    break
                for r in rows:
                    region_raw = r.get("CLS_NM", "")
                    ym_raw = str(r.get("WRTTIME_IDTFR_ID", ""))
                    val = r.get("DTA_VAL")
                    
                    if ym_raw and val is not None and region_raw:
                        short_reg = region_raw.replace(" ", "")[:2]
                        if short_reg in TARGET_REGIONS:
                            try:
                                ratio = float(val)
                                ym = f"{ym_raw[:4]}-{ym_raw[4:6]}" if len(ym_raw) >= 6 else ym_raw
                                records.append((ym, short_reg, ratio))
                            except ValueError:
                                continue
            print(f"  페이지 {pIndex} 수신 완료 (누적 타겟 데이터: {len(records)}건)")
        except Exception as e:
            print(f"  페이지 {pIndex} 오류:", e)
            break
            
    print(f"✔ R-ONE 유효 전세가율 총 {len(records)}건 수집 완료")
    return records


def fetch_kosis_permits():
    """KOSIS 국토교통부 시도별 주택건설인허가실적(월별)"""
    print("\n--- 2. KOSIS 월별 주택인허가 실적 수집 시작 ---")
    
    # DT_1YL202008E (주택건설 인허가실적 시도별)
    kosis_url = (
        "https://kosis.kr/openapi/Param/statisticsParameterData.do?"
        f"method=getList&apiKey={KOSIS_KEY}"
        "&itmId=ALL&objL1=ALL&format=json&jsonVD=Y"
        "&prdSe=M&startPrdDe=201801&endPrdDe=202608"
        "&orgId=116&tblId=DT_1YL202008E"
    )
    
    records = []
    try:
        req = urllib.request.Request(kosis_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                for r in data:
                    region = r.get("C1_NM", "").strip()
                    ym = r.get("PRD_DE", "")
                    val = r.get("DT", "")
                    if ym and val and region:
                        try:
                            cnt = int(float(val))
                            short_reg = region[:2]
                            if short_reg in TARGET_REGIONS:
                                formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                                records.append((formatted_ym, short_reg, cnt))
                        except (ValueError, TypeError):
                            continue
                print(f"✔ KOSIS 인허가 데이터 {len(records)}건 수신 성공")
            else:
                print("⚠ KOSIS 응답 메시지:", data)
    except Exception as e:
        print("❌ KOSIS 수집 오류:", e)
        
    return records


def save_and_verify(j_records, p_records):
    print("\n--- 3. DB 적재 및 검증 ---")
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    c = conn.cursor()
    
    for ym, reg, ratio in j_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_ratio)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                jeonse_ratio = excluded.jeonse_ratio,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, ratio))
        
    for ym, reg, cnt in p_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                permit_count = excluded.permit_count,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, cnt))
        
    conn.commit()
    
    print("\n=== 대구 / 부산 / 서울 최근 6개월 데이터 현황 ===")
    rows = c.execute("""
        SELECT deal_ym, region_name, permit_count, jeonse_ratio 
        FROM macro_regional_indicators 
        WHERE region_name IN ('대구', '부산', '서울') AND deal_ym >= '2024-01'
        ORDER BY deal_ym DESC, region_name ASC
        LIMIT 18
    """).fetchall()
    
    for row in rows:
        ym, reg, p_cnt, j_rat = row
        p_str = f"{p_cnt:,}호" if p_cnt is not None else "-"
        j_str = f"{j_rat}%" if j_rat is not None else "-"
        print(f"[{ym}] {reg}  |  인허가: {p_str:>8}  |  전세가율: {j_str:>6}")
        
    total_cnt = c.execute("SELECT COUNT(*) FROM macro_regional_indicators").fetchone()[0]
    conn.close()
    print(f"\n🎉 전체 적재 완료! 총 누적 행 수: {total_cnt}건")

if __name__ == "__main__":
    init_db()
    j_data = fetch_rone_jeonse_ratios()
    p_data = fetch_kosis_permits()
    save_and_verify(j_data, p_data)
