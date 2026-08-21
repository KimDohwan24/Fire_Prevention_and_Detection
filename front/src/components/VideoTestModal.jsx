import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  FileVideo,
  Flame,
  Loader2,
  MapPin,
  Play,
  Siren,
  Video,
  X,
} from 'lucide-react';
import { resolveMediaUrl, videoTestApi } from '../api';

const TERMINAL_STATES = new Set(['SUCCEEDED', 'FAILED']);

const formatBytes = (value) => {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 1024) return `${bytes || 0} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatSeconds = (value) => {
  const seconds = Number(value);
  return Number.isFinite(seconds) ? `${seconds.toFixed(1)}초` : '-';
};

const phaseLabel = (phase) => ({
  QUEUED: '분석 대기 중',
  ANALYZING: '영상 분석 중',
  DETECTING: '화재·연기 감지 중',
  FIRE_CONFIRMED: '화재 확정 — 경보 발생',
  DISMISSED: '오탐으로 처리됨',
  COMPLETED: '분석 완료',
  FAILED: '분석 실패',
}[phase] || '분석 준비 중');

function VideoTestModal({ isOpen, onClose, cctvs = [], onStatus, onDecision }) {
  const [samples, setSamples] = useState([]);
  const [selectedSample, setSelectedSample] = useState('');
  const [selectedCctvNo, setSelectedCctvNo] = useState('');
  const [loadState, setLoadState] = useState('idle');
  const [runState, setRunState] = useState('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [job, setJob] = useState(null);
  const [decisionState, setDecisionState] = useState('idle');
  const [decisionError, setDecisionError] = useState('');
  const jobRef = useRef(null);
  const alarmCallbackRef = useRef(onStatus);
  const notifiedPhaseRef = useRef(null);
  const videoRef = useRef(null);

  useEffect(() => {
    alarmCallbackRef.current = onStatus;
  }, [onStatus]);

  useEffect(() => {
    if (!isOpen) return undefined;

    let cancelled = false;
    setSamples([]);
    setLoadState('loading');
    setErrorMessage('');
    const activeJob = jobRef.current;
    if (!activeJob || TERMINAL_STATES.has(activeJob.status)) {
      setSelectedSample('');
      setSelectedCctvNo('');
      setRunState('idle');
      setJob(null);
      jobRef.current = null;
      notifiedPhaseRef.current = null;
      setDecisionState('idle');
      setDecisionError('');
    } else {
      setRunState('running');
    }

    videoTestApi.listSamples()
      .then((response) => {
        if (cancelled) return;
        setSamples(Array.isArray(response?.items) ? response.items : []);
        setLoadState('ready');
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadState('error');
        setErrorMessage(error?.message || '샘플 영상 목록을 불러오지 못했습니다.');
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!job?.job_id) return undefined;

    let cancelled = false;
    let timer = null;
    const poll = async () => {
      try {
        const current = await videoTestApi.getJob(job.job_id);
        if (cancelled) return;
        setJob(current);
        jobRef.current = current;

        const shouldNotify = ['DETECTING', 'FIRE_CONFIRMED', 'DISMISSED'].includes(current.phase);
        const phaseKey = `${current.job_id}:${current.phase}`;
        if (shouldNotify && notifiedPhaseRef.current !== phaseKey) {
          notifiedPhaseRef.current = phaseKey;
          alarmCallbackRef.current?.(current);
        }

        if (TERMINAL_STATES.has(current.status)) {
          setRunState(current.status === 'SUCCEEDED' ? 'success' : 'error');
          if (current.error?.message) setErrorMessage(current.error.message);
          return;
        }

        timer = window.setTimeout(poll, 1000);
      } catch (error) {
        if (cancelled) return;
        setRunState('error');
        setErrorMessage(error?.message || '영상 테스트 상태를 확인하지 못했습니다.');
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [job?.job_id]);

  const selectedCctv = useMemo(
    () => cctvs.find((item) => String(item.cctv_no) === String(selectedCctvNo)),
    [cctvs, selectedCctvNo],
  );
  const selectedSampleInfo = useMemo(
    () => samples.find((sample) => sample.name === selectedSample),
    [samples, selectedSample],
  );

  const isRunning = Boolean(job && !TERMINAL_STATES.has(job.status));
  const canRun = Boolean(selectedSample && selectedCctvNo) && !isRunning;
  const finalResult = job?.result;
  const statistics = finalResult?.statistics || {};
  const evidence = Array.isArray(finalResult?.media) ? finalResult.media : [];
  const isFire = finalResult?.result === 'FIRE';
  const needsHumanReview = Boolean(
    job?.phase === 'DETECTING' && job?.human_review_required && job?.event_no,
  );

  const handleDecision = async (decision) => {
    if (!needsHumanReview || decisionState === 'saving') return;
    setDecisionState('saving');
    setDecisionError('');
    try {
      const response = await videoTestApi.decide(job.job_id, decision);
      setJob(response);
      jobRef.current = response;
      onDecision?.(decision, response);
      setDecisionState('done');
    } catch (error) {
      setDecisionState('idle');
      setDecisionError(error?.message || '관제자 판단을 반영하지 못했습니다.');
    }
  };

  const handleRun = async () => {
    if (!canRun) return;
    setRunState('running');
    setErrorMessage('');
    setJob(null);
    jobRef.current = null;
    notifiedPhaseRef.current = null;
    setDecisionState('idle');
    setDecisionError('');
    try {
      const response = await videoTestApi.runSample({
        sample_name: selectedSample,
        cctv_no: Number(selectedCctvNo),
      });
      setJob(response);
      jobRef.current = response;
    } catch (error) {
      setRunState('error');
      setErrorMessage(error?.message || '영상 테스트 작업을 시작하지 못했습니다.');
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="video-test-modal-title"
        style={{ width: '720px', minWidth: '320px', maxWidth: '95vw' }}
        className="bg-canvas border border-hairline rounded-2xl shadow-2xl overflow-hidden shrink-0 flex flex-col box-border max-h-[90vh]"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-hairline shrink-0 bg-surface-soft/50">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-xl bg-red-500/10 border border-red-500/30 text-red-500 shrink-0">
              <Flame className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h3 id="video-test-modal-title" className="font-display text-body-lg-strong font-bold text-ink truncate">
                AI 영상 화재 판정 테스트
              </h3>
              <p className="text-caption-sm text-mute truncate">
                요청 후 백그라운드에서 분석하며, 화재 확정 순간 즉시 화면 경보를 표시합니다.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-mute hover:text-ink transition-colors p-1.5 rounded-lg hover:bg-surface-soft cursor-pointer shrink-0 focus:outline-none focus-visible:outline-none"
            aria-label="영상 테스트 닫기"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 max-h-[75vh] overflow-y-auto space-y-5">
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-caption-sm text-amber-700">
            선택한 CCTV의 실시간 스트림은 변경되지 않습니다. 테스트 경보와 119 신고는 모의 처리로만 기록되며 실제 신고는 발생하지 않습니다.
          </div>

          <section className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <h4 className="text-body-sm font-bold text-ink flex items-center gap-2">
                <Video className="w-4 h-4 text-red-500" />
                CCTV 선택
              </h4>
              <span className="text-caption-sm text-mute">{cctvs.length}대</span>
            </div>
            {cctvs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-hairline px-4 py-5 text-center text-caption-sm text-mute">
                선택할 수 있는 등록 CCTV가 없습니다.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {cctvs.map((cctv) => {
                  const isSelected = String(cctv.cctv_no) === String(selectedCctvNo);
                  return (
                    <button
                      key={cctv.cctv_no}
                      type="button"
                      disabled={isRunning}
                      onClick={() => setSelectedCctvNo(String(cctv.cctv_no))}
                      className={`text-left p-3 rounded-xl border transition-colors cursor-pointer disabled:cursor-wait disabled:opacity-60 focus:outline-none focus-visible:outline-none ${isSelected ? 'border-red-500 bg-red-500/10' : 'border-hairline bg-surface-soft hover:border-red-500/50'}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-body-sm font-bold text-ink truncate">
                          {cctv.name || cctv.cctv_name || `CCTV #${cctv.cctv_no}`}
                        </span>
                        <span className="text-caption-sm font-mono text-mute shrink-0">#{cctv.cctv_no}</span>
                      </div>
                      <p className="mt-1 text-caption-sm text-mute flex items-center gap-1 truncate">
                        <MapPin className="w-3.5 h-3.5 shrink-0" />
                        {cctv.location || cctv.cctv_location || '위치 정보 없음'}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <h4 className="text-body-sm font-bold text-ink flex items-center gap-2">
                <FileVideo className="w-4 h-4 text-red-500" />
                샘플 영상 선택
              </h4>
              <span className="text-caption-sm text-mute">ai-model/samples</span>
            </div>
            {loadState === 'loading' && (
              <div className="flex items-center justify-center gap-2 rounded-xl border border-hairline px-4 py-6 text-caption-sm text-mute">
                <Loader2 className="w-4 h-4 animate-spin" />
                샘플 영상 목록을 불러오는 중입니다.
              </div>
            )}
            {loadState === 'error' && (
              <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-caption-sm text-red-600">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{errorMessage}</span>
              </div>
            )}
            {loadState === 'ready' && samples.length === 0 && (
              <div className="rounded-xl border border-dashed border-hairline px-4 py-5 text-center text-caption-sm text-mute">
                samples 폴더에 테스트 영상이 없습니다.
              </div>
            )}
            {loadState === 'ready' && samples.length > 0 && (
              <div className="space-y-2">
                {samples.map((sample) => {
                  const isSelected = sample.name === selectedSample;
                  return (
                    <button
                      key={sample.name}
                      type="button"
                      disabled={isRunning}
                      onClick={() => setSelectedSample(sample.name)}
                      className={`w-full text-left p-3 rounded-xl border transition-colors cursor-pointer disabled:cursor-wait disabled:opacity-60 flex items-center justify-between gap-3 focus:outline-none focus-visible:outline-none ${isSelected ? 'border-red-500 bg-red-500/10' : 'border-hairline bg-surface-soft hover:border-red-500/50'}`}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <FileVideo className="w-4 h-4 text-red-500 shrink-0" />
                        <span className="text-body-sm font-semibold text-ink truncate">{sample.name}</span>
                      </span>
                      <span className="text-caption-sm text-mute shrink-0">{formatBytes(sample.size_bytes)}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {selectedSampleInfo?.preview_url && (
            <section className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-body-sm font-bold text-ink flex items-center gap-2">
                  <Play className="w-4 h-4 text-red-500" />
                  선택 영상 미리보기
                </h4>
                <span className="text-caption-sm text-mute">AI 분석 원본</span>
              </div>
              <div className="rounded-xl overflow-hidden border border-hairline bg-black aspect-video">
                <video
                  ref={videoRef}
                  key={selectedSampleInfo.preview_url}
                  src={resolveMediaUrl(selectedSampleInfo.preview_url)}
                  controls
                  muted
                  preload="metadata"
                  className="w-full h-full object-contain"
                />
              </div>
            </section>
          )}

          {job && !TERMINAL_STATES.has(job.status) && (
            <div className={`rounded-xl border px-4 py-4 space-y-2 ${job.phase === 'DETECTING' ? 'border-amber-500/40 bg-amber-500/10' : job.phase === 'DISMISSED' ? 'border-slate-400/40 bg-slate-500/10' : 'border-red-500/30 bg-red-500/10'}`}>
              <div className={`flex items-center gap-2 ${job.phase === 'DETECTING' ? 'text-amber-700' : job.phase === 'DISMISSED' ? 'text-slate-600' : 'text-red-600'}`}>
                {job.alarm_triggered ? <Siren className="w-5 h-5 animate-pulse" /> : <Loader2 className="w-5 h-5 animate-spin" />}
                <p className="text-body-sm font-bold">{phaseLabel(job.phase)}</p>
              </div>
              <p className="text-caption-sm text-mute">
                {selectedCctv?.name || `CCTV #${job.cctv_no}`} · {job.sample_name}
              </p>
              <p className="text-caption-sm text-mute">
                처리 {job.processed_frames}프레임 · 양성 {job.positive_frames}/{job.threshold_frames}프레임
                {job.first_detected_offset_sec != null && ` · 최초 감지 ${formatSeconds(job.first_detected_offset_sec)}`}
              </p>
              {job.alarm_triggered && (
                <div className="rounded-lg border border-red-500/30 bg-red-600 px-3 py-2 text-xs font-bold text-white">
                  화재 확정 기준에 도달했습니다. 상단 관제 경보가 발생했습니다.
                </div>
              )}
            </div>
          )}

          {needsHumanReview && (
            <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 space-y-3">
              <div>
                <p className="text-body-sm font-bold text-amber-800">관제자 판단 필요</p>
                <p className="mt-1 text-caption-sm text-amber-700">
                  최초 화염 감지 이미지를 확인한 뒤 화재 여부를 선택하세요. 선택하지 않으면 AI 분석이 계속됩니다.
                </p>
              </div>
              {job.first_detection_media_url && (
                <img
                  src={resolveMediaUrl(job.first_detection_media_url)}
                  alt="최초 화염 감지 증거"
                  className="w-full max-h-64 object-contain rounded-lg bg-black border border-amber-500/30"
                />
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleDecision('CONFIRM_FIRE')}
                  disabled={decisionState === 'saving'}
                  className="h-10 px-4 rounded-full bg-red-600 hover:bg-red-700 text-white text-xs font-bold disabled:opacity-50 cursor-pointer disabled:cursor-wait"
                >
                  {decisionState === 'saving' ? '처리 중...' : '119 신고 (테스트)'}
                </button>
                <button
                  type="button"
                  onClick={() => handleDecision('DISMISS')}
                  disabled={decisionState === 'saving'}
                  className="h-10 px-4 rounded-full border border-amber-600/40 bg-canvas hover:bg-amber-500/10 text-amber-800 text-xs font-bold disabled:opacity-50 cursor-pointer disabled:cursor-wait"
                >
                  오탐 처리
                </button>
              </div>
              {decisionError && <p className="text-xs font-semibold text-red-600">{decisionError}</p>}
            </div>
          )}

          {job?.alarm_triggered && job.media_url && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 space-y-2">
              <p className="text-caption-sm font-bold text-red-600 flex items-center gap-1.5">
                <Siren className="w-3.5 h-3.5" /> 화재 확정 시점 AI 증거 이미지
              </p>
              <img src={resolveMediaUrl(job.media_url)} alt="화재 확정 시점 AI 증거" className="w-full max-h-64 object-contain rounded-lg bg-black" />
            </div>
          )}

          {runState === 'error' && (
            <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-caption-sm text-red-600">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{errorMessage || '영상 분석에 실패했습니다.'}</span>
            </div>
          )}

          {runState === 'success' && finalResult && (
            <section className="space-y-3 rounded-xl border border-hairline bg-surface-soft p-4">
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-body-sm font-bold text-ink flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  최종 분석 결과
                </h4>
                <span className={`px-2.5 py-1 rounded-full text-caption-sm font-bold border ${isFire ? 'bg-red-500/10 border-red-500/30 text-red-600' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-700'}`}>
                  {finalResult.result}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div className="rounded-lg border border-hairline bg-canvas p-2.5"><p className="text-[10px] text-mute">CCTV</p><p className="mt-1 text-caption-sm font-bold text-ink">#{finalResult.cctv_no}</p></div>
                <div className="rounded-lg border border-hairline bg-canvas p-2.5"><p className="text-[10px] text-mute">검출/기준</p><p className="mt-1 text-caption-sm font-bold text-ink">{finalResult.event_detected_frames} / {finalResult.event_threshold_frames}</p></div>
                <div className="rounded-lg border border-hairline bg-canvas p-2.5"><p className="text-[10px] text-mute">신뢰도</p><p className="mt-1 text-caption-sm font-bold text-ink">{Number.isFinite(Number(finalResult.event_confidence)) ? `${Math.round(Number(finalResult.event_confidence) * 100)}%` : '-'}</p></div>
                <div className="rounded-lg border border-hairline bg-canvas p-2.5"><p className="text-[10px] text-mute">처리 프레임</p><p className="mt-1 text-caption-sm font-bold text-ink">{finalResult.event_processed_frames}</p></div>
              </div>

              <div className="text-caption-sm text-mute space-y-1">
                <p className="flex items-center gap-1.5"><Clock3 className="w-3.5 h-3.5" /> 영상: {finalResult.video?.name || selectedSample} · {formatSeconds(finalResult.video?.duration_sec)}</p>
                <p>최초 검출: {formatSeconds(statistics.first_detected_offset_sec)} · 확정: {formatSeconds(statistics.confirmed_offset_sec)}</p>
                <p>저장 이벤트 #{finalResult.event_no} · 테스트 이벤트로 저장됨</p>
              </div>

              <div>
                <p className="mb-2 text-caption-sm font-bold text-ink flex items-center gap-1.5"><Flame className="w-3.5 h-3.5 text-red-500" /> 증거 이미지 ({evidence.length}장)</p>
                {evidence.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {evidence.map((media) => (
                      <div key={media.media_no || media.media_url} className="aspect-video rounded-lg overflow-hidden bg-black border border-hairline">
                        <img src={resolveMediaUrl(media.media_url)} alt="AI 증거 이미지" className="w-full h-full object-contain" />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}
        </div>

        <div className="px-6 py-4 border-t border-hairline shrink-0 bg-surface-soft/30 flex items-center justify-between gap-3">
          <p className="text-caption-sm text-mute truncate">
            {selectedCctv ? `${selectedCctv.name} (#${selectedCctv.cctv_no})` : 'CCTV를 선택하세요'} · {selectedSample || '샘플 영상을 선택하세요'}
          </p>
          <div className="flex items-center gap-2 shrink-0">
            <button type="button" onClick={onClose} className="h-10 px-4 rounded-full border border-hairline hover:bg-surface-soft text-body-sm font-bold text-mute transition-colors cursor-pointer focus:outline-none focus-visible:outline-none">닫기</button>
            <button type="button" onClick={handleRun} disabled={!canRun} className="h-10 px-4 rounded-full bg-red-600 hover:bg-red-700 text-white text-body-sm font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 focus:outline-none focus-visible:outline-none">
              {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {runState === 'success' ? '다시 분석' : '분석 시작'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default VideoTestModal;
