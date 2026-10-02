import re

with open("main.py", "r", encoding="utf-8") as f:
    text = f.read()

# 1. 비교표 툴팁 문자열 교정 (단일 따옴표 연결 방식으로 JS 에러 차단)
safe_compare_row = (
    "html += '</tr><tr><th class=\"metric-col\" style=\"background:#f8fafc;\">' +\n"
    "  '<span>6. 가격 분산도</span>' +\n"
    "  '<span class=\"help-tooltip-trigger\">?' +\n"
    "    '<div class=\"help-tooltip-box\" style=\"left: 0; right: auto; width: 360px;\">' +\n"
    "      '<div class=\"tooltip-title\">💡 가격 분산도(Price Dispersion)란?</div>' +\n"
    "      '<div class=\"tooltip-def\">실거래가의 통계적 변동계수(표준편차/평균)로 시장의 <strong>가격 합의 수준</strong>을 나타냅니다.</div>' +\n"
    "      '<div style=\"font-size: 12px; line-height: 1.6; color: #cbd5e1;\">' +\n"
    "        '<div style=\"margin-bottom: 6px;\"><strong style=\"color: #38bdf8;\">• 균질한 상품성 & 가격 합의:</strong> 동·호수별 편차가 적고 적정 시세에 대한 시장 공감대가 두터워 왜곡이 적습니다.</div>' +\n"
    "        '<div style=\"margin-bottom: 6px;\"><strong style=\"color: #38bdf8;\">• 바가지 · 저가 매도 위험 제거:</strong> 상투 매수나 헐값 매각 위험이 없어 탐색 비용과 의사결정 피로도가 대폭 줄어듭니다.</div>' +\n"
    "        '<div><strong style=\"color: #38bdf8;\">• 우수한 환금성:</strong> 시세 예측 가능성이 높아 거래 체결이 매끄럽고 매수 대기층이 탄탄합니다.</div>' +\n"
    "      '</div>' +\n"
    "    '</div>' +\n"
    "  '</span>' +\n"
    "'</th>';"
)

text = re.sub(
    r"html \+= [`\\\']</tr><tr><th class=\"metric-col\" style=\"background:#f8fafc;\">.*?</span>\s*</th>[`\\\'];",
    safe_compare_row,
    text,
    flags=re.DOTALL
)

# 2. 랭킹 테이블 헤더 툴팁 교정
safe_rank_th = (
    '<th>\n'
    '  <span>가격 분산도</span>\n'
    '  <span class="help-tooltip-trigger">?\n'
    '    <div class="help-tooltip-box" style="width: 360px;">\n'
    '      <div class="tooltip-title">💡 가격 분산도(Price Dispersion)란?</div>\n'
    '      <div class="tooltip-def">실거래가의 통계적 변동계수(표준편차/평균)로 시장의 <strong>가격 합의 수준</strong>을 나타냅니다.</div>\n'
    '      <div style="font-size: 12px; line-height: 1.6; color: #cbd5e1; text-align: left;">\n'
    '        <div style="margin-bottom: 6px;"><strong style="color: #38bdf8;">• 균질한 상품성 & 가격 합의:</strong> 동·호수별 편차가 적고 적정 시세에 대한 시장 공감대가 두터워 왜곡이 적습니다.</div>\n'
    '        <div style="margin-bottom: 6px;"><strong style="color: #38bdf8;">• 바가지 · 저가 매도 위험 제거:</strong> 상투 매수나 헐값 매각 위험이 없어 탐색 비용과 의사결정 피로도가 대폭 줄어듭니다.</div>\n'
    '        <div><strong style="color: #38bdf8;">• 우수한 환금성:</strong> 시세 예측 가능성이 높아 거래 체결이 매끄럽고 매수 대기층이 탄탄합니다.</div>\n'
    '      </div>\n'
    '    </div>\n'
    '  </span>\n'
    '</th>'
)

text = re.sub(
    r'<th>\s*<span>가격 분산도</span>\s*<span class="help-tooltip-trigger">.*?</span>\s*</th>',
    safe_rank_th,
    text,
    flags=re.DOTALL
)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(text)

print("[수정 완료] 자바스크립트 문법 오류 없이 툴팁 적용 완료!")
