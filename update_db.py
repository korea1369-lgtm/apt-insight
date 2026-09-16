import requests
import xml.etree.ElementTree as ET
import sqlite3
import datetime

API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
SERVICE_KEY = "cf3c93776dd439770d18b80d5c35a8ac14ea00bd7e5373a28f872d269514a05a"
DB_PATH = "apt_data_render_master.db"

LAWD_CDS = {
    "중구": "27110", "동구": "27140", "서구": "27170", "남구": "27200",
    "북구": "27230", "수성구": "27260", "달서구": "27290", "달성군": "27710"
}

def fetch_and_clean_month(lawd_cd, deal_ym):
    params = {
        "serviceKey": SERVICE_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ym,
        "numOfRows": "4000",
        "pageNo": "1"
    }
    records = []
    unique_meta = set()
    
    try:
        res = requests.get(API_URL, params=params, timeout=20)
        root = ET.fromstring(res.text)
        
        for item in root.findall(".//item"):
            # 1. 취소 거래 원천 필터링
            cdeal_type = item.findtext("cdealType", "").strip().upper()
            cdeal_day = item.findtext("cdealDay", "").strip()
            if cdeal_type == "O" or len(cdeal_day) >= 5:
                continue
                
            apt_name = item.findtext("aptNm", "").strip()
            year = item.findtext("dealYear", "").strip()
            month = item.findtext("dealMonth", "").strip().zfill(2)
            day = item.findtext("dealDay", "").strip().zfill(2)
            deal_date = f"{year}-{month}-{day}"
            
            amt_str = item.findtext("dealAmount", "0").replace(",", "").strip()
            deal_amount = int(amt_str) if amt_str.isdigit() else 0
            
            area_str = item.findtext("excluUseAr", "0").strip()
            exclu_use_ar = float(area_str) if area_str else 0.0
            
            flr_str = item.findtext("floor", "0").strip()
            floor = int(flr_str) if flr_str.lstrip('-').isdigit() else 0
            
            # 2. 메타데이터 기반 순수 API 중복 전송분 디듀프
            rgst_date = item.findtext("rgstDate", "").strip()
            agent_sgg = item.findtext("estateAgentSggNm", "").strip()
        raw_deal_type = item.findtext("dealingGbn", "").strip()
        # 중개사 소재지가 없거나 공백이면 100% 법적 직거래
        if raw_deal_type == "직거래" or not agent_sgg or agent_sgg in ["-", "없음"]:
            deal_type = "직거래"
        else:
            deal_type = "중개거래" 
            buyer_gbn = item.findtext("buyerGbn", "").strip()
            sler_gbn = item.findtext("slerGbn", "").strip()
            jibun = item.findtext("jibun", "").strip()
            
            meta_key = (apt_name, jibun, deal_date, deal_amount, exclu_use_ar, floor, rgst_date, agent_sgg, buyer_gbn, sler_gbn)
            if meta_key in unique_meta:
                continue
            unique_meta.add(meta_key)
            
            records.append((apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor))
    except Exception as e:
        print(f"⚠️ 에러 발생 ({lawd_cd}, {deal_ym}): {e}")
        
    return records

def refresh_rank_summary(conn):
    cur = conn.cursor()
    print("🔄 웹 랭킹 요약 테이블(apt_rank_yearly_summary) 2026년 자동 동기화 중...")
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
            2026 AS deal_year,
            apt_name,
            SUBSTR(lawd_cd, 1, 5) AS lawd_5,
            COUNT(*) AS total_trade_cnt,
            COUNT(CASE WHEN exclu_use_ar BETWEEN 83 AND 86 THEN 1 END) AS trade_cnt_84,
            COUNT(CASE WHEN exclu_use_ar BETWEEN 58 AND 61 THEN 1 END) AS trade_cnt_59,
            MAX(deal_amount) AS max_price,
            ROUND(AVG(deal_amount), 1) AS avg_price,
            ROUND(MAX(deal_amount / (exclu_use_ar / 3.30578)), 1) AS max_pyeong,
            ROUND(AVG(deal_amount / (exclu_use_ar / 3.30578)), 1) AS avg_pyeong,
            MAX(CASE WHEN exclu_use_ar BETWEEN 83 AND 86 THEN deal_amount END) AS max_84_price,
            ROUND(AVG(CASE WHEN exclu_use_ar BETWEEN 83 AND 86 THEN deal_amount END), 1) AS avg_84_price,
            MAX(CASE WHEN exclu_use_ar BETWEEN 58 AND 61 THEN deal_amount END) AS max_59_price,
            ROUND(AVG(CASE WHEN exclu_use_ar BETWEEN 58 AND 61 THEN deal_amount END), 1) AS avg_59_price,
            (SELECT deal_date FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_date,
            (SELECT exclu_use_ar FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_area,
            (SELECT ROUND(exclu_use_ar / 3.30578, 1) FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_pyeong_est,
            (SELECT floor FROM apt_trades t2 WHERE t2.apt_name = t1.apt_name AND t2.deal_date >= '2026-01-01' ORDER BY deal_amount DESC, deal_date DESC LIMIT 1) AS max_p_floor,
            0.0 AS dispersion_cv
        FROM apt_trades t1
        WHERE deal_date >= '2026-01-01'
        GROUP BY SUBSTR(lawd_cd, 1, 5), apt_name
    """)
    conn.commit()

def run_update():
    print("=" * 65)
    print("🚀 [자동 업데이트 파이프라인] 실거래 수집 및 무결성 동기화 시작")
    print("=" * 65)
    
    now = datetime.datetime.now()
    target_months = []
    for i in range(3):
        dt = now - datetime.timedelta(days=i*30)
        target_months.append(dt.strftime("%Y%m"))
    target_months = sorted(list(set(target_months)))
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    for ym in target_months:
        print(f"📡 {ym} 데이터 무결성 검증 및 갱신 중...")
        start_date = f"{ym[:4]}-{ym[4:]}-01"
        end_date = f"{ym[:4]}-{ym[4:]}-31"
        
        all_month_trades = []
        for gu_name, lawd_cd in LAWD_CDS.items():
            all_month_trades.extend(fetch_and_clean_month(lawd_cd, ym))
            
        cur.execute("DELETE FROM apt_trades WHERE deal_date BETWEEN ? AND ?", (start_date, end_date))
        cur.executemany("""
            INSERT INTO apt_trades (apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor)
            VALUES (?, ?, ?, ?, ?, ?)
        """, all_month_trades)
        conn.commit()
    
    # 랭킹 통계 테이블 자동 재계산
    refresh_rank_summary(conn)
    
    print("\n" + "=" * 65)
    print("📊 핵심 단지 정합성 최종 확인")
    print("=" * 65)
    for target in ["더샵디어엘로", "e편한세상범어"]:
        cur.execute("SELECT total_trade_cnt FROM apt_rank_yearly_summary WHERE deal_year = 2026 AND apt_name LIKE ?", (f"%{target}%",))
        cnt = cur.fetchone()[0]
        print(f"▶ [{target}] 2026년 웹 랭킹 집계: {cnt}건")
        
    conn.close()

if __name__ == "__main__":
    run_update()
