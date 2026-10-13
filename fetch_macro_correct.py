import sqlite3
import json
import urllib.request
import urllib.parse

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def get_rone_jeonse_ratio():
    """R-ONE에서 '매매가격대비 전세가격비율' (전세가율) 탐색 및 수집"""
    print("\n--- 1. R-ONE 아파트 전세가율 수집 시작 ---")
    target_id = None
    target_name = ""
    
    # 1) 통계표 검색
    for pIndex in range(1, 10):
        url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do?KEY={RONE_KEY}&Type=json&pIndex={pIndex}&pSize=100"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("SttsApiTbl", [{}, {}])[1].get("row", [])
                for r in rows:
                    name = r.get("STATBL_NM", "")
                    # 전세가격비율 / 전세가율 아파트 월간 통계 검색
                    if ("전세가격비율" in name or "전세가비율" in name or "전세가율" in name) and "아파트" in name and r.get("DTACYCLE_CD") == "MM":
                        target_id = r.get("STATBL_ID")
                        target_name = name
                        print(f"  ✔ 전세가율 통계표 발견: [{target_id}] {name}")
                        break
            if target_id:
                break
        except Exception as e:
            print("  통계표 탐색 오류:", e)
            break

    if not target_id:
        print("  ⚠ 전세가율 통계표를 찾지 못했습니다.")
        return []

    # 2) 데이터 수치 조회
    data_url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?KEY={RONE_KEY}&Type=json&STATBL_ID={target_id}&pIndex=1&pSize=1000"
    records = []
    try:
        req = urllib.request.Request(data_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            rows = data.get("SttsApiTblData", [{}, {}])[1].get("row", [])
            print(f"  ✔ R-ONE 전세가율 수치 데이터 수신: {len(rows)}건")
            for r in rows:
                region = r.get("WRT_C1_NM") or r.get("C1_NM") or r.get("REGION_NM") or ""
                ym = str(r.get("WRT_TIME") or r.get("PRD_DE") or "")
                val = r.get("DTA_VAL") or r.get("DT")
                if ym and val and region:
                    try:
                        ratio = float(val)
                        short_reg = region[:2]
                        formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                        # 2023년 이후 데이터만 수집
                        if formatted_ym >= "2023-01":
                            records.append((formatted_ym, short_reg, ratio))
                    except ValueError:
                        continue
    except Exception as e:
        print("  ❌ R-ONE 전세가율 데이터 호출 실패:", e)
        
    print(f"  ✔ 유효 전세가율 레코드 정제 완료: {len(records)}건")
    return records


def get_kosis_permits():
    """KOSIS 인허가실적(DT_MLTM_666) 항목코드 자동 조회 후 수집"""
    print("\n--- 2. KOSIS 주택건설인허가 데이터 수집 시작 ---")
    
    # 1) 정확한 itmId(항목코드)와 objL1(시도분류코드) 찾기
    item_url = f"https://kosis.kr/openapi/statisticsData.do?method=getList&apiKey={KOSIS_KEY}&format=json&jsonVD=Y&userStatsId=kkh890615/116/DT_MLTM_666/2/1/20261005200000"
    
    # KOSIS 기본 일반 파라미터 API
    param_url = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={KOSIS_KEY}&itmId=13103114389T1&objL1=ALL&format=json&jsonVD=Y&prdSe=M&startPrdDe=202301&endPrdDe=202608&orgId=116&tblId=DT_MLTM_666"
    
    records = []
    # 시도 1: 대표 itmId 호출
    for try_itm in ["13103114389T1", "T1", "T01", "ALL"]:
        try:
            url = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={KOSIS_KEY}&itmId={try_itm}&objL1=ALL&format=json&jsonVD=Y&prdSe=M&startPrdDe=202301&endPrdDe=202608&orgId=116&tblId=DT_MLTM_666"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
                    print(f"  ✔ KOSIS 호출 성공 (itmId: {try_itm}), 총 {len(data)}건")
                    for r in data:
                        region = r.get("C1_NM", "").strip()
                        ym = r.get("PRD_DE", "")
                        val = r.get("DT", "")
                        if ym and val and region:
                            try:
                                cnt = int(float(val))
                                formatted_ym = f"{ym[:4]}-{ym[4:6]}" if len(ym) >= 6 else ym
                                records.append((formatted_ym, region[:2], cnt))
                            except (ValueError, TypeError):
                                continue
                    break
        except Exception as e:
            continue
            
    if not records:
        print("  ⚠ KOSIS 파라미터 응답 확인 필요 (통계표 파라미터 재확인)")
    return records


def save_to_db(jeonse_records, permit_records):
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
    
    # 전세가율 저장
    for ym, reg, ratio in jeonse_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_ratio)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                jeonse_ratio = excluded.jeonse_ratio,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, ratio))
        
    # 인허가 실적 저장
    for ym, reg, cnt in permit_records:
        c.execute("""
            INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
            VALUES (?, ?, ?)
            ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                permit_count = excluded.permit_count,
                updated_at = CURRENT_TIMESTAMP
        """, (ym, reg, cnt))
        
    conn.commit()
    cnt = c.execute("SELECT COUNT(*) FROM macro_regional_indicators").fetchone()[0]
    sample = c.execute("SELECT deal_ym, region_name, permit_count, jeonse_ratio FROM macro_regional_indicators WHERE jeonse_ratio IS NOT NULL OR permit_count IS NOT NULL ORDER BY deal_ym DESC LIMIT 10").fetchall()
    conn.close()
    
    print(f"\n🎉 적재 완료! 총 누적 행 수: {cnt}건")
    print("=== 최신 적재 데이터 샘플 (전세가율 / 인허가량) ===")
    for s in sample:
        print(s)

if __name__ == "__main__":
    j_data = get_rone_jeonse_ratio()
    p_data = get_kosis_permits()
    save_to_db(j_data, p_data)
