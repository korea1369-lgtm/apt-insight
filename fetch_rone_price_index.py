import sqlite3
import json
import urllib.request
import urllib.parse

DB_FILE = "apt_data_render_master.db"
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def clean_region(raw_name):
    if not raw_name: return ""
    name = raw_name.strip()
    for reg in ["서울", "경기", "인천", "대구", "부산", "광주", "대전", "울산", "세종", 
                "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "전국"]:
        if name.startswith(reg):
            return reg
    return ""

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 기존 테이블에 sale_price_index 컬럼이 없으면 자동 추가
    c.execute("PRAGMA table_info(macro_regional_indicators)")
    cols = [r[1] for r in c.fetchall()]
    if "sale_price_index" not in cols:
        c.execute("ALTER TABLE macro_regional_indicators ADD COLUMN sale_price_index REAL")
        print("✔ macro_regional_indicators에 'sale_price_index' 컬럼 추가 완료")
    conn.commit()
    conn.close()

def get_sale_index_tbl_id():
    """R-ONE 통계목록에서 '아파트 매매가격지수' 월간 통계표 탐색"""
    print("\n--- 1. R-ONE 아파트 매매가격지수 통계표 검색 ---")
    for page in range(1, 15):
        url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do?KEY={RONE_KEY}&Type=json&pIndex={page}&pSize=100"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("SttsApiTbl", [{}, {}])[1].get("row", [])
                for r in rows:
                    title = r.get("STATBL_NM", "")
                    cycle = r.get("DTACYCLE_CD", "")
                    if ("매매가격지수" in title or "매매종합지수" in title) and "아파트" in title and cycle == "MM":
                        tbl_id = r.get("STATBL_ID")
                        print(f"  ✔ 통계표 발견! ID: [{tbl_id}] / 제목: {title}")
                        return tbl_id
        except Exception as e:
            print("  검색 오류:", e)
            break
    return "A_2024_00070"  # 기본 표준 아파트 매매가격지수 ID 폴백

def fetch_rone_sale_index(tbl_id):
    print(f"\n--- 2. 아파트 매매가격지수 데이터 수집 (통계표: {tbl_id}) ---")
    records = []
    page = 1
    total_count = None
    
    while True:
        url = (
            "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?"
            f"KEY={RONE_KEY}&Type=json&STATBL_ID={tbl_id}"
            f"&DTACYCLE_CD=MM&pIndex={page}&pSize=1000"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                head = data.get("SttsApiTblData", [{}, {}])[0].get("head", [])
                if total_count is None and head:
                    total_count = head[0].get("list_total_count", 0)
                    print(f"  총 대상 데이터 건수: {total_count:,}건")
                
                rows = data.get("SttsApiTblData", [{}, {}])[1].get("row", [])
                if not rows:
                    break
                    
                for r in rows:
                    reg_raw = r.get("CLS_NM") or r.get("WRT_C1_NM") or r.get("C1_NM") or ""
                    ym_raw = str(r.get("WRTTIME_IDTFR_ID") or r.get("WRT_TIME") or r.get("PRD_DE") or "")
                    val = r.get("DTA_VAL") or r.get("DT")
                    
                    reg = clean_region(reg_raw)
                    if reg and ym_raw and val is not None:
                        try:
                            idx_val = float(val)
                            formatted_ym = f"{ym_raw[:4]}-{ym_raw[4:6]}" if len(ym_raw) >= 6 else ym_raw
                            records.append((formatted_ym, reg, idx_val))
                        except ValueError:
                            continue
                            
            if page % 5 == 0 or len(rows) < 1000:
                print(f"  {page}페이지 수신 완료 (누적 유효 레코드: {len(records):,}건)")
            page += 1
            if total_count and (page - 1) * 1000 >= total_count:
                break
        except Exception as e:
            print("  호출 에러:", e)
            break
            
    print(f"✔ 총 {len(records):,}건 매매가격지수 수집 완료")
    return records

def save_to_db(records):
    print("\n--- 3. DB 적재 및 검증 ---")
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    c = conn.cursor()
    c.executemany("""
        INSERT INTO macro_regional_indicators (deal_ym, region_name, sale_price_index)
        VALUES (?, ?, ?)
        ON CONFLICT(deal_ym, region_name) DO UPDATE SET
            sale_price_index = excluded.sale_price_index,
            updated_at = CURRENT_TIMESTAMP
    """, records)
    conn.commit()
    
    # 2021년 고점 vs 2023년 하락 검증 출력
    print("\n=== 대구 / 서울 / 부산 매매가격지수 추이 검증 ===")
    sample = c.execute("""
        SELECT deal_ym, region_name, sale_price_index 
        FROM macro_regional_indicators 
        WHERE region_name IN ('대구', '서울', '부산') 
          AND deal_ym IN ('2021-06', '2021-11', '2022-12', '2023-12', '2024-12')
        ORDER BY region_name, deal_ym ASC
    """).fetchall()
    
    for row in sample:
        ym, reg, idx = row
        print(f"  [{ym}] {reg} 매매가격지수: {idx} pt")
        
    conn.close()
    print("\n🎉 적재 완료!")

if __name__ == "__main__":
    init_db()
    tbl_id = get_sale_index_tbl_id()
    recs = fetch_rone_sale_index(tbl_id)
    if recs:
        save_to_db(recs)