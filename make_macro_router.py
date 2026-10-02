with open("macro_server.py", "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# FastAPI 인스턴스를 APIRouter로 변경
code = code.replace("app = FastAPI()", "macro_router = APIRouter()")
code = code.replace("@app.", "@macro_router.")

# 필요한 import 보강
header = """import os
import sqlite3
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

"""

# 기존 app 실행 구문(uvicorn.run) 비활성화
code = code.replace('if __name__ == "__main__":', 'if False and __name__ == "__main__":')

# 매크로 뷰 서빙 엔드포인트(/view/macro) 추가
router_endpoint = """
@macro_router.get("/view/macro", response_class=HTMLResponse)
def get_macro_view_page():
    html_file = os.path.join(os.path.dirname(__file__), "macro_view.html")
    with open(html_file, "r", encoding="utf-8") as f:
        return f.read()
"""

# 상단에 header 결합
final_code = header + code + "\n" + router_endpoint

with open("macro_router.py", "w", encoding="utf-8") as f:
    f.write(final_code)

print("✅ 1단계 성공: macro_router.py 생성 완료!")
