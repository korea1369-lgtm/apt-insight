import urllib.request
import json
import urllib.error

SUPABASE_URL = "https://hikwjqgjollisdistbif.supabase.co"
SUPABASE_KEY = "sb_publishable_eIzC8sNZ6gBe62KixTRm1w_1dE2dNG9"

url = f"{SUPABASE_URL}/rest/v1/apt_compare_pairs?on_conflict=apt_a,apt_b"
payload = json.dumps([{
    "apt_a": "남산자이하늘채",
    "apt_b": "청라힐스자이",
    "compare_count": 1
}]).encode("utf-8")

req = urllib.request.Request(url, data=payload, method="POST", headers={
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
})

try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(f"✅ Supabase 전송 성공! 응답 코드: {resp.status}")
except urllib.error.HTTPError as e:
    print(f"❌ HTTP 에러 발생: {e.code}")
    print("서버 응답 내용:", e.read().decode("utf-8"))
except Exception as e:
    print(f"❌ 기타 에러: {e}")
