import React, { useEffect } from 'react';
import { ShieldCheck, X } from 'lucide-react';

// 개인정보처리방침 검토 전 사용하는 회원가입 안내 초안입니다.
const CONSENT_DETAILS = [
  {
    label: '수집 항목',
    content: '아이디, 비밀번호, 이름, 이메일, 전화번호, 주소, 성별, 생년월일',
  },
  {
    label: '수집·이용 목적',
    content: '회원 식별 및 계정 관리, 이메일 인증, 서비스 운영 및 알림 제공',
  },
  {
    label: '보유 및 이용 기간',
    content: '회원 탈퇴 시까지 보유합니다. 단, 관련 법령에 따라 보존이 필요한 경우 해당 기간 동안 보관합니다.',
  },
];

function PrivacyConsentModal({ isOpen, onClose }) {
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      onMouseDown={onClose}
    >
      <section
        className="flex max-h-[90vh] flex-col overflow-hidden rounded-2xl border border-hairline bg-canvas"
        style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="privacy-consent-modal-title"
        aria-describedby="privacy-consent-modal-description"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-hairline bg-canvas px-6 py-4">
          <h2
            id="privacy-consent-modal-title"
            className="flex items-center gap-2 text-heading-md font-bold text-ink"
          >
            <ShieldCheck className="h-5 w-5 text-charcoal" aria-hidden="true" />
            개인정보 수집·이용 동의
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-mute transition-colors hover:text-ink focus:outline-none focus-visible:outline-none"
            aria-label="개인정보 수집·이용 동의 상세 닫기"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div
          id="privacy-consent-modal-description"
          className="max-h-[75vh] space-y-4 overflow-y-auto px-6 py-6"
        >
          <p className="text-body-sm leading-6 text-body">
            FireGuard 회원가입을 위해 아래와 같이 개인정보를 수집·이용합니다.
          </p>

          <div className="space-y-3">
            {CONSENT_DETAILS.map((detail) => (
              <div key={detail.label} className="rounded-xl border border-hairline bg-surface-soft p-4">
                <h3 className="text-body-sm-strong text-ink">{detail.label}</h3>
                <p className="mt-1 text-body-sm leading-6 text-body">{detail.content}</p>
              </div>
            ))}
          </div>

          <p className="text-caption-sm leading-5 text-mute">
            위 내용은 현재 회원가입 화면을 기준으로 작성된 안내 초안이며, 운영 전 최종 정책 검토가 필요합니다.
          </p>
        </div>

        <div className="flex shrink-0 justify-end border-t border-hairline bg-surface-soft px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="h-11 rounded-full bg-primary px-6 text-caption-sm font-bold text-on-primary transition-colors hover:bg-ink-deep focus:outline-none focus-visible:outline-none"
          >
            확인
          </button>
        </div>
      </section>
    </div>
  );
}

export default PrivacyConsentModal;
