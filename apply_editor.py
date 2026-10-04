import os, shutil

# 대상 파일 탐색
target = "index.html"
if not os.path.exists(target):
    for p in ["templates/index.html", "static/index.html"]:
        if os.path.exists(p):
            target = p
            break

if not os.path.exists(target):
    print("❌ index.html 파일을 찾을 수 없습니다. 경로를 확인해주세요.")
    exit()

# 1. 안전 백업 생성
shutil.copyfile(target, target + ".backup")
print(f"✅ 원본 백업 완료: {target}.backup")

with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# 2. Quill CDN 추가 (head 닫히기 직전)
quill_cdn = """
    <!-- Quill Rich Text Editor CDN -->
    <link href="https://cdn.quilljs.com/1.3.6/quill.snow.css" rel="stylesheet">
    <script src="https://cdn.quilljs.com/1.3.6/quill.min.js"></script>
</head>"""

if "quill.snow.css" not in content:
    content = content.replace("</head>", quill_cdn, 1)

# 3. 기존 textarea 교체
old_tag = '<textarea id="insightContent"'
if old_tag in content:
    start_idx = content.find(old_tag)
    end_idx = content.find("</textarea>", start_idx) + len("</textarea>")
    new_editor = """<div id="insightEditorWrapper" class="mb-3">
        <div id="insightEditor" style="min-height: 380px; background: #ffffff; color: #111827; border-radius: 0 0 8px 8px; font-size: 15px;"></div>
        <input type="hidden" id="insightContent">
      </div>"""
    content = content[:start_idx] + new_editor + content[end_idx:]
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    print("🎉 성공! 에디터 HTML 적용이 완벽하게 끝났습니다!")
else:
    print("⚠ textarea id=\"insightContent\" 위치를 찾지 못했습니다.")