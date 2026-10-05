import os
import sqlite3
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

macro_router = APIRouter()

# 1. 기존 매크로 데이터베이스
DB_PATH = "macro_insight.db"

# 2. 이번에 인허가 및 전세가율을 적재한 마스터 데이터베이스
MASTER_DB_PATH = os.path.join(os.path.dirname(__file__), "apt_data_render_master.db")

def get_db():
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=500, detail="Database file not found")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_master_db():
    conn = sqlite3.connect(MASTER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@macro_router.get("/api/symbols")
def get_symbols():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM macro_monthly_stats ORDER BY symbol")
    raw_symbols = [r[0] for r in cur.fetchall()]
    
    symbols = []
    # 1. 서울 전체
    symbols.append({"symbol": "서울 전체", "name": "서울특별시 전체", "category": "SEOUL", "desc": "서울 25개 자치구 통합"})
    
    # 2. 서울 자치구
    seoul_gus = ["강남구", "서초구", "송파구", "강동구", "마포구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구", "도봉구", "노원구", "은평구", "서대문구", "종로구", "중구", "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구", "관악구"]
    for g in seoul_gus:
        if g in raw_symbols:
            symbols.append({"symbol": g, "name": f"서울 {g}", "category": "SEOUL_GU", "desc": f"서울특별시 {g}"})
            
    # 3. 경기 주요 시
    for s in raw_symbols:
        if s.endswith("시") and s not in ["대구광역시", "부산광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"]:
            symbols.append({"symbol": s, "name": f"경기/지방 {s}", "category": "SI", "desc": f"{s} 전역 통합"})
            
    # 4. 광역시
    for m in ["대구광역시", "부산광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"]:
        if m in raw_symbols:
            symbols.append({"symbol": m, "name": m, "category": "METRO", "desc": f"{m} 전역 통합"})
            
    conn.close()
    return {"symbols": symbols}

@macro_router.get("/api/indicators")
def get_indicators():
    return {
        "indicators": [
            {"id": "BOK_RATE", "name": "한국은행 기준금리", "category": "거시/금리", "unit": "%", "is_regional": False, "desc": "한국은행 정책 기준금리 (2006-2026)"},
            {"id": "HOUSING_PERMIT", "name": "국토부 주택건설 인허가 실적", "category": "수급/수익률", "unit": "호", "is_regional": True, "desc": "국토교통부 시도별 월간 주택건설 인허가실적 (공급 선행지표)"},
            {"id": "UNSOLD", "name": "국토부 미분양 매물 수", "category": "수급/수익률", "unit": "호", "is_regional": True, "desc": "국토교통부 시/도별 미분양 주택수"},
            {"id": "JEONSE_RATIO", "name": "아파트 전세가율", "category": "가치평가", "unit": "%", "is_regional": True, "desc": "한국부동산원 매매가격 대비 전세가격 비율 (2012-2026)"},
            {"id": "RENT_CONV_RATE", "name": "전월세전환율", "category": "수급/수익률", "unit": "%", "is_regional": True, "desc": "전세보증금을 월세로 전환할 때의 이율"},
            {"id": "PIR", "name": "KB 소득대비 주택가격 (PIR)", "category": "가치평가", "unit": "배", "is_regional": True, "desc": "연소득 대비 아파트 매매가격 배율"},
            {"id": "HAI", "name": "K-HAI 주택구입부담지수", "category": "가치평가", "unit": "pt", "is_regional": True, "desc": "중위가구 소득 대비 주택구입 상환부담"},
            {"id": "PRR", "name": "PRR (임대료대비 주택가격)", "category": "가치평가", "unit": "배", "is_regional": True, "desc": "임대료 현금흐름 대비 시가총액 배수"},
            {"id": "DEBT_TO_GDP", "name": "GDP 대비 가계부채 비율", "category": "거시/금리", "unit": "%", "is_regional": False, "desc": "BIS/한국은행 가계신용 / GDP 비율"}
        ]
    }

def clean_region_name(raw_name: str) -> str:
    """지역명을 표준 2글자로 정제 (예: '대구광역시' -> '대구', '서울 전체' -> '서울')"""
    if not raw_name: return "전국"
    name = raw_name.replace("전체", "").replace("광역시", "").replace("특별시", "").replace("특별자치시", "").replace("도", "").strip()
    return name[:2] if name else "전국"

@macro_router.get("/api/indicator_series")
def get_indicator_series(ind_id: str, region: str = "전국"):
    # 1. 주택건설 인허가 실적 (신규 적재 DB 연동)
    if ind_id in ["HOUSING_PERMIT", "PERMITS", "PERMIT"]:
        clean_reg = clean_region_name(region)
        conn = get_master_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT deal_ym, permit_count 
            FROM macro_regional_indicators 
            WHERE region_name = ? AND permit_count IS NOT NULL AND deal_ym LIKE '%-%'
            ORDER BY deal_ym ASC
        """, (clean_reg,))
        rows = cur.fetchall()
        if not rows:
            cur.execute("""
                SELECT deal_ym, permit_count 
                FROM macro_regional_indicators 
                WHERE region_name = '전국' AND permit_count IS NOT NULL AND deal_ym LIKE '%-%'
                ORDER BY deal_ym ASC
            """)
            rows = cur.fetchall()
        conn.close()
        return {
            "ind_id": ind_id,
            "region": region,
            "series": [{"time": f"{r['deal_ym']}-01", "value": float(r['permit_count'])} for r in rows]
        }

    # 2. 아파트 전세가율 (신규 적재 DB 우선 연동)
    if ind_id == "JEONSE_RATIO":
        clean_reg = clean_region_name(region)
        conn = get_master_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT deal_ym, jeonse_ratio 
            FROM macro_regional_indicators 
            WHERE region_name = ? AND jeonse_ratio IS NOT NULL AND deal_ym LIKE '%-%'
            ORDER BY deal_ym ASC
        """, (clean_reg,))
        rows = cur.fetchall()
        if rows:
            conn.close()
            return {
                "ind_id": ind_id,
                "region": region,
                "series": [{"time": f"{r['deal_ym']}-01", "value": round(float(r['jeonse_ratio']), 2)} for r in rows]
            }
        conn.close()

    # 3. 기존 기타 지표 (기준금리, 미분양, PIR 등)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT deal_ym, val FROM macro_indicator_stats WHERE indicator_id = ? AND region = ? ORDER BY deal_ym ASC", (ind_id, region))
    rows = cur.fetchall()
    if not rows:
        cur.execute("SELECT deal_ym, val FROM macro_indicator_stats WHERE indicator_id = ? AND region = '전국' ORDER BY deal_ym ASC", (ind_id,))
        rows = cur.fetchall()
    conn.close()
    return {"ind_id": ind_id, "region": region, "series": [{"time": f"{r['deal_ym'][:4]}-{r['deal_ym'][4:6]}-01", "value": float(r['val'])} for r in rows]}

@macro_router.get("/api/chart_data")
def get_chart_data(expr: str, cat: str = "84"):
    conn = get_db()
    cur = conn.cursor()

    def get_series_dict(target_sym: str, target_cat: str):
        if target_sym == "서울 전체":
            cur.execute("""
                SELECT deal_ym, 
                       ROUND(SUM(avg_price * trade_count) / SUM(trade_count), 1) as p
                FROM macro_monthly_stats
                WHERE symbol IN ('강남구', '서초구', '송파구', '강동구', '마포구', '용산구', '성동구', '광진구', '동대문구', '중랑구', '성북구', '강북구', '도봉구', '노원구', '은평구', '서대문구', '종로구', '중구', '양천구', '강서구', '구로구', '금천구', '영등포구', '동작구', '관악구')
                  AND area_cat = ?
                GROUP BY deal_ym
                ORDER BY deal_ym ASC
            """, (target_cat,))
        else:
            cur.execute("""
                SELECT deal_ym, avg_price as p
                FROM macro_monthly_stats
                WHERE symbol = ? AND area_cat = ?
                ORDER BY deal_ym ASC
            """, (target_sym, target_cat))
        rows = cur.fetchall()
        
        if not rows and target_cat != "ALL":
            if target_sym == "서울 전체":
                cur.execute("""
                    SELECT deal_ym, ROUND(SUM(avg_price * trade_count) / SUM(trade_count), 1) as p
                    FROM macro_monthly_stats
                    WHERE symbol IN ('강남구', '서초구', '송파구', '마포구', '용산구') AND area_cat = 'ALL'
                    GROUP BY deal_ym ORDER BY deal_ym ASC
                """)
            else:
                cur.execute("SELECT deal_ym, avg_price as p FROM macro_monthly_stats WHERE symbol = ? AND area_cat = 'ALL' ORDER BY deal_ym ASC", (target_sym,))
            rows = cur.fetchall()
        return {r["deal_ym"]: float(r["p"]) for r in rows}

    if "/" in expr:
        sym_a, sym_b = [s.strip() for s in expr.split("/", 1)]
        d_a = get_series_dict(sym_a, cat)
        d_b = get_series_dict(sym_b, cat)
        common = sorted(list(set(d_a.keys()) & set(d_b.keys())))
        series = [{"time": f"{ym[:4]}-{ym[4:6]}-01", "value": round(d_a[ym] / d_b[ym], 3)} for ym in common if d_b[ym] > 0]
    else:
        d_a = get_series_dict(expr.strip(), cat)
        series = [{"time": f"{ym[:4]}-{ym[4:6]}-01", "value": val} for ym, val in sorted(d_a.items())]

    conn.close()
    return {"expr": expr, "cat": cat, "series": series}

@macro_router.get("/api/indicator_regions")
def get_indicator_regions(ind_id: str):
    # 전국 17개 시도 표준 목록
    all_standard_regions = [
        "전국", "서울", "경기", "인천", "대구", "부산", "광주", "대전", "울산", "세종",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"
    ]
    
    # 신규 DB 연동 지표 (인허가, 전세가율)는 17개 시도 전체 100% 지원
    if ind_id in ["HOUSING_PERMIT", "PERMITS", "PERMIT", "JEONSE_RATIO"]:
        return {
            "ind_id": ind_id,
            "regions": [
                {
                    "value": reg,
                    "label": "전국 전체" if reg == "전국" else (f"{reg}광역시" if reg in ["대구", "부산", "인천", "광주", "대전", "울산"] else (f"{reg}특별시" if reg == "서울" else (f"{reg}특별자치시" if reg == "세종" else (f"{reg}도" if reg in ["경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남"] else f"{reg}특별자치도")))),
                    "available": True
                }
                for reg in all_standard_regions
            ]
        }

    # 기존 지표의 경우 원래 로직 유지
    groups = [
        ("전국",), ("서울 전체", "서울특별시", "서울"),
        ("부산광역시", "부산"), ("대구광역시", "대구"),
        ("인천광역시", "인천"), ("광주광역시", "광주"),
        ("대전광역시", "대전"), ("울산광역시", "울산"),
        ("세종특별자치시", "세종"), ("경기도", "경기"),
        ("강원특별자치도", "강원도", "강원"),
        ("충청북도", "충북"), ("충청남도", "충남"),
        ("전북특별자치도", "전라북도", "전북"),
        ("전라남도", "전남"), ("경상북도", "경북"),
        ("경상남도", "경남"), ("제주특별자치도", "제주도", "제주"),
    ]
    conn = get_db()
    try:
        available = {row[0] for row in conn.execute(
            "SELECT DISTINCT region FROM macro_indicator_stats "
            "WHERE indicator_id = ? AND val IS NOT NULL", (ind_id,)
        )}
    finally:
        conn.close()
    regions = []
    for aliases in groups:
        actual = next((name for name in aliases if name in available), None)
        regions.append({
            "value": actual or aliases[0],
            "label": "전국 전체" if aliases[0] == "전국" else aliases[0],
            "available": actual is not None,
        })
    return {"ind_id": ind_id, "regions": regions}

@macro_router.get("/view/macro", response_class=HTMLResponse)
def get_macro_view_page():
    html_file = os.path.join(os.path.dirname(__file__), "macro_view.html")
    with open(html_file, "r", encoding="utf-8") as f:
        return f.read()