target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 확실한 위치(chartjs 플러그인 바로 다음)에 Quill CDN 스크립트 강제 주입
marker = '<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>'
quill_tags = """  <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
  <!-- Quill 에디터 라이브러리 CDN -->
  <link href="https://cdn.quilljs.com/1.3.6/quill.snow.css" rel="stylesheet">
  <script src="https://cdn.quilljs.com/1.3.6/quill.min.js"></script>"""

if "quill.min.js" not in code:
    code = code.replace(marker, quill_tags, 1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("✅ Quill 라이브러리 CDN 삽입 성공!")
else:
    print("ℹ️ 이미 Quill CDN이 포함되어 있습니다. 위치를 재배치합니다.")
    # 혹시 잘못된 위치에 있다면 다시 정리
    code = code.replace('<link href="https://cdn.quilljs.com/1.3.6/quill.snow.css" rel="stylesheet">\n  <script src="https://cdn.quilljs.com/1.3.6/quill.min.js"></script>\n', '')
    code = code.replace(marker, quill_tags, 1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("✅ Quill 라이브러리 CDN 재정리 완료!")
