import { useCallback, useEffect, useRef, useState } from 'react';
import {
  alertApi,
  authApi,
  cctvApi,
  eventApi,
  getCurrentUserFromStorage,
  reportApi,
  setCurrentUserToStorage,
} from '../api';
import { createDashboardMockData } from '../utils/dashboardMockData';

const PAGE_SIZE = 100;
const HISTORY_DAYS = 30;
const LIVE_DATA_REFRESH_INTERVAL_MS = 10_000;
const DASHBOARD_DEMO_ENABLED = import.meta.env.VITE_DASHBOARD_DEMO !== 'false';

const EMPTY_DATA = {
  cctvs: [],
  events: [],
  alerts: [],
  reports: [],
};

const EMPTY_ERRORS = {
  session: '',
  cctvs: '',
  events: '',
  alerts: '',
  reports: '',
};

const getItems = (response) => {
  if (Array.isArray(response)) return response;
  return Array.isArray(response?.items) ? response.items : [];
};

const getErrorMessage = (error, fallback) => error?.message || fallback;

const DASHBOARD_DATA_KEYS = ['cctvs', 'events', 'alerts', 'reports'];

const hasCompleteDashboardData = (dashboardData) => DASHBOARD_DATA_KEYS
  .every((key) => Array.isArray(dashboardData[key]) && dashboardData[key].length > 0);

const scopeDashboardData = (dashboardData, user) => (
  user ? scopeDataForUser(dashboardData, user) : dashboardData
);

const getDemoDashboardData = (user) => {
  const demoData = createDashboardMockData(user);
  const hasUserScope = user?.user_no != null;
  const isAdmin = user?.role === 'admin' || user?.rawRole === 'ADMIN';

  // 로그인 정보가 아직 완성되지 않은 순간에는 샘플 데이터를 먼저 보여준다.
  if (user && !hasUserScope && !isAdmin) return demoData;
  return scopeDashboardData(demoData, user);
};

const toDateParam = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getHistoryParams = () => {
  const dateTo = new Date();
  const rollingDateFrom = new Date(dateTo);
  rollingDateFrom.setDate(rollingDateFrom.getDate() - (HISTORY_DAYS - 1));

  const monthDateFrom = new Date(dateTo.getFullYear(), dateTo.getMonth(), 1);
  const dateFrom = monthDateFrom < rollingDateFrom ? monthDateFrom : rollingDateFrom;

  return {
    date_from: toDateParam(dateFrom),
    date_to: toDateParam(dateTo),
    // 테스트 이벤트도 최근 감지 사건 카드에서 확인할 수 있도록 가져온다.
    // KPI·추이 통계에서의 제외는 dashboardMetrics.js에서 별도로 유지한다.
    include_test: true,
  };
};

const fetchAllPages = async (requestPage, params = {}) => {
  const firstResponse = await requestPage({ ...params, page: 1, size: PAGE_SIZE });
  const firstItems = getItems(firstResponse);
  const totalPages = Number(firstResponse?.total_pages || 1);

  if (!Number.isFinite(totalPages) || totalPages <= 1) return firstItems;

  const remainingResponses = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, index) => (
      requestPage({ ...params, page: index + 2, size: PAGE_SIZE })
    )),
  );

  return remainingResponses.reduce(
    (items, response) => items.concat(getItems(response)),
    firstItems,
  );
};

const normalizeSessionUser = (response, fallback) => {
  const sessionUser = response?.user || response;
  if (!sessionUser?.user_id || sessionUser?.user_no == null) return fallback;

  return {
    id: sessionUser.user_id,
    user_no: sessionUser.user_no,
    name: sessionUser.user_name || fallback?.name || sessionUser.user_id,
    role: sessionUser.user_role === 'ADMIN' ? 'admin' : 'user',
    rawRole: sessionUser.user_role,
    authProvider: fallback?.authProvider || null,
  };
};

const scopeDataForUser = ({ cctvs, events, alerts, reports }, user) => {
  const isAdmin = user?.role === 'admin' || user?.rawRole === 'ADMIN';
  if (isAdmin) return { cctvs, events, alerts, reports };

  const userNo = String(user?.user_no ?? '');
  const scopedCctvs = cctvs.filter((cctv) => String(cctv.user_no ?? '') === userNo);
  const cctvNos = new Set(scopedCctvs.map((cctv) => String(cctv.cctv_no)));
  const scopedEvents = events.filter((event) => cctvNos.has(String(event.cctv_no)));
  const eventNos = new Set(scopedEvents.map((event) => String(event.event_no)));

  const belongsToScope = (item) => {
    if (item.cctv_no != null) return cctvNos.has(String(item.cctv_no));
    return item.event_no != null && eventNos.has(String(item.event_no));
  };

  return {
    cctvs: scopedCctvs,
    events: scopedEvents,
    alerts: alerts.filter(belongsToScope),
    reports: reports.filter(belongsToScope),
  };
};

const resolveDashboardData = (rawData, user, keepDemoData = false) => {
  const scopedData = scopeDashboardData(rawData, user);

  if (DASHBOARD_DEMO_ENABLED && (keepDemoData || !hasCompleteDashboardData(scopedData))) {
    return {
      data: getDemoDashboardData(user),
      isDemoData: true,
    };
  }

  return { data: scopedData, isDemoData: false };
};

export default function useDashboardData() {
  const storedUser = getCurrentUserFromStorage();
  const initialData = DASHBOARD_DEMO_ENABLED
    ? getDemoDashboardData(storedUser)
    : EMPTY_DATA;
  const [currentUser, setCurrentUser] = useState(storedUser);
  const [data, setData] = useState(initialData);
  const [errors, setErrors] = useState(EMPTY_ERRORS);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [isDemoData, setIsDemoData] = useState(DASHBOARD_DEMO_ENABLED);

  const mountedRef = useRef(false);
  const initializedRef = useRef(false);
  const refreshInFlightRef = useRef(false);
  const liveDataInFlightRef = useRef(false);
  const dataRef = useRef(initialData);
  const userRef = useRef(storedUser);
  const demoDataRef = useRef(DASHBOARD_DEMO_ENABLED);

  const updateData = useCallback((updater) => {
    setData((previous) => {
      const next = typeof updater === 'function' ? updater(previous) : updater;
      dataRef.current = next;
      return next;
    });
  }, []);

  const refresh = useCallback(async ({ silent = false } = {}) => {
    if (refreshInFlightRef.current || liveDataInFlightRef.current) return;
    refreshInFlightRef.current = true;

    if (!silent) setIsRefreshing(true);
    if (!initializedRef.current) setIsLoading(true);

    let resolvedUser = userRef.current;
    let sessionError = '';

    try {
      const sessionResponse = await authApi.me();
      resolvedUser = normalizeSessionUser(sessionResponse, resolvedUser);
      if (resolvedUser && mountedRef.current) {
        userRef.current = resolvedUser;
        setCurrentUser(resolvedUser);
        setCurrentUserToStorage(resolvedUser);
      }
    } catch (error) {
      sessionError = getErrorMessage(error, '로그인 사용자 정보를 확인하지 못했습니다.');
    }

    const isAdmin = resolvedUser?.role === 'admin' || resolvedUser?.rawRole === 'ADMIN';
    const cctvFilters = isAdmin || resolvedUser?.user_no == null
      ? {}
      : { user_no: resolvedUser.user_no };
    const historyParams = getHistoryParams();

    const [cctvResult, eventResult, alertResult, reportResult] = await Promise.allSettled([
      cctvApi.list(cctvFilters),
      fetchAllPages(eventApi.list, historyParams),
      fetchAllPages(alertApi.list),
      fetchAllPages(reportApi.list),
    ]);

    if (mountedRef.current) {
      const previous = dataRef.current;
      const rawData = {
        cctvs: cctvResult.status === 'fulfilled' ? getItems(cctvResult.value) : previous.cctvs,
        events: eventResult.status === 'fulfilled' ? eventResult.value : previous.events,
        alerts: alertResult.status === 'fulfilled' ? alertResult.value : previous.alerts,
        reports: reportResult.status === 'fulfilled' ? reportResult.value : previous.reports,
      };

      const hasFreshData = [cctvResult, eventResult, alertResult, reportResult].some((result) => (
        result.status === 'fulfilled' && getItems(result.value).length > 0
      ));
      const resolvedData = resolveDashboardData(
        rawData,
        resolvedUser,
        demoDataRef.current && !hasFreshData,
      );

      updateData(resolvedData.data);
      demoDataRef.current = resolvedData.isDemoData;
      setIsDemoData(resolvedData.isDemoData);

      const nextErrors = {
        session: sessionError,
        cctvs: cctvResult.status === 'rejected'
          ? getErrorMessage(cctvResult.reason, 'CCTV 현황을 불러오지 못했습니다.')
          : '',
        events: eventResult.status === 'rejected'
          ? getErrorMessage(eventResult.reason, '화재 이벤트를 불러오지 못했습니다.')
          : '',
        alerts: alertResult.status === 'rejected'
          ? getErrorMessage(alertResult.reason, '알림 현황을 불러오지 못했습니다.')
          : '',
        reports: reportResult.status === 'rejected'
          ? getErrorMessage(reportResult.reason, '119 신고 이력을 불러오지 못했습니다.')
          : '',
      };
      if (resolvedData.isDemoData) {
        nextErrors.cctvs = '';
        nextErrors.events = '';
        nextErrors.alerts = '';
        nextErrors.reports = '';
      }
      setErrors(nextErrors);
      setLastUpdated(new Date());
      initializedRef.current = true;
      setIsLoading(false);
      setIsRefreshing(false);
    }

    refreshInFlightRef.current = false;
  }, [updateData]);

  const refreshLiveData = useCallback(async () => {
    if (refreshInFlightRef.current || liveDataInFlightRef.current) return;
    liveDataInFlightRef.current = true;

    try {
      const [eventResult, alertResult, reportResult] = await Promise.allSettled([
        fetchAllPages(eventApi.list, getHistoryParams()),
        fetchAllPages(alertApi.list),
        fetchAllPages(reportApi.list),
      ]);

      if (mountedRef.current) {
        const previous = dataRef.current;
        const rawLiveData = {
          cctvs: previous.cctvs,
          events: eventResult.status === 'fulfilled' ? getItems(eventResult.value) : previous.events,
          alerts: alertResult.status === 'fulfilled' ? getItems(alertResult.value) : previous.alerts,
          reports: reportResult.status === 'fulfilled' ? getItems(reportResult.value) : previous.reports,
        };
        const hasFreshLiveData = [eventResult, alertResult, reportResult].some((result) => (
          result.status === 'fulfilled' && getItems(result.value).length > 0
        ));
        const resolvedLiveData = resolveDashboardData(
          rawLiveData,
          userRef.current,
          demoDataRef.current && !hasFreshLiveData,
        );

        updateData(resolvedLiveData.data);
        demoDataRef.current = resolvedLiveData.isDemoData;
        setIsDemoData(resolvedLiveData.isDemoData);
        setErrors((previousErrors) => {
          const nextErrors = {
            ...previousErrors,
            events: eventResult.status === 'rejected'
              ? getErrorMessage(eventResult.reason, 'Failed to refresh fire events.')
              : '',
            alerts: alertResult.status === 'rejected'
              ? getErrorMessage(alertResult.reason, 'Failed to refresh alerts.')
              : '',
            reports: reportResult.status === 'rejected'
              ? getErrorMessage(reportResult.reason, 'Failed to refresh 119 reports.')
              : '',
          };
          if (resolvedLiveData.isDemoData) {
            nextErrors.events = '';
            nextErrors.alerts = '';
            nextErrors.reports = '';
          }
          return nextErrors;
        });
        setLastUpdated(new Date());
      }
    } catch (error) {
      if (mountedRef.current) {
        setErrors((previous) => ({
          ...previous,
          alerts: getErrorMessage(error, '실시간 알림을 갱신하지 못했습니다.'),
        }));
      }
    } finally {
      liveDataInFlightRef.current = false;
    }
  }, [updateData]);

  useEffect(() => {
    mountedRef.current = true;
    refresh();

    const dashboardInterval = window.setInterval(() => refresh({ silent: true }), 30_000);
    const liveDataInterval = window.setInterval(refreshLiveData, LIVE_DATA_REFRESH_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      window.clearInterval(dashboardInterval);
      window.clearInterval(liveDataInterval);
    };
  }, [refresh, refreshLiveData]);

  return {
    ...data,
    currentUser,
    errors,
    isLoading,
    isRefreshing,
    isDemoData,
    lastUpdated,
    refresh: () => refresh({ silent: false }),
  };
}
