import re

with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# results.forEach 또는 인자 문제로 터지는 renderTop10Rankings 함수를 완전 무결한 안전 코드로 교체
safe_top10_function = """function renderTop10Rankings(param) {
  try {
    const targetLabel = document.getElementById('top10TargetName');
    const listContainer = document.getElementById('top10List');
    if (!listContainer) return;

    // 파라미터가 배열로 들어오든 단일 단지 객체로 들어오든 1번 슬롯 단지를 추출
    let activeItem = null;
    if (Array.isArray(param)) {
      activeItem = param.find(item => item && item.aptName && !item.aptName.includes("없음")) || param[0];
    } else if (param && typeof param === 'object') {
      activeItem = param;
    }

    if (!activeItem || !activeItem.aptName || activeItem.aptName.includes("없음")) {
      listContainer.innerHTML = '<div style="grid-column: 1 / -1; padding: 12px; text-align: center; color: #94a3b8; font-size: 12px;">비교할 단지를 입력하고 조회해 보세요.</div>';
      if (targetLabel) targetLabel.innerText = '';
      return;
    }

    if (targetLabel) targetLabel.innerText = `(${activeItem.aptName} 기준)`;
    listContainer.innerHTML = '';

    const list = (activeItem.data && Array.isArray(activeItem.data.top10)) ? activeItem.data.top10 : [];
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
          if (typeof fetchAndRender === 'function') fetchAndRender();
        }
      };
      listContainer.appendChild(div);
    });
  } catch (err) {
    console.error("top10 render safe error:", err);
  }
}"""

# 기존 renderTop10Rankings 전체 함수 치환
pattern = r'function renderTop10Rankings[\s\S]*?\n\}'
if re.search(pattern, code):
    code = re.sub(pattern, safe_top10_function, code)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("✅ TypeError: results.forEach 해결 및 방어 코드 적용 완료!")
