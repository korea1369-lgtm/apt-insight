with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. CSS에서 top10-panel 관련 display none 완벽 제거 및 눈에 띄는 스타일 보장
code = code.replace(".top10-panel { display: none !important; }", "")
code = code.replace(".recommend-box { display: none !important; }", "")

# 2. 주석 처리되어 있던 HTML 블록 주석 해제 (<!-- HIDDEN RECOMMEND BLOCK ... --> 형태 제거)
import re
code = re.sub(r'<!--\s*HIDDEN RECOMMEND BLOCK\s*', '', code)
code = re.sub(r'-->\s*<!--\s*END RECOMMEND BLOCK\s*-->', '', code)

# 3. 만약 HTML 본문에 top10-panel 컨테이너가 누락되어 있거나 주석으로 감싸진 경우를 대비해 정상 구조 확인/주입
target_panel_html = """
    <!-- 자주 함께 비교되는 단지 Top 10 패널 -->
    <div class="top10-panel" id="top10Panel" style="margin-top: 24px; padding: 18px 20px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.04);">
      <div style="font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 12px; display: flex; align-items: center; gap: 6px;">
        <span>🔥 자주 함께 비교되는 단지 Top 10</span>
        <span id="top10TargetName" style="font-size: 13px; font-weight: 500; color: #64748b;"></span>
      </div>
      <div id="top10List" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px;">
        <div style="grid-column: 1 / -1; padding: 12px; text-align: center; color: #94a3b8; font-size: 13px;">비교할 단지를 검색하면 순위가 표시됩니다.</div>
      </div>
    </div>
"""

# slot-results-container 또는 차트 컨테이너 뒤쪽에 top10-panel이 없으면 명시적으로 추가
if 'id="top10Panel"' not in code:
    if '<div id="chartContainer"' in code:
        code = code.replace('<div id="chartContainer"', target_panel_html + '\n<div id="chartContainer"')
    elif '<div class="chart-container"' in code:
        code = code.replace('<div class="chart-container"', target_panel_html + '\n<div class="chart-container"')

# 4. renderTop10Rankings JS 함수가 UI를 정확하게 채우도록 업데이트
js_render_func = """
function renderTop10Rankings(activeItem) {
  const panel = document.getElementById('top10Panel');
  const targetLabel = document.getElementById('top10TargetName');
  const listContainer = document.getElementById('top10List');
  if (!panel || !listContainer) return;

  if (!activeItem || !activeItem.aptName) {
    listContainer.innerHTML = '<div style="grid-column: 1 / -1; padding: 15px; text-align: center; color: #94a3b8; font-size: 13px;">단지를 입력하고 조회하면 함께 비교된 단지 Top 10이 표시됩니다.</div>';
    if (targetLabel) targetLabel.innerText = '';
    return;
  }

  if (targetLabel) targetLabel.innerText = `(${activeItem.aptName} 기준)`;
  listContainer.innerHTML = '';

  const list = (activeItem.data && activeItem.data.top10) ? activeItem.data.top10 : [];
  if (list.length === 0) {
    listContainer.innerHTML = '<div style="grid-column: 1 / -1; padding: 20px; text-align: center; color: #94a3b8; font-size: 13px;">아직 함께 비교된 단지 데이터가 없습니다.</div>';
    return;
  }

  list.forEach((name, idx) => {
    const div = document.createElement('div');
    div.style.cssText = "padding: 8px 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s;";
    div.innerHTML = `<span><b>${idx + 1}위</b> ${name}</span><span style="font-size:11px; color:#3b82f6;">비교 +</span>`;
    div.onmouseover = () => { div.style.background = "#eff6ff"; div.style.borderColor = "#93c5fd"; };
    div.onmouseout = () => { div.style.background = "#f8fafc"; div.style.borderColor = "#e2e8f0"; };
    div.onclick = () => {
      const input2 = document.getElementById('aptInput2');
      if (input2) {
        input2.value = name;
        if (typeof fetchAndRender === 'function') fetchAndRender();
      }
    };
    listContainer.appendChild(div);
  });
}
"""

if "function renderTop10Rankings" in code:
    code = re.sub(r'function renderTop10Rankings\([^\)]*\)\s*\{[\s\S]*?\n\}', js_render_func.strip(), code)
else:
    code = code.replace("function renderChart(", js_render_func + "\nfunction renderChart(")

# 5. 차트 렌더 완료 시(fetchAndRender 끝부분) renderTop10Rankings(slotResults[0]) 자동 호출 보장
if "renderTop10Rankings(slotResults[0]);" not in code:
    code = code.replace("globalSlotResults = slotResults;", "globalSlotResults = slotResults;\n      if (slotResults && slotResults.length > 0) renderTop10Rankings(slotResults[0]);")

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("✨ Top 10 UI 패널 및 렌더링 스크립트 복구 완료!")
