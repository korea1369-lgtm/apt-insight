import json
import urllib.request
import urllib.parse

RONE_KEY = "7e913398413e4c63bd415700acb2dfda"
KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="

# 1. KOSIS objL1=ALL & objL2=ALL 보완 호출 (월간 인허가)
print("=== 1. KOSIS 월간 인허가 호출 테스트 ===")
kosis_url = (
    "https://kosis.kr/openapi/Param/statisticsParameterData.do?"
    f"method=getList&apiKey={KOSIS_KEY}"
    "&itmId=ALL&objL1=ALL&objL2=ALL&format=json&jsonVD=Y"
    "&prdSe=M&startPrdDe=202401&endPrdDe=202403"
    "&orgId=116&tblId=DT_MLTM_2082"
)
try:
    req = urllib.request.Request(kosis_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        if isinstance(res, list):
            print(f"✔ KOSIS 성공! 응답 레코드: {len(res)}건")
            print("  샘플:", res[0])
        else:
            print("⚠ KOSIS 메시지:", res)
except Exception as e:
    print("KOSIS 에러:", e)


# 2. R-ONE 필수값 보완 호출 (조사주기 및 조회기간 추가)
print("\n=== 2. R-ONE 전세가율 호출 테스트 ===")
# R-ONE API 필수 파라미터 조합 (DTACYCLE_CD=MM, WRT_TIME 설정)
rone_url = (
    "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?"
    f"KEY={RONE_KEY}&Type=json&STATBL_ID=A_2024_00072"
    "&DTACYCLE_CD=MM&pIndex=1&pSize=5"
)
try:
    req = urllib.request.Request(rone_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("R-ONE 응답 결과:\n", json.dumps(res, ensure_ascii=False)[:350])
except Exception as e:
    print("R-ONE 에러:", e)
