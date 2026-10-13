import sqlite3
import json
import urllib.request
import urllib.parse
import time

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def get_rone_statbl_id():
    """R-ONE 전체 목록(1~15페이지)을 순회하며 '매매가격대비 전세가격비율(아파트)' 통계표 정확 매칭"""
    print("\n--- 1. R-ONE 아파트 전세가율 통계표 검색 ---")
    matched_id = None
    matched_title = ""
    
    for page in range(1, 15):
        url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do?KEY={RONE_KEY}&Type=json&pIndex={page}&pSize=100"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("SttsApiTbl", [{}, {}])[1].get("row", [])
                for r in rows:
                    title = r.get("STATBL_NM", "").replace(" ", "")
                    # '매매가격대비전세가격' 혹은 '전세가격비율' 포함 여부
                    if ("매매가격대비전세가격" in title or "전세가격비율" in title or "전세가율" in title) and "아파트" in title:
                        matched_id = r.get("STATBL_ID")
                        matched_title = r.get("STATBL_NM")
                        print(f"  ✔ 통계표 발견! ID: [{matched_id}] / 제목: {matched_title} / 주기: {r.get('DTACYCLE_NM')}")
                        if r.get("DTACYCLE_CD") == "MM": # 월간 통계 우선 선택
                            return matched_id, matched_title
        except Exception as e:
            break
            
    return matched_id, matched_title

def fetch_rone_jeonse_data(statbl_id):
    if not statbl_id:
        print("  ⚠ R-ONE 통계표 ID를 찾지 못했습니다.")
        return []
        
    print(f"\n--- 2. R-ONE 전세가율 시계열 데이터 수집 (ID: {statbl_id}) ---")
    records = []
    # 데이터는 페이징으로 최대 3000건 확보 (대구, 부산, 서울 등 전 시도 시계열)
    for pIndex in range(1, 5):
        url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?KEY={RONE_KEY}&Type=json&STATBL_ID={statbl_id}&pIndex={pIndex}&pSize=1000"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("SttsApiTblData", [{}, {}])[1].get("row", [])
                if not rows:
                    break
                for r in rows:
                    region = r.get("WRT_C1_NM") or r.get("C1_NM") or r.get("REGION_NM") or ""
                    ym = str(r.get("WRT_TIME") or r.get("PRD_DE") or "")
                    val = r.get("DTA_VAL") or r.get("DT")
                    if ym and val and region:
                        try:
                            rate = float(val)
                            # 지역명 앞 2글자 (대구, 부산, 서울, 경기 등)
                            reg = region[:2]
                            formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                            records.append((formatted_ym, reg, rate))
                        except ValueError:
                            continue
        except Exception as e:
            print("  ❌ R-ONE 데이터 페이징 오류:", e)
            break
            
    print(f"  ✔ R-ONE 전세가율 총 {len(records)}건 수신 완료")
    return records


def fetch_kosis_monthly_permits():
    """KOSIS 국토교통부 시도별 주택건설인허가실적(DT_MLTM_666) 월별 전체 시계열 수집"""
    print("\n--- 3. KOSIS 주택건설인허가(월별·시도별 전체 시계열) 수집 ---")
    
    # 주요 시도코드 정의 (전국:00, 서울:11, 부산:21, 대구:22, 인천:23, 광주:24, 대전:25, 울산:26, 세종:29, 경기:31)
    # objL1에 지정하거나 ALL로 월별 파라미터 호출
    base_url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    
    # 201801부터 202608까지 월간(M) 데이터 호출
    params = {
        "method": "getList",
        "apiKey": KOSIS_KEY,
        "itmId": "ALL",
        "objL1": "ALL",
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "M",          # 월별 강제 지정
        "startPrdDe": "201801", # 2018년부터 누적 시계열
        "endPrdDe": "202608",
        "orgId": "116",
        "tblId": "DT_MLTM_666"
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    records = []
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                print(f"  ✔ KOSIS 월별 인허가 데이터 원시 수신: {len(data)}건")
                for r in data:
                    region = r.get("C1_NM", "").strip()
                    ym = r.get("PRD_DE", "")
                    val = r.get("DT", "")
                    
                    if ym and val and region:
                        try:
                            cnt = int(float(val))
                            # 202401 -> 2024-01
                            formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                            records.append((formatted_ym, region[:2], cnt))
                        except (ValueError, TypeError):
                            continue
            else:
                print("  ⚠ KOSIS 응답 메시지:", data)
    except Exception as e:
        print("  ❌ KOSIS 수집 오류:", e)
        
    print(f"  ✔ KOSIS 월별 인허가 정제 완료: {len(records)}건")
    return records


def save_to_db(j_records, p_records):
    print("\n--- 4. SQLite DB(apt_data_render_master.db) 적재 ---")
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
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
    
    # 1. 인허가량 적재
    for ym, reg, cnt in p_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                permit_count = excluded.permit_count,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, cnt))
        
    # 2. 전세가율 적재
    for ym, reg, ratio in j_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_ratio)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                jeonse_ratio = excluded.jeonse_ratio,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, ratio))
        
    conn.commit()
    
    # 검증: 대구, 부산, 서울, 경기 최신 월별 데이터 확인
    print("\n=== 대구 / 부산 / 서울 / 경기 최근 5개월 적재 현황 ===")
    check_rows = c.execute("""
        SELECT deal_ym, region_name, permit_count, jeonse_ratio 
        FROM macro_regional_indicators 
        WHERE region_name IN ('대구', '부산', '서울', '경기')
        ORDER BY deal_ym DESC, region_name ASC
        LIMIT 16
    """).fetchall()
    
    for row in check_rows:
        ym, reg, p_cnt, j_rat = row
        p_str = f"인허가: {p_cnt:,}호" if p_cnt is not None else "인허가: -"
        j_str = f"전세가율: {j_rat}%" if j_rat is not None else "전세가율: -"
        print(f"[{ym}] {reg} -> {p_str} | {j_str}")
        
    total_cnt = c.execute("SELECT COUNT(*) FROM macro_regional_indicators").fetchone()[0]
    conn.close()
    print(f"\n🎉 전체 적재 완료! 총 누적 행 수: {total_cnt}건")

if __name__ == "__main__":
    stat_id, title = get_rone_statbl_id()
    j_records = fetch_rone_jeonse_data(stat_id)
    p_records = fetch_kosis_monthly_permits()
    save_to_db(j_records, p_records)
