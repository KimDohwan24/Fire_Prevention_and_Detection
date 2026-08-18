import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell,
  Flame,
  LayoutDashboard,
  MapPin,
  PhoneCall,
  RefreshCw,
  Settings,
  UserRound,
  Video,
} from 'lucide-react';
import { authApi } from '../api';
import AppHeader from '../components/AppHeader';
import EventDetailModal from '../components/dashboard/EventDetailModal';
import {
  AlertStatusSummary,
  CctvHealthList,
  DashboardKpiCard,
  EventTrendChart,
  RecentEventsTable,
} from '../components/dashboard/DashboardWidgets';
import useDashboardData from '../hooks/useDashboardData';
import {
  buildEventTrend,
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
  const [trendDays, setTrendDays] = useState(7);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const {
    currentUser,
    cctvs,
    events,
    alerts,
    reports,
    errors,
    isLoading,
    isRefreshing,
    lastUpdated,
    refresh,
  } = useDashboardData();

  const metrics = useMemo(() => createDashboardMetrics({
    cctvs,
    events,
    alerts,
    reports,
  }), [alerts, cctvs, events, reports]);
  const trendPoints = useMemo(
    () => buildEventTrend(events, trendDays),
    [events, trendDays],
  );

  const isAdmin = currentUser?.role === 'admin';
  const activeAlert = metrics.activeAlerts[0] || null;
  const activeAlertEvent = activeAlert
    ? events.find((event) => String(event.event_no) === String(activeAlert.event_no))
    : null;
  const latestConfirmedEvent = metrics.confirmedToday[0] || null;
  const latestReport = metrics.reportsToday[0] || null;
  const attentionCctv = metrics.unhealthyCctvs[0] || null;

  const openMonitoring = (params) => navigate(createMonitoringPath(params));

  const handleLogout = async () => {
    await authApi.logout();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-canvas text-ink font-ui">
      <AppHeader
        currentPage="dashboard"
        currentUser={currentUser}
        onLogout={handleLogout}
      />

      <main className="max-w-7xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-10">
        {(activeAlert || metrics.noResponseAlerts.length > 0) && (
          <button
            type="button"
            onClick={() => openMonitoring({
              event_no: activeAlert?.event_no || metrics.noResponseAlerts[0]?.event_no,
              cctv_no: activeAlertEvent?.cctv_no,
            })}
            className="w-full mb-7 px-5 py-4 rounded-lg border border-red-500 bg-canvas dark:border-red-400/40 dark:bg-red-950/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-left focus:outline-none focus-visible:outline-none"
          >
            <span className="flex items-start gap-3">
              <span className="w-9 h-9 rounded-full border border-red-200 bg-canvas text-red-600 dark:border-red-400/40 dark:text-red-200 flex items-center justify-center shrink-0">
                <Bell className="w-4.5 h-4.5" />
              </span>
              <span>
                <span className="block text-body-sm font-semibold text-red-700 dark:text-red-100">
                  {activeAlert ? '즉시 확인이 필요한 화재 경보가 있습니다.' : '응답 기한을 넘긴 경보가 있습니다.'}
                </span>
                <span className="block mt-1 text-caption-sm text-red-700/80 dark:text-red-200/80">
                  {activeAlert?.cctv_name || activeAlertEvent?.cctv_name || '대상 CCTV'}
                  {' · '}
                  {formatDateTime(activeAlert?.alert_sent_at || metrics.noResponseAlerts[0]?.alert_sent_at)}
                </span>
              </span>
            </span>
            <span className="shrink-0 text-caption-sm font-semibold text-red-700 dark:text-red-100 underline underline-offset-4">
              실시간 관제에서 확인
            </span>
          </button>
        )}

        {errors.session && (
          <div className="mb-7 px-4 py-3 rounded-lg border border-amber-200 bg-amber-50 text-caption-sm text-amber-700">
            저장된 사용자 범위로 현황을 표시하고 있습니다. {errors.session}
          </div>
        )}

        <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-8">
          <div>
            <div className="flex items-center gap-2 text-caption-sm font-semibold text-body mb-3">
              <LayoutDashboard className="w-4 h-4" />
              <span>{isAdmin ? '전체 시스템 현황' : '담당 CCTV 현황'}</span>
            </div>
            <h1 className="font-display text-display-xl font-semibold tracking-tight text-ink">
              운영 대시보드
            </h1>
            <p className="mt-3 max-w-2xl text-body-sm text-body leading-relaxed">
              현재 위험 상태와 장비 가동률, 최근 감지 추이와 119 대응 결과를 한눈에 확인합니다.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-[11px] text-mute">
              {lastUpdated
                ? `마지막 갱신 ${lastUpdated.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
                : '데이터 연결 대기 중'}
            </span>
            <button
              type="button"
              onClick={refresh}
              disabled={isRefreshing}
              className="h-9 px-4 rounded-full border border-hairline bg-canvas text-caption-sm font-semibold text-ink flex items-center gap-1.5 disabled:text-mute disabled:cursor-wait focus:outline-none focus-visible:outline-none"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {isRefreshing ? '갱신 중' : '새로고침'}
            </button>
            <button
              type="button"
              onClick={() => openMonitoring()}
              className="h-9 px-5 rounded-full bg-primary text-on-primary text-caption-sm font-semibold flex items-center gap-1.5 focus:outline-none focus-visible:outline-none"
            >
              <MapPin className="w-3.5 h-3.5" /> 실시간 관제
            </button>
          </div>
        </section>

        <section aria-label="핵심 운영 지표" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-8">
          <DashboardKpiCard
            icon={<Bell className="w-4 h-4" />}
            label="대응 필요 경보"
            value={`${metrics.activeAlerts.length}건`}
            helper="현재 SENT 상태 알림"
            detail={metrics.noResponseAlerts.length > 0 ? `무응답 ${metrics.noResponseAlerts.length}건` : '무응답 경보 없음'}
            error={errors.alerts}
            loading={isLoading}
            critical={metrics.activeAlerts.length > 0 || metrics.noResponseAlerts.length > 0}
            onClick={() => openMonitoring({
              event_no: activeAlert?.event_no || metrics.noResponseAlerts[0]?.event_no,
              cctv_no: activeAlertEvent?.cctv_no,
            })}
          />
          <DashboardKpiCard
            icon={<Video className="w-4 h-4" />}
            label="CCTV 가동 현황"
            value={`${metrics.activeCctvs.length} / ${cctvs.length}`}
            helper={`${metrics.cctvAvailability}% 가동률`}
            detail={metrics.unhealthyCctvs.length > 0 ? `점검 필요 ${metrics.unhealthyCctvs.length}대` : '전체 장비 정상'}
            error={errors.cctvs}
            loading={isLoading}
            onClick={() => openMonitoring({
              cctv_status: attentionCctv ? 'UNHEALTHY' : 'ACTIVE',
              cctv_no: attentionCctv?.cctv_no,
            })}
          />
          <DashboardKpiCard
            icon={<Flame className="w-4 h-4" />}
            label="오늘 화재 확정"
            value={`${metrics.confirmedToday.length}건`}
            helper="테스트 이벤트 제외"
            detail={latestConfirmedEvent ? `${latestConfirmedEvent.cctv_name || 'CCTV'}에서 최근 감지` : '오늘 확정 이벤트 없음'}
            error={errors.events}
            loading={isLoading}
            critical={metrics.confirmedToday.length > 0}
            onClick={() => openMonitoring({
              event_no: latestConfirmedEvent?.event_no,
              cctv_no: latestConfirmedEvent?.cctv_no,
            })}
          />
          <DashboardKpiCard
            icon={<PhoneCall className="w-4 h-4" />}
            label="오늘 119 신고"
            value={`${metrics.dispatchedReportsToday.length} / ${metrics.reportsToday.length}`}
            helper="접수 완료 / 전체 신고"
            detail={metrics.failedReportsToday.length > 0 ? `전송 실패 ${metrics.failedReportsToday.length}건` : '신고 전송 실패 없음'}
            error={errors.reports}
            loading={isLoading}
            critical={metrics.failedReportsToday.length > 0}
            onClick={() => openMonitoring({ event_no: latestReport?.event_no })}
          />
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] gap-4 mb-8">
          <article className="rounded-lg border border-hairline bg-canvas p-5 sm:p-6">
            <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-heading-sm font-semibold text-ink">AI 감지 추이</h2>
                <p className="mt-1 text-caption-sm text-mute">테스트를 제외한 유형별 감지 이벤트</p>
              </div>
              <div className="inline-flex self-start rounded-full border border-hairline bg-surface-soft p-1">
                {[7, 30].map((days) => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => setTrendDays(days)}
                    className={`h-7 px-3 rounded-full text-[11px] font-semibold focus:outline-none focus-visible:outline-none ${
                      trendDays === days ? 'bg-primary text-on-primary' : 'text-body'
                    }`}
                  >
                    {days}일
                  </button>
                ))}
              </div>
            </div>
            <EventTrendChart points={trendPoints} loading={isLoading} error={errors.events} />
          </article>

          <article className="rounded-lg border border-hairline bg-canvas p-5 sm:p-6">
            <div className="mb-6">
              <h2 className="text-heading-sm font-semibold text-ink">알림 대응 현황</h2>
              <p className="mt-1 text-caption-sm text-mute">최근 30일 알림 상태와 평균 처리 시간</p>
            </div>
            <AlertStatusSummary
              items={metrics.alertBreakdown}
              averageResponse={formatDuration(metrics.averageAlertResponseSeconds)}
              averageDispatch={formatDuration(metrics.averageReportDispatchSeconds)}
              loading={isLoading}
              error={errors.alerts || errors.reports}
            />
          </article>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          <article className="min-w-0 rounded-lg border border-hairline bg-canvas p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3 pb-3 border-b border-hairline">
              <div>
                <h2 className="text-heading-sm font-semibold text-ink">점검 필요 CCTV</h2>
                <p className="mt-1 text-caption-sm text-mute">오류 장비를 가장 먼저 표시합니다.</p>
              </div>
              <span className="h-7 min-w-7 px-2 rounded-full border border-hairline bg-surface-soft text-[11px] font-mono text-ink flex items-center justify-center">
                {metrics.unhealthyCctvs.length}
              </span>
            </div>
            <CctvHealthList
              items={metrics.unhealthyCctvs}
              loading={isLoading}
              error={errors.cctvs}
              onOpenMonitoring={(cctv) => openMonitoring({ cctv_no: cctv.cctv_no })}
            />
          </article>

          <article className="min-w-0 rounded-lg border border-hairline bg-surface-soft p-5 sm:p-6 flex flex-col justify-between min-h-[280px]">
            <div>
              <div className="w-10 h-10 rounded-full border border-hairline bg-canvas flex items-center justify-center">
                {isAdmin ? <Settings className="w-4.5 h-4.5" /> : <UserRound className="w-4.5 h-4.5" />}
              </div>
              <h2
                className="mt-6 text-heading-md sm:text-heading-lg font-semibold text-ink break-keep"
                style={{ wordBreak: 'keep-all', overflowWrap: 'normal' }}
              >
                {isAdmin ? '전체 시스템을 기준으로 집계했습니다.' : '내 CCTV 범위만 안전하게 집계했습니다.'}
              </h2>
              <p
                className="mt-3 max-w-3xl text-body-sm text-body leading-relaxed break-keep"
                style={{ wordBreak: 'keep-all', overflowWrap: 'normal' }}
              >
                {isAdmin
                  ? '전체 CCTV와 감지 이벤트를 확인하고, 장비 또는 회원 설정이 필요하면 관리자 페이지에서 관리할 수 있습니다.'
                  : '본인이 등록하거나 담당하는 CCTV와 연결된 이벤트·알림·신고 이력만 대시보드에 표시됩니다.'}
              </p>
            </div>
            <div className="mt-6 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => openMonitoring()}
                className="h-9 px-4 rounded-full border border-hairline-strong bg-canvas text-caption-sm font-semibold text-ink focus:outline-none focus-visible:outline-none"
              >
                관제 화면 열기
              </button>
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => navigate('/admin')}
                  className="h-9 px-4 rounded-full border border-hairline-strong bg-canvas text-caption-sm font-semibold text-ink focus:outline-none focus-visible:outline-none"
                >
                  시스템 관리
                </button>
              )}
            </div>
          </article>
        </section>

        <section className="rounded-lg border border-hairline bg-canvas p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-heading-sm font-semibold text-ink">최근 감지 사건</h2>
              <p className="mt-1 text-caption-sm text-mute">최근 5건의 감지·알림·119 신고 상태</p>
            </div>
            <button
              type="button"
              onClick={() => openMonitoring()}
              className="h-8 px-3 rounded-full border border-hairline text-[11px] font-semibold text-ink whitespace-nowrap focus:outline-none focus-visible:outline-none"
            >
              전체 관제 보기
            </button>
          </div>
          <RecentEventsTable
            events={metrics.recentEvents}
            loading={isLoading}
            error={errors.events}
            onOpenEvent={setSelectedEvent}
          />
        </section>
      </main>

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
