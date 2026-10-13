import sqlite3
import json
import urllib.request
import urllib.parse
from datetime import datetime

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def init_macro_table():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 지역별 월간 매크로 지표 테이블 생성
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
    print("✔ macro_regional_indicators 테이블 준비 완료")

def fetch_kosis_housing_permits():
    """
    KOSIS 주택건설인허가실적(시도별) 수집
    통계표ID: DT_1YL202008E (또는 주택건설인허가 통계표)
    """
    print("\n--- 1. KOSIS 인허가 실적 수집 시작 ---")
    # KOSIS API 파라미터 구성
    base_url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    params = {
        "method": "getList",
        "apiKey": KOSIS_KEY,
        "itmId": "T1+",
        "objL1": "ALL",
        "objL2": "",
        "objL3": "",
        "objL4": "",
        "objL5": "",
        "objL6": "",
        "objL7": "",
        "objL8": "",
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "M",
        "startPrdDe": "202301",
        "endPrdDe": "202608",
        "orgId": "116",
        "tblId": "DT_MLTM_2082"  # 국토교통부 시도별 주택건설 인허가실적
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    records = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if isinstance(res_data, list):
                for row in res_data:
                    # C1_NM(시도명), PRD_DE(연월), DT(수치)
                    region = row.get("C1_NM", "").strip()
                    ym = row.get("PRD_DE", "")
                    val = row.get("DT", "")
                    if ym and val:
                        try:
                            # 202601 -> 2026-01
                            formatted_ym = f"{ym[:4]}-{ym[4:6]}"
                            cnt = int(float(val))
                            # 주요 시도명 축약 정제 (대구광역시 -> 대구)
                            short_region = region[:2] if len(region) >= 2 else region
                            records.append((formatted_ym, short_region, cnt))
                        except ValueError:
                            continue
                print(f"✔ KOSIS 인허가 데이터 {len(records)}건 수신 성공")
            else:
                print("⚠ KOSIS 응답 확인 필요:", res_data)
    except Exception as e:
        print(f"❌ KOSIS API 호출 중 오류 발생: {e}")
    return records

def fetch_rone_jeonse_indicators():
    """
    R-ONE 부동산통계정보시스템 Open API 연동
    전월세전환율 및 전세가율 수집
    """
    print("\n--- 2. R-ONE 부동산통계정보 수집 시작 ---")
    # R-ONE REST API 엔드포인트
    base_url = "https://www.reb.or.kr/r-one/openapi/statistics"
    
    # 예시: 월간 전월세전환율/전세가율 조회 파라미터
    params = {
        "key": RONE_KEY,
        "format": "json",
        "numOfRows": "1000",
        "pageNo": "1"
    }
    
    records = []
    # R-ONE API 엔드포인트 호출 테스트
    try:
        test_url = f"https://api.odcloud.kr/api/15063424/v1/uddi:7e913398-413e-4c63-bd41-5700acb2dfda?serviceKey={RONE_KEY}"
        req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode("utf-8"))
            data_list = res.get("data", [])
            print(f"✔ R-ONE 공공 API 응답 수신: {len(data_list)}건")
            for item in data_list:
                # 필드 매핑
                ym = item.get("날짜") or item.get("조사연월") or item.get("연월")
                region = item.get("지역") or item.get("시도") or ""
                ratio = item.get("전월세전환율") or item.get("전세가율")
                if ym and region and ratio:
                    records.append((str(ym), str(region)[:2], float(ratio)))
    except Exception as e:
        print(f"ℹ R-ONE 특화 엔드포인트 연동 안내: {e}")
    return records

def save_to_db(permit_data, rone_data):
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    c = conn.cursor()
    
    # 1. 인허가 데이터 반영
    for ym, region, cnt in permit_data:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                permit_count = excluded.permit_count,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, region, cnt))
        
    # 2. 전월세전환율/전세가율 데이터 반영
    for ym, region, val in rone_data:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_to_rent_ratio)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                jeonse_to_rent_ratio = excluded.jeonse_to_rent_ratio,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, region, val))
        
    conn.commit()
    
    # 저장 확인
    cnt_total = c.execute("SELECT COUNT(*) FROM macro_regional_indicators").fetchone()[0]
    sample = c.execute("SELECT deal_ym, region_name, permit_count, jeonse_to_rent_ratio FROM macro_regional_indicators WHERE permit_count IS NOT NULL LIMIT 5").fetchall()
    
    conn.close()
    print(f"\n🎉 DB 적재 완료! 총 적재 행 수: {cnt_total}건")
    print("=== 적재 샘플 미리보기 ===")
    for s in sample:
        print(s)

if __name__ == "__main__":
    init_macro_table()
    permits = fetch_kosis_housing_permits()
    rone_stats = fetch_rone_jeonse_indicators()
    save_to_db(permits, rone_stats)
