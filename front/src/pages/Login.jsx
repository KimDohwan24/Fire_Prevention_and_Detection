import React from 'react';
import { Link } from 'react-router-dom';

const Login = () => {
  return (
    <div className="min-h-screen bg-canvas flex flex-col items-center pt-32 px-4 font-ui">

      {/* Brand / Logo (Horizontal Layout) */}
      <div className="flex flex-row items-center space-x-5 mb-10">
        <div className="text-[48px] leading-none">🔥</div>
        <div className="flex flex-col">
          <h1 className="font-display text-display-lg font-medium text-ink tracking-tight mb-1">
            FireGuard
          </h1>
          <p className="text-body text-body-md">
            지능형 화재 예방 및 탐지 시스템
          </p>
        </div>
      </div>

      {/* Login Form */}
      <div className="w-full max-w-[360px]">
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <div>
            <input
              type="text"
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink focus:ring-[3px] focus:ring-[#3b82f680] transition-all"
              placeholder="아이디"
              required
            />
          </div>
          <div>
            <input
              type="password"
              className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus:border-ink focus:ring-[3px] focus:ring-[#3b82f680] transition-all"
              placeholder="비밀번호"
              required
            />
          </div>

          <button
            type="submit"
            className="w-full h-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep transition-colors mt-2"
          >
            로그인
          </button>
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
