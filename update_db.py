import requests
import xml.etree.ElementTree as ET
import sqlite3
import datetime

API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
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
            # 1. 취소 거래 필터링 (cdealType == 'O' 또는 해제일자 존재 시 제외)
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

def run_update():
    print("=" * 65)
    print("🚀 [자동 업데이트 파이프라인] 실거래 수집 및 무결성 동기화 시작")
    print("=" * 65)
    
    # 최근 3개월치(해제 신고 감안) 재수집 범위 설정
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
            
        # 해당 월 데이터 원자적 교체 (취소/중복 원천 방지)
        cur.execute("DELETE FROM apt_trades WHERE deal_date BETWEEN ? AND ?", (start_date, end_date))
        cur.executemany("""
            INSERT INTO apt_trades (apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor)
            VALUES (?, ?, ?, ?, ?, ?)
        """, all_month_trades)
        conn.commit()
    
    print("\n" + "=" * 65)
    print("📊 핵심 단지 정합성 최종 확인")
    print("=" * 65)
    for target in ["더샵디어엘로", "e편한세상범어"]:
        cur.execute("SELECT COUNT(*) FROM apt_trades WHERE apt_name LIKE ? AND deal_date >= '2026-01-01'", (f"%{target}%",))
        cnt = cur.fetchone()[0]
        print(f"▶ [{target}] 2026년 거래량: {cnt}건")
        
    conn.close()

if __name__ == "__main__":
    run_update()
