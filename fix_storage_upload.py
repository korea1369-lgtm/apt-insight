target = "main.py"
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# uploadSmartImage 함수를 더 견고하고 표준적인 업로드 방식으로 교체
old_upload_fn = """  // 선명도는 극대화하고 용량은 90% 아끼는 스마트 최적화 (2048px, WebP 품질 0.88)
  async function uploadSmartImage(file) {
    const optimizedFile = await resizeImage(file, 2048, 0.88);
    const fileName = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}.webp`;
    const filePath = `posts/${fileName}`;

    const { error } = await supabaseClient.storage.from('board-images').upload(filePath, optimizedFile);
    if (error) throw error;
    const { data: { publicUrl } } = supabaseClient.storage.from('board-images').getPublicUrl(filePath);
    return publicUrl;
  }"""

new_upload_fn = """  // 선명도는 극대화하고 용량은 90% 아끼는 스마트 최적화 (2048px, WebP 품질 0.88)
  async function uploadSmartImage(file) {
    const optimizedFile = await resizeImage(file, 2048, 0.88);
    const fileName = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}.webp`;
    const filePath = `posts/${fileName}`;

    // contentType 명시 및 upsert 옵션 적용 (400 Bad Request 방지)
    const { data, error } = await supabaseClient.storage
      .from('board-images')
      .upload(filePath, optimizedFile, {
        contentType: 'image/webp',
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

if old_upload_fn in code:
    code = code.replace(old_upload_fn, new_upload_fn, 1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("✅ 400 에러 방지 헤더(contentType: 'image/webp') 패치 완료!")
else:
    # 혹시 줄바꿈이나 띄어쓰기 차이가 있을 경우 부분 치환
    target_snippet = ".upload(filePath, optimizedFile);"
    replace_snippet = """.upload(filePath, optimizedFile, {
        contentType: 'image/webp',
        cacheControl: '3600',
        upsert: false
      });"""
    if target_snippet in code:
        code = code.replace(target_snippet, replace_snippet, 1)
        with open(target, "w", encoding="utf-8") as f:
            f.write(code)
        print("✅ 400 에러 방지 헤더(부분 치환) 패치 완료!")
    else:
        print("⚠ 대상 코드를 찾지 못했습니다.")
