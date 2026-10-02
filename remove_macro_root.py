with open("macro_router.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

new_lines = []
skip = False

for line in lines:
    # 133번째 줄 부근의 @macro_router.get("/") 시작 감지
    if '@macro_router.get("/",' in line or '@macro_router.get("/")' in line:
        skip = True
        continue
    
    # 다음 라우터 데코레이터(@macro_router.)가 나오면 스킵 종료
    if skip and line.strip().startswith("@macro_router."):
        skip = False

    if not skip:
        new_lines.append(line)

with open("macro_router.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("✅ macro_router.py에서 루트(/) 가로채기 완벽 제거 완료!")
