import sqlite3
import json
import urllib.request
import urllib.parse

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS macro_regional_indicators (
            deal_ym TEXT,
            region_name TEXT,
            permit_count INTEGER,
            jeonse_to_rent_ratio REAL,
            jeonse_ratio REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (deal_ym, region_name)
        )
    """)
    conn.commit()
    conn.close()

def get_rone_statbl_id(keyword):
    """R-ONE 통계 목록에서 키워드(전월세전환율, 전세가격)에 맞는 STATBL_ID 검색"""
    url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do?KEY={RONE_KEY}&Type=json&pIndex=1&pSize=1000"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        rows = res["SttsApiTbl"][1]["row"]
        for r in rows:
            nm = r.get("STATBL_NM", "")
            # 월간 아파트 전월세전환율 또는 전세가격비율 탐색
            if keyword in nm and "아파트" in nm and r.get("DTACYCLE_CD") == "MM":
                return r.get("STATBL_ID"), nm
    return None, None

def fetch_rone_data():
    """R-ONE에서 전월세전환율 및 전세가율 수집"""
    print("\n[1] R-ONE 통계 데이터 수집 시작...")
    tbl_id, tbl_name = get_rone_statbl_id("전환율")
    if not tbl_id:
        tbl_id, tbl_name = get_rone_statbl_id("전월세")
    
    print(f"-> 발견된 R-ONE 통계표: [{tbl_id}] {tbl_name}")
    if not tbl_id:
        print("❌ R-ONE 통계표 ID를 찾지 못했습니다.")
        return []

    # 실제 데이터 호출
    data_url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?KEY={RONE_KEY}&Type=json&STATBL_ID={tbl_id}&pIndex=1&pSize=1000"
    records = []
    try:
        req = urllib.request.Request(data_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            rows = res.get("SttsApiTblData", [{}, {}])[1].get("row", [])
            print(f"-> R-ONE 통계 레코드 수신: {len(rows)}건")
            for r in rows:
                region = r.get("CLS_NM", "") or r.get("REGION_NM", "")
                ym = r.get("WRT_TIME", "") or r.get("PRD_DE", "")
                val = r.get("DTA_VAL") or r.get("DT")
                if ym and val and region:
                    try:
                        v = float(val)
                        short_reg = region.strip()[:2]
                        if short_reg in ["전국", "대구", "부산", "서울", "경기", "인천", "대전", "광주", "울산", "세종"]:
                            formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                            records.append((formatted_ym, short_reg, v))
                    except ValueError:
                        continue
    except Exception as e:
        print(f"❌ R-ONE 데이터 수집 오류: {e}")
    return records

def fetch_kosis_data():
    """KOSIS 인허가 데이터 파라미터 규격 완성 수집"""
    print("\n[2] KOSIS 주택건설인허가 데이터 수집 시작...")
    # KOSIS 공식 주택건설인허가실적(시도별)
    # itmId=T1+(호수), objL1=ALL(전체 시도)
    url = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={KOSIS_KEY}&itmId=T1+&objL1=ALL&objL2=ALL&format=json&jsonVD=Y&prdSe=M&startPrdDe=202401&endPrdDe=202608&orgId=116&tblId=DT_MLTM_2082"
    records = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                print(f"-> KOSIS 원본 데이터 수신: {len(data)}건")
                for r in data:
                    region = r.get("C1_NM", "").strip()
                    c2 = r.get("C2_NM", "").strip()
                    ym = r.get("PRD_DE", "")
                    val = r.get("DT", "")
                    # 전체(총계) 호수만 추출
                    if ("계" in c2 or not c2 or "합계" in c2) and ym and val:
                        try:
                            cnt = int(float(val))
                            short_reg = region[:2]
                            formatted_ym = f"{ym[:4]}-{ym[4:6]}"
                            records.append((formatted_ym, short_reg, cnt))
                        except:
                            continue
            else:
                print("⚠ KOSIS 응답 내용:", data)
    except Exception as e:
        print(f"❌ KOSIS 수집 오류: {e}")
    return records

def main():
    init_db()
    rone_records = fetch_rone_data()
    kosis_records = fetch_kosis_data()

    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    c = conn.cursor()

    # R-ONE 적재 (전월세전환율)
    for ym, reg, val in rone_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_to_rent_ratio)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                jeonse_to_rent_ratio = excluded.jeonse_to_rent_ratio,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, val))

    # KOSIS 적재 (인허가 실적)
    for ym, reg, cnt in kosis_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                permit_count = excluded.permit_count,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, cnt))

    conn.commit()
    
    total = c.execute("SELECT COUNT(*) FROM macro_regional_indicators").fetchone()[0]
    sample = c.execute("SELECT deal_ym, region_name, permit_count, jeonse_to_rent_ratio FROM macro_regional_indicators ORDER BY deal_ym DESC LIMIT 10").fetchall()
    conn.close()

    print(f"\n🎉 작업 완료! 총 적재 건수: {total}건")
    print("=== 최신 적재 데이터 샘플 ===")
    for s in sample:
        print(s)

if __name__ == "__main__":
    main()
