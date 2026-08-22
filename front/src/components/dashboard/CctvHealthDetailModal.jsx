import React, { useEffect } from 'react';
import {
  ArrowRight,
  CircleAlert,
  MapPin,
  VideoOff,
  X,
} from 'lucide-react';
import { StatusPill } from './DashboardWidgets';

const STATUS_CONFIG = {
  INACTIVE: {
    label: '동작 중지',
    tone: 'neutral',
    reason: '관리자 설정에 의해 CCTV가 비활성화된 상태입니다.',
    action: '장비 연결 상태를 확인한 뒤 관리자 페이지에서 초기 관제 상태를 정상 작동으로 변경하세요.',
  },
  ERROR: {
    label: '연결 오류',
    tone: 'critical',
    reason: 'CCTV 스트림 연결에 실패한 상태입니다.',
    action: '스트림 URL, 네트워크 연결, 카메라 장비 상태를 확인하세요.',
  },
};

function CctvHealthDetailModal({ cctv, onClose, onOpenMonitoring }) {
  const status = STATUS_CONFIG[cctv?.cctv_status] || {
    label: '확인 필요',
    tone: 'neutral',
    reason: '정상 작동 상태가 아닌 CCTV입니다.',
    action: '관리자 페이지에서 CCTV 상태와 연결 정보를 확인하세요.',
  };

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  if (!cctv) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/70 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cctv-health-detail-title"
        aria-describedby="cctv-health-detail-description"
        style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
        className="my-auto box-border max-h-[calc(100vh-2rem)] shrink-0 overflow-hidden rounded-2xl border border-hairline bg-canvas shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-hairline bg-surface-soft p-5">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-hairline bg-canvas text-ink">
              <VideoOff className="h-4.5 w-4.5" />
            </span>
            <div className="min-w-0">
              <h2 id="cctv-health-detail-title" className="text-heading-sm font-semibold text-ink">
                CCTV 점검 사유
              </h2>
              <p id="cctv-health-detail-description" className="mt-1 text-caption-sm text-mute">
                점검 필요 CCTV의 현재 상태와 확인할 항목입니다.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-hairline bg-canvas text-mute hover:text-ink focus:outline-none focus-visible:outline-none"
            aria-label="CCTV 점검 사유 닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[75vh] space-y-4 overflow-y-auto p-5">
          <section className="rounded-lg border border-hairline bg-surface-soft p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-body-sm font-semibold text-ink truncate">
                  {cctv.cctv_name || `CCTV #${cctv.cctv_no}`}
                </p>
                <p className="mt-1 flex items-center gap-1 text-caption-sm text-mute truncate">
                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                  <span>{cctv.cctv_location || '위치 정보 없음'}</span>
                </p>
              </div>
              <StatusPill tone={status.tone}>{status.label}</StatusPill>
            </div>
          </section>

          <section className="rounded-lg border border-hairline p-4">
            <div className="flex items-start gap-3">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <div>
                <h3 className="text-body-sm font-semibold text-ink">현재 상태</h3>
                <p className="mt-1 text-caption-sm leading-relaxed text-body">{status.reason}</p>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-hairline p-4">
            <h3 className="text-body-sm font-semibold text-ink">확인할 항목</h3>
            <p className="mt-1 text-caption-sm leading-relaxed text-body">{status.action}</p>
          </section>
        </div>

        <footer className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-hairline bg-surface-soft p-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-full border border-hairline bg-canvas px-5 text-caption-sm font-semibold text-ink hover:border-hairline-strong focus:outline-none focus-visible:outline-none"
          >
            닫기
          </button>
          <button
            type="button"
            onClick={() => onOpenMonitoring(cctv)}
            className="inline-flex h-10 items-center gap-1.5 rounded-full bg-primary px-5 text-caption-sm font-semibold text-on-primary hover:bg-ink-deep focus:outline-none focus-visible:outline-none"
          >
            실시간 관제로 이동
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </footer>
      </div>
    </div>
  );
}

export default CctvHealthDetailModal;
