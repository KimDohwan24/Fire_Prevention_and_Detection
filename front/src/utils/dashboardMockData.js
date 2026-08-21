const MINUTES_IN_DAY = 24 * 60;
const MINUTE_MS = 60 * 1000;

const timestampMinutesAgo = (now, minutesAgo) => (
  new Date(now.getTime() - minutesAgo * MINUTE_MS).toISOString()
);

const createCctv = ({
  cctv_no,
  user_no,
  cctv_name,
  cctv_location,
  cctv_status,
  cctv_lat,
  cctv_lng,
}) => ({
  cctv_no,
  user_no,
  cctv_name,
  cctv_location,
  cctv_status,
  cctv_lat,
  cctv_lng,
  cctv_stream_url: '',
  cctv_width: 1920,
  cctv_height: 1080,
  cctv_created_at: '2026-01-15T09:00:00.000Z',
});

const createEvent = ({
  now,
  event_no,
  cctv,
  minutesAgo,
  event_status,
  event_class,
  event_confidence,
}) => ({
  event_no,
  cctv_no: cctv.cctv_no,
  cctv_name: cctv.cctv_name,
  cctv_location: cctv.cctv_location,
  event_status,
  event_class,
  event_first_detected_at: timestampMinutesAgo(now, minutesAgo),
  event_detected_at: timestampMinutesAgo(now, Math.max(minutesAgo - 2, 0)),
  event_confidence,
  event_is_test: false,
  event_detected_frames: event_status === 'CONFIRMED' ? 12 : 5,
  event_threshold_frames: 8,
  event_source_metadata: { source: 'dashboard-demo' },
  thumbnail_url: null,
});

const createAlert = ({
  now,
  alert_no,
  event,
  minutesAgo,
  alert_status,
  respondedMinutesAgo = null,
}) => ({
  alert_no,
  event_no: event.event_no,
  cctv_no: event.cctv_no,
  cctv_name: event.cctv_name,
  cctv_location: event.cctv_location,
  event_status: event.event_status,
  event_class: event.event_class,
  event_confidence: event.event_confidence,
  event_first_detected_at: event.event_first_detected_at,
  event_detected_at: event.event_detected_at,
  event_is_test: false,
  alert_level: alert_status === 'SENT' ? 3 : 2,
  alert_channel: 'PUSH',
  alert_status,
  alert_sent_at: timestampMinutesAgo(now, minutesAgo),
  alert_deadline_at: timestampMinutesAgo(now, Math.max(minutesAgo - 3, 0)),
  alert_responded_at: respondedMinutesAgo == null
    ? null
    : timestampMinutesAgo(now, respondedMinutesAgo),
});

const createReport = ({
  now,
  report_no,
  event,
  report_status,
  reportedMinutesAgo,
  acceptedMinutesAgo = null,
  dispatchedMinutesAgo = null,
  report_error_message = null,
}) => ({
  report_no,
  event_no: event.event_no,
  cctv_no: event.cctv_no,
  report_sequence: 1,
  report_external_id: `DEMO-119-${String(report_no).padStart(4, '0')}`,
  report_trigger_reason: report_status === 'SENDING' ? 'ALERT_ACTIVE' : 'FIRE_CONFIRMED',
  report_status,
  report_address: event.cctv_location,
  report_distance_km: 1.8,
  report_attempt_count: 1,
  reported_at: timestampMinutesAgo(now, reportedMinutesAgo),
  report_accepted_at: acceptedMinutesAgo == null
    ? null
    : timestampMinutesAgo(now, acceptedMinutesAgo),
  report_dispatched_at: dispatchedMinutesAgo == null
    ? null
    : timestampMinutesAgo(now, dispatchedMinutesAgo),
  report_error_message,
});

/**
 * API가 아직 비어 있는 개발 화면에서만 사용하는 대시보드용 샘플 데이터다.
 * user_no는 현재 로그인 사용자에 맞춰 생성해 일반 사용자 범위 필터도 통과한다.
 */
export const createDashboardMockData = (user = {}, now = new Date()) => {
  const userNo = user?.user_no ?? 1;
  const cctvs = [
    createCctv({
      cctv_no: 101,
      user_no: userNo,
      cctv_name: '본관 1층 로비 메인',
      cctv_location: '서울시 종로구 본관 1층 중앙 로비',
      cctv_status: 'ACTIVE',
      cctv_lat: 37.5732,
      cctv_lng: 126.9788,
    }),
    createCctv({
      cctv_no: 102,
      user_no: userNo,
      cctv_name: '본관 3층 전기실',
      cctv_location: '본관 3층 전기실 출입구',
      cctv_status: 'ACTIVE',
      cctv_lat: 37.5741,
      cctv_lng: 126.9796,
    }),
    createCctv({
      cctv_no: 103,
      user_no: userNo,
      cctv_name: 'B동 주차장 입구',
      cctv_location: 'B동 지상 주차장 북문',
      cctv_status: 'ACTIVE',
      cctv_lat: 37.5724,
      cctv_lng: 126.9811,
    }),
    createCctv({
      cctv_no: 104,
      user_no: userNo,
      cctv_name: '창고동 북측 통로',
      cctv_location: '창고동 북측 적재 통로',
      cctv_status: 'ERROR',
      cctv_lat: 37.5752,
      cctv_lng: 126.9774,
    }),
    createCctv({
      cctv_no: 105,
      user_no: userNo,
      cctv_name: '연구동 서쪽 출입구',
      cctv_location: '연구동 1층 서쪽 출입구',
      cctv_status: 'ACTIVE',
      cctv_lat: 37.5718,
      cctv_lng: 126.9798,
    }),
    createCctv({
      cctv_no: 106,
      user_no: userNo,
      cctv_name: '옥외 적재장',
      cctv_location: '옥외 적재장 남측 펜스',
      cctv_status: 'INACTIVE',
      cctv_lat: 37.5709,
      cctv_lng: 126.9818,
    }),
  ];

  const cctvByNo = new Map(cctvs.map((cctv) => [cctv.cctv_no, cctv]));
  const events = [
    createEvent({
      now,
      event_no: 9001,
      cctv: cctvByNo.get(101),
      minutesAgo: 18,
      event_status: 'CONFIRMED',
      event_class: 'FLAME_SMOKE',
      event_confidence: 0.97,
    }),
    createEvent({
      now,
      event_no: 9002,
      cctv: cctvByNo.get(102),
      minutesAgo: 150,
      event_status: 'CONFIRMED',
      event_class: 'SMOKE',
      event_confidence: 0.89,
    }),
    createEvent({
      now,
      event_no: 9003,
      cctv: cctvByNo.get(103),
      minutesAgo: 2 * MINUTES_IN_DAY + 45,
      event_status: 'DISMISSED',
      event_class: 'FLAME',
      event_confidence: 0.62,
    }),
    createEvent({
      now,
      event_no: 9004,
      cctv: cctvByNo.get(104),
      minutesAgo: 5 * MINUTES_IN_DAY + 480,
      event_status: 'CONFIRMED',
      event_class: 'FLAME',
      event_confidence: 0.94,
    }),
    createEvent({
      now,
      event_no: 9005,
      cctv: cctvByNo.get(105),
      minutesAgo: 12 * MINUTES_IN_DAY + 30,
      event_status: 'CONFIRMED',
      event_class: 'FLAME_SMOKE',
      event_confidence: 0.91,
    }),
    createEvent({
      now,
      event_no: 9006,
      cctv: cctvByNo.get(103),
      minutesAgo: 22 * MINUTES_IN_DAY + 90,
      event_status: 'DISMISSED',
      event_class: 'SMOKE',
      event_confidence: 0.54,
    }),
  ];

  const eventByNo = new Map(events.map((event) => [event.event_no, event]));
  const alerts = [
    createAlert({
      now,
      alert_no: 7001,
      event: eventByNo.get(9001),
      minutesAgo: 16,
      alert_status: 'READ',
      respondedMinutesAgo: 10,
    }),
    createAlert({
      now,
      alert_no: 7002,
      event: eventByNo.get(9002),
      minutesAgo: 145,
      alert_status: 'READ',
      respondedMinutesAgo: 130,
    }),
    createAlert({
      now,
      alert_no: 7003,
      event: eventByNo.get(9003),
      minutesAgo: 2 * MINUTES_IN_DAY + 40,
      alert_status: 'CANCELED',
      respondedMinutesAgo: 2 * MINUTES_IN_DAY + 35,
    }),
    createAlert({
      now,
      alert_no: 7004,
      event: eventByNo.get(9004),
      minutesAgo: 5 * MINUTES_IN_DAY + 475,
      alert_status: 'READ',
      respondedMinutesAgo: 5 * MINUTES_IN_DAY + 470,
    }),
    createAlert({
      now,
      alert_no: 7005,
      event: eventByNo.get(9005),
      minutesAgo: 12 * MINUTES_IN_DAY + 25,
      alert_status: 'READ',
      respondedMinutesAgo: 12 * MINUTES_IN_DAY + 20,
    }),
    createAlert({
      now,
      alert_no: 7006,
      event: eventByNo.get(9006),
      minutesAgo: 22 * MINUTES_IN_DAY + 85,
      alert_status: 'CANCELED',
      respondedMinutesAgo: 22 * MINUTES_IN_DAY + 80,
    }),
  ];

  const reports = [
    createReport({
      now,
      report_no: 8001,
      event: eventByNo.get(9001),
      report_status: 'SENDING',
      reportedMinutesAgo: 14,
    }),
    createReport({
      now,
      report_no: 8002,
      event: eventByNo.get(9002),
      report_status: 'ACCEPTED',
      reportedMinutesAgo: 140,
      acceptedMinutesAgo: 132,
      dispatchedMinutesAgo: 135,
    }),
    createReport({
      now,
      report_no: 8003,
      event: eventByNo.get(9004),
      report_status: 'NO_RESPONSE',
      reportedMinutesAgo: 5 * MINUTES_IN_DAY + 470,
    }),
    createReport({
      now,
      report_no: 8004,
      event: eventByNo.get(9005),
      report_status: 'FAILED',
      reportedMinutesAgo: 12 * MINUTES_IN_DAY + 20,
      report_error_message: '119 상황실 응답 지연으로 재시도가 필요합니다.',
    }),
  ];

  return { cctvs, events, alerts, reports };
};
