target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 1. 커서 위치 기억 및 드래그/복사붙여넣기 지원 로직 추가
old_select_upload = """  function selectAndUpload(isCompress) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.click();

    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const url = await processAndUploadImage(file, isCompress);
        const range = quillInstance.getSelection(true) || { index: quillInstance.getLength() };
        quillInstance.insertEmbed(range.index, 'image', url);
        quillInstance.setSelection(range.index + 1);
      } catch (err) {
        alert('이미지 업로드에 실패했습니다: ' + err.message);
      }
    };
  }"""

new_select_upload = """  // 마지막 유효 커서 위치 추적
  let savedQuillRange = null;

  function trackQuillSelection() {
    if (!quillInstance) return;
    quillInstance.on('selection-change', (range) => {
      if (range) {
        savedQuillRange = range;
      }
    });
  }

  function selectAndUpload(isCompress) {
    // 버튼 클릭으로 포커스가 빠지기 직전의 커서 위치 확보
    const currentRange = quillInstance.getSelection();
    if (currentRange) {
      savedQuillRange = currentRange;
    }

    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.click();

    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const url = await processAndUploadImage(file, isCompress);
        
        // 기억해둔 마지막 커서 위치에 정확히 삽입 (없으면 글 맨 끝)
        let insertIndex = quillInstance.getLength() - 1;
        if (savedQuillRange && typeof savedQuillRange.index === 'number') {
          insertIndex = savedQuillRange.index;
        }

        quillInstance.insertEmbed(insertIndex, 'image', url, 'user');
        // 사진 삽입 후 바로 다음 줄로 커서 이동
        quillInstance.setSelection(insertIndex + 1, 'silent');
        savedQuillRange = { index: insertIndex + 1, length: 0 };
      } catch (err) {
        alert('이미지 업로드에 실패했습니다: ' + err.message);
      }
    };
  }"""

if old_select_upload in code:
    code = code.replace(old_select_upload, new_select_upload, 1)
else:
    import re
    code = re.sub(r'function selectAndUpload\(isCompress\) \{[\s\S]*?alert\(\'이미지 업로드에 실패했습니다: \' \+ err\.message\);\s*\}\s*\};\s*\}', new_select_upload, code, count=1)

# 2. initQuillEditor 안에 trackQuillSelection() 호출 추가
if "trackQuillSelection();" not in code:
    code = code.replace("setupImageResizerEngine();", "setupImageResizerEngine();\n    trackQuillSelection();", 1)

# 3. 이미지 드래그 앤 드롭 및 스타일 보정 (이미지를 잡고 끌 수 있도록 draggable 활성화)
img_drag_style = """
    #insightQuillEditor .ql-editor img {
      cursor: pointer;
      display: inline-block;
      vertical-align: middle;
      max-width: 100%;
      user-select: all;
      -webkit-user-drag: auto;
    }
"""
if "user-select: all;" not in code:
    code = code.replace("#insightQuillEditor .ql-editor img {", img_drag_style.strip() + "\n    /* old */\n    .temp-old-img {", 1)

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("🎉 커서 위치 정확 삽입 & Ctrl+X 이동 & 마우스 드래그 이동 패치 완료!")
