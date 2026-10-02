with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. results.forEach 관련 구문을 완전히 안전한 배열 체크 코드로 강제 치환
target_broken_pattern = "results.forEach"

if target_broken_pattern in code:
    # results가 배열이 아니더라도 안전하게 순회하도록 변경
    code = code.replace(
        "results.forEach",
        "(Array.isArray(results) ? results : (results ? [results] : [])).forEach"
    )
    print("✅ results.forEach 방어 코드 치환 완료!")

# 2. 혹시 fetchAndRender에서 넘기는 인자가 문제일 경우 대비
code = code.replace(
    "renderTop10Rankings(results)",
    "renderTop10Rankings(Array.isArray(results) ? results : (globalSlotResults || []))"
)

# 3. renderTop10Rankings 시작 부분에 강력한 방어 로직 주입
safe_start = """function renderTop10Rankings(rawResults) {
  const results = Array.isArray(rawResults) ? rawResults : (rawResults ? [rawResults] : []);
"""

import re
code = re.sub(
    r'function renderTop10Rankings\s*\([^)]*\)\s*\{',
    safe_start,
    code,
    count=1
)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("🚀 치환 완료! 파일 저장 성공.")
