with open("macro_router.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    # macro_router가 루트("/")를 가로채지 못하도록 차단
    if '@macro_router.get("/")' in line or "@macro_router.get('/')" in line:
        skip = True
        continue
    if skip and line.startswith("def "):
        skip = False
        continue
    if not skip:
        out.append(line)

with open("macro_router.py", "w", encoding="utf-8") as f:
    f.writelines(out)

print("✅ 루트 엔드포인트 충돌 해결 완료!")
