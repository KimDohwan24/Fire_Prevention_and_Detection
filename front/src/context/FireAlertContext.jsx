import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import {
  alertApi,
  cctvApi,
  eventApi,
  getAccessToken,
  getCurrentUserFromStorage,
  videoTestApi,
} from '../api';
import { appendLocalActivityLog } from '../utils/activityLog';

const FireAlertContext = createContext(null);

const PUBLIC_PATHS = new Set([
  '/',
  '/login',
  '/signup',
  '/forgot-password',
  '/find-account',
  '/find-id-pw',
]);

const POLL_INTERVAL_MS = 4_000;
const TEST_END_NOTICE = '비상 알림 테스트가 종료되었습니다.';
const TEST_END_NOTICE_TIMEOUT_MS = 5_000;

const getItems = (response) => {
  if (Array.isArray(response)) return response;
  return Array.isArray(response?.items) ? response.items : [];
};

const isTrue = (value) => value === true || value === 1 || value === '1' || value === 'true';

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

const toConfidencePercent = (value) => {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return 0;
  return Math.round((confidence <= 1 ? confidence : confidence / 100) * 100);
};

const toEventConfidence = (value) => {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return null;
  return confidence > 1 ? confidence / 100 : confidence;
};

const getEventKey = (event) => {
  const source = event?.isTest || isTrue(event?.event_is_test) ? 'test' : 'event';
  const id = event?.event_no ?? event?.alert_no ?? event?.job_id ?? 'unknown';
  const status = event?.event_status || event?.severity || 'ACTIVE';
  return `${source}:${id}:${status}`;
};

const isTestEvent = (event) => isTrue(event?.event_is_test) || event?.isTest === true;

const isResolvedEvent = (event, falseAlarmEvents, resolvedEvents) => (
  ['FALSE_ALARM', 'RESOLVED', 'CANCEL'].includes(event?.event_status)
  || event?.alert_status === 'CANCEL'
  || falseAlarmEvents.includes(event?.event_no)
  || resolvedEvents.includes(event?.event_no)
);

const readNumberList = (key) => {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const appendNumberToStorage = (key, values) => {
  const current = readNumberList(key);
  const next = [...current];
  values.filter((value) => value != null).forEach((value) => {
    if (!next.some((stored) => String(stored) === String(value))) next.push(value);
  });
  localStorage.setItem(key, JSON.stringify(next));
};

const normalizeTestEvent = (event) => {
  const metadata = parseMetadata(event?.event_source_metadata);
  const eventStatus = event?.event_status || 'PENDING';
  const isDetecting = eventStatus === 'PENDING';

  return {
    ...event,
    key: getEventKey(event),
    event_no: event?.event_no ?? null,
    alert_no: null,
    cctv_no: event?.cctv_no ?? null,
    cctv_name: event?.cctv_name || `CCTV #${event?.cctv_no ?? '-'}`,
    cctv_location: event?.cctv_location || '관제 구역',
    location: event?.cctv_location || '관제 구역',
    confidence: toConfidencePercent(event?.event_confidence),
    event_confidence: toEventConfidence(event?.event_confidence),
    event_class: event?.event_class || 'FLAME_SMOKE',
    detected_at: event?.event_first_detected_at || event?.event_detected_at || new Date().toISOString(),
    isTest: true,
    event_is_test: true,
    event_status: eventStatus,
    severity: isDetecting ? 'detecting' : eventStatus === 'DISMISSED' ? 'dismissed' : 'confirmed',
    job_id: metadata.job_id || null,
    media_url: event?.thumbnail_url || null,
    first_detection_media_url: event?.thumbnail_url || null,
    operator_decision: metadata.operator_decision || null,
  };
};

const normalizeTestJob = (job) => {
  const phase = job?.phase || 'DETECTING';
  const eventStatus = phase === 'DETECTING'
    ? 'PENDING'
    : phase === 'DISMISSED' ? 'DISMISSED' : 'CONFIRMED';
  const event = {
    event_no: job?.event_no ?? null,
    event_status: eventStatus,
    event_class: job?.event_class || 'FLAME_SMOKE',
    event_confidence: job?.confidence,
    event_is_test: true,
    event_source_metadata: { job_id: job?.job_id },
    cctv_no: job?.cctv_no ?? null,
    cctv_name: job?.cctv_name,
    cctv_location: job?.cctv_location,
    thumbnail_url: job?.first_detection_media_url || job?.media_url || null,
  };

  return {
    ...normalizeTestEvent(event),
    key: `test:${job?.event_no ?? job?.job_id ?? 'unknown'}:${eventStatus}`,
    job_id: job?.job_id || null,
    operator_decision: job?.operator_decision || null,
  };
};

const normalizeRealAlert = (alert, event) => {
  const eventConfidence = event?.event_confidence ?? alert?.event_confidence;
  const eventStatus = event?.event_status || 'CONFIRMED';

  return {
    ...event,
    ...alert,
    key: `event:${alert?.event_no ?? event?.event_no ?? alert?.alert_no ?? 'unknown'}:${eventStatus}`,
    event_no: alert?.event_no ?? event?.event_no ?? null,
    alert_no: alert?.alert_no ?? null,
    cctv_no: alert?.cctv_no ?? event?.cctv_no ?? null,
    cctv_name: alert?.cctv_name || event?.cctv_name || '카메라',
    cctv_location: alert?.cctv_location || event?.cctv_location || '관제 구역',
    location: alert?.cctv_location || event?.cctv_location || '관제 구역',
    confidence: toConfidencePercent(eventConfidence),
    event_confidence: toEventConfidence(eventConfidence),
    event_class: alert?.event_class || event?.event_class || 'FLAME_SMOKE',
    detected_at: event?.event_first_detected_at || alert?.alert_sent_at || new Date().toISOString(),
    event_status: eventStatus,
    severity: eventStatus === 'PENDING' ? 'detecting' : 'confirmed',
    isTest: false,
    event_is_test: false,
    media_url: event?.thumbnail_url || null,
    first_detection_media_url: event?.thumbnail_url || null,
  };
};

const createEventLog = (event) => {
  const isTest = isTestEvent(event);
  const confidence = toConfidencePercent(event?.event_confidence);
  const type = event?.event_status === 'PENDING'
    ? 'detecting'
    : event?.event_status === 'DISMISSED' ? 'false_alarm' : 'fire';

  return {
    id: event?.event_no ?? event?.event_source_metadata?.job_id,
    event_no: event?.event_no,
    isTest,
    event_status: event?.event_status,
    time: event?.event_first_detected_at
      ? String(event.event_first_detected_at).substring(11, 19)
      : '14:00:00',
    message: `${event?.cctv_name || '카메라'} ${event?.event_status === 'PENDING' ? '최초 화염 감지' : event?.event_status === 'DISMISSED' ? '오탐 처리' : '화재 확정'} (${confidence}%)`,
    type,
  };
};

const filterScopedData = (events, alerts, scope) => {
  if (scope?.isAdmin || !scope?.cctvNos) return { events, alerts };

  const scopedEvents = events.filter((event) => scope.cctvNos.has(String(event.cctv_no)));
  const eventNos = new Set(scopedEvents.map((event) => String(event.event_no)));
  const scopedAlerts = alerts.filter((alert) => (
    alert.cctv_no != null
      ? scope.cctvNos.has(String(alert.cctv_no))
      : eventNos.has(String(alert.event_no))
  ));

  return { events: scopedEvents, alerts: scopedAlerts };
};

function FireAlertProvider({ children }) {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [events, setEvents] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [eventLogs, setEventLogs] = useState([]);
  const [activeAlert, setActiveAlert] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [actionNotice, setActionNotice] = useState(null);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [scope, setScope] = useState(null);
  const [localTestAlert, setLocalTestAlert] = useState(null);

  const mountedRef = useRef(false);
  const refreshInFlightRef = useRef(false);
  const dismissedKeysRef = useRef(new Set());
  const testEndNoticeTimerRef = useRef(null);
  const openedQueryEventRef = useRef(null);
  const dataRef = useRef({ events: [], alerts: [] });

  const isProtectedRoute = !PUBLIC_PATHS.has(location.pathname);
  const storedUser = getCurrentUserFromStorage();
  const hasSession = Boolean(getAccessToken());
  const sessionKey = `${hasSession ? 'authenticated' : 'anonymous'}:${storedUser?.user_no ?? ''}`;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => () => {
    if (testEndNoticeTimerRef.current) {
      window.clearTimeout(testEndNoticeTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!isProtectedRoute || !hasSession) {
      setScope(null);
      setEvents([]);
      setAlerts([]);
      setEventLogs([]);
      setActiveAlert(null);
      setLocalTestAlert(null);
      return undefined;
    }

    let cancelled = false;
    const user = getCurrentUserFromStorage();
    const isAdmin = user?.role === 'admin' || user?.rawRole === 'ADMIN' || Number(user?.user_no) === 1;

    cctvApi.list(isAdmin ? {} : { user_no: user?.user_no })
      .then((response) => {
        if (cancelled) return;
        const cctvs = getItems(response);
        setScope({
          isAdmin,
          cctvNos: isAdmin ? null : new Set(cctvs.map((cctv) => String(cctv.cctv_no))),
        });
      })
      .catch(() => {
        if (!cancelled) setScope({ isAdmin, cctvNos: null });
      });

    return () => {
      cancelled = true;
    };
  }, [hasSession, isProtectedRoute, sessionKey]);

  const updateEventLogs = useCallback((nextEvents) => {
    const falseAlarmEvents = readNumberList('falseAlarmEvents');
    const resolvedEvents = readNumberList('resolvedEvents');
    const nextLogs = nextEvents
      .filter((event) => !isResolvedEvent(event, falseAlarmEvents, resolvedEvents))
      .filter((event) => !dismissedKeysRef.current.has(getEventKey(event)))
      .map(createEventLog);

    setEventLogs(nextLogs);
  }, []);

  const selectActiveAlert = useCallback((nextEvents, nextAlerts, nextLocalTestAlert) => {
    const falseAlarmEvents = readNumberList('falseAlarmEvents');
    const resolvedEvents = readNumberList('resolvedEvents');
    const eventByNo = new Map(nextEvents.map((event) => [String(event.event_no), event]));

    const pendingAlert = nextAlerts.find((alert) => (
      alert.alert_status === 'SENT'
      && !falseAlarmEvents.includes(alert.event_no)
      && !falseAlarmEvents.includes(alert.alert_no)
      && !resolvedEvents.includes(alert.event_no)
      && !resolvedEvents.includes(alert.alert_no)
    ));
    const pendingEvent = pendingAlert ? eventByNo.get(String(pendingAlert.event_no)) : null;
    const confirmedEvent = nextEvents.find((event) => (
      !isTestEvent(event)
      && event.event_status === 'CONFIRMED'
      && !isResolvedEvent(event, falseAlarmEvents, resolvedEvents)
    ));
    const persistedTestEvent = nextEvents.find((event) => (
      isTestEvent(event)
      && event.event_status === 'PENDING'
      && !event.event_test_finished_at
    ));

    const candidate = pendingAlert
      ? normalizeRealAlert(pendingAlert, pendingEvent)
      : confirmedEvent
        ? normalizeRealAlert(null, confirmedEvent)
        : nextLocalTestAlert || (persistedTestEvent ? normalizeTestEvent(persistedTestEvent) : null);

    if (candidate && !dismissedKeysRef.current.has(candidate.key)) {
      setActiveAlert(candidate);
    } else {
      setActiveAlert(null);
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!isProtectedRoute || !hasSession || refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    setIsLoading((current) => current || events.length === 0);

    try {
      const [eventResult, alertResult] = await Promise.allSettled([
        eventApi.list({ size: 100, include_test: true }),
        alertApi.list({ size: 100 }),
      ]);
      const nextRawEvents = eventResult.status === 'fulfilled'
        ? getItems(eventResult.value)
        : dataRef.current.events;
      const nextRawAlerts = alertResult.status === 'fulfilled'
        ? getItems(alertResult.value)
        : dataRef.current.alerts;
      const scoped = filterScopedData(nextRawEvents, nextRawAlerts, scope);

      if (!mountedRef.current) return;
      dataRef.current = scoped;
      setEvents(scoped.events);
      setAlerts(scoped.alerts);
      updateEventLogs(scoped.events);
      selectActiveAlert(scoped.events, scoped.alerts, localTestAlert);
    } catch (error) {
      if (mountedRef.current) {
        setActionNotice(error?.message || '화재 감지 정보를 갱신하지 못했습니다.');
      }
    } finally {
      if (mountedRef.current) setIsLoading(false);
      refreshInFlightRef.current = false;
    }
  }, [events.length, hasSession, isProtectedRoute, localTestAlert, scope, selectActiveAlert, updateEventLogs]);

  useEffect(() => {
    if (!isProtectedRoute || !hasSession) return undefined;

    refresh();
    const intervalId = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [hasSession, isProtectedRoute, refresh, sessionKey]);

  useEffect(() => {
    const requestedEventNo = searchParams.get('event_no');
    if (!isProtectedRoute || !requestedEventNo) {
      openedQueryEventRef.current = null;
      return;
    }
    if (openedQueryEventRef.current === requestedEventNo) return;

    openedQueryEventRef.current = requestedEventNo;
    const summary = events.find((event) => String(event.event_no) === String(requestedEventNo));
    setSelectedEvent(summary || { event_no: Number(requestedEventNo) || requestedEventNo });
  }, [events, isProtectedRoute, searchParams]);

  const reportTestJob = useCallback((job) => {
    if (!job) return null;
    const nextAlert = normalizeTestJob(job);
    setLocalTestAlert(nextAlert);
    setActiveAlert(nextAlert);
    setEventLogs((previousLogs) => [
      {
        id: nextAlert.event_no || nextAlert.job_id,
        event_no: nextAlert.event_no,
        job_id: nextAlert.job_id,
        isTest: true,
        event_status: nextAlert.event_status,
        time: new Date().toLocaleTimeString('ko-KR', { hour12: false }),
        message: `${nextAlert.cctv_name} ${nextAlert.event_status === 'PENDING' ? '최초 화염 감지' : nextAlert.event_status === 'DISMISSED' ? '오탐 처리' : '화재 확정'} (${nextAlert.confidence}%)`,
        type: nextAlert.severity === 'detecting' ? 'detecting' : nextAlert.severity === 'dismissed' ? 'false_alarm' : 'fire',
      },
      ...previousLogs.filter((log) => log.event_no !== nextAlert.event_no && log.job_id !== nextAlert.job_id),
    ]);
    return nextAlert;
  }, []);

  const recordTestDecision = useCallback((decision, job) => {
    const nextAlert = reportTestJob(job);
    const currentUser = getCurrentUserFromStorage();
    const isConfirm = decision === 'CONFIRM_FIRE';
    const cctvName = nextAlert?.cctv_name || `CCTV #${job?.cctv_no ?? '-'}`;

    appendLocalActivityLog({
      id: `${job?.event_no || job?.job_id}-${decision}`,
      user_no: currentUser?.user_no,
      activity_type: isConfirm ? 'FIRE_CONFIRMED' : 'FIRE_DISMISSED',
      time: new Date().toISOString(),
      type: isConfirm ? 'fire' : 'false_alarm',
      title: isConfirm ? '영상 테스트 119 신고(테스트)' : '영상 테스트 오탐 처리',
      detail: `${cctvName} - ${isConfirm ? '관제자 119 신고 모의 처리' : '관제자 오탐 처리'}`,
    });
    setActionNotice(isConfirm
      ? `${cctvName} 화재 확정 테스트가 반영되었습니다.`
      : `${cctvName} 오탐 처리 테스트가 반영되었습니다.`);
    return nextAlert;
  }, [reportTestJob]);

  const decideTest = useCallback(async (decision) => {
    if (!activeAlert?.isTest || !activeAlert.job_id || activeAlert.severity !== 'detecting' || isActionLoading) return;
    setIsActionLoading(true);
    setActionNotice(null);
    try {
      const job = await videoTestApi.decide(activeAlert.job_id, decision);
      recordTestDecision(decision, job);
    } catch (error) {
      setActionNotice(error?.message || '테스트 판정을 반영하지 못했습니다.');
    } finally {
      setIsActionLoading(false);
    }
  }, [activeAlert, isActionLoading, recordTestDecision]);

  const respondRealAlert = useCallback(async (action) => {
    if (!activeAlert || activeAlert.isTest || !activeAlert.alert_no || isActionLoading) return;
    setIsActionLoading(true);
    setActionNotice(null);
    try {
      const response = await alertApi.respond(activeAlert.alert_no, action);
      const isConfirm = action === 'READ';
      const currentUser = getCurrentUserFromStorage();
      const eventNo = activeAlert.event_no;

      appendLocalActivityLog({
        id: `${eventNo || activeAlert.alert_no}-${action}`,
        user_no: currentUser?.user_no,
        activity_type: isConfirm ? 'FIRE_CONFIRMED' : 'FALSE_ALARM_CANCELLED',
        time: new Date().toISOString(),
        type: isConfirm ? 'fire' : 'false_alarm',
        title: isConfirm ? '화재 확인 및 119 신고 절차 시작' : '화재 알림 오탐 처리',
        detail: `${activeAlert.cctv_name} - ${isConfirm ? '119 신고 절차 시작' : '관제자 오탐 처리 완료'}`,
      });

      appendNumberToStorage(isConfirm ? 'resolvedEvents' : 'falseAlarmEvents', [eventNo, activeAlert.alert_no]);
      dismissedKeysRef.current.add(activeAlert.key);
      setActiveAlert(null);
      setActionNotice(isConfirm
        ? (response?.alert_status === 'NO_RESPONSE' ? '화재 확인 후 무응답 상태로 전환되었습니다.' : '화재 확인과 119 신고 절차가 시작되었습니다.')
        : '오탐 처리되었습니다.');
      await refresh();
    } catch (error) {
      setActionNotice(error?.message || '감지 조치를 반영하지 못했습니다.');
    } finally {
      setIsActionLoading(false);
    }
  }, [activeAlert, isActionLoading, refresh]);

  const dismissAlert = useCallback(() => {
    if (!activeAlert) return;
    dismissedKeysRef.current.add(activeAlert.key);
    setActiveAlert(null);
    setActionNotice(null);
  }, [activeAlert]);

  const endTestAlert = useCallback(() => {
    if (!activeAlert?.isTest && !localTestAlert?.isTest) return;
    const target = activeAlert || localTestAlert;
    if (target?.key) dismissedKeysRef.current.add(target.key);
    setLocalTestAlert(null);
    setActiveAlert(null);
    setEventLogs((previousLogs) => previousLogs.filter((log) => !log.isTest));
    if (testEndNoticeTimerRef.current) {
      window.clearTimeout(testEndNoticeTimerRef.current);
    }
    setActionNotice(TEST_END_NOTICE);
    testEndNoticeTimerRef.current = window.setTimeout(() => {
      setActionNotice((currentNotice) => (
        currentNotice === TEST_END_NOTICE ? null : currentNotice
      ));
      testEndNoticeTimerRef.current = null;
    }, TEST_END_NOTICE_TIMEOUT_MS);
  }, [activeAlert, localTestAlert]);

  const openEventDetail = useCallback((eventOrNo) => {
    if (eventOrNo && typeof eventOrNo === 'object') {
      const matchingEvent = events.find((event) => (
        eventOrNo.event_no != null
        && String(event.event_no) === String(eventOrNo.event_no)
      ));
      setSelectedEvent(matchingEvent
        ? {
          ...matchingEvent,
          ...eventOrNo,
          event_source_metadata: {
            ...parseMetadata(matchingEvent.event_source_metadata),
            ...parseMetadata(eventOrNo.event_source_metadata),
          },
        }
        : eventOrNo);
      return;
    }
    const summary = events.find((event) => String(event.event_no) === String(eventOrNo));
    setSelectedEvent(summary || { event_no: Number(eventOrNo) || eventOrNo });
  }, [events]);

  const contextValue = useMemo(() => ({
    activeAlert,
    actionNotice,
    alerts,
    decideTest,
    dismissAlert,
    endTestAlert,
    eventLogs,
    events,
    isActionLoading,
    isLoading,
    openEventDetail,
    recordTestDecision,
    refresh,
    reportTestJob,
    respondRealAlert,
    selectedEvent,
    setActionNotice,
    setSelectedEvent,
  }), [
    actionNotice,
    activeAlert,
    alerts,
    decideTest,
    dismissAlert,
    endTestAlert,
    eventLogs,
    events,
    isActionLoading,
    isLoading,
    openEventDetail,
    recordTestDecision,
    refresh,
    reportTestJob,
    respondRealAlert,
    selectedEvent,
  ]);

  return (
    <FireAlertContext.Provider value={contextValue}>
      {children}
    </FireAlertContext.Provider>
  );
}

export function useFireAlert() {
  const context = useContext(FireAlertContext);
  if (!context) throw new Error('useFireAlert must be used inside FireAlertProvider');
  return context;
}

export default FireAlertProvider;
