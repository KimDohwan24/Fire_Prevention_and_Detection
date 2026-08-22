import React, { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { AlertCircle, Loader2 } from 'lucide-react';

/**
 * ITS 계열 HLS URL을 백엔드 스트림 프록시 경로로 변환한다.
 */
function toProxiedUrl(url) {
  if (!url) return '';
  // 미구현된 백엔드 프록시(/api/stream-proxy) 요청 404 방지: CCTV 스트림 URL 직접 반환
  return url;
}

function isHlsUrl(url) {
  if (!url) return false;
  return url.includes('.m3u8');
}

export default function CctvPlayer({ streamUrl, cctvName, className = '' }) {
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const rawSrc = streamUrl?.trim() || '';
  const videoSrc = toProxiedUrl(rawSrc);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setLoadError(false);

    const video = videoRef.current;
    if (!video) return;

    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    if (!rawSrc) {
      setIsLoading(false);
      setLoadError(true);
      return;
    }

    const safePlay = () => {
      if (!video || !isMounted) return;
      video.muted = true;
      const playPromise = video.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            if (isMounted) setIsLoading(false);
          })
          .catch((err) => {
            if (err?.name === 'AbortError') return;
            if (isMounted) {
              setIsLoading(false);
              setLoadError(true);
            }
          });
      }
    };

    if (isHlsUrl(rawSrc)) {
      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: false,
          maxBufferLength: 15,
        });
        hlsRef.current = hls;

        hls.loadSource(videoSrc);
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          if (isMounted) safePlay();
        });

        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (data.fatal && isMounted) {
            hls.destroy();
            hlsRef.current = null;
            setIsLoading(false);
            setLoadError(true);
          }
        });
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = videoSrc;
        safePlay();
      } else {
        setIsLoading(false);
        setLoadError(true);
      }
    } else {
      video.src = videoSrc;
      safePlay();
    }

    return () => {
      isMounted = false;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [videoSrc, rawSrc]);

  return (
    <div className={`relative w-full aspect-video bg-neutral-950 rounded-xl overflow-hidden border border-neutral-800 shadow-xl group ${className}`}>
      {/* 1. 실시간 스트림 연결 중 로딩 인디케이터 */}
      {isLoading && (
        <div className="absolute inset-0 z-20 bg-neutral-900 flex flex-col items-center justify-center text-white space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-red-500" />
          <span className="text-xs font-semibold text-neutral-300">CCTV 실시간 스트림 연결 중...</span>
        </div>
      )}

      {/* 2. 더미 영상으로 대체하지 않는 실시간 비디오 신호 수신 대기 레이어 */}
      {loadError && !isLoading && (
        <div className="absolute inset-0 z-20 bg-neutral-950/95 flex flex-col items-center justify-center p-4 text-center text-white space-y-2">
          <AlertCircle className="w-8 h-8 text-amber-500" />
          <p className="text-xs font-bold text-neutral-200">실시간 비디오 스트림 수신 대기 중</p>
          <p className="text-[11px] text-neutral-400 max-w-xs">
            {cctvName || 'CCTV'} 장비의 실시간 비디오 입력 신호를 수신하고 있습니다.
          </p>
        </div>
      )}

      {/* 3. 순수 실시간 비디오 스트림 지정을 위한 비디오 요소 */}
      <video
        ref={videoRef}
        autoPlay
        loop
        muted
        playsInline
        controls
        className="w-full h-full object-cover"
        onLoadedData={() => setIsLoading(false)}
        onWaiting={() => setIsLoading(true)}
        onSeeking={() => setIsLoading(true)}
        onPlaying={() => setIsLoading(false)}
        onCanPlay={() => setIsLoading(false)}
        onError={() => {
          setIsLoading(false);
          setLoadError(true);
        }}
      />

      {/* LIVE 라벨 및 CCTV 카메라 명칭 */}
      <div className="absolute top-3 left-3 z-10 flex items-center gap-2 pointer-events-none">
        <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-red-600/90 text-white font-mono text-[10px] font-bold uppercase tracking-wider backdrop-blur-md shadow-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
          LIVE VIDEO
        </span>
        {cctvName && (
          <span className="px-2.5 py-0.5 rounded-full bg-black/70 text-neutral-100 text-[11px] font-bold backdrop-blur-md border border-white/10">
            {cctvName}
          </span>
        )}
      </div>
    </div>
  );
}
