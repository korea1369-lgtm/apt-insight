import os
import sys
import subprocess
import time
import sqlite3
import json
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def clean_region_name(raw_name):
    if not raw_name:
        return ""
    name = raw_name.strip()
    for reg in ["서울", "경기", "인천", "대구", "부산", "광주", "대전", "울산", "세종", 
                "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "전국"]:
        if name.startswith(reg):
            return reg
    return ""

def update_macro_indicators():
    """R-ONE 전세가율 및 KOSIS 주택인허가 최신 월 데이터 자동 동기화"""
    print("=" * 60)
    print("[*] [2/4] 부동산 매크로 보조지표 업데이트 (전세가율 & 인허가실적)")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS macro_regional_indicators (
            deal_ym TEXT,
            region_name TEXT,
            permit_count INTEGER,
            jeonse_ratio REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (deal_ym, region_name)
        )
    """)
    conn.commit()

    # 1. R-ONE 아파트 전세가율 최신 수집 (최근 1~2페이지 조회로 최신월 보강)
    print("  -> [1/2] 한국부동산원(R-ONE) 아파트 전세가율 최신 데이터 수신 중...")
    jeonse_records = []
    try:
        # 최근 월 데이터는 상위 페이지에 있으므로 최근 5페이지(5,000건) 집중 업데이트
        for page in range(1, 6):
            url = (
                "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?"
                f"KEY={RONE_KEY}&Type=json&STATBL_ID=A_2024_00072"
                f"&DTACYCLE_CD=MM&pIndex={page}&pSize=1000"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("SttsApiTblData", [{}, {}])[1].get("row", [])
                if not rows:
                    break
                for r in rows:
                    reg = clean_region_name(r.get("CLS_NM", ""))
                    ym_raw = str(r.get("WRTTIME_IDTFR_ID", ""))
                    val = r.get("DTA_VAL")
                    if reg and len(ym_raw) >= 6 and val is not None:
                        try:
                            rate = float(val)
                            ym = f"{ym_raw[:4]}-{ym_raw[4:6]}"
                            jeonse_records.append((ym, reg, rate))
                        except ValueError:
                            continue
        
        if jeonse_records:
            c.executemany("""
                INSERT INTO macro_regional_indicators (deal_ym, region_name, jeonse_ratio)
                VALUES (?, ?, ?)
                ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                    jeonse_ratio = excluded.jeonse_ratio,
                    updated_at = CURRENT_TIMESTAMP
            """, jeonse_records)
            conn.commit()
            print(f"     ✔ 전세가율 {len(jeonse_records):,}건 최신화 반영 완료")
    except Exception as e:
        print(f"     ⚠ 전세가율 갱신 중 건너뜀: {e}")

    # 2. KOSIS 주택건설 인허가실적 최신 수집 (올해 및 직전 연도 누계 차감)
    print("  -> [2/2] 국토교통부(KOSIS) 주택건설 인허가실적 최신 데이터 수신 중...")
    now_year = datetime.now().year
    start_prd = f"{now_year - 1}01"
    end_prd = f"{now_year}12"

    params = {
        "method": "getList",
        "apiKey": KOSIS_KEY,
        "itmId": "13103871089T1",
        "objL1": "13102871089A.0001",
        "objL2": "13102871089B.0001",
        "objL3": "ALL",
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "M",
        "startPrdDe": start_prd,
        "endPrdDe": end_prd,
        "orgId": "116",
        "tblId": "DT_MLTM_1946"
    }
    url = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
        if isinstance(data, list) and len(data) > 0 and "err" not in data[0]:
            cum_data = defaultdict(lambda: defaultdict(dict))
            for r in data:
                reg = clean_region_name(r.get("C3_NM", ""))
                ym = r.get("PRD_DE", "")
                val = r.get("DT", "")
                if reg and len(ym) == 6 and val:
                    try:
                        year = ym[:4]
                        month = int(ym[4:6])
                        cum_data[reg][year][month] = int(float(val))
                    except:
                        continue

            permit_records = []
            for reg, years in cum_data.items():
                for year, months in years.items():
                    sorted_months = sorted(months.keys())
                    prev_cum = 0
                    for m in sorted_months:
                        curr_cum = months[m]
                        monthly_val = curr_cum if m == 1 else max(0, curr_cum - prev_cum)
                        prev_cum = curr_cum
                        permit_records.append((f"{year}-{m:02d}", reg, monthly_val))

            if permit_records:
                c.executemany("""
                    INSERT INTO macro_regional_indicators (deal_ym, region_name, permit_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(deal_ym, region_name) DO UPDATE SET
                        permit_count = excluded.permit_count,
                        updated_at = CURRENT_TIMESTAMP
                """, permit_records)
                conn.commit()
                print(f"     ✔ 인허가실적 {len(permit_records):,}건 최신화 반영 완료")
        else:
            print("     ⚠ KOSIS 응답 확인:", data)
    except Exception as e:
        print(f"     ⚠ 인허가실적 갱신 중 건너뜀: {e}")

    # 혹시 모를 비정상 연도 찌꺼기 삭제
    c.execute("DELETE FROM macro_regional_indicators WHERE deal_ym NOT LIKE '%-%'")
    conn.commit()
    conn.close()
    print("-> 매크로 보조지표 동기화 완료\n")

def run_step(step_name, cmd):
    print("=" * 60)
    print(f"[*] {step_name}")
    print("=" * 60)
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"\n[오류 발생] {step_name} 단계에서 실패했습니다.")
        sys.exit(res.returncode)
    print()

def main():
    # 1. 국토부 실거래가 수집
    run_step("[1/4] 국토부 최신 실거래가 수집 (update_trades.py)", "python update_trades.py")

    # 2. 부동산 매크로 보조지표(전세가율 & 인허가실적) 최신화
    update_macro_indicators()

    # 3. 랭킹 요약 재집계
    run_step("[3/4] 아파트 랭킹 요약 집계 (refresh_rank_summary.py)", "python refresh_rank_summary.py")

    # 4. DB 가벼운 최적화 (인덱스 통계 갱신)
    print("=" * 60)
    print("[4/4] DB 인덱스 통계 갱신 및 캐시 정리")
    print("=" * 60)
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("ANALYZE;")
        conn.close()
        print("-> DB 최적화 완료")
    except Exception as e:
        print(f"-> DB 최적화 건너뜀: {e}")
    print()

    # 5. 서버 재시작
    print("=" * 60)
    print("[서버 재시작] 기존 서버 종료 후 새 캐시로 구동")
    print("=" * 60)
    os.system("taskkill /f /im python.exe > nul 2>&1")
    time.sleep(1)
    os.system("start \"TECH REALTY INSIGHT SERVER\" python main.py")

    print("\n" + "=" * 60)
    print(" [완료] 실거래가, 매크로 지표, 랭킹 업데이트가 모두 정상적으로 끝났습니다!")
    print(" 브라우저에서 Ctrl + F5를 눌러 확인해 주세요.")
    print("=" * 60)
    time.sleep(3)

if __name__ == "__main__":
    main()