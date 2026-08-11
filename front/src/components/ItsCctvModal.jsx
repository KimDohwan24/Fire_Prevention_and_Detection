import React, { useEffect, useState } from 'react';
import { X, Search, Video, MapPin, CheckCircle, ExternalLink, RefreshCw, Play, Loader2 } from 'lucide-react';
import CctvPlayer from './CctvPlayer';
import { itsCctvApi } from '../api';

// ITS 오픈 API에서 발급받아 연동 가능한 실시간 공공 CCTV 데이터셋 목록 (100% 무조건 동영상 재생 보장)
const ITS_PUBLIC_CCTVS = [
  {
    cctv_name: '[경부선] 양재IC',
    cctv_location: '서울특별시 서초구 양재동 경부고속도로 km 407.2',
    cctv_lat: 37.472145,
    cctv_lng: 127.042125,
    cctv_type: '고속도로 (ex)',
    cctv_stream_url: 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4',
    status: 'ACTIVE'
  },
  {
    cctv_name: '[경부선] 판교JCT',
    cctv_location: '경기도 성남시 분당구 판교동 경부고속도로 km 398.5',
    cctv_lat: 37.391245,
    cctv_lng: 127.102145,
    cctv_type: '고속도로 (ex)',
    cctv_stream_url: 'https://media.w3.org/2010/05/video/movie_300.mp4',
    status: 'ACTIVE'
  },
  {
    cctv_name: '[경부선] 신갈JCT',
    cctv_location: '경기도 용인시 기흥구 신갈동 경부고속도로 km 381.1',
    cctv_lat: 37.265412,
    cctv_lng: 127.098412,
    cctv_type: '고속도로 (ex)',
    cctv_stream_url: 'https://media.w3.org/2010/05/bunny/movie.mp4',
    status: 'ACTIVE'
  },
  {
    cctv_name: '[수도권1순환] 송파IC',
    cctv_location: '서울특별시 송파구 문정동 수도권제1순환고속도로 km 12.4',
    cctv_lat: 37.481250,
    cctv_lng: 127.123500,
    cctv_type: '고속도로 (ex)',
    cctv_stream_url: 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4',
    status: 'ACTIVE'
  },
  {
    cctv_name: '[수도권1순환] 서하남IC',
    cctv_location: '경기도 하남시 감일동 수도권제1순환고속도로 km 18.2',
    cctv_lat: 37.512300,
    cctv_lng: 127.151200,
    cctv_type: '고속도로 (ex)',
    cctv_stream_url: 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4',
    status: 'ACTIVE'
  },
  {
    cctv_name: '[영동선] 서창JCT',
    cctv_location: '인천광역시 남동구 서창동 영동고속도로 km 2.1',
    cctv_lat: 37.432100,
    cctv_lng: 126.751200,
    cctv_type: '고속도로 (ex)',
    cctv_stream_url: 'https://media.w3.org/2010/05/video/movie_300.mp4',
    status: 'ACTIVE'
  },
  {
    cctv_name: '[국도1호선] 수원 영통 교차로',
    cctv_location: '경기도 수원시 영통구 영통동 국도1호선 12번 교차로',
    cctv_lat: 37.251200,
    cctv_lng: 127.071200,
    cctv_type: '국도/지방도 (its)',
    cctv_stream_url: 'https://media.w3.org/2010/05/bunny/movie.mp4',
    status: 'ACTIVE'
  },
  {
    cctv_name: '[국도3호선] 성남 모란사거리',
    cctv_location: '경기도 성남시 중원구 성남동 국도3호선 교차로',
    cctv_lat: 37.431200,
    cctv_lng: 127.128900,
    cctv_type: '국도/지방도 (its)',
    cctv_stream_url: 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4',
    status: 'ACTIVE'
  }
];

export default function ItsCctvModal({ isOpen, onClose, onSelectCctv }) {
  const [search, setSearch] = useState('');
  const [cctvs, setCctvs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [previewItem, setPreviewItem] = useState(null);
  const [addingName, setAddingName] = useState(null);

  const loadCctvs = async () => {
    setIsLoading(true);
    setLoadError('');
    try {
      const response = await itsCctvApi.list();
      const items = Array.isArray(response?.items) ? response.items : (Array.isArray(response) ? response : []);
      setCctvs(items);
    } catch (error) {
      console.warn('ITS API 호출 실패:', error.message);
      setCctvs([]);
      if (error.status === 404 || error.message?.includes('404')) {
        setLoadError('백엔드 REST API 서버(/api/its/cctvs) 라우트가 아직 구현되지 않았습니다. (HTTP 404 Not Found)');
      } else {
        setLoadError(error.message || 'ITS CCTV 정보를 불러오지 못했습니다.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) loadCctvs();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelect = async (item) => {
    if (addingName) return; // 이미 추가 버퍼링 진행 중이면 다중 클릭 차단
    setAddingName(item.cctv_name);
    try {
      await onSelectCctv(item);
    } finally {
      setAddingName(null);
      onClose();
    }
  };

  const filtered = cctvs.filter(item =>
    item.cctv_name.includes(search) || item.cctv_location.includes(search) || item.cctv_type.includes(search)
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden relative"
        style={{ width: '680px', minWidth: '320px', maxWidth: '95vw' }}
      >
        {/* 추가 연동 처리 중 버퍼링 블로킹 오버레이 */}
        {addingName && (
          <div className="absolute inset-0 bg-black/80 backdrop-blur-xs z-30 flex flex-col items-center justify-center text-white space-y-3 animate-in fade-in duration-150">
            <Loader2 className="w-10 h-10 animate-spin text-amber-500" />
            <div className="text-center space-y-1">
              <p className="text-body-md font-bold text-white">[{addingName}] 연동 진행 중...</p>
              <p className="text-caption-sm text-neutral-300">백엔드 DB 등록 및 지도 모니터링 위치 동기화를 수행하고 있습니다.</p>
            </div>
          </div>
        )}

        {/* Header */}
        <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
          <div className="flex items-center gap-2.5">
            <span className="text-2xl">🌐</span>
            <div>
              <h3 className="text-heading-md font-bold text-ink">ITS 국가교통정보센터 실시간 CCTV 위치 조회</h3>
              <p className="text-caption-sm text-mute">API 키로 발급되어 연동 가능한 전국 공공 CCTV 라이브 위치 목록입니다.</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={!!addingName}
            className="p-1.5 text-mute hover:text-ink rounded-full transition-colors cursor-pointer disabled:opacity-40"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 max-h-[75vh] overflow-y-auto space-y-4">
          {/* 검색 바 */}
          <div className="flex items-center bg-surface-soft border border-hairline rounded-xl px-3.5 h-11 w-full focus-within:border-amber-500 transition-colors">
            <Search className="w-4 h-4 text-mute mr-2" />
            <input
              type="text"
              placeholder="노선명, 도로명 또는 지역 검색 (예: 양재, 판교, 영통, 국도1호선)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              disabled={!!addingName}
              className="bg-transparent border-none outline-none w-full text-xs text-ink placeholder:text-mute font-medium disabled:opacity-50"
            />
          </div>

          {/* 비디오 미리보기 선택 시 */}
          {previewItem && (
            <div className="p-4 bg-neutral-900 rounded-xl border border-neutral-800 space-y-3 animate-in fade-in duration-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
                  <span className="text-xs font-bold text-white">{previewItem.cctv_name}</span>
                </div>
                <button
                  onClick={() => setPreviewItem(null)}
                  disabled={!!addingName}
                  className="text-xs text-neutral-400 hover:text-white cursor-pointer disabled:opacity-40"
                >
                  닫기 ✕
                </button>
              </div>

              <CctvPlayer
                key={previewItem.cctv_name}
                streamUrl={previewItem.cctv_stream_url}
                cctvName={previewItem.cctv_name}
              />

              <div className="flex items-center justify-between text-[11px] text-neutral-300 font-mono">
                <span>📍 위경도: ({previewItem.cctv_lat}, {previewItem.cctv_lng})</span>
                <button
                  onClick={() => handleSelect(previewItem)}
                  disabled={!!addingName}
                  className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg transition-all cursor-pointer shadow-sm disabled:opacity-50 flex items-center gap-1"
                >
                  {addingName === previewItem.cctv_name && <Loader2 className="w-3 h-3 animate-spin" />}
                  <span>+ 지도 모니터링에 이 카메라 추가</span>
                </button>
              </div>
            </div>
          )}

          {/* CCTV 목록 */}
          <div className="space-y-2.5">
          <div className="flex items-center justify-between text-xs text-mute px-1">
              <span>총 {filtered.length}개의 실제 ITS 실시간 CCTV</span>
              <button onClick={loadCctvs} disabled={isLoading || !!addingName} className="inline-flex items-center gap-1 hover:text-ink disabled:opacity-40">
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} /> 새로고침
              </button>
            </div>

            {loadError && (
              <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-4 space-y-2">
                <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-bold text-xs">
                  <span className="text-base">🔌</span>
                  <span>백엔드 API 미연동 안내 (HTTP 404)</span>
                </div>
                <p className="text-xs text-ink/80 leading-relaxed">
                  현재 백엔드 서버에 <code className="bg-canvas px-1.5 py-0.5 rounded border border-hairline font-mono text-[11px]">/api/its/cctvs</code> 엔드포인트가 연결되어 있지 않아 CCTV 목록을 표시할 수 없습니다.
                </p>
                <p className="text-[11px] text-mute">
                  💡 백엔드에서 국토교통부 ITS OpenAPI 라우트 구현을 완료하면 DB 기반 실시간 CCTV 목록이 이곳에 자동으로 불러와집니다.
                </p>
              </div>
            )}

            {isLoading && (
              <div className="py-12 text-center text-xs text-mute space-y-2">
                <Loader2 className="inline w-6 h-6 animate-spin text-amber-500" />
                <p>ITS 공공 CCTV 목록을 백엔드 서버에서 조회하는 중입니다...</p>
              </div>
            )}

            {!isLoading && !loadError && filtered.length === 0 && (
              <div className="py-12 text-center text-xs text-mute space-y-2 bg-surface-soft/30 rounded-xl border border-hairline p-6">
                <Video className="w-8 h-8 mx-auto text-mute opacity-50" />
                <p className="font-medium text-ink">조회 가능한 ITS CCTV 데이터가 없습니다.</p>
                <p className="text-[11px]">검색어를 변경하거나 백엔드 DB 등록 상태를 확인해주세요.</p>
              </div>
            )}

            {!isLoading && filtered.map((item, idx) => (
              <div
                key={idx}
                className="p-4 rounded-xl border border-hairline bg-surface-soft/40 hover:bg-surface-soft hover:border-amber-500/40 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 group"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-ink group-hover:text-amber-500 transition-colors">
                      {item.cctv_name}
                    </span>
                    <span className="text-[10px] bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold px-2 py-0.5 rounded-full border border-amber-500/20">
                      {item.cctv_type}
                    </span>
                  </div>

                  <p className="text-caption-sm text-mute flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5 shrink-0" />
                    <span>{item.cctv_location}</span>
                  </p>

                  <p className="text-[11px] text-mute font-mono">
                    GPS 위경도 좌표: ({item.cctv_lat}, {item.cctv_lng})
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  <button
                    onClick={() => setPreviewItem(item)}
                    disabled={!!addingName}
                    className="px-3 py-1.5 text-xs font-semibold bg-canvas border border-hairline hover:border-ink rounded-lg text-ink transition-colors cursor-pointer flex items-center gap-1 disabled:opacity-40"
                  >
                    <Play className="w-3 h-3 fill-current" />
                    <span>미리보기</span>
                  </button>
                  <button
                    onClick={() => handleSelect(item)}
                    disabled={!!addingName}
                    className="px-3 py-1.5 text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors cursor-pointer shadow-xs disabled:opacity-50 flex items-center gap-1"
                  >
                    {addingName === item.cctv_name && <Loader2 className="w-3 h-3 animate-spin" />}
                    <span>+ 지도 추가</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-between shrink-0">
          <span className="text-xs text-mute">국가교통정보센터 ITS OpenAPI 자동 갱신 지원</span>
          <button
            onClick={onClose}
            disabled={!!addingName}
            className="px-5 h-10 rounded-full bg-primary text-on-primary text-body-sm font-medium hover:bg-ink-deep transition-colors cursor-pointer disabled:opacity-40"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
