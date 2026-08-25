import React from 'react';
import { Loader2, Lock, ShieldCheck, X } from 'lucide-react';
import PasswordInput from './PasswordInput';

export default function MyPagePasswordGate({
  password,
  onPasswordChange,
  onSubmit,
  onCancel,
  errorMessage,
  isSubmitting,
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
      <div
        className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="mypage-password-gate-title"
        aria-describedby="mypage-password-gate-description"
      >
        <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
          <h1
            id="mypage-password-gate-title"
            className="text-heading-md font-bold text-ink flex items-center gap-2"
          >
            <ShieldCheck className="w-5 h-5 text-charcoal" />
            <span>마이페이지 보안 확인</span>
          </h1>
          <button
            type="button"
            onClick={onCancel}
            className="p-1 text-mute hover:text-ink rounded-full transition-colors focus:outline-none cursor-pointer"
            aria-label="대시보드로 돌아가기"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col shrink-0">
          <div className="p-6 max-h-[75vh] overflow-y-auto space-y-5">
            <div className="flex items-start gap-3 rounded-xl border border-hairline bg-surface-soft p-4">
              <Lock className="mt-0.5 h-5 w-5 shrink-0 text-body" />
              <p
                id="mypage-password-gate-description"
                className="text-body-sm leading-6 text-body"
              >
                개인정보 보호를 위해 현재 로그인한 계정의 비밀번호를 입력해 주세요.
              </p>
            </div>

            <div>
              <label
                htmlFor="mypage-current-password"
                className="block text-caption-sm font-bold text-ink mb-1"
              >
                현재 비밀번호
              </label>
              <PasswordInput
                id="mypage-current-password"
                value={password}
                onChange={(event) => onPasswordChange(event.target.value)}
                className="block box-border w-full h-11 px-4 bg-canvas border border-hairline-strong rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                placeholder="현재 사용 중인 비밀번호"
                autoComplete="current-password"
                autoFocus
                aria-invalid={Boolean(errorMessage)}
                aria-describedby={errorMessage ? 'mypage-password-gate-error' : undefined}
                disabled={isSubmitting}
                required
              />
              {errorMessage && (
                <p
                  id="mypage-password-gate-error"
                  className="mt-2 text-body-sm font-medium text-red-600"
                  role="alert"
                >
                  {errorMessage}
                </p>
              )}
            </div>
          </div>

          <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-end gap-3 shrink-0">
            <button
              type="button"
              onClick={onCancel}
              className="px-5 h-11 rounded-full text-caption-sm font-bold text-body hover:text-ink transition-colors focus:outline-none cursor-pointer"
              disabled={isSubmitting}
            >
              대시보드로 돌아가기
            </button>
            <button
              type="submit"
              className="flex items-center gap-2 px-6 h-11 bg-primary text-on-primary rounded-full text-caption-sm font-bold hover:bg-ink-deep transition-colors focus:outline-none cursor-pointer shadow-xs disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isSubmitting}
            >
              {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
              <span>{isSubmitting ? '확인 중...' : '확인하고 입장'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
