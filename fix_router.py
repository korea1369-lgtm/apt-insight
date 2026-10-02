with open("macro_server.py", "r", encoding="utf-8-sig", errors="ignore") as f:
    lines = f.readlines()

out = [
    "import os\n",
    "import sqlite3\n",
    "from fastapi import APIRouter, Query, HTTPException\n",
    "from fastapi.responses import HTMLResponse, JSONResponse\n\n",
    "macro_router = APIRouter()\n\n"
]

for line in lines:
    clean = line.replace('\ufeff', '')
    if "app = FastAPI" in clean:
        continue
    clean = clean.replace("@app.", "@macro_router.")
    if 'if __name__ == "__main__":' in clean:
        break
    out.append(clean)

out.append("""

@macro_router.get("/view/macro", response_class=HTMLResponse)
def get_macro_view_page():
    html_file = os.path.join(os.path.dirname(__file__), "macro_view.html")
    with open(html_file, "r", encoding="utf-8") as f:
        return f.read()
""")

with open("macro_router.py", "w", encoding="utf-8") as f:
    f.writelines(out)

print("✅ macro_router.py 정상 재구성 완료!")
