import os
import re

# "단지 종합 스펙" 또는 "가격 분산도" 텍스트가 들어있는 실제 프론트 파일 탐색
target_file = None
keywords = ["단지 종합 스펙", "가격 분산도", "최근 이평시세"]

for root, dirs, files in os.walk("."):
    if ".git" in root or "__pycache__" in root:
        continue
    for file in files:
        if file.endswith((".html", ".py", ".js")):
            fpath = os.path.join(root, file)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()
                    if any(k in text for k in keywords):
                        target_file = fpath
                        print(f"🎯 UI 화면 코드가 포함된 파일 발견: {target_file}")
                        break
            except Exception:
                pass
    if target_file:
        break

if not target_file:
    print("❌ UI 화면 코드가 들어있는 파일을 찾지 못했습니다. 프로젝트 파일 목록을 확인해야 합니다.")
    exit()

with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

# 1. 분산도 툴팁 교체 문구 (정의 + 4대 핵심 가치)
dispersion_tooltip = """평당 실거래가의 변동계수(CV)로, 거래 가격이 특정 기준선 주변에 얼마나 촘촘하게 형성되어 있는지를 나타냅니다.

[분산도가 낮고 안정적인 단지의 4대 가치]
1. 뛰어난 환금성 & 회전율: 매도·매수 호가 차이가 좁아 빠른 거래 성사 및 자금 회수 예측성 우수
2. 강력한 하방 경직성: 탄탄한 실수요 지지선 구축으로 하락장 및 급매 충격 흡수
3. 균질한 상품성: 동·층 간 편차가 적어 비로열층도 단지 프리미엄을 안정적으로 공유
4. 의사결정 피로도 경감: 상투나 헐값 매도 위험이 없어 탐색 비용과 거래 스트레스 최소화"""

# 2. 최근 이평시세 툴팁 문구
ma_tooltip = """최근 실거래가 추세를 통계적으로 반영한 이동평균선(MA)의 가장 최신 종점 가격입니다.
단발성 특이 거래(급매/이상 최고가) 1~2건에 휘둘리지 않고, 현재 시장에서 형성된 실질적인 '단지 기준 체감 시세'를 뜻합니다."""

# 툴팁 교체 및 주입
# 기존 분산도 title / data-tooltip 교체
content = re.sub(
    r'(가격\s*분산도[^\'\"]*?(?:title|data-tooltip)=[\'\"])[^\'\"]*?([\'\"])',
    rf'\g<1>{dispersion_tooltip}\g<2>',
    content
)

# 최근 이평시세 옆에 도움말 아이콘(?) 추가
if "최근 이평시세" in content and "최신 종점 가격" not in content:
    # <th> 또는 <td> 안의 '최근 이평시세' 옆에 ? 아이콘 붙이기
    content = re.sub(
        r'(최근\s*이평시세)(\s*)(</)',
        rf'\1 <span title="{ma_tooltip}" style="cursor:pointer; color:#888; font-size:12px;">&#9432;</span>\2\3',
        content
    )

# 3. 기본 단지 2개로 변경: 힐스테이트범어 vs 수성범어W
# 기본 배열 교체
content = re.sub(r'\[\s*[\'\"]수성범어W[\'\"],\s*[\'\"]더샵디어엘로[\'\"],\s*[\'\"]청라힐스자이[\'\"]\s*\]', 
                 '["힐스테이트범어", "수성범어W"]', content)
content = re.sub(r'\[\s*[\'\"]수성범어W[\'\"]\s*,\s*[\'\"]더샵디어엘로[\'\"]\s*\]', 
                 '["힐스테이트범어", "수성범어W"]', content)

# 셀렉트박스 기본 선택을 2개 단지로 변경
content = re.sub(r'(<option\s+value=[\'\"]?2[\'\"]?)([^>]*)>', r'\1 selected\2>', content)
content = re.sub(r'(<option\s+value=[\'\"]?3[\'\"]?[^>]*)selected', r'\1', content)

with open(target_file, "w", encoding="utf-8") as f:
    f.write(content)

print("🎉 프론트엔드 UI(툴팁 및 기본 힐스테이트범어 vs 수성범어W) 수정 완료!")
