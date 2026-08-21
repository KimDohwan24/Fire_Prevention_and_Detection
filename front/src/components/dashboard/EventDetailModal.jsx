import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Clock3,
  Flame,
  Image as ImageIcon,
  Loader2,
  MapPin,
  ShieldAlert,
  X,
  XCircle,
} from 'lucide-react';
import { eventApi, resolveMediaUrl } from '../../api';
import {
  EVENT_CLASS_LABELS,
  formatDateTime,
} from '../../utils/dashboardMetrics';
import {
  buildDetectionTimeline,
  buildSituationActions,
  getEventStage,
  getEventStatusLabel,
} from '../../utils/eventTimeline';
import { useFireAlert } from '../../context/FireAlertContext';
import { StatusPill } from './DashboardWidgets';

const getEventStatusTone = (stage) => {
  if (stage === 'CONFIRMED') return 'critical';
  if (stage === 'DISMISSED') return 'neutral';
  return 'warning';
};

const mergeEventDetail = (summary, response) => {
  const camera = response?.cctv || summary?.cctv || {};

  return {
    ...summary,
    ...response,
    cctv: camera,
    cctv_name: response?.cctv_name || camera.cctv_name || summary?.cctv_name,
    cctv_location: response?.cctv_location || camera.cctv_location || summary?.cctv_location,
  };
};

const getMediaUrl = (media) => resolveMediaUrl(
  media?.media_url || media?.thumbnail_url || '',
);

const getConfidencePercent = (value) => {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return null;
  return Math.round((confidence <= 1 ? confidence : confidence / 100) * 100);
};

const getStageClass = (stage) => {
  if (stage === 'CONFIRMED') return 'border-red-500/30 bg-red-500/10 text-red-600';
  if (stage === 'DISMISSED') return 'border-slate-400/40 bg-slate-500/10 text-slate-600';
  return 'border-amber-500/40 bg-amber-500/10 text-amber-700';
};

const getTimelineToneClass = (tone) => {
  if (tone === 'confirmed') return 'border-red-500 bg-red-500';
  if (tone === 'dismissed') return 'border-slate-500 bg-slate-500';
  if (tone === 'detecting') return 'border-amber-500 bg-amber-500';
  return 'border-hairline bg-canvas';
};

const getMediaRoleLabel = (media) => {
  if (media?.media_is_confirmation) return '확정 시점';
  if (media?.media_is_first) return '최초 감지';
  if (media?.media_is_primary) return '대표 증거';
  return 'AI 증거';
};

function DetailRow({ label, children }) {
  return (
    <div className="flex items-start justify-between gap-4 text-caption-sm">
      <span className="shrink-0 text-mute">{label}</span>
      <span className="text-right font-medium text-ink">{children}</span>
    </div>
  );
}

function TimelineList({ items, title, icon: Icon, tone = 'neutral' }) {
  if (items.length === 0) return null;

  return (
    <section className="space-y-3 rounded-xl border border-hairline bg-surface-soft p-4">
      <h3 className="flex items-center gap-2 text-body-sm font-bold text-ink">
        <Icon className={`h-4 w-4 ${tone === 'action' ? 'text-red-500' : 'text-amber-500'}`} />
        {title}
      </h3>
      <div className="relative space-y-4 pl-1 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-hairline">
        {items.map((item) => (
          <div key={item.id} className="relative pl-7 text-caption-sm">
            <span
              className={`absolute left-1 top-1 h-3.5 w-3.5 -translate-x-1/2 rounded-full border-2 ${getTimelineToneClass(item.tone)}`}
            />
            <span className="block font-mono text-[11px] text-mute">
              {formatDateTime(item.timestamp)}
            </span>
            <p className="mt-0.5 font-medium leading-relaxed text-ink">{item.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function EventDetailModal({ event, onClose, zIndexClassName = 'z-50' }) {
  const {
    activeAlert,
    actionNotice,
    decideTest,
    events,
    isActionLoading,
    respondRealAlert,
  } = useFireAlert();
  const [detail, setDetail] = useState(event);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [activeMediaIndex, setActiveMediaIndex] = useState(0);

  useEffect(() => {
    let isCancelled = false;

    setDetail(event);
    setIsLoading(false);
    setLoadError('');
    setActiveMediaIndex(0);

    if (event?.event_no == null) return undefined;

    setIsLoading(true);
    eventApi.get(event.event_no)
      .then((response) => {
        if (!isCancelled && response) {
          setDetail(mergeEventDetail(event, response));
        }
      })
      .catch(() => {
        if (!isCancelled) setLoadError('상세 정보를 불러오지 못해 현재 감지 정보만 보여드립니다.');
      })
      .finally(() => {
        if (!isCancelled) setIsLoading(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [event]);

  useEffect(() => {
    const handleEscape = (keyboardEvent) => {
      if (keyboardEvent.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  if (!event) return null;

  const loadedDetail = detail?.event_no != null
    && String(detail.event_no) === String(event.event_no)
    ? detail
    : event;
  const contextEvent = events.find((item) => (
    event.event_no != null
    && String(item.event_no) === String(event.event_no)
  ));
  const isActiveAlertDetail = Boolean(activeAlert && (
    event === activeAlert
    || (activeAlert.event_no != null
      && event.event_no != null
      && String(activeAlert.event_no) === String(event.event_no))
    || (activeAlert.job_id && event?.job_id && activeAlert.job_id === event.job_id)
  ));
  const visibleDetail = {
    ...event,
    ...loadedDetail,
    ...(contextEvent || {}),
    ...(isActiveAlertDetail ? activeAlert : {}),
  };
  const camera = visibleDetail.cctv || {};
  const cctvName = visibleDetail.cctv_name
    || camera.cctv_name
    || `CCTV #${visibleDetail.cctv_no || '-'}`;
  const cctvLocation = visibleDetail.cctv_location
    || camera.cctv_location
    || '위치 정보 없음';
  const stage = getEventStage(visibleDetail);
  const isDetecting = stage === 'DETECTING';
  const statusLabel = getEventStatusLabel(visibleDetail);
  const confidence = getConfidencePercent(visibleDetail.event_confidence ?? visibleDetail.confidence);
  const rawMediaItems = Array.isArray(visibleDetail.media) ? visibleDetail.media : [];
  const fallbackMediaUrl = visibleDetail.first_detection_media_url
    || visibleDetail.thumbnail_url
    || visibleDetail.media_url;
  const mediaItems = rawMediaItems.length > 0
    ? rawMediaItems
    : fallbackMediaUrl
      ? [{ media_url: fallbackMediaUrl, media_is_first: isDetecting, media_is_primary: true }]
      : [];
  const firstMedia = mediaItems.find((media) => media.media_is_first) || mediaItems[0] || null;
  const displayMediaItems = isDetecting
    ? (firstMedia ? [firstMedia] : [])
    : mediaItems;
  const activeMedia = displayMediaItems[activeMediaIndex] || displayMediaItems[0] || null;
  const detectionTimeline = isDetecting ? [] : buildDetectionTimeline(visibleDetail);
  const situationActions = isDetecting ? [] : buildSituationActions(visibleDetail);
  const canConfirmTest = isActiveAlertDetail
    && activeAlert.isTest
    && activeAlert.severity === 'detecting';
  const canRespondReal = isActiveAlertDetail
    && !activeAlert.isTest
    && Boolean(activeAlert.alert_no);
  const hasActionButtons = canConfirmTest || canRespondReal;
  const mediaTitle = isDetecting
    ? '최초 감지 증거'
    : stage === 'CONFIRMED' ? 'AI 판정 증거' : '오탐 판단 근거';

  return (
    <div
      className={`fixed inset-0 ${zIndexClassName} flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs`}
      onClick={(clickEvent) => {
        if (clickEvent.target === clickEvent.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-detail-modal-title"
        style={{ width: '840px', minWidth: '320px', maxWidth: '95vw' }}
        className="box-border flex max-h-[calc(100vh-2rem)] shrink-0 flex-col rounded-2xl border border-hairline bg-canvas shadow-2xl"
        onClick={(clickEvent) => clickEvent.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between gap-4 rounded-t-2xl border-b border-hairline bg-surface-soft/60 p-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className={`shrink-0 rounded-xl border p-2 ${getStageClass(stage)}`}>
              {stage === 'CONFIRMED' ? <Flame className="h-6 w-6" /> : <ShieldAlert className="h-6 w-6" />}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${
                  stage === 'CONFIRMED'
                    ? 'bg-red-600 text-white'
                    : stage === 'DISMISSED'
                      ? 'bg-slate-600 text-white'
                      : 'bg-amber-500 text-white'
                }`}>
                  {statusLabel}
                </span>
                {visibleDetail.isTest || visibleDetail.event_is_test ? (
                  <span className="rounded-full border border-hairline px-2 py-0.5 text-[10px] font-bold text-mute">
                    영상 테스트
                  </span>
                ) : null}
                {confidence != null && (
                  <span className="font-mono text-xs text-mute">신뢰도 {confidence}%</span>
                )}
              </div>
              <h2 id="event-detail-modal-title" className="mt-1 truncate text-heading-sm font-bold text-ink">
                {cctvName} 감지 상세
              </h2>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 text-mute transition-colors hover:bg-surface-soft hover:text-ink focus:outline-none focus-visible:outline-none"
            aria-label="상세보기 닫기"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[75vh] space-y-5 overflow-y-auto p-6">
          {isLoading && (
            <div className="flex items-center gap-2 rounded-lg border border-hairline bg-surface-soft px-3 py-2 text-caption-sm text-body">
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
              감지 정보와 AI 증거를 불러오는 중입니다.
            </div>
          )}

          {loadError && (
            <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-caption-sm text-amber-700">
              {loadError}
            </p>
          )}

          <div className="grid grid-cols-1 gap-5 md:grid-cols-12">
            <div className="space-y-3 md:col-span-7">
              <div className="flex items-center justify-between gap-3">
                <h3 className="flex items-center gap-2 text-body-sm font-bold text-ink">
                  <ImageIcon className="h-4 w-4 text-red-500" />
                  {mediaTitle}
                </h3>
                {activeMedia && (
                  <span className="rounded-full border border-hairline px-2 py-0.5 text-[10px] font-semibold text-mute">
                    {getMediaRoleLabel(activeMedia)}
                  </span>
                )}
              </div>

              <div className="relative aspect-video overflow-hidden rounded-xl border border-hairline bg-black">
                {getMediaUrl(activeMedia) ? (
                  <img
                    src={getMediaUrl(activeMedia)}
                    alt={`${cctvName} ${mediaTitle}`}
                    className="h-full w-full object-contain"
                  />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-mute">
                    <ImageIcon className="h-10 w-10" />
                    <span className="text-caption-sm">
                      {isDetecting ? '최초 감지 이미지를 준비 중입니다.' : '저장된 AI 증거 이미지가 없습니다.'}
                    </span>
                  </div>
                )}
              </div>

              {displayMediaItems.length > 1 && (
                <div className="flex gap-2 overflow-x-auto pb-1" aria-label="AI 증거 이미지 목록">
                  {displayMediaItems.map((media, index) => (
                    <button
                      key={media.media_no || `${getMediaUrl(media)}-${index}`}
                      type="button"
                      onClick={() => setActiveMediaIndex(index)}
                      className={`h-12 w-16 shrink-0 overflow-hidden rounded-lg border bg-black focus:outline-none focus-visible:outline-none ${
                        index === activeMediaIndex ? 'border-red-500' : 'border-hairline'
                      }`}
                      aria-label={`${getMediaRoleLabel(media)} 이미지 보기`}
                    >
                      {getMediaUrl(media) ? (
                        <img src={getMediaUrl(media)} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <ImageIcon className="mx-auto h-4 w-4 text-mute" />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-3 md:col-span-5">
              <div className="space-y-3 rounded-xl border border-hairline bg-surface-soft p-4">
                <div className="flex items-center gap-2 text-caption-sm font-bold text-ink">
                  <MapPin className="h-4 w-4 text-red-500" />
                  카메라 위치
                </div>
                <div>
                  <p className="text-body-sm font-semibold text-ink">{cctvName}</p>
                  <p className="mt-1 text-caption-sm text-mute">{cctvLocation}</p>
                </div>
              </div>

              <div className="space-y-3 rounded-xl border border-hairline bg-surface-soft p-4">
                <div className="flex items-center gap-2 text-caption-sm font-bold text-ink">
                  <Clock3 className="h-4 w-4 text-red-500" />
                  감지 정보
                </div>
                <DetailRow label="현재 상태">
                  <StatusPill tone={getEventStatusTone(stage)}>{statusLabel}</StatusPill>
                </DetailRow>
                <DetailRow label="감지 클래스">
                  {EVENT_CLASS_LABELS[visibleDetail.event_class] || visibleDetail.event_class || '-'}
                </DetailRow>
                <DetailRow label="최초 감지">
                  {formatDateTime(visibleDetail.event_first_detected_at || visibleDetail.event_detected_at)}
                </DetailRow>
                {visibleDetail.event_detected_at && stage === 'CONFIRMED' && (
                  <DetailRow label="화재 확정">
                    {formatDateTime(visibleDetail.event_detected_at)}
                  </DetailRow>
                )}
                {visibleDetail.event_detected_frames != null && (
                  <DetailRow label="감지 프레임">
                    {visibleDetail.event_detected_frames} / {visibleDetail.event_threshold_frames || '-'}
                  </DetailRow>
                )}
              </div>
            </div>
          </div>

          {isDetecting ? (
            <section className="space-y-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-amber-800">
              <h3 className="flex items-center gap-2 text-body-sm font-bold">
                <ShieldAlert className="h-4 w-4" />
                관제자 판단 필요
              </h3>
              <p className="text-caption-sm leading-relaxed">
                AI가 최초 화염·연기 패턴을 감지했습니다. 확정 전 단계이므로 상단 경보의 화재 확정 또는 오탐 처리 버튼으로 판단을 반영할 수 있습니다.
              </p>
            </section>
          ) : (
            <>
              <TimelineList
                items={detectionTimeline}
                title="감지 타임라인"
                icon={Clock3}
              />
              <TimelineList
                items={situationActions}
                title="상황 조치 이력"
                icon={stage === 'DISMISSED' ? XCircle : CheckCircle2}
                tone="action"
              />
            </>
          )}
        </div>

        <div className={`flex shrink-0 flex-wrap items-center gap-3 rounded-b-2xl border-t border-hairline bg-surface-soft/60 p-4 ${hasActionButtons || actionNotice ? 'justify-between' : 'justify-end'}`}>
          {(hasActionButtons || actionNotice) && (
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              {canConfirmTest && (
                <>
                  <button
                    type="button"
                    onClick={() => decideTest('CONFIRM_FIRE')}
                    disabled={isActionLoading}
                    className="h-10 rounded-full bg-red-600 px-4 text-caption-sm font-bold text-white transition-colors hover:bg-red-700 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                  >
                    119 신고 (테스트)
                  </button>
                  <button
                    type="button"
                    onClick={() => decideTest('DISMISS')}
                    disabled={isActionLoading}
                    className="h-10 rounded-full border border-amber-600/40 bg-canvas px-4 text-caption-sm font-bold text-amber-700 transition-colors hover:bg-amber-500/10 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                  >
                    오탐 처리
                  </button>
                </>
              )}
              {canRespondReal && (
                <>
                  <button
                    type="button"
                    onClick={() => respondRealAlert('READ')}
                    disabled={isActionLoading}
                    className="h-10 rounded-full bg-red-600 px-4 text-caption-sm font-bold text-white transition-colors hover:bg-red-700 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                  >
                    119 신고
                  </button>
                  <button
                    type="button"
                    onClick={() => respondRealAlert('CANCEL')}
                    disabled={isActionLoading}
                    className="h-10 rounded-full border border-amber-600/40 bg-canvas px-4 text-caption-sm font-bold text-amber-700 transition-colors hover:bg-amber-500/10 disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none"
                  >
                    오탐 취소
                  </button>
                </>
              )}
              {actionNotice && (
                <span role="status" className="max-w-[280px] text-caption-sm font-semibold text-amber-700">
                  {actionNotice}
                </span>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-full bg-primary px-5 text-caption-sm font-semibold text-on-primary focus:outline-none focus-visible:outline-none"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

export default EventDetailModal;
