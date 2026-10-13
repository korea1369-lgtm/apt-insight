import json
import urllib.request

RONE_KEY = "7e913398413e4c63bd415700acb2dfda"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="

# 1. R-ONE 데이터 응답 구조 점검
print("=== 1. R-ONE 데이터 응답 점검 ===")
url_rone = f"https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?KEY={RONE_KEY}&Type=json&STATBL_ID=A_2024_00072&pIndex=1&pSize=5"
try:
    req = urllib.request.Request(url_rone, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = resp.read().decode("utf-8")
        print("R-ONE 원본 응답:\n", res[:500])
except Exception as e:
    print("R-ONE 에러:", e)

# 2. KOSIS 월간 인허가 통계표 점검
print("\n=== 2. KOSIS 월간 인허가 통계표 점검 ===")
url_kosis = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={KOSIS_KEY}&itmId=ALL&objL1=ALL&format=json&jsonVD=Y&prdSe=M&startPrdDe=202401&endPrdDe=202405&orgId=116&tblId=DT_MLTM_2082"
try:
    req = urllib.request.Request(url_kosis, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = resp.read().decode("utf-8")
        print("KOSIS 원본 응답:\n", res[:500])
except Exception as e:
    print("KOSIS 에러:", e)
