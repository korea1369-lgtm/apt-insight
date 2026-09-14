import os
import sqlite3
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime

API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
SERVICE_KEY = "cf3c93776dd439770d18b80d5c35a8ac14ea00bd7e5373a28f872d269514a05a"
DB_PATH = "apt_data_render_master.db"

if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f"❌ {DB_PATH} 파일을 찾을 수 없습니다. 프로젝트 루트에 파일이 있는지 확인하세요.")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1. 기존 취소 거래(수성범어W 등) 일괄 정제
print("🧹 [1/4] 기존 DB 내 취소/해제 거래 정제 중...")
cur.execute("""
    DELETE FROM apt_trades 
    WHERE (apt_name LIKE '%수성범어W%' OR apt_name LIKE '%범어W%') 
      AND deal_amount = 86000 
      AND deal_date LIKE '%12-30%'
""")
conn.commit()

# 2. DB 최신 거래일 조회
max_row = cur.execute("SELECT MAX(deal_date) FROM apt_trades").fetchone()
last_deal_date = max_row[0] if max_row and max_row[0] else "2026-08-31"
print(f"📅 현재 DB 최신 거래일: {last_deal_date}")

TARGET_LAWD_CDS = {
    "중구": "27110", "동구": "27140", "서구": "27170", "남구": "27200",
    "북구": "27230", "수성구": "27260", "달서구": "27290", "달성군": "27710"
}

ym_list = ["202608", "202609"]
new_trades = []

cur.execute("SELECT apt_name, deal_date, deal_amount, exclu_use_ar, floor FROM apt_trades WHERE deal_date >= '2026-08-01'")
existing_keys = set(cur.fetchall())

print("🚀 [2/4] 국토부 공공데이터포털 실시간 수집 시작 (대구 전역)...")

for ym in ym_list:
    for gu_name, lawd in TARGET_LAWD_CDS.items():
        url = f"{API_URL}?serviceKey={SERVICE_KEY}&LAWD_CD={lawd}&DEAL_YMD={ym}&pageNo=1&numOfRows=9999"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                continue
            root = ET.fromstring(res.text)
            items = root.findall(".//item")
            
            for item in items:
                cdeal_day = (item.findtext("cdealDay") or "").strip()
                cdeal_type = (item.findtext("cdealType") or "").strip()
                if cdeal_day or (cdeal_type in ['O', 'Y', '1']):
                    continue
                
                apt_name = (item.findtext("aptNm") or "").strip()
                if not apt_name:
                    continue
                
                year = (item.findtext("dealYear") or "").strip()
                month = (item.findtext("dealMonth") or "").strip().zfill(2)
                day = (item.findtext("dealDay") or "").strip().zfill(2)
                deal_date = f"{year}-{month}-{day}"
                
                deal_amount_str = (item.findtext("dealAmount") or "0").replace(",", "").strip()
                deal_amount = int(deal_amount_str)
                exclu_use_ar = round(float(item.findtext("excluUseAr") or 0), 2)
                floor_str = (item.findtext("floor") or "0").strip()
                floor = int(floor_str) if floor_str and floor_str != "-" else 0
                
                key = (apt_name, deal_date, deal_amount, exclu_use_ar, floor)
                if key not in existing_keys:
                    new_trades.append((apt_name, lawd, deal_date, deal_amount, exclu_use_ar, floor))
                    existing_keys.add(key)
        except Exception as e:
            print(f"⚠️ {gu_name} {ym} 호출 오류: {e}")

print(f"✨ 신규 정상 거래 발견: 총 {len(new_trades):,}건")

# 3. 신규 거래 적재
if new_trades:
    cur.executemany("""
        INSERT INTO apt_trades (apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor)
        VALUES (?, ?, ?, ?, ?, ?)
    """, new_trades)
    conn.commit()
    print("✅ DB 신규 실거래 삽입 완료!")

# 4. 연도별 랭킹 요약 캐시 재생성
print("📊 [3/4] 2010~2026 랭킹 요약 캐시 재계산 중...")
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
cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_name ON apt_trades(apt_name);")
conn.commit()

# 5. 공간 압축
print("🧹 [4/4] VACUUM 압축 실행 중...")
cur.execute("VACUUM;")
conn.close()

size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
print(f"\n🎉 모든 업데이트 완료! 최종 DB 용량: {size_mb:.2f} MB")
