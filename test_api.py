import urllib.request
import urllib.error

key = "cf3c93776dd439770d18b80d5c35a8ac14ea00bd7e5373a28f872d269514a05a"
candidates = [
    # 1. 국토교통부 아파트매매 실거래자료 (신규 표준)
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    # 2. 공공데이터포털 개편 주소
    "https://apis.data.go.kr/1613000/AptTradeService/getAptTradeDev",
    "https://apis.data.go.kr/1613000/AptTradeService/getAptTrade",
    # 3. HTTP 프로토콜
    "http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
]

for u in candidates:
    full = f"{u}?serviceKey={key}&pageNo=1&numOfRows=1&LAWD_CD=27260&DEAL_YMD=202401"
    req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            if "<items>" in body or "<totalCount>" in body:
                print(f"\n[★ 성공 엔드포인트 발견!] -> {u}\n")
                break
            else:
                print(f"[응답 메시지] {u.split('/')[-2]+'/'+u.split('/')[-1]}")
                print("   ->", body.replace("\n", " ").strip()[:150])
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore").replace("\n", " ").strip()
        print(f"[HTTP {e.code}] {u.split('/')[-2]+'/'+u.split('/')[-1]}")
        print("   ->", err_msg[:150])
    except Exception as e:
        print(f"[기타 에러] {u.split('/')[-2]+'/'+u.split('/')[-1]} -> {e}")
