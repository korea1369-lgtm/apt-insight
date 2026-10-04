import shutil

target = "main.py"
shutil.copyfile(target, target + ".backup_editor")
print(f"✅ 원본 백업 완료: {target}.backup_editor")

with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 1. Quill CDN 추가 (head 태그 내부)
quill_cdn = """  <link href="https://cdn.quilljs.com/1.3.6/quill.snow.css" rel="stylesheet">
  <script src="https://cdn.quilljs.com/1.3.6/quill.min.js"></script>
</head>"""
if "quill.snow.css" not in code:
    code = code.replace("</head>", quill_cdn, 1)

# 2. writeModal 모달 너비 확장 (네이버 블로그 에디터 작업 영역 확보)
code = code.replace(
    "#writeModal { border:1px solid #475569; border-radius:16px; padding:28px; width:min(680px, calc(100vw - 40px));",
    "#writeModal { border:1px solid #475569; border-radius:16px; padding:28px; width:min(900px, calc(100vw - 32px));"
)

# 3. 에디터 영역 HTML 교체
old_content_area = """      <div class="form-group">
        <label class="form-label">내용 (단지 응원, 실거주 후기, 인프라 장단점 등)</label>
        <textarea id="postContentInput" class="form-control" rows="8" placeholder="자유롭게 작성해 주세요" required></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">현장 사진 첨부 (스마트폰 원본 사진도 자동 다운사이징 압축)</label>
        <input type="file" id="postImageInput" accept="image/*" multiple onchange="handleImageSelection(this)" style="font-size: 13px;">
        <div id="imagePreviewContainer" class="image-preview-grid"></div>
      </div>"""

new_content_area = """      <!-- 내용 입력 영역 분기 -->
      <div class="form-group" id="normalContentGroup">
        <label class="form-label">내용 (단지 응원, 실거주 후기, 인프라 장단점 등)</label>
        <textarea id="postContentInput" class="form-control" rows="8" placeholder="자유롭게 작성해 주세요"></textarea>
      </div>
      <div class="form-group" id="insightEditorGroup" style="display:none;">
        <label class="form-label">칼럼 본문 작성 (네이버 블로그형 에디터)</label>
        <div id="insightQuillEditor" style="height: 480px; background: #ffffff; color: #1e293b; font-size: 16px;"></div>
      </div>
      <div class="form-group" id="normalImageGroup">
        <label class="form-label">현장 사진 첨부 (스마트폰 원본 사진도 자동 다운사이징 압축)</label>
        <input type="file" id="postImageInput" accept="image/*" multiple onchange="handleImageSelection(this)" style="font-size: 13px;">
        <div id="imagePreviewContainer" class="image-preview-grid"></div>
      </div>"""

if old_content_area in code:
    code = code.replace(old_content_area, new_content_area, 1)

# 4. 자바스크립트 로직 교체 (용량 최적화 2048px / 0.88 설정 포함)
js_search_target = "  let currentBoardType = 'insight';"

new_js_logic = """  let currentBoardType = 'insight';
  let quillInstance = null;

  function initQuillEditor() {
    if (quillInstance) return;
    const toolbarOptions = [
      [{ 'font': [] }, { 'size': ['small', false, 'large', 'huge'] }],
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'color': [] }, { 'background': [] }],
      [{ 'align': [] }],
      [{ 'list': 'ordered'}, { 'list': 'bullet' }],
      [{ 'indent': '-1'}, { 'indent': '+1' }],
      ['blockquote', 'link', 'image'],
      ['clean']
    ];

    quillInstance = new Quill('#insightQuillEditor', {
      theme: 'snow',
      placeholder: '글과 함께 부동산 인사이트를 기록해 보세요! 사진 버튼을 누르거나 이미지를 복사(Ctrl+V)해 바로 붙여넣을 수 있습니다.',
      modules: { toolbar: toolbarOptions }
    });

    const toolbar = quillInstance.getModule('toolbar');
    toolbar.addHandler('image', selectQuillImage);
  }

  function selectQuillImage() {
    const input = document.createElement('input');
    input.setAttribute('type', 'file');
    input.setAttribute('accept', 'image/*');
    input.click();

    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const uploadUrl = await uploadSmartImage(file);
        const range = quillInstance.getSelection(true);
        quillInstance.insertEmbed(range.index, 'image', uploadUrl);
        quillInstance.setSelection(range.index + 1);
      } catch (err) {
        alert('이미지 업로드에 실패했습니다: ' + err.message);
      }
    };
  }

  // 선명도는 극대화하고 용량은 90% 아끼는 스마트 최적화 (2048px, WebP 품질 0.88)
  async function uploadSmartImage(file) {
    const optimizedFile = await resizeImage(file, 2048, 0.88);
    const fileName = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}.webp`;
    const filePath = `posts/${fileName}`;

    const { error } = await supabaseClient.storage.from('board-images').upload(filePath, optimizedFile);
    if (error) throw error;
    const { data: { publicUrl } } = supabaseClient.storage.from('board-images').getPublicUrl(filePath);
    return publicUrl;
  }"""

if js_search_target in code:
    code = code.replace(js_search_target, new_js_logic, 1)

# 5. 모달 열기 분기 (인사이트 작성 시 에디터 활성화)
old_open_modal = """    document.getElementById('postTitleInput').value = '';
    document.getElementById('postContentInput').value = '';
    document.getElementById('postImageInput').value = '';
    document.getElementById('imagePreviewContainer').innerHTML = '';
    pendingCompressedImages = [];
    document.getElementById('writeModal').showModal();"""

new_open_modal = """    document.getElementById('postTitleInput').value = '';
    document.getElementById('postContentInput').value = '';
    document.getElementById('postImageInput').value = '';
    document.getElementById('imagePreviewContainer').innerHTML = '';
    pendingCompressedImages = [];

    if (boardType === 'insight') {
      initQuillEditor();
      document.getElementById('insightEditorGroup').style.display = 'block';
      document.getElementById('normalContentGroup').style.display = 'none';
      document.getElementById('normalImageGroup').style.display = 'none';
      document.getElementById('postContentInput').removeAttribute('required');
      if (quillInstance) quillInstance.root.innerHTML = '';
    } else {
      document.getElementById('insightEditorGroup').style.display = 'none';
      document.getElementById('normalContentGroup').style.display = 'block';
      document.getElementById('normalImageGroup').style.display = 'block';
      document.getElementById('postContentInput').setAttribute('required', 'required');
    }
    document.getElementById('writeModal').showModal();"""

if old_open_modal in code:
    code = code.replace(old_open_modal, new_open_modal, 1)

# 6. 글 등록 처리 (HTML 및 대표 이미지 자동 연동)
old_submit = """    const title = document.getElementById('postTitleInput').value.trim();
    const content = document.getElementById('postContentInput').value.trim();"""

new_submit = """    const title = document.getElementById('postTitleInput').value.trim();
    let content = '';
    let uploadedUrls = [];

    if (currentBoardType === 'insight') {
      content = quillInstance.root.innerHTML;
      if (!quillInstance.getText().trim() && !content.includes('<img')) {
        alert('내용을 입력해 주세요.');
        return;
      }
      const parser = new DOMParser();
      const doc = parser.parseFromString(content, 'text/html');
      doc.querySelectorAll('img').forEach(img => {
        if (img.src) uploadedUrls.push(img.src);
      });
    } else {
      content = document.getElementById('postContentInput').value.trim();
    }"""

if old_submit in code:
    code = code.replace(old_submit, new_submit, 1)

old_loop = """      const uploadedUrls = [];
      for (const imgFile of pendingCompressedImages) {"""
new_loop = """      if (currentBoardType !== 'insight') {
      for (const imgFile of pendingCompressedImages) {"""
if old_loop in code:
    code = code.replace(old_loop, new_loop, 1)
    code = code.replace("uploadedUrls.push(publicUrl);\n        }\n      }", "uploadedUrls.push(publicUrl);\n        }\n      }\n      }", 1)

# 7. 상세 조회 서식 지원
old_detail_render = """<div class="post-detail-content">${insightEscape(post.content)}</div>"""
new_detail_render = """<div class="post-detail-content">${(boardType === 'insight') ? (post.content || '') : insightEscape(post.content)}</div>"""
if old_detail_render in code:
    code = code.replace(old_detail_render, new_detail_render, 1)

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("🎉 성공! 스마트 용량 최적화 에디터가 main.py에 안전하게 반영되었습니다!")
