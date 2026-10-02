with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# provider kakao 요청 시 scopes 지정
target = """    const { error } = await supabaseClient.auth.signInWithOAuth({
      provider: 'kakao',
      options: {
        redirectTo: window.location.origin
      }
    });"""

replacement = """    const { error } = await supabaseClient.auth.signInWithOAuth({
      provider: 'kakao',
      options: {
        redirectTo: window.location.origin,
        scopes: 'profile_nickname profile_image'
      }
    });"""

if target in code:
    code = code.replace(target, replacement)
    with open("main.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("✅ 카카오 요청 권한(scopes)을 필수 동의된 닉네임/사진으로 한정했습니다!")
else:
    print("⚠️ 대상 코드를 찾지 못했습니다.")
