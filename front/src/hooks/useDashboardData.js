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

const PAGE_SIZE = 100;
const HISTORY_DAYS = 30;

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

const toDateParam = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getHistoryParams = () => {
  const dateTo = new Date();
  const dateFrom = new Date(dateTo);
  dateFrom.setDate(dateFrom.getDate() - (HISTORY_DAYS - 1));

  return {
    date_from: toDateParam(dateFrom),
    date_to: toDateParam(dateTo),
    include_test: false,
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

export default function useDashboardData() {
  const storedUser = getCurrentUserFromStorage();
  const [currentUser, setCurrentUser] = useState(storedUser);
  const [data, setData] = useState(EMPTY_DATA);
  const [errors, setErrors] = useState(EMPTY_ERRORS);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const mountedRef = useRef(false);
  const initializedRef = useRef(false);
  const refreshInFlightRef = useRef(false);
  const alertInFlightRef = useRef(false);
  const dataRef = useRef(EMPTY_DATA);
  const userRef = useRef(storedUser);

  const updateData = useCallback((updater) => {
    setData((previous) => {
      const next = typeof updater === 'function' ? updater(previous) : updater;
      dataRef.current = next;
      return next;
    });
  }, []);

  const refresh = useCallback(async ({ silent = false } = {}) => {
    if (refreshInFlightRef.current) return;
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

      updateData(scopeDataForUser(rawData, resolvedUser));
      setErrors({
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
      });
      setLastUpdated(new Date());
      initializedRef.current = true;
      setIsLoading(false);
      setIsRefreshing(false);
    }

    refreshInFlightRef.current = false;
  }, [updateData]);

  const refreshAlerts = useCallback(async () => {
    if (alertInFlightRef.current) return;
    alertInFlightRef.current = true;

    try {
      const alerts = await fetchAllPages(alertApi.list);
      if (mountedRef.current) {
        updateData((previous) => scopeDataForUser(
          { ...previous, alerts },
          userRef.current,
        ));
        setErrors((previous) => ({ ...previous, alerts: '' }));
      }
    } catch (error) {
      if (mountedRef.current) {
        setErrors((previous) => ({
          ...previous,
          alerts: getErrorMessage(error, '실시간 알림을 갱신하지 못했습니다.'),
        }));
      }
    } finally {
      alertInFlightRef.current = false;
    }
  }, [updateData]);

  useEffect(() => {
    mountedRef.current = true;
    refresh();

    const dashboardInterval = window.setInterval(() => refresh({ silent: true }), 30_000);
    const alertInterval = window.setInterval(refreshAlerts, 4_000);

    return () => {
      mountedRef.current = false;
      window.clearInterval(dashboardInterval);
      window.clearInterval(alertInterval);
    };
  }, [refresh, refreshAlerts]);

  return {
    ...data,
    currentUser,
    errors,
    isLoading,
    isRefreshing,
    lastUpdated,
    refresh: () => refresh({ silent: false }),
  };
}
