target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 1. CSS 스타일 보정: 캡처 선명도 유지 및 리사이즈 오버레이 스타일
style_marker = "</style>"
custom_editor_style = """
    /* 인라인 이미지 리사이즈 핸들러 스타일 */
    .editor-img-wrapper { position: relative; display: inline-block; max-width: 100%; margin: 8px 0; }
    .editor-img-wrapper img { display: block; max-width: 100%; cursor: pointer; image-rendering: -webkit-optimize-contrast; }
    .editor-img-wrapper.active-resizing { outline: 2px solid #2563eb; }
    .img-resize-handle {
      position: absolute; width: 10px; height: 10px; background: #2563eb; border: 1.5px solid #fff; border-radius: 2px; z-index: 100;
    }
    .handle-nw { top: -5px; left: -5px; cursor: nwse-resize; }
    .handle-ne { top: -5px; right: -5px; cursor: nesw-resize; }
    .handle-sw { bottom: -5px; left: -5px; cursor: nesw-resize; }
    .handle-se { bottom: -5px; right: -5px; cursor: nwse-resize; }
    .post-detail-content img { max-width: 100%; height: auto; border-radius: 6px; image-rendering: -webkit-optimize-contrast; }
</style>"""

if "editor-img-wrapper" not in code:
    code = code.replace("</style>", custom_editor_style, 1)

# 2. 에디터 폼 상단의 체크박스 UI 제거 (불필요해짐)
import re
code = re.sub(r'<div style="display:flex; justify-content:space-between;[\s\S]*?📱 스마트폰 사진 압축 리사이징[\s\S]*?<\/label>\s*<\/div>', 
              '<label class="form-label">칼럼 본문 작성 (📷 캡처 원본 | 📱 스마트폰 사진 압축)</label>', code)

# 3. 툴바에 개별 업로드 버튼(📷 원본 캡처용, 📱 스마트폰 압축용) 구성 및 안정적인 클릭 리사이즈 엔진 교체
old_init_pattern = r"  function initQuillEditor\(\) \{[\s\S]*?async function uploadSmartImage\(file\) \{[\s\S]*?return publicUrl;\s*\}"

new_engine = """  function initQuillEditor() {
    if (quillInstance) return;

    // 툴바 구성: 캡처 원본 삽입(📷)과 스마트폰 사진 압축 삽입(📱) 분리
    const toolbarOptions = [
      [{ 'font': [] }, { 'size': ['small', false, 'large', 'huge'] }],
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'color': [] }, { 'background': [] }],
      [{ 'align': [] }],
      [{ 'list': 'ordered'}, { 'list': 'bullet' }],
      [{ 'indent': '-1'}, { 'indent': '+1' }],
      ['blockquote', 'link'],
      ['clean']
    ];

    quillInstance = new Quill('#insightQuillEditor', {
      theme: 'snow',
      placeholder: '글과 함께 부동산 인사이트를 기록해 보세요! 상단 툴바 버튼으로 사진을 넣을 수 있습니다.',
      modules: { toolbar: toolbarOptions }
    });

    // 툴바 끝에 직관적인 2종 사진 버튼 추가
    const tbEl = quillInstance.getModule('toolbar').container;
    const btnGroup = document.createElement('span');
    btnGroup.className = 'ql-formats';
    btnGroup.innerHTML = `
      <button type="button" id="btnUploadOriginal" title="PC 캡처·스크린샷 (100% 무압축 원본)" style="width:auto; padding:0 8px; font-weight:700; color:#0284c7; font-size:12px;">📷 캡처원본</button>
      <button type="button" id="btnUploadMobile" title="스마트폰 고용량 사진 (2048px 경량화 압축)" style="width:auto; padding:0 8px; font-weight:700; color:#16a34a; font-size:12px;">📱 폰사진압축</button>
    `;
    tbEl.appendChild(btnGroup);

    document.getElementById('btnUploadOriginal').onclick = () => selectAndUpload(false);
    document.getElementById('btnUploadMobile').onclick = () => selectAndUpload(true);

    // 본문 이미지 클릭 시 테두리 및 4개 모서리 크기 조절 핸들 부착
    quillInstance.root.addEventListener('click', (e) => {
      if (e.target && e.target.tagName === 'IMG') {
        attachImageResizer(e.target);
      } else {
        removeResizers();
      }
    });
  }

  let activeResizerImg = null;
  function removeResizers() {
    document.querySelectorAll('.active-resizing').forEach(el => el.classList.remove('active-resizing'));
    document.querySelectorAll('.img-resize-handle').forEach(el => el.remove());
    activeResizerImg = null;
  }

  function attachImageResizer(img) {
    if (activeResizerImg === img) return;
    removeResizers();
    activeResizerImg = img;

    const parent = img.parentElement;
    parent.classList.add('editor-img-wrapper', 'active-resizing');

    ['nw', 'ne', 'sw', 'se'].forEach(pos => {
      const handle = document.createElement('div');
      handle.className = `img-resize-handle handle-${pos}`;
      parent.appendChild(handle);

      handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const startX = e.clientX;
        const startWidth = img.offsetWidth;

        function onMouseMove(moveEvt) {
          const deltaX = (pos === 'se' || pos === 'ne') ? (moveEvt.clientX - startX) : (startX - moveEvt.clientX);
          const newW = Math.max(80, startWidth + deltaX);
          img.style.width = newW + 'px';
          img.setAttribute('width', newW);
        }

        function onMouseUp() {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    });
  }

  function selectAndUpload(isCompress) {
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
  }

  async function processAndUploadImage(file, isCompress) {
    let finalFile = file;
    let ext = file.name.split('.').pop() || 'png';
    let contentType = file.type || 'image/png';

    // 스마트폰 버튼을 눌렀을 때만 2048px WebP 리사이징
    if (isCompress) {
      finalFile = await resizeImage(file, 2048, 0.88);
      ext = 'webp';
      contentType = 'image/webp';
    }

    const fileName = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}.${ext}`;
    const filePath = `posts/${fileName}`;

    const { error } = await supabaseClient.storage
      .from('board-images')
      .upload(filePath, finalFile, {
        contentType: contentType,
        cacheControl: '3600',
        upsert: false
      });

    if (error) throw error;
    const { data: { publicUrl } } = supabaseClient.storage.from('board-images').getPublicUrl(filePath);
    return publicUrl;
  }"""

code = re.sub(old_init_pattern, new_engine, code, count=1)

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("🎉 3가지 개선(클릭 리사이즈 활성화, 원본 선명도 보존, 📷캡처/📱폰사진 분리 툴바) 적용 완료!")
