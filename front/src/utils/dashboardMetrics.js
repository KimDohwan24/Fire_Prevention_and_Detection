const DAY_MS = 24 * 60 * 60 * 1000;

export const EVENT_CLASS_LABELS = {
  FLAME: '불꽃',
  SMOKE: '연기',
  FLAME_SMOKE: '불꽃·연기',
};

export const EVENT_STATUS_LABELS = {
  CONFIRMED: '화재 확정',
  DISMISSED: '기준 미달',
  FALSE_ALARM: '오탐 취소',
  RESOLVED: '조치 완료',
  CANCEL: '취소',
  CANCELED: '취소',
};

export const ALERT_STATUS_LABELS = {
  SENT: '대응 필요',
  READ: '확인 완료',
  CANCELED: '오탐 취소',
  CANCEL: '오탐 취소',
  NO_RESPONSE: '무응답',
};

export const REPORT_STATUS_LABELS = {
  SENDING: '전송 중',
  DISPATCHED: '출동 접수',
  ACCEPTED: '접수 완료',
  NO_RESPONSE: '승계 처리',
  FAILED: '전송 실패',
};

const getDate = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const toDateKey = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getEventDate = (event) => getDate(
  event.event_first_detected_at || event.event_detected_at,
);

const isTestEvent = (event) => (
  event.event_is_test === true
  || event.event_is_test === 1
  || event.event_is_test === 'true'
);

const isCurrentMonthToDate = (value, now) => {
  const date = getDate(value);
  if (!date) return false;

  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  monthStart.setHours(0, 0, 0, 0);

  const timestamp = date.getTime();
  return timestamp >= monthStart.getTime() && timestamp <= now.getTime();
};

const isWithinDays = (value, days, now) => {
  const date = getDate(value);
  if (!date) return false;
  const difference = now.getTime() - date.getTime();
  return difference >= 0 && difference <= days * DAY_MS;
};

const sortByDateDesc = (items, dateSelector) => [...items].sort((left, right) => {
  const leftTime = getDate(dateSelector(left))?.getTime() || 0;
  const rightTime = getDate(dateSelector(right))?.getTime() || 0;
  return rightTime - leftTime;
});

const averageSecondsBetween = (items, startSelector, endSelector) => {
  const durations = items.flatMap((item) => {
    const startedAt = getDate(startSelector(item));
    const endedAt = getDate(endSelector(item));
    if (!startedAt || !endedAt || endedAt < startedAt) return [];
    return [(endedAt.getTime() - startedAt.getTime()) / 1000];
  });

  if (durations.length === 0) return null;
  return durations.reduce((sum, duration) => sum + duration, 0) / durations.length;
};

export const formatDuration = (seconds) => {
  if (seconds == null || !Number.isFinite(seconds)) return '집계 전';
  if (seconds < 60) return `${Math.round(seconds)}초`;

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return remainingSeconds > 0 ? `${minutes}분 ${remainingSeconds}초` : `${minutes}분`;
};

export const formatDateTime = (value) => {
  const date = getDate(value);
  if (!date) return '-';

  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
};

export const buildEventTrend = (events, days = 7, now = new Date()) => {
  const safeEvents = events.filter((event) => !isTestEvent(event));
  const points = Array.from({ length: days }, (_, index) => {
    const date = new Date(now);
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - (days - index - 1));

    return {
      key: toDateKey(date),
      label: `${date.getMonth() + 1}.${date.getDate()}`,
      FLAME: 0,
      SMOKE: 0,
      FLAME_SMOKE: 0,
      total: 0,
    };
  });
  const pointByDate = new Map(points.map((point) => [point.key, point]));

  safeEvents.forEach((event) => {
    const eventDate = getEventDate(event);
    if (!eventDate) return;
    const point = pointByDate.get(toDateKey(eventDate));
    if (!point) return;

    const eventClass = EVENT_CLASS_LABELS[event.event_class]
      ? event.event_class
      : 'FLAME_SMOKE';
    point[eventClass] += 1;
    point.total += 1;
  });

  return points;
};

export const calculateTrendSummary = (points = []) => {
  const total = points.reduce((sum, point) => sum + (point.total || 0), 0);
  const average = points.length > 0 ? (total / points.length).toFixed(1) : '0.0';
  let peak = { label: '-', count: 0 };

  points.forEach((point) => {
    if (point.total > peak.count) {
      peak = { label: point.label, count: point.total };
    }
  });

  return {
    total,
    average,
    peakLabel: peak.count > 0 ? `${peak.label} (${peak.count}건)` : '발생 없음',
    peakCount: peak.count,
  };
};

export const createDashboardMetrics = ({
  cctvs = [],
  events = [],
  alerts = [],
  reports = [],
  now = new Date(),
}) => {
  const productionEvents = events.filter((event) => !isTestEvent(event));
  const sortedAllEvents = sortByDateDesc(
    events,
    (event) => event.event_first_detected_at || event.event_detected_at,
  );
  const sortedEvents = sortByDateDesc(
    productionEvents,
    (event) => event.event_first_detected_at || event.event_detected_at,
  );
  const sortedAlerts = sortByDateDesc(alerts, (alert) => alert.alert_sent_at);
  const sortedReports = sortByDateDesc(reports, (report) => report.reported_at);
  const recentAlerts = sortedAlerts.filter((alert) => isWithinDays(alert.alert_sent_at, 30, now));
  const recentReports = sortedReports.filter((report) => isWithinDays(report.reported_at, 30, now));

  const activeAlerts = sortedAlerts.filter((alert) => alert.alert_status === 'SENT');
  const noResponseAlerts = sortedAlerts.filter((alert) => alert.alert_status === 'NO_RESPONSE');
  const activeCctvs = cctvs.filter((cctv) => cctv.cctv_status === 'ACTIVE');
  const unhealthyCctvs = cctvs
    .filter((cctv) => cctv.cctv_status !== 'ACTIVE')
    .sort((left, right) => {
      if (left.cctv_status === right.cctv_status) {
        return String(left.cctv_name || '').localeCompare(String(right.cctv_name || ''), 'ko');
      }
      return left.cctv_status === 'ERROR' ? -1 : 1;
    });
  const confirmedThisMonth = sortedEvents.filter((event) => (
    event.event_status === 'CONFIRMED'
    && isCurrentMonthToDate(event.event_first_detected_at || event.event_detected_at, now)
  ));
  const reportsThisMonth = sortedReports.filter((report) => (
    isCurrentMonthToDate(report.reported_at, now)
  ));
  const dispatchedReportsThisMonth = reportsThisMonth.filter((report) => (
    report.report_status === 'DISPATCHED' || report.report_status === 'ACCEPTED'
  ));
  const failedReportsThisMonth = reportsThisMonth.filter((report) => (
    report.report_status === 'FAILED'
  ));

  const alertByEvent = new Map();
  sortedAlerts.forEach((alert) => {
    const key = String(alert.event_no ?? '');
    if (key && !alertByEvent.has(key)) alertByEvent.set(key, alert);
  });

  const reportByEvent = new Map();
  sortedReports.forEach((report) => {
    const key = String(report.event_no ?? '');
    if (key && !reportByEvent.has(key)) reportByEvent.set(key, report);
  });

  const recentEvents = sortedAllEvents.slice(0, 5).map((event) => ({
    ...event,
    alert: alertByEvent.get(String(event.event_no)) || null,
    report: reportByEvent.get(String(event.event_no)) || null,
  }));

  const alertBreakdown = ['SENT', 'READ', 'CANCELED', 'NO_RESPONSE'].map((status) => ({
    status,
    label: ALERT_STATUS_LABELS[status],
    count: recentAlerts.filter((alert) => (
      status === 'CANCELED'
        ? alert.alert_status === 'CANCELED' || alert.alert_status === 'CANCEL'
        : alert.alert_status === status
    )).length,
  }));

  return {
    activeAlerts,
    noResponseAlerts,
    activeCctvs,
    unhealthyCctvs,
    confirmedThisMonth,
    reportsThisMonth,
    dispatchedReportsThisMonth,
    failedReportsThisMonth,
    recentEvents,
    alertBreakdown,
    averageAlertResponseSeconds: averageSecondsBetween(
      recentAlerts,
      (alert) => alert.alert_sent_at,
      (alert) => alert.alert_responded_at,
    ),
    averageReportDispatchSeconds: averageSecondsBetween(
      recentReports,
      (report) => report.reported_at,
      (report) => report.report_dispatched_at || report.report_accepted_at,
    ),
    cctvAvailability: cctvs.length > 0
      ? Math.round((activeCctvs.length / cctvs.length) * 100)
      : 0,
  };
};

export const isRecentDate = (value, days, now = new Date()) => {
  return isWithinDays(value, days, now);
};
