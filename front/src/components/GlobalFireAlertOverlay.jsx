import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Flame, Siren, X } from 'lucide-react';
import EventDetailModal from './dashboard/EventDetailModal';
import { useFireAlert } from '../context/FireAlertContext';

const TEST_AUTO_REPORT_DELAY_MS = 60 * 1000;
const TEST_AUTO_REPORT_REASON = '60초 무응답 자동 신고';

function GlobalFireAlertOverlay() {
  const {
    activeAlert,
    actionNotice,
    decideTest,
    dismissAlert,
    endTestAlert,
    isActionLoading,
    openEventDetail,
    respondRealAlert,
    selectedEvent,
    setActionNotice,
    setSelectedEvent,
  } = useFireAlert();
  const [autoReportSecondsLeft, setAutoReportSecondsLeft] = useState(null);
  const decideTestRef = useRef(decideTest);
  const autoReportAttemptedJobRef = useRef(null);

  useEffect(() => {
    decideTestRef.current = decideTest;
  }, [decideTest]);

  useEffect(() => {
    const jobId = activeAlert?.job_id;
    const eventNo = activeAlert?.event_no;
    const timerKey = jobId && eventNo != null ? `${jobId}:${eventNo}` : null;
    const shouldAutoReport = Boolean(
      activeAlert?.isTest
      && timerKey
      && !activeAlert?.operator_decision,
    );

    if (
      !shouldAutoReport
      || isActionLoading
      || autoReportAttemptedJobRef.current === timerKey
    ) {
      setAutoReportSecondsLeft(null);
      return undefined;
    }

    const startedAt = Date.now();
    const delaySeconds = TEST_AUTO_REPORT_DELAY_MS / 1000;
    setAutoReportSecondsLeft(delaySeconds);

    const countdownTimer = window.setInterval(() => {
      const elapsedMs = Date.now() - startedAt;
      const secondsLeft = Math.max(
        0,
        Math.ceil((TEST_AUTO_REPORT_DELAY_MS - elapsedMs) / 1000),
      );
      setAutoReportSecondsLeft(secondsLeft);
      if (secondsLeft <= 0) window.clearInterval(countdownTimer);
    }, 1000);

    const autoReportTimer = window.setTimeout(() => {
      autoReportAttemptedJobRef.current = timerKey;
      setAutoReportSecondsLeft(0);
      decideTestRef.current?.('CONFIRM_FIRE', TEST_AUTO_REPORT_REASON);
    }, TEST_AUTO_REPORT_DELAY_MS);

    return () => {
      window.clearTimeout(autoReportTimer);
      window.clearInterval(countdownTimer);
    };
  }, [activeAlert?.event_no, activeAlert?.isTest, activeAlert?.job_id, activeAlert?.operator_decision, isActionLoading]);

  const isDetecting = activeAlert?.severity === 'detecting';
  const isDismissed = activeAlert?.severity === 'dismissed';
  const isTest = activeAlert?.isTest === true;

  return (
    <>
      {activeAlert && (
        <div className="fixed top-16 left-1/2 z-[60] w-[min(720px,95vw)] -translate-x-1/2 pointer-events-auto" aria-live="assertive">
          <div
            className={`rounded-2xl border-2 px-5 py-3 text-white shadow-2xl ${
              isDetecting
                ? 'bg-amber-500 border-amber-300 ring-4 ring-amber-400/40'
                : isDismissed
                  ? 'bg-slate-600 border-slate-400 ring-4 ring-slate-400/30'
                  : 'bg-red-600 border-red-400 ring-4 ring-red-500/40'
            }`}
          >
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <span className="h-3 w-3 shrink-0 animate-ping rounded-full bg-white" />
                <Flame className="h-5 w-5 shrink-0" />
                <div className="min-w-0 truncate text-xs font-bold sm:text-sm">
                  <span>
                    {isDetecting ? '[화재 의심 감지]' : isDismissed ? '[오탐 처리]' : '[화재 긴급 감지]'}{' '}
                    {activeAlert.cctv_name}
                  </span>
                  <span className="ml-2 font-mono text-xs font-semibold text-white/80">
                    ({activeAlert.confidence}% 신뢰도)
                  </span>
                  {isTest && (
                    <span className="ml-2 rounded-full border border-white/40 px-2 py-0.5 text-[10px] font-bold">
                      테스트
                    </span>
                  )}
                </div>
              </div>

              <div className="flex w-full shrink-0 flex-wrap items-center justify-end gap-1.5 sm:w-auto">
                <button
                  type="button"
                  onClick={() => openEventDetail(activeAlert)}
                  className="inline-flex h-8 items-center gap-1 rounded-full bg-white px-3 text-xs font-bold text-red-600 transition-colors hover:bg-red-50 focus:outline-none focus-visible:outline-none"
                >
                  <Siren className="h-3.5 w-3.5" />
                  상세보기
                </button>

                {isTest && isDetecting ? (
                  <>
                    <button
                      type="button"
                      onClick={() => decideTest('CONFIRM_FIRE')}
                      disabled={isActionLoading}
                      className="h-8 rounded-full bg-red-700 px-3 text-xs font-bold text-white transition-colors hover:bg-red-800 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                    >
                      119 신고 (테스트)
                    </button>
                    <button
                      type="button"
                      onClick={() => decideTest('DISMISS')}
                      disabled={isActionLoading}
                      className="h-8 rounded-full bg-white px-3 text-xs font-bold text-amber-700 transition-colors hover:bg-amber-50 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                    >
                      오탐 처리
                    </button>
                  </>
                ) : isTest ? (
                  <button
                    type="button"
                    onClick={endTestAlert}
                    className="inline-flex h-8 items-center gap-1 rounded-full bg-black px-3 text-xs font-bold text-white transition-colors hover:bg-neutral-900 focus:outline-none focus-visible:outline-none"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    테스트 종료
                  </button>
                ) : activeAlert.alert_no ? (
                  <>
                    <button
                      type="button"
                      onClick={() => respondRealAlert('CANCEL')}
                      disabled={isActionLoading}
                      className="h-8 rounded-full bg-amber-500 px-3 text-xs font-bold text-white transition-colors hover:bg-amber-600 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                    >
                      오탐 처리
                    </button>
                    <button
                      type="button"
                      onClick={() => respondRealAlert('READ')}
                      disabled={isActionLoading}
                      className="h-8 rounded-full bg-black px-3 text-xs font-bold text-white transition-colors hover:bg-neutral-900 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                    >
                      화재 확인
                    </button>
                  </>
                ) : null}

                {isTest && autoReportSecondsLeft != null && (
                  <div className="w-full rounded-lg bg-white/15 px-3 py-1.5 text-center text-xs font-semibold text-white sm:w-auto">
                    무응답 자동 신고까지 {autoReportSecondsLeft}초
                  </div>
                )}

                <button
                  type="button"
                  onClick={dismissAlert}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors hover:bg-white/15 focus:outline-none focus-visible:outline-none"
                  aria-label="화재 감지 팝업 닫기"
                  title="팝업만 닫기"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {actionNotice && (
                <div role="status" className="flex w-full items-center gap-2 rounded-lg bg-white/15 px-3 py-2 text-xs font-semibold text-white">
                  <span className="flex-1 text-center">{actionNotice}</span>
                  <button
                    type="button"
                    onClick={() => setActionNotice(null)}
                    className="rounded-full p-1 text-white hover:bg-white/20 focus:outline-none focus-visible:outline-none"
                    aria-label="안내 닫기"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {!activeAlert && actionNotice && (
        <div className="fixed bottom-6 right-6 z-[60] flex max-w-[min(420px,calc(100vw-2rem))] items-center gap-3 rounded-xl border border-hairline bg-primary px-4 py-3 text-xs font-semibold text-on-primary shadow-2xl" role="status">
          <span className="flex-1">{actionNotice}</span>
          <button
            type="button"
            onClick={() => setActionNotice(null)}
            className="rounded-full p-1 text-on-primary hover:bg-white/15 focus:outline-none focus-visible:outline-none"
            aria-label="안내 닫기"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          zIndexClassName="z-[70]"
        />
      )}
    </>
  );
}

export default GlobalFireAlertOverlay;
