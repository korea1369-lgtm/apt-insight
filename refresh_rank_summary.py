import os
import sqlite3
import pandas as pd
import numpy as np

DB_FILE = os.path.join(os.path.dirname(__file__), "apt_data_render_master.db")

def refresh_rank_summary(target_year=2026):
    conn = sqlite3.connect(DB_FILE)
    print(f"{target_year}년도 랭킹 통계 데이터(국평 전용 분산도 주입) 재집계 시작...")
    
    query = """
        SELECT apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor
        FROM apt_trades
        WHERE strftime('%Y', deal_date) = ?
    """
    df = pd.read_sql_query(query, conn, params=[str(target_year)])
    if df.empty:
        print("집계할 데이터가 없습니다.")
        conn.close()
        return

    df['lawd_5'] = df['lawd_cd'].str[:5]
    df['pyeong'] = df['deal_amount'] / (df['exclu_use_ar'] / 3.30578)

    summary_rows = []
    grouped = df.groupby(['apt_name', 'lawd_5'])

    for (apt_name, lawd_5), g in grouped:
        total_cnt = len(g)
        max_idx = g['deal_amount'].idxmax()
        max_row = g.loc[max_idx]
        
        max_price = round(max_row['deal_amount'] / 10000.0, 3)
        avg_price = round((g['deal_amount'].mean()) / 10000.0, 3)
        avg_pyeong = round(g['pyeong'].mean(), 1)
        max_pyeong = round(g['pyeong'].max(), 1)
        
        # 84 평형 (83~85.99)
        g_84 = g[(g['exclu_use_ar'] >= 83.0) & (g['exclu_use_ar'] <= 85.99)]
        t_cnt_84 = len(g_84)
        max_84 = round(g_84['deal_amount'].max() / 10000.0, 3) if t_cnt_84 > 0 else 0
        avg_84 = round(g_84['deal_amount'].mean() / 10000.0, 3) if t_cnt_84 > 0 else 0

        # 59 평형 (58~60.99)
        g_59 = g[(g['exclu_use_ar'] >= 58.0) & (g['exclu_use_ar'] <= 60.99)]
        t_cnt_59 = len(g_59)
        max_59 = round(g_59['deal_amount'].max() / 10000.0, 3) if t_cnt_59 > 0 else 0
        avg_59 = round(g_59['deal_amount'].mean() / 10000.0, 3) if t_cnt_59 > 0 else 0

        # [핵심] 84 거래가 2건 이상이면 국평(84) 거래들만의 실거래가 CV 산출
        # 84 거래가 부족하면 면적 왜곡이 배제된 전체 평당가 CV 산출
        if t_cnt_84 >= 2:
            m84 = g_84['deal_amount'].mean()
            s84 = g_84['deal_amount'].std()
            cv = round((s84 / m84) * 100.0, 2) if (pd.notnull(s84) and m84 > 0) else 0.0
        else:
            mpy = g['pyeong'].mean()
            spy = g['pyeong'].std()
            cv = round((spy / mpy) * 100.0, 2) if (pd.notnull(spy) and mpy > 0) else 0.0

        p_est = round(float(max_row['exclu_use_ar']) / 3.30578, 1)

        summary_rows.append((
            target_year, apt_name, lawd_5, total_cnt, t_cnt_84, t_cnt_59,
            max_price, avg_price, max_pyeong, avg_pyeong,
            max_84, avg_84, max_59, avg_59,
            max_row['deal_date'], round(float(max_row['exclu_use_ar']), 2),
            p_est, int(max_row['floor']), cv
        ))

    cur = conn.cursor()
    cur.execute("DELETE FROM apt_rank_yearly_summary WHERE deal_year = ?", (target_year,))
    cur.executemany("""
        INSERT INTO apt_rank_yearly_summary (
            deal_year, apt_name, lawd_5, total_trade_cnt, trade_cnt_84, trade_cnt_59,
            max_price, avg_price, max_pyeong, avg_pyeong,
            max_84_price, avg_84_price, max_59_price, avg_59_price,
            max_p_date, max_p_area, max_p_pyeong_est, max_p_floor, dispersion_cv
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, summary_rows)

    conn.commit()
    conn.close()
    print(f"\n[성공] {target_year}년도 랭킹 요약 데이터 {len(summary_rows)}건 정상 반영 완료!")

if __name__ == "__main__":
    refresh_rank_summary(2026)
