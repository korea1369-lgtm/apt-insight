with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. 중복 삽입되었거나 꼬인 top10Panel 제거 및 위치 정상화
import re

# 기존 삽입된 패널 태그 제거
code = re.sub(r'<!-- 자주 함께 비교되는 단지 Top 10 패널 -->[\s\S]*?</div>\s*</div>', '', code)

# 깨끗한 Top 10 UI 패널 정의
panel_html = """
    <!-- 🔥 자주 함께 비교되는 단지 Top 10 패널 -->
    <div class="top10-panel" id="top10Panel" style="margin-top: 20px; padding: 16px 20px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.03);">
      <div style="font-size: 14px; font-weight: 700; color: #1e293b; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 6px;">
          <span>🔥 자주 함께 비교되는 단지 Top 10</span>
          <span id="top10TargetName" style="font-size: 12px; font-weight: 500; color: #64748b;"></span>
        </div>
      </div>
      <div id="top10List" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px;">
        <div style="grid-column: 1 / -1; padding: 12px; text-align: center; color: #94a3b8; font-size: 12.5px;">단지를 입력하고 조회하면 함께 비교된 단지 목록이 표시됩니다.</div>
      </div>
    </div>
"""

# 차트 컨테이너가 닫히는 태그 바로 뒤 또는 slotResults 컨테이너 뒤에 안전하게 부착
if 'id="top10Panel"' not in code:
    if '</canvas>' in code:
        # canvas 감싸는 부모 div 닫힘 직후에 배치
        code = code.replace('</canvas>\n      </div>', '</canvas>\n      </div>\n' + panel_html, 1)
    elif 'id="chartContainer"' in code:
        code = code.replace('</div>\n    <div class="table-container"', '</div>\n' + panel_html + '\n    <div class="table-container"', 1)

# 2. 안전한 Top 10 렌더러 함수 등록 (차트 로직과 완전 분리)
safe_js_func = """
function renderTop10Rankings(activeItem) {
  try {
    const targetLabel = document.getElementById('top10TargetName');
    const listContainer = document.getElementById('top10List');
    if (!listContainer) return;

    if (!activeItem || !activeItem.aptName || activeItem.aptName.includes('없음')) {
      listContainer.innerHTML = '<div style="grid-column: 1 / -1; padding: 12px; text-align: center; color: #94a3b8; font-size: 12px;">비교할 단지를 입력하고 조회해 보세요.</div>';
      if (targetLabel) targetLabel.innerText = '';
      return;
    }

    if (targetLabel) targetLabel.innerText = `(${activeItem.aptName} 기준)`;
    listContainer.innerHTML = '';

    const list = (activeItem.data && activeItem.data.top10) ? activeItem.data.top10 : [];
    if (!list || list.length === 0) {
      listContainer.innerHTML = '<div style="grid-column: 1 / -1; padding: 15px; text-align: center; color: #94a3b8; font-size: 12px;">아직 함께 비교된 단지 데이터가 없습니다.</div>';
      return;
    }

    list.forEach((name, idx) => {
      const div = document.createElement('div');
      div.style.cssText = "padding: 8px 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 12.5px; cursor: pointer; display: flex; justify-content: space-between; align-items: center;";
      div.innerHTML = `<span><b>${idx + 1}위</b> ${name}</span><span style="font-size:11px; color:#3b82f6; font-weight: 600;">비교 +</span>`;
      div.onmouseover = () => { div.style.background = "#eff6ff"; div.style.borderColor = "#93c5fd"; };
      div.onmouseout = () => { div.style.background = "#f8fafc"; div.style.borderColor = "#e2e8f0"; };
      div.onclick = () => {
        const input2 = document.getElementById('aptInput2');
        if (input2) {
          input2.value = name;
          fetchAndRender();
        }
      };
      listContainer.appendChild(div);
    });
  } catch (err) {
    console.error("top10 render error:", err);
  }
}
"""

# 기존 renderTop10Rankings 교체
if "function renderTop10Rankings" in code:
    code = re.sub(r'function renderTop10Rankings\([^\)]*\)\s*\{[\s\S]*?\n\}', safe_js_func.strip(), code)
else:
    code = code.replace("function renderChart(", safe_js_func + "\nfunction renderChart(")

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("✅ 차트 캔버스 구조 보존 및 Top 10 독립 연동 완료!")
