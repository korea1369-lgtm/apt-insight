import sqlite3
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
SERVICE_KEY = "cf3c93776dd439770d18b80d5c35a8ac14ea00bd7e5373a28f872d269514a05a"
DB_PATH = "apt_data_render_master.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1. 확정 취소건(수성범어W 등) 우선 삭제
print("🧹 [1/4] 확정 이상치/취소 거래 선제거 중...")
cur.execute("""
    DELETE FROM apt_trades 
    WHERE (apt_name LIKE '%수성범어W%' OR apt_name LIKE '%범어W%') 
      AND deal_amount >= 86000 AND deal_amount <= 87000
      AND deal_date LIKE '2025-12%';
""")
conn.commit()

# 2. 2006년 1월 ~ 2026년 9월 전체 연월 생성 (총 20년 치)
TARGET_LAWD_CDS = {
    "중구": "27110", "동구": "27140", "서구": "27170", "남구": "27200",
    "북구": "27230", "수성구": "27260", "달서구": "27290", "달성군": "27710"
}

ym_list = pd.date_range(start="2006-01-01", end="2026-09-01", freq="MS").strftime("%Y%m").tolist()
tasks = []
for ym in ym_list:
    for gu, lawd in TARGET_LAWD_CDS.items():
        tasks.append((lawd, ym))

print(f"🚀 [2/4] 대구 전역 20년 치(2006~2026) 총 {len(tasks):,}개 구간 해제 거래 병렬 전수 스캔 시작...")

cancelled_trades = []

def fetch_cancelled(task):
    lawd, ym = task
    url = f"{API_URL}?serviceKey={SERVICE_KEY}&LAWD_CD={lawd}&DEAL_YMD={ym}&pageNo=1&numOfRows=9999"
    results = []
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200 and "<item>" in res.text:
            root = ET.fromstring(res.text)
            for item in root.findall(".//item"):
                cdeal_day = (item.findtext("cdealDay") or "").strip()
                cdeal_type = (item.findtext("cdealType") or "").strip()
                if cdeal_day or cdeal_type in ['O', 'Y', '1']:
                    apt_name = (item.findtext("aptNm") or "").strip()
                    year = (item.findtext("dealYear") or "").strip()
                    month = (item.findtext("dealMonth") or "").strip().zfill(2)
                    day = (item.findtext("dealDay") or "").strip().zfill(2)
                    deal_date = f"{year}-{month}-{day}"
                    deal_amount = int((item.findtext("dealAmount") or "0").replace(",", "").strip())
                    exclu_use_ar = round(float(item.findtext("excluUseAr") or 0), 2)
                    fl = (item.findtext("floor") or "0").strip()
                    floor = int(fl) if fl and fl != "-" else 0
                    if apt_name and deal_amount > 0:
                        results.append((apt_name, deal_date, deal_amount, exclu_use_ar, floor))
    except Exception:
        pass
    return results

completed = 0
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(fetch_cancelled, t) for t in tasks]
    for f in as_completed(futures):
        res = f.result()
        if res:
            cancelled_trades.extend(res)
        completed += 1
        if completed % 300 == 0 or completed == len(tasks):
            print(f"   스캔 진행률: {completed}/{len(tasks)} (발견된 취소 거래: {len(cancelled_trades)}건)")

print(f"\n⚠️ 20년 치 스캔 결과 대구 전역 국토부 해제 거래: 총 {len(cancelled_trades):,}건 확인")

# 3. 마스터 DB 대조 전수 삭제
if cancelled_trades:
    cur.execute("DROP TABLE IF EXISTS temp_all_cancelled;")
    cur.execute("""
        CREATE TEMP TABLE temp_all_cancelled (
            apt_name TEXT, deal_date TEXT, deal_amount INTEGER, exclu_use_ar REAL, floor INTEGER
        );
    """)
    cur.executemany("INSERT INTO temp_all_cancelled VALUES (?, ?, ?, ?, ?)", cancelled_trades)
    
    cur.execute("""
        DELETE FROM apt_trades
        WHERE EXISTS (
            SELECT 1 FROM temp_all_cancelled c
            WHERE apt_trades.apt_name = c.apt_name
              AND apt_trades.deal_date = c.deal_date
              AND apt_trades.deal_amount = c.deal_amount
              AND apt_trades.floor = c.floor
              AND ROUND(apt_trades.exclu_use_ar, 2) = c.exclu_use_ar
        );
    """)
    purged_cnt = cur.rowcount
    conn.commit()
    print(f"🗑️ [3/4] 마스터 DB에서 일치하여 완전히 제거된 과거 취소 거래: 총 {purged_cnt:,}건")

# 4. 연도별 랭킹 요약 캐시 재생성 (2010~2026 순수 정상 거래 기반)
print("\n📊 [4/4] 2010~2026 연도별 랭킹 요약 캐시 재생성 중...")
cur.execute("DROP TABLE IF EXISTS apt_rank_yearly_summary;")
cur.execute("""
    CREATE TABLE apt_rank_yearly_summary AS
    WITH ranked_max AS (
        SELECT 
            CAST(SUBSTR(deal_date, 1, 4) AS INTEGER) AS deal_year,
            apt_name,
            SUBSTR(lawd_cd, 1, 5) AS lawd_5,
            deal_date,
            deal_amount,
            exclu_use_ar,
            floor,
            ROW_NUMBER() OVER (
                PARTITION BY CAST(SUBSTR(deal_date, 1, 4) AS INTEGER), apt_name, SUBSTR(lawd_cd, 1, 5)
                ORDER BY deal_amount DESC
            ) as rn
        FROM apt_trades
        WHERE deal_date >= '2010-01-01' AND apt_name IS NOT NULL AND apt_name != ''
    ),
    stats_summary AS (
        SELECT 
            CAST(SUBSTR(deal_date, 1, 4) AS INTEGER) AS deal_year,
            apt_name,
            SUBSTR(lawd_cd, 1, 5) AS lawd_5,
            COUNT(*) AS total_trade_cnt,
            SUM(CASE WHEN exclu_use_ar >= 83.0 AND exclu_use_ar <= 85.99 THEN 1 ELSE 0 END) AS trade_cnt_84,
            SUM(CASE WHEN exclu_use_ar >= 58.0 AND exclu_use_ar <= 60.99 THEN 1 ELSE 0 END) AS trade_cnt_59,
            ROUND(MAX(deal_amount / 10000.0), 3) AS max_price,
            ROUND(AVG(deal_amount / 10000.0), 2) AS avg_price,
            ROUND(MAX(deal_amount / (exclu_use_ar / 3.30578)), 1) AS max_pyeong,
            ROUND(AVG(deal_amount / (exclu_use_ar / 3.30578)), 1) AS avg_pyeong,
            ROUND(MAX(CASE WHEN exclu_use_ar >= 83.0 AND exclu_use_ar <= 85.99 THEN deal_amount / 10000.0 END), 3) AS max_84_price,
            ROUND(AVG(CASE WHEN exclu_use_ar >= 83.0 AND exclu_use_ar <= 85.99 THEN deal_amount / 10000.0 END), 2) AS avg_84_price,
            ROUND(MAX(CASE WHEN exclu_use_ar >= 58.0 AND exclu_use_ar <= 60.99 THEN deal_amount / 10000.0 END), 3) AS max_59_price,
            ROUND(AVG(CASE WHEN exclu_use_ar >= 58.0 AND exclu_use_ar <= 60.99 THEN deal_amount / 10000.0 END), 2) AS avg_59_price,
            AVG(deal_amount / (exclu_use_ar / 3.30578)) as mean_pyeong,
            AVG((deal_amount / (exclu_use_ar / 3.30578)) * (deal_amount / (exclu_use_ar / 3.30578))) as mean_sq_pyeong
        FROM apt_trades
        WHERE deal_date >= '2010-01-01' AND apt_name IS NOT NULL AND apt_name != ''
        GROUP BY CAST(SUBSTR(deal_date, 1, 4) AS INTEGER), apt_name, SUBSTR(lawd_cd, 1, 5)
    )
    SELECT 
        s.deal_year, s.apt_name, s.lawd_5,
        s.total_trade_cnt, s.trade_cnt_84, s.trade_cnt_59,
        s.max_price, s.avg_price, s.max_pyeong, s.avg_pyeong,
        s.max_84_price, s.avg_84_price, s.max_59_price, s.avg_59_price,
        r.deal_date AS max_p_date,
        ROUND(r.exclu_use_ar, 1) AS max_p_area,
        ROUND((r.exclu_use_ar / 3.30578) * 1.3, 1) AS max_p_pyeong_est,
        COALESCE(r.floor, '-') AS max_p_floor,
        CASE 
            WHEN s.total_trade_cnt >= 2 AND s.mean_pyeong > 0 AND (s.mean_sq_pyeong - (s.mean_pyeong * s.mean_pyeong)) > 0
            THEN ROUND((SQRT(s.mean_sq_pyeong - (s.mean_pyeong * s.mean_pyeong)) / s.mean_pyeong) * 100.0, 1)
            ELSE 0.0
        END AS dispersion_cv
    FROM stats_summary s
    LEFT JOIN ranked_max r
      ON s.deal_year = r.deal_year AND s.apt_name = r.apt_name AND s.lawd_5 = r.lawd_5 AND r.rn = 1;
""")

cur.execute("CREATE INDEX IF NOT EXISTS idx_rank_lookup ON apt_rank_yearly_summary(deal_year, lawd_5);")
conn.commit()

# VACUUM 압축
cur.execute("VACUUM;")
conn.close()

size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
print(f"\n🎉 20년 치 전수 취소 소독 완료! 최종 DB 용량: {size_mb:.2f} MB")
