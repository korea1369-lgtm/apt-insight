import os
import sys
import sqlite3
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

SERVICE_KEY = "cf3c93776dd439770d18b80d5c35a8ac14ea00bd7e5373a28f872d269514a05a"
DB_FILE = os.path.join(os.path.dirname(__file__), "apt_data_render_master.db")
LAWD_CODES = ["27110", "27140", "27170", "27200", "27230", "27260", "27290", "27710"]
API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"

def get_target_months():
    now = datetime.datetime.now()
    months = []
    for i in range(3):
        dt = now - datetime.timedelta(days=i * 28)
        months.append(dt.strftime("%Y%m"))
    return sorted(list(set(months)))

def fetch_rtms_data(lawd_cd, deal_ymd):
    url = f"{API_URL}?serviceKey={SERVICE_KEY}&pageNo=1&numOfRows=5000&LAWD_CD={lawd_cd}&DEAL_YMD={deal_ymd}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
            return ET.fromstring(xml_data)
    except Exception as e:
        print(f"[{lawd_cd}-{deal_ymd}] 통신 오류: {e}")
        return None

def update_database():
    if not os.path.exists(DB_FILE):
        print(f"DB 파일({DB_FILE})을 찾을 수 없습니다.")
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    target_months = get_target_months()
    print(f"최신 실거래 데이터 수집 대상 월: {target_months}")

    total_inserted = 0
    total_cancelled = 0

    for ym in target_months:
        for lawd_cd in LAWD_CODES:
            root = fetch_rtms_data(lawd_cd, ym)
            if root is None:
                continue

            items = root.findall(".//item")
            for item in items:
                apt_name = item.findtext("aptNm", "").strip()
                deal_year = item.findtext("dealYear", "").strip()
                deal_month = item.findtext("dealMonth", "").strip().zfill(2)
                deal_day = item.findtext("dealDay", "").strip().zfill(2)
                deal_date = f"{deal_year}-{deal_month}-{deal_day}"

                amount_str = item.findtext("dealAmount", "0").replace(",", "").strip()
                deal_amount = int(amount_str) if amount_str.isdigit() else 0

                try:
                    exclu_use_ar = float(item.findtext("excluUseAr", "0"))
                except ValueError:
                    exclu_use_ar = 0.0

                floor_str = item.findtext("floor", "0").strip()
                try:
                    floor = int(floor_str)
                except ValueError:
                    floor = 0

                deal_type = item.findtext("dealingGbn", "중개거래").strip() or "중개거래"
                estate_agent_sgg_nm = item.findtext("estateAgentSggNm", "").strip()
                c_deal_type = item.findtext("cdealType", "").strip()
                c_deal_day = item.findtext("cdealDay", "").strip()

                if c_deal_type == "O" or c_deal_day:
                    cur.execute("""
                        INSERT OR IGNORE INTO apt_cancelled_trades (apt_name, deal_date, deal_amount, exclu_use_ar, floor)
                        VALUES (?, ?, ?, ?, ?)
                    """, (apt_name, deal_date, deal_amount, exclu_use_ar, floor))
                    total_cancelled += 1
                else:
                    cur.execute("""
                        SELECT 1 FROM apt_trades 
                        WHERE apt_name = ? AND deal_date = ? AND deal_amount = ? AND exclu_use_ar = ? AND floor = ?
                    """, (apt_name, deal_date, deal_amount, exclu_use_ar, floor))
                    if not cur.fetchone():
                        cur.execute("""
                            INSERT INTO apt_trades (apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor, deal_type, estate_agent_sgg_nm)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (apt_name, lawd_cd, deal_date, deal_amount, exclu_use_ar, floor, deal_type, estate_agent_sgg_nm))
                        total_inserted += 1

            conn.commit()
            print(f"[{lawd_cd} - {ym}] 수신: {len(items)}건 처리 완료")

    cur.execute("UPDATE _db_sync_touch SET updated_at = datetime('now', 'localtime') WHERE id = 1")
    conn.commit()
    conn.close()
    print(f"\n최신화 완료! 신규 실거래 등록: {total_inserted}건 / 신규 취소 등록: {total_cancelled}건")

if __name__ == "__main__":
    update_database()
