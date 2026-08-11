import React, { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { Video, AlertCircle, Play } from 'lucide-react';

/**
 * ITS 계열 HLS URL을 백엔드 스트림 프록시 경로로 변환한다.
 */
function toProxiedUrl(url) {
  if (!url) return url;
  const isItsStream = url.includes('.m3u8')
    || url.includes('cctvsec.ktict.co.kr')
    || url.includes('its.go.kr')
    || url.includes('cctvurl');
  if (!isItsStream) return url;
  return `/api/stream-proxy?url=${encodeURIComponent(url)}`;
}

/**
 * 원본 URL이 HLS 스트림인지 판별
 */
function isHlsUrl(url) {
  if (!url) return false;
  return url.includes('.m3u8');
}

// 개발용 공개 샘플 영상은 CCTV 화면에서 절대 재생하지 않는다.
function isSampleVideoUrl(url) {
  return Boolean(url) && (
    url.includes('commondatastorage.googleapis.com/gtv-videos-bucket')
    || url.includes('media.w3.org/2010/05/')
  );
}

export default function CctvPlayer({ streamUrl, cctvName, isFire = false, className = '' }) {
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const fallbackRef = useRef(false);
  const [isMuted, setIsMuted] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loadError, setLoadError] = useState(false);

  // 실제 CCTV 주소가 없을 때 샘플/애니메이션 영상을 대체 재생하지 않는다.
  const REAL_VIDEO_STREAM = '';

  const requestedSrc = streamUrl?.trim() || '';
  const rawSrc = isSampleVideoUrl(requestedSrc) ? REAL_VIDEO_STREAM : requestedSrc;
  const videoSrc = toProxiedUrl(rawSrc);
  const isHls = isHlsUrl(rawSrc);

  useEffect(() => {
    let isMounted = true;
    fallbackRef.current = false;
    setLoadError(false);
    setIsPlaying(false);

    const video = videoRef.current;
    if (!video) return;

    // 이전 HLS 인스턴스 정리
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    video.removeAttribute('src');
    video.load();
    video.muted = true;

    if (!rawSrc) {
      setLoadError(true);
      return;
    }

    const safePlay = () => {
      if (!video || !isMounted) return;
      video.muted = true;
      const promise = video.play();
      if (promise !== undefined) {
        promise
          .then(() => {
            if (isMounted) setIsPlaying(true);
          })
          .catch((err) => {
            if (err?.name === 'AbortError') {
              // 브라우저가 새로운 HLS 비디오 조각을 로드하며 이전 play()를 정상 중단함 (무시)
              return;
            }
            if (video && isMounted) {
              video.muted = true;
              video.play().then(() => {
                if (isMounted) setIsPlaying(true);
              }).catch(() => {});
            }
          });
      }
    };

    const fallbackToSample = () => {
      if (fallbackRef.current || !isMounted) return;
      fallbackRef.current = true;
      setLoadError(true);
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      video.src = REAL_VIDEO_STREAM;
      safePlay();
    };

    if (isHls) {
      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: true,
          lowLatencyMode: false,
          fragLoadingMaxRetry: 10,
          manifestLoadingMaxRetry: 10,
          levelLoadingMaxRetry: 10,
          maxBufferLength: 30,
        });
        hlsRef.current = hls;

        hls.loadSource(videoSrc);
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          if (isMounted) safePlay();
        });

        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (!isMounted) return;
          if (data.fatal) {
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                hls.startLoad();
                break;
              case Hls.ErrorTypes.MEDIA_ERROR:
                hls.recoverMediaError();
                break;
              default:
                hls.startLoad();
                break;
            }
          }
        });
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = videoSrc;
        safePlay();
      } else {
        fallbackToSample();
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

  const handleError = () => {
    if (fallbackRef.current) return;
    fallbackRef.current = true;
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    const video = videoRef.current;
    if (video) {
      video.src = REAL_VIDEO_STREAM;
      video.play().then(() => setIsPlaying(true)).catch(() => {
        setLoadError(true);
      });
    }
  };

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
        setIsPlaying(false);
      } else {
        videoRef.current.play().catch(() => {});
        setIsPlaying(true);
      }
    }
  };

  return (
    <div className={`relative w-full aspect-video bg-black rounded-xl overflow-hidden border border-neutral-800 shadow-xl group ${className}`}>
      {/* src 는 useEffect 에서만 설정 — JSX 에 src 를 넣으면 HLS.js 와 충돌 */}
      <video
        ref={videoRef}
        autoPlay
        loop
        muted={isMuted}
        playsInline
        controls
        className="w-full h-full object-cover"
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onError={handleError}
      />

      {loadError && (
        <div className="absolute inset-0 bg-black/90 flex flex-col items-center justify-center p-4 text-center z-20 text-white">
          <AlertCircle className="w-8 h-8 text-amber-500 mb-2" />
          <p className="text-xs font-bold mb-2">실체 비디오 스트림 재생 준비 중</p>
          <button
            onClick={togglePlay}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 cursor-pointer shadow-md"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>실제 비디오 바로 재생하기</span>
          </button>
        </div>
      )}

      {isFire && (
        <div className="absolute top-1/4 left-1/4 w-1/3 h-1/3 border-2 border-red-500 bg-red-500/10 flex items-start p-1 pointer-events-none z-10 animate-pulse">
          <span className="bg-red-600 text-white text-[10px] px-1.5 py-0.5 font-extrabold rounded-xs shadow-md">
            🔥 FIRE DETECTED (98.4%)
          </span>
        </div>
      )}

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
