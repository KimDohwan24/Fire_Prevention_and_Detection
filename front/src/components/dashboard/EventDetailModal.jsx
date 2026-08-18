import React, { useEffect, useState } from 'react';
import {
  Clock3,
  FileText,
  Flame,
  Image as ImageIcon,
  Loader2,
  MapPin,
  PhoneCall,
  X,
} from 'lucide-react';
import { eventApi } from '../../api';
import {
  ALERT_STATUS_LABELS,
  EVENT_CLASS_LABELS,
  EVENT_STATUS_LABELS,
  REPORT_STATUS_LABELS,
  formatDateTime,
} from '../../utils/dashboardMetrics';
import { StatusPill } from './DashboardWidgets';

const getEventStatusTone = (status) => (
  status === 'CONFIRMED' ? 'critical' : status === 'DISMISSED' ? 'neutral' : 'warning'
);

const getAlertStatusTone = (status) => {
  if (status === 'SENT' || status === 'NO_RESPONSE') return 'critical';
  if (status === 'READ') return 'success';
  return 'neutral';
};

const getReportStatusTone = (status) => {
  if (status === 'FAILED') return 'critical';
  if (status === 'DISPATCHED' || status === 'ACCEPTED') return 'success';
  if (status === 'SENDING' || status === 'NO_RESPONSE') return 'warning';
  return 'neutral';
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

const getMediaUrl = (media) => media?.media_url || media?.thumbnail_url || '';

function DetailRow({ label, children }) {
  return (
    <div className="flex items-start justify-between gap-4 text-caption-sm">
      <span className="shrink-0 text-mute">{label}</span>
      <span className="text-right font-medium text-ink">{children}</span>
    </div>
  );
}

function EmptyHistory({ children }) {
  return <p className="rounded-lg border border-dashed border-hairline px-3 py-4 text-center text-caption-sm text-mute">{children}</p>;
}

function EventDetailModal({ event, onClose }) {
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
        if (!isCancelled) setLoadError('상세 정보를 불러오지 못해 목록에 표시된 정보만 보여드립니다.');
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

  const visibleDetail = detail?.event_no != null
    && String(detail.event_no) === String(event.event_no)
    ? detail
    : event;
  const camera = visibleDetail.cctv || {};
  const cctvName = visibleDetail.cctv_name || camera.cctv_name || `CCTV #${visibleDetail.cctv_no || '-'}`;
  const cctvLocation = visibleDetail.cctv_location || camera.cctv_location || '위치 정보 없음';
  const mediaItems = Array.isArray(visibleDetail.media)
    ? visibleDetail.media
    : visibleDetail.thumbnail_url
      ? [{ media_url: visibleDetail.thumbnail_url, media_is_primary: true }]
      : [];
  const activeMedia = mediaItems[activeMediaIndex] || mediaItems[0] || null;
  const alertItems = Array.isArray(visibleDetail.alerts)
    ? visibleDetail.alerts
    : visibleDetail.alert
      ? [visibleDetail.alert]
      : [];
  const reportItems = Array.isArray(visibleDetail.reports)
    ? visibleDetail.reports
    : visibleDetail.report
      ? [visibleDetail.report]
      : [];
  const confidence = Number(visibleDetail.event_confidence);
  const hasConfidence = Number.isFinite(confidence);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs"
      onClick={(clickEvent) => {
        if (clickEvent.target === clickEvent.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dashboard-event-detail-title"
        style={{ width: '840px', minWidth: '320px', maxWidth: '95vw' }}
        className="max-h-[calc(100vh-2rem)] bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col shrink-0 box-border"
        onClick={(clickEvent) => clickEvent.stopPropagation()}
      >
        <div className="p-5 border-b border-hairline flex items-center justify-between gap-4 bg-surface-soft/60 shrink-0 rounded-t-2xl">
          <div className="min-w-0 flex items-center gap-3">
            <div className="p-2 bg-red-500/10 text-red-500 rounded-xl border border-red-500/20 shrink-0">
              <Flame className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2 py-0.5 bg-red-600 text-white font-bold rounded text-[11px]">
                  감지 사건 #{visibleDetail.event_no}
                </span>
                {hasConfidence && (
                  <span className="text-xs text-mute font-mono">
                    신뢰도 {Math.round(confidence * 100)}%
                  </span>
                )}
              </div>
              <h2 id="dashboard-event-detail-title" className="mt-1 text-heading-sm font-bold text-ink truncate">
                {cctvName} 감지 상세
              </h2>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-mute hover:text-ink hover:bg-surface-soft transition-colors shrink-0 focus:outline-none focus-visible:outline-none"
            aria-label="상세보기 닫기"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 max-h-[75vh] overflow-y-auto space-y-5">
          {isLoading && (
            <div className="flex items-center gap-2 rounded-lg border border-hairline bg-surface-soft px-3 py-2 text-caption-sm text-body">
              <Loader2 className="w-4 h-4 animate-spin shrink-0" />
              상세 미디어와 처리 이력을 불러오는 중입니다.
            </div>
          )}

          {loadError && (
            <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-caption-sm text-amber-700">
              {loadError}
            </p>
          )}

          <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
            <div className="md:col-span-7 space-y-3">
              <div className="aspect-video bg-black rounded-xl overflow-hidden border border-hairline relative">
                {getMediaUrl(activeMedia) ? (
                  <img
                    src={getMediaUrl(activeMedia)}
                    alt={`${cctvName} 감지 이미지`}
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-mute gap-2">
                    <ImageIcon className="w-10 h-10" />
                    <span className="text-caption-sm">저장된 감지 이미지가 없습니다.</span>
                  </div>
                )}
              </div>

              {mediaItems.length > 1 && (
                <div className="flex gap-2 overflow-x-auto pb-1" aria-label="감지 이미지 목록">
                  {mediaItems.map((media, index) => (
                    <button
                      key={media.media_no || `${getMediaUrl(media)}-${index}`}
                      type="button"
                      onClick={() => setActiveMediaIndex(index)}
                      className={`w-16 h-12 shrink-0 overflow-hidden rounded-lg border bg-black focus:outline-none focus-visible:outline-none ${
                        index === activeMediaIndex ? 'border-red-500' : 'border-hairline'
                      }`}
                      aria-label={`감지 이미지 ${index + 1} 보기`}
                    >
                      {getMediaUrl(media) ? (
                        <img src={getMediaUrl(media)} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <ImageIcon className="w-4 h-4 mx-auto text-mute" />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="md:col-span-5 space-y-3">
              <div className="p-4 bg-surface-soft border border-hairline rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-caption-sm font-bold text-ink">
                  <MapPin className="w-4 h-4 text-red-500" />
                  카메라 위치
                </div>
                <div>
                  <p className="text-body-sm font-semibold text-ink">{cctvName}</p>
                  <p className="mt-1 text-caption-sm text-mute">{cctvLocation}</p>
                </div>
              </div>

              <div className="p-4 bg-surface-soft border border-hairline rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-caption-sm font-bold text-ink">
                  <Clock3 className="w-4 h-4 text-red-500" />
                  감지 정보
                </div>
                <DetailRow label="이벤트 상태">
                  <StatusPill tone={getEventStatusTone(visibleDetail.event_status)}>
                    {EVENT_STATUS_LABELS[visibleDetail.event_status] || visibleDetail.event_status || '확인 중'}
                  </StatusPill>
                </DetailRow>
                <DetailRow label="감지 클래스">
                  {EVENT_CLASS_LABELS[visibleDetail.event_class] || visibleDetail.event_class || '-'}
                </DetailRow>
                <DetailRow label="최초 감지">
                  {formatDateTime(visibleDetail.event_first_detected_at || visibleDetail.event_detected_at)}
                </DetailRow>
                {visibleDetail.event_detected_frames != null && (
                  <DetailRow label="감지 프레임">
                    {visibleDetail.event_detected_frames} / {visibleDetail.event_threshold_frames || '-'}
                  </DetailRow>
                )}
              </div>
            </div>
          </div>

          <section className="p-4 bg-surface-soft border border-hairline rounded-xl space-y-3">
            <h3 className="flex items-center gap-2 text-body-sm font-bold text-ink">
              <PhoneCall className="w-4 h-4 text-red-500" />
              알림 이력
            </h3>
            {alertItems.length === 0 ? (
              <EmptyHistory>연결된 알림 이력이 없습니다.</EmptyHistory>
            ) : (
              <div className="space-y-2">
                {alertItems.map((alert, index) => (
                  <div key={alert.alert_no || `${alert.alert_sent_at}-${index}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-hairline bg-canvas px-3 py-3">
                    <div className="flex items-center gap-2 text-caption-sm">
                      <span className="font-semibold text-ink">{alert.alert_channel || '알림'}</span>
                      <span className="text-mute">{formatDateTime(alert.alert_sent_at)}</span>
                    </div>
                    <StatusPill tone={getAlertStatusTone(alert.alert_status)}>
                      {ALERT_STATUS_LABELS[alert.alert_status] || alert.alert_status || '상태 없음'}
                    </StatusPill>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="p-4 bg-surface-soft border border-hairline rounded-xl space-y-3">
            <h3 className="flex items-center gap-2 text-body-sm font-bold text-ink">
              <FileText className="w-4 h-4 text-red-500" />
              119 신고 이력
            </h3>
            {reportItems.length === 0 ? (
              <EmptyHistory>연결된 119 신고 이력이 없습니다.</EmptyHistory>
            ) : (
              <div className="space-y-2">
                {reportItems.map((report, index) => (
                  <div key={report.report_no || `${report.reported_at}-${index}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-hairline bg-canvas px-3 py-3">
                    <div className="min-w-0 text-caption-sm">
                      <p className="font-semibold text-ink truncate">{report.agency_name || '119 관할 기관'}</p>
                      <p className="mt-1 text-mute">신고 {formatDateTime(report.reported_at)}</p>
                    </div>
                    <StatusPill tone={getReportStatusTone(report.report_status)}>
                      {REPORT_STATUS_LABELS[report.report_status] || report.report_status || '상태 없음'}
                    </StatusPill>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="p-4 border-t border-hairline bg-surface-soft/60 flex justify-end shrink-0 rounded-b-2xl">
          <button
            type="button"
            onClick={onClose}
            className="h-10 px-5 rounded-full bg-primary text-on-primary text-caption-sm font-semibold focus:outline-none focus-visible:outline-none"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

export default EventDetailModal;
