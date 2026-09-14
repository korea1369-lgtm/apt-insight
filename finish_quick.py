import sqlite3
import os

DB_PATH = "apt_data_render_master.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("⚡ SQLite 엔진 고속 모드 가동 중...")
cur.execute("PRAGMA synchronous = OFF;")
cur.execute("PRAGMA journal_mode = MEMORY;")

# 1. 1단계: 수성범어W 등 핵심 이상치 즉시 삭제
print("🧹 [1/3] 수성범어W 8.66억 취소 거래 확정 삭제 중...")
cur.execute("""
    DELETE FROM apt_trades 
    WHERE (apt_name LIKE '%수성범어W%' OR apt_name LIKE '%범어W%') 
      AND deal_amount >= 86000 AND deal_amount <= 87000
      AND deal_date LIKE '2025-12%';
""")
deleted_w = cur.rowcount
conn.commit()
print(f"   -> 수성범어W 취소 거래 {deleted_w}건 제거 완료!")

# 2. 2단계: 랭킹 요약 캐시 재생성
print("📊 [2/3] 2010~2026 연도별 랭킹 요약 캐시 초고속 재계산 중...")
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

# 3. 3단계: 압축
print("🧹 [3/3] 최종 최적 압축(VACUUM) 진행 중...")
cur.execute("VACUUM;")
conn.close()

size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
print(f"\n🎉 모든 작업 완료! 최종 DB 용량: {size_mb:.2f} MB")
