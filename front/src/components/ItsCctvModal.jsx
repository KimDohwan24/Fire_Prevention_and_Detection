import React, { useEffect, useMemo, useState } from 'react';
import { X, Search, Video, MapPin, RefreshCw, Play, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import CctvPlayer from './CctvPlayer';
import { itsCctvApi } from '../api';

const PAGE_SIZE = 10;
const FETCH_SIZE = 20;

const getItemsFromResponse = (response) => {
  if (Array.isArray(response?.items)) return response.items;
  if (Array.isArray(response?.cctvs)) return response.cctvs;
  if (Array.isArray(response?.data?.items)) return response.data.items;
  if (Array.isArray(response?.data?.cctvs)) return response.data.cctvs;
  if (Array.isArray(response)) return response;
  return [];
};

const getTotalFromResponse = (response) => {
  const total = response?.total ?? response?.total_count ?? response?.data?.total ?? response?.data?.total_count;
  return Number.isFinite(Number(total)) ? Number(total) : null;
};

export default function ItsCctvModal({ isOpen, onClose, onSelectCctv, canRegister = false, canPreview = false }) {
  const [search, setSearch] = useState('');
  const [cctvs, setCctvs] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [totalCctvs, setTotalCctvs] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [previewItem, setPreviewItem] = useState(null);
  const [addingName, setAddingName] = useState(null);

  const mergeCctvs = (prev, next) => {
    const seen = new Set(prev.map((item) => item.cctv_name));
    return [...prev, ...next.filter((item) => !seen.has(item.cctv_name))];
  };

  const loadCctvs = async () => {
    setIsLoading(true);
    setLoadError('');
    setPreviewItem(null);
    setCurrentPage(1);
    try {
      const response = await itsCctvApi.list({ limit: PAGE_SIZE, offset: 0 });
      const items = getItemsFromResponse(response);
      const responseTotal = getTotalFromResponse(response);
      const total = responseTotal ?? items.length;

      if (items.length > 0) {
        setCctvs(items);
        setTotalCctvs(total);
        setHasMore(responseTotal !== null ? items.length < total : items.length === PAGE_SIZE);
      } else {
        setCctvs([]);
        setTotalCctvs(0);
        setHasMore(false);
        setLoadError('ITS API에서 조회된 CCTV가 없습니다. 백엔드 ITS API 키 설정을 확인하세요.');
      }
    } catch (error) {
      console.warn('ITS 백엔드 API 호출 실패:', error.message);
      setCctvs([]);
      setTotalCctvs(0);
      setHasMore(false);
      if (error.status === 404) {
        setLoadError('백엔드 ITS API 라우트(/api/its/cctvs)가 아직 구현되지 않았습니다.');
      } else {
        setLoadError(error.message || 'ITS CCTV 정보를 불러오지 못했습니다. 백엔드 서버 연결을 확인하세요.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const fetchNextBatch = async (offset = cctvs.length) => {
    if (isLoadingMore || !hasMore) return false;

    setIsLoadingMore(true);
    try {
      const response = await itsCctvApi.list({ limit: FETCH_SIZE, offset });
      const items = getItemsFromResponse(response);
      const responseTotal = getTotalFromResponse(response);
      const total = responseTotal ?? Math.max(totalCctvs, offset + items.length);

      setCctvs((prev) => mergeCctvs(prev, items));
      setTotalCctvs(total);
      setHasMore(responseTotal !== null ? offset + items.length < total && items.length > 0 : items.length === FETCH_SIZE);
      return items.length > 0;
    } catch (error) {
      console.warn('ITS CCTV additional load failed:', error.message);
      setHasMore(false);
      return false;
    } finally {
      setIsLoadingMore(false);
    }
  };

  useEffect(() => {
    if (isOpen) loadCctvs();
  }, [isOpen]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return cctvs;

    return cctvs.filter((item) =>
      [item.cctv_name, item.cctv_location, item.cctv_type]
        .some((value) => String(value || '').toLowerCase().includes(term))
    );
  }, [cctvs, search]);

  if (!isOpen) return null;

  const handleSelect = async (item) => {
    if (!canRegister || addingName) return;
    setAddingName(item.cctv_name);
    try {
      await onSelectCctv(item);
    } finally {
      setAddingName(null);
    }
  };

  const totalItems = search ? filtered.length : Math.max(totalCctvs, cctvs.length);
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
  const visibleTotalPages = hasMore && !search ? Math.max(totalPages, currentPage + 1) : totalPages;
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const pageItems = filtered.slice(pageStart, pageStart + PAGE_SIZE);
  const canGoPrevious = currentPage > 1;
  const canGoNext = search ? currentPage < totalPages : currentPage < visibleTotalPages;

  const movePage = async (nextPage) => {
    if (nextPage < 1 || nextPage === currentPage || addingName || isLoadingMore) return;

    const requiredCount = nextPage * PAGE_SIZE;
    if (!search && requiredCount > cctvs.length && hasMore) {
      const loaded = await fetchNextBatch(cctvs.length);
      if (!loaded && cctvs.length < (nextPage - 1) * PAGE_SIZE + 1) return;
    } else if (!search && nextPage > currentPage && hasMore) {
      fetchNextBatch(cctvs.length);
    }

    setCurrentPage(nextPage);
    setPreviewItem(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden relative"
        style={{ width: '680px', minWidth: '320px', maxWidth: '95vw' }}
      >
        {addingName && (
          <div className="absolute inset-0 bg-black/80 backdrop-blur-xs z-30 flex flex-col items-center justify-center text-white space-y-3 animate-in fade-in duration-150">
            <Loader2 className="w-10 h-10 animate-spin text-amber-500" />
            <div className="text-center space-y-1">
              <p className="text-body-md font-bold text-white">[{addingName}] 연동 진행 중...</p>
              <p className="text-caption-sm text-neutral-300">백엔드 DB 등록 및 지도 모니터링 위치 동기화를 수행하고 있습니다.</p>
            </div>
          </div>
        )}

        <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
          <div className="flex items-center gap-2.5">
            <span className="text-2xl">📹</span>
            <div>
              <h3 className="text-heading-md font-bold text-ink">ITS 국가교통정보센터 실시간 CCTV 위치 조회</h3>
              <p className="text-caption-sm text-mute">
                {canRegister
                  ? '전국 공공 CCTV 위치를 조회하고 관제용 CCTV로 등록할 수 있습니다.'
                  : '전국 공공 CCTV의 명칭, 위치, GPS 좌표를 조회할 수 있습니다.'}
              </p>
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

        <div className="p-6 max-h-[75vh] overflow-y-auto space-y-4">
          <div className="flex items-center bg-surface-soft border border-hairline rounded-xl px-3.5 h-11 w-full focus-within:border-amber-500 transition-colors">
            <Search className="w-4 h-4 text-mute mr-2" />
            <input
              type="text"
              placeholder="노선명, 도로명 또는 지역 검색"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentPage(1);
                setPreviewItem(null);
              }}
              disabled={!!addingName}
              className="bg-transparent border-none outline-none w-full text-xs text-ink placeholder:text-mute font-medium disabled:opacity-50"
            />
          </div>

          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs text-mute px-1">
              <span>총 {totalItems}개의 ITS 실시간 CCTV</span>
              <button onClick={loadCctvs} disabled={isLoading || !!addingName} className="inline-flex items-center gap-1 hover:text-ink disabled:opacity-40">
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} /> 새로고침
              </button>
            </div>

            {loadError && (
              <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-4 space-y-2">
                <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-bold text-xs">
                  <span className="text-base">⚠️</span>
                  <span>백엔드 API 미연동 안내</span>
                </div>
                <p className="text-xs text-ink/80 leading-relaxed">
                  현재 백엔드 서버에 <code className="bg-canvas px-1.5 py-0.5 rounded border border-hairline font-mono text-[11px]">/api/its/cctvs</code> 엔드포인트가 연결되어 있지 않아 CCTV 목록을 표시할 수 없습니다.
                </p>
                <p className="text-[11px] text-mute">
                  백엔드에서 국토교통부 ITS OpenAPI 라우트 구현이 완료되면 DB 기반 실시간 CCTV 목록을 자동으로 불러옵니다.
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
                <p className="text-[11px]">검색어를 변경하거나 백엔드 DB 등록 상태를 확인하세요.</p>
              </div>
            )}

            {!isLoading && pageItems.map((item) => (
              <div key={`${item.cctv_name}-${item.cctv_lat}-${item.cctv_lng}`} className="space-y-2.5">
                <div className="p-4 rounded-xl border border-hairline bg-surface-soft/40 hover:bg-surface-soft hover:border-amber-500/40 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 group">
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
                    {canRegister ? (
                      <>
                        {canPreview && (
                          <button
                            onClick={() => setPreviewItem((current) => current?.cctv_name === item.cctv_name ? null : item)}
                            disabled={!!addingName}
                            className="px-3 py-1.5 text-xs font-semibold bg-canvas border border-hairline hover:border-ink rounded-lg text-ink transition-colors cursor-pointer flex items-center gap-1 disabled:opacity-40"
                          >
                            <Play className="w-3 h-3 fill-current" />
                            <span>{previewItem?.cctv_name === item.cctv_name ? '접기' : '미리보기'}</span>
                          </button>
                        )}
                        <button
                          onClick={() => handleSelect(item)}
                          disabled={!!addingName}
                          className="px-3 py-1.5 text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors cursor-pointer shadow-xs disabled:opacity-50 flex items-center gap-1"
                        >
                          {addingName === item.cctv_name && <Loader2 className="w-3 h-3 animate-spin" />}
                          <span>+ 지도 추가</span>
                        </button>
                      </>
                    ) : (
                      <span className="px-3 py-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                        위치 조회 전용
                      </span>
                    )}
                  </div>
                </div>

                {canPreview && previewItem?.cctv_name === item.cctv_name && (
                  <div className="p-4 bg-neutral-900 rounded-xl border border-neutral-800 space-y-3 animate-in fade-in slide-in-from-top-1 duration-200">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
                        <span className="text-xs font-bold text-white">{item.cctv_name}</span>
                      </div>
                      <button
                        onClick={() => setPreviewItem(null)}
                        disabled={!!addingName}
                        className="text-xs text-neutral-400 hover:text-white cursor-pointer disabled:opacity-40"
                      >
                        닫기
                      </button>
                    </div>

                    <CctvPlayer
                      key={item.cctv_name}
                      streamUrl={item.cctv_stream_url}
                      cctvName={item.cctv_name}
                    />

                    <div className="flex items-center justify-between text-[11px] text-neutral-300 font-mono gap-3">
                      <span>위경도: ({item.cctv_lat}, {item.cctv_lng})</span>
                      <button
                        onClick={() => handleSelect(item)}
                        disabled={!!addingName}
                        className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg transition-all cursor-pointer shadow-sm disabled:opacity-50 flex items-center gap-1"
                      >
                        {addingName === item.cctv_name && <Loader2 className="w-3 h-3 animate-spin" />}
                        <span>+ 지도 모니터링에 카메라 추가</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {!isLoading && !loadError && filtered.length > 0 && (
              <div className="flex items-center justify-between gap-3 pt-2">
                <span className="text-[11px] text-mute">
                  {currentPage} / {visibleTotalPages} 페이지, 페이지당 {PAGE_SIZE}건
                  {isLoadingMore && <span className="ml-2 text-amber-500">20건 추가 조회 중...</span>}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => movePage(currentPage - 1)}
                    disabled={!canGoPrevious || !!addingName || isLoadingMore}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hairline bg-canvas text-ink hover:border-ink disabled:opacity-40 disabled:hover:border-hairline"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => movePage(currentPage + 1)}
                    disabled={!canGoNext || !!addingName || isLoadingMore}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hairline bg-canvas text-ink hover:border-ink disabled:opacity-40 disabled:hover:border-hairline"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

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
