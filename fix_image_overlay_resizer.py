target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 1. 완벽한 독립 오버레이 리사이저 CSS 주입
overlay_css = """
    /* 절대 좌표 기반 Quill 이미지 리사이저 오버레이 */
    #quillImageResizerBox {
      position: absolute;
      display: none;
      border: 2px solid #2563eb;
      pointer-events: none;
      z-index: 10000;
      box-sizing: border-box;
    }
    .quill-resizer-handle {
      position: absolute;
      width: 11px;
      height: 11px;
      background: #2563eb;
      border: 2px solid #ffffff;
      border-radius: 2px;
      pointer-events: auto;
      box-sizing: border-box;
    }
    .handle-tl { top: -6px; left: -6px; cursor: nwse-resize; }
    .handle-tr { top: -6px; right: -6px; cursor: nesw-resize; }
    .handle-bl { bottom: -6px; left: -6px; cursor: nesw-resize; }
    .handle-br { bottom: -6px; right: -6px; cursor: nwse-resize; }
    #insightQuillEditor .ql-editor img {
      cursor: pointer;
      display: inline-block;
      vertical-align: middle;
      max-width: 100%;
    }
</style>"""

if "#quillImageResizerBox" not in code:
    code = code.replace("</style>", overlay_css, 1)

# 2. 에디터 컨테이너에 relative 스타일 보장 및 오버레이 박스 주입
editor_box_old = '<div id="insightQuillEditor" style="height: 480px; background: #ffffff; color: #1e293b; font-size: 16px;"></div>'
editor_box_new = """<div style="position: relative;">
          <div id="insightQuillEditor" style="height: 480px; background: #ffffff; color: #1e293b; font-size: 16px;"></div>
          <div id="quillImageResizerBox">
            <div class="quill-resizer-handle handle-tl" data-dir="tl"></div>
            <div class="quill-resizer-handle handle-tr" data-dir="tr"></div>
            <div class="quill-resizer-handle handle-bl" data-dir="bl"></div>
            <div class="quill-resizer-handle handle-br" data-dir="br"></div>
          </div>
        </div>"""

if editor_box_old in code and "#quillImageResizerBox" not in code:
    code = code.replace(editor_box_old, editor_box_new, 1)

# 3. 신뢰도 100% 오버레이 리사이징 이벤트 엔진 연결
import re

resizer_js = """
  let activeTargetImg = null;

  function updateResizerPosition() {
    const resizerBox = document.getElementById('quillImageResizerBox');
    if (!resizerBox || !activeTargetImg) {
      if (resizerBox) resizerBox.style.display = 'none';
      return;
    }
    const container = document.getElementById('insightQuillEditor').parentElement;
    const cRect = container.getBoundingClientRect();
    const iRect = activeTargetImg.getBoundingClientRect();

    resizerBox.style.display = 'block';
    resizerBox.style.top = (iRect.top - cRect.top) + 'px';
    resizerBox.style.left = (iRect.left - cRect.left) + 'px';
    resizerBox.style.width = iRect.width + 'px';
    resizerBox.style.height = iRect.height + 'px';
  }

  function setupImageResizerEngine() {
    const editorEl = document.getElementById('insightQuillEditor');
    const resizerBox = document.getElementById('quillImageResizerBox');
    if (!editorEl || !resizerBox) return;

    // 본문 내부 이미지 클릭 감지
    editorEl.addEventListener('click', (e) => {
      if (e.target && e.target.tagName === 'IMG') {
        e.stopPropagation();
        activeTargetImg = e.target;
        updateResizerPosition();
      } else {
        activeTargetImg = null;
        resizerBox.style.display = 'none';
      }
    });

    // 스크롤 시 오버레이 위치 추적
    const qlEditor = editorEl.querySelector('.ql-editor');
    if (qlEditor) {
      qlEditor.addEventListener('scroll', () => {
        if (activeTargetImg) updateResizerPosition();
      });
    }

    // 모서리 핸들 드래그 이벤트
    const handles = resizerBox.querySelectorAll('.quill-resizer-handle');
    handles.forEach(handle => {
      handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!activeTargetImg) return;

        const dir = handle.getAttribute('data-dir');
        const startX = e.clientX;
        const startWidth = activeTargetImg.offsetWidth;
        const aspectRatio = (activeTargetImg.naturalHeight || activeTargetImg.offsetHeight) / 
                            (activeTargetImg.naturalWidth || activeTargetImg.offsetWidth || 1);

        function onMouseMove(moveEvt) {
          const deltaX = (dir === 'br' || dir === 'tr') ? (moveEvt.clientX - startX) : (startX - moveEvt.clientX);
          const newWidth = Math.max(60, startWidth + deltaX);
          
          activeTargetImg.style.width = newWidth + 'px';
          activeTargetImg.style.height = 'auto';
          activeTargetImg.setAttribute('width', newWidth);
          updateResizerPosition();
        }

        function onMouseUp() {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    });

    // 모달창 바깥 클릭 시 오버레이 해제
    document.addEventListener('click', (e) => {
      if (!editorEl.contains(e.target) && !resizerBox.contains(e.target)) {
        activeTargetImg = null;
        resizerBox.style.display = 'none';
      }
    });
  }
"""

# 기존 부실했던 리사이저 핸들러 함수들 제거 및 신규 엔진 교체
code = re.sub(r'let activeResizerImg = null;[\s\S]*?attachImageResizer\(img\) \{[\s\S]*?\}\s*\}\);?\s*\}', '', code)

# initQuillEditor 내부에서 setupImageResizerEngine 호출하도록 보강
init_call_old = "tbEl.appendChild(btnGroup);"
init_call_new = """tbEl.appendChild(btnGroup);
    setupImageResizerEngine();"""

if init_call_old in code and "setupImageResizerEngine();" not in code:
    code = code.replace(init_call_old, init_call_new, 1)

# 전역 함수로 주입
if "function setupImageResizerEngine()" not in code:
    code = code.replace("function selectAndUpload(isCompress) {", resizer_js + "\n  function selectAndUpload(isCompress) {", 1)

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("🎉 절대 좌표 기반 오버레이 리사이저 패치 완료!")
