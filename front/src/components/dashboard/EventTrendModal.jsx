import React, { useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  CircleAlert,
  Loader2,
  X,
} from 'lucide-react';
import {
  buildEventTrend,
  calculateTrendSummary,
} from '../../utils/dashboardMetrics';

function EventTrendModal({
  events = [],
  loading = false,
  error = '',
  onClose,
}) {
  const [trendDays, setTrendDays] = useState(7);

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  const points = useMemo(
    () => buildEventTrend(events, trendDays),
    [events, trendDays],
  );

  const summary = useMemo(
    () => calculateTrendSummary(points),
    [points],
  );

  const maxTotal = Math.max(1, ...points.map((p) => p.total));
  const labelInterval = points.length > 14 ? 3 : 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="trend-modal-title"
        style={{ width: '760px', minWidth: '320px', maxWidth: '95vw' }}
        className="box-border flex max-h-[calc(100vh-2rem)] shrink-0 flex-col overflow-hidden rounded-2xl border border-hairline bg-canvas shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex shrink-0 items-center justify-between border-b border-hairline bg-surface-soft p-5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-hairline-strong bg-canvas text-ink">
              <BarChart3 className="h-5 w-5" />
            </span>
            <div>
              <h2 id="trend-modal-title" className="text-heading-sm font-bold text-ink">
                AI 화재 감지 추이 분석
              </h2>
              <p className="mt-0.5 text-caption-sm font-medium text-body">
                기간별 불꽃 · 연기 · 복합 감지 발생 패턴 통계
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-hairline-strong bg-canvas text-body hover:text-ink focus:outline-none focus-visible:outline-none"
            aria-label="닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[75vh] space-y-4 overflow-y-auto p-5 sm:p-6">
          {loading ? (
            <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-hairline bg-surface-soft text-center text-body">
              <Loader2 className="mb-2 h-5 w-5 animate-spin text-ink" />
              <p className="text-body-sm font-bold">감지 추이를 집계하고 있습니다.</p>
            </div>
          ) : error ? (
            <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-red-200 bg-red-50 text-center text-red-700">
              <CircleAlert className="mb-2 h-5 w-5" />
              <p className="text-body-sm font-bold">{error}</p>
            </div>
          ) : (
            <>
              {/* 상단 컨트롤 바 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="inline-flex rounded-full border border-hairline-strong bg-surface-soft p-1 text-xs">
                  {[7, 14, 30].map((days) => (
                    <button
                      key={days}
                      type="button"
                      onClick={() => setTrendDays(days)}
                      className={`h-7 px-4 rounded-full text-caption-sm font-bold transition-all focus:outline-none focus-visible:outline-none ${
                        trendDays === days
                          ? 'bg-primary text-on-primary shadow-xs'
                          : 'text-body hover:text-ink'
                      }`}
                    >
                      {days}일
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-3 text-caption-sm font-semibold text-charcoal" aria-label="감지 유형 범례">
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-red-600" />불꽃</span>
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-amber-500" />연기</span>
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-ink" />불꽃·연기</span>
                </div>
              </div>

              {/* 핵심 요약 칩 */}
              <div className="grid grid-cols-3 gap-2 rounded-lg border border-hairline-strong bg-surface-soft p-3.5 text-center">
                <div>
                  <span className="block text-caption-sm font-semibold text-body">선택 기간 총 감지</span>
                  <span className="font-display text-lg font-bold text-ink">{summary.total}건</span>
                </div>
                <div className="border-x border-hairline-strong">
                  <span className="block text-caption-sm font-semibold text-body">일평균 감지</span>
                  <span className="font-display text-lg font-bold text-ink">{summary.average}건</span>
                </div>
                <div>
                  <span className="block text-caption-sm font-semibold text-body">최다 감지일</span>
                  <span className={`font-display text-lg font-bold ${summary.peakCount > 0 ? 'text-red-700' : 'text-ink'}`}>
                    {summary.peakLabel}
                  </span>
                </div>
              </div>

              {/* 막대 차트 */}
              <div className="h-56 flex items-end gap-1.5 sm:gap-2 border-b border-hairline-strong pb-2 px-1 relative">
                {points.map((point, index) => {
                  const barHeight = point.total > 0 ? Math.max((point.total / maxTotal) * 100, 8) : 2;
                  const showLabel = index % labelInterval === 0 || index === points.length - 1;

                  return (
                    <div key={point.key} className="group relative h-full min-w-0 flex-1 flex flex-col items-center justify-end">
                      {/* 마우스 호버 툴팁 */}
                      <div className="pointer-events-none absolute bottom-full mb-2 z-30 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap rounded-lg bg-surface-dark px-3 py-2 text-xs font-semibold leading-relaxed text-on-dark shadow-2xl border border-hairline/30">
                        <span className="font-bold">{point.label}</span>: 총 {point.total}건
                        {point.FLAME > 0 && <><br /><span className="text-red-400 font-bold">&bull; 불꽃 {point.FLAME}건</span></>}
                        {point.SMOKE > 0 && <><br /><span className="text-amber-300 font-bold">&bull; 연기 {point.SMOKE}건</span></>}
                        {point.FLAME_SMOKE > 0 && <><br /><span className="text-on-dark font-bold">&bull; 불꽃·연기 {point.FLAME_SMOKE}건</span></>}
                      </div>

                      <span className={`mb-1 h-4 font-mono text-caption-sm font-bold ${point.total > 0 ? 'text-ink' : 'text-mute'}`}>
                        {point.total > 0 ? point.total : ''}
                      </span>

                      <div
                        className={`w-full max-w-7 rounded-t-xs overflow-hidden flex flex-col-reverse transition-all duration-300 ${
                          point.total === 0 ? 'bg-hairline-strong h-0.5' : 'bg-surface-soft'
                        }`}
                        style={{ height: `${barHeight}%` }}
                      >
                        {point.total > 0 && (
                          <>
                            <span
                              className="block bg-red-600 w-full"
                              style={{ flex: point.FLAME }}
                            />
                            <span
                              className="block bg-amber-500 w-full"
                              style={{ flex: point.SMOKE }}
                            />
                            <span
                              className="block bg-ink w-full"
                              style={{ flex: point.FLAME_SMOKE }}
                            />
                          </>
                        )}
                      </div>

                      <span className="mt-2 h-4 text-caption-sm text-body font-bold whitespace-nowrap font-mono truncate">
                        {showLabel ? point.label : ''}
                      </span>
                    </div>
                  );
                })}
              </div>

              <p className="text-caption-sm font-medium text-body text-right">
                * 테스트 이벤트를 제외한 AI 유효 감지 데이터입니다.
              </p>
            </>
          )}
        </div>

        <footer className="flex shrink-0 justify-end border-t border-hairline bg-surface-soft p-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-full bg-primary px-5 text-caption-sm font-bold text-on-primary hover:bg-ink-deep focus:outline-none focus-visible:outline-none"
          >
            닫기
          </button>
        </footer>
      </div>
    </div>
  );
}

export default EventTrendModal;
