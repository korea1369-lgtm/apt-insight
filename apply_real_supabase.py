with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. 화면에 노출되던 "-->" 찌꺼기 문자열 제거
code = code.replace("🔥 자주 함께 비교되는 단지 Top 10</div>\n -->", "🔥 자주 함께 비교되는 단지 Top 10</div>")
code = code.replace("🔥 자주 함께 비교되는 단지 Top 10</div>\n-->", "🔥 자주 함께 비교되는 단지 Top 10</div>")
code = code.replace("-->\n              <div class=\"top10-tabs\"", "<div class=\"top10-tabs\"")

# 2. 화살표 액션 제거 ("비교 ➜" 또는 화살표 문자열 삭제)
code = code.replace("action.textContent = '비교 ➜';", "action.textContent = '';")
code = code.replace("action.textContent = '비교 +';", "action.textContent = '';")

# 3. get_chart_data 내부에서 하드코딩(APT_COMPARE_RANKINGS)을 버리고 실제 Supabase 순위 호출로 교체
old_top10_logic = "top10_list = APT_COMPARE_RANKINGS.get(pure_name, DEFAULT_RANK)"
new_top10_logic = "top10_list = get_real_top10_compared(pure_name)"

if old_top10_logic in code:
    code = code.replace(old_top10_logic, new_top10_logic)

# 4. 프론트엔드에서 단지 2개 이상 비교 조회 시 Supabase에 카운트를 누적하는 엔드포인트 및 호출 연결
log_endpoint = """
@app.post("/api/log-compare")
async def log_compare_api(payload: dict):
    apts = payload.get("apts", [])
    if apts and len(apts) >= 2:
        record_compare_pair(apts)
    return {"status": "ok"}
"""

if "/api/log-compare" not in code:
    code = code.replace("app = FastAPI()", "app = FastAPI()\n" + log_endpoint)

# 5. fetchAndRender 비동기 흐름 끝에 비교 로그 기록 요청 삽입
js_log_call = """      // Supabase 비교 로그 기록
      const validNames = slotResults.map(r => r.aptName).filter(n => n && !n.includes("없음"));
      if (validNames.length >= 2) {
        fetch('/api/log-compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ apts: validNames })
        }).catch(() => {});
      }
"""

if "fetch('/api/log-compare'" not in code:
    code = code.replace(
        "globalSlotResults = slotResults;",
        "globalSlotResults = slotResults;\n" + js_log_call
    )

# 6. Top 10 빈 값 표시 문구 개선
code = code.replace("표시할 비교 순위가 없습니다.", "아직 함께 비교된 단지 데이터가 없습니다.")

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("🚀 찌꺼기 주석 제거, 가상 데이터 완전 삭제, Supabase 실시간 연동 완료!")
