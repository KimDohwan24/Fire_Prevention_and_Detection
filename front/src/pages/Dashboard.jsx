import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart3,
  Bell,
  Flame,
  LayoutDashboard,
  MapPin,
  PhoneCall,
  RefreshCw,
  Video,
} from 'lucide-react';
import { authApi } from '../api';
import AppHeader from '../components/AppHeader';
import CctvHealthDetailModal from '../components/dashboard/CctvHealthDetailModal';
import EventDetailModal from '../components/dashboard/EventDetailModal';
import EventTrendModal from '../components/dashboard/EventTrendModal';
import MonthlyKpiDetailModal from '../components/dashboard/MonthlyKpiDetailModal';
import {
  AlertStatusSummary,
  DashboardKpiCard,
  RecentEventsTable,
} from '../components/dashboard/DashboardWidgets';
import useDashboardData from '../hooks/useDashboardData';
import { useFireAlert } from '../context/FireAlertContext';
import {
  createDashboardMetrics,
  formatDateTime,
  formatDuration,
} from '../utils/dashboardMetrics';

const createMonitoringPath = (params = {}) => {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== '' && value != null),
  ).toString();
  return query ? `/monitoring?${query}` : '/monitoring';
};

function Dashboard() {
  const navigate = useNavigate();
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [isCctvStatusModalOpen, setIsCctvStatusModalOpen] = useState(false);
  const [isTrendModalOpen, setIsTrendModalOpen] = useState(false);
  const [selectedMonthlyKpi, setSelectedMonthlyKpi] = useState(null);

  const {
    currentUser,
    cctvs,
    events,
    alerts,
    reports,
    errors,
    isLoading,
    isRefreshing,
    isDemoData,
    lastUpdated,
    refresh,
  } = useDashboardData();

  const {
    activeAlert: globalActiveAlert,
    openEventDetail,
  } = useFireAlert();

  const metrics = useMemo(() => createDashboardMetrics({
    cctvs,
    events,
    alerts,
    reports,
  }), [alerts, cctvs, events, reports]);

  const isAdmin = currentUser?.role === 'admin';
  const activeAlert = metrics.activeAlerts[0] || null;
  const noResponseAlert = metrics.noResponseAlerts[0] || null;
  const noResponseAlertEvent = noResponseAlert
    ? events.find((event) => String(event.event_no) === String(noResponseAlert.event_no))
    : null;
  const isGlobalAlertDismissed = globalActiveAlert?.severity === 'dismissed';
  const globalAlertIsAlreadyCounted = Boolean(
    globalActiveAlert?.event_no
    && (metrics.activeAlerts.some((alert) => String(alert.event_no) === String(globalActiveAlert.event_no))
      || metrics.noResponseAlerts.some((alert) => String(alert.event_no) === String(globalActiveAlert.event_no))),
  );
  const dashboardActiveAlert = !isGlobalAlertDismissed && globalActiveAlert && !globalAlertIsAlreadyCounted
    ? globalActiveAlert
    : activeAlert;
  const dashboardActiveAlertEvent = dashboardActiveAlert?.event_no
    ? events.find((event) => String(event.event_no) === String(dashboardActiveAlert.event_no))
    : null;
  const attentionAlertCount = metrics.activeAlerts.length
    + metrics.noResponseAlerts.length
    + (dashboardActiveAlert && dashboardActiveAlert !== activeAlert ? 1 : 0);

  const reportAcceptedCount = metrics.dispatchedReportsThisMonth.length;
  const reportTotalCount = metrics.reportsThisMonth.length;
  const reportRate = reportTotalCount > 0
    ? Math.round((reportAcceptedCount / reportTotalCount) * 100)
    : 100;

  const openMonitoring = (params) => navigate(createMonitoringPath(params));

  const openEventFromMonthlyKpi = (event) => {
    setSelectedMonthlyKpi(null);
    setSelectedEvent(event);
  };

  const handleLogout = async () => {
    await authApi.logout();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-canvas text-ink font-ui transition-colors duration-300">
      <AppHeader
        currentPage="dashboard"
        currentUser={currentUser}
        onLogout={handleLogout}
      />

      <main className="max-w-7xl mx-auto w-full px-4 py-6 sm:px-6 sm:py-8 space-y-6">
        {/* 긴급 알림 배너 */}
        {(dashboardActiveAlert || metrics.noResponseAlerts.length > 0) && (
          <button
            type="button"
            onClick={() => {
              if (dashboardActiveAlert) {
                openEventDetail(dashboardActiveAlert);
                return;
              }
              openMonitoring({
                event_no: noResponseAlert?.event_no,
                cctv_no: noResponseAlert?.cctv_no || noResponseAlertEvent?.cctv_no,
              });
            }}
            className="flex w-full flex-col justify-between gap-3 rounded-xl border border-red-500 bg-red-50/90 dark:bg-red-950/40 dark:border-red-600 p-4 text-left sm:flex-row sm:items-center sm:px-5 focus:outline-none focus-visible:outline-none shadow-xs"
          >
            <span className="flex items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-red-200 dark:border-red-700 bg-canvas text-red-600 dark:text-red-400">
                <Bell className="w-4.5 h-4.5" />
              </span>
              <span>
                <span className="block text-body-sm font-bold text-red-900 dark:text-red-200">
                  {dashboardActiveAlert ? '즉시 확인이 필요한 화재 경보가 있습니다.' : '응답 기한을 넘긴 경보가 있습니다.'}
                </span>
                <span className="mt-0.5 block text-caption-sm font-medium text-red-800 dark:text-red-300">
                  {dashboardActiveAlert?.cctv_name
                    || dashboardActiveAlertEvent?.cctv_name
                    || noResponseAlert?.cctv_name
                    || noResponseAlertEvent?.cctv_name
                    || '대상 CCTV'}
                  {' · '}
                  {formatDateTime(dashboardActiveAlert?.alert_sent_at || dashboardActiveAlert?.detected_at || noResponseAlert?.alert_sent_at)}
                </span>
              </span>
            </span>
            <span className="inline-flex h-8.5 shrink-0 items-center justify-center rounded-full bg-red-600 px-4 text-caption-sm font-bold text-white hover:bg-red-700">
              관제에서 즉시 확인 &rarr;
            </span>
          </button>
        )}

        {errors.session && (
          <div className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 px-4 py-3 text-caption-sm font-semibold text-amber-900 dark:text-amber-300">
            저장된 사용자 범위로 현황을 표시하고 있습니다. {errors.session}
          </div>
        )}

        {/* 상단 타이틀 및 액션 바 (다크 모드 지원) */}
        <section className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="inline-flex h-6.5 items-center gap-1.5 rounded-full border border-hairline-strong bg-surface-soft px-3 text-caption-sm font-bold text-charcoal">
                <LayoutDashboard className="h-3.5 w-3.5" />
                {isAdmin ? '전체 시스템 운영 현황' : '담당 CCTV 운영 현황'}
              </span>
              {isDemoData && (
                <span className="inline-flex h-6.5 items-center rounded-full border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 px-3 text-caption-sm font-bold text-amber-800 dark:text-amber-300">
                  샘플 데이터
                </span>
              )}
            </div>
            <h1 className="font-display text-display-lg font-bold tracking-tight text-ink">
              운영 대시보드
            </h1>
            <p className="mt-1 text-body-sm font-medium leading-relaxed text-body">
              화재 위험 상태와 CCTV 가동률, 최근 감지 사건 및 119 출동 접수 현황을 한눈에 확인합니다.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <span className="mr-1 text-caption-sm font-semibold text-body font-mono" role="status">
              {lastUpdated
                ? `갱신 ${lastUpdated.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
                : '연결 대기 중'}
            </span>
            <button
              type="button"
              onClick={refresh}
              disabled={isRefreshing}
              className="h-9 px-3.5 rounded-full border border-hairline-strong bg-canvas text-caption-sm font-bold text-ink flex items-center gap-1.5 hover:border-ink hover:bg-surface-soft disabled:text-mute disabled:cursor-wait focus:outline-none focus-visible:outline-none transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? '갱신 중' : '새로고침'}
            </button>

            {/* 새로고침과 실시간 관제 사이: [AI 감지 추이] 버튼 */}
            <button
              type="button"
              onClick={() => setIsTrendModalOpen(true)}
              className="h-9 px-4 rounded-full border border-hairline-strong bg-canvas text-caption-sm font-bold text-ink flex items-center gap-1.5 hover:border-ink hover:bg-surface-soft focus:outline-none focus-visible:outline-none transition-all shadow-xs"
            >
              <BarChart3 className="w-3.5 h-3.5" /> AI 감지 추이
            </button>

            <button
              type="button"
              onClick={() => openMonitoring()}
              className="flex h-9 items-center gap-1.5 rounded-full bg-primary text-on-primary px-4.5 text-caption-sm font-bold hover:bg-ink-deep focus:outline-none focus-visible:outline-none transition-colors shadow-xs"
            >
              <MapPin className="w-3.5 h-3.5" /> 실시간 관제
            </button>
          </div>
        </section>

        {/* 1행: 4대 핵심 KPI 카드 */}
        <section aria-label="핵심 운영 지표" className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
          <DashboardKpiCard
            icon={<Bell className="w-4 h-4" />}
            label="대응 필요 경보"
            value={attentionAlertCount}
            unit="건"
            tooltip="관제사의 확인이 필요한 실시간 활성 경보 건수입니다."
            error={errors.alerts}
            loading={isLoading}
            tone={attentionAlertCount > 0 || metrics.noResponseAlerts.length > 0 ? 'critical' : 'neutral'}
            onClick={() => {
              if (dashboardActiveAlert) {
                openEventDetail(dashboardActiveAlert);
                return;
              }
              openMonitoring({
                event_no: noResponseAlert?.event_no,
                cctv_no: noResponseAlert?.cctv_no || noResponseAlertEvent?.cctv_no,
              });
            }}
          />
          <DashboardKpiCard
            icon={<Video className="w-4 h-4" />}
            label="CCTV 가동률"
            value={metrics.cctvAvailability}
            unit={`% (${metrics.activeCctvs.length}/${cctvs.length}대)`}
            tooltip="전체 등록 카메라 중 실시간 영상 스트림이 정상 연결된 비율입니다."
            error={errors.cctvs}
            loading={isLoading}
            tone={metrics.unhealthyCctvs.length > 0 ? 'warning' : 'neutral'}
            onClick={() => setIsCctvStatusModalOpen(true)}
          />
          <DashboardKpiCard
            icon={<Flame className="w-4 h-4" />}
            label="이번 달 화재 확정"
            value={metrics.confirmedThisMonth.length}
            unit="건"
            tooltip="AI 및 관제사에 의해 화재로 확정된 실제 사건 수(테스트 제외)입니다."
            error={errors.events}
            loading={isLoading}
            tone="neutral"
            onClick={() => setSelectedMonthlyKpi('confirmed')}
          />
          <DashboardKpiCard
            icon={<PhoneCall className="w-4 h-4" />}
            label="119 신고 접수"
            value={reportRate}
            unit={`% (${reportAcceptedCount}/${reportTotalCount}건)`}
            tooltip="119 상황실로 전송된 신고 건수 및 소방서 출동 접수 완료율입니다."
            error={errors.reports}
            loading={isLoading}
            tone={metrics.failedReportsThisMonth.length > 0 ? 'critical' : 'neutral'}
            onClick={() => setSelectedMonthlyKpi('reports')}
          />
        </section>

        {/* 2행: 최근 감지 사건 (좌측 2fr) + 골든타임 알림 대응 현황 (우측 1fr) */}
        <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(330px,1.1fr)] gap-4">
          {/* 좌측 (2fr): 최근 감지 사건 실시간 테이블 */}
          <article className="rounded-xl border border-hairline bg-canvas p-5 sm:p-6 flex flex-col justify-between shadow-xs">
            <div>
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-heading-sm font-bold text-ink">최근 감지 사건</h2>
                  <p className="mt-0.5 text-caption-sm font-medium text-body">AI 감지 내역 및 119 신고 실시간 연계 현황</p>
                </div>
                <button
                  type="button"
                  onClick={() => openMonitoring()}
                  className="h-8 px-3 rounded-full border border-hairline-strong text-caption-sm font-bold text-ink hover:border-ink hover:bg-surface-soft whitespace-nowrap focus:outline-none focus-visible:outline-none transition-colors"
                >
                  관제 지도 &rarr;
                </button>
              </div>

              <RecentEventsTable
                events={metrics.recentEvents}
                loading={isLoading}
                error={errors.events}
                onOpenEvent={setSelectedEvent}
              />
            </div>
          </article>

          {/* 우측 (1fr): 알림 대응 및 골든타임 현황 */}
          <article className="rounded-xl border border-hairline bg-canvas p-5 sm:p-6 flex flex-col justify-between shadow-xs">
            <div>
              <div className="mb-4">
                <h2 className="text-heading-sm font-bold text-ink">골든타임 대응 현황</h2>
                <p className="mt-0.5 text-caption-sm font-medium text-body">알림 확인 및 119 출동 접수 소요 시간</p>
              </div>

              <AlertStatusSummary
                items={metrics.alertBreakdown}
                averageResponse={formatDuration(metrics.averageAlertResponseSeconds)}
                averageDispatch={formatDuration(metrics.averageReportDispatchSeconds)}
                loading={isLoading}
                error={errors.alerts || errors.reports}
              />
            </div>
          </article>
        </section>
      </main>

      {/* 팝업 모달 체계 */}
      {isTrendModalOpen && (
        <EventTrendModal
          events={events}
          loading={isLoading}
          error={errors.events}
          onClose={() => setIsTrendModalOpen(false)}
        />
      )}

      {isCctvStatusModalOpen && (
        <CctvHealthDetailModal
          cctvs={cctvs}
          activeCount={metrics.activeCctvs.length}
          availability={metrics.cctvAvailability}
          loading={isLoading}
          error={errors.cctvs}
          onClose={() => setIsCctvStatusModalOpen(false)}
        />
      )}

      {selectedMonthlyKpi && (
        <MonthlyKpiDetailModal
          type={selectedMonthlyKpi}
          items={selectedMonthlyKpi === 'confirmed' ? metrics.confirmedThisMonth : metrics.reportsThisMonth}
          events={events}
          loading={isLoading}
          error={selectedMonthlyKpi === 'confirmed' ? errors.events : errors.reports}
          onClose={() => setSelectedMonthlyKpi(null)}
          onOpenEvent={openEventFromMonthlyKpi}
        />
      )}

      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}

export default Dashboard;
