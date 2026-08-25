import React, { useEffect, useMemo } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Flame,
  Loader2,
  PhoneCall,
  X,
} from 'lucide-react';
import {
  EVENT_CLASS_LABELS,
  EVENT_STATUS_LABELS,
  REPORT_STATUS_LABELS,
  formatDateTime,
} from '../../utils/dashboardMetrics';
import { StatusPill } from './DashboardWidgets';

const MODAL_CONFIG = {
  confirmed: {
    title: '이번 달 화재 확정',
    description: '이번 달 확정된 화재 사건을 최신순으로 확인합니다.',
    emptyTitle: '이번 달 확정된 화재가 없습니다.',
    emptyDescription: '새로운 확정 사건이 발생하면 이곳에 표시됩니다.',
    loadingMessage: '이번 달 화재 확정 내역을 불러오고 있습니다.',
    Icon: Flame,
  },
  reports: {
    title: '이번 달 119 신고',
    description: '이번 달 전송된 119 신고와 접수 상태를 최신순으로 확인합니다.',
    emptyTitle: '이번 달 등록된 119 신고가 없습니다.',
    emptyDescription: '새로운 신고가 전송되면 이곳에 표시됩니다.',
    loadingMessage: '이번 달 119 신고 내역을 불러오고 있습니다.',
    Icon: PhoneCall,
  },
};

const getEventStatusTone = (status) => (
  status === 'CONFIRMED' ? 'critical' : 'neutral'
);

const getReportStatusTone = (status) => {
  if (status === 'FAILED') return 'critical';
  if (status === 'DISPATCHED' || status === 'ACCEPTED') return 'success';
  if (status === 'SENDING' || status === 'NO_RESPONSE') return 'warning';
  return 'neutral';
};

function SummaryMetric({ label, value, tone = 'neutral' }) {
  const toneClass = tone === 'critical' ? 'text-red-600' : 'text-ink';

  return (
    <div className="min-w-0 rounded-lg border border-hairline bg-canvas px-4 py-3">
      <p className="text-[11px] font-medium text-mute">{label}</p>
      <p className={`mt-1 font-display text-heading-md font-semibold ${toneClass}`}>{value}건</p>
    </div>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-lg border border-dashed border-hairline px-5 py-12 text-center">
      <CheckCircle2 className="mx-auto h-8 w-8 text-ink" />
      <p className="mt-3 text-body-sm font-semibold text-ink">{title}</p>
      <p className="mt-1 text-caption-sm text-mute">{description}</p>
    </div>
  );
}

function ConfirmedEventRow({ event, onOpenEvent }) {
  return (
    <button
      type="button"
      onClick={() => onOpenEvent(event)}
      className="group w-full rounded-lg border border-hairline bg-canvas p-4 text-left hover:border-hairline-strong focus:outline-none focus-visible:outline-none"
    >
      <span className="flex items-start justify-between gap-4">
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-body-sm font-semibold text-ink truncate">
              {event.cctv_name || `CCTV #${event.cctv_no || '-'}`}
            </span>
            <StatusPill tone={getEventStatusTone(event.event_status)}>
              {EVENT_STATUS_LABELS[event.event_status] || event.event_status || '화재 확정'}
            </StatusPill>
          </span>
          <span className="mt-1 block text-caption-sm text-mute truncate">
            {event.cctv_location || '위치 정보 없음'}
          </span>
        </span>
        <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-mute" aria-hidden="true" />
      </span>

      <span className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-hairline pt-3 text-caption-sm">
        <span className="font-medium text-body">
          {EVENT_CLASS_LABELS[event.event_class] || event.event_class || '감지 유형 없음'}
        </span>
        <span className="font-mono text-mute">
          {formatDateTime(event.event_first_detected_at || event.event_detected_at)}
        </span>
        <span className="ml-auto text-[11px] font-semibold text-ink">사건 #{event.event_no}</span>
      </span>
    </button>
  );
}

function ReportRow({ report, event, onOpenEvent }) {
  const canOpenEvent = report.event_no != null;
  const content = (
    <>
      <span className="flex items-start justify-between gap-4">
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-body-sm font-semibold text-ink truncate">
              {report.agency_name || '119 관할 기관'}
            </span>
            <StatusPill tone={getReportStatusTone(report.report_status)}>
              {REPORT_STATUS_LABELS[report.report_status] || report.report_status || '상태 없음'}
            </StatusPill>
          </span>
          <span className="mt-1 block text-caption-sm text-mute truncate">
            {report.report_address || event?.cctv_location || '신고 위치 정보 없음'}
          </span>
        </span>
        {canOpenEvent && <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-mute" aria-hidden="true" />}
      </span>

      <span className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-hairline pt-3 text-caption-sm">
        <span className="font-mono text-mute">{formatDateTime(report.reported_at)}</span>
        {Number(report.report_sequence) > 1 && (
          <span className="font-medium text-body">승계 {report.report_sequence}차</span>
        )}
        {report.event_no != null && (
          <span className="ml-auto text-[11px] font-semibold text-ink">사건 #{report.event_no}</span>
        )}
      </span>
    </>
  );

  if (!canOpenEvent) {
    return <div className="w-full rounded-lg border border-hairline bg-canvas p-4 text-left">{content}</div>;
  }

  return (
    <button
      type="button"
      onClick={() => onOpenEvent(event || { event_no: report.event_no, report })}
      className="group w-full rounded-lg border border-hairline bg-canvas p-4 text-left hover:border-hairline-strong focus:outline-none focus-visible:outline-none"
    >
      {content}
    </button>
  );
}

function MonthlyKpiDetailModal({
  type,
  items = [],
  events = [],
  loading = false,
  error = '',
  onClose,
  onOpenEvent,
}) {
  const config = MODAL_CONFIG[type] || MODAL_CONFIG.confirmed;
  const { Icon } = config;
  const isReports = type === 'reports';
  const acceptedCount = isReports
    ? items.filter((item) => item.report_status === 'DISPATCHED' || item.report_status === 'ACCEPTED').length
    : 0;
  const failedCount = isReports
    ? items.filter((item) => item.report_status === 'FAILED').length
    : 0;
  const eventById = useMemo(
    () => new Map(events.map((event) => [String(event.event_no), event])),
    [events],
  );

  useEffect(() => {
    const handleEscape = (keyboardEvent) => {
      if (keyboardEvent.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={(clickEvent) => {
        if (clickEvent.target === clickEvent.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="monthly-kpi-detail-title"
        aria-describedby="monthly-kpi-detail-description"
        style={{ width: '720px', minWidth: '320px', maxWidth: '95vw' }}
        className="max-h-[calc(100vh-2rem)] shrink-0 box-border flex flex-col rounded-lg border border-hairline bg-canvas"
        onClick={(clickEvent) => clickEvent.stopPropagation()}
      >
        <header className="shrink-0 flex items-start justify-between gap-4 rounded-t-lg border-b border-hairline bg-surface-soft p-5">
          <div className="min-w-0 flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-hairline bg-canvas text-ink">
              <Icon className="h-4.5 w-4.5" />
            </span>
            <span className="min-w-0">
              <h2 id="monthly-kpi-detail-title" className="text-heading-sm font-semibold text-ink">
                {config.title}
              </h2>
              <p id="monthly-kpi-detail-description" className="mt-1 text-caption-sm text-mute">
                {config.description}
              </p>
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-hairline bg-canvas text-mute hover:text-ink focus:outline-none focus-visible:outline-none"
            aria-label={`${config.title} 팝업 닫기`}
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[75vh] overflow-y-auto space-y-4 p-5">
          {!loading && !error && (
            isReports ? (
              <section className="grid grid-cols-3 gap-2" aria-label="이번 달 119 신고 요약">
                <SummaryMetric label="전체 신고" value={items.length} />
                <SummaryMetric label="접수 완료" value={acceptedCount} />
                <SummaryMetric label="전송 실패" value={failedCount} tone={failedCount > 0 ? 'critical' : 'neutral'} />
              </section>
            ) : (
              <section className="rounded-lg border border-hairline bg-surface-soft px-5 py-4" aria-label="이번 달 화재 확정 요약">
                <p className="text-caption-sm font-medium text-body">이번 달 확정된 화재</p>
                <div className="mt-1 flex flex-wrap items-end justify-between gap-2">
                  <p className="font-display text-display-lg font-semibold text-ink">{items.length}건</p>
                  <span className="rounded-full border border-hairline bg-canvas px-3 py-1 text-[11px] font-semibold text-body">
                    테스트 이벤트 제외
                  </span>
                </div>
              </section>
            )
          )}

          {loading ? (
            <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-hairline bg-surface-soft text-center text-mute">
              <Loader2 className="mb-2 h-5 w-5 animate-spin" />
              <p className="px-4 text-body-sm font-medium">{config.loadingMessage}</p>
            </div>
          ) : error ? (
            <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-red-200 bg-red-50 text-center text-red-700">
              <CircleAlert className="mb-2 h-5 w-5" />
              <p className="px-4 text-body-sm font-semibold">내역을 불러오지 못했습니다.</p>
              <p className="mt-1 px-4 text-caption-sm">{error}</p>
            </div>
          ) : items.length === 0 ? (
            <EmptyState title={config.emptyTitle} description={config.emptyDescription} />
          ) : (
            <section className="space-y-2" aria-label={`${config.title} 목록`}>
              {items.map((item, index) => (
                isReports ? (
                  <ReportRow
                    key={item.report_no || `${item.event_no}-${item.reported_at}-${index}`}
                    report={item}
                    event={eventById.get(String(item.event_no))}
                    onOpenEvent={onOpenEvent}
                  />
                ) : (
                  <ConfirmedEventRow
                    key={item.event_no || `${item.event_first_detected_at}-${index}`}
                    event={item}
                    onOpenEvent={onOpenEvent}
                  />
                )
              ))}
            </section>
          )}
        </div>

        <footer className="shrink-0 flex justify-end rounded-b-lg border-t border-hairline bg-surface-soft p-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-full bg-primary px-5 text-caption-sm font-semibold text-on-primary focus:outline-none focus-visible:outline-none"
          >
            닫기
          </button>
        </footer>
      </div>
    </div>
  );
}

export default MonthlyKpiDetailModal;
