import os
import re
import sqlite3
from functools import lru_cache
from datetime import datetime
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, Request
from html import escape
import logging
from fastapi.responses import HTMLResponse
import uvicorn

# Render 실행 환경(루트 디렉터리) 기준 상대 경로
DB_FILE = os.path.join(os.path.dirname(__file__), "apt_data_render_master.db")

def clean_apt_name(raw_name):
    if not raw_name: return ""
    return re.sub(r'\[.*?\]', '', raw_name).strip()

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute("SELECT DISTINCT apt_name FROM apt_trades ORDER BY apt_name ASC")
rows = c.fetchall()
CACHED_APT_NAMES = []
for r in rows:
    n = clean_apt_name(str(r[0]))
    if n and not re.match(r'^[\d\-\(\)]+$', n) and n not in CACHED_APT_NAMES:
        CACHED_APT_NAMES.append(n)
conn.close()

APT_COMPARE_RANKINGS = {
    "청라힐스자이": ["남산자이하늘채", "남산롯데캐슬센트럴스카이", "더샵디어엘로", "대신센트럴자이", "힐스테이트대구역", "수성범어W"],
    "더샵디어엘로": ["동대구역화성파크드림", "청라힐스자이", "동대구더샵센트럴시티", "이안센트럴D", "신천센트럴자이", "힐스테이트대구역", "남산자이하늘채"],
    "수성범어W": ["힐스테이트범어", "두산위브더제니스(대구 수성)", "e편한세상범어", "범어SKVIEW", "더샵디어엘로", "남산자이하늘채"],
    "힐스테이트대구역": ["대구역오페라W", "힐스테이트도원센트럴", "대구역유림노르웨이숲", "청라힐스자이", "더샵디어엘로", "남산자이하늘채"]
}
DEFAULT_RANK = ["수성범어W", "두산위브더제니스(대구 수성)", "더샵디어엘로", "청라힐스자이", "힐스테이트대구역", "남산자이하늘채"]

LAWD_CD_MAP = {
    "대구전체": ["27110", "27140", "27170", "27200", "27230", "27260", "27290", "27710"],
    "중구": ["27110"], "동구": ["27140"], "서구": ["27170"], "남구": ["27200"],
    "북구": ["27230"], "수성구": ["27260"], "달서구": ["27290"], "달성군": ["27710"]
}

from macro_router import macro_router
import urllib.request
import json
import urllib.parse

SUPABASE_URL = "https://hikwjqgjollisdistbif.supabase.co"
SUPABASE_KEY = "sb_publishable_eIzC8sNZ6gBe62KixTRm1w_1dE2dNG9"

def record_compare_pair(apt_list):
    valid_apts = sorted(list(set([a.strip() for a in apt_list if a and a.strip()])))
    if len(valid_apts) < 2: return
    for i in range(len(valid_apts)):
        for j in range(i + 1, len(valid_apts)):
            a, b = valid_apts[i], valid_apts[j]
            try:
                query = urllib.parse.urlencode({"apt_a": f"eq.{a}", "apt_b": f"eq.{b}", "select": "compare_count"})
                url = f"{SUPABASE_URL}/rest/v1/apt_compare_pairs?{query}"
                req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                
                current_cnt = data[0]['compare_count'] if data else 0
                payload = json.dumps({"apt_a": a, "apt_b": b, "compare_count": current_cnt + 1}).encode('utf-8')
                upsert_url = f"{SUPABASE_URL}/rest/v1/apt_compare_pairs"
                upsert_req = urllib.request.Request(upsert_url, data=payload, method="POST", headers={
                    "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"
                })
                urllib.request.urlopen(upsert_req, timeout=3)
            except Exception: pass

def get_real_top10_compared(apt_name):
    clean = clean_apt_name(apt_name)
    try:
        query_a = urllib.parse.urlencode({"or": f"(apt_a.eq.{clean},apt_b.eq.{clean})", "order": "compare_count.desc", "limit": "10", "select": "apt_a,apt_b,compare_count"})
        url = f"{SUPABASE_URL}/rest/v1/apt_compare_pairs?{query_a}"
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        result = []
        for row in data:
            partner = row['apt_b'] if row['apt_a'] == clean else row['apt_a']
            result.append(partner)
        return result
    except Exception: return []

app = FastAPI()

@app.post("/api/log-compare")
async def log_compare_api(payload: dict):
    apts = payload.get("apts", [])
    if apts and len(apts) >= 2: record_compare_pair(apts)
    return {"status": "ok"}

app.include_router(macro_router)

@app.get("/api/search-apt")
def search_apt(q: str = Query("")):
    query_str = q.strip().lower()
    if not query_str: return CACHED_APT_NAMES[:20]
    q_compact = query_str.replace(" ", "")
    keywords = query_str.split()
    matched = []
    for name in CACHED_APT_NAMES:
        name_lower = name.lower()
        if q_compact in name_lower.replace(" ", "") or all(k in name_lower for k in keywords):
            matched.append(name)
            if len(matched) >= 20: break
    return matched

@lru_cache(maxsize=128)
def query_chart_from_db(pure_name: str, months: int, area_type: str, exclude_direct: bool = False):
    conn = sqlite3.connect(DB_FILE)
    max_date_row = conn.execute("SELECT MAX(deal_date) FROM apt_trades").fetchone()
    if not max_date_row or not max_date_row[0]:
        conn.close()
        return None, None, []

    end_date = pd.to_datetime(max_date_row[0])
    start_date = end_date - pd.DateOffset(months=months)
    start_str = start_date.strftime("%Y-%m-%d")

    direct_cond = " AND (deal_type IS NULL OR deal_type != '직거래')" if exclude_direct else ""
    area_cond = ""
    params = [pure_name, pure_name, start_str]
    if area_type == "84": area_cond = "AND exclu_use_ar >= 83.0 AND exclu_use_ar <= 85.99"
    elif area_type == "59": area_cond = "AND exclu_use_ar >= 58.0 AND exclu_use_ar <= 60.99"

    query = f"""
        SELECT deal_date, deal_amount, exclu_use_ar, floor
        FROM apt_trades
        WHERE (apt_name = ? OR REPLACE(apt_name, ' ', '') = REPLACE(?, ' ', ''))
          AND deal_date >= ?
          {area_cond}{direct_cond}
        ORDER BY deal_date ASC
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return start_str, max_date_row[0], df.to_dict('records')

@app.get("/api/chart-data")
def get_chart_data(apt_name: str = Query(...), months: int = Query(12), area_type: str = Query("84"), exclude_direct: bool = Query(False)):
    pure_name = clean_apt_name(apt_name)
    start_str, max_date, raw_records = query_chart_from_db(pure_name, months, area_type, exclude_direct)
    
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    clean_k = pure_name.replace(" ", "").lower()
    cur.execute("SELECT built_year, built_str, units_str, type_info FROM apt_meta_master WHERE norm_name = ? OR apt_name = ?", (clean_k, pure_name))
    meta_row = cur.fetchone()
    if not meta_row:
        cur.execute("SELECT built_year, built_str, units_str, type_info FROM apt_meta_master WHERE norm_name LIKE ? LIMIT 1", (f"%{clean_k}%",))
        meta_row = cur.fetchone()

    if meta_row and meta_row[2] and meta_row[2] != "-":
        byear, bstr, ustr, tinfo = meta_row
    else:
        cur.execute("SELECT MIN(deal_date) FROM apt_trades WHERE apt_name = ? OR REPLACE(apt_name, ' ', '') = ?", (pure_name, clean_k))
        min_row = cur.fetchone()
        byear = int(min_row[0][:4]) if (min_row and min_row[0]) else 2020
        age = 2026 - byear + 1
        bstr, ustr, tinfo = f"{byear}년 ({age}년차)", "-", "전용 정보 확인중"
    conn.close()

    top10_list = get_real_top10_compared(pure_name)
    if not raw_records:
        return {
            "result": "empty", "dates": [], "prices": [], "ma": [], "upper": [], "lower": [], "details": [],
            "start_date": start_str, "built_date": f"{byear}-01-01",
            "stats": {"built": bstr, "units": ustr, "type_info": tinfo, "trade_count": 0, "max_price": "-", "max_info": "기간 내 거래 없음", "avg_price": "-", "latest_ma": "-", "dispersion": "-"},
            "top10": top10_list, "pure_name": pure_name
        }

    df = pd.DataFrame(raw_records)
    if area_type == "all":
        df['price'] = (df['deal_amount'] / (df['exclu_use_ar'] / 3.30578)).round(1)
        unit_suffix = "만원/평"
    else:
        df['price'] = (df['deal_amount'] / 10000.0).round(3)
        unit_suffix = "억"

    mean_val, std_val = df['price'].mean(), df['price'].std()
    if pd.notnull(mean_val) and mean_val > 0 and pd.notnull(std_val):
        cv = (std_val / mean_val) * 100.0
        if cv <= 3.5: disp_badge = f"{round(cv, 1)}% (매우 안정)"
        elif cv <= 6.5: disp_badge = f"{round(cv, 1)}% (안정)"
        elif cv <= 10.0: disp_badge = f"{round(cv, 1)}% (보통)"
        else: disp_badge = f"{round(cv, 1)}% (편차 큼)"
    else: disp_badge = "-"

    prices = df['price'].tolist()
    ma_list, upper_list, lower_list = [], [], []
    for i in range(len(prices)):
        window = prices[max(0, i - 19): i + 1]
        m, s = float(np.mean(window)), float(np.std(window))
        ma_list.append(round(m, 2))
        upper_list.append(round(m + (s * 2), 2))
        lower_list.append(round(m - (s * 2), 2))

    details = [{"excluUseAr": round(float(r['exclu_use_ar']), 2), "floor": int(r['floor']) if pd.notnull(r['floor']) else "-"} for _, r in df.iterrows()]
    max_idx = df['price'].idxmax()
    max_row = df.loc[max_idx]

    stats = {
        "built": bstr, "units": ustr, "type_info": tinfo, "trade_count": len(df),
        "max_price": f"{max_row['price']}{unit_suffix}",
        "max_info": f"계약일: {max_row['deal_date']} / {int(max_row['floor']) if pd.notnull(max_row['floor']) else '-'}층 ({round(float(max_row['exclu_use_ar']),1)}㎡)",
        "avg_price": f"{round(mean_val, 2)}{unit_suffix}",
        "latest_ma": f"{ma_list[-1]}{unit_suffix}" if ma_list else "-",
        "dispersion": disp_badge
    }

    return {
        "result": "ok", "dates": df['deal_date'].tolist(), "prices": prices, "ma": ma_list,
        "upper": upper_list, "lower": lower_list, "start_date": start_str, "built_date": f"{byear}-01-01",
        "details": details, "stats": stats, "top10": top10_list, "pure_name": pure_name
    }

@app.get("/api/rankings")
def get_rankings(year: int = Query(2026), rank_type: str = Query("price_max"), regions: str = Query("대구전체")):
    conn = sqlite3.connect(DB_FILE)
    lawd_codes = []
    if "대구전체" in regions: lawd_codes = LAWD_CD_MAP["대구전체"]
    else:
        for r in regions.split(","):
            r_clean = r.strip()
            if r_clean in LAWD_CD_MAP: lawd_codes.extend(LAWD_CD_MAP[r_clean])
    lawd_codes = list(set(lawd_codes)) if lawd_codes else LAWD_CD_MAP["대구전체"]
    placeholders = ",".join(["?"] * len(lawd_codes))
    where_extra = ""
    
    if rank_type == "price_max": order_col, metric_name = "COALESCE(s.max_price, 0) DESC", "단지 최고가"
    elif rank_type == "84_max": where_extra, order_col, metric_name = "AND s.max_84_price > 0", "s.max_84_price DESC", "국평(84) 최고가"
    elif rank_type == "84_avg": where_extra, order_col, metric_name = "AND s.avg_84_price > 0", "s.avg_84_price DESC", "국평(84) 평균가"
    elif rank_type == "59_max": where_extra, order_col, metric_name = "AND s.max_59_price > 0", "s.max_59_price DESC", "전용 59 최고가"
    elif rank_type == "59_avg": where_extra, order_col, metric_name = "AND s.avg_59_price > 0", "s.avg_59_price DESC", "전용 59 평균가"
    elif rank_type == "trade_cnt": order_col, metric_name = "s.total_trade_cnt DESC", "연간 거래량"
    elif rank_type == "pyeong_avg": order_col, metric_name = "COALESCE(s.avg_pyeong, 0) DESC", "평균 평당가"
    else: order_col, metric_name = "COALESCE(s.max_price, 0) DESC", "단지 최고가"

    units_select = "COALESCE(m.units_84_str, '-')" if "84" in rank_type else ("COALESCE(m.units_59_str, '-')" if "59" in rank_type else "COALESCE(m.units_str, '-')")
    query = f"""
        SELECT 
            s.apt_name, s.lawd_5, s.total_trade_cnt, s.trade_cnt_84, s.trade_cnt_59,
            COALESCE(s.max_price, 0) as max_price, COALESCE(s.avg_price, 0) as avg_price,
            COALESCE(s.avg_pyeong, 0) as avg_pyeong,
            COALESCE(s.max_84_price, 0) as max_84_price, COALESCE(s.avg_84_price, 0) as avg_84_price,
            COALESCE(s.max_59_price, 0) as max_59_price, COALESCE(s.avg_59_price, 0) as avg_59_price,
            s.max_p_date, s.max_p_area, s.max_p_pyeong_est, s.max_p_floor, COALESCE(s.dispersion_cv, 0) as dispersion_cv,
            COALESCE(m.built_str, '-') as built_str, {units_select} as units_str, COALESCE(m.type_info, '-') as type_info
        FROM apt_rank_yearly_summary s
        LEFT JOIN apt_meta_master m ON REPLACE(s.apt_name, ' ', '') = m.norm_name
        WHERE s.deal_year = ? AND s.lawd_5 IN ({placeholders}) {where_extra}
        ORDER BY {order_col} LIMIT 50
    """
    df = pd.read_sql_query(query, conn, params=[year] + lawd_codes)
    conn.close()

    lawd_to_gu = {"27110":"중구", "27140":"동구", "27170":"서구", "27200":"남구", "27230":"북구", "27260":"수성구", "27290":"달서구", "27710":"달성군"}
    results = []
    for idx, r in df.iterrows():
        gu = lawd_to_gu.get(str(r['lawd_5']), "대구")
        display_trade_cnt = int(r['trade_cnt_84']) if "84" in rank_type else (int(r['trade_cnt_59']) if "59" in rank_type else int(r['total_trade_cnt']))
        tooltip_info = f"계약일: {r['max_p_date']} | {r['max_price']}억 | 약 {r['max_p_pyeong_est']}평형(전용 {r['max_p_area']}㎡) | {r['max_p_floor']}층" if rank_type == "price_max" and r['max_p_date'] else ""

        if rank_type == "price_max": metric_val = f"{r['max_price']} 억"
        elif rank_type == "84_max": metric_val = f"{r['max_84_price']} 억"
        elif rank_type == "84_avg": metric_val = f"{r['avg_84_price']} 억"
        elif rank_type == "59_max": metric_val = f"{r['max_59_price']} 억"
        elif rank_type == "59_avg": metric_val = f"{r['avg_59_price']} 억"
        elif rank_type == "trade_cnt": metric_val = f"{int(r['total_trade_cnt']):,} 건"
        elif rank_type == "pyeong_avg": metric_val = f"{r['avg_pyeong']:,.1f} 만원/평"
        else: metric_val = f"{r['max_price']} 억"

        cv_val = float(r['dispersion_cv'])
        disp_badge = "-" if cv_val <= 0 or r['total_trade_cnt'] < 2 else (f"{cv_val:.1f}% (매우 안정)" if cv_val <= 3.5 else (f"{cv_val:.1f}% (안정)" if cv_val <= 6.5 else (f"{cv_val:.1f}% (보통)" if cv_val <= 10.0 else f"{cv_val:.1f}% (편차 큼)")))

        results.append({
            "rank": idx + 1, "apt_name": r['apt_name'], "region": f"대구 {gu}", "metric_name": metric_name, "metric_val": metric_val,
            "tooltip_info": tooltip_info, "dispersion": disp_badge, "trade_cnt": display_trade_cnt,
            "built_str": r['built_str'], "units_str": r['units_str'], "type_info": r['type_info']
        })
    return results

INSIGHT_CATEGORIES = {
    "real_estate": "🏢 부동산 분석",
    "stock_macro": "📈 주식·매크로",
    "personal_finance": "💡 생활금융",
}
INSIGHT_CSS = '\n    .insight-filters {display:flex;gap:8px;flex-wrap:wrap;margin:20px 0 28px}\n    .insight-filter {border:1px solid #cbd5e1;border-radius:24px;padding:10px 18px;background:white;color:#475569;cursor:pointer;text-decoration:none;font:inherit}\n    .insight-filter.active {background:#0f172a;color:white;border-color:#0f172a}\n    .insight-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}\n    .insight-card {border:1px solid #e2e8f0;border-radius:18px;overflow:hidden;background:white;transition:transform .2s,box-shadow .2s;min-width:0}\n    .insight-card:hover {transform:translateY(-4px);box-shadow:0 12px 30px #0f172a12}\n    .insight-card a {display:block;color:inherit;text-decoration:none}\n    .insight-card a:focus-visible {outline:3px solid #2563eb;outline-offset:-3px}\n    .insight-cover {aspect-ratio:16/9;background:linear-gradient(135deg,#dbeafe,#eff6ff);display:grid;place-items:center;overflow:hidden;font-size:44px;color:#334155}\n    .insight-cover[data-category="stock_macro"] {background:linear-gradient(135deg,#d1fae5,#ecfdf5)}\n    .insight-cover[data-category="personal_finance"] {background:linear-gradient(135deg,#fef3c7,#fffbeb)}\n    .insight-cover img {width:100%;height:100%;object-fit:cover;grid-area:1/1}\n    .insight-card-body {padding:22px}\n    .insight-badge {display:inline-block;font-size:12px;font-weight:700;color:#0369a1;background:#f0f9ff;border-radius:6px;padding:5px 9px}\n    .insight-card h2 {font-size:20px;line-height:1.5;margin:12px 0 8px;overflow-wrap:anywhere}\n    .insight-excerpt {color:#64748b;font-size:14px;line-height:1.7;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:3.4em;margin:0 0 22px;overflow-wrap:anywhere}\n    .insight-meta {display:flex;justify-content:space-between;gap:12px;color:#64748b;font-size:12px}\n    .insight-status {grid-column:1/-1;padding:48px;text-align:center;color:#64748b}\n    .insight-quick {margin:0 22px 20px;border:0;background:none;color:#0369a1;cursor:pointer;padding:0}\n    @media(max-width:1000px){.insight-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}\n    @media(max-width:620px){.insight-grid{grid-template-columns:1fr}.board-header{flex-wrap:wrap;gap:12px}}\n'

def insight_public_posts(params):
    query = {"select": "*", "board_type": "eq.insight", **params}
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/posts?{urllib.parse.urlencode(query)}",
        headers={"apikey": SUPABASE_KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        posts = json.loads(response.read().decode("utf-8"))
    if not isinstance(posts, list):
        raise ValueError("Unexpected posts response")
    return posts

def insight_category(post):
    category = post.get("category")
    return category if category in INSIGHT_CATEGORIES else "real_estate"

def insight_images(post):
    urls = post.get("image_urls")
    if not isinstance(urls, list):
        return []
    valid = []
    for value in urls:
        if not isinstance(value, str):
            continue
        try:
            parsed = urllib.parse.urlsplit(value)
            if parsed.scheme in ("https", "http") and parsed.netloc:
                valid.append(value)
        except ValueError:
            pass
    return valid

from html.parser import HTMLParser


class InsightHTML(HTMLParser):
    """Allow Quill markup while excluding executable tags/attributes."""
    tags = set('p br strong b em i u s strike blockquote pre code h1 h2 h3 h4 h5 h6 ol ul li span div a img sub sup'.split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.images = set()

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            return
        clean = []
        for key, value in attrs:
            value = value or ''
            if key in ('src', 'href') and ((tag == 'img' and key == 'src') or (tag == 'a' and key == 'href')):
                try:
                    parsed = urllib.parse.urlsplit(value.strip())
                except ValueError:
                    continue
                if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                    continue
                if tag == 'img':
                    self.images.add(value)
                clean.append((key, value))
            elif key in ('width', 'height') and tag == 'img' and re.fullmatch(r'[0-9]{1,5}', value):
                clean.append((key, value))
            elif key in ('alt', 'title'):
                clean.append((key, value))
            elif key == 'class':
                classes = [c for c in value.split() if re.fullmatch(r'ql-(?:align-(?:center|right|justify)|indent-[1-8]|size-(?:small|large|huge)|font-(?:serif|monospace)|direction-rtl|syntax)', c)]
                if classes:
                    clean.append((key, ' '.join(classes)))
            elif key == 'style':
                styles = []
                for declaration in value.split(';'):
                    prop, sep, val = declaration.partition(':')
                    prop, val = prop.strip().lower(), val.strip()
                    if prop in ('color', 'background-color') and re.fullmatch(r'(?:#[0-9a-fA-F]{3,8}|[a-zA-Z]+|rgba?\([0-9.,% ]+\))', val):
                        styles.append(prop + ':' + val)
                if styles:
                    clean.append(('style', ';'.join(styles)))
        self.parts.append('<' + tag + ''.join(' ' + k + '="' + escape(v, quote=True) + '"' for k, v in clean) + '>')

    def handle_endtag(self, tag):
        if tag in self.tags and tag not in ('img', 'br'):
            self.parts.append('</' + tag + '>')

    def handle_data(self, data):
        self.parts.append(escape(data))


def insight_render_content(content):
    parser = InsightHTML()
    if not re.search(r'<(?:p|div|h[1-6]|img|ul|ol|blockquote|pre)(?:\s|>)', content, re.I):
        return escape(content), set()
    parser.feed(content)
    parser.close()
    return ''.join(parser.parts), parser.images


def insight_document(request, title, description, body, path, metadata="", status=200):
    base = os.environ.get("SITE_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    url = escape(base + path, quote=True)
    robots = '<meta name="robots" content="noindex">' if status != 200 else ''
    html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} | TECH REALTY INSIGHT</title>
<meta name="description" content="{escape(description, quote=True)}">
<link rel="canonical" href="{url}"><meta property="og:url" content="{url}">
<meta property="og:title" content="{escape(title, quote=True)}">
<meta property="og:description" content="{escape(description, quote=True)}">
<meta property="og:locale" content="ko_KR">{robots}{metadata}
<style>{INSIGHT_CSS}
*{{box-sizing:border-box}}body{{margin:0;background:#f8fafc;color:#0f172a;font-family:system-ui,sans-serif}}
main{{max-width:1160px;margin:auto;padding:40px 22px 80px}}header{{border-bottom:1px solid #e2e8f0;padding:20px 24px;background:white}}
a{{color:#0369a1}}header a{{text-decoration:none;font-weight:800}}h1{{font-size:clamp(28px,5vw,42px);line-height:1.4;overflow-wrap:anywhere}}
.insight-article{{max-width:800px;margin:auto;background:white;padding:clamp(20px,4vw,48px);border-radius:18px}}
.article-content{{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.95;font-size:17px;margin:32px 0}}
.article-content img{{max-width:100%;height:auto}}
.article-content .ql-align-center{{text-align:center}}
.article-content .ql-align-right{{text-align:right}}
.article-content .ql-align-justify{{text-align:justify}}
.article-images img{{display:block;max-width:100%;height:auto;margin:24px auto;border-radius:12px}}
.article-meta{{color:#64748b;font-size:14px;display:flex;gap:16px;flex-wrap:wrap}}
footer{{margin-top:40px;color:#64748b;font-size:13px}}
</style><link rel="stylesheet" href="https://cdn.quilljs.com/1.3.6/quill.snow.css"></head>
<body><header><a href="/">TECH REALTY INSIGHT</a></header><main>{body}
<footer><a href="/insight">투자 인사이트 목록</a> · <a href="/#insight">대시보드로 돌아가기</a></footer></main></body></html>'''
    return HTMLResponse(html, status_code=status)

def insight_unavailable(request):
    logging.getLogger(__name__).warning("Public insight data could not be loaded")
    response = insight_document(request, "잠시 후 다시 시도해 주세요", "게시글을 불러올 수 없습니다.",
        '<h1>게시글을 불러올 수 없습니다.</h1><p>잠시 후 다시 접속해 주세요.</p>', request.url.path, status=503)
    response.headers["Retry-After"] = "60"
    return response

@app.get("/insight", response_class=HTMLResponse)
def insight_index(request: Request, category: str = "all", page: int = Query(1, ge=1)):
    if category not in INSIGHT_CATEGORIES and category != "all":
        return insight_document(request, "분류를 찾을 수 없습니다", "", '<h1>분류를 찾을 수 없습니다.</h1>', '/insight', status=404)
    params = {"order": "created_at.desc,id.desc", "limit": "25", "offset": str((page - 1) * 24)}
    if category == "real_estate":
        params["or"] = "(category.eq.real_estate,category.is.null)"
    elif category != "all":
        params["category"] = f"eq.{category}"
    try:
        posts = insight_public_posts(params)
    except Exception:
        return insight_unavailable(request)
    filters = ''.join(f'<a class="insight-filter{ " active" if key == category else ""}" href="/insight?category={key}">{label}</a>'
        for key, label in {"all": "전체", **INSIGHT_CATEGORIES}.items())
    cards = []
    for post in posts[:24]:
        cat = insight_category(post)
        label = INSIGHT_CATEGORIES[cat]
        title = escape(str(post.get("title") or "제목 없음"))
        images = insight_images(post)
        cover = f'<img src="{escape(images[0], quote=True)}" alt="{title}" loading="lazy">' if images else label.split()[0]
        href = '/insight/' + urllib.parse.quote(str(post["id"]), safe='')
        summary = escape(' '.join(str(post.get("content") or '').split())[:240])
        date = escape(str(post.get("created_at") or '')[:10])
        views = escape(str(post.get("views") or 0))
        cards.append(f'<article class="insight-card"><a href="{href}"><div class="insight-cover" data-category="{cat}">{cover}</div><div class="insight-card-body"><span class="insight-badge">{label}</span><h2>{title}</h2><p class="insight-excerpt">{summary}</p><div class="insight-meta"><time>{date}</time><span>조회 {views}</span></div></div></a></article>')
    paging = ''
    if page > 1:
        paging += f'<a href="/insight?category={category}&amp;page={page-1}">← 이전</a> '
    if len(posts) > 24:
        paging += f'<a href="/insight?category={category}&amp;page={page+1}">다음 →</a>'
    body = '<h1>투자 인사이트</h1><p>데이터로 읽는 시장, 일상에 도움이 되는 금융 이야기.</p>'
    body += f'<nav class="insight-filters" aria-label="카테고리">{filters}</nav><div class="insight-grid">' + (''.join(cards) or '<p>등록된 글이 없습니다.</p>') + f'</div><nav style="margin-top:28px" aria-label="페이지">{paging}</nav>'
    path = '/insight' + ('?' + urllib.parse.urlencode({"category": category, "page": page}) if category != 'all' or page != 1 else '')
    return insight_document(request, '투자 인사이트', '부동산 분석, 주식·매크로, 생활금융 칼럼을 만나보세요.', body, path)

@app.get("/insight/{post_id}", response_class=HTMLResponse)
def insight_post(request: Request, post_id: str):
    if not re.fullmatch(r"(?:[0-9]{1,20}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})", post_id):
        return insight_document(request, "글을 찾을 수 없습니다", "", '<h1>글을 찾을 수 없습니다.</h1>', request.url.path, status=404)
    try:
        posts = insight_public_posts({"id": f"eq.{post_id}", "limit": "1"})
    except Exception:
        return insight_unavailable(request)
    if not posts:
        return insight_document(request, "글을 찾을 수 없습니다", "", '<h1>글을 찾을 수 없습니다.</h1>', request.url.path, status=404)
    post = posts[0]
    title = str(post.get("title") or "제목 없음")
    content = str(post.get("content") or "")
    rendered_content, inline_images = insight_render_content(content)
    description = ' '.join(re.sub(r'<[^>]*>', '', content).split())[:160]
    category = INSIGHT_CATEGORIES[insight_category(post)]
    date = str(post.get("created_at") or '')
    author = str(post.get("nickname") or '운영자')
    images = insight_images(post)
    figures = ''.join(f'<img src="{escape(url, quote=True)}" alt="{escape(title, quote=True)} — 첨부 이미지 {i+1}" loading="lazy">' for i, url in enumerate(images) if url not in inline_images)
    body = f'<article class="insight-article"><span class="insight-badge">{category}</span><h1>{escape(title)}</h1><div class="article-meta"><span>{escape(author)}</span><time datetime="{escape(date, quote=True)}">{escape(date[:10])}</time><span>조회 {escape(str(post.get("views") or 0))}</span></div><div class="article-content ql-editor">{rendered_content}</div><div class="article-images">{figures}</div></article>'
    metadata = '<meta property="og:type" content="article">'
    if images:
        metadata += f'<meta property="og:image" content="{escape(images[0], quote=True)}">'
    if date:
        metadata += f'<meta property="article:published_time" content="{escape(date, quote=True)}">'
    structured = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": title,
                  "description": description, "articleSection": category, "author": {"@type": "Person", "name": author}}
    if date:
        structured["datePublished"] = date
    if images:
        structured["image"] = images
    metadata += '<script type="application/ld+json">' + json.dumps(structured, ensure_ascii=True).replace('<', '\\u003c') + '</script>'
    return insight_document(request, title, description, body, '/insight/' + post_id, metadata)

UI_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>TECH REALTY INSIGHT - 실거래가 기술적 분석실</title>
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
  <!-- Quill 에디터 라이브러리 CDN -->
  <link href="https://cdn.quilljs.com/1.3.6/quill.snow.css" rel="stylesheet">
  <script src="https://cdn.quilljs.com/1.3.6/quill.min.js"></script>
  <style>
    :root { --primary: #2563eb; --bg: #f8fafc; --card: #ffffff; --border: #e2e8f0; --text: #0f172a; --sub: #64748b; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 0; background: var(--bg); color: var(--text); }
    .global-nav { background: #0f172a; color: #fff; padding: 0 24px; height: 60px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 10000; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
    .logo-area { font-size: 17px; font-weight: 800; color: #38bdf8; cursor: pointer; display: flex; align-items: center; gap: 8px; white-space: nowrap; }
    .nav-links { display: flex; gap: 4px; height: 100%; align-items: center; }
    .nav-btn { background: transparent; border: none; color: #94a3b8; font-size: 13.5px; font-weight: 600; padding: 0 12px; height: 38px; border-radius: 8px; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
    .nav-btn:hover { color: #fff; background: rgba(255,255,255,0.08); }
    .nav-btn.active { color: #38bdf8; background: rgba(56,189,248,0.12); font-weight: 700; }
    .main-wrapper { max-width: 1440px; margin: 24px auto; padding: 0 20px 40px; }
    .page-view { display: none; }
    .page-view.active { display: block; }

    .hero-banner { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: #fff; border-radius: 18px; padding: 36px; margin-bottom: 24px; }
    .hero-banner h1 { font-size: 24px; font-weight: 800; margin-bottom: 8px; }
    .hero-banner p { font-size: 14.5px; color: #94a3b8; line-height: 1.6; }
    .hub-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
    .hub-card { background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 22px; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 16px rgba(0,0,0,0.04); }
    .hub-card:hover { transform: translateY(-4px); box-shadow: 0 12px 28px rgba(37,99,235,0.1); border-color: var(--primary); }
    .hub-title { font-size: 18px; font-weight: 700; color: #1e293b; margin-bottom: 8px; }
    .hub-desc { font-size: 13px; color: #64748b; line-height: 1.5; margin-bottom: 16px; }
    .hub-action { font-size: 13px; font-weight: 700; color: var(--primary); }

    .ranking-header { background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 22px 24px; margin-bottom: 20px; }
    .year-selection-bar { display: flex; align-items: center; gap: 8px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 16px; border-bottom: 1px solid #f1f5f9; }
    .year-label { font-size: 13.5px; font-weight: 800; color: #0f172a; white-space: nowrap; margin-right: 4px; }
    .btn-year { padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 700; border: 1px solid #cbd5e1; background: #fff; color: #475569; cursor: pointer; white-space: nowrap; }
    .btn-year.active { background: #2563eb; color: #fff; border-color: #2563eb; }
    .rank-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    .rank-tab-btn { padding: 8px 16px; border-radius: 9px; font-size: 13px; font-weight: 700; border: 1px solid #cbd5e1; background: #fff; color: #475569; cursor: pointer; }
    .rank-tab-btn.active { background: #0f172a; color: #fff; border-color: #0f172a; }
    .filter-section { border-top: 1px solid #f1f5f9; padding-top: 14px; }
    .region-parent-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }
    .region-checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 13.5px; font-weight: 600; color: #1e293b; cursor: pointer; }
    .btn-subregion-toggle { font-size: 12px; font-weight: 700; color: #e11d48; background: #fff1f2; border: 1px solid #fecdd3; padding: 3px 8px; border-radius: 6px; cursor: pointer; }
    .subregion-container { background: #f8fafc; border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; display: flex; gap: 16px; flex-wrap: wrap; }
    .subregion-item { display: flex; align-items: center; gap: 5px; font-size: 13px; font-weight: 500; color: #334155; cursor: pointer; }
    .ranking-table-card { background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 22px; position: relative; }
    .ranking-loading-overlay { position: absolute; inset: 0; background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(2px); border-radius: 16px; display: none; flex-direction: column; align-items: center; justify-content: center; z-index: 100; gap: 12px; }
    .loading-hourglass { font-size: 34px; animation: spinHourglass 1.4s infinite ease-in-out; }
    @keyframes spinHourglass { 0% { transform: rotate(0deg); } 50% { transform: rotate(180deg); } 100% { transform: rotate(360deg); } }
    .loading-text { font-size: 14px; font-weight: 700; color: #1e293b; }
    table.rank-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
    table.rank-table th { background: #f8fafc; padding: 12px 10px; text-align: center; font-weight: 700; color: #475569; border-bottom: 2px solid #e2e8f0; }
    table.rank-table td { padding: 12px 10px; text-align: center; border-bottom: 1px solid #f1f5f9; }
    table.rank-table tr:hover { background-color: #f8fafc; }
    .rank-num { font-weight: 800; font-size: 15px; width: 50px; }
    .rank-num.top1 { color: #e11d48; }
    .rank-num.top2 { color: #f97316; }
    .rank-num.top3 { color: #eab308; }
    .apt-name-click { font-weight: 700; color: #1e293b; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
    .apt-name-click:hover { color: var(--primary); }
    .metric-hover-box { position: relative; display: inline-block; cursor: help; }
    .metric-tooltip { visibility: hidden; opacity: 0; position: absolute; bottom: 125%; left: 50%; transform: translateX(-50%); background-color: #0f172a; color: #f8fafc; padding: 8px 12px; border-radius: 8px; font-size: 12px; font-weight: 600; white-space: nowrap; box-shadow: 0 8px 24px rgba(0,0,0,0.3); z-index: 5000; transition: opacity 0.15s ease-in-out; pointer-events: none; }
    .metric-tooltip::after { content: ""; position: absolute; top: 100%; left: 50%; margin-left: -5px; border-width: 5px; border-style: solid; border-color: #0f172a transparent transparent transparent; }
    .metric-hover-box:hover .metric-tooltip { visibility: visible; opacity: 1; }
    .help-tooltip-trigger { display: inline-flex; align-items: center; justify-content: center; width: 15px; height: 15px; border-radius: 50%; background: #94a3b8; color: #fff; font-size: 10.5px; font-weight: 700; cursor: help; margin-left: 4px; position: relative; vertical-align: middle; }
    .help-tooltip-trigger:hover { background: var(--primary); }
    .help-tooltip-box { display: none; position: absolute; right: 0; top: 120%; width: 420px; max-height: 500px; overflow-y: auto; background: #0f172a; color: #f8fafc; border-radius: 12px; padding: 16px 18px; font-size: 12px; line-height: 1.55; z-index: 3000; box-shadow: 0 12px 32px rgba(0,0,0,0.35); text-align: left; }
    .help-tooltip-trigger:hover .help-tooltip-box { display: block; }
    .tooltip-title { font-weight: 800; color: #38bdf8; font-size: 13.5px; margin-bottom: 6px; }
    .tooltip-def { background: #1e293b; padding: 8px 10px; border-radius: 8px; border-left: 3px solid #38bdf8; font-size: 12px; margin-bottom: 10px; color: #e2e8f0; }

    .container { max-width: 1440px; margin: 0 auto; background: var(--card); padding: 28px; border-radius: 18px; box-shadow: 0 6px 24px rgba(0,0,0,0.06); }
    .header-area { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #f1f5f9; padding-bottom: 16px; flex-wrap: wrap; gap: 12px; }
    h2 { font-size: 22px; font-weight: 700; color: #1e293b; }
    .area-filter-bar { display: inline-flex; background: #e2e8f0; padding: 3px; border-radius: 10px; gap: 4px; }
    .filter-btn { padding: 7px 15px; border-radius: 8px; font-size: 13.5px; font-weight: 600; border: none; background: transparent; color: var(--sub); cursor: pointer; }
    .filter-btn.active { background: #fff; color: var(--primary); box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
    .selector-container { background: #f8fafc; border: 1px solid var(--border); border-radius: 14px; padding: 16px; margin-bottom: 18px; }
    .slot-config-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 14px; font-weight: 600; color: #334155; }
    .search-inputs-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
    .search-slot-wrapper { position: relative; width: 100%; }
    .select-item { display: flex; align-items: center; gap: 10px; background: #fff; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border); transition: border-color 0.2s; }
    .select-item:focus-within { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(37,99,235,0.12); }
    .color-pill { width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }
    input.search-input { width: 100%; border: none; outline: none; font-size: 13.5px; font-weight: 600; background: transparent; color: #0f172a; }
    .autocomplete-dropdown { position: absolute; top: calc(100% + 4px); left: 0; right: 0; background: #ffffff; border: 1px solid var(--border); border-radius: 10px; max-height: 250px; overflow-y: auto; z-index: 1000; box-shadow: 0 8px 24px rgba(0,0,0,0.12); display: none; }
    .ac-item { padding: 9px 14px; font-size: 13px; font-weight: 500; cursor: pointer; border-bottom: 1px solid #f8fafc; display: flex; align-items: center; justify-content: space-between; }
    .ac-item:hover { background-color: #f1f5f9; color: var(--primary); font-weight: 600; }
    .ac-item.ac-none { background-color: #fff1f2; color: #e11d48; font-weight: 700; border-bottom: 1px solid #fecdd3; }
    .ac-item.ac-disabled { opacity: 0.45; cursor: not-allowed; background-color: #f8fafc; }
    .toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
    .tool-group { display: flex; align-items: center; gap: 10px; }
    select.period-select { padding: 7px 12px; font-size: 13.5px; border-radius: 8px; border: 1px solid #cbd5e1; background: #fff; font-weight: 600; }
    .btn-toggle { padding: 6px 14px; font-size: 13px; font-weight: 600; border-radius: 8px; border: 1px solid var(--border); background: #fff; cursor: pointer; transition: all 0.2s; }
    .btn-toggle.active { background: #0284c7; color: #fff; border-color: #0284c7; }
    .btn-reset-zoom { padding: 6px 12px; font-size: 12.5px; font-weight: 700; border-radius: 8px; border: 1px solid #cbd5e1; background: #f8fafc; color: #334155; cursor: pointer; }
    .btn-reset-zoom:hover { background: #e2e8f0; color: #0f172a; }
    .dashboard-body { display: flex; gap: 20px; align-items: flex-start; margin-bottom: 28px; }
    .chart-section { flex: 1 1 60%; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
    .chart-box { position: relative; height: 580px; background: #fff; border: 1px solid var(--border); border-radius: 14px; padding: 16px; cursor: grab; }
    .chart-box:active { cursor: grabbing; }
    .chart-loading-overlay { position: absolute; inset: 0; background: rgba(255, 255, 255, 0.82); backdrop-filter: blur(2px); border-radius: 14px; display: none; flex-direction: column; align-items: center; justify-content: center; z-index: 50; gap: 12px; }
    .chart-guide-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px 18px; }
    .guide-title { font-size: 13px; font-weight: 700; color: #334155; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
    .guide-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; font-size: 12px; }
    .guide-item { background: #fff; padding: 10px 12px; border-radius: 8px; border: 1px solid #e2e8f0; line-height: 1.45; }
    .guide-item strong { display: block; font-size: 12.5px; margin-bottom: 4px; }
    .right-side-panel { flex: 1 1 40%; min-width: 360px; display: flex; flex-direction: column; gap: 16px; }
    .compare-panel { background: #ffffff; border: 1px solid var(--border); border-radius: 14px; padding: 18px; }
    .compare-title { font-size: 15.5px; font-weight: 700; color: #1e293b; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; }
    table.compare-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    table.compare-table th, table.compare-table td { padding: 9px 6px; text-align: center; border-bottom: 1px solid #f1f5f9; }
    table.compare-table th.metric-col { text-align: left; font-weight: 700; color: #475569; background: #f8fafc; width: 34%; padding-left: 8px; }
    .type-info-cell { font-size: 11.5px; line-height: 1.4; color: #475569; word-break: keep-all; }
    .top10-panel { background: #f8fafc; border: 1px solid var(--border); border-radius: 14px; padding: 18px; }
    .top10-title { font-size: 14.5px; font-weight: 700; color: #1e293b; margin-bottom: 10px; }
    .top10-tabs { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
    .top10-tab-btn { padding: 5px 10px; font-size: 12px; font-weight: 600; border-radius: 6px; border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
    .top10-tab-btn.active { background: #0f172a; color: #fff; border-color: #0f172a; }
    .top10-list { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .top10-item { font-size: 12px; color: #334155; padding: 6px 8px; background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; }
    .recommend-box, .recommend-card, .recommend-container, [id*="recommend"], [class*="recommend"], .compare-rec-box, .rec-card { display: none !important; }

    #nicknameModal { border:1px solid #475569; border-radius:16px; padding:28px; width:min(400px, calc(100vw - 48px)); box-sizing:border-box; background:#0f172a; color:#f8fafc; margin:auto; }
    #nicknameModal::backdrop { background:rgba(2,6,23,.75); }
    #nicknameModal input { box-sizing:border-box; width:100%; padding:12px; margin:12px 0; border:1px solid #64748b; border-radius:8px; background:#1e293b; color:white; font-size:16px; }
    #nicknameModal button { padding:9px 14px; border:0; border-radius:8px; cursor:pointer; }
    #nicknameModal button:disabled { opacity:.5; cursor:wait; }
    #nicknameMessage { color:#fca5a5; min-height:24px; font-size:13px; }

    /* 게시판 & 단지이야기 전용 스타일 */
    .board-container { background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.03); }
    .board-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; border-bottom: 1.5px solid #f1f5f9; padding-bottom: 16px; }
    .board-title-text { font-size: 20px; font-weight: 800; color: #0f172a; display: flex; align-items: center; gap: 8px; }
    .region-pills-bar { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid #f1f5f9; }
    .region-pill { padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 700; border: 1px solid #e2e8f0; background: #fff; color: #475569; cursor: pointer; transition: all 0.15s; }
    .region-pill:hover { background: #f1f5f9; }
    .region-pill.active { background: #2563eb; color: #fff; border-color: #2563eb; }
    .btn-write-post { background: #2563eb; color: #fff; border: none; border-radius: 8px; padding: 8px 16px; font-size: 13.5px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px; }
    .btn-write-post:hover { background: #1d4ed8; }
    table.board-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    table.board-table th { background: #f8fafc; padding: 12px 10px; text-align: center; font-weight: 700; color: #475569; border-bottom: 2px solid #e2e8f0; }
    table.board-table td { padding: 12px 10px; text-align: center; border-bottom: 1px solid #f1f5f9; }
    table.board-table tr:hover { background-color: #f8fafc; }
    .post-title-link { color: #1e293b; font-weight: 600; text-decoration: none; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
    .post-title-link:hover { color: #2563eb; text-decoration: underline; }
    .img-badge { font-size: 11px; background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; padding: 1px 5px; border-radius: 4px; font-weight: 700; }
    .region-badge { font-size: 11.5px; background: #f1f5f9; color: #475569; padding: 2px 7px; border-radius: 4px; font-weight: 700; margin-right: 6px; }

    #writeModal { border:1px solid #475569; border-radius:16px; padding:28px; width:min(900px, calc(100vw - 32px)); box-sizing:border-box; background:#ffffff; color:#0f172a; margin:auto; box-shadow: 0 20px 40px rgba(0,0,0,0.3); }
    #writeModal::backdrop { background:rgba(15,23,42,.75); }
    .form-group { margin-bottom: 14px; }
    .form-label { font-size: 13.5px; font-weight: 700; color: #334155; margin-bottom: 6px; display: block; }
    .form-control { width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; outline: none; }
    .form-control:focus { border-color: #2563eb; }
    .image-preview-grid { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
    .img-preview-item { width: 80px; height: 80px; border-radius: 8px; border: 1px solid #cbd5e1; object-fit: cover; }
    .post-detail-box { display: none; margin-top: 20px; border-top: 2px solid #0f172a; padding-top: 20px; }
    .post-detail-title { font-size: 22px; font-weight: 800; color: #0f172a; margin-bottom: 8px; }
    .post-detail-meta { font-size: 13px; color: #64748b; margin-bottom: 24px; display: flex; gap: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 14px; }
    .post-detail-content { font-size: 15px; line-height: 1.8; color: #1e293b; white-space: pre-wrap; margin-bottom: 30px; }
    .post-detail-images { display: flex; flex-direction: column; gap: 14px; margin-bottom: 30px; }
    .post-detail-images img { max-width: 100%; border-radius: 10px; border: 1px solid #e2e8f0; }
    .comments-section { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
    .comments-title { font-size: 15px; font-weight: 800; color: #0f172a; margin-bottom: 14px; }
    .comment-item { padding: 12px 0; border-bottom: 1px solid #e2e8f0; font-size: 13.5px; }
    .comment-meta { font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 4px; display: flex; justify-content: space-between; }
    .comment-body { color: #1e293b; line-height: 1.5; }
    .comment-form { display: flex; gap: 8px; margin-top: 16px; }
    .comment-input { flex: 1; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13.5px; }

    /* 호갱노노/직방 스타일 단지 이야기 모달 팝업 */
    #aptStoryModal { border:1px solid #cbd5e1; border-radius:20px; padding:0; width:min(720px, calc(100vw - 32px)); max-height:88vh; box-sizing:border-box; background:#ffffff; color:#0f172a; margin:auto; box-shadow:0 24px 48px rgba(0,0,0,0.3); overflow:hidden; }
    #aptStoryModal::backdrop { background:rgba(15,23,42,.75); }
    .apt-story-header { background:#0f172a; color:#fff; padding:18px 24px; display:flex; justify-content:space-between; align-items:center; }
    .apt-story-body { padding:22px; max-height:calc(88vh - 75px); overflow-y:auto; }
    .apt-gallery-box { margin-bottom:20px; }
    .apt-gallery-scroll { display:flex; gap:10px; overflow-x:auto; padding-bottom:8px; }
    .apt-gallery-thumb { width:120px; height:90px; border-radius:8px; object-fit:cover; border:1px solid #e2e8f0; flex-shrink:0; cursor:pointer; }
    .story-card { background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:16px; margin-bottom:14px; box-shadow:0 2px 8px rgba(0,0,0,0.03); }
    .story-card-meta { display:flex; justify-content:space-between; font-size:12.5px; color:#64748b; margin-bottom:8px; }
    .story-card-title { font-size:16px; font-weight:700; color:#0f172a; margin-bottom:6px; }
    .story-card-content { font-size:14px; line-height:1.6; color:#334155; white-space:pre-wrap; }
    .story-card-photos { display:flex; gap:8px; margin-top:10px; overflow-x:auto; }
    .story-card-photo { width:90px; height:90px; border-radius:8px; object-fit:cover; border:1px solid #e2e8f0; }

    .insight-filters {display:flex;gap:8px;flex-wrap:wrap;margin:20px 0 28px}
    .insight-filter {border:1px solid #cbd5e1;border-radius:24px;padding:10px 18px;background:white;color:#475569;cursor:pointer;text-decoration:none;font:inherit}
    .insight-filter.active {background:#0f172a;color:white;border-color:#0f172a}
    .insight-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}
    .insight-card {border:1px solid #e2e8f0;border-radius:18px;overflow:hidden;background:white;transition:transform .2s,box-shadow .2s;min-width:0}
    .insight-card:hover {transform:translateY(-4px);box-shadow:0 12px 30px #0f172a12}
    .insight-card a {display:block;color:inherit;text-decoration:none}
    .insight-card a:focus-visible {outline:3px solid #2563eb;outline-offset:-3px}
    .insight-cover {aspect-ratio:16/9;background:linear-gradient(135deg,#dbeafe,#eff6ff);display:grid;place-items:center;overflow:hidden;font-size:44px;color:#334155}
    .insight-cover[data-category="stock_macro"] {background:linear-gradient(135deg,#d1fae5,#ecfdf5)}
    .insight-cover[data-category="personal_finance"] {background:linear-gradient(135deg,#fef3c7,#fffbeb)}
    .insight-cover img {width:100%;height:100%;object-fit:cover;grid-area:1/1}
    .insight-card-body {padding:22px}
    .insight-badge {display:inline-block;font-size:12px;font-weight:700;color:#0369a1;background:#f0f9ff;border-radius:6px;padding:5px 9px}
    .insight-card h2 {font-size:20px;line-height:1.5;margin:12px 0 8px;overflow-wrap:anywhere}
    .insight-excerpt {color:#64748b;font-size:14px;line-height:1.7;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:3.4em;margin:0 0 22px;overflow-wrap:anywhere}
    .insight-meta {display:flex;justify-content:space-between;gap:12px;color:#64748b;font-size:12px}
    .insight-status {grid-column:1/-1;padding:48px;text-align:center;color:#64748b}
    .insight-quick {margin:0 22px 20px;border:0;background:none;color:#0369a1;cursor:pointer;padding:0}
    @media(max-width:1000px){.insight-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:620px){.insight-grid{grid-template-columns:1fr}.board-header{flex-wrap:wrap;gap:12px}}
  </style>
<style>
#insightQuillEditor .ql-editor img {
      cursor: pointer;
      display: inline-block;
      vertical-align: middle;
      max-width: 100%;
      user-select: all;
      -webkit-user-drag: auto;
    }
    /* old */
    .temp-old-img {max-width:100%;height:auto;cursor:pointer;pointer-events:auto;}
#quillImageResizerBox {position:absolute;display:none;border:2px solid #2563eb;pointer-events:none;z-index:10000;box-sizing:border-box;}
#quillImageResizerBox button {position:absolute;width:14px;height:14px;padding:0;background:#2563eb;border:2px solid white;border-radius:2px;pointer-events:auto;touch-action:none;}
#quillImageResizerBox [data-dir="nw"] {top:-7px;left:-7px;cursor:nwse-resize;}
#quillImageResizerBox [data-dir="ne"] {top:-7px;right:-7px;cursor:nesw-resize;}
#quillImageResizerBox [data-dir="sw"] {bottom:-7px;left:-7px;cursor:nesw-resize;}
#quillImageResizerBox [data-dir="se"] {bottom:-7px;right:-7px;cursor:nwse-resize;}
.post-detail-content img {max-width:100%;height:auto;}
</style>
</head>
<body>

  <!-- 닉네임 설정 모달 -->
  <dialog id="nicknameModal" aria-labelledby="nicknameTitle" aria-describedby="nicknameHelp">
    <form id="nicknameForm">
      <h2 id="nicknameTitle" style="margin-top:0;font-size:21px;">사이트 전용 닉네임 설정</h2>
      <p id="nicknameHelp" style="font-size:13.5px;color:#cbd5e1;line-height:1.5;">
        카카오톡 실명 대신 게시판에서 활동할 닉네임입니다.<br>
        <span style="color:#ef4444;font-weight:700;">⚠️️ 닉네임은 최초 1회 설정 후 변경할 수 없으니 신중히 입력해 주세요.</span><br>
        (한글·영문·숫자 2~12자)
      </p>
      <input id="nicknameInput" autocomplete="off" spellcheck="false" required placeholder="예: 범어대장, 아인싸러" maxlength="12">
      <p id="nicknameMessage" role="status" aria-live="polite"></p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button id="nicknameSave" type="submit" style="background:#38bdf8;color:#0f172a;font-weight:700;">확인 및 설정 완료</button>
        <button type="button" onclick="logoutKakao()" style="background:#334155;color:#94a3b8;">로그아웃</button>
      </div>
    </form>
  </dialog>

  <!-- 호갱노노 스타일 단지 이야기 모달 -->
  <dialog id="aptStoryModal">
    <div class="apt-story-header">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 20px;">🏢</span>
        <span id="aptStoryTitle" style="font-size: 17px; font-weight: 800; color: #38bdf8;">단지 이야기</span>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <button id="btnAptStoryWrite" onclick="openAptStoryWrite()" style="background: #2563eb; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12.5px; font-weight: 700; cursor: pointer;">✏️ 이야기/사진 등록</button>
        <button onclick="closeAptStoryModal()" style="background: none; border: none; font-size: 20px; color: #94a3b8; cursor: pointer;">✕</button>
      </div>
    </div>
    <div class="apt-story-body">
      <!-- 사진 갤러리 섹션 -->
      <div class="apt-gallery-box" id="aptGalleryBox" style="display: none;">
        <div style="font-size: 13.5px; font-weight: 700; color: #1e293b; margin-bottom: 8px;">📸 단지 현장 사진 모아보기</div>
        <div class="apt-gallery-scroll" id="aptGalleryScroll"></div>
      </div>

      <!-- 단지 이야기 리스트 -->
      <div style="font-size: 15px; font-weight: 800; color: #0f172a; margin-bottom: 12px; display: flex; justify-content: space-between;">
        <span>💬 단지 주민/투자자 이야기 (<span id="aptStoryCount">0</span>건)</span>
      </div>
      <div id="aptStoryListContainer"><div style="padding: 30px; text-align: center; color: #94a3b8;">이야기를 불러오는 중입니다...</div></div>
    </div>
  </dialog>

  <!-- 글쓰기 모달 (이미지 다운사이징 포함) -->
  <dialog id="writeModal">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h3 style="font-size: 18px; font-weight: 800; color: #0f172a;" id="writeModalTitle">새 글 작성</h3>
      <button onclick="closeWriteModal()" style="background: none; border: none; font-size: 18px; cursor: pointer; color: #94a3b8;">✕</button>
    </div>
    <form id="postWriteForm">
      <div class="form-group" id="insightCategoryGroup" style="display:none">
        <label class="form-label" for="postCategorySelect">카테고리</label>
        <select id="postCategorySelect" class="form-control">
          <option value="real_estate">🏢 부동산 분석</option>
          <option value="stock_macro">📈 주식·매크로</option>
          <option value="personal_finance">💡 생활금융</option>
        </select>
        <small>첫 번째 첨부 사진이 대표 썸네일로 표시됩니다.</small>
      </div>
      <div class="form-group" id="regionSelectGroup">
        <label class="form-label">지역 선택</label>
        <select id="postRegionSelect" class="form-control" style="background: white;">
          <option value="서울">서울</option><option value="경기">경기</option><option value="인천">인천</option>
          <option value="부산">부산</option><option value="대구" selected>대구</option><option value="울산">울산</option>
          <option value="세종">세종</option><option value="광주">광주</option><option value="대전">대전</option>
          <option value="경북">경북</option><option value="경남">경남</option><option value="충북">충북</option>
          <option value="충남">충남</option><option value="전북">전북</option><option value="전남">전남</option>
          <option value="강원">강원</option><option value="제주">제주</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">제목</label>
        <input type="text" id="postTitleInput" class="form-control" placeholder="제목을 입력하세요" required maxlength="100">
      </div>
      <!-- 내용 입력 영역 분기 -->
      <div class="form-group" id="normalContentGroup">
        <label class="form-label">내용 (단지 응원, 실거주 후기, 인프라 장단점 등)</label>
        <textarea id="postContentInput" class="form-control" rows="8" placeholder="자유롭게 작성해 주세요"></textarea>
      </div>
      <div class="form-group" id="insightEditorGroup" style="display:none;">
        <label class="form-label">칼럼 본문 작성 (📷 캡처 원본 | 📱 스마트폰 사진 압축)</label>
        <div id="insightQuillEditor" style="height: 480px; background: #ffffff; color: #1e293b; font-size: 16px;"></div>
      </div>
      <div class="form-group" id="normalImageGroup">
        <label class="form-label">현장 사진 첨부 (스마트폰 원본 사진도 자동 다운사이징 압축)</label>
        <input type="file" id="postImageInput" accept="image/*" multiple onchange="handleImageSelection(this)" style="font-size: 13px;">
        <div id="imagePreviewContainer" class="image-preview-grid"></div>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px;">
        <button type="button" onclick="closeWriteModal()" style="padding: 9px 16px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; cursor: pointer;">취소</button>
        <button type="submit" id="btnSubmitPost" style="padding: 9px 18px; border: none; border-radius: 8px; background: #2563eb; color: #fff; font-weight: 700; cursor: pointer;">등록하기</button>
      </div>
    </form>
  </dialog>

  <!-- 글로벌 상단 네비게이션 -->
  <nav class="global-nav">
    <div class="logo-area" onclick="navigateTo('home')">🏢 <span>TECH REALTY INSIGHT</span></div>
    <div class="nav-links">
      <button class="nav-btn active" id="nav-home" onclick="navigateTo('home')">홈 (허브)</button>
      <button class="nav-btn" id="nav-rank" onclick="navigateTo('rank')">아파트 랭킹</button>
      <button class="nav-btn" id="nav-vs" onclick="navigateTo('vs')">아파트 vs 아파트</button>
      <button class="nav-btn" id="nav-macro" onclick="navigateTo('macro')">부동산 매크로</button>
      <button class="nav-btn" id="nav-insight" onclick="navigateTo('insight')">✍️ 투자 인사이트</button>
      <button class="nav-btn" id="nav-board" onclick="navigateTo('board')">💬 지역별 게시판</button>
      <button class="nav-btn" style="opacity: 0.45; cursor: not-allowed;">지역 vs 지역</button>
    
      <div id="authArea" style="display: flex; align-items: center; gap: 10px; margin-left: 10px;">
        <button id="btnKakaoLogin" onclick="loginWithKakao()" style="display: flex; align-items: center; gap: 6px; background: #FEE500; color: #191919; border: none; font-size: 12.5px; font-weight: 700; padding: 6px 12px; border-radius: 8px; cursor: pointer;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#191919"><path d="M12 3C6.477 3 2 6.477 2 10.768c0 2.76 1.848 5.176 4.636 6.536-.205.76-.745 2.753-.855 3.193-.135.545.2.538.42.392.174-.116 2.772-1.884 3.904-2.654.618.087 1.25.133 1.895.133 5.523 0 10-3.477 10-7.768S17.523 3 12 3z"/></svg>
          카카오 로그인
        </button>
        <div id="userProfile" style="display: none; align-items: center; gap: 8px;">
          <span id="userName" style="font-size: 13.5px; font-weight: 700; color: #38bdf8;"></span>
          <button onclick="logoutKakao()" style="font-size: 11px; font-weight: 600; background: transparent; border: 1px solid #475569; color: #94a3b8; padding: 3px 6px; border-radius: 6px; cursor: pointer;">로그아웃</button>
        </div>
      </div>
    </div>
  </nav>

  <div class="main-wrapper">
    <!-- 1. 홈 뷰 -->
    <div class="page-view active" id="page-home">
      <div class="hero-banner">
        <h1>📊 부동산 데이터 테크니컬 분석 플랫폼</h1>
        <p>전국 280만 건의 국토부 실거래가 원천 데이터와 기술적 지표를 통해 단지의 가치와 랭킹을 확인합니다.</p>
      </div>
      <div class="hub-grid">
        <div class="hub-card" onclick="navigateTo('vs')">
          <div style="font-size: 12px; font-weight: 700; color: #1d4ed8; margin-bottom: 8px;">핵심 분석실</div>
          <div class="hub-title">⚔️ 아파트 vs 아파트 비교</div>
          <div class="hub-desc">최대 4개 단지를 한 차트에 올려 실거래 점, 20건 이동평균선, 볼린저 밴드를 정밀 비교합니다.</div>
          <div class="hub-action">비교 분석실 바로가기 ➔</div>
        </div>
        <div class="hub-card" onclick="navigateTo('rank')">
          <div style="font-size: 12px; font-weight: 700; color: #7e22ce; margin-bottom: 8px;">스마트 랭킹</div>
          <div class="hub-title">🏆 아파트 랭킹 (2010~2026)</div>
          <div class="hub-desc">단지 최고가, 국평(84), 전용 59 최고가·평균가, 분산도 및 거래량 랭킹을 확인합니다.</div>
          <div class="hub-action">단지별 랭킹 확인하기 ➔</div>
        </div>
        <div class="hub-card" onclick="navigateTo('board')">
          <div style="font-size: 12px; font-weight: 700; color: #16a34a; margin-bottom: 8px;">실시간 토론방</div>
          <div class="hub-title">💬 지역별 게시판</div>
          <div class="hub-desc">서울, 경기, 대구, 부산 등 각 지역 부동산 논쟁과 생생한 임장 후기를 나눕니다.</div>
          <div class="hub-action">지역 게시판 바로가기 ➔</div>
        </div>
        <div class="hub-card" onclick="navigateTo('insight')">
          <div style="font-size: 12px; font-weight: 700; color: #0284c7; margin-bottom: 8px;">주인장 칼럼</div>
          <div class="hub-title">✍️ 투자 인사이트</div>
          <div class="hub-desc">빅데이터 분석과 시장 사이클을 기반으로 한 부동산 핵심 투자 칼럼 공간입니다.</div>
          <div class="hub-action">인사이트 칼럼 보기 ➔</div>
        </div>
      </div>
    </div>

    <!-- 2. 아파트 랭킹 뷰 -->
    <div class="page-view" id="page-rank">
      <div class="ranking-header">
        <div style="font-size: 18px; font-weight: 800; color: #0f172a; margin-bottom: 14px;">🏆 실거래가 기반 아파트 종합 랭킹</div>
        <div class="year-selection-bar"><span class="year-label">📅 기준 연도:</span><div id="yearButtonsContainer" style="display: flex; gap: 6px;"></div></div>
        <div class="rank-tabs">
          <button class="rank-tab-btn active" onclick="setRankType('price_max', this)">단지 최고가 순위</button>
          <button class="rank-tab-btn" onclick="setRankType('84_max', this)">국평(84) 최고가 순위</button>
          <button class="rank-tab-btn" onclick="setRankType('84_avg', this)">국평(84) 평균가 순위</button>
          <button class="rank-tab-btn" onclick="setRankType('59_max', this)">전용 59 최고가 순위</button>
          <button class="rank-tab-btn" onclick="setRankType('59_avg', this)">전용 59 평균가 순위</button>
          <button class="rank-tab-btn" onclick="setRankType('pyeong_avg', this)">평균 평당가 순위</button>
          <button class="rank-tab-btn" onclick="setRankType('trade_cnt', this)">거래량 순위</button>
        </div>
        <div class="filter-section">
          <div class="region-parent-row">
            <label class="region-checkbox-label"><input type="checkbox" id="chkAllRegions" onchange="toggleAllRegions(this)" checked> 전체</label>
            <div style="display: flex; align-items: center;">
              <label class="region-checkbox-label"><input type="checkbox" class="region-chk" value="대구전체" checked onchange="handleRegionCheck()"> 대구</label>
              <button class="btn-subregion-toggle" onclick="toggleSubregionBox()">세부지역 ▼</button>
            </div>
          </div>
          <div class="subregion-container" id="subregionBox" style="display: flex;">
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="수성구" checked onchange="handleGuCheck()"> 수성구</label>
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="중구" checked onchange="handleGuCheck()"> 중구</label>
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="동구" checked onchange="handleGuCheck()"> 동구</label>
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="북구" checked onchange="handleGuCheck()"> 북구</label>
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="달서구" checked onchange="handleGuCheck()"> 달서구</label>
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="남구" checked onchange="handleGuCheck()"> 남구</label>
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="서구" checked onchange="handleGuCheck()"> 서구</label>
            <label class="subregion-item"><input type="checkbox" class="gu-chk" value="달성군" checked onchange="handleGuCheck()"> 달성군</label>
          </div>
        </div>
      </div>
      <div class="ranking-table-card">
        <div class="ranking-loading-overlay" id="rankingLoadingOverlay"><div class="loading-hourglass">⏳</div><div class="loading-text">실거래 랭킹 빅데이터 로딩 중...</div></div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
          <span style="font-size: 15px; font-weight: 700; color: #1e293b;" id="rankTableTitle">2026년 Top 50 랭킹</span>
          <span style="font-size: 12.5px; color: #64748b;">(단지명 클릭 시 [아파트 vs 아파트] 차트 분석으로 즉시 이동)</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="rank-table">
            <thead>
              <tr id="rankTableHeaderRow">
                <th>순위</th><th>단지명</th><th>지역</th><th style="color: #2563eb;" id="rankMetricHeader">기준 지표</th>
                <th>입주 연식</th><th>세대수</th><th>연간 거래량</th>
                <th>
                  <span>가격 분산도</span>
                  <span class="help-tooltip-trigger">?
                    <div class="help-tooltip-box" style="width: 360px;">
                      <div class="tooltip-title">💡 가격 분산도(Price Dispersion)란?</div>
                      <div class="tooltip-def">실거래가의 통계적 변동계수(표준편차/평균)로 시장의 <strong>가격 합의 수준</strong>을 나타냅니다.</div>
                      <div style="font-size: 12px; line-height: 1.6; color: #cbd5e1; text-align: left;">
                        <div style="margin-bottom: 6px;"><strong style="color: #38bdf8;">• 균질한 상품성 & 가격 합의:</strong> 동·호수별 편차가 적고 적정 시세에 대한 시장 공감대가 두터워 왜곡이 적습니다.</div>
                        <div style="margin-bottom: 6px;"><strong style="color: #38bdf8;">• 바가지 · 저가 매도 위험 제거:</strong> 상투 매수나 헐값 매각 위험이 없어 탐색 비용과 의사결정 피로도가 대폭 줄어듭니다.</div>
                        <div><strong style="color: #38bdf8;">• 우수한 환금성:</strong> 시세 예측 가능성이 높아 거래 체결이 매끄럽고 매수 대기층이 탄탄합니다.</div>
                      </div>
                    </div>
                  </span>
                </th>
              </tr>
            </thead>
            <tbody id="rankTableBody"><tr><td colspan="8" style="padding: 30px; color: #94a3b8;">데이터를 불러오는 중입니다...</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 3. 아파트 vs 아파트 비교 뷰 -->
    <div class="page-view" id="page-vs">
      <div class="container">
        <div class="header-area">
          <h2>📊 전국 아파트 실거래가 기술적 분석실 (Render 배포용)</h2>
          <div class="area-filter-bar">
            <button class="filter-btn active" onclick="setAreaFilter('84', this)">전용 84㎡ (83~85)</button>
            <button class="filter-btn" onclick="setAreaFilter('59', this)">전용 59㎡ (58~60)</button>
            <button class="filter-btn" onclick="setAreaFilter('all', this)">전체 평형(평당가)</button>
            <label style="display:inline-flex; align-items:center; gap:6px; margin-left:12px; font-size:13px; font-weight:700; color:#dc2626; cursor:pointer; background:#fef2f2; border:1px solid #fecaca; padding:5px 12px; border-radius:8px; vertical-align:middle;">
              <input type="checkbox" id="excludeDirectChk" onchange="fetchAndRender();" style="width:16px; height:16px; cursor:pointer; accent-color:#dc2626;"> 🚫 직거래 제외
            </label>
          </div>
        </div>
        <div class="selector-container">
          <div class="slot-config-row">
            <span>비교 단지 수:</span>
            <select id="slotCountSelect" onchange="updateSlotCount(this.value)">
              <option value="2">2개 단지</option><option value="3" selected>3개 단지</option><option value="4">4개 단지</option>
            </select>
          </div>
          <div class="search-inputs-grid" id="searchInputsContainer"></div>
        </div>
        <div class="toolbar">
          <div class="tool-group"><label style="font-size: 13.5px; font-weight: 600;">분석 주기:</label><select id="periodSelect" class="period-select" onchange="fetchAndRender()"></select></div>
          <div class="tool-group">
            <button id="toggleScatterBtn" class="btn-toggle active" onclick="toggleCategory('scatter')">● 실거래가 점</button>
            <button id="toggleSMABtn" class="btn-toggle active" onclick="toggleCategory('sma')">━ 이동평균선</button>
            <button id="toggleBBBtn" class="btn-toggle active" onclick="toggleCategory('bb')">╍ 볼린저 밴드</button>
            <button class="btn-reset-zoom" onclick="resetChartZoom()">🔍 줌 리셋</button>
          </div>
        </div>
        <div class="dashboard-body">
          <div class="chart-section">
            <div class="chart-box">
              <div class="chart-loading-overlay" id="chartLoadingOverlay"><div class="loading-hourglass">⏳</div><div class="loading-text">실거래 빅데이터 정밀 분석 중...</div></div>
              <canvas id="aptChart"></canvas>
            </div>
            <div class="chart-guide-card">
              <div class="guide-title"><span>📌 조작 안내</span><span style="font-size: 11.5px; color: #059669; font-weight: 600;">✨ 마우스 휠 줌(확대/축소) & 드래그 이동(Pan) 지원</span></div>
              <div class="guide-grid">
                <div class="guide-item"><strong>● 실거래가 점</strong>국토부 실거래 신고 건입니다. 마우스를 올리면 계약일, 층수, 전용면적을 확인합니다.</div>
                <div class="guide-item"><strong>━ 20일 이동평균선</strong>직전 20건 거래의 흐름선입니다. 층별 급매 왜곡을 지우고 진짜 시세를 파악합니다.</div>
                <div class="guide-item"><strong>╍ 볼린저 밴드</strong>통계적 정상 거래 범위(±2σ)입니다. 밴드가 좁을수록 단지 가격이 안정적입니다.</div>
                <div class="guide-item"><strong>🔍 Y축 확대/이동</strong>휠로 가격 범위를 정밀 확대하고, 클릭 드래그로 위아래로 이동할 수 있습니다.</div>
              </div>
            </div>
          </div>
          <div class="right-side-panel">
            <div class="compare-panel">
              <div class="compare-title">
                <span>⚖️ 단지 종합 스펙 & 실거래 비교</span>
                <span style="font-size: 11.5px; color: #2563eb; font-weight: 600;">👉 단지명을 누르면 [단지 이야기/후기] 오픈!</span>
              </div>
              <div id="compareTableWrapper"></div>
            </div>
            <div class="top10-panel"><div class="top10-title">🔥 자주 함께 비교되는 단지 Top 10</div><div class="top10-tabs" id="top10TabsContainer"></div><div class="top10-list" id="top10ListContainer"></div></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 4. 부동산 매크로 뷰 -->
    <div class="page-view" id="page-macro" style="height: calc(100vh - 100px); margin: 0 -20px;">
      <iframe id="macroFrame" src="" style="width: 100%; height: 100%; border: none; border-radius: 14px; background: #0f172a;" loading="lazy"></iframe>
    </div>

    <!-- 5. 투자 인사이트 뷰 -->
    <div class="page-view" id="page-insight">
      <div class="board-container">
        <div class="board-header">
          <div class="board-title-text">✍️ 투자 인사이트 <span style="font-size: 13px; color: #64748b; font-weight: 500;">(운영자 분석 칼럼 공간)</span></div>
          <button id="btnWriteInsight" class="btn-write-post" style="display: none;" onclick="openWriteModal('insight')">✏️ 인사이트 작성</button>
        </div>
        <div id="insightListView">
          <p style="color:#64748b">데이터로 읽는 시장, 일상에 도움이 되는 금융 이야기.</p>
          <div class="insight-filters" id="insightFilters" aria-label="인사이트 카테고리">
            <button class="insight-filter active" aria-pressed="true" onclick="filterInsights('all',this)">전체</button>
            <button class="insight-filter" aria-pressed="false" onclick="filterInsights('real_estate',this)">부동산</button>
            <button class="insight-filter" aria-pressed="false" onclick="filterInsights('stock_macro',this)">주식</button>
            <button class="insight-filter" aria-pressed="false" onclick="filterInsights('personal_finance',this)">생활금융</button>
          </div>
          <div id="insightGrid" class="insight-grid" aria-live="polite"></div>
          <p><a href="/insight">인사이트 전체 글 · 고유 주소 목록 →</a></p>
        </div>
        <div id="insightDetailView" class="post-detail-box"></div>
      </div>
    </div>

    <!-- 6. 지역별 게시판 뷰 -->
    <div class="page-view" id="page-board">
      <div class="board-container">
        <div class="board-header">
          <div class="board-title-text">💬 지역별 부동산 토론 광장</div>
          <button class="btn-write-post" onclick="openWriteModal('region')">✏️ 글쓰기</button>
        </div>
        <div class="region-pills-bar" id="regionPillsContainer">
          <button class="region-pill active" onclick="filterRegionBoard('전체', this)">전체</button>
          <button class="region-pill" onclick="filterRegionBoard('강원', this)">강원</button>
          <button class="region-pill" onclick="filterRegionBoard('경기', this)">경기</button>
          <button class="region-pill" onclick="filterRegionBoard('경남', this)">경남</button>
          <button class="region-pill" onclick="filterRegionBoard('경북', this)">경북</button>
          <button class="region-pill" onclick="filterRegionBoard('광주', this)">광주</button>
          <button class="region-pill" onclick="filterRegionBoard('대구', this)">대구</button>
          <button class="region-pill" onclick="filterRegionBoard('대전', this)">대전</button>
          <button class="region-pill" onclick="filterRegionBoard('부산', this)">부산</button>
          <button class="region-pill" onclick="filterRegionBoard('서울', this)">서울</button>
          <button class="region-pill" onclick="filterRegionBoard('세종', this)">세종</button>
          <button class="region-pill" onclick="filterRegionBoard('울산', this)">울산</button>
          <button class="region-pill" onclick="filterRegionBoard('인천', this)">인천</button>
          <button class="region-pill" onclick="filterRegionBoard('전남', this)">전남</button>
          <button class="region-pill" onclick="filterRegionBoard('전북', this)">전북</button>
          <button class="region-pill" onclick="filterRegionBoard('제주', this)">제주</button>
          <button class="region-pill" onclick="filterRegionBoard('충남', this)">충남</button>
          <button class="region-pill" onclick="filterRegionBoard('충북', this)">충북</button>
        </div>
        <div id="boardListView">
          <table class="board-table">
            <thead><tr><th style="width: 70px;">번호</th><th style="width: 80px;">지역</th><th>제목</th><th style="width: 130px;">작성자</th><th style="width: 110px;">작성일</th><th style="width: 70px;">조회</th></tr></thead>
            <tbody id="boardTableBody"><tr><td colspan="6" style="padding: 30px; color: #94a3b8;">글을 불러오는 중입니다...</td></tr></tbody>
          </table>
        </div>
        <div id="boardDetailView" class="post-detail-box"></div>
      </div>
    </div>
  </div>

<script>
  let currentYear = 2026;
  let currentRankType = 'price_max';

  function showRankingLoading(show) {
    const overlay = document.getElementById('rankingLoadingOverlay');
    if (overlay) overlay.style.display = show ? 'flex' : 'none';
  }

  function buildYearButtons() {
    const container = document.getElementById('yearButtonsContainer');
    if (!container) return;
    container.innerHTML = '';
    for (let y = 2026; y >= 2010; y--) {
      const btn = document.createElement('button');
      btn.className = `btn-year ${y === currentYear ? 'active' : ''}`;
      btn.innerText = `${y}년`;
      btn.onclick = () => {
        currentYear = y;
        document.querySelectorAll('.btn-year').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        fetchRankings();
      };
      container.appendChild(btn);
    }
  }

  function navigateTo(pageId) {
    document.querySelectorAll('.page-view').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(`page-${pageId}`).classList.add('active');
    const navBtn = document.getElementById(`nav-${pageId}`);
    if (navBtn) navBtn.classList.add('active');

    if (pageId === 'vs') {
      if (!chart) initVsChart();
      else fetchAndRender();
    } else if (pageId === 'rank') {
      fetchRankings();
    } else if (pageId === 'macro') {
      const frame = document.getElementById('macroFrame');
      if (frame && (!frame.src || frame.src === 'about:blank' || frame.src.endsWith('/'))) {
        frame.src = '/view/macro';
      }
    } else if (pageId === 'insight') {
      loadPosts('insight');
    } else if (pageId === 'board') {
      loadPosts('region');
    }
  }

  function setRankType(type, btn) {
    currentRankType = type;
    document.querySelectorAll('.rank-tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchRankings();
  }

  function toggleSubregionBox() {
    const box = document.getElementById('subregionBox');
    box.style.display = (box.style.display === 'none') ? 'flex' : 'none';
  }

  function toggleAllRegions(master) {
    const checked = master.checked;
    document.querySelectorAll('.region-chk, .gu-chk').forEach(c => c.checked = checked);
    fetchRankings();
  }

  function handleRegionCheck() {
    const deaguAll = document.querySelector('.region-chk[value="대구전체"]').checked;
    document.querySelectorAll('.gu-chk').forEach(c => c.checked = deaguAll);
    fetchRankings();
  }

  function handleGuCheck() {
    const allGus = Array.from(document.querySelectorAll('.gu-chk'));
    const allChecked = allGus.every(c => c.checked);
    document.querySelector('.region-chk[value="대구전체"]').checked = allChecked;
    fetchRankings();
  }

  function getSelectedRegions() {
    const deaguAll = document.querySelector('.region-chk[value="대구전체"]')?.checked;
    if (deaguAll) return "대구전체";
    const checkedGus = Array.from(document.querySelectorAll('.gu-chk:checked')).map(c => c.value);
    return checkedGus.length > 0 ? checkedGus.join(',') : "대구전체";
  }

  async function fetchRankings() {
    showRankingLoading(true);
    const regions = getSelectedRegions();
    document.getElementById('rankTableTitle').innerText = `${currentYear}년 Top 50 랭킹`;

    try {
      const res = await fetch(`/api/rankings?year=${currentYear}&rank_type=${currentRankType}&regions=${encodeURIComponent(regions)}`);
      if (!res.ok) throw new Error('API 응답 에러');
      const list = await res.json();
      const tbody = document.getElementById('rankTableBody');
      
      if (!list || list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="padding: 30px; color: #94a3b8;">${currentYear}년도 해당 조건의 거래 데이터가 없습니다.</td></tr>`;
        return;
      }
      
      document.getElementById('rankMetricHeader').innerText = list[0].metric_name;
      let html = '';
      list.forEach(item => {
        let rankClass = item.rank === 1 ? 'top1' : (item.rank === 2 ? 'top2' : (item.rank === 3 ? 'top3' : ''));
        let metricContent = `<span style="font-weight: 800; color: #2563eb;">${item.metric_val}</span>`;
        if (currentRankType === 'price_max' && item.tooltip_info) {
          metricContent = `
            <div class="metric-hover-box">
              <span style="font-weight: 800; color: #2563eb; text-decoration: underline dotted;">${item.metric_val}</span>
              <div class="metric-tooltip">📌 ${item.tooltip_info}</div>
            </div>
          `;
        }
        html += `
          <tr>
            <td class="rank-num ${rankClass}">${item.rank}</td>
            <td style="text-align: left;"><span class="apt-name-click" onclick="sendToVsCompare('${item.apt_name}')">${item.apt_name}</span></td>
            <td><span style="background: #f1f5f9; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: 600;">${item.region}</span></td>
            <td>${metricContent}</td>
            <td style="color: #475569;">${item.built_str}</td>
            <td style="color: #475569;">${item.units_str}</td>
            <td style="font-weight: 600;">${item.trade_cnt}건</td>
            <td style="font-weight: 700; color: #0f172a;">${item.dispersion}</td>
          </tr>
        `;
      });
      tbody.innerHTML = html;
    } catch(e) {
      document.getElementById('rankTableBody').innerHTML = '<tr><td colspan="8" style="padding: 30px; color: #ef4444;">랭킹 데이터를 불러오지 못했습니다.</td></tr>';
    } finally {
      showRankingLoading(false);
    }
  }

  function sendToVsCompare(aptName) {
    navigateTo('vs');
    const input1 = document.getElementById('aptInput1');
    if (input1) {
      input1.value = aptName;
      fetchAndRender();
    }
  }

  const slotConfigs = [
    { slot: 1, color: "#2563eb", fill: "rgba(37, 99, 235, 0.08)", defaultVal: "힐스테이트범어" },
    { slot: 2, color: "#f97316", fill: "rgba(249, 115, 22, 0.08)", defaultVal: "수성범어W" },
    { slot: 3, color: "#16a34a", fill: "rgba(22, 163, 74, 0.08)", defaultVal: "" },
    { slot: 4, color: "#9333ea", fill: "rgba(147, 51, 234, 0.08)", defaultVal: "" }
  ];

  let currentAreaMode = '84';
  let currentSlotCount = 3;
  let visibilityFlags = { scatter: true, sma: true, bb: true };
  let chart = null;
  let globalSlotResults = [];
  let currentActiveTabIdx = 0;

  function showLoading(show) {
    const overlay = document.getElementById('chartLoadingOverlay');
    if (overlay) overlay.style.display = show ? 'flex' : 'none';
  }

  function resetChartZoom() { if (chart) chart.resetZoom(); }

  function buildPeriodOptions() {
    const sel = document.getElementById('periodSelect');
    if (!sel) return;
    sel.innerHTML = '';
    for (let m = 3; m <= 36; m++) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.innerText = (m % 12 === 0) ? `${m}개월 (${m/12}년)` : `${m}개월`;
      if (m === 24) opt.selected = true;
      sel.appendChild(opt);
    }
    for (let y = 4; y <= 20; y++) {
      const opt = document.createElement('option');
      opt.value = y * 12;
      opt.innerText = `${y}년 (${y * 12}개월)`;
      sel.appendChild(opt);
    }
  }

  function setAreaFilter(mode, btn) {
    currentAreaMode = mode;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchAndRender();
  }

  function updateSlotCount(count) {
    currentSlotCount = parseInt(count);
    renderSearchInputs();
    fetchAndRender();
  }

  function isAptEmpty(val) { return !val || val.trim() === "" || val.includes("없음"); }

  function getSelectedAptNames(excludeSlotIdx) {
    const names = new Set();
    for (let i = 1; i <= currentSlotCount; i++) {
      if (i === excludeSlotIdx) continue;
      const inp = document.getElementById(`aptInput${i}`);
      if (inp && !isAptEmpty(inp.value)) names.add(inp.value.trim().replace(" ", ""));
    }
    return names;
  }

  function closeAllDropdowns(exceptIdx = -1) {
    for (let i = 1; i <= 4; i++) {
      if (i === exceptIdx) continue;
      const dd = document.getElementById(`acDropdown${i}`);
      if (dd) dd.style.display = 'none';
    }
  }

  function renderSearchInputs() {
    const container = document.getElementById('searchInputsContainer');
    if (!container) return;
    container.innerHTML = '';
    for (let i = 0; i < currentSlotCount; i++) {
      const cfg = slotConfigs[i];
      const slotDiv = document.createElement('div');
      slotDiv.className = 'search-slot-wrapper';
      slotDiv.innerHTML = `
        <div class="select-item">
          <span class="color-pill" style="background-color: ${cfg.color};"></span>
          <input class="search-input" id="aptInput${i+1}" value="${cfg.defaultVal}"
                 placeholder="단지명 검색 (예: 힐스테이트)"
                 onfocus="openAutocomplete(${i+1})"
                 oninput="handleSearchInput(${i+1})"
                 onkeydown="handleKeyDown(event, ${i+1})">
        </div>
        <div class="autocomplete-dropdown" id="acDropdown${i+1}"></div>
      `;
      container.appendChild(slotDiv);
    }
  }

  async function handleSearchInput(slotIdx) {
    const input = document.getElementById(`aptInput${slotIdx}`);
    if (input) openAutocomplete(slotIdx, input.value.trim());
  }

  async function openAutocomplete(slotIdx, query = "") {
    closeAllDropdowns(slotIdx);
    const input = document.getElementById(`aptInput${slotIdx}`);
    if (!input) return;
    const q = (query !== "") ? query : input.value.trim();
    const dropdown = document.getElementById(`acDropdown${slotIdx}`);
    if (!dropdown) return;
    const alreadySelected = getSelectedAptNames(slotIdx);

    try {
      const res = await fetch(`/api/search-apt?q=${encodeURIComponent(q)}`);
      const aptList = await res.json();
      let html = `<div class="ac-item ac-none" onmousedown="selectApt(${slotIdx}, '')">🚫 [없음]</div>`;
      aptList.forEach(name => {
        const isDuplicated = alreadySelected.has(name.replace(" ", ""));
        if (isDuplicated) {
          html += `<div class="ac-item ac-disabled"><span>🏢 ${name}</span><span style="font-size:11px; color:#ef4444; font-weight:700;">[선택됨]</span></div>`;
        } else {
          html += `<div class="ac-item" onmousedown="selectApt(${slotIdx}, '${name}')"><span>🏢 ${name}</span><span style="font-size:11px; color:#94a3b8;">선택</span></div>`;
        }
      });
      dropdown.innerHTML = html;
      dropdown.style.display = 'block';
    } catch(e) {}
  }

  function selectApt(slotIdx, name) {
    const input = document.getElementById(`aptInput${slotIdx}`);
    const dropdown = document.getElementById(`acDropdown${slotIdx}`);
    if (!input) return;
    if (name !== "" && getSelectedAptNames(slotIdx).has(name.replace(" ", ""))) {
      alert("이미 다른 슬롯에서 비교 중인 단지입니다.");
      if (dropdown) dropdown.style.display = 'none';
      return;
    }
    input.value = name;
    if (dropdown) dropdown.style.display = 'none';
    fetchAndRender();
  }

  function handleKeyDown(e, slotIdx) {
    if (e.key === 'Enter') {
      const input = document.getElementById(`aptInput${slotIdx}`);
      if (!input) return;
      const val = input.value.trim();
      if (val && getSelectedAptNames(slotIdx).has(val.replace(" ", ""))) {
        alert("이미 다른 슬롯에서 비교 중인 단지입니다.");
        input.value = "";
      }
      closeAllDropdowns();
      fetchAndRender();
    }
  }

  document.addEventListener('click', (e) => {
    let clickedInside = false;
    for (let i = 1; i <= 4; i++) {
      if (document.getElementById(`acDropdown${i}`)?.contains(e.target) || document.getElementById(`aptInput${i}`)?.contains(e.target)) {
        clickedInside = true; break;
      }
    }
    if (!clickedInside) closeAllDropdowns();
  });

  function renderCompareTable(results) {
    const wrapper = document.getElementById('compareTableWrapper');
    if (!wrapper) return;
    if (!Array.isArray(results) || results.length === 0) { wrapper.replaceChildren(); return; }

    const currentMonths = document.getElementById('periodSelect')?.value || 24;
    const periodDisplayStr = (currentMonths >= 48) ? `${currentMonths/12}년(${currentMonths}개월)` : `${currentMonths}개월`;
    let tradeLabel = "3. 거래량 (전용 84㎡)";
    if (currentAreaMode === '59') tradeLabel = "3. 거래량 (전용 59㎡)";
    else if (currentAreaMode === 'all') tradeLabel = "3. 거래량 (전체)";

    let html = '<table class="compare-table"><thead><tr><th class="metric-col">항목</th>';
    results.forEach(r => {
      html += `
        <th style="color: ${r.cfg.color}; font-size:13.5px; padding: 10px 4px;">
          <div style="cursor: pointer; text-decoration: underline; text-underline-offset: 4px;" onclick="openAptStoryModal('${r.aptName}')" title="단지 이야기 및 사진 보기">
            🏢 ${r.aptName}
          </div>
          <div style="font-size: 11px; color: #2563eb; font-weight: 700; margin-top: 4px; cursor: pointer;" onclick="openAptStoryModal('${r.aptName}')">
            💬 이야기 보기
          </div>
        </th>
      `;
    });
    html += '</tr></thead><tbody>';

    html += '<tr><th class="metric-col">1. 입주(연식)</th>';
    results.forEach(r => html += `<td style="font-weight:600;">${r.data.stats?.built || '-'}</td>`);
    html += '</tr><tr><th class="metric-col">2. 세대수</th>';
    results.forEach(r => html += `<td style="font-weight:700; color:#0f172a;">${r.data.stats?.units || '-'}</td>`);
    html += '</tr><tr><th class="metric-col" style="background:#f1f5f9;">└ 평형 구성</th>';
    results.forEach(r => html += `<td class="type-info-cell">${r.data.stats?.type_info || '-'}</td>`);
    html += `</tr><tr><th class="metric-col" style="color:#2563eb;">${tradeLabel}</th>`;
    results.forEach(r => html += `<td style="font-weight:700; color:#2563eb;">${r.data.stats?.trade_count || 0}건</td>`);
    html += '</tr><tr><th class="metric-col">4. 최고가</th>';
    results.forEach(r => html += `<td style="font-weight:700;">${r.data.stats?.max_price || '-'}</td>`);
    html += '</tr><tr><th class="metric-col"><span>5. 누적 평균가</span></th>';
    results.forEach(r => html += `<td style="font-weight:600;">${r.data.stats?.avg_price || '-'}</td>`);
    html += '</tr><tr><th class="metric-col" style="color:#0284c7;"><span>└ 최근 이평시세</span></th>';
    results.forEach(r => html += `<td style="font-weight:700; color:#0284c7;">${r.data.stats?.latest_ma || '-'}</td>`);
    html += '</tr><tr><th class="metric-col" style="background:#f8fafc;">' +
      '<span>6. 가격 분산도</span>' +
      '<span class="help-tooltip-trigger">?' +
        '<div class="help-tooltip-box" style="left: 0; right: auto; width: 360px;">' +
          '<div class="tooltip-title">💡 가격 분산도(Price Dispersion)란?</div>' +
          '<div class="tooltip-def">실거래가의 통계적 변동계수(표준편차/평균)로 시장의 <strong>가격 합의 수준</strong>을 나타냅니다.</div>' +
          '<div style="font-size: 12px; line-height: 1.6; color: #cbd5e1;">' +
            '<div style="margin-bottom: 6px;"><strong style="color: #38bdf8;">• 균질한 상품성 & 가격 합의:</strong> 동·호수별 편차가 적고 적정 시세에 대한 시장 공감대가 두터워 왜곡이 적습니다.</div>' +
            '<div style="margin-bottom: 6px;"><strong style="color: #38bdf8;">• 바가지 · 저가 매도 위험 제거:</strong> 상투 매수나 헐값 매각 위험이 없어 탐색 비용과 의사결정 피로도가 대폭 줄어듭니다.</div>' +
            '<div><strong style="color: #38bdf8;">• 우수한 환금성:</strong> 시세 예측 가능성이 높아 거래 체결이 매끄럽고 매수 대기층이 탄탄합니다.</div>' +
          '</div>' +
        '</div>' +
      '</span>' +
    '</th>';
    results.forEach(r => html += `<td style="font-weight:700; color:#0f172a;">${r.data.stats?.dispersion || '-'}</td>`);
    html += '</tr></tbody></table>';
    wrapper.innerHTML = html;
  }

  function renderTop10Rankings(results) {
    const tabsContainer = document.getElementById('top10TabsContainer');
    const listContainer = document.getElementById('top10ListContainer');
    if (!tabsContainer || !listContainer) return;
    tabsContainer.replaceChildren();
    listContainer.replaceChildren();

    const items = results.filter(item => item && item.data);
    if (!items.length) { listContainer.textContent = '비교할 단지를 선택해 주세요.'; return; }
    if (currentActiveTabIdx >= items.length) currentActiveTabIdx = 0;

    items.forEach((item, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `top10-tab-btn ${idx === currentActiveTabIdx ? 'active' : ''}`;
      btn.textContent = `단지 ${idx + 1} (${item.aptName})`;
      btn.onclick = () => { currentActiveTabIdx = idx; renderTop10Rankings(items); };
      tabsContainer.appendChild(btn);
    });

    const activeItem = items[currentActiveTabIdx];
    const names = Array.isArray(activeItem.data.top10) ? activeItem.data.top10.slice(0, 10) : [];
    if (!names.length) { listContainer.textContent = '아직 함께 비교된 단지 데이터가 없습니다.'; return; }
    names.forEach((name, rank) => {
      const row = document.createElement('div');
      row.className = 'top10-item';
      row.innerHTML = `<span>${rank + 1}위 ${name}</span><span style="font-size:11px; color:#94a3b8;"></span>`;
      row.onclick = () => {
        const input = document.getElementById('aptInput1');
        if (input) { input.value = name; fetchAndRender(); }
      };
      listContainer.appendChild(row);
    });
  }

  let latestChartRequestId = 0;
  async function fetchAndRender() {
    const requestId = ++latestChartRequestId;
    showLoading(true);
    const months = document.getElementById('periodSelect')?.value || 24;
    const areaMode = currentAreaMode;
    const excludeDirect = document.getElementById('excludeDirectChk')?.checked ? 'true' : 'false';
    const requests = [];
    for (let i = 0; i < currentSlotCount; i++) {
      const input = document.getElementById(`aptInput${i + 1}`);
      if (input && !isAptEmpty(input.value)) requests.push({ aptName: input.value.trim(), cfg: slotConfigs[i] });
    }

    try {
      const slotResults = [];
      for (const { aptName, cfg } of requests) {
        try {
          const params = new URLSearchParams({ apt_name: aptName, months, area_type: areaMode, exclude_direct: excludeDirect });
          const res = await fetch(`/api/chart-data?${params}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          if (data && ['ok', 'empty'].includes(data.result)) {
            slotResults.push({ cfg, aptName: data.pure_name || aptName, data });
          }
        } catch (e) {}
        if (requestId !== latestChartRequestId) return;
      }
      if (requestId !== latestChartRequestId) return;
      globalSlotResults = slotResults;

      const validNames = slotResults.map(r => r.aptName).filter(n => n && !n.includes("없음"));
      if (validNames.length >= 2) {
        fetch('/api/log-compare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ apts: validNames }) }).catch(() => {});
      }

      renderChart(slotResults);
      renderCompareTable(slotResults);
      renderTop10Rankings(slotResults);
    } finally {
      if (requestId === latestChartRequestId) showLoading(false);
    }
  }

  function renderChart(slotResults) {
    let allDatesSet = new Set();
    slotResults.forEach(({ data }) => { data?.dates?.forEach(d => allDatesSet.add(d)); });
    const sortedDates = Array.from(allDatesSet).sort();
    const datasets = [];

    slotResults.forEach(({ cfg, aptName, data }) => {
      if (!data || data.result !== 'ok' || !data.dates) return;
      const priceMap = {}, maMap = {}, upperMap = {}, lowerMap = {}, detailMap = {};
      data.dates.forEach((d, idx) => {
        priceMap[d] = data.prices[idx]; maMap[d] = data.ma[idx];
        upperMap[d] = data.upper[idx]; lowerMap[d] = data.lower[idx]; detailMap[d] = data.details[idx];
      });

      const upperArr = [], lowerArr = [], maArr = [], scatterArr = [], detailsArr = [];
      sortedDates.forEach(d => {
        if (data.built_date && d < data.built_date) {
          upperArr.push(null); lowerArr.push(null); maArr.push(null); scatterArr.push(null); detailsArr.push(null);
        } else {
          upperArr.push(upperMap[d] ?? null); lowerArr.push(lowerMap[d] ?? null);
          maArr.push(maMap[d] ?? null); scatterArr.push(priceMap[d] ?? null); detailsArr.push(detailMap[d] || null);
        }
      });

      datasets.push({ label: `${aptName} BB상단`, typeCategory: 'bb', data: upperArr, borderColor: cfg.color, borderDash: [4,4], borderWidth: 1.2, pointRadius: 0, fill: '+1', backgroundColor: cfg.fill, spanGaps: true, hidden: !visibilityFlags.bb });
      datasets.push({ label: `${aptName} BB하단`, typeCategory: 'bb', data: lowerArr, borderColor: cfg.color, borderDash: [4,4], borderWidth: 1.2, pointRadius: 0, fill: false, spanGaps: true, hidden: !visibilityFlags.bb });
      datasets.push({ label: `${aptName} 이동평균`, typeCategory: 'sma', data: maArr, borderColor: cfg.color, borderWidth: 2.8, pointRadius: 0, fill: false, tension: 0.2, spanGaps: true, hidden: !visibilityFlags.sma });
      datasets.push({ label: `${aptName} 실거래`, typeCategory: 'scatter', type: 'scatter', data: scatterArr, backgroundColor: cfg.color, borderColor: 'transparent', pointRadius: 4.5, pointHoverRadius: 7, hidden: !visibilityFlags.scatter, details: detailsArr, pureName: aptName });
    });

    if (chart) {
      chart.data.labels = sortedDates;
      chart.data.datasets = datasets;
      if (typeof chart.resetZoom === 'function') chart.resetZoom();
      chart.update();
    }
  }

  function toggleCategory(cat) {
    visibilityFlags[cat] = !visibilityFlags[cat];
    const btnMap = { scatter: 'toggleScatterBtn', sma: 'toggleSMABtn', bb: 'toggleBBBtn' };
    document.getElementById(btnMap[cat])?.classList.toggle('active', visibilityFlags[cat]);
    if (chart) {
      chart.data.datasets.forEach(ds => { if (ds.typeCategory === cat) ds.hidden = !visibilityFlags[cat]; });
      chart.update();
    }
  }

  function initVsChart() {
    buildPeriodOptions();
    renderSearchInputs();
    chart = new Chart(document.getElementById('aptChart').getContext('2d'), {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => `📅 계약일자: ${items[0].label}`,
              label: (ctx) => {
                const ds = ctx.dataset;
                const unit = (currentAreaMode === 'all') ? `${ctx.parsed.y}만원/평` : `${ctx.parsed.y}억`;
                if (ds.typeCategory === 'scatter') {
                  const d = ds.details ? ds.details[ctx.dataIndex] : null;
                  return d ? `🏢 ${ds.pureName}: ${unit} (전용 ${d.excluUseAr}㎡ / ${d.floor}층)` : `🏢 ${ds.pureName}: ${unit}`;
                }
                return `${ds.label}: ${unit}`;
              }
            }
          },
          zoom: {
            pan: { enabled: true, mode: 'y', modifierKey: null },
            zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'y' }
          }
        },
        scales: {
          x: { grid: { color: '#f1f5f9' }, ticks: { maxTicksLimit: 14 } },
          y: { title: { display: true, text: '실거래 가격 (억 원)' }, grid: { color: '#f1f5f9' } }
        }
      }
    });
    fetchAndRender();
  }

  // ===== Supabase Auth 로그인 & 닉네임 로직 =====
  const SUPABASE_AUTH_URL = "https://hikwjqgjollisdistbif.supabase.co";
  const SUPABASE_AUTH_KEY = "sb_publishable_eIzC8sNZ6gBe62KixTRm1w_1dE2dNG9";
  const supabaseClient = supabase.createClient(SUPABASE_AUTH_URL, SUPABASE_AUTH_KEY);

  // 운영자 고유 식별 번호 (관리자 전용 잠금)
  const ADMIN_UID = 'c29ebf61-5caf-4ff4-b119-d2aec688e1be';

  let currentUser = null;
  let siteNickname = '';
  let authStarted = false;
  const nickEl = id => document.getElementById(id);

  function renderAuth() {
    nickEl('btnKakaoLogin').style.display = currentUser ? 'none' : 'flex';
    nickEl('userProfile').style.display = currentUser && siteNickname ? 'flex' : 'none';
    nickEl('userName').textContent = siteNickname ? '🏷️ ' + siteNickname + '님' : '';

    // 투자 인사이트 작성 버튼: 로그인한 사용자가 운영자 UID와 일치할 때만 노출
    const insightBtn = document.getElementById('btnWriteInsight');
    if (insightBtn) {
      insightBtn.style.display = (currentUser && currentUser.id === ADMIN_UID) ? 'flex' : 'none';
    }
  }

  function openNicknameModal() {
    if (!currentUser || siteNickname) return;
    nickEl('nicknameInput').value = '';
    nickEl('nicknameMessage').textContent = '';
    if (!nickEl('nicknameModal').open) nickEl('nicknameModal').showModal();
    nickEl('nicknameInput').focus();
  }

  async function loadSiteNickname() {
    if (!currentUser) return;
    try {
      const { data, error } = await supabaseClient.from('profiles').select('nickname').eq('id', currentUser.id).maybeSingle();
      if (error) throw error;
      siteNickname = typeof data?.nickname === 'string' ? data.nickname.trim() : '';
      renderAuth();
      if (siteNickname) nickEl('nicknameModal').close();
      else openNicknameModal();
    } catch (_) { openNicknameModal(); }
  }

  function handleAuthChange(user) {
    currentUser = user;
    siteNickname = '';
    renderAuth();
    if (user) void loadSiteNickname();
  }

  function checkAuthSession() {
    if (authStarted) return;
    authStarted = true;
    supabaseClient.auth.onAuthStateChange((_event, session) => {
      setTimeout(() => handleAuthChange(session?.user || null), 0);
    });
  }

  nickEl('nicknameModal').addEventListener('cancel', event => {
    if (!siteNickname) event.preventDefault();
  });

  nickEl('nicknameForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (!currentUser) return;
    const nickname = nickEl('nicknameInput').value.trim();
    if (!/^[가-힣a-zA-Z0-9_]{2,12}$/.test(nickname)) {
      nickEl('nicknameMessage').textContent = '한글·영문·숫자 2~12자로 입력해 주세요.';
      nickEl('nicknameInput').focus();
      return;
    }
    const saveBtn = nickEl('nicknameSave');
    saveBtn.disabled = true;
    nickEl('nicknameMessage').textContent = '닉네임을 등록하고 있습니다…';

    try {
      const { error } = await supabaseClient.from('profiles').insert({ id: currentUser.id, nickname: nickname });
      if (error) {
        if (error.code === '23505') {
          nickEl('nicknameMessage').textContent = '이미 다른 회원이 사용 중인 닉네임입니다.';
          saveBtn.disabled = false;
          return;
        }
        throw error;
      }
      siteNickname = nickname;
      alert(`'${nickname}' 닉네임으로 확정되었습니다!`);
      renderAuth();
      nickEl('nicknameModal').close();
    } catch (err) {
      nickEl('nicknameMessage').textContent = '저장에 실패했습니다. 다시 시도해 주세요.';
    } finally {
      saveBtn.disabled = false;
    }
  });

  async function loginWithKakao() {
    try {
      const { error } = await supabaseClient.auth.signInWithOAuth({
        provider: 'kakao', options: { redirectTo: window.location.origin }
      });
      if (error) throw error;
    } catch (_) { alert('카카오 로그인에 실패했습니다.'); }
  }

  async function logoutKakao() {
    try {
      await supabaseClient.auth.signOut();
      currentUser = null;
      siteNickname = '';
      nickEl('nicknameModal').close();
      renderAuth();
    } catch (_) { alert('로그아웃 처리 중 오류가 발생했습니다.'); }
  }

  // ===== [호갱노노 스타일] 단지 전용 이야기 & 피드 엔진 =====
  let currentStoryAptName = '';

  async function openAptStoryModal(aptName) {
    currentStoryAptName = aptName;
    document.getElementById('aptStoryTitle').innerText = `${aptName} 이야기 & 후기`;
    document.getElementById('aptStoryModal').showModal();
    loadAptStories(aptName);
  }

  function closeAptStoryModal() {
    document.getElementById('aptStoryModal').close();
  }

  function openAptStoryWrite() {
    if (!currentUser) { alert('이야기를 작성하려면 카카오 로그인이 필요합니다.'); return; }
    if (!siteNickname) { openNicknameModal(); return; }
    openWriteModal('apt', currentStoryAptName);
  }

  async function loadAptStories(aptName) {
    const listContainer = document.getElementById('aptStoryListContainer');
    const galleryScroll = document.getElementById('aptGalleryScroll');
    const galleryBox = document.getElementById('aptGalleryBox');
    listContainer.innerHTML = '<div style="padding: 30px; text-align: center; color: #94a3b8;">이야기를 불러오는 중입니다...</div>';

    try {
      const { data: posts, error } = await supabaseClient
        .from('posts')
        .select('*')
        .eq('board_type', 'apt')
        .eq('apt_name', aptName)
        .order('created_at', { ascending: false });

      if (error) throw error;

      document.getElementById('aptStoryCount').innerText = posts ? posts.length : 0;

      const allImages = [];
      posts?.forEach(p => {
        if (p.image_urls && p.image_urls.length > 0) {
          allImages.push(...p.image_urls);
        }
      });

      if (allImages.length > 0) {
        galleryBox.style.display = 'block';
        galleryScroll.innerHTML = allImages.map(img => `<img class="apt-gallery-thumb" src="${img}" onclick="window.open('${img}', '_blank')">`).join('');
      } else {
        galleryBox.style.display = 'none';
      }

      if (!posts || posts.length === 0) {
        listContainer.innerHTML = `
          <div style="padding: 40px 20px; text-align: center; color: #94a3b8;">
            <div style="font-size: 30px; margin-bottom: 8px;">🏢</div>
            아직 등록된 단지 이야기가 없습니다.<br>
            첫 번째 실거주 후기나 단지 응원글을 남겨보세요!
          </div>
        `;
        return;
      }

      let html = '';
      posts.forEach(p => {
        const dateStr = p.created_at ? p.created_at.substring(0, 16).replace('T', ' ') : '-';
        let imgsHtml = '';
        if (p.image_urls && p.image_urls.length > 0) {
          imgsHtml = `<div class="story-card-photos">` + p.image_urls.map(url => `<img class="story-card-photo" src="${url}" onclick="window.open('${url}', '_blank')">`).join('') + `</div>`;
        }

        html += `
          <div class="story-card">
            <div class="story-card-meta">
              <span>🏷️ <strong>${p.nickname}</strong></span>
              <span>${dateStr}</span>
            </div>
            <div class="story-card-title">${p.title}</div>
            <div class="story-card-content">${p.content}</div>
            ${imgsHtml}
          </div>
        `;
      });
      listContainer.innerHTML = html;
    } catch(err) {
      listContainer.innerHTML = '<div style="padding: 20px; color: #ef4444; text-align: center;">이야기를 불러오지 못했습니다.</div>';
    }
  }

  // ===== 일반 게시판 및 이미지 다운사이징 엔진 =====
  let currentBoardType = 'insight';
  let quillInstance = null;

  function initQuillEditor() {
    if (quillInstance) return;

    // 툴바 구성: 캡처 원본 삽입(📷)과 스마트폰 사진 압축 삽입(📱) 분리
    const toolbarOptions = [
      [{ 'font': [] }, { 'size': ['small', false, 'large', 'huge'] }],
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'color': [] }, { 'background': [] }],
      [{ 'align': [] }],
      [{ 'list': 'ordered'}, { 'list': 'bullet' }],
      [{ 'indent': '-1'}, { 'indent': '+1' }],
      ['blockquote', 'link'],
      ['clean']
    ];

    quillInstance = new Quill('#insightQuillEditor', {
      theme: 'snow',
      placeholder: '글과 함께 부동산 인사이트를 기록해 보세요! 상단 툴바 버튼으로 사진을 넣을 수 있습니다.',
      modules: { toolbar: toolbarOptions }
    });

    // 툴바 끝에 직관적인 2종 사진 버튼 추가
    const tbEl = quillInstance.getModule('toolbar').container;
    const btnGroup = document.createElement('span');
    btnGroup.className = 'ql-formats';
    btnGroup.innerHTML = `
      <button type="button" id="btnUploadOriginal" title="PC 캡처·스크린샷 (100% 무압축 원본)" style="width:auto; padding:0 8px; font-weight:700; color:#0284c7; font-size:12px;">📷 캡처원본</button>
      <button type="button" id="btnUploadMobile" title="스마트폰 고용량 사진 (2048px 경량화 압축)" style="width:auto; padding:0 8px; font-weight:700; color:#16a34a; font-size:12px;">📱 폰사진압축</button>
    `;
    tbEl.appendChild(btnGroup);
    setupImageResizerEngine();
    setupInsightImageEditing();

    document.getElementById('btnUploadOriginal').onclick = () => selectAndUpload(false);
    document.getElementById('btnUploadMobile').onclick = () => selectAndUpload(true);

  }

  let activeResizerImg = null;
  let finishImageResize = null;
  let insightUploadPending = false;
  let insightDraftVersion = 0;
  let insightLastRange = null;

  function removeResizers() {
    if (finishImageResize) finishImageResize();
    activeResizerImg = null;
    const box = document.getElementById('quillImageResizerBox');
    if (box) box.style.display = 'none';
  }

  function updateResizerPosition() {
    const box = document.getElementById('quillImageResizerBox');
    const modal = document.getElementById('writeModal');
    if (!box || !activeResizerImg) return;
    if (!modal.open || !quillInstance.root.contains(activeResizerImg)) {
      removeResizers(); return;
    }
    const r = activeResizerImg.getBoundingClientRect();
    const rootRect = quillInstance.root.getBoundingClientRect();
    const m = modal.getBoundingClientRect();
    // Hide handles when the image is outside the editor's scrolling viewport.
    if (!r.width || r.bottom <= rootRect.top || r.top >= rootRect.bottom) {
      box.style.display = 'none'; return;
    }
    box.style.display = 'block';
    box.style.left = (r.left - m.left - modal.clientLeft + modal.scrollLeft) + 'px';
    box.style.top = (r.top - m.top - modal.clientTop + modal.scrollTop) + 'px';
    box.style.width = r.width + 'px';
    box.style.height = r.height + 'px';
  }

  function setupImageResizerEngine() {
    const root = quillInstance.root;
    const modal = document.getElementById('writeModal');
    const box = document.createElement('div');
    box.id = 'quillImageResizerBox';
    box.contentEditable = 'false';
    // A modal dialog occupies the top layer: the overlay must be inside it,
    // but outside Quill's editable DOM so Parchment never removes the handles.
    modal.appendChild(box);
    const selectImage = (e) => {
      if (e.target.tagName !== 'IMG') { removeResizers(); return; }
      // Let pointerdown retain native image dragging; select the embed on click.
      if (e.type === 'click') {
        e.preventDefault(); e.stopPropagation();
        const index = quillInstance.getIndex(Quill.find(e.target));
        quillInstance.setSelection(index, 1, 'user');
      }
      if (activeResizerImg !== e.target) removeResizers();
      activeResizerImg = e.target;
      updateResizerPosition();
    };
    root.addEventListener('pointerdown', selectImage, true);
    root.addEventListener('click', e => {
      if (e.target.tagName === 'IMG') selectImage(e);
    }, true);
    root.addEventListener('load', updateResizerPosition, true);
    root.addEventListener('keydown', removeResizers);
    document.addEventListener('pointerdown', e => {
      if (!root.contains(e.target) && !box.contains(e.target)) removeResizers();
    }, true);
    document.addEventListener('scroll', updateResizerPosition, true);
    window.addEventListener('resize', updateResizerPosition);
    new ResizeObserver(updateResizerPosition).observe(root);
    modal.addEventListener('close', () => { insightDraftVersion++; removeResizers(); });
    quillInstance.on('text-change', () => requestAnimationFrame(updateResizerPosition));
    quillInstance.on('selection-change', range => {
      if (range) insightLastRange = {index: range.index, length: range.length};
    });
    ['nw', 'ne', 'sw', 'se'].forEach(dir => {
      const handle = document.createElement('button');
      handle.type = 'button';
      handle.dataset.dir = dir;
      handle.setAttribute('aria-label', '이미지 크기 조절 ' + dir);
      box.appendChild(handle);
      handle.addEventListener('pointerdown', e => {
        if (!activeResizerImg || e.button !== 0) return;
        e.preventDefault(); e.stopPropagation();
        const img = activeResizerImg;
        const startX = e.clientX;
        const startWidth = img.getBoundingClientRect().width;
        const styleWidth = img.style.width;
        const pointerId = e.pointerId;
        let width = startWidth;
        const move = event => {
          if (event.pointerId !== pointerId) return;
          event.preventDefault();
          const cs = getComputedStyle(root);
          const max = root.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
          width = Math.round(Math.min(max, Math.max(Math.min(60, max), startWidth +
            (dir.endsWith('e') ? 1 : -1) * (event.clientX - startX))));
          img.style.width = width + 'px';
          updateResizerPosition();
        };
        const finish = event => {
          if (event && event.pointerId !== undefined && event.pointerId !== pointerId) return;
          document.removeEventListener('pointermove', move, true);
          document.removeEventListener('pointerup', finish, true);
          document.removeEventListener('pointercancel', finish, true);
          window.removeEventListener('blur', finish);
          finishImageResize = null;
          img.style.width = styleWidth;
          if (root.contains(img) && Math.round(startWidth) !== width) {
            const blot = Quill.find(img);
            const index = quillInstance.getIndex(blot);
            quillInstance.getModule('history').cutoff();
            quillInstance.formatText(index, 1, {width: String(width), height: false}, 'user');
            quillInstance.getModule('history').cutoff();
          }
          updateResizerPosition();
        };
        finishImageResize = finish;
        document.addEventListener('pointermove', move, true);
        document.addEventListener('pointerup', finish, true);
        document.addEventListener('pointercancel', finish, true);
        window.addEventListener('blur', finish);
      });
    });
  }

  let insightUploadRange = null;

  function rememberInsightSelection() {
    // Never focus the editor here: doing so can manufacture a cursor at zero.
    const range = quillInstance.getSelection();
    if (range) insightLastRange = {index: range.index, length: range.length};
    return insightLastRange;
  }

  function setupInsightImageEditing() {
    const q = quillInstance;
    const root = q.root;
    const modal = document.getElementById('writeModal');
    ['btnUploadOriginal', 'btnUploadMobile'].forEach(id => {
      const button = document.getElementById(id);
      const capture = e => {
        const range = rememberInsightSelection();
        insightUploadRange = range ? {...range} : {index: q.getLength() - 1, length: 0};
        // Capture before focus transfers from contenteditable to the toolbar.
        e.preventDefault();
      };
      button.addEventListener('pointerdown', capture);
      button.addEventListener('mousedown', capture);
    });
    // editor-change includes silent selection changes as well as user changes.
    q.on('editor-change', (name, range) => {
      if (name === 'selection-change' && range) {
        insightLastRange = {index: range.index, length: range.length};
      }
    });
    root.addEventListener('keyup', rememberInsightSelection);
    root.addEventListener('mouseup', rememberInsightSelection);

    // Use the system clipboard. Quill's existing HTML paste importer restores
    // the standard image embed (including width); no private clipboard fallback.
    ['copy', 'cut'].forEach(type => root.addEventListener(type, e => {
      const range = q.getSelection();
      if (!range || range.length !== 1 || !e.clipboardData) return;
      const data = q.getContents(range.index, 1);
      const op = data.ops[0];
      if (!op || !op.insert || typeof op.insert.image !== 'string') return;
      const image = document.createElement('img');
      image.src = op.insert.image;
      for (const attr of ['width', 'height', 'alt']) {
        if (op.attributes && op.attributes[attr] != null) image.setAttribute(attr, op.attributes[attr]);
      }
      e.clipboardData.setData('text/html', image.outerHTML);
      e.clipboardData.setData('text/plain', op.insert.image);
      e.preventDefault();
      e.stopImmediatePropagation();
      if (type === 'cut') {
        q.getModule('history').cutoff();
        q.deleteText(range.index, 1, 'user');
        q.getModule('history').cutoff();
        q.setSelection(range.index, 0, 'user');
        removeResizers();
      }
    }, true));

    let draggedImage = null;
    const marker = document.createElement('div');
    marker.id = 'insightImageDropMarker';
    marker.style.cssText = 'display:none;position:absolute;width:3px;background:#2563eb;pointer-events:none;z-index:10001;';
    modal.appendChild(marker);
    const clearDrag = () => { draggedImage = null; marker.style.display = 'none'; };
    const indexAtPoint = e => {
      let range;
      if (document.caretPositionFromPoint) {
        const caret = document.caretPositionFromPoint(e.clientX, e.clientY);
        if (caret) { range = document.createRange(); range.setStart(caret.offsetNode, caret.offset); range.collapse(true); }
      } else if (document.caretRangeFromPoint) {
        range = document.caretRangeFromPoint(e.clientX, e.clientY);
      }
      if (!range || !root.contains(range.startContainer)) return null;
      let node = range.startContainer;
      let offset = range.startOffset;
      // An element offset is a child boundary; a text offset is a character.
      if (node.nodeType === Node.ELEMENT_NODE && node.childNodes.length) {
        if (offset < node.childNodes.length) { node = node.childNodes[offset]; offset = 0; }
        else {
          node = node.lastChild;
          const blot = Quill.find(node, true);
          if (blot) return Math.min(q.getLength() - 1, q.getIndex(blot) + blot.length());
        }
      }
      if (node === root) return q.getLength() - 1;
      const blot = Quill.find(node, true);
      if (!blot) return null;
      const inner = blot.index ? blot.index(node, offset) : 0;
      return Math.max(0, Math.min(q.getLength() - 1, q.getIndex(blot) + Math.max(0, inner)));
    };
    root.addEventListener('dragstart', e => {
      if (e.target.tagName !== 'IMG' || !e.dataTransfer) return;
      if (finishImageResize) finishImageResize();
      draggedImage = e.target;
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/html', draggedImage.outerHTML);
      e.dataTransfer.setData('text/plain', draggedImage.src);
      e.dataTransfer.setData('application/x-insight-image', 'internal');
    });
    root.addEventListener('dragover', e => {
      if (!draggedImage || !root.contains(draggedImage)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const index = indexAtPoint(e);
      if (index === null) { marker.style.display = 'none'; return; }
      const bounds = q.getBounds(index);
      const container = q.container.getBoundingClientRect();
      const m = modal.getBoundingClientRect();
      marker.style.left = (container.left + bounds.left - m.left - modal.clientLeft + modal.scrollLeft) + 'px';
      marker.style.top = (container.top + bounds.top - m.top - modal.clientTop + modal.scrollTop) + 'px';
      marker.style.height = Math.max(18, bounds.height) + 'px';
      marker.style.display = 'block';
    });
    root.addEventListener('drop', e => {
      if (!draggedImage || !root.contains(draggedImage)) return;
      e.preventDefault(); e.stopPropagation();
      const target = indexAtPoint(e);
      const from = q.getIndex(Quill.find(draggedImage));
      const imageDelta = q.getContents(from, 1);
      clearDrag(); removeResizers();
      if (target === null || target === from || target === from + 1) return;
      const Delta = Quill.import('delta');
      // One Delta transaction preserves image attributes and one-step undo.
      const change = target < from
        ? new Delta().retain(target).concat(imageDelta).retain(from - target).delete(1)
        : new Delta().retain(from).delete(1).retain(target - from - 1).concat(imageDelta);
      q.getModule('history').cutoff();
      q.updateContents(change, 'user');
      q.getModule('history').cutoff();
      q.setSelection(target < from ? target : target - 1, 1, 'user');
    });
    root.addEventListener('dragleave', e => {
      if (!root.contains(e.relatedTarget)) marker.style.display = 'none';
    });
    document.addEventListener('dragend', clearDrag);
    modal.addEventListener('close', clearDrag);
  }

  function selectAndUpload(isCompress) {
    if (insightUploadPending) return;
    const range = insightUploadRange || rememberInsightSelection() || {index: quillInstance.getLength() - 1, length: 0};
    insightUploadRange = null;
    let insertionIndex = range.index;
    const draft = insightDraftVersion;
    const input = document.createElement('input');
    input.type = 'file'; input.accept = 'image/*';
    input.onchange = async () => {
      const file = input.files[0];
      if (!file || insightUploadPending) return;
      insightUploadPending = true;
      const trackEdits = delta => { insertionIndex = delta.transformPosition(insertionIndex); };
      quillInstance.on('text-change', trackEdits);
      const buttons = ['btnUploadOriginal', 'btnUploadMobile'].map(id => document.getElementById(id));
      buttons.forEach(button => { button.disabled = true; });
      try {
        const url = await processAndUploadImage(file, isCompress);
        if (draft !== insightDraftVersion || !document.getElementById('writeModal').open) return;
        quillInstance.off('text-change', trackEdits);
        const index = Math.min(insertionIndex, quillInstance.getLength() - 1);
        quillInstance.insertEmbed(index, 'image', url, 'user');
        quillInstance.setSelection(index + 1, 0, 'user');
        insightLastRange = {index: index + 1, length: 0};
      } catch (err) {
        alert('이미지 업로드에 실패했습니다: ' + err.message);
      } finally {
        quillInstance.off('text-change', trackEdits);
        insightUploadPending = false;
        buttons.forEach(button => { button.disabled = false; });
      }
    };
    input.click();
  }

  async function processAndUploadImage(file, isCompress) {
    let finalFile = file;
    let ext = file.name.split('.').pop() || 'png';
    let contentType = file.type || 'image/png';

    // 스마트폰 버튼을 눌렀을 때만 2048px WebP 리사이징
    if (isCompress) {
      finalFile = await resizeImage(file, 2048, 0.88);
      ext = 'webp';
      contentType = 'image/webp';
    }

    const fileName = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}.${ext}`;
    const filePath = `posts/${fileName}`;

    const { error } = await supabaseClient.storage
      .from('board-images')
      .upload(filePath, finalFile, {
        contentType: contentType,
        cacheControl: '3600',
        upsert: false
      });

    if (error) throw error;
    const { data: { publicUrl } } = supabaseClient.storage.from('board-images').getPublicUrl(filePath);
    return publicUrl;
  }
  let currentSelectedRegion = '전체';
  let currentTargetApt = '';
  let pendingCompressedImages = [];

  function filterRegionBoard(region, btn) {
    currentSelectedRegion = region;
    document.querySelectorAll('.region-pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadPosts('region');
  }

  const insightCategories = {real_estate:'🏢 부동산 분석',stock_macro:'📈 주식·매크로',personal_finance:'💡 생활금융'};
  let insightCategory = 'all';
  let insightLoadSequence = 0;
  function insightEscape(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function insightImage(value) {
    try { const u = new URL(value); return ['https:','http:'].includes(u.protocol) ? u.href : ''; } catch { return ''; }
  }
  function filterInsights(category, button) {
    insightCategory = category;
    document.querySelectorAll('#insightFilters button').forEach(b => {
      b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button));
    });
    loadPosts('insight');
  }
  async function loadInsightCards() {
    const sequence = ++insightLoadSequence;
    const category = insightCategory;
    const grid = document.getElementById('insightGrid');
    document.getElementById('insightDetailView').style.display = 'none';
    document.getElementById('insightListView').style.display = 'block';
    grid.innerHTML = '<p class="insight-status">글을 불러오는 중입니다…</p>';
    try {
      const {data, error} = await supabaseClient.from('posts').select('*').eq('board_type','insight').order('created_at',{ascending:false});
      if (sequence !== insightLoadSequence) return;
      if (error) throw error;
      const posts = (data || []).filter(p => category === 'all' || (p.category || 'real_estate') === category);
      grid.innerHTML = posts.length ? posts.map(p => {
        const cat = Object.hasOwn(insightCategories,p.category) ? p.category : 'real_estate';
        const label = insightCategories[cat];
        const img = insightImage(Array.isArray(p.image_urls) ? p.image_urls[0] : '');
        const id = encodeURIComponent(String(p.id));
        return `<article class="insight-card"><a href="/insight/${id}">
          <div class="insight-cover" data-category="${cat}">${img ? `<img src="${insightEscape(img)}" alt="${insightEscape(p.title)}" loading="lazy" onerror="this.replaceWith(document.createTextNode('📖'))">` : label.split(' ')[0]}</div>
          <div class="insight-card-body"><span class="insight-badge">${label}</span>
          <h2>${insightEscape(p.title)}</h2><p class="insight-excerpt">${insightEscape(p.content)}</p>
          <div class="insight-meta"><time>${insightEscape((p.created_at || '').slice(0,10))}</time><span>조회 ${Number(p.views) || 0}</span></div></div></a>
          <button class="insight-quick" data-post-id="${insightEscape(p.id)}">빠른 보기 · 댓글</button></article>`;
      }).join('') : '<p class="insight-status">등록된 글이 없습니다.</p>';
      grid.querySelectorAll('.insight-quick').forEach(b => b.addEventListener('click', () => viewPostDetail(b.dataset.postId,'insight')));
    } catch (err) {
      if (sequence === insightLoadSequence) grid.innerHTML = '<p class="insight-status">글을 불러오지 못했습니다. 카테고리를 눌러 다시 시도해 주세요.</p>';
    }
  }
  async function loadPosts(boardType) {
    if (boardType === 'insight') { currentBoardType = boardType; return loadInsightCards(); }
    currentBoardType = boardType;
    const isInsight = (boardType === 'insight');
    const tbody = document.getElementById(isInsight ? 'insightTableBody' : 'boardTableBody');
    const detailBox = document.getElementById(isInsight ? 'insightDetailView' : 'boardDetailView');
    const listBox = document.getElementById(isInsight ? 'insightListView' : 'boardListView');
    
    detailBox.style.display = 'none';
    listBox.style.display = 'block';
    tbody.innerHTML = `<tr><td colspan="${isInsight ? 5 : 6}" style="padding: 30px; color: #94a3b8;">목록을 불러오는 중...</td></tr>`;

    try {
      let query = supabaseClient.from('posts').select('*').eq('board_type', boardType).order('created_at', { ascending: false });
      if (!isInsight && currentSelectedRegion !== '전체') {
        query = query.eq('region', currentSelectedRegion);
      }
      const { data: posts, error } = await query;
      if (error) throw error;

      if (!posts || posts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${isInsight ? 5 : 6}" style="padding: 30px; color: #94a3b8;">등록된 게시글이 없습니다.</td></tr>`;
        return;
      }

      let html = '';
      posts.forEach((p, idx) => {
        const postNum = posts.length - idx;
        const dateStr = p.created_at ? p.created_at.substring(0, 10) : '-';
        const hasImgBadge = (p.image_urls && p.image_urls.length > 0) ? `<span class="img-badge">📷 사진</span>` : '';
        const regionBadge = (!isInsight && p.region) ? `<span class="region-badge">${p.region}</span>` : '';

        html += `
          <tr>
            <td style="color: #64748b;">${postNum}</td>
            ${!isInsight ? `<td>${regionBadge}</td>` : ''}
            <td style="text-align: left;">
              <span class="post-title-link" onclick="viewPostDetail(${p.id}, '${boardType}')">${p.title} ${hasImgBadge}</span>
            </td>
            <td style="font-weight: 600; color: #0284c7;">${p.nickname}</td>
            <td style="color: #64748b; font-size: 13px;">${dateStr}</td>
            <td style="color: #64748b;">${p.views || 0}</td>
          </tr>
        `;
      });
      tbody.innerHTML = html;
    } catch(err) {
      tbody.innerHTML = `<tr><td colspan="${isInsight ? 5 : 6}" style="padding: 30px; color: #ef4444;">게시글을 불러오지 못했습니다.</td></tr>`;
    }
  }

  async function viewPostDetail(postId, boardType) {
    const isInsight = (boardType === 'insight');
    const listBox = document.getElementById(isInsight ? 'insightListView' : 'boardListView');
    const detailBox = document.getElementById(isInsight ? 'insightDetailView' : 'boardDetailView');

    try {
      const { data: post, error } = await supabaseClient.from('posts').select('*').eq('id', postId).single();
      if (error || !post) throw error;

      supabaseClient.from('posts').update({ views: (post.views || 0) + 1 }).eq('id', postId).then(() => {});

      let imgHtml = '';
      const inlineDoc = new DOMParser().parseFromString(isInsight ? (post.content || '') : '', 'text/html');
      const inlineUrls = new Set(Array.from(inlineDoc.querySelectorAll('img'), img => img.getAttribute('src')));
      if (post.image_urls && post.image_urls.length > 0) {
        post.image_urls.forEach(url => {
          if (inlineUrls.has(url)) return;
          imgHtml += `<img src="${insightEscape(insightImage(url))}" loading="lazy">`;
        });
      }

      const dateStr = post.created_at ? post.created_at.substring(0, 16).replace('T', ' ') : '-';
      detailBox.innerHTML = `
        <button onclick="backToList('${boardType}')" style="margin-bottom: 16px; padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; font-size: 13px;">← 목록으로 돌아가기</button>
        ${isInsight ? `<p><a href="/insight/${encodeURIComponent(String(post.id))}">이 글의 고유 주소로 열기 ↗</a></p>` : ''}
        <div class="post-detail-title">${post.region ? `[${insightEscape(post.region)}] ` : ''}${insightEscape(post.title)}</div>
        <div class="post-detail-meta">
          <span>작성자: <strong>${insightEscape(post.nickname)}</strong></span>
          <span>등록일: ${dateStr}</span>
          <span>조회수: ${(post.views || 0) + 1}</span>
        </div>
        <div class="post-detail-content ${isInsight ? 'ql-editor' : ''}">${(boardType === 'insight') ? (post.content || '') : insightEscape(post.content)}</div>
        <div class="post-detail-images">${imgHtml}</div>

        <div class="comments-section">
          <div class="comments-title">💬 댓글 <span id="commentCount">0</span>개</div>
          <div id="commentsList_${postId}"><div style="color:#94a3b8; font-size:13px;">댓글 로딩 중...</div></div>
          <form class="comment-form" onsubmit="submitComment(event, ${postId})">
            <input type="text" id="commentInput_${postId}" class="comment-input" placeholder="${currentUser ? '댓글을 작성해 보세요' : '로그인 후 댓글 작성이 가능합니다'}" ${!currentUser ? 'disabled' : ''} required>
            <button type="submit" style="padding: 8px 16px; background: #2563eb; color: white; border: none; border-radius: 8px; font-weight: 700; cursor: pointer;" ${!currentUser ? 'disabled' : ''}>등록</button>
          </form>
        </div>
      `;

      listBox.style.display = 'none';
      detailBox.style.display = 'block';
      loadComments(postId);
    } catch(err) {
      alert('게시글을 불러올 수 없습니다.');
    }
  }

  function backToList(boardType) {
    const isInsight = (boardType === 'insight');
    document.getElementById(isInsight ? 'insightDetailView' : 'boardDetailView').style.display = 'none';
    document.getElementById(isInsight ? 'insightListView' : 'boardListView').style.display = 'block';
  }

  async function loadComments(postId) {
    const container = document.getElementById(`commentsList_${postId}`);
    if (!container) return;
    try {
      const { data: comments, error } = await supabaseClient.from('comments').select('*').eq('post_id', postId).order('created_at', { ascending: true });
      if (error) throw error;
      document.getElementById('commentCount').innerText = comments.length;
      if (comments.length === 0) {
        container.innerHTML = '<div style="color:#94a3b8; font-size:13px; padding: 10px 0;">첫 댓글을 남겨보세요!</div>';
        return;
      }
      let html = '';
      comments.forEach(c => {
        const timeStr = c.created_at ? c.created_at.substring(5, 16).replace('T', ' ') : '';
        html += `
          <div class="comment-item">
            <div class="comment-meta">
              <span style="color:#0284c7;">🏷️ ${c.nickname}</span>
              <span style="color:#94a3b8; font-weight: 400;">${timeStr}</span>
            </div>
            <div class="comment-body">${c.content}</div>
          </div>
        `;
      });
      container.innerHTML = html;
    } catch(e) {}
  }

  async function submitComment(e, postId) {
    e.preventDefault();
    if (!currentUser) { alert('로그인이 필요합니다.'); return; }
    if (!siteNickname) { openNicknameModal(); return; }
    const input = document.getElementById(`commentInput_${postId}`);
    const content = input.value.trim();
    if (!content) return;

    try {
      const { error } = await supabaseClient.from('comments').insert({
        post_id: postId, author_id: currentUser.id, nickname: siteNickname, content: content
      });
      if (error) throw error;
      input.value = '';
      loadComments(postId);
    } catch(err) {
      alert('댓글 등록 실패: ' + err.message);
    }
  }

  async function resizeImage(file, maxWidth = 1200, quality = 0.8) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const objectUrl = URL.createObjectURL(file);
      img.onload = () => {
        URL.revokeObjectURL(objectUrl);
        let width = img.width;
        let height = img.height;
        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob((blob) => {
          if (!blob || blob.type !== 'image/webp') return reject(new Error('이 브라우저에서 WebP 변환을 지원하지 않습니다. 캡처원본을 사용해 주세요.'));
          const resizedFile = new File([blob], file.name.replace(/[.][^/.]+$/, "") + ".webp", {
            type: "image/webp", lastModified: Date.now()
          });
          resolve(resizedFile);
        }, "image/webp", quality);
      };
      img.onerror = () => { URL.revokeObjectURL(objectUrl); reject(new Error('이미지를 읽을 수 없습니다. JPG 또는 PNG 파일을 사용해 주세요.')); };
      img.src = objectUrl;
    });
  }

  async function handleImageSelection(input) {
    const previewContainer = document.getElementById('imagePreviewContainer');
    previewContainer.innerHTML = '';
    pendingCompressedImages = [];
    const files = Array.from(input.files);

    if (files.length > 5) {
      alert('이미지는 한 번에 최대 5장까지만 첨부할 수 있습니다.');
      input.value = '';
      return;
    }

    for (const f of files) {
      try {
        const compressed = await resizeImage(f, 1200, 0.8);
        pendingCompressedImages.push(compressed);
        const imgElem = document.createElement('img');
        imgElem.className = 'img-preview-item';
        imgElem.src = URL.createObjectURL(compressed);
        previewContainer.appendChild(imgElem);
      } catch(e) {
        console.error('이미지 리사이징 실패:', e);
      }
    }
  }

  function openWriteModal(boardType, targetApt = '') {
    if (!currentUser) { alert('글을 작성하려면 카카오 로그인이 필요합니다.'); return; }
    if (!siteNickname) { openNicknameModal(); return; }

    insightDraftVersion++;
    removeResizers();
    insightLastRange = null;
    insightUploadRange = null;
    currentBoardType = boardType;
    currentTargetApt = targetApt;
    document.getElementById('insightCategoryGroup').style.display = boardType === 'insight' ? 'block' : 'none';
    document.getElementById('postCategorySelect').value = 'real_estate';

    if (boardType === 'apt') {
      document.getElementById('writeModalTitle').innerText = `🏢 ${targetApt} 이야기 등록`;
      document.getElementById('regionSelectGroup').style.display = 'none';
      document.getElementById('postTitleInput').placeholder = '예: 2년 실거주 후기, 로열동 추천, 학군 배정 후기';
    } else if (boardType === 'insight') {
      document.getElementById('writeModalTitle').innerText = '✍️ 투자 인사이트 칼럼 작성';
      document.getElementById('regionSelectGroup').style.display = 'none';
      document.getElementById('postTitleInput').placeholder = '제목을 입력하세요';
    } else {
      document.getElementById('writeModalTitle').innerText = '💬 지역 게시판 글쓰기';
      document.getElementById('regionSelectGroup').style.display = 'block';
      document.getElementById('postTitleInput').placeholder = '제목을 입력하세요';
    }

    document.getElementById('postTitleInput').value = '';
    document.getElementById('postContentInput').value = '';
    document.getElementById('postImageInput').value = '';
    document.getElementById('imagePreviewContainer').innerHTML = '';
    pendingCompressedImages = [];

    if (boardType === 'insight') {
      initQuillEditor();
      document.getElementById('insightEditorGroup').style.display = 'block';
      document.getElementById('normalContentGroup').style.display = 'none';
      document.getElementById('normalImageGroup').style.display = 'none';
      document.getElementById('postContentInput').removeAttribute('required');
      if (quillInstance) quillInstance.setText('', 'silent');
    } else {
      document.getElementById('insightEditorGroup').style.display = 'none';
      document.getElementById('normalContentGroup').style.display = 'block';
      document.getElementById('normalImageGroup').style.display = 'block';
      document.getElementById('postContentInput').setAttribute('required', 'required');
    }
    document.getElementById('writeModal').showModal();
  }

  function closeWriteModal() { insightDraftVersion++; removeResizers(); document.getElementById('writeModal').close(); }

  document.getElementById('postWriteForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentUser) return;
    if (currentBoardType === 'insight' && insightUploadPending) {
      alert('이미지 업로드가 끝난 후 등록해 주세요.'); return;
    }
    removeResizers();
    const title = document.getElementById('postTitleInput').value.trim();
    let content = '';
    let uploadedUrls = [];

    if (currentBoardType === 'insight') {
      content = quillInstance.root.innerHTML;
      if (!quillInstance.getText().trim() && !content.includes('<img')) {
        alert('내용을 입력해 주세요.');
        return;
      }
      const parser = new DOMParser();
      const doc = parser.parseFromString(content, 'text/html');
      doc.querySelectorAll('img').forEach(img => {
        if (img.src) uploadedUrls.push(img.src);
      });
    } else {
      content = document.getElementById('postContentInput').value.trim();
    }
    const region = (currentBoardType === 'region') ? document.getElementById('postRegionSelect').value : null;
    const aptName = (currentBoardType === 'apt') ? currentTargetApt : null;
    const submitBtn = document.getElementById('btnSubmitPost');
    submitBtn.disabled = true;
    submitBtn.innerText = '업로드 중…';

    try {
      if (currentBoardType !== 'insight') {
      for (const imgFile of pendingCompressedImages) {
        const fileExt = 'webp';
        const fileName = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}.${fileExt}`;
        const filePath = `posts/${fileName}`;

        const { data: uploadData, error: uploadErr } = await supabaseClient.storage
          .from('board-images')
          .upload(filePath, imgFile);

        if (!uploadErr) {
          const { data: { publicUrl } } = supabaseClient.storage.from('board-images').getPublicUrl(filePath);
          uploadedUrls.push(publicUrl);
        }
      }
      }

      const { error: insertErr } = await supabaseClient.from('posts').insert({
        board_type: currentBoardType,
        ...(currentBoardType === 'insight' ? {category: document.getElementById('postCategorySelect').value} : {}),
        region: region,
        apt_name: aptName,
        title: title,
        content: content,
        image_urls: uploadedUrls,
        author_id: currentUser.id,
        nickname: siteNickname,
        views: 0
      });
      if (insertErr) throw insertErr;

      alert('성공적으로 등록되었습니다!');
      closeWriteModal();

      if (currentBoardType === 'apt') {
        loadAptStories(currentTargetApt);
      } else {
        loadPosts(currentBoardType);
      }
    } catch(err) {
      alert('글 등록 실패: ' + err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerText = '등록하기';
    }
  });

  window.onload = () => {
    checkAuthSession();
    buildYearButtons();
    navigateTo(location.hash === '#insight' ? 'insight' : 'home');
  };
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return UI_HTML

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)