import sqlite3
import json
import urllib.request
import urllib.parse

DB_FILE = "apt_data_render_master.db"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="
RONE_KEY = "7e913398413e4c63bd415700acb2dfda"

def test_rone():
    print("=== 1. R-ONE 통계 API 점검 ===")
    # R-ONE 통계목록 혹은 테이블 데이터 조회 테스트
    # 공식 주소: https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do (통계목록)
    #            https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do (통계데이터)
    url = f"https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do?KEY={RONE_KEY}&Type=json&pIndex=1&pSize=10"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
            print("R-ONE 원본 응답 앞부분:", raw[:250])
            data = json.loads(raw)
            print("✔ R-ONE 연결 성공!")
            return True
    except Exception as e:
        print("❌ R-ONE 테스트 에러:", e)
        return False

def test_kosis():
    print("\n=== 2. KOSIS 인허가 통계 파라미터 점검 ===")
    # 국토교통부 시도별 주택건설인허가실적 (DT_MLTM_666 또는 DT_MLTM_2082)
    # objL1, itmId를 1단계 포괄로 호출
    url = f"https://kosis.kr/openapi/statisticsData.do?method=getList&apiKey={KOSIS_KEY}&format=json&jsonVD=Y&orgId=116&tblId=DT_MLTM_666&prdSe=Y&startPrdDe=2020&endPrdDe=2025"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
            print("KOSIS 응답 앞부분:", raw[:250])
            data = json.loads(raw)
            if isinstance(data, list):
                print(f"✔ KOSIS 연결 및 {len(data)}건 수신 성공!")
                return data
            else:
                print("KOSIS 메시지:", data)
    except Exception as e:
        print("❌ KOSIS 테스트 에러:", e)
    return None

if __name__ == "__main__":
    test_rone()
    test_kosis()
