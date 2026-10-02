import shutil

# 0. 만약을 대비한 원본 main.py 안전 백업
shutil.copy("main.py", "main_backup_safe.py")
print("🔒 기존 main.py 백업 완료 -> main_backup_safe.py")

with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. macro_router 임포트 및 FastAPI 앱에 마운트
if "from macro_router import macro_router" not in code:
    code = code.replace("app = FastAPI()", "from macro_router import macro_router\napp = FastAPI()\napp.include_router(macro_router)")

# 2. 상단 네비게이션 버튼 활성화
old_nav_btn = '<button class="nav-btn" style="opacity: 0.45; cursor: not-allowed;">부동산 매크로</button>'
new_nav_btn = '<button class="nav-btn" id="nav-macro" onclick="navigateTo(\'macro\')">부동산 매크로</button>'
code = code.replace(old_nav_btn, new_nav_btn)

# 3. 메인 화면에 매크로 전용 iframe 샌드박스 영역 추가 (기존 vs 영역 바로 아래)
macro_page_html = """
    <div class="page-view" id="page-macro" style="height: calc(100vh - 100px); margin: 0 -20px;">
      <iframe id="macroFrame" src="" style="width: 100%; height: 100%; border: none; border-radius: 14px; background: #0f172a;" loading="lazy"></iframe>
    </div>
"""
if 'id="page-macro"' not in code:
    # page-vs 닫히는 태그 뒤에 매크로 페이지 배치
    code = code.replace('</div>\n    </div>\n  </div>\n\n<script>', '</div>\n    </div>' + macro_page_html + '\n  </div>\n\n<script>')

# 4. navigateTo 함수에 매크로 탭 전환 및 지연 로딩(Lazy Loading) 연결
old_nav_logic = """    if (pageId === 'vs') {
      if (!chart) initVsChart();
      else fetchAndRender();
    } else if (pageId === 'rank') {
      fetchRankings();
    }"""

new_nav_logic = """    if (pageId === 'vs') {
      if (!chart) initVsChart();
      else fetchAndRender();
    } else if (pageId === 'rank') {
      fetchRankings();
    } else if (pageId === 'macro') {
      const frame = document.getElementById('macroFrame');
      if (frame && (!frame.src || frame.src === 'about:blank' || frame.src.endsWith('/'))) {
        frame.src = '/view/macro';
      }
    }"""

code = code.replace(old_nav_logic, new_nav_logic)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("🎉 2단계 성공: main.py 안전 통합 완료!")
