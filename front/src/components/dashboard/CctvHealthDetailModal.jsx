import React, { useEffect } from 'react';
import {
  CheckCircle2,
  CircleAlert,
  MapPin,
  Video,
  VideoOff,
  X,
} from 'lucide-react';
import { StatusPill } from './DashboardWidgets';

const STATUS_CONFIG = {
  ACTIVE: {
    label: '정상 작동',
    tone: 'success',
    Icon: Video,
    iconClassName: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  },
  ERROR: {
    label: '연결 오류',
    tone: 'critical',
    Icon: VideoOff,
    iconClassName: 'border-red-200 bg-red-50 text-red-700',
  },
  INACTIVE: {
    label: '동작 중지',
    tone: 'neutral',
    Icon: VideoOff,
    iconClassName: 'border-hairline bg-surface-soft text-mute',
  },
};

const STATUS_PRIORITY = {
  ERROR: 0,
  INACTIVE: 1,
  ACTIVE: 2,
};

const DEFAULT_STATUS_CONFIG = {
  label: '확인 필요',
  tone: 'warning',
  Icon: CircleAlert,
  iconClassName: 'border-amber-200 bg-amber-50 text-amber-700',
};

const getStatusConfig = (status) => STATUS_CONFIG[status] || DEFAULT_STATUS_CONFIG;

const compareCctvs = (left, right) => {
  const leftPriority = STATUS_PRIORITY[left.cctv_status] ?? 1;
  const rightPriority = STATUS_PRIORITY[right.cctv_status] ?? 1;

  if (leftPriority !== rightPriority) return leftPriority - rightPriority;

  const nameComparison = String(left.cctv_name || '').localeCompare(
    String(right.cctv_name || ''),
    'ko',
  );
  if (nameComparison !== 0) return nameComparison;

  return Number(left.cctv_no || 0) - Number(right.cctv_no || 0);
};

function CctvHealthDetailModal({
  cctvs = [],
  activeCount,
  availability,
  loading = false,
  error = '',
  onClose,
}) {
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

  const cctvList = Array.isArray(cctvs) ? cctvs : [];
  const totalCount = cctvList.length;
  const computedActiveCount = cctvList.filter((cctv) => cctv.cctv_status === 'ACTIVE').length;
  const resolvedActiveCount = Number.isFinite(activeCount) ? activeCount : computedActiveCount;
  const resolvedAvailability = Number.isFinite(availability)
    ? availability
    : totalCount > 0
      ? Math.round((resolvedActiveCount / totalCount) * 100)
      : 0;
  const unhealthyCount = Math.max(totalCount - resolvedActiveCount, 0);
  const sortedCctvs = [...cctvList].sort(compareCctvs);

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
        className="my-auto box-border flex max-h-[calc(100vh-2rem)] shrink-0 flex-col overflow-hidden rounded-2xl border border-hairline bg-canvas shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-hairline bg-surface-soft p-5">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-hairline bg-canvas text-ink">
              <Video className="h-4.5 w-4.5" />
            </span>
            <div className="min-w-0">
              <h2 id="cctv-health-detail-title" className="text-heading-sm font-semibold text-ink">
                CCTV 가동 현황
              </h2>
              <p id="cctv-health-detail-description" className="mt-1 text-caption-sm text-mute">
                현재 확인 가능한 CCTV 전체 상태입니다.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-hairline bg-canvas text-mute hover:text-ink focus:outline-none focus-visible:outline-none"
            aria-label="CCTV 가동 현황 닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[75vh] space-y-4 overflow-y-auto p-5">
          {loading && (
            <div className="rounded-lg border border-hairline bg-surface-soft px-3 py-3 text-caption-sm text-body">
              CCTV 상태를 확인하고 있습니다.
            </div>
          )}

          {!loading && error && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-caption-sm text-red-700">
              {error}
            </div>
          )}

          {!loading && !error && (
            <>
              <section className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="CCTV 상태 요약">
                <div className="rounded-lg border border-hairline bg-surface-soft p-3">
                  <p className="text-[11px] text-mute">전체</p>
                  <p className="mt-1 text-body-sm font-semibold text-ink">{totalCount}대</p>
                </div>
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-emerald-700">
                  <p className="text-[11px]">정상</p>
                  <p className="mt-1 text-body-sm font-semibold">{resolvedActiveCount}대</p>
                </div>
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-700">
                  <p className="text-[11px]">점검 필요</p>
                  <p className="mt-1 text-body-sm font-semibold">{unhealthyCount}대</p>
                </div>
                <div className="rounded-lg border border-hairline bg-surface-soft p-3">
                  <p className="text-[11px] text-mute">가동률</p>
                  <p className="mt-1 text-body-sm font-semibold text-ink">{resolvedAvailability}%</p>
                </div>
              </section>

              {sortedCctvs.length === 0 ? (
                <div className="rounded-lg border border-hairline bg-surface-soft py-10 text-center">
                  <CheckCircle2 className="mx-auto h-7 w-7 text-ink" />
                  <p className="mt-3 text-body-sm font-semibold text-ink">등록된 CCTV가 없습니다.</p>
                  <p className="mt-1 text-caption-sm text-mute">CCTV를 등록하면 이곳에서 상태를 확인할 수 있습니다.</p>
                </div>
              ) : (
                <section aria-label="CCTV 전체 목록" className="divide-y divide-hairline rounded-lg border border-hairline">
                  {sortedCctvs.map((cctv) => {
                    const status = getStatusConfig(cctv.cctv_status);
                    const StatusIcon = status.Icon;

                    return (
                      <div key={cctv.cctv_no || cctv.cctv_name} className="flex items-center justify-between gap-3 p-3">
                        <div className="flex min-w-0 items-center gap-3">
                          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border ${status.iconClassName}`}>
                            <StatusIcon className="h-4 w-4" />
                          </span>
                          <div className="min-w-0">
                            <p className="truncate text-body-sm font-semibold text-ink">
                              {cctv.cctv_name || `CCTV #${cctv.cctv_no}`}
                            </p>
                            <p className="mt-1 flex min-w-0 items-center gap-1 truncate text-caption-sm text-mute">
                              <MapPin className="h-3.5 w-3.5 shrink-0" />
                              <span className="truncate">{cctv.cctv_location || '위치 정보 없음'}</span>
                            </p>
                          </div>
                        </div>
                        <span className="shrink-0">
                          <StatusPill tone={status.tone}>{status.label}</StatusPill>
                        </span>
                      </div>
                    );
                  })}
                </section>
              )}
            </>
          )}
        </div>

        <footer className="flex shrink-0 justify-end border-t border-hairline bg-surface-soft p-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-full bg-primary px-5 text-caption-sm font-semibold text-on-primary hover:bg-ink-deep focus:outline-none focus-visible:outline-none"
          >
            닫기
          </button>
        </footer>
      </div>
    </div>
  );
}

export default CctvHealthDetailModal;
