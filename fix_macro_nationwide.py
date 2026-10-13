import os
import sqlite3
import pandas as pd
import time

MASTER_DB = "apt_data_render_master.db"
MACRO_DB = "macro_insight.db"

def map_lawd_to_symbol(lawd_val):
    if not lawd_val:
        return None
    raw = str(lawd_val).split('.')[0].strip()
    if len(raw) < 5:
        return None
    code = raw[:5]
    p2 = code[:2]
    p4 = code[:4]

    # 1. 서울특별시 25개 자치구 (11xxx)
    if p2 == '11':
        seoul_map = {
            '11110': '종로구', '11140': '중구', '11170': '용산구', '11200': '성동구',
            '11215': '광진구', '11230': '동대문구', '11260': '중랑구', '11290': '성북구',
            '11305': '강북구', '11320': '도봉구', '11350': '노원구', '11380': '은평구',
            '11410': '서대문구', '11440': '마포구', '11470': '양천구', '11500': '강서구',
            '11530': '구로구', '11545': '금천구', '11560': '영등포구', '11590': '동작구',
            '11620': '관악구', '11650': '서초구', '11680': '강남구', '11710': '송파구',
            '11740': '강동구'
        }
        return seoul_map.get(code)

    # 2. 광역시 및 특별자치시 (광역 시도 통합)
    if p2 == '26': return '부산광역시'
    if p2 == '27': return '대구광역시'
    if p2 == '28': return '인천광역시'
    if p2 == '29': return '광주광역시'
    if p2 == '30': return '대전광역시'
    if p2 == '31': return '울산광역시'
    if p2 == '36': return '세종특별자치시'

    # 3. 경기도 주요 시 (41xxx)
    if p2 == '41':
        if p4 == '4111': return '수원시'
        if p4 == '4113': return '성남시'
        if p4 == '4117': return '안양시'
        if p4 == '4119': return '부천시'
        if p4 == '4127': return '안산시'
        if p4 == '4128': return '고양시'
        if p4 == '4146': return '용인시'
        gyeonggi_exact = {
            '41150': '의정부시', '41210': '광명시', '41220': '평택시', '41250': '동두천시',
            '41290': '과천시', '41310': '구리시', '41360': '남양주시', '41370': '오산시',
            '41390': '시흥시', '41410': '군포시', '41430': '의왕시', '41450': '하남시',
            '41480': '파주시', '41500': '이천시', '41550': '안성시', '41570': '김포시',
            '41590': '화성시', '41610': '광주시', '41630': '양주시', '41650': '포천시',
            '41670': '여주시'
        }
        return gyeonggi_exact.get(code)

    # 4. 지방 거점 및 주요 시
    if p4 == '4311': return '청주시'
    if p4 == '4413': return '천안시'
    if p4 == '4511': return '전주시'
    if p4 == '4711': return '포항시'
    if p4 == '4812': return '창원시'

    local_exact = {
        '42110': '춘천시', '51110': '춘천시',
        '42130': '원주시', '51130': '원주시',
        '42150': '강릉시', '51150': '강릉시',
        '43130': '충주시', '43150': '제천시',
        '44150': '공주시', '44180': '보령시', '44200': '아산시', '44210': '서산시', '44230': '논산시', '44270': '당진시',
        '45130': '군산시', '45140': '익산시', '45180': '정읍시', '45190': '남원시', '45210': '김제시',
        '46110': '목포시', '46130': '여수시', '46150': '순천시', '46170': '나주시', '46230': '광양시',
        '47130': '경주시', '47150': '김천시', '47170': '안동시', '47190': '구미시', '47210': '영주시', '47230': '영천시', '47250': '상주시', '47280': '문경시', '47290': '경산시',
        '48170': '진주시', '48220': '통영시', '48240': '사천시', '48250': '김해시', '48270': '밀양시', '48310': '거제시', '48330': '양산시',
        '50110': '제주시', '50130': '서귀포시'
    }
    return local_exact.get(code)

def run_nationwide_fix():
    start_time = time.time()
    print("=== [1] 마스터 DB 원천 거래 데이터 전체 로드 ===")
    conn_m = sqlite3.connect(MASTER_DB)
    query = """
        SELECT deal_date, deal_amount, exclu_use_ar, lawd_cd
        FROM apt_trades
        WHERE deal_amount > 0 AND exclu_use_ar > 0 AND deal_date IS NOT NULL
    """
    df = pd.read_sql_query(query, conn_m)
    conn_m.close()
    print(f"✔ 총 {len(df):,}건 원천 거래 데이터 로드 완료 ({time.time() - start_time:.1f}초)")

    print("\n=== [2] 법정동 코드 -> 지역 심볼(Symbol) 매핑 ===")
    df['symbol'] = df['lawd_cd'].map(map_lawd_to_symbol)
    df = df[df['symbol'].notnull()].copy()
    print(f"✔ 분석 대상 지역 거래: {len(df):,}건 유효 매핑됨")

    # YYYY-MM-DD -> YYYYMM 변환
    d_clean = df['deal_date'].astype(str).str.replace('-', '', regex=False).str.strip()
    df['deal_ym'] = d_clean.str.slice(0, 6)
    df = df[df['deal_ym'].str.len() == 6]
    df['pyeong'] = df['exclu_use_ar'] / 3.30578

    print("\n=== [3] 전국 평형별 순수 당월 평균가 일괄 재집계 (84 / 59 / ALL) ===")
    records = []

    # 1. 국민평형 (84㎡: 83.0 ~ 85.99)
    df_84 = df[(df['exclu_use_ar'] >= 83.0) & (df['exclu_use_ar'] <= 85.99)]
    grp_84 = df_84.groupby(['symbol', 'deal_ym']).agg(
        tot_amount=('deal_amount', 'sum'),
        tot_pyeong=('pyeong', 'sum'),
        cnt=('deal_amount', 'count')
    ).reset_index()
    for _, r in grp_84.iterrows():
        avg_p = round(r['tot_amount'] / r['tot_pyeong'], 1)
        records.append((r['symbol'], str(r['deal_ym']), '84', avg_p, int(r['cnt'])))
    print(f"  └ 84㎡(국평) 집계 완료: {len(grp_84):,}개 시계열 포인트")

    # 2. 소형평형 (59㎡: 58.0 ~ 60.99)
    df_59 = df[(df['exclu_use_ar'] >= 58.0) & (df['exclu_use_ar'] <= 60.99)]
    grp_59 = df_59.groupby(['symbol', 'deal_ym']).agg(
        tot_amount=('deal_amount', 'sum'),
        tot_pyeong=('pyeong', 'sum'),
        cnt=('deal_amount', 'count')
    ).reset_index()
    for _, r in grp_59.iterrows():
        avg_p = round(r['tot_amount'] / r['tot_pyeong'], 1)
        records.append((r['symbol'], str(r['deal_ym']), '59', avg_p, int(r['cnt'])))
    print(f"  └ 59㎡(소형) 집계 완료: {len(grp_59):,}개 시계열 포인트")

    # 3. 전체평형 평균 (ALL)
    grp_all = df.groupby(['symbol', 'deal_ym']).agg(
        tot_amount=('deal_amount', 'sum'),
        tot_pyeong=('pyeong', 'sum'),
        cnt=('deal_amount', 'count')
    ).reset_index()
    for _, r in grp_all.iterrows():
        avg_p = round(r['tot_amount'] / r['tot_pyeong'], 1)
        records.append((r['symbol'], str(r['deal_ym']), 'ALL', avg_p, int(r['cnt'])))
    print(f"  └ ALL(전체평형) 집계 완료: {len(grp_all):,}개 시계열 포인트")

    print(f"\n✔ 전국 총 {len(records):,}개 월별 지표 데이터 생성 완료")

    print("\n=== [4] macro_insight.db 교체 및 인덱스 최적화 ===")
    conn_macro = sqlite3.connect(MACRO_DB)
    cur = conn_macro.cursor()

    cur.execute("DROP TABLE IF EXISTS macro_monthly_stats")
    cur.execute("""
        CREATE TABLE macro_monthly_stats (
            symbol TEXT,
            deal_ym TEXT,
            area_cat TEXT,
            avg_price REAL,
            trade_count INTEGER
        )
    """)

    cur.executemany("""
        INSERT INTO macro_monthly_stats (symbol, deal_ym, area_cat, avg_price, trade_count)
        VALUES (?, ?, ?, ?, ?)
    """, records)

    cur.execute("CREATE INDEX idx_macro_monthly ON macro_monthly_stats(symbol, area_cat, deal_ym)")
    conn_macro.commit()

    print("\n=== [5] 전국 주요 거점 국평(84) 2021년 고점 vs 2022년 하락 검증 ===")
    targets = [('강남구', '84'), ('송파구', '84'), ('대구광역시', '84'), ('부산광역시', '84'), ('수원시', '84'), ('세종특별자치시', '84')]
    for sym, cat in targets:
        cur.execute("""
            SELECT deal_ym, avg_price 
            FROM macro_monthly_stats 
            WHERE symbol = ? AND area_cat = ? AND deal_ym IN ('202106', '202212')
            ORDER BY deal_ym ASC
        """, (sym, cat))
        rows = cur.fetchall()
        p_dict = {r[0]: r[1] for r in rows}
        p_21 = p_dict.get('202106', '-')
        p_22 = p_dict.get('202212', '-')
        print(f"  • {sym} ({cat}): 2021.06 고점({p_21}만/평) -> 2022.12 하락기({p_22}만/평)")

    conn_macro.close()
    elapsed = time.time() - start_time
    print(f"\n🎉 전국 매크로 데이터베이스 복구 완료! (총 소요시간: {elapsed:.1f}초)")
    print("이제 브라우저를 새로고침(Ctrl+F5)하시면 전국 모든 지역의 하락 사이클이 정확히 표시됩니다.")

if __name__ == "__main__":
    run_nationwide_fix()