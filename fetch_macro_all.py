import sqlite3
import json
import urllib.request
import urllib.parse
import time

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
            jeonse_ratio REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (deal_ym, region_name)
        )
    """)
    conn.commit()
    conn.close()

def clean_region(raw_name):
    """시도명 표준화 (2글자 표준 축약)"""
    if not raw_name:
        return ""
    name = raw_name.strip()
    if name.startswith("서울"): return "서울"
    if name.startswith("경기"): return "경기"
    if name.startswith("인천"): return "인천"
    if name.startswith("대구"): return "대구"
    if name.startswith("부산"): return "부산"
    if name.startswith("광주"): return "광주"
    if name.startswith("대전"): return "대전"
    if name.startswith("울산"): return "울산"
    if name.startswith("세종"): return "세종"
    if name.startswith("강원"): return "강원"
    if name.startswith("충북") or name.startswith("충청북"): return "충북"
    if name.startswith("충남") or name.startswith("충청남"): return "충남"
    if name.startswith("전북") or name.startswith("전라북"): return "전북"
    if name.startswith("전남") or name.startswith("전라남"): return "전남"
    if name.startswith("경북") or name.startswith("경상북"): return "경북"
    if name.startswith("경남") or name.startswith("경상남"): return "경남"
    if name.startswith("제주"): return "제주"
    if name.startswith("전국"): return "전국"
    return ""

def fetch_rone_all_jeonse():
    """R-ONE 아파트 전세가율: 17개 시도 전체 + 2012년부터 최신월까지 완주 수집"""
    print("\n--- 1. R-ONE 아파트 전세가율 전체 시계열 / 전 지역 수집 ---")
    records = []
    page = 1
    total_count = None
    
    while True:
        url = (
            "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?"
            f"KEY={RONE_KEY}&Type=json&STATBL_ID=A_2024_00072"
            f"&DTACYCLE_CD=MM&pIndex={page}&pSize=1000"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                head = data.get("SttsApiTblData", [{}, {}])[0].get("head", [])
                if total_count is None and head:
                    total_count = head[0].get("list_total_count", 0)
                    print(f"  총 대상 데이터 수: {total_count:,}건 (약 {(total_count//1000)+1}페이지 조회)")
                
                rows = data.get("SttsApiTblData", [{}, {}])[1].get("row", [])
                if not rows:
                    break
                    
                for r in rows:
                    reg_raw = r.get("CLS_NM", "")
                    ym_raw = str(r.get("WRTTIME_IDTFR_ID", ""))
                    val = r.get("DTA_VAL")
                    
                    reg = clean_region(reg_raw)
                    if reg and ym_raw and val is not None:
                        try:
                            rate = float(val)
                            ym = f"{ym_raw[:4]}-{ym_raw[4:6]}" if len(ym_raw) >= 6 else ym_raw
                            records.append((ym, reg, rate))
                        except ValueError:
                            continue
                            
            if page % 5 == 0 or len(rows) < 1000:
                print(f"  {page}페이지 완료... (현재 수집된 유효 레코드: {len(records):,}건)")
            page += 1
            if total_count and (page - 1) * 1000 >= total_count:
                break
        except Exception as e:
            print(f"  {page}페이지 오류:", e)
            break
            
    print(f"✔ R-ONE 전세가율 총 {len(records):,}건 완주 수집 완료!")
    return records


def find_and_fetch_kosis_permits():
    """KOSIS 국토교통부 월간 인허가 통계표 자동 매칭 후 전 시도 전체 시계열 수집"""
    print("\n--- 2. KOSIS 인허가 통계표 탐색 및 월별 시계열 수집 ---")
    
    # 1) 국토부 인허가 후보 통계표 목록
    candidate_tbls = ["DT_MLTM_1322", "DT_MLTM_2080", "DT_MLTM_2081", "DT_MLTM_666"]
    
    records = []
    for tbl in candidate_tbls:
        url = (
            "https://kosis.kr/openapi/Param/statisticsParameterData.do?"
            f"method=getList&apiKey={KOSIS_KEY}"
            "&itmId=ALL&objL1=ALL&format=json&jsonVD=Y"
            "&prdSe=M&startPrdDe=201501&endPrdDe=202608"
            f"&orgId=116&tblId={tbl}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                    print(f"  ✔ 유효 월간 인허가 통계표 발견! TBL_ID: {tbl} ({len(data):,}건 수신)")
                    for r in data:
                        region_raw = r.get("C1_NM", "")
                        ym = r.get("PRD_DE", "")
                        val = r.get("DT", "")
                        reg = clean_region(region_raw)
                        if reg and ym and val:
                            try:
                                cnt = int(float(val))
                                formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                                records.append((formatted_ym, reg, cnt))
                            except (ValueError, TypeError):
                                continue
                    break
        except Exception:
            continue
            
    # 후보에 없는 경우 연간/월간 복합 통계표(DT_MLTM_666)의 월간 분할치 조회 시도
    if not records:
        print("  보조 통계표 조회 시도 중...")
        url = (
            "https://kosis.kr/openapi/Param/statisticsParameterData.do?"
            f"method=getList&apiKey={KOSIS_KEY}"
            "&itmId=ALL&objL1=ALL&objL2=ALL&format=json&jsonVD=Y"
            "&prdSe=M&startPrdDe=201801&endPrdDe=202608"
            "&orgId=116&tblId=DT_MLTM_666"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                    print(f"  ✔ KOSIS 인허가 {len(data):,}건 수신")
                    for r in data:
                        reg = clean_region(r.get("C1_NM", ""))
                        ym = r.get("PRD_DE", "")
                        val = r.get("DT", "")
                        if reg and ym and val:
                            try:
                                cnt = int(float(val))
                                formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                                records.append((formatted_ym, reg, cnt))
                            except:
                                pass
        except Exception as e:
            print("  KOSIS 조회 에러:", e)
            
    print(f"✔ KOSIS 인허가 총 {len(records):,}건 정제 완료")
    return records


def save_to_db(j_records, p_records):
    print("\n--- 3. DB 적재 및 무결성 검증 ---")
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    c = conn.cursor()
    
    # 1. 전세가율 일괄 업서트
    c.executemany("""
        INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_ratio)
        VALUES (?, ?, ?)
        ON CONFLICT(deal_ym, region_name) DO UPDATE SET
            jeonse_ratio = excluded.jeonse_ratio,
            updated_at = CURRENT_TIMESTAMP
    """, j_records)
    
    # 2. 인허가 실적 일괄 업서트
    c.executemany("""
        INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
        VALUES (?, ?, ?)
        ON CONFLICT(deal_ym, region_name) DO UPDATE SET
            permit_count = excluded.permit_count,
            updated_at = CURRENT_TIMESTAMP
    """, p_records)
    
    conn.commit()
    
    # 검증: 수집된 지역 목록 및 연도 범위
    regions = [r[0] for r in c.execute("SELECT DISTINCT region_name FROM macro_regional_indicators ORDER BY region_name").fetchall()]
    ym_range = c.execute("SELECT MIN(deal_ym), MAX(deal_ym), COUNT(*) FROM macro_regional_indicators").fetchone()
    
    print("\n================ 적재 결과 보고 ================")
    print(f"✔ 수집된 지역 ({len(regions)}개): {', '.join(regions)}")
    print(f"✔ 시계열 범위: {ym_range[0]} ~ {ym_range[1]} (총 {ym_range[2]:,}개 행)")
    
    print("\n=== 최근 3개월 대구, 부산, 서울, 경기, 세종 샘플 ===")
    sample = c.execute("""
        SELECT deal_ym, region_name, permit_count, jeonse_ratio 
        FROM macro_regional_indicators 
        WHERE region_name IN ('대구', '부산', '서울', '경기', '세종')
        ORDER BY deal_ym DESC, region_name ASC
        LIMIT 15
    """).fetchall()
    
    for row in sample:
        ym, reg, p_cnt, j_rat = row
        p_str = f"{p_cnt:,}호" if p_cnt is not None else "집계중"
        j_str = f"{j_rat}%" if j_rat is not None else "집계중"
        print(f"[{ym}] {reg}  |  인허가: {p_str:>8}  |  전세가율: {j_str:>6}")
        
    conn.close()

if __name__ == "__main__":
    init_db()
    j_data = fetch_rone_all_jeonse()
    p_data = find_and_fetch_kosis_permits()
    save_to_db(j_data, p_data)
