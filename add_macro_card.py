target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 홈 허브 카드 목록에 [부동산 매크로] 카드 추가
macro_card = """        <div class="hub-card" onclick="navigateTo('macro')">
          <div style="font-size: 12px; font-weight: 700; color: #ea580c; margin-bottom: 8px;">거시경제 지표</div>
          <div class="hub-title">🌐 부동산 매크로</div>
          <div class="hub-desc">금리, 통화량(M2), 환율, 미분양 추이 등 부동산 시장의 큰 흐름을 분석합니다.</div>
          <div class="hub-action">매크로 분석실 바로가기 ➔</div>
        </div>
"""

# "✍️ 투자 인사이트" 카드 바로 앞 또는 "🏆 아파트 랭킹" 뒤에 자연스럽게 배치
target_marker = """        <div class="hub-card" onclick="navigateTo('insight')">"""

if "navigateTo('macro')" not in code.split('<div class="hub-grid">')[1].split('</div>\n    </div>')[0]:
    if target_marker in code:
        code = code.replace(target_marker, macro_card + target_marker, 1)

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("🎉 홈 화면에 [부동산 매크로] 바로가기 카드가 추가되었습니다!")
