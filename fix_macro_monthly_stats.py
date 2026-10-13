import os
import sqlite3
import pandas as pd

MASTER_DB = "apt_data_render_master.db"
MACRO_DB = "macro_insight.db"

def fix_macro_stats():
    if not os.path.exists(MASTER_DB):
        print(f"❌ 마스터 데이터베이스({MASTER_DB})를 찾을 수 없습니다.")
        return
    if not os.path.exists(MACRO_DB):
        print(f"❌ 매크로 데이터베이스({MACRO_DB})를 찾을 수 없습니다.")
        return

    print("=== [1] 데이터베이스 스키마 및 원천 데이터 점검 ===")
    conn_master = sqlite3.connect(MASTER_DB)
    cur_m = conn_master.cursor()

    # apt_trades 테이블 컬럼 확인
    cur_m.execute("PRAGMA table_info(apt_trades)")
    cols = [r[1] for r in cur_m.fetchall()]
    print(f"-> apt_trades 컬럼 목록: {cols}")

    lawd_col = next((c for c in ['lawd_cd', 'lawd_5', 'sgg_cd', 'bjd_code'] if c in cols), None)

    # 1. 대구 거래 데이터 추출 조건 설정
    # (법정동 코드가 있으면 27% 사용, 없으면 단지 메타와 조인 또는 대구 전체 추출)
    where_clause = ""
    if lawd_col:
        where_clause = f"WHERE ({lawd_col} LIKE '27%' OR {lawd_col} IN ('27110', '27140', '27170', '27200', '27230', '27260', '27290', '27710'))"

    query = f"""
        SELECT 
            deal_date,
            deal_amount,
            exclu_use_ar
        FROM apt_trades
        {where_clause}
    """
    print(f"-> 대구 원천 거래 데이터 로딩 중...")
    df = pd.read_sql_query(query, conn_master)
    conn_master.close()

    if df.empty:
        print("❌ apt_trades에서 거래 데이터를 가져오지 못했습니다.")
        return

    print(f"✔ 총 {len(df):,}건의 거래 데이터를 성공적으로 읽었습니다.")

    # 2. 날짜 및 평당가 연산 (누적 X, 순수 당월 거래 기준)
    df['deal_date'] = df['deal_date'].astype(str)
    # YYYY-MM-DD -> YYYYMM 형식 변환
    df['deal_ym'] = df['deal_date'].str.slice(0, 4) + df['deal_date'].str.slice(5, 7)
    df['pyeong'] = df['exclu_use_ar'] / 3.30578

    print("=== [2] 평형별 순수 당월 평균가 재집계 (84 / 59 / ALL) ===")
    records = []

    # (1) 국민평형 (84㎡: 83.0 ~ 85.99)
    df_84 = df[(df['exclu_use_ar'] >= 83.0) & (df['exclu_use_ar'] <= 85.99)]
    grp_84 = df_84.groupby('deal_ym').agg(
        total_amount=('deal_amount', 'sum'),
        total_pyeong=('pyeong', 'sum'),
        trade_count=('deal_amount', 'count')
    ).reset_index()
    for _, r in grp_84.iterrows():
        avg_p = round(r['total_amount'] / r['total_pyeong'], 1)
        records.append(('대구광역시', str(r['deal_ym']), '84', avg_p, int(r['trade_count'])))

    # (2) 소형 (59㎡: 58.0 ~ 60.99)
    df_59 = df[(df['exclu_use_ar'] >= 58.0) & (df['exclu_use_ar'] <= 60.99)]
    grp_59 = df_59.groupby('deal_ym').agg(
        total_amount=('deal_amount', 'sum'),
        total_pyeong=('pyeong', 'sum'),
        trade_count=('deal_amount', 'count')
    ).reset_index()
    for _, r in grp_59.iterrows():
        avg_p = round(r['total_amount'] / r['total_pyeong'], 1)
        records.append(('대구광역시', str(r['deal_ym']), '59', avg_p, int(r['trade_count'])))

    # (3) 전체 평균 (ALL)
    grp_all = df.groupby('deal_ym').agg(
        total_amount=('deal_amount', 'sum'),
        total_pyeong=('pyeong', 'sum'),
        trade_count=('deal_amount', 'count')
    ).reset_index()
    for _, r in grp_all.iterrows():
        avg_p = round(r['total_amount'] / r['total_pyeong'], 1)
        records.append(('대구광역시', str(r['deal_ym']), 'ALL', avg_p, int(r['trade_count'])))

    print(f"✔ 재집계 완료: 총 {len(records):,}개 월별 지표 데이터 생성됨")

    # 3. macro_insight.db의 macro_monthly_stats 테이블에 반영
    print("=== [3] macro_insight.db 데이터 덮어쓰기 ===")
    conn_macro = sqlite3.connect(MACRO_DB)
    cur_macro = conn_macro.cursor()

    # 기존 잘못된 대구 데이터 삭제
    cur_macro.execute("DELETE FROM macro_monthly_stats WHERE symbol = '대구광역시'")
    print(f"-> 기존 대구광역시 왜곡 데이터 삭제 완료")

    # 정상 집계 데이터 일괄 삽입
    cur_macro.executemany("""
        INSERT INTO macro_monthly_stats (symbol, deal_ym, area_cat, avg_price, trade_count)
        VALUES (?, ?, ?, ?, ?)
    """, records)
    conn_macro.commit()

    # 4. 검증: 대구 84㎡ 주요 분기점 가격 추이 확인
    print("\n=== [4] 대구 국평(84) 주요 연도별 실제 평균가 검증 ===")
    cur_macro.execute("""
        SELECT deal_ym, avg_price, trade_count
        FROM macro_monthly_stats
        WHERE symbol = '대구광역시' AND area_cat = '84' AND deal_ym IN ('201512', '201912', '202105', '202110', '202212', '202312', '202412')
        ORDER BY deal_ym ASC
    """)
    rows = cur_macro.fetchall()
    for r in rows:
        ym = f"{r[0][:4]}년 {r[0][4:]}월"
        print(f"  {ym}: 평당 {r[1]:,.1f} 만원/평 (월 거래량 {r[2]}건)")

    conn_macro.close()
    print("\n🎉 macro_insight.db 교체 완료! 브라우저를 새로고침하시면 정상적인 하락 사이클 차트가 표시됩니다.")

if __name__ == "__main__":
    fix_macro_stats()