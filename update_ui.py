import os
import re

# index.html 파일 경로 탐색
target_file = None
for root, dirs, files in os.walk("."):
    for f in files:
        if f == "index.html":
            target_file = os.path.join(root, f)
            break
    if target_file:
        break

if not target_file:
    print("❌ index.html 파일을 찾을 수 없습니다.")
    exit()

print(f"📄 대상 파일: {target_file}")
with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

# 1. 분산도 툴팁 교체 (정의 + 4대 장점 요약)
dispersion_tooltip_html = """평당 실거래가의 변동계수(CV)로, 거래 가격이 특정 기준선 주변에 얼마나 촘촘하게 형성되어 있는지를 나타냅니다.

[분산도가 낮고 안정적인 단지의 4대 가치]
1. 뛰어난 환금성 & 회전율: 매도·매수 호가 차이가 좁아 빠른 거래 성사 및 자금 회수 예측성 우수
2. 강력한 하방 경직성: 탄탄한 실수요 지지선 구축으로 하락장 및 급매 충격 흡수
3. 균질한 상품성: 동·층 간 편차가 적어 비로열층도 단지 프리미엄을 안정적으로 공유
4. 의사결정 피로도 경감: 상투나 헐값 매도 위험이 없어 탐색 비용과 거래 스트레스 최소화"""

# 2. 최근 이평시세 툴팁
ma_tooltip_html = """최근 실거래가 추세를 통계적으로 반영한 이동평균선(MA)의 가장 최신 종점 가격입니다.
단발성 특이 거래(급매/이상 최고가) 1~2건에 휘둘리지 않고, 현재 시장에서 형성된 실질적인 '단지 기준 체감 시세'를 뜻합니다."""

# 툴팁 교체 (기존 data-tooltip 또는 title 속성 보정)
content = re.sub(
    r'(가격\s*분산도\s*<span[^>]*class="[^"]*tooltip[^"]*"[^>]*title=")[^"]*(")',
    rf'\g<1>{dispersion_tooltip_html}\g<2>',
    content
)
content = re.sub(
    r'(가격\s*분산도\s*<span[^>]*data-tooltip=")[^"]*(")',
    rf'\g<1>{dispersion_tooltip_html}\g<2>',
    content
)

# 최근 이평시세 옆에 물음표 툴팁 추가 (없을 경우 삽입)
if "최근 이평시세" in content and ma_tooltip_html not in content:
    content = re.sub(
        r'(최근\s*이평시세)(\s*)(</th|</td|<span)',
        rf'\1 <span class="help-icon" title="{ma_tooltip_html}" style="cursor:pointer; color:#888; font-size:12px;">&#9432;</span>\2\3',
        content
    )

# 3. 기본 아파트 설정 변경 (힐스테이트범어, 수성범어W / 기본 2개 비교)
# JS 변수 또는 select 기본값 패턴 교체
content = re.sub(r'const\s+DEFAULT_APTS\s*=\s*\[.*?\];', 'const DEFAULT_APTS = ["힐스테이트범어", "수성범어W"];', content)
content = re.sub(r'defaultApts\s*=\s*\[.*?\];', 'defaultApts = ["힐스테이트범어", "수성범어W"];', content)
content = re.sub(r'let\s+selectedApts\s*=\s*\[.*?\];', 'let selectedApts = ["힐스테이트범어", "수성범어W"];', content)

# 비교 단지 수 셀렉트박스 기본값을 2개로 변경
content = re.sub(r'(<option\s+value="2")(\s*)>', r'\1 selected>', content)
content = re.sub(r'(<option\s+value="3"[^>]*)selected', r'\1', content)

with open(target_file, "w", encoding="utf-8") as f:
    f.write(content)

print("✨ UI 툴팁 설명 및 기본 단지(힐스테이트범어 vs 수성범어W) 설정 완료!")
