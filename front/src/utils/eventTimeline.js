const parseMetadata = (value) => {
  if (!value) return {};
  if (typeof value === 'object') return value;

  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const isTestEvent = (event) => (
  event?.isTest === true
  || event?.event_is_test === true
  || event?.event_is_test === 1
  || event?.event_is_test === '1'
  || event?.event_is_test === 'true'
);

const isSameTime = (left, right) => (
  left && right && new Date(left).getTime() === new Date(right).getTime()
);

const addItem = (items, timestamp, label, tone = 'neutral') => {
  if (!timestamp || !label) return;
  items.push({
    id: `${timestamp}-${label}`,
    timestamp,
    label,
    tone,
  });
};

const sortItems = (items) => [...items]
  .sort((left, right) => {
    const leftTime = new Date(left.timestamp).getTime();
    const rightTime = new Date(right.timestamp).getTime();
    return (Number.isNaN(leftTime) ? 0 : leftTime) - (Number.isNaN(rightTime) ? 0 : rightTime);
  })
  .filter((item, index, all) => (
    index === all.findIndex((candidate) => (
      candidate.timestamp === item.timestamp && candidate.label === item.label
    ))
  ));

export const getEventStage = (event) => {
  if (event?.event_status === 'CONFIRMED') return 'CONFIRMED';
  if (event?.event_status === 'DISMISSED') return 'DISMISSED';
  return 'DETECTING';
};

export const getEventStatusLabel = (event) => {
  const stage = getEventStage(event);
  if (stage === 'CONFIRMED') return '화재 확정';
  if (stage === 'DISMISSED') {
    const metadata = parseMetadata(event?.event_source_metadata);
    return isTestEvent(event)
      || metadata.operator_decision === 'DISMISS'
      || event?.operator_decision === 'DISMISS'
      ? '오탐 처리'
      : '기준 미달';
  }
  return '관측 중';
};

export const buildDetectionTimeline = (event) => {
  const timeline = [];
  const firstDetectedAt = event?.event_first_detected_at || event?.event_detected_at;
  const stage = getEventStage(event);

  addItem(timeline, firstDetectedAt, 'AI 모듈 · 최초 화염/연기 패턴 감지', 'detecting');

  if (
    event?.event_detected_at
    && !isSameTime(event.event_detected_at, firstDetectedAt)
    && stage === 'CONFIRMED'
  ) {
    addItem(timeline, event.event_detected_at, 'AI 모듈 · 화재 판정 기준 충족', 'confirmed');
  }

  if (
    event?.event_test_finished_at
    && !isSameTime(event.event_test_finished_at, event.event_detected_at)
    && stage !== 'DETECTING'
  ) {
    addItem(timeline, event.event_test_finished_at, 'AI 영상 분석 종료', 'neutral');
  }

  return sortItems(timeline);
};

export const buildSituationActions = (event) => {
  const actions = [];
  const metadata = parseMetadata(event?.event_source_metadata);
  const testEvent = isTestEvent(event);
  const operatorDecision = metadata.operator_decision || event?.operator_decision;
  const operatorDecidedAt = metadata.operator_decided_at || event?.operator_decided_at;

  if (operatorDecision) {
    const confirmed = operatorDecision === 'CONFIRM_FIRE';
    addItem(
      actions,
      operatorDecidedAt || event?.event_detected_at || event?.event_first_detected_at,
      confirmed
        ? (testEvent ? '관제자 화재 확정 · 119 신고 모의 처리' : '관제자 화재 확인 · 119 신고 절차 시작')
        : (testEvent ? '관제자 오탐 처리 · 영상 테스트' : '관제자 오탐 처리'),
      confirmed ? 'confirmed' : 'dismissed',
    );
  }

  if (!testEvent && !operatorDecision) {
    (Array.isArray(event?.alerts) ? event.alerts : []).forEach((alert) => {
      if (!alert?.alert_responded_at) return;

      const isConfirmed = alert.alert_status === 'READ';
      const isDismissed = alert.alert_status === 'CANCEL' || alert.alert_status === 'CANCELED';
      if (!isConfirmed && !isDismissed) return;

      addItem(
        actions,
        alert.alert_responded_at,
        isConfirmed ? '관제자 화재 확인 · 119 신고 절차 시작' : '관제자 오탐 처리',
        isConfirmed ? 'confirmed' : 'dismissed',
      );
    });

    const hasConfirmedAction = actions.some((action) => action.tone === 'confirmed');
    (Array.isArray(event?.reports) ? event.reports : []).forEach((report) => {
      if (report?.reported_at && !hasConfirmedAction) {
        addItem(actions, report.reported_at, '119 신고 절차 시작', 'confirmed');
      }
      if (report?.report_accepted_at) {
        addItem(actions, report.report_accepted_at, '119 신고 접수 확인', 'confirmed');
      }
      if (report?.report_dispatched_at) {
        addItem(actions, report.report_dispatched_at, '119 출동 요청 전달', 'confirmed');
      }
    });
  }

  return sortItems(actions);
};
