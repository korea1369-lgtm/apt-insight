target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 1. 상단 로고 UI 변경
old_logo = """    <div class="logo-area" onclick="navigateTo('home')">🏢 <span>TECH REALTY INSIGHT</span></div>"""
new_logo = """    <div class="logo-area" onclick="navigateTo('home')" style="display:flex; align-items:center; gap:9px; cursor:pointer;">
      <img src="/static/logo.png" alt="아인싸 로고" onerror="this.onerror=null; this.src='아인싸.png';" style="height:36px; width:auto; border-radius:6px; object-fit:contain;">
      <span style="font-size:18px; font-weight:800; letter-spacing:-0.3px; color:#38bdf8;">아인싸 <span style="font-size:13.5px; font-weight:600; color:#94a3b8; margin-left:2px;">(Apt InSight)</span></span>
    </div>"""

if old_logo in code:
    code = code.replace(old_logo, new_logo, 1)

# 2. 브라우저 탭 타이틀도 함께 매끄럽게 변경
old_title = "<title>TECH REALTY INSIGHT - 실거래가 기술적 분석실</title>"
new_title = "<title>아인싸 (Apt InSight) - 아파트 실거래가 기술적 분석</title>"
if old_title in code:
    code = code.replace(old_title, new_title, 1)

# 3. 로컬 이미지 서빙을 위해 static 마운트가 없을 경우를 대비한 라우트 보장
if "from fastapi.staticfiles import StaticFiles" not in code and "@app.get('/static/logo.png')" not in code:
    route_patch = """
from fastapi.responses import FileResponse

@app.get("/static/logo.png")
@app.get("/logo.png")
def get_site_logo():
    for p in ["logo.png", "아인싸.png", "static/logo.png"]:
        if os.path.exists(p):
            return FileResponse(p)
    return HTMLResponse("", status_code=404)
"""
    code = code.replace("app = FastAPI()", "app = FastAPI()\n" + route_patch, 1)

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("🎉 상단 네비게이션 로고가 [아인싸 (Apt InSight)]로 성공적으로 변경되었습니다!")
