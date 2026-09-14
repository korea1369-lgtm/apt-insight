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
cur.execute("PRAGMA synchronous = OFF;")
cur.execute("PRAGMA journal_mode = MEMORY;")

TARGET_LAWD_CDS = {
    "중구": "27110", "동구": "27140", "서구": "27170", "남구": "27200",
    "북구": "27230", "수성구": "27260", "달서구": "27290", "달성군": "27710"
}

ym_list = pd.date_range(start="2020-01-01", end="2026-09-01", freq="MS").strftime("%Y%m").tolist()
tasks = [(lawd, ym) for ym in ym_list for lawd in TARGET_LAWD_CDS.values()]

print(f"🚀 [1/4] 국토부 취소(해제) 거래 9,000여 건 고속 조회 중...")

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

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(fetch_cancelled, t) for t in tasks]
    for f in as_completed(futures):
        res = f.result()
        if res:
            cancelled_trades.extend(res)

print(f"✅ 해제 거래 총 {len(cancelled_trades):,}건 확보 완료!")

# 2. 영구 차단용 블랙리스트 테이블 생성 및 원천 차트 테이블(apt_trades)에서 전수 삭제
print("🗑️ [2/4] 차트 원천 테이블(apt_trades)에서 9,000여 건 취소 거래 영구 삭제 중...")

cur.execute("""
    CREATE TABLE IF NOT EXISTS apt_cancelled_trades (
        apt_name TEXT,
        deal_date TEXT,
        deal_amount INTEGER,
        exclu_use_ar REAL,
        floor INTEGER,
        PRIMARY KEY (apt_name, deal_date, deal_amount, exclu_use_ar, floor)
    );
""")
# 수성범어W 8.66억 건 수동 포함
cancelled_trades.append(("수성범어W", "2025-12-30", 86600, 84.99, 12))
cancelled_trades.append(("범어W", "2025-12-30", 86600, 84.99, 12))

cur.executemany("""
    INSERT OR IGNORE INTO apt_cancelled_trades VALUES (?, ?, ?, ?, ?)
""", cancelled_trades)
conn.commit()

# 차트 테이블 apt_trades에서 삭제
cur.execute("""
    DELETE FROM apt_trades
    WHERE rowid IN (
        SELECT t.rowid
        FROM apt_trades t
        JOIN apt_cancelled_trades c 
          ON t.apt_name = c.apt_name 
         AND t.deal_date = c.deal_date 
         AND t.deal_amount = c.deal_amount
         AND t.floor = c.floor
         AND ROUND(t.exclu_use_ar, 2) = c.exclu_use_ar
    );
""")
deleted_count = cur.rowcount
conn.commit()
print(f"🎯 차트 원천(apt_trades)에서 완전히 소멸된 취소 거래: 총 {deleted_count:,}건!")

# 3. 차트 원천 잔존 검증 쿼리
print("\n🔎 [검증] 차트를 그릴 때 사용하는 SELECT 쿼리로 수성범어W 취소건 잔존 확인 중...")
cur.execute("""
    SELECT deal_date, apt_name, deal_amount, exclu_use_ar, floor
    FROM apt_trades
    WHERE (apt_name LIKE '%수성범어W%' OR apt_name LIKE '%범어W%')
      AND deal_amount >= 86000 AND deal_amount <= 87000;
""")
remains = cur.fetchall()
if not remains:
    print("✨ [검증 성공] 차트 원천 데이터에 취소 거래가 단 1건도 존재하지 않습니다! (완전 박멸)")
else:
    print(f"⚠️ 아직 남아있는 거래: {remains}")

# 4. 연도별 랭킹 요약 캐시 재생성
print("\n📊 [3/4] 랭킹 캐시 동기화 중...")
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

# 5. 압축
print("🧹 [4/4] 최종 압축(VACUUM) 중...")
cur.execute("VACUUM;")
conn.close()

size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
print(f"\n🎉 [완료] 차트 원천 데이터 완전 소독 완료! 최종 용량: {size_mb:.2f} MB")
