import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { authApi, oauthApi, SOCIAL_PROVIDERS } from '../api';

// 브랜드 로고는 외부 자산을 새로 들이지 않으려고 전부 인라인 SVG 로 둔다.
const GoogleMark = () => (
  <svg className="w-4 h-4 shrink-0" viewBox="0 0 18 18" aria-hidden="true">
    <path fill="#4285F4" d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" />
    <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.859-3.048.859-2.344 0-4.328-1.583-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" />
    <path fill="#FBBC05" d="M3.964 10.709A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.333z" />
    <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.346l2.582-2.582C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" />
  </svg>
);

const KakaoMark = () => (
  <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#000000" d="M12 3C6.9 3 3 6.3 3 10.3c0 2.6 1.7 4.9 4.3 6.2l-1 3.7c-.1.4.3.6.6.4l4.4-2.9c.2 0 .5.01.7.01 5.1 0 9-3.3 9-7.4S17.1 3 12 3z" />
  </svg>
);

const NaverMark = () => (
  <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#FFFFFF" d="M14.2 12.4 9.6 5.5H5.5v13h4.3v-6.9l4.6 6.9h4.1v-13h-4.3v6.9z" />
  </svg>
);

// 프로바이더별 겉모습만 여기서 정한다. 어떤 프로바이더가 있는지는 api.js 의
// SOCIAL_PROVIDERS 한 곳에서만 관리한다 — 목록이 두 벌이면 콜백 쪽과 어긋난다.
// 형태(높이·라운드)는 아래 로그인 버튼과 맞추고 색만 브랜드를 따른다.
const SOCIAL_BUTTON_STYLES = {
  google: {
    Mark: GoogleMark,
    className: 'bg-white text-[#1f1f1f] border border-hairline hover:bg-[#f5f5f5]',
  },
  kakao: {
    Mark: KakaoMark,
    className: 'bg-[#FEE500] text-[#191600] hover:bg-[#f0d800]',
  },
  naver: {
    Mark: NaverMark,
    className: 'bg-[#03C75A] text-white hover:bg-[#02b351]',
  },
};

const Login = () => {
  const navigate = useNavigate();
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // 어떤 소셜 버튼이 이동 준비 중인지 — 리다이렉트 전까지 중복 클릭을 막는다.
  const [pendingProvider, setPendingProvider] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);

    try {
      // 백엔드 REST API 로그인 호출 (/api/auth/login -> JWT 토큰 발급 및 localStorage 저장)
      await authApi.login(id.trim(), password);
      navigate('/dashboard');
    } catch (err) {
      console.error('로그인 실패:', err);
      setErrorMsg(err.message || '로그인에 실패했습니다. 아이디와 비밀번호를 확인해주세요.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSocialLogin = async (provider) => {
    setErrorMsg('');
    setPendingProvider(provider);

    try {
      const res = await oauthApi.getAuthorizeUrl(provider);
      if (!res?.authorize_url) {
        throw new Error('소셜 로그인 주소를 받지 못했습니다. 잠시 후 다시 시도해주세요.');
      }
      // 콜백에서 대조할 state 를 먼저 저장한 뒤에 이동한다 — 순서가 바뀌면 저장 전에 창이 떠난다.
      oauthApi.saveState(provider, res.state);
      window.location.href = res.authorize_url;
    } catch (err) {
      console.error('소셜 로그인 시작 실패:', err);
      setErrorMsg(
        err.code === 'OAUTH_NOT_CONFIGURED'
          ? '해당 소셜 로그인이 아직 설정되지 않았습니다. 관리자에게 문의해주세요.'
          : err.message || '소셜 로그인을 시작하지 못했습니다.'
      );
      setPendingProvider('');
    }
  };

  return (
    <div className="min-h-screen bg-canvas flex flex-col items-center pt-32 px-4 font-ui relative transition-colors duration-300">

      {/* Brand / Logo (Horizontal Layout) */}
      <div className="flex flex-row items-center space-x-5 mb-10">
        <div className="text-[48px] leading-none">🔥</div>
        <div className="flex flex-col">
          <h1 className="font-display text-display-lg font-medium text-ink tracking-tight mb-1">
            FireGuard
          </h1>
          <p className="text-body text-body-md">
            화재 예방 및 탐지 시스템
          </p>
        </div>
      </div>

      {/* Login Form */}
      <div className="w-full max-w-[360px]">
        <form className="space-y-4" onSubmit={handleLogin}>
          {errorMsg && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-500 text-xs font-semibold text-center">
              {errorMsg}
            </div>
          )}

          <div>
            <input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value)}
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
              placeholder="아이디"
              onInvalid={(e) => e.target.setCustomValidity('아이디를 꼭 입력해주세요!')}
              onInput={(e) => e.target.setCustomValidity('')}
              required
            />
          </div>
          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
              placeholder="비밀번호"
              onInvalid={(e) => e.target.setCustomValidity('비밀번호를 꼭 입력해주세요!')}
              onInput={(e) => e.target.setCustomValidity('')}
              required
            />
          </div>

          <div className="flex flex-col space-y-2 pt-2">
            <button
              type="submit"
              disabled={isLoading}
              className="w-full h-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep active:scale-[0.98] transition-all duration-200 disabled:opacity-50"
            >
              {isLoading ? '로그인 중...' : '로그인'}
            </button>
          </div>
        </form>

        {/* 소셜 로그인 — 클릭 시 authorize URL 을 받아 프로바이더 동의 화면으로 이동한다. */}
        <div className="mt-6 flex items-center space-x-3">
          <div className="flex-1 h-px bg-hairline" />
          <span className="text-body-sm text-mute">또는</span>
          <div className="flex-1 h-px bg-hairline" />
        </div>

        <div className="mt-4 flex flex-col space-y-2">
          {SOCIAL_PROVIDERS.map(({ id: provider, name }) => {
            const { Mark, className } = SOCIAL_BUTTON_STYLES[provider];
            return (
              <button
                key={provider}
                type="button"
                onClick={() => handleSocialLogin(provider)}
                disabled={isLoading || Boolean(pendingProvider)}
                className={`w-full h-[36px] rounded-full text-button-md flex items-center justify-center space-x-2 active:scale-[0.98] transition-all duration-200 disabled:opacity-50 ${className}`}
              >
                <Mark />
                <span>{pendingProvider === provider ? '이동 중...' : `${name}로 로그인`}</span>
              </button>
            );
          })}
        </div>

        <div className="mt-8 flex flex-col items-center space-y-4 text-body-sm">
          <Link to="/forgot-password" className="text-body hover:text-ink underline decoration-hairline hover:decoration-ink underline-offset-4 transition-colors">
            아이디/비밀번호 찾기
          </Link>
          <div className="flex items-center space-x-2 text-body">
            <span>계정이 없으신가요?</span>
            <Link to="/signup" className="text-ink underline decoration-hairline hover:decoration-ink underline-offset-4 transition-colors">
              회원가입
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
