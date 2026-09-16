import sqlite3
import requests
import xml.etree.ElementTree as ET
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PATH = "apt_data_render_master.db"
SERVICE_KEY = "cf3c93776dd439770d18b80d5c35a8ac14ea00bd7e5373a28f872d269514a05a"
API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

LAWD_CDS = ["27110", "27140", "27170", "27200", "27230", "27260", "27290", "27710", "27720"]
TARGET_YM = "202609"

print("=" * 65)
print(f"🚀 {TARGET_YM} 대구 실거래가 최신 데이터 수집 및 동기화")
print("=" * 65)

headers = {"User-Agent": "Mozilla/5.0"}
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

total_new_inserted = 0

for lawd in LAWD_CDS:
    params = {
        "serviceKey": requests.utils.unquote(SERVICE_KEY),
        "LAWD_CD": lawd,
        "DEAL_YMD": TARGET_YM,
        "pageNo": "1",
        "numOfRows": "3000"
    }
    try:
        res = requests.get(API_URL, params=params, headers=headers, timeout=20, verify=False)
        if res.status_code != 200:
            print(f"❌ 지역코드 {lawd} API 응답 실패 ({res.status_code})")
            continue

        root = ET.fromstring(res.content)
        
        # API 오류 태그 점검
        err_msg = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg")
        if err_msg:
            print(f"⚠️ {lawd} API 응답 오류: {err_msg}")
            continue

        items = root.findall(".//item")
        inserted_cnt = 0
        
        for item in items:
            # 해제/취소된 거래 필터링
            c_deal = item.findtext("cdealType", "").strip()
            c_day = item.findtext("cdealDay", "").strip()
            if c_deal == "O" or c_day:
                continue

            # 태그명 추출 (소대문자 호환 대응)
            apt_name = (item.findtext("aptNm") or item.findtext("aptName") or item.findtext("아파트") or "").strip()
            deal_year = (item.findtext("dealYear") or item.findtext("년") or "").strip()
            deal_month = str(int((item.findtext("dealMonth") or item.findtext("월") or "0"))).zfill(2)
            deal_day = str(int((item.findtext("dealDay") or item.findtext("일") or "0"))).zfill(2)
            deal_date = f"{deal_year}-{deal_month}-{deal_day}"

            amount_raw = (item.findtext("dealAmount") or item.findtext("거래금액") or "0").replace(",", "").strip()
            deal_amount = int(amount_raw)
            exclu_use_ar = float((item.findtext("excluUseAr") or item.findtext("전용면적") or "0").strip())
            floor = (item.findtext("floor") or item.findtext("층") or "").strip()

            if not apt_name or deal_amount == 0:
                continue

            # 중복 체크
            cur.execute("""
                SELECT 1 FROM apt_trades 
                WHERE apt_name = ? AND deal_date = ? AND deal_amount = ? AND exclu_use_ar = ? AND floor = ?
            """, (apt_name, deal_date, deal_amount, exclu_use_ar, floor))

            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO apt_trades (apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (apt_name, lawd, deal_date, deal_amount, exclu_use_ar, floor))
                inserted_cnt += 1

        total_new_inserted += inserted_cnt
        print(f" - 지역 {lawd}: 응답 {len(items)}건 | 신규 추가 {inserted_cnt}건")

    except Exception as e:
        print(f"⚠️ {lawd} 처리 중 예외 발생: {e}")

conn.commit()
print(f"\n✅ 원천 테이블(apt_trades) 신규 거래 총 {total_new_inserted}건 반영 완료")

if total_new_inserted > 0:
    print("\n🔄 웹 랭킹 요약 테이블(apt_rank_yearly_summary) 2026년 동기화 중...")
    cur.execute("DELETE FROM apt_rank_yearly_summary WHERE deal_year = 2026")
    cur.execute("""
    INSERT INTO apt_rank_yearly_summary (
        deal_year, apt_name, lawd_5, total_trade_cnt,
        trade_cnt_84, trade_cnt_59, max_price, avg_price,
        max_pyeong, avg_pyeong, max_84_price, avg_84_price,
        max_59_price, avg_59_price, max_p_date, max_p_area,
        max_p_pyeong_est, max_p_floor, dispersion_cv
    )
    SELECT 
        2026,
        t1.apt_name,
        SUBSTR(t1.lawd_cd, 1, 5) AS lawd_5,
        COUNT(*) AS total_trade_cnt,
        SUM(CASE WHEN t1.exclu_use_ar BETWEEN 83 AND 86 THEN 1 ELSE 0 END) AS trade_cnt_84,
        SUM(CASE WHEN t1.exclu_use_ar BETWEEN 58 AND 61 THEN 1 ELSE 0 END) AS trade_cnt_59,
        ROUND(MAX(t1.deal_amount / 10000.0), 3) AS max_price,
        ROUND(AVG(t1.deal_amount / 10000.0), 3) AS avg_price,
        ROUND(MAX(t1.deal_amount / (t1.exclu_use_ar / 3.30578)), 1) AS max_pyeong,
        ROUND(AVG(t1.deal_amount / (t1.exclu_use_ar / 3.30578)), 1) AS avg_pyeong,
        ROUND(MAX(CASE WHEN t1.exclu_use_ar BETWEEN 83 AND 86 THEN t1.deal_amount / 10000.0 END), 3) AS max_84_price,
        ROUND(AVG(CASE WHEN t1.exclu_use_ar BETWEEN 83 AND 86 THEN t1.deal_amount / 10000.0 END), 3) AS avg_84_price,
        ROUND(MAX(CASE WHEN t1.exclu_use_ar BETWEEN 58 AND 61 THEN t1.deal_amount / 10000.0 END), 3) AS max_59_price,
        ROUND(AVG(CASE WHEN t1.exclu_use_ar BETWEEN 58 AND 61 THEN t1.deal_amount / 10000.0 END), 3) AS avg_59_price,
        (SELECT deal_date FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_date,
        (SELECT ROUND(exclu_use_ar, 1) FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_area,
        (SELECT ROUND((exclu_use_ar / 3.30578) * 1.3, 1) FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_pyeong_est,
        (SELECT floor FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_floor,
        0.0
    FROM apt_trades t1
    WHERE t1.deal_date >= '2026-01-01'
    GROUP BY t1.apt_name, SUBSTR(t1.lawd_cd, 1, 5)
    """)
    conn.commit()
    print("🎉 랭킹 요약 통계 동기화 완료!")
else:
    print("ℹ️ 기존 DB에 이미 모두 반영되어 있는 최신 상태입니다.")

conn.close()
