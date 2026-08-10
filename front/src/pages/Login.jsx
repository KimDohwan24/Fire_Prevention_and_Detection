import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { authApi } from '../api';

const Login = () => {
  const navigate = useNavigate();
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

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

          <div className="text-xs text-mute text-center">
            💡 테스트 정보: 관리자 계정 <code className="bg-surface-soft px-1.5 py-0.5 rounded text-ink font-semibold">admin / 1234</code>
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
