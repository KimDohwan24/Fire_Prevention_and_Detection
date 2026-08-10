import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LogOut, Search, Bell, AlertTriangle, CheckCircle,
  Video, MapPin, Search as SearchIcon, VideoOff, X, ArrowLeft,
  ShieldCheck, Users, PlusCircle, Settings, ShieldAlert, UserCheck, Loader2
} from 'lucide-react';
import { cctvApi, agencyApi, eventApi } from '../api';
import CctvPlayer from '../components/CctvPlayer';
import ItsCctvModal from '../components/ItsCctvModal';

// 가상의 CCTV 더미 mock 데이터 완전 제거 (DB 실시간 연동)
const INITIAL_CCTVS = [];

// 가상의 회원 목록 데이터 (관리자 전용)
const MOCK_USERS = [
  { id: 'admin', name: '최고 관리자', email: 'admin@fireguard.or.kr', role: 'admin', status: '승인' },
  { id: 'user01', name: '홍길동 (관제1팀)', email: 'gildong@fireguard.or.kr', role: 'user', status: '승인' },
  { id: 'user02', name: '김철수 (시설팀)', email: 'chulsoo@fireguard.or.kr', role: 'user', status: '승인' },
  { id: 'user03', name: '이영희 (보안팀)', email: 'younghee@fireguard.or.kr', role: 'user', status: '대기' },
];

const INITIAL_LOGS = [
  { id: 1, time: '14:45:00', message: 'A동 1층 로비 화재 의심 감지', type: 'fire' },
  { id: 2, time: '14:10:00', message: 'CCTV-05 옥상 카메라 연결 끊김', type: 'offline' },
  { id: 3, time: '12:00:00', message: '시스템 정기 점검 완료', type: 'normal' },
];

// 기본 소방서 위치
const MOCK_FIRE_STATION = {
  agency_no: 1,
  name: '종로소방서',
  agency_name: '종로소방서',
  lat: 37.5730,
  lng: 126.9790,
  agency_lat: 37.5730,
  agency_lng: 126.9790,
  x: 50,
  y: 35,
  address: '서울특별시 종로구 종로1길 28',
  phone: '02-760-0119',
  agency_is_active: true,
};

function Dashboard() {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState(null);
  const [cctvList, setCctvList] = useState(INITIAL_CCTVS);
  const [selectedCCTV, setSelectedCCTV] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  // 관할 소방서 및 이벤트 로그 목록 State
  const [agencyList, setAgencyList] = useState([MOCK_FIRE_STATION]);
  const [fireStation, setFireStation] = useState(MOCK_FIRE_STATION);
  const [eventLogs, setEventLogs] = useState(INITIAL_LOGS);

  // 지도 오버레이 및 탭 조작 UI State
  const [showFireStation, setShowFireStation] = useState(true);
  const [isAgencyTabOpen, setIsAgencyTabOpen] = useState(false);
  const [isItsModalOpen, setIsItsModalOpen] = useState(false);
  const [highlightedAgencyNo, setHighlightedAgencyNo] = useState(null);

  // 관리자 전용 모달 상태
  const [activeAdminTab, setActiveAdminTab] = useState(null);
  const [userList, setUserList] = useState(MOCK_USERS);
  const [newCCTVName, setNewCCTVName] = useState('');
  const [autoNotify119, setAutoNotify119] = useState(true);

  useEffect(() => {
    // 1. localStorage에서 현재 로그인 유저 정보 가져오기
    const storedUser = localStorage.getItem('currentUser');
    if (storedUser) {
      try {
        const user = JSON.parse(storedUser);
        if (user.name) {
          user.name = user.name.replace(/\s*님$/, '');
        }
        setCurrentUser(user);
      } catch (e) {
        console.error(e);
      }
    } else {
      const defaultUser = { id: 'user01', name: '홍길동', role: 'user' };
      setCurrentUser(defaultUser);
    }

    // 2. 백엔드 REST API (agencyApi, cctvApi, eventApi) 동적 DB 조회
    const fetchApiData = async () => {
      setLoading(true);

      // 2-1. 소방서 DB 조회 (agencyApi.list -> GET /api/agencies)
      try {
        const agencyRes = await agencyApi.list();
        const rawAgencies = agencyRes?.items || (Array.isArray(agencyRes) ? agencyRes : []);
        if (rawAgencies.length > 0) {
          const mappedAgencies = rawAgencies.map((ag, idx) => ({
            agency_no: ag.agency_no || idx + 1,
            name: ag.agency_name,
            agency_name: ag.agency_name,
            agency_lat: parseFloat(ag.agency_lat) || 37.5730,
            agency_lng: parseFloat(ag.agency_lng) || 126.9790,
            lat: parseFloat(ag.agency_lat) || 37.5730,
            lng: parseFloat(ag.agency_lng) || 126.9790,
            agency_endpoint: ag.agency_endpoint || 'http://127.0.0.1:6000/api/119/report',
            agency_is_active: ag.agency_is_active !== false,
            x: 50 + (idx * 22),
            y: 35 + (idx * 15),
            address: ag.agency_name === '종로소방서' ? '서울특별시 종로구 종로1길 28' : '관할 구역 긴급 센터',
            phone: '119 (비상 종합 상황실)',
          }));
          setAgencyList(mappedAgencies);
          setFireStation(mappedAgencies[0]);
        } else {
          setAgencyList([MOCK_FIRE_STATION]);
          setFireStation(MOCK_FIRE_STATION);
        }
      } catch (err) {
        console.error('소방서 DB 조회 실패, fallback 기본 소방서 설정:', err.message);
        setAgencyList([MOCK_FIRE_STATION]);
        setFireStation(MOCK_FIRE_STATION);
      }

      // 2-2. CCTV 목록 수신 (DB 및 로컬 저장소 중복 없는 병합 동기화)
      try {
        const cctvRes = await cctvApi.list();
        const rawItems = cctvRes?.items || cctvRes || [];
        const localSaved = localStorage.getItem('fireguard_cctv_list');
        let localList = [];
        if (localSaved) {
          try { localList = JSON.parse(localSaved); } catch (e) {}
        }

        if (Array.isArray(rawItems) && rawItems.length > 0) {
          const mappedCctvs = rawItems.map(item => ({
            id: `CCTV-${String(item.cctv_no).padStart(2, '0')}`,
            cctv_no: item.cctv_no,
            name: item.cctv_name,
            status: item.cctv_status === 'ACTIVE' ? 'normal' : item.cctv_status === 'INACTIVE' ? 'offline' : 'fire',
            location: item.cctv_location,
            ownerId: 'user01',
            ownerName: '홍길동',
            lat: parseFloat(item.cctv_lat) || 37.5665,
            lng: parseFloat(item.cctv_lng) || 126.9780,
            stream_url: item.cctv_stream_url,
            installedAt: item.cctv_created_at ? item.cctv_created_at.substring(0, 10) : '2026-01-01',
            history: [
              { id: 1, time: item.cctv_created_at || '2026-08-10 10:00:00', type: 'normal', message: `${item.cctv_name} 스트림 연결 정상` }
            ]
          }));

          setCctvList(mappedCctvs);
          setSelectedCCTV(mappedCctvs[0]);
          localStorage.setItem('fireguard_cctv_list', JSON.stringify(mappedCctvs));
        } else if (localList.length > 0) {
          setCctvList(localList);
          if (!selectedCCTV && localList.length > 0) setSelectedCCTV(localList[0]);
        } else {
          setCctvList(INITIAL_CCTVS);
          localStorage.setItem('fireguard_cctv_list', JSON.stringify(INITIAL_CCTVS));
        }
      } catch (err) {
        console.warn('CCTV 목록 로드 오류, 로컬 저장소 데이터로 복원:', err.message);
        const localSaved = localStorage.getItem('fireguard_cctv_list');
        if (localSaved) {
          try {
            setCctvList(JSON.parse(localSaved));
          } catch (e) {
            setCctvList(INITIAL_CCTVS);
          }
        } else {
          setCctvList(INITIAL_CCTVS);
        }
      }

      // 2-3. 실시간 이벤트 수신
      try {
        const eventRes = await eventApi.list({ size: 10 });
        const items = eventRes?.items || [];
        if (Array.isArray(items) && items.length > 0) {
          const mappedLogs = items.map(ev => ({
            id: ev.event_no,
            time: ev.event_detected_at ? ev.event_detected_at.substring(11, 19) : '14:00:00',
            message: `${ev.cctv_name || '카메라'} ${ev.event_class === 'FIRE' ? '화재 감지' : '연기 감지'} (신뢰도 ${(ev.event_confidence * 100).toFixed(1)}%)`,
            type: ev.event_status === 'CONFIRMED' || ev.event_class === 'FIRE' ? 'fire' : 'normal'
          }));
          setEventLogs(mappedLogs);
        }
      } catch (err) {
        console.warn('이벤트 로드 오류:', err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchApiData();
  }, []);

  const isAdmin = currentUser?.role === 'admin';

  // 일반 사용자인 경우 본인이 소유/담당하는 CCTV만 필터링
  const accessibleCCTVs = cctvList.filter(cctv => {
    if (isAdmin) return true;
    return cctv.ownerId === currentUser?.id || cctv.ownerId === 'user01';
  });

  const filteredCCTVs = accessibleCCTVs.filter(cctv =>
    cctv.name.includes(searchQuery) || cctv.id.includes(searchQuery) || cctv.location?.includes(searchQuery)
  );

  // 지도상 CCTV 마커 위치 구하기
  const getCctvMapPosition = (cctv, index) => {
    const stationX = fireStation?.x || 50;
    const stationY = fireStation?.y || 38;

    const presets = [
      { left: stationX + 22, top: stationY - 18 },
      { left: stationX + 24, top: stationY + 22 },
      { left: stationX - 24, top: stationY - 16 },
      { left: stationX - 25, top: stationY + 24 },
      { left: stationX,       top: stationY - 24 },
      { left: stationX,       top: stationY + 26 },
    ];

    if (index < presets.length) {
      const pos = presets[index];
      return { top: `${Math.max(10, Math.min(88, pos.top))}%`, left: `${Math.max(8, Math.min(90, pos.left))}%` };
    }

    const angle = (index * 60) * (Math.PI / 180);
    const radiusX = 26 + (index % 2) * 8;
    const radiusY = 22 + (index % 2) * 6;
    const left = Math.max(8, Math.min(90, stationX + Math.cos(angle) * radiusX));
    const top = Math.max(10, Math.min(88, stationY + Math.sin(angle) * radiusY));

    return { top: `${top}%`, left: `${left}%` };
  };

  const handleLogout = () => {
    localStorage.removeItem('currentUser');
    navigate('/login');
  };

  const handleAddCCTV = (e) => {
    e.preventDefault();
    if (!newCCTVName.trim()) return;
    const newId = `CCTV-0${cctvList.length + 1}`;
    const newCCTV = {
      id: newId,
      name: newCCTVName,
      status: 'normal',
      lat: 37.5660 + (Math.random() * 0.002 - 0.001),
      lng: 126.9780 + (Math.random() * 0.002 - 0.001),
    };
    setCctvList([...cctvList, newCCTV]);
    setNewCCTVName('');
    setActiveAdminTab(null);
    alert(`새 CCTV (${newCCTV.name})가 등록되었습니다!`);
  };

  const handleMoveToAgency = (agency) => {
    setFireStation(agency);
    setHighlightedAgencyNo(agency.agency_no);
    setIsAgencyTabOpen(false);
    setTimeout(() => {
      setHighlightedAgencyNo(null);
    }, 3500);
  };

  // ui_modal_rules 수칙 100% 준수: 고정 및 제약 너비(style) 지정 + shrink-0 + box-border
  if (loading) {
    return (
      <div className="min-h-screen bg-canvas text-ink flex flex-col items-center justify-center font-ui p-4 transition-colors duration-300">
        <div
          style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          className="shrink-0 flex flex-col items-center gap-6 p-8 rounded-2xl bg-canvas border border-hairline shadow-2xl text-center box-border"
        >
          <div className="shrink-0 relative flex items-center justify-center w-16 h-16">
            <Loader2 className="w-14 h-14 text-red-500 animate-spin shrink-0" />
            <span className="absolute text-xl animate-pulse">🔥</span>
          </div>
          <div className="shrink-0 space-y-2 w-full">
            <h3 className="font-display text-heading-md font-bold text-ink tracking-tight">
              데이터베이스 정보 수신 중
            </h3>
            <p className="text-body-sm text-mute leading-relaxed">
              CCTV 자산 데이터 및 관할 소방서, 실시간 HLS 스트림 정보를 불러오고 있습니다.
            </p>
          </div>
          <div className="shrink-0 flex items-center justify-center gap-2 px-4 h-11 rounded-full bg-surface-soft text-caption-sm font-bold text-mute border border-hairline animate-pulse w-full max-w-[340px] box-border">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping shrink-0" />
            <span className="truncate">DB 동기화 완료 대기 중...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-ui transition-colors duration-300">
      {/* 1. 상단 네비게이션 바 (GNB) */}
      <header className="flex items-center justify-between px-6 h-14 border-b border-hairline shrink-0 bg-canvas z-20">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-ink" />
            <span className="font-display text-heading-md tracking-tight">FireGuard</span>
          </div>

          {/* 권한 표시 배지 */}
          {isAdmin ? (
            <span className="flex items-center gap-1.5 text-xs bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold px-3 py-1 rounded-full border border-amber-500/30">
              <ShieldCheck className="w-4 h-4" /> 관리자 권한
            </span>
          ) : (
            <span className="text-xs bg-surface-soft text-mute px-2.5 py-1 rounded-full border border-hairline">
              일반 사용자
            </span>
          )}
        </div>

        <div className="flex items-center gap-6">
          <nav className="flex items-center gap-6 text-body-sm-strong text-body">
            <button onClick={() => navigate('/mypage')} className="hover:text-ink transition-colors cursor-pointer">마이페이지</button>

            {isAdmin && (
              <button
                onClick={() => navigate('/admin')}
                className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400 font-bold bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 px-3 py-1 rounded-full transition-all text-xs cursor-pointer shadow-sm"
              >
                <span>관리자 페이지</span>
              </button>
            )}

            <button className="text-ink transition-colors font-bold">CCTV 모니터링</button>
          </nav>

          <div className="flex items-center gap-3">
            <span className="text-xs text-white font-bold bg-neutral-900 dark:bg-neutral-800 px-3 py-1 rounded-full border border-neutral-700 hidden sm:inline-flex items-center shadow-xs">
              {currentUser?.name ? `${currentUser.name.replace(/\s*님$/, '')}님` : '사용자님'}
            </span>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 bg-primary text-on-primary px-4 h-[34px] rounded-full text-button-md hover:bg-ink-deep transition-colors focus:outline-none focus-visible:outline-none text-xs"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>로그아웃</span>
            </button>
          </div>
        </div>
      </header>

      {/* 2. 메인 레이아웃 (지도 + 우측 패널) */}
      <main className="flex flex-col md:flex-row flex-1 overflow-hidden">

        {/* 좌측: GIS 지도 영역 */}
        <section className="flex-1 bg-surface-soft relative border-r border-hairline overflow-hidden flex flex-col">
          {/* 상단 검색/필터 바 및 DB 관할 소방서 뱃지 오버레이 */}
          <div className="absolute top-4 left-4 right-4 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
            <div className="flex items-center gap-2 pointer-events-auto">
              <div className="flex items-center bg-canvas/90 backdrop-blur-md border border-hairline rounded-full px-4 h-[38px] w-full max-w-xs shadow-md">
                <SearchIcon className="w-4 h-4 text-mute mr-2" />
                <input
                  type="text"
                  placeholder="CCTV 이름 또는 ID 검색"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="bg-transparent border-none outline-none w-full text-body-sm text-ink placeholder:text-mute focus:outline-none"
                />
              </div>

              {/* 소방서 위치 ON/OFF 버튼 */}
              <button
                onClick={() => setShowFireStation(!showFireStation)}
                className={`px-3.5 h-[38px] rounded-full text-xs font-bold transition-all shadow-md flex items-center gap-1.5 cursor-pointer border ${showFireStation
                  ? 'bg-red-600 text-white border-red-500 ring-2 ring-red-500/40'
                  : 'bg-canvas/90 text-mute border-hairline hover:bg-surface-soft'
                  }`}
                title="지도에서 소방서 위치 마커 표시/숨김 토글"
              >
                <span>🚒 소방서 위치</span>
                <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-mono ${showFireStation ? 'bg-white/20 text-white font-bold' : 'bg-surface-soft text-mute'}`}>
                  {showFireStation ? 'ON' : 'OFF'}
                </span>
              </button>

              {/* ITS 공공 CCTV 위치 확인/추가 버튼 */}
              <button
                onClick={() => setIsItsModalOpen(true)}
                className="px-3.5 h-[38px] rounded-full text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white shadow-md transition-all flex items-center gap-1.5 cursor-pointer border border-amber-400"
                title="국가교통정보센터(ITS) API 발급 가능 CCTV 위치 조회"
              >
                <Video className="w-3.5 h-3.5" />
                <span>ITS 공공 CCTV 검색</span>
              </button>
            </div>

            {/* DB 동적 관할 소방서 선택 드롭다운 버튼 */}
            <div className="relative pointer-events-auto">
              <button
                onClick={() => setIsAgencyTabOpen(!isAgencyTabOpen)}
                className="flex items-center gap-2 bg-canvas/90 backdrop-blur-md border border-hairline rounded-full px-4 h-[38px] shadow-md hover:border-ink transition-all cursor-pointer text-xs font-bold text-ink"
              >
                <MapPin className="w-3.5 h-3.5 text-red-500" />
                <span>소방서: {fireStation?.name || '소방서'}</span>
              </button>

              {/* 소방서 선택 팝업 패널 */}
              {isAgencyTabOpen && (
                <div
                  style={{ width: '320px', minWidth: '280px', maxWidth: '90vw' }}
                  className="absolute right-0 top-11 z-30 bg-canvas border border-hairline rounded-2xl shadow-2xl p-3 shrink-0 box-border"
                >
                  <div className="flex items-center justify-between px-2 pb-2 border-b border-hairline mb-2">
                    <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                      🚒 소방서 목록
                    </span>
                    <button
                      onClick={() => setIsAgencyTabOpen(false)}
                      className="text-mute hover:text-ink cursor-pointer p-1"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1">
                    {agencyList.map((ag) => (
                      <div
                        key={ag.agency_no}
                        onClick={() => handleMoveToAgency(ag)}
                        className={`p-2.5 rounded-xl border text-xs cursor-pointer transition-all ${fireStation?.agency_no === ag.agency_no
                          ? 'border-red-500/50 bg-red-500/10 text-ink font-bold shadow-xs'
                          : 'border-hairline hover:border-hairline-deep bg-surface-soft text-body'
                          }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold">{ag.agency_name || ag.name}</span>
                          {ag.agency_is_active && (
                            <span className="text-[10px] text-emerald-500 font-mono bg-emerald-500/10 px-1.5 py-0.5 rounded-full border border-emerald-500/20">
                              가동 중
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-mute mt-1 truncate">{ag.address}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 가상 GIS 격자 레이아웃 */}
          <div className="w-full h-full relative bg-surface-soft flex items-center justify-center select-none overflow-hidden">
            {/* 격자 배경 그래픽 */}
            <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#374151_1px,transparent_1px)] [background-size:24px_24px] opacity-60" />

            {/* 소방서 메인 위치 마커 */}
            {showFireStation && fireStation && (
              <div
                style={{ top: `${fireStation.y || 38}%`, left: `${fireStation.x || 50}%` }}
                className={`absolute -translate-x-1/2 -translate-y-1/2 z-10 transition-all duration-500 ${highlightedAgencyNo === fireStation.agency_no ? 'scale-125 z-20' : ''
                  }`}
              >
                <div className="relative group cursor-pointer" onClick={() => setIsAgencyTabOpen(true)}>
                  <div className="w-12 h-12 rounded-full bg-red-600 border-2 border-white shadow-xl flex items-center justify-center text-white relative z-10 hover:scale-110 transition-transform">
                    <span className="text-xl">🚒</span>
                  </div>
                  <div className="absolute top-14 left-1/2 -translate-x-1/2 bg-canvas/90 backdrop-blur-md border border-hairline px-3 py-1 rounded-full shadow-lg whitespace-nowrap text-xs font-bold text-ink flex items-center gap-1.5">
                    <span>{fireStation.name}</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  </div>
                </div>
              </div>
            )}

            {/* 지도 위 CCTV 마커 렌더링 */}
            {filteredCCTVs.map((cctv, idx) => {
              const isSelected = selectedCCTV?.id === cctv.id;
              const pos = getCctvMapPosition(cctv, idx);
              const isFire = cctv.status === 'fire';
              const isOffline = cctv.status === 'offline';

              return (
                <div
                  key={cctv.id}
                  style={{ top: pos.top, left: pos.left }}
                  className={`absolute -translate-x-1/2 -translate-y-1/2 z-0 transition-all duration-300 ${isSelected ? 'scale-125 z-20' : 'hover:scale-110'
                    }`}
                >
                  <button
                    onClick={() => setSelectedCCTV(cctv)}
                    className="relative group cursor-pointer focus:outline-none"
                  >
                    {isFire && (
                      <div className="absolute -inset-2 bg-red-500/30 rounded-full animate-ping" />
                    )}
                    <div className={`w-9 h-9 rounded-full border-2 border-white shadow-lg flex items-center justify-center text-white transition-all ${isFire ? 'bg-red-600 ring-4 ring-red-500/30' : isOffline ? 'bg-neutral-500 opacity-60' : 'bg-emerald-600'
                      }`}>
                      <Video className="w-4 h-4" />
                    </div>
                    <div className="absolute top-10 left-1/2 -translate-x-1/2 bg-canvas/90 backdrop-blur-md border border-hairline px-2.5 py-0.5 rounded-full shadow-md whitespace-nowrap text-[11px] font-bold text-ink flex items-center gap-1">
                      <span>{cctv.name}</span>
                      {isFire && <span className="text-red-500 text-[10px]">🔥</span>}
                    </div>
                  </button>
                </div>
              );
            })}
          </div>
        </section>

        {/* 우측: CCTV 모니터링 및 실시간 관제 패널 */}
        <section className="w-full md:w-[460px] bg-canvas border-l border-hairline flex flex-col shrink-0 overflow-y-auto">
          {/* 비디오 및 CCTV 선택 화면 */}
          <div className="p-4 border-b border-hairline space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-body-lg-strong font-bold text-ink flex items-center gap-2">
                <Video className="w-5 h-5 text-red-500" />
                <span>실시간 CCTV 관제 스트림</span>
              </h2>
              {selectedCCTV && (
                <button
                  onClick={() => setSelectedCCTV(null)}
                  className="text-xs text-mute hover:text-ink flex items-center gap-1 cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" /> 선택 해제
                </button>
              )}
            </div>

            {/* CCTV HLS 비디오 플레이어 컴포넌트 */}
            {selectedCCTV ? (
              <div className="rounded-xl overflow-hidden border border-hairline shadow-md bg-black relative">
                <CctvPlayer
                  key={selectedCCTV.id || selectedCCTV.cctv_no}
                  cctv={selectedCCTV}
                  autoPlay={true}
                />
                <div className="p-3 bg-canvas border-t border-hairline flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-ink">{selectedCCTV.name}</span>
                    <p className="text-[11px] text-mute">{selectedCCTV.location}</p>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${selectedCCTV.status === 'fire'
                    ? 'bg-red-500/10 text-red-500 border border-red-500/20'
                    : selectedCCTV.status === 'offline'
                      ? 'bg-neutral-500/10 text-neutral-500 border border-neutral-500/20'
                      : 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                    }`}>
                    {selectedCCTV.status === 'fire' ? '화재 감지' : selectedCCTV.status === 'offline' ? '오프라인' : '정상 작동'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="h-56 rounded-xl border border-dashed border-hairline flex flex-col items-center justify-center text-center p-4 bg-surface-soft">
                <VideoOff className="w-8 h-8 text-mute mb-2" />
                <p className="text-body-sm font-bold text-ink">선택된 CCTV가 없습니다</p>
                <p className="text-caption-sm text-mute mt-1">
                  좌측 지도에서 카메라 마커를 선택하거나 아래 목록에서 클릭하세요.
                </p>
              </div>
            )}
          </div>

          {/* CCTV 관제 목록 */}
          <div className="p-4 border-b border-hairline flex-1">
            <h3 className="text-xs font-bold text-mute uppercase tracking-wider mb-3">
              등록된 CCTV 자산 ({filteredCCTVs.length}개)
            </h3>
            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {filteredCCTVs.map((cctv) => (
                <div
                  key={cctv.id}
                  onClick={() => setSelectedCCTV(cctv)}
                  className={`p-3 rounded-xl border text-xs cursor-pointer transition-all flex items-center justify-between ${selectedCCTV?.id === cctv.id
                    ? 'border-red-500/50 bg-red-500/10 text-ink font-bold shadow-xs'
                    : 'border-hairline hover:border-hairline-deep bg-canvas text-body'
                    }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2.5 h-2.5 rounded-full ${cctv.status === 'fire' ? 'bg-red-500 animate-ping' : cctv.status === 'offline' ? 'bg-neutral-400' : 'bg-emerald-500'
                      }`} />
                    <div>
                      <p className="font-bold text-ink">{cctv.name}</p>
                      <p className="text-[11px] text-mute">{cctv.location}</p>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono text-mute">{cctv.id}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 실시간 감지 로그 패널 */}
          <div className="p-4 space-y-3">
            <h3 className="text-xs font-bold text-mute uppercase tracking-wider flex items-center gap-1.5">
              <Bell className="w-3.5 h-3.5" />
              <span>실시간 AI 화재 감지 로그</span>
            </h3>
            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {eventLogs.map((log) => (
                <div key={log.id} className="p-2.5 rounded-lg border border-hairline bg-surface-soft text-xs space-y-1">
                  <div className="flex items-center justify-between text-caption-sm text-mute">
                    <span className="font-mono">{log.time}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${log.type === 'fire' ? 'bg-red-500/10 text-red-500' : 'bg-emerald-500/10 text-emerald-500'
                      }`}>
                      {log.type === 'fire' ? '경보' : '정보'}
                    </span>
                  </div>
                  <p className="text-ink font-medium">{log.message}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* ITS 공공 CCTV 검색 모달 다이얼로그 */}
      {isItsModalOpen && (
        <ItsCctvModal
          isOpen={isItsModalOpen}
          onClose={() => setIsItsModalOpen(false)}
          onSelectCctv={(newCctv) => {
            setCctvList(prev => {
              const updated = [newCctv, ...prev];
              localStorage.setItem('fireguard_cctv_list', JSON.stringify(updated));
              return updated;
            });
            setSelectedCCTV(newCctv);
            setIsItsModalOpen(false);
          }}
        />
      )}
    </div>
  );
}

export default Dashboard;
