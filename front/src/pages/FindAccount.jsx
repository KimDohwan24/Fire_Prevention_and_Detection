import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { authApi } from '../api';
import PasswordInput from '../components/PasswordInput';

const FindAccount = () => {
  const [activeTab, setActiveTab] = useState('findId'); // 'findId' | 'findPw'

  // 아이디 찾기 상태
  const [findIdForm, setFindIdForm] = useState({ name: '', email: '' });
  const [findIdResult, setFindIdResult] = useState(null); // { success: boolean, userId?: string, createdAt?: string, message?: string }

  // 비밀번호 찾기 상태
  const [findPwStep, setFindPwStep] = useState(1); // 1: 정보입력, 2: 새 비밀번호 설정, 3: 완료
  const [findPwForm, setFindPwForm] = useState({ userId: '', name: '', email: '' });
  const [newPasswordForm, setNewPasswordForm] = useState({ code: '', password: '', passwordConfirm: '' });
  const [findPwError, setFindPwError] = useState('');
  const [findPwNotice, setFindPwNotice] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 아이디 찾기 제출
  const handleFindIdSubmit = async (e) => {
    e.preventDefault();
    if (!findIdForm.name || !findIdForm.email) return;

    setIsSubmitting(true);
    setFindIdResult(null);
    try {
      const result = await authApi.findId(findIdForm.name.trim(), findIdForm.email.trim());
      setFindIdResult({ success: true, userId: result.user_id });
    } catch (error) {
      setFindIdResult({ success: false, message: error.message || '아이디를 찾지 못했습니다.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  // 비밀번호 찾기 1단계 제출 (회원 정보 확인)
  const handleFindPwSubmit = async (e) => {
    e.preventDefault();
    setFindPwError('');
    setFindPwNotice('');
    if (!findPwForm.userId || !findPwForm.name || !findPwForm.email) return;

    setIsSubmitting(true);
    try {
      const result = await authApi.requestPasswordReset(
        findPwForm.userId.trim(),
        findPwForm.name.trim(),
        findPwForm.email.trim(),
      );
      setFindPwNotice(result.message || '입력한 정보가 일치하면 등록된 연락처로 인증코드를 보냈습니다.');
      setFindPwStep(2);
    } catch (error) {
      setFindPwError(error.message || '인증코드 요청에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 비밀번호 찾기 2단계 제출 (새 비밀번호 설정)
  const handleResetPasswordSubmit = async (e) => {
    e.preventDefault();
    setFindPwError('');

    if (!newPasswordForm.code.trim()) {
      setFindPwError('SMS로 받은 인증코드를 입력해 주세요.');
      return;
    }
    if (newPasswordForm.password.length < 8) {
      setFindPwError('비밀번호는 영문·숫자·특수문자를 포함해 8자 이상이어야 합니다.');
      return;
    }

    if (newPasswordForm.password !== newPasswordForm.passwordConfirm) {
      setFindPwError('비밀번호가 일치하지 않습니다.');
      return;
    }

    setIsSubmitting(true);
    try {
      await authApi.confirmPasswordReset(
        findPwForm.userId.trim(),
        newPasswordForm.code.trim(),
        newPasswordForm.password,
      );
      setFindPwStep(3);
      setNewPasswordForm({ code: '', password: '', passwordConfirm: '' });
    } catch (error) {
      setFindPwError(error.message || '비밀번호 변경에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 탭 변경 시 상태 리셋
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setFindIdResult(null);
    setFindPwStep(1);
    setFindPwError('');
    setFindPwNotice('');
    setNewPasswordForm({ code: '', password: '', passwordConfirm: '' });
  };

  return (
    <div className="min-h-screen bg-canvas flex flex-col items-center pt-24 pb-16 px-4 font-ui relative transition-colors duration-300">
      {/* Brand / Logo */}
      <div className="flex flex-row items-center space-x-5 mb-8">
        <div className="text-[48px] leading-none">🔥</div>
        <div className="flex flex-col">
          <h1 className="font-display text-display-lg font-medium text-ink tracking-tight mb-1">
            FireGuard
          </h1>
          <p className="text-body text-body-md">
            계정 정보 찾기
          </p>
        </div>
      </div>

      {/* Main Container */}
      <div className="w-full max-w-[400px]">
        {/* Tab Buttons (Ollama Pill Style) */}
        <div className="flex p-1 bg-surface-soft rounded-full border border-hairline mb-8">
          <button
            type="button"
            onClick={() => handleTabChange('findId')}
            className={`flex-1 h-[36px] rounded-full text-button-md transition-all duration-200 ${
              activeTab === 'findId'
                ? 'bg-primary text-on-primary font-medium'
                : 'text-body hover:text-ink'
            }`}
          >
            아이디 찾기
          </button>
          <button
            type="button"
            onClick={() => handleTabChange('findPw')}
            className={`flex-1 h-[36px] rounded-full text-button-md transition-all duration-200 ${
              activeTab === 'findPw'
                ? 'bg-primary text-on-primary font-medium'
                : 'text-body hover:text-ink'
            }`}
          >
            비밀번호 찾기
          </button>
        </div>

        {/* Tab 1: 아이디 찾기 */}
        {activeTab === 'findId' && (
          <div>
            {!findIdResult ? (
              <form onSubmit={handleFindIdSubmit} className="space-y-4">
                <p className="text-body-sm text-body mb-2 text-center">
                  가입 시 등록한 이름과 이메일 주소를 입력해 주세요.
                </p>
                <div>
                  <input
                    type="text"
                    value={findIdForm.name}
                    onChange={(e) => setFindIdForm({ ...findIdForm, name: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="이름"
                    onInvalid={(e) => e.target.setCustomValidity('이름을 입력해주세요!')}
                    onInput={(e) => e.target.setCustomValidity('')}
                    required
                  />
                </div>
                <div>
                  <input
                    type="email"
                    value={findIdForm.email}
                    onChange={(e) => setFindIdForm({ ...findIdForm, email: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="이메일 주소 (example@domain.com)"
                    onInvalid={(e) => e.target.setCustomValidity('이메일 주소를 입력해주세요!')}
                    onInput={(e) => e.target.setCustomValidity('')}
                    required
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full h-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep active:scale-[0.98] transition-all duration-200 mt-2"
                >
                  {isSubmitting ? '조회 중...' : '아이디 찾기'}
                </button>
              </form>
            ) : (
              <div className="bg-surface-soft border border-hairline rounded-2xl p-6 text-center space-y-4">
                {findIdResult.success ? (
                  <>
                    <div className="w-12 h-12 bg-canvas border border-hairline rounded-full flex items-center justify-center mx-auto text-2xl">
                      🔍
                    </div>
                    <div>
                      <p className="text-body-sm text-body mb-1">입력하신 정보와 일치하는 아이디입니다.</p>
                      <p className="text-heading-md font-semibold text-ink my-2 tracking-wide">
                        {findIdResult.userId}
                      </p>
                    </div>
                    <div className="pt-2 space-y-2">
                      <button
                        type="button"
                        onClick={() => handleTabChange('findPw')}
                        className="w-full h-[36px] bg-canvas border border-hairline text-ink rounded-full text-button-md hover:border-ink transition-all duration-200"
                      >
                        비밀번호 찾기로 이동
                      </button>
                      <Link
                        to="/"
                        className="block w-full h-[36px] leading-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep transition-all duration-200"
                      >
                        로그인하러 가기
                      </Link>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="w-12 h-12 bg-canvas border border-hairline rounded-full flex items-center justify-center mx-auto text-2xl">
                      ⚠️
                    </div>
                    <p className="text-body-md text-ink font-medium">
                      {findIdResult.message}
                    </p>
                    <button
                      type="button"
                      onClick={() => setFindIdResult(null)}
                      className="w-full h-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep transition-all duration-200 mt-2"
                    >
                      다시 시도하기
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: 비밀번호 찾기 */}
        {activeTab === 'findPw' && (
          <div>
            {/* Step 1: 계정 정보 확인 */}
            {findPwStep === 1 && (
              <form onSubmit={handleFindPwSubmit} className="space-y-4">
                <p className="text-body-sm text-body mb-2 text-center">
                  가입한 아이디, 이름, 이메일 주소를 입력해 주세요.
                </p>
                {findPwError && (
                  <p className="text-body-sm text-red-500 text-center font-medium bg-red-50 py-2 rounded-full border border-red-100">
                    {findPwError}
                  </p>
                )}

                <div>
                  <input
                    type="text"
                    value={findPwForm.userId}
                    onChange={(e) => setFindPwForm({ ...findPwForm, userId: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="아이디"
                    onInvalid={(e) => e.target.setCustomValidity('아이디를 입력해주세요!')}
                    onInput={(e) => e.target.setCustomValidity('')}
                    required
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={findPwForm.name}
                    onChange={(e) => setFindPwForm({ ...findPwForm, name: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="이름"
                    onInvalid={(e) => e.target.setCustomValidity('이름을 입력해주세요!')}
                    onInput={(e) => e.target.setCustomValidity('')}
                    required
                  />
                </div>
                <div>
                  <input
                    type="email"
                    value={findPwForm.email}
                    onChange={(e) => setFindPwForm({ ...findPwForm, email: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="이메일 주소"
                    onInvalid={(e) => e.target.setCustomValidity('이메일 주소를 입력해주세요!')}
                    onInput={(e) => e.target.setCustomValidity('')}
                    required
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full h-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep active:scale-[0.98] transition-all duration-200 mt-2"
                >
                  {isSubmitting ? '요청 중...' : '비밀번호 재설정 요청'}
                </button>
              </form>
            )}

            {/* Step 2: 새 비밀번호 입력 */}
            {findPwStep === 2 && (
              <form onSubmit={handleResetPasswordSubmit} className="space-y-4">
                <div className="text-center mb-4">
                  <p className="text-body-sm text-body">
                    <span className="font-semibold text-ink">{findPwForm.userId}</span> 님의 본인 확인이 완료되었습니다.
                  </p>
                  <p className="text-body-sm text-body">새로 사용할 비밀번호를 입력해 주세요.</p>
                </div>

                {findPwError && (
                  <p className="text-body-sm text-red-500 text-center font-medium bg-red-50 py-2 rounded-full border border-red-100">
                    {findPwError}
                  </p>
                )}

                {findPwNotice && (
                  <p className="text-body-sm text-body text-center font-medium bg-surface-soft py-2 rounded-full border border-hairline">
                    {findPwNotice}
                  </p>
                )}

                <div>
                  <label className="sr-only" htmlFor="reset-code">SMS 인증코드</label>
                  <input
                    id="reset-code"
                    type="text"
                    value={newPasswordForm.code}
                    onChange={(e) => setNewPasswordForm({ ...newPasswordForm, code: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="SMS로 받은 인증코드"
                    autoComplete="one-time-code"
                    required
                  />
                </div>

                <div>
                  <PasswordInput
                    value={newPasswordForm.password}
                    onChange={(e) => setNewPasswordForm({ ...newPasswordForm, password: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="새 비밀번호 (8자 이상)"
                    minLength={8}
                    required
                  />
                </div>
                <div>
                  <PasswordInput
                    value={newPasswordForm.passwordConfirm}
                    onChange={(e) => setNewPasswordForm({ ...newPasswordForm, passwordConfirm: e.target.value })}
                    className="w-full h-[40px] px-4 bg-canvas border border-hairline rounded-full text-body-md text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none focus:border-ink transition-all"
                    placeholder="새 비밀번호 확인"
                    minLength={8}
                    required
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full h-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep active:scale-[0.98] transition-all duration-200 mt-2"
                >
                  {isSubmitting ? '변경 중...' : '비밀번호 변경하기'}
                </button>
              </form>
            )}

            {/* Step 3: 비밀번호 변경 완료 */}
            {findPwStep === 3 && (
              <div className="bg-surface-soft border border-hairline rounded-2xl p-6 text-center space-y-4">
                <div className="w-12 h-12 bg-canvas border border-hairline rounded-full flex items-center justify-center mx-auto text-2xl">
                  ✨
                </div>
                <div>
                  <p className="text-heading-md font-semibold text-ink mb-1">
                    비밀번호가 변경되었습니다!
                  </p>
                  <p className="text-body-sm text-body">
                    새로 설정한 비밀번호로 로그인해 주세요.
                  </p>
                </div>
                <Link
                  to="/"
                  className="block w-full h-[36px] leading-[36px] bg-primary text-on-primary rounded-full text-button-md hover:bg-ink-deep transition-all duration-200 mt-4"
                >
                  로그인하러 가기
                </Link>
              </div>
            )}
          </div>
        )}

        {/* Footer Navigation */}
        <div className="mt-10 flex flex-col items-center space-y-3 text-body-sm">
          <div className="flex items-center space-x-3 text-body">
            <Link to="/" className="hover:text-ink underline decoration-hairline hover:decoration-ink underline-offset-4 transition-colors">
              로그인으로 돌아가기
            </Link>
            <span>•</span>
            <Link to="/signup" className="hover:text-ink underline decoration-hairline hover:decoration-ink underline-offset-4 transition-colors">
              회원가입
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FindAccount;
