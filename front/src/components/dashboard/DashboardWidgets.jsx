import React from 'react';
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
} from 'lucide-react';
import {
  ALERT_STATUS_LABELS,
  EVENT_CLASS_LABELS,
  EVENT_STATUS_LABELS,
  REPORT_STATUS_LABELS,
  formatDateTime,
} from '../../utils/dashboardMetrics';

const STATUS_STYLES = {
  critical: 'border-red-500 bg-canvas text-red-700 dark:border-red-400/40 dark:bg-red-950/30 dark:text-red-200',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  neutral: 'border-hairline bg-surface-soft text-body',
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

export function StatusPill({ children, tone = 'neutral' }) {
  return (
    <span className={`inline-flex items-center min-h-6 px-2.5 rounded-full border text-[11px] font-semibold whitespace-nowrap ${STATUS_STYLES[tone]}`}>
      {children}
    </span>
  );
}

export function DashboardKpiCard({
  icon,
  label,
  value,
  helper,
  detail,
  error,
  loading = false,
  onClick,
  critical = false,
}) {
  const className = `w-full min-h-[172px] p-5 rounded-lg border text-left flex flex-col justify-between focus:outline-none focus-visible:outline-none ${
    critical
      ? 'border-red-500 bg-canvas dark:border-red-400/40 dark:bg-red-950/30'
      : 'border-hairline bg-canvas'
  } ${onClick ? (critical ? 'cursor-pointer hover:border-red-600 dark:hover:border-red-300' : 'cursor-pointer hover:border-hairline-strong') : ''}`;

  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className={`w-9 h-9 rounded-full border flex items-center justify-center ${
          critical ? 'border-red-200 bg-canvas text-red-600' : 'border-hairline bg-surface-soft text-ink'
        }`}>
          {icon}
        </div>
        {onClick && (
          <ArrowRight
            className={`w-4 h-4 ${critical ? 'text-mute dark:text-red-200' : 'text-mute'}`}
            aria-hidden="true"
          />
        )}
      </div>

      <div className="mt-5">
        <p className={`text-caption-sm font-semibold ${critical ? 'text-body dark:text-red-100' : 'text-body'}`}>
          {label}
        </p>
        {loading ? (
          <p className={`mt-2 text-body-sm ${critical ? 'text-mute dark:text-red-200' : 'text-mute'}`}>
            집계 중...
          </p>
        ) : error ? (
          <p className="mt-2 text-body-sm font-semibold text-red-600 dark:text-red-200">집계 실패</p>
        ) : (
          <p className={`mt-1 font-display text-display-lg font-semibold tracking-tight ${critical ? 'text-ink dark:text-red-50' : 'text-ink'}`}>
            {value}
          </p>
        )}
        <p className={`mt-1 text-caption-sm ${error ? 'text-red-600 dark:text-red-200' : critical ? 'text-mute dark:text-red-200' : 'text-mute'}`}>
          {error || helper}
        </p>
        {detail && !error && (
          <p className={`mt-2 text-[11px] font-medium ${critical ? 'text-body dark:text-red-100' : 'text-body'}`}>
            {detail}
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

export function EventTrendChart({ points, loading, error }) {
  if (loading) {
    return <SectionMessage>감지 추이를 집계하고 있습니다.</SectionMessage>;
  }

  if (error) {
    return <SectionMessage tone="error">{error}</SectionMessage>;
  }

  const maxTotal = Math.max(1, ...points.map((point) => point.total));
  const labelInterval = points.length > 10 ? 5 : 1;

  return (
    <div>
      <div className="flex items-center gap-4 text-[11px] text-body mb-6" aria-label="감지 유형 범례">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-red-600" />불꽃</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-500" />연기</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-ink" />불꽃·연기</span>
      </div>

      <div className="h-56 flex items-end gap-1.5 sm:gap-2 border-b border-hairline" role="img" aria-label="기간별 화재 감지 이벤트 막대 차트">
        {points.map((point, index) => {
          const barHeight = point.total > 0 ? Math.max((point.total / maxTotal) * 100, 7) : 2;
          const showLabel = index % labelInterval === 0 || index === points.length - 1;

          return (
            <div key={point.key} className="h-full min-w-0 flex-1 flex flex-col items-center justify-end">
              <span className="text-[10px] font-mono text-mute mb-1 h-4">
                {point.total > 0 ? point.total : ''}
              </span>
              <div
                className="w-full max-w-7 flex flex-col-reverse rounded-t-sm overflow-hidden bg-surface-soft"
                style={{ height: `${barHeight}%` }}
                title={`${point.label}: 총 ${point.total}건`}
              >
                {point.total === 0 ? (
                  <span className="block h-full bg-hairline" />
                ) : (
                  <>
                    <span
                      className="block bg-red-600"
                      style={{ flex: point.FLAME }}
                      title={`불꽃 ${point.FLAME}건`}
                    />
                    <span
                      className="block bg-amber-500"
                      style={{ flex: point.SMOKE }}
                      title={`연기 ${point.SMOKE}건`}
                    />
                    <span
                      className="block bg-ink"
                      style={{ flex: point.FLAME_SMOKE }}
                      title={`불꽃·연기 ${point.FLAME_SMOKE}건`}
                    />
                  </>
                )}
              </div>
              <span className="mt-2 h-4 text-[10px] text-mute whitespace-nowrap">
                {showLabel ? point.label : ''}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function AlertStatusSummary({ items, averageResponse, averageDispatch, loading, error }) {
  if (loading) return <SectionMessage>알림 대응 현황을 집계하고 있습니다.</SectionMessage>;
  if (error) return <SectionMessage tone="error">{error}</SectionMessage>;

  const total = items.reduce((sum, item) => sum + item.count, 0);
  const maxCount = Math.max(1, ...items.map((item) => item.count));

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.status}>
            <div className="mb-1.5 flex items-center justify-between text-caption-sm">
              <span className="font-medium text-body">{item.label}</span>
              <span className="font-mono text-ink">{item.count}건</span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-soft overflow-hidden">
              <div
                className={`h-full rounded-full ${item.status === 'SENT' || item.status === 'NO_RESPONSE' ? 'bg-red-600' : 'bg-ink'}`}
                style={{ width: `${item.count === 0 ? 0 : Math.max((item.count / maxCount) * 100, 6)}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {total === 0 && <p className="text-caption-sm text-mute">최근 알림 기록이 없습니다.</p>}

      <div className="grid grid-cols-2 gap-3 pt-4 border-t border-hairline">
        <div>
          <p className="text-[11px] text-mute">평균 알림 대응</p>
          <p className="mt-1 text-body-sm font-semibold text-ink">{averageResponse}</p>
        </div>
        <div>
          <p className="text-[11px] text-mute">평균 119 접수</p>
          <p className="mt-1 text-body-sm font-semibold text-ink">{averageDispatch}</p>
        </div>
      </div>
    </div>
  );
}

export function RecentEventsTable({ events, loading, error, onOpenEvent }) {
  if (loading) return <SectionMessage>최근 사건을 불러오고 있습니다.</SectionMessage>;
  if (error) return <SectionMessage tone="error">{error}</SectionMessage>;

  if (events.length === 0) {
    return (
      <div className="py-12 text-center">
        <CheckCircle2 className="w-8 h-8 mx-auto text-ink" />
        <p className="mt-3 text-body-sm font-semibold text-ink">최근 감지된 사건이 없습니다.</p>
        <p className="mt-1 text-caption-sm text-mute">새 이벤트가 수신되면 이곳에 최신순으로 표시됩니다.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] border-collapse">
        <thead>
          <tr className="border-b border-hairline text-left text-[11px] font-semibold text-mute">
            <th className="pb-3 pr-4">감지 시각</th>
            <th className="pb-3 pr-4">CCTV / 위치</th>
            <th className="pb-3 pr-4">감지 결과</th>
            <th className="pb-3 pr-4">알림 상태</th>
            <th className="pb-3 pr-4">119 신고</th>
            <th className="pb-3 text-right">관제</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {events.map((event) => {
            const confidence = Number(event.event_confidence);
            const alertStatus = event.alert?.alert_status;
            const reportStatus = event.report?.report_status;

            return (
              <tr key={event.event_no} className="text-caption-sm">
                <td className="py-4 pr-4 font-mono text-body whitespace-nowrap">
                  {formatDateTime(event.event_first_detected_at || event.event_detected_at)}
                </td>
                <td className="py-4 pr-4 max-w-[230px]">
                  <p className="font-semibold text-ink truncate">{event.cctv_name || `CCTV #${event.cctv_no}`}</p>
                  <p className="mt-0.5 text-mute truncate">{event.cctv_location || '위치 정보 없음'}</p>
                </td>
                <td className="py-4 pr-4">
                  <div className="flex items-center gap-2">
                    <StatusPill tone={getEventStatusTone(event.event_status)}>
                      {EVENT_STATUS_LABELS[event.event_status] || event.event_status || '확인 중'}
                    </StatusPill>
                    {event.event_is_test && (
                      <StatusPill tone="warning">테스트</StatusPill>
                    )}
                    <span className="text-body whitespace-nowrap">
                      {EVENT_CLASS_LABELS[event.event_class] || event.event_class || '-'}
                      {Number.isFinite(confidence) ? ` · ${Math.round(confidence * 100)}%` : ''}
                    </span>
                  </div>
                </td>
                <td className="py-4 pr-4">
                  <StatusPill tone={getAlertStatusTone(alertStatus)}>
                    {ALERT_STATUS_LABELS[alertStatus] || '알림 없음'}
                  </StatusPill>
                </td>
                <td className="py-4 pr-4">
                  <StatusPill tone={getReportStatusTone(reportStatus)}>
                    {REPORT_STATUS_LABELS[reportStatus] || '신고 없음'}
                  </StatusPill>
                </td>
                <td className="py-4 text-right">
                  <button
                    type="button"
                    onClick={() => onOpenEvent(event)}
                    className="inline-flex items-center gap-1 h-8 px-3 rounded-full border border-hairline text-[11px] font-semibold text-ink hover:border-hairline-strong focus:outline-none focus-visible:outline-none"
                  >
                    상세 보기 <ArrowRight className="w-3 h-3" />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SectionMessage({ children, tone = 'neutral' }) {
  const isError = tone === 'error';

  return (
    <div className={`min-h-40 flex flex-col items-center justify-center text-center rounded-lg border ${
      isError ? 'border-red-200 bg-red-50 text-red-700' : 'border-hairline bg-surface-soft text-mute'
    }`}>
      {isError && <CircleAlert className="w-5 h-5 mb-2" />}
      <p className="px-4 text-body-sm font-medium">{children}</p>
    </div>
  );
}
