target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# 1. 에디터 폼 상단에 토글 스위치 UI 추가
old_editor_label = """      <div class="form-group" id="insightEditorGroup" style="display:none;">
        <label class="form-label">칼럼 본문 작성 (네이버 블로그형 에디터)</label>"""

new_editor_label = """      <div class="form-group" id="insightEditorGroup" style="display:none;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <label class="form-label" style="margin-bottom:0;">칼럼 본문 작성 (네이버 블로그형 에디터)</label>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:700; color:#0284c7; background:#f0f9ff; border:1px solid #bae6fd; padding:4px 10px; border-radius:20px; cursor:pointer; user-select:none;">
            <input type="checkbox" id="chkSmartPhoneResize" style="width:14px; height:14px; cursor:pointer; accent-color:#0284c7;">
            📱 스마트폰 사진 압축 리사이징 (2048px WebP)
          </label>
        </div>"""

if old_editor_label in code:
    code = code.replace(old_editor_label, new_editor_label, 1)

# 2. 이미지 업로드 함수에 체크박스 연동 로직 적용
old_upload_fn_start = "  async function uploadSmartImage(file) {"
new_upload_logic = """  async function uploadSmartImage(file) {
    const isMobileOptimize = document.getElementById('chkSmartPhoneResize')?.checked;
    let targetFile = file;
    let contentType = file.type || 'image/png';
    let ext = file.name.split('.').pop() || 'png';

    // 체크박스가 켜져 있을 때만 스마트폰 고용량 압축 다운사이징 적용
    if (isMobileOptimize) {
      targetFile = await resizeImage(file, 2048, 0.88);
      contentType = 'image/webp';
      ext = 'webp';
    }

    const fileName = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}.${ext}`;
    const filePath = `posts/${fileName}`;

    const { data, error } = await supabaseClient.storage
      .from('board-images')
      .upload(filePath, targetFile, {
        contentType: contentType,
        cacheControl: '3600',
        upsert: false
      });

    if (error) {
      console.error('Supabase 스토리지 업로드 상세 에러:', error);
      throw error;
    }
    const { data: { publicUrl } } = supabaseClient.storage.from('board-images').getPublicUrl(filePath);
    return publicUrl;
  }"""

import re
pattern = r"  async function uploadSmartImage\(file\) \{[\s\S]*?return publicUrl;\s*\}"
if re.search(pattern, code):
    code = re.sub(pattern, new_upload_logic.strip(), code, count=1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("🎉 성공! 스마트폰 사진 압축 리사이징 선택 버튼이 추가되었습니다!")
else:
    print("⚠ 업로드 함수 치환 대상을 찾지 못했습니다.")
