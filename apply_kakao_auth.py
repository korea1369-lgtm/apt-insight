with open("main.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Supabase 공식 JS SDK CDN 주입
if "@supabase/supabase-js" not in code:
    code = code.replace(
        '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>',
        '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>\n  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>'
    )

# 2. 상단 네비게이션 우측에 카카오 로그인 / 프로필 표시 영역 주입
auth_nav_html = """
      <div id="authArea" style="display: flex; align-items: center; gap: 10px; margin-left: 12px;">
        <button id="btnKakaoLogin" onclick="loginWithKakao()" style="display: flex; align-items: center; gap: 6px; background: #FEE500; color: #191919; border: none; font-size: 13px; font-weight: 700; padding: 6px 14px; border-radius: 8px; cursor: pointer; transition: transform 0.1s ease;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="#191919"><path d="M12 3C6.477 3 2 6.477 2 10.768c0 2.76 1.848 5.176 4.636 6.536-.205.76-.745 2.753-.855 3.193-.135.545.2.538.42.392.174-.116 2.772-1.884 3.904-2.654.618.087 1.25.133 1.895.133 5.523 0 10-3.477 10-7.768S17.523 3 12 3z"/></svg>
          카카오 로그인
        </button>
        <div id="userProfile" style="display: none; align-items: center; gap: 8px;">
          <img id="userAvatar" src="" style="width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #38bdf8; object-fit: cover;">
          <span id="userName" style="font-size: 13.5px; font-weight: 700; color: #38bdf8;"></span>
          <button onclick="logoutKakao()" style="font-size: 11.5px; font-weight: 600; background: transparent; border: 1px solid #475569; color: #94a3b8; padding: 3px 8px; border-radius: 6px; cursor: pointer;">로그아웃</button>
        </div>
      </div>
    </div>
  </nav>
"""

if 'id="authArea"' not in code:
    code = code.replace("</div>\n  </nav>", auth_nav_html)

# 3. Supabase Auth 브라우저 클라이언트 초기화 및 로그인/로그아웃 JS 스크립트 주입
auth_js_code = """
  // ===== Supabase Auth 소셜 로그인 클라이언트 =====
  const SUPABASE_AUTH_URL = "https://hikwjqgjollisdistbif.supabase.co";
  const SUPABASE_AUTH_KEY = "sb_publishable_eIzC8sNZ6gBe62KixTRm1w_1dE2dNG9";
  const supabaseClient = supabase.createClient(SUPABASE_AUTH_URL, SUPABASE_AUTH_KEY);

  let currentUser = null;

  async function checkAuthSession() {
    const { data: { session } } = await supabaseClient.auth.getSession();
    handleAuthChange(session?.user || null);

    supabaseClient.auth.onAuthStateChange((_event, session) => {
      handleAuthChange(session?.user || null);
    });
  }

  function handleAuthChange(user) {
    currentUser = user;
    const loginBtn = document.getElementById('btnKakaoLogin');
    const profileBox = document.getElementById('userProfile');
    const avatar = document.getElementById('userAvatar');
    const nameLabel = document.getElementById('userName');

    if (user) {
      if (loginBtn) loginBtn.style.display = 'none';
      if (profileBox) profileBox.style.display = 'flex';
      
      const meta = user.user_metadata || {};
      const nick = meta.full_name || meta.name || meta.user_name || '회원';
      const pic = meta.avatar_url || meta.picture || 'https://via.placeholder.com/32';
      
      if (avatar) avatar.src = pic;
      if (nameLabel) nameLabel.innerText = nick;
    } else {
      if (loginBtn) loginBtn.style.display = 'flex';
      if (profileBox) profileBox.style.display = 'none';
    }
  }

  async function loginWithKakao() {
    const { error } = await supabaseClient.auth.signInWithOAuth({
      provider: 'kakao',
      options: {
        redirectTo: window.location.origin
      }
    });
    if (error) alert('카카오 로그인 실패: ' + error.message);
  }

  async function logoutKakao() {
    await supabaseClient.auth.signOut();
    handleAuthChange(null);
  }
"""

if "SUPABASE_AUTH_URL" not in code:
    code = code.replace("window.onload = () => {", auth_js_code + "\n  window.onload = () => {\n    checkAuthSession();")

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("🚀 카카오 로그인 UI & 세션 연동이 main.py에 완벽 적용되었습니다!")
