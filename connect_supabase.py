import re

with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# Supabase 연동 전용 함수 정의
supabase_funcs = """
import urllib.request
import json
import urllib.parse

SUPABASE_URL = "https://hikwjqgjollisdistbif.supabase.co"
SUPABASE_KEY = "sb_publishable_eIzC8sNZ6gBe62KixTRm1w_1dE2dNG9"

def record_compare_pair(apt_list):
    valid_apts = sorted(list(set([a.strip() for a in apt_list if a and a.strip()])))
    if len(valid_apts) < 2:
        return
    for i in range(len(valid_apts)):
        for j in range(i + 1, len(valid_apts)):
            a, b = valid_apts[i], valid_apts[j]
            try:
                # 1. 기존 카운트 조회
                query = urllib.parse.urlencode({"apt_a": f"eq.{a}", "apt_b": f"eq.{b}", "select": "compare_count"})
                url = f"{SUPABASE_URL}/rest/v1/apt_compare_pairs?{query}"
                req = urllib.request.Request(url, headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                })
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                
                # 2. 카운트 누적 Upsert
                current_cnt = data[0]['compare_count'] if data else 0
                payload = json.dumps({
                    "apt_a": a,
                    "apt_b": b,
                    "compare_count": current_cnt + 1
                }).encode('utf-8')
                
                upsert_url = f"{SUPABASE_URL}/rest/v1/apt_compare_pairs"
                upsert_req = urllib.request.Request(upsert_url, data=payload, method="POST", headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates"
                })
                urllib.request.urlopen(upsert_req, timeout=3)
            except Exception:
                pass

def get_real_top10_compared(apt_name):
    clean = clean_apt_name(apt_name)
    try:
        query_a = urllib.parse.urlencode({
            "or": f"(apt_a.eq.{clean},apt_b.eq.{clean})",
            "order": "compare_count.desc",
            "limit": "10",
            "select": "apt_a,apt_b,compare_count"
        })
        url = f"{SUPABASE_URL}/rest/v1/apt_compare_pairs?{query_a}"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        })
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        result = []
        for row in data:
            partner = row['apt_b'] if row['apt_a'] == clean else row['apt_a']
            result.append(partner)
        return result
    except Exception:
        return []
"""

# 기존 로컬 SQLite 기반 tracking 함수 교체
pattern = r'def record_compare_pair\(apt_list\):[\s\S]*?return \[r\[0\] for r in rows\][\s\S]*?except Exception:[\s\S]*?return \[\]'
if re.search(pattern, code):
    code = re.sub(pattern, supabase_funcs.strip(), code)
else:
    code = code.replace("app = FastAPI()", supabase_funcs + "\napp = FastAPI()")

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("🚀 Supabase 클라우드 DB 연동 완료!")
