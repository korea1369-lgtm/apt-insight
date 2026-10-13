import json
import urllib.request

KOSIS_KEY = "YWJkOGI3ZGFmNzFiNzQwYjQ2N2E0ZDQ5MTkxMjgxNDg="

# 2024년 1월 딱 1개월치만 샘플로 호출하여 분류 체계 확인
url = (
    "https://kosis.kr/openapi/Param/statisticsParameterData.do?"
    f"method=getList&apiKey={KOSIS_KEY}"
    "&itmId=ALL&objL1=ALL&objL2=ALL&objL3=ALL&format=json&jsonVD=Y"
    "&prdSe=M&startPrdDe=202401&endPrdDe=202401"
    "&orgId=116&tblId=DT_MLTM_1946"
)

req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))

if isinstance(data, list) and len(data) > 0:
    print(f"✔ 2024년 1월 데이터 수신: {len(data)}건")
    c1_set = {r.get("C1_NM") for r in data}
    c2_set = {r.get("C2_NM") for r in data}
    c3_set = {r.get("C3_NM") for r in data}
    itm_set = {r.get("ITM_NM") for r in data}
    
    print("\n[C1_NM (지역 등)]:", list(c1_set)[:5])
    print("[C2_NM (부문/구분)]:", list(c2_set))
    print("[C3_NM (규모/세부)]:", list(c3_set))
    print("[ITM_NM (항목명)]:", list(itm_set))
    print("\n샘플 레코드 1건:\n", json.dumps(data[0], ensure_ascii=False, indent=2))
else:
    print("응답 메시지:", data)
