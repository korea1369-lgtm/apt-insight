import sqlite3
import json
import urllib.request
import urllib.parse

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def fetch_rone_jeonse_to_rent():
    """
    R-ONE 공식 부동산통계정보 API (전월세전환율)
    엔드포인트: https://www.reb.or.kr/r-one/openapi/SttsApi.do
    """
    print("\n--- 1. R-ONE 전월세전환율 수집 시작 ---")
    url = "https://www.reb.or.kr/r-one/openapi/SttsApi.do"
    
    # R-ONE 아파트 전월세전환율 (통계표: 10401)
    params = {
        "key": RONE_KEY,
        "format": "json",
        "tblId": "10401",     # 아파트 전월세전환율
        "prdSe": "M",          # 월간
        "startPrdDe": "202301",
        "endPrdDe": "202608"
    }
    
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    records = []
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("SttsApi", {}).get("row", [])
            if not items and isinstance(data, list):
                items = data
            
            print(f"✔ R-ONE 원시 데이터 {len(items)}건 수신")
            for item in items:
                # 시도명 / 연월 / 수치 파싱
                region = item.get("C1_NM") or item.get("REGION_NM") or item.get("C1_NM_KOR") or ""
                ym = item.get("PRD_DE") or item.get("WRT_TIME") or ""
                val = item.get("DT") or item.get("DATA_VAL")
                
                if ym and val and region:
                    try:
                        formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                        rate = float(val)
                        short_region = region[:2]
                        # 주요 지역만 축약 필터
                        if short_region in ["전국", "대구", "부산", "서울", "경기", "인천", "대전", "광주", "울산", "세종"]:
                            records.append((formatted_ym, short_region, rate))
                    except ValueError:
                        continue
    except Exception as e:
        print(f"❌ R-ONE API 호출 오류: {e}")
        
    print(f"✔ R-ONE 유효 데이터 정제 완료: {len(records)}건")
    return records


def fetch_kosis_permits():
    """
    KOSIS 주택건설인허가실적 (공식 비파라미터/통계표 전송 방식)
    """
    print("\n--- 2. KOSIS 인허가 실적 수집 시작 ---")
    url = "https://kosis.kr/openapi/statisticsData.do"
    
    # 국토교통부 주택건설인허가실적(시도별·부문별)
    # userStatsId 대신 공식 statisticsData 방식 적용
    params = {
        "method": "getList",
        "apiKey": KOSIS_KEY,
        "format": "json",
        "jsonVD": "Y",
        "userStatsId": "kkh890615/116/DT_MLTM_2082/2/1/20261005200000", # 임시 통계표 ID 우회
        "prdSe": "M",
        "startPrdDe": "202301",
        "endPrdDe": "202608",
        "orgId": "116",
        "tblId": "DT_MLTM_2082"
    }
    
    # KOSIS 기본 일반 목록 호출
    kosis_url = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={KOSIS_KEY}&itmId=T1&objL1=00+11+21+22+23+24+25+26+29+31+32+33+34+35+36+37+38+39&objL2=ALL&format=json&jsonVD=Y&prdSe=M&startPrdDe=202301&endPrdDe=202608&orgId=116&tblId=DT_MLTM_2082"
    
    records = []
    try:
        req = urllib.request.Request(kosis_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            if isinstance(res_json, list):
                for row in res_json:
                    region = row.get("C1_NM", "").strip()
                    gubun = row.get("C2_NM", "").strip() # 전체/부문구분
                    ym = row.get("PRD_DE", "")
                    val = row.get("DT", "")
                    
                    # 총계(전체) 인허가 호수만 필터링
                    if "총계" in gubun or "계" in gubun or not gubun:
                        try:
                            formatted_ym = f"{ym[:4]}-{ym[4:6]}"
                            cnt = int(float(val))
                            short_region = region[:2] if len(region) >= 2 else region
                            records.append((formatted_ym, short_region, cnt))
                        except (ValueError, TypeError):
                            continue
                print(f"✔ KOSIS 인허가 데이터 {len(records)}건 수신 성공")
            else:
                print("⚠ KOSIS 원본 응답:", res_json)
    except Exception as e:
        print(f"❌ KOSIS API 호출 오류: {e}")
        
    return records


def save_to_db(rone_data, permit_data):
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    c = conn.cursor()
    
    # 1. R-ONE 전월세전환율 적재
    for ym, region, val in rone_data:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_to_rent_ratio)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                jeonse_to_rent_ratio = excluded.jeonse_to_rent_ratio,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, region, val))
        
    # 2. 인허가 실적 적재
    for ym, region, cnt in permit_data:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                permit_count = excluded.permit_count,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, region, cnt))
        
    conn.commit()
    cnt_total = c.execute("SELECT COUNT(*) FROM macro_regional_indicators").fetchone()[0]
    sample = c.execute("SELECT deal_ym, region_name, permit_count, jeonse_to_rent_ratio FROM macro_regional_indicators ORDER BY deal_ym DESC LIMIT 10").fetchall()
    conn.close()
    
    print(f"\n🎉 최종 DB 적재 완료! 총 행 수: {cnt_total}건")
    print("=== 최신 적재 데이터 샘플 ===")
    for s in sample:
        print(s)

if __name__ == "__main__":
    r_data = fetch_rone_jeonse_to_rent()
    p_data = fetch_kosis_permits()
    save_to_db(r_data, p_data)
