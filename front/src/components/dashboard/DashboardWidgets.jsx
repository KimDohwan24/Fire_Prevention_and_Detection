import React, { useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
} from 'lucide-react';
import {
  ALERT_STATUS_LABELS,
  EVENT_STATUS_LABELS,
  REPORT_STATUS_LABELS,
  formatDateTime,
} from '../../utils/dashboardMetrics';

const STATUS_STYLES = {
  critical: 'border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-400 font-bold',
  warning: 'border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 font-bold',
  success: 'border-emerald-300 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-400 font-bold',
  neutral: 'border-hairline-strong bg-surface-soft text-charcoal font-semibold',
};

const KPI_TONE_STYLES = {
  neutral: {
    card: 'border-hairline-strong bg-canvas hover:border-ink dark:hover:border-hairline-strong',
    icon: 'border-hairline bg-surface-soft text-ink',
    label: 'text-charcoal font-bold',
    value: 'text-ink',
    unit: 'text-body font-semibold',
    arrow: 'text-mute group-hover:text-ink',
  },
  warning: {
    card: 'border-amber-300 dark:border-amber-700/50 bg-amber-50/50 dark:bg-amber-950/25 hover:border-amber-600 dark:hover:border-amber-400',
    icon: 'border-amber-200 dark:border-amber-700 bg-canvas text-amber-700 dark:text-amber-400',
    label: 'text-amber-900 dark:text-amber-300 font-bold',
    value: 'text-ink',
    unit: 'text-amber-800 dark:text-amber-400 font-semibold',
    arrow: 'text-amber-700 dark:text-amber-400 group-hover:text-ink',
  },
  critical: {
    card: 'border-red-400 dark:border-red-700/50 bg-red-50/50 dark:bg-red-950/25 hover:border-red-600 dark:hover:border-red-400 shadow-xs',
    icon: 'border-red-200 dark:border-red-700 bg-canvas text-red-600 dark:text-red-400',
    label: 'text-red-900 dark:text-red-300 font-bold',
    value: 'text-ink',
    unit: 'text-red-800 dark:text-red-400 font-semibold',
    arrow: 'text-red-700 dark:text-red-400 group-hover:text-ink',
  },
};

const getEventStatusTone = (status) => (
  status === 'CONFIRMED' ? 'critical' : status === 'DISMISSED' ? 'neutral' : 'warning'
);

const getAlertStatusTone = (status) => {
  if (status === 'SENT' || status === 'NO_RESPONSE') return 'critical';
  if (status === 'READ') return 'success';
  return 'neutral';
};

const getReportStatusTone = (status) => {
  if (status === 'FAILED') return 'critical';
  if (status === 'DISPATCHED' || status === 'ACCEPTED') return 'success';
  if (status === 'SENDING' || status === 'NO_RESPONSE') return 'warning';
  return 'neutral';
};

export function Tooltip({ text, children, position = 'top' }) {
  if (!text) return children;

  const positionClass = position === 'top'
    ? 'bottom-full mb-2 left-1/2 -translate-x-1/2'
    : 'top-full mt-2 left-1/2 -translate-x-1/2';

  return (
    <div className="relative group/tooltip inline-flex items-center">
      {children}
      <div
        role="tooltip"
        className={`pointer-events-none absolute ${positionClass} z-40 hidden group-hover/tooltip:block w-60 rounded-lg bg-surface-dark dark:bg-neutral-800 p-2.5 text-xs font-medium leading-relaxed text-white shadow-2xl border border-hairline/30 dark:border-neutral-700 transition-all`}
      >
        {text}
      </div>
    </div>
  );
}

export function StatusPill({ children, tone = 'neutral' }) {
  return (
    <span className={`inline-flex items-center min-h-6 px-2.5 rounded-full border text-caption-sm whitespace-nowrap ${STATUS_STYLES[tone]}`}>
      {children}
    </span>
  );
}

export function DashboardKpiCard({
  icon,
  label,
  value,
  unit,
  subtext,
  tooltip,
  error,
  loading = false,
  onClick,
  tone = 'neutral',
}) {
  const styles = KPI_TONE_STYLES[tone] || KPI_TONE_STYLES.neutral;
  const className = `w-full min-h-[148px] p-4 sm:p-5 rounded-xl border text-left flex flex-col justify-between transition-all focus:outline-none focus-visible:outline-none group ${styles.card} ${onClick ? 'cursor-pointer' : ''}`;

  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className={`w-9 h-9 shrink-0 rounded-full border flex items-center justify-center ${styles.icon}`}>
            {icon}
          </div>
          <p className={`min-w-0 truncate text-body-sm font-bold tracking-tight ${styles.label}`}>
            {label}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {tooltip && (
            <Tooltip text={tooltip}>
              <span className="w-4 h-4 rounded-full border border-hairline-strong bg-surface-soft text-body flex items-center justify-center text-[10px] font-bold font-mono cursor-help hover:text-ink hover:border-ink">
                ?
              </span>
            </Tooltip>
          )}
          {onClick && (
            <span className={`text-caption-sm font-semibold flex items-center gap-0.5 transition-colors ${styles.arrow}`}>
              상세 <ArrowRight className="w-3 h-3" />
            </span>
          )}
        </div>
      </div>

      <div className="mt-3">
        {loading ? (
          <p className="mt-1 text-caption-sm text-body font-medium">집계 중...</p>
        ) : error ? (
          <p className="mt-1 text-caption-sm font-bold text-red-600 dark:text-red-400">집계 실패</p>
        ) : (
          <div className="mt-0.5 flex items-baseline gap-1.5">
            <span className={`font-display text-3xl sm:text-4xl font-bold tracking-tight ${styles.value}`}>
              {value}
            </span>
            {unit && (
              <span className={`text-sm font-semibold ${styles.unit}`}>
                {unit}
              </span>
            )}
          </div>
        )}
        {subtext && !error && !loading && (
          <p className="mt-1 text-caption-sm text-body font-medium truncate">
            {subtext}
          </p>
        )}
      </div>
    </>
  );

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={className}>
        {content}
      </button>
    );
  }

  return <div className={className}>{content}</div>;
}

export function AlertStatusSummary({
  items,
  averageResponse,
  averageDispatch,
  loading,
  error,
}) {
  if (loading) return <SectionMessage>알림 대응 현황을 집계하고 있습니다.</SectionMessage>;
  if (error) return <SectionMessage tone="error">{error}</SectionMessage>;

  const total = items.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="space-y-4">
      {/* 골든타임 2개 하이라이트 박스 */}
      <div className="grid grid-cols-2 gap-2.5">
        <div className="rounded-lg border border-hairline-strong bg-surface-soft p-3 text-center">
          <span className="block text-caption-sm font-semibold text-charcoal">평균 알림 확인</span>
          <p className="mt-0.5 font-display text-xl font-bold text-ink font-mono">{averageResponse}</p>
        </div>
        <div className="rounded-lg border border-hairline-strong bg-surface-soft p-3 text-center">
          <span className="block text-caption-sm font-semibold text-charcoal">평균 119 접수</span>
          <p className="mt-0.5 font-display text-xl font-bold text-ink font-mono">{averageDispatch}</p>
        </div>
      </div>

      {/* 상태별 처리 건수 및 프로그레스 */}
      <div className="space-y-2.5">
        {items.map((item) => {
          const percent = total > 0 ? Math.round((item.count / total) * 100) : 0;
          const isCritical = item.status === 'SENT' || item.status === 'NO_RESPONSE';

          return (
            <div key={item.status} className="rounded-lg border border-hairline bg-surface-soft p-3">
              <div className="mb-1.5 flex items-center justify-between text-caption-sm">
                <span className="font-semibold text-charcoal">{item.label}</span>
                <span className={`font-mono font-bold ${isCritical && item.count > 0 ? 'text-red-600 dark:text-red-400' : 'text-ink'}`}>
                  {item.count}건 {total > 0 && `(${percent}%)`}
                </span>
              </div>
              <div className="h-2 rounded-full bg-canvas border border-hairline overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${isCritical && item.count > 0 ? 'bg-red-600' : 'bg-primary'}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="pt-2 text-center text-caption-sm font-medium text-body">
        최근 30일간 누적 알림 처리 현황
      </div>
    </div>
  );
}

export function RecentEventsTable({
  events = [],
  loading,
  error,
  onOpenEvent,
}) {
  const [filter, setFilter] = useState('ALL');

  if (loading) return <SectionMessage>최근 사건을 불러오고 있습니다.</SectionMessage>;
  if (error) return <SectionMessage tone="error">{error}</SectionMessage>;

  const filteredEvents = events.filter((event) => {
    if (filter === 'ALL') return true;
    if (filter === 'CONFIRMED') return event.event_status === 'CONFIRMED';
    if (filter === 'DISMISSED') return event.event_status === 'DISMISSED';
    return true;
  });

  return (
    <div className="space-y-3.5">
      {/* 상단 퀵 필터 탭 */}
      <div className="flex items-center justify-between gap-3">
        <div className="inline-flex rounded-full border border-hairline bg-surface-soft p-1 text-caption-sm">
          {[
            { key: 'ALL', label: '전체' },
            { key: 'CONFIRMED', label: '화재 확정' },
            { key: 'DISMISSED', label: '기준 미달' },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setFilter(tab.key)}
              className={`h-6.5 px-3.5 rounded-full text-caption-sm font-bold transition-all focus:outline-none focus-visible:outline-none ${
                filter === tab.key
                  ? 'bg-primary text-on-primary shadow-xs'
                  : 'text-body hover:text-ink'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <span className="text-caption-sm font-bold text-body font-mono">
          총 {filteredEvents.length}건
        </span>
      </div>

      {filteredEvents.length === 0 ? (
        <div className="py-12 text-center">
          <CheckCircle2 className="w-7 h-7 mx-auto text-ink" />
          <p className="mt-2 text-caption-sm font-bold text-ink">해당 조건의 사건이 없습니다.</p>
          <p className="mt-0.5 text-caption-sm text-body">새 이벤트가 수신되면 실시간으로 표시됩니다.</p>
        </div>
      ) : (
        <>
          {/* 모바일 카드 뷰 */}
          <div className="space-y-2.5 lg:hidden">
            {filteredEvents.map((event) => {
              const alertStatus = event.alert?.alert_status;
              const reportStatus = event.report?.report_status;

              return (
                <article key={event.event_no} className="rounded-lg border border-hairline bg-canvas p-3.5 shadow-xs">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-mono text-caption-sm font-bold text-body">
                      {formatDateTime(event.event_first_detected_at || event.event_detected_at)}
                    </p>
                    <StatusPill tone={getEventStatusTone(event.event_status)}>
                      {EVENT_STATUS_LABELS[event.event_status] || event.event_status || '확인 중'}
                    </StatusPill>
                  </div>

                  <div className="mt-2">
                    <p className="truncate text-body-sm font-bold text-ink">
                      {event.cctv_name || `CCTV #${event.cctv_no}`}
                    </p>
                    <p className="mt-0.5 truncate text-caption-sm font-medium text-body">
                      {event.cctv_location || '위치 정보 없음'}
                    </p>
                  </div>

                  <div className="mt-3 flex items-center justify-between border-t border-hairline pt-2.5">
                    <div className="flex gap-2">
                      <StatusPill tone={getAlertStatusTone(alertStatus)}>
                        {ALERT_STATUS_LABELS[alertStatus] || '알림 없음'}
                      </StatusPill>
                      <StatusPill tone={getReportStatusTone(reportStatus)}>
                        {REPORT_STATUS_LABELS[reportStatus] || '신고 없음'}
                      </StatusPill>
                    </div>
                    <button
                      type="button"
                      onClick={() => onOpenEvent(event)}
                      className="h-7 px-3 rounded-full border border-hairline-strong text-caption-sm font-bold text-ink hover:border-ink focus:outline-none focus-visible:outline-none"
                    >
                      상세 보기
                    </button>
                  </div>
                </article>
              );
            })}
          </div>

          {/* 데스크톱 테이블 뷰 */}
          <div className="hidden overflow-x-auto lg:block">
            <table className="w-full min-w-[620px] border-collapse text-left text-caption-sm">
              <thead>
                <tr className="border-b border-hairline-strong text-caption-sm font-bold text-charcoal">
                  <th className="pb-2.5 pr-3">감지 시각</th>
                  <th className="pb-2.5 pr-3">CCTV / 위치</th>
                  <th className="pb-2.5 pr-3">감지 결과</th>
                  <th className="pb-2.5 pr-3">알림</th>
                  <th className="pb-2.5 pr-3">119 신고</th>
                  <th className="pb-2.5 text-right">관제</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {filteredEvents.map((event) => {
                  const alertStatus = event.alert?.alert_status;
                  const reportStatus = event.report?.report_status;

                  return (
                    <tr key={event.event_no} className="hover:bg-surface-soft/80 transition-colors">
                      <td className="py-3 pr-3 font-mono font-semibold text-charcoal whitespace-nowrap">
                        {formatDateTime(event.event_first_detected_at || event.event_detected_at)}
                      </td>
                      <td className="py-3 pr-3 max-w-[200px]">
                        <p className="font-bold text-ink truncate">{event.cctv_name || `CCTV #${event.cctv_no}`}</p>
                        <p className="text-caption-sm font-medium text-body truncate">{event.cctv_location || '위치 정보 없음'}</p>
                      </td>
                      <td className="py-3 pr-3 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <StatusPill tone={getEventStatusTone(event.event_status)}>
                            {EVENT_STATUS_LABELS[event.event_status] || event.event_status || '확인 중'}
                          </StatusPill>
                        </div>
                      </td>
                      <td className="py-3 pr-3 whitespace-nowrap">
                        <StatusPill tone={getAlertStatusTone(alertStatus)}>
                          {ALERT_STATUS_LABELS[alertStatus] || '알림 없음'}
                        </StatusPill>
                      </td>
                      <td className="py-3 pr-3 whitespace-nowrap">
                        <StatusPill tone={getReportStatusTone(reportStatus)}>
                          {REPORT_STATUS_LABELS[reportStatus] || '신고 없음'}
                        </StatusPill>
                      </td>
                      <td className="py-3 text-right whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => onOpenEvent(event)}
                          className="h-7 px-3.5 rounded-full border border-hairline-strong bg-canvas text-caption-sm font-bold text-ink hover:border-ink hover:bg-surface-soft transition-colors focus:outline-none focus-visible:outline-none"
                        >
                          상세 보기
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export function SectionMessage({ children, tone = 'neutral' }) {
  const isError = tone === 'error';

  return (
    <div className={`min-h-36 flex flex-col items-center justify-center text-center rounded-lg border ${
      isError ? 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-300' : 'border-hairline bg-surface-soft text-body'
    }`}>
      {isError && <CircleAlert className="w-5 h-5 mb-1.5 text-red-600 dark:text-red-400" />}
      <p className="px-4 text-caption-sm font-bold">{children}</p>
    </div>
  );
}
