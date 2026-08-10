import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LogOut, Search, Bell, AlertTriangle, CheckCircle,
  Video, MapPin, Search as SearchIcon, VideoOff, X, ArrowLeft,
  ShieldCheck, Users, PlusCircle, Settings, ShieldAlert, UserCheck
} from 'lucide-react';

// 가상의 CCTV 데이터 (소유자 ownerId 및 이력 history 포함)
const INITIAL_CCTVS = [
  {
    id: 'CCTV-01',
    name: '정문 주차장',
    status: 'normal',
    location: '1F 외부 주차장 1열',
    ownerId: 'user01',
    ownerName: '홍길동',
    lat: 37.5665,
    lng: 126.9780,
    installedAt: '2026-02-10',
    history: [
      { id: 101, time: '2026-08-10 10:00:00', type: 'normal', message: '카메라 실시간 입력 상태 정상 (24fps)' },
      { id: 102, time: '2026-08-08 12:00:00', type: 'normal', message: '시설팀 정기 화소 및 클리닝 점검 완료' },
      { id: 103, time: '2026-08-01 09:30:00', type: 'system', message: 'CCTV 신규 등록 및 AI 추론 모델 할당' }
    ]
  },
  {
    id: 'CCTV-02',
    name: '후문 분리수거장',
    status: 'normal',
    location: '1F 외부 후문 담장',
    ownerId: 'user01',
    ownerName: '홍길동',
    lat: 37.5668,
    lng: 126.9785,
    installedAt: '2026-03-01',
    history: [
      { id: 201, time: '2026-08-09 18:20:00', type: 'normal', message: '담배 연기 오탐지 해제 (현장 점검 이상없음)' },
      { id: 202, time: '2026-08-07 14:10:00', type: 'system', message: '야간 인공지능 탐지 감도 자가 교정' }
    ]
  },
  {
    id: 'CCTV-03',
    name: 'A동 1층 로비',
    status: 'fire',
    location: 'A동 1F 메인 인포데스크 앞',
    ownerId: 'user02',
    ownerName: '김철수',
    lat: 37.5662,
    lng: 126.9790,
    installedAt: '2026-01-15',
    history: [
      { id: 301, time: '2026-08-10 14:45:00', type: 'fire', message: '🔥 화재 및 고온 연기 감지 (신뢰도 98.4%) - 119 자동 신고 접수' },
      { id: 302, time: '2026-08-10 14:46:00', type: 'fire', message: '관제 요원 현장 비상 전파 및 대피 방송 지시' },
      { id: 303, time: '2026-08-05 11:00:00', type: 'normal', message: '화재 감지 센서 캘리브레이션 정상' }
    ]
  },
  {
    id: 'CCTV-04',
    name: 'B동 뒷골목',
    status: 'normal',
    location: 'B동 외곽 통로',
    ownerId: 'user01',
    ownerName: '홍길동',
    lat: 37.5670,
    lng: 126.9770,
    installedAt: '2026-04-12',
    history: [
      { id: 401, time: '2026-08-09 08:00:00', type: 'normal', message: '시스템 헬스체크 응답 정상 (Ping 12ms)' }
    ]
  },
  {
    id: 'CCTV-05',
    name: '옥상 태양광 패널 구역',
    status: 'offline',
    location: 'A동 R층 옥상',
    ownerId: 'admin',
    ownerName: '최고 관리자',
    lat: 37.5655,
    lng: 126.9775,
    installedAt: '2026-05-20',
    history: [
      { id: 501, time: '2026-08-10 14:10:00', type: 'offline', message: '⚠️ RTSP 비디오 스트림 응답 시간 초과 (네트워크 오프라인)' },
      { id: 502, time: '2026-08-10 14:11:30', type: 'system', message: '시설관리팀 네트워크 점검 자가 티켓 자동 발행' }
    ]
  },
];

// 가상의 회원 목록 데이터 (관리자 전용)
const MOCK_USERS = [
  { id: 'admin', name: '최고 관리자', email: 'admin@fireguard.or.kr', role: 'admin', status: '승인' },
  { id: 'user01', name: '홍길동 (관제1팀)', email: 'gildong@fireguard.or.kr', role: 'user', status: '승인' },
  { id: 'user02', name: '김철수 (시설팀)', email: 'chulsoo@fireguard.or.kr', role: 'user', status: '승인' },
  { id: 'user03', name: '이영희 (보안팀)', email: 'younghee@fireguard.or.kr', role: 'user', status: '대기' },
];

const MOCK_LOGS = [
  { id: 1, time: '14:45:00', message: 'A동 1층 로비 화재 의심 감지', type: 'fire' },
  { id: 2, time: '14:10:00', message: 'CCTV-05 옥상 카메라 연결 끊김', type: 'offline' },
  { id: 3, time: '12:00:00', message: '시스템 정기 점검 완료', type: 'normal' },
];

// 가상의 소방서 위치 데이터
const MOCK_FIRE_STATION = {
  name: '소방서 위치',
  lat: 37.5660,
  lng: 126.9782,
  x: 50, // 화면 내 고정 좌표 (%)
  y: 40,
};

function Dashboard() {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState(null);
  const [cctvList, setCctvList] = useState(INITIAL_CCTVS);
  const [selectedCCTV, setSelectedCCTV] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // 관리자 전용 모달 상태
  const [activeAdminTab, setActiveAdminTab] = useState(null); // 'addCCTV' | 'users' | 'settings' | null
  const [userList, setUserList] = useState(MOCK_USERS);
  const [newCCTVName, setNewCCTVName] = useState('');
  const [autoNotify119, setAutoNotify119] = useState(true);

  // 소방서 위치 정보
  const [fireStation] = useState(MOCK_FIRE_STATION);

  useEffect(() => {
    // localStorage에서 현재 로그인 유저 정보 가져오기
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
      // 기본값 설정 (비로그인 접근 시 user01 홍길동으로 가정)
      const defaultUser = { id: 'user01', name: '홍길동', role: 'user' };
      setCurrentUser(defaultUser);
    }
  }, []);

  const isAdmin = currentUser?.role === 'admin';

  // 일반 사용자인 경우 본인이 소유/담당하는 CCTV만 필터링 (소유 CCTV가 없을 경우 user01 기본 할당)
  const accessibleCCTVs = cctvList.filter(cctv => {
    if (isAdmin) return true; // 관리자는 전체 조회
    // 일반 사용자는 본인이 소유한 CCTV만 조회 (테스트 목적으로 ownerId 없는 경우 user01 포함)
    return cctv.ownerId === currentUser?.id || cctv.ownerId === 'user01';
  });

  const filteredCCTVs = accessibleCCTVs.filter(cctv =>
    cctv.name.includes(searchQuery) || cctv.id.includes(searchQuery) || cctv.location?.includes(searchQuery)
  );

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

  const toggleUserRole = (userId) => {
    setUserList(prev => prev.map(u => {
      if (u.id === userId) {
        const nextRole = u.role === 'admin' ? 'user' : 'admin';
        return { ...u, role: nextRole };
      }
      return u;
    }));
  };

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

            {/* 👑 관리자가 접속하면 마이페이지 옆에 보이는 '관리자 페이지' */}
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

        {/* 좌측: GIS 지도 영역 (가짜 지도 UI로 대체) */}
        <section className="flex-1 bg-surface-soft relative border-r border-hairline overflow-hidden flex flex-col">
          {/* 상단 검색/필터 바 */}
          <div className="absolute top-4 left-4 right-4 z-10 flex gap-2">
            <div className="flex items-center bg-canvas border border-hairline rounded-full px-4 h-[36px] w-full max-w-sm">
              <SearchIcon className="w-4 h-4 text-mute mr-2" />
              <input
                type="text"
                placeholder="CCTV 이름 또는 ID 검색"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-transparent border-none outline-none w-full text-body-sm text-ink placeholder:text-mute focus:outline-none focus-visible:outline-none"
              />
            </div>
          </div>

          {/* 지도 뷰어 플레이스홀더 */}
          <div className="flex-1 w-full h-full relative">
            <div className="absolute inset-0 flex items-center justify-center text-mute pointer-events-none">
              <span className="text-heading-lg tracking-widest uppercase">GIS Map Area</span>
            </div>

            {/* 119 소방서 위치 표시 (고정 이모지) */}
            <div
              className="absolute transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center justify-center z-0 select-none cursor-default"
              style={{ top: `${fireStation.y}%`, left: `${fireStation.x}%` }}
              title={`${fireStation.name} (${fireStation.lat}, ${fireStation.lng})`}
            >
              <span className="text-2xl drop-shadow-md">🚒</span>
              <span className="text-[10px] font-bold text-ink bg-canvas/80 px-1 rounded-sm mt-1 whitespace-nowrap border border-hairline shadow-sm">
                {fireStation.name}
              </span>
            </div>

            {/* 마커 표시 */}
            {filteredCCTVs.map((cctv, index) => (
              <button
                key={cctv.id}
                onClick={() => setSelectedCCTV(cctv)}
                className={`absolute w-3 h-3 rounded-full border border-canvas transform -translate-x-1/2 -translate-y-1/2 cursor-pointer transition-transform hover:scale-125 focus:outline-none focus-visible:outline-none ${cctv.status === 'fire' ? 'bg-terminal-red' :
                  cctv.status === 'offline' ? 'bg-mute' : 'bg-terminal-green'
                  } ${selectedCCTV?.id === cctv.id ? 'ring-2 ring-focus-ring ring-offset-2 ring-offset-canvas scale-125' : ''}`}
                style={{
                  top: `${30 + (index * 15)}%`,
                  left: `${20 + (index * 12)}%`
                }}
                title={cctv.name}
              />
            ))}
          </div>
        </section>

        {/* 우측: 상세 정보 패널 */}
        <section className="w-full md:w-96 bg-canvas shrink-0 flex flex-col overflow-y-auto">
          {selectedCCTV ? (
            <div className="flex flex-col h-full">
              {/* CCTV 상세 헤더 (화재 시 반전) */}
              <div className={`p-6 border-b border-hairline ${selectedCCTV.status === 'fire' ? 'bg-surface-dark text-on-dark' : 'bg-canvas'}`}>
                {/* 뒤로가기 / 닫기 버튼 */}
                <div className="flex items-center justify-between mb-4">
                  <button
                    onClick={() => setSelectedCCTV(null)}
                    className={`flex items-center gap-1.5 text-body-sm transition-colors focus:outline-none ${selectedCCTV.status === 'fire' ? 'text-on-dark-mute hover:text-on-dark' : 'text-body hover:text-ink'}`}
                  >
                    <ArrowLeft className="w-4 h-4" />
                    <span>전체 현황으로 돌아가기</span>
                  </button>

                  <button
                    onClick={() => setSelectedCCTV(null)}
                    className={`p-1 rounded-full hover:bg-black/10 transition-colors focus:outline-none ${selectedCCTV.status === 'fire' ? 'text-on-dark-mute hover:text-on-dark' : 'text-mute hover:text-ink'}`}
                    title="닫기"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h2 className="text-heading-md">{selectedCCTV.name}</h2>
                    <p className={`text-body-sm ${selectedCCTV.status === 'fire' ? 'text-on-dark-mute' : 'text-body'}`}>{selectedCCTV.id}</p>
                  </div>
                  {selectedCCTV.status === 'fire' ? (
                    <span className="px-3 py-1 bg-terminal-red/10 text-terminal-red rounded-full text-caption-sm font-bold border border-terminal-red/20">위험 (화재)</span>
                  ) : selectedCCTV.status === 'offline' ? (
                    <span className="px-3 py-1 bg-surface-soft text-mute rounded-full text-caption-sm font-medium border border-hairline">오프라인</span>
                  ) : (
                    <span className="px-3 py-1 bg-surface-soft text-terminal-green rounded-full text-caption-sm font-medium border border-hairline">안전</span>
                  )}
                </div>
              </div>

              <div className="p-6 flex flex-col gap-8">
                {/* 실시간 영상 영역 */}
                <div>
                  <h3 className="text-body-sm-strong text-body mb-3 flex items-center gap-2">
                    <Video className="w-4 h-4" /> 실시간 화면
                  </h3>
                  <div className="w-full aspect-video bg-surface-soft border border-hairline rounded-lg flex items-center justify-center overflow-hidden relative">
                    {selectedCCTV.status === 'offline' ? (
                      <div className="flex flex-col items-center text-mute">
                        <VideoOff className="w-8 h-8 mb-2" />
                        <span className="text-body-sm-strong">카메라 연결 끊김</span>
                      </div>
                    ) : (
                      <div className="w-full h-full bg-hairline flex items-center justify-center relative">
                        <span className="text-mute text-body-sm">실시간 스트리밍 재생 영역</span>
                        {/* 화재 감지 시 BBOX 가상 표시 */}
                        {selectedCCTV.status === 'fire' && (
                          <div className="absolute top-1/4 left-1/4 w-1/3 h-1/3 border-2 border-terminal-red bg-terminal-red/10 flex items-start p-1 pointer-events-none">
                            <span className="bg-terminal-red text-white text-caption-sm px-1 font-bold">Fire 98%</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* 위치 정보 및 119 서버 연동 */}
                <div>
                  <h3 className="text-body-sm-strong text-body mb-3 flex items-center gap-2">
                    <MapPin className="w-4 h-4" /> 설치 위치 및 좌표
                  </h3>
                  <div className="bg-canvas border border-hairline rounded-lg p-3 font-mono text-code-sm text-ink space-y-1">
                    <div><span className="text-mute">설치장소:</span> {selectedCCTV.location || '미지정'}</div>
                    <div><span className="text-mute">등록자:</span> {selectedCCTV.ownerName || selectedCCTV.ownerId}</div>
                    <div><span className="text-mute">GPS:</span> {selectedCCTV.lat}, {selectedCCTV.lng}</div>
                  </div>

                  {selectedCCTV.status === 'fire' && (
                    <button className="w-full mt-3 bg-primary text-on-primary h-[36px] rounded-full text-button-md hover:bg-ink-deep transition-colors focus:outline-none flex justify-center items-center gap-2">
                      <Bell className="w-4 h-4" />
                      119 상황 전파하기
                    </button>
                  )}
                </div>

                {/* 📋 해당 CCTV 상태 변동 및 감지 이력 (History Log) */}
                <div>
                  <h3 className="text-body-sm-strong text-body mb-3 flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4" /> 상태 감지 & 이력 ({selectedCCTV.history?.length || 0}건)
                    </span>
                  </h3>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {selectedCCTV.history && selectedCCTV.history.length > 0 ? (
                      selectedCCTV.history.map(item => (
                        <div key={item.id} className="p-2.5 rounded-lg border border-hairline bg-canvas text-xs space-y-1">
                          <div className="flex items-center justify-between text-[11px] text-mute">
                            <span className="font-mono">{item.time}</span>
                            {item.type === 'fire' && <span className="text-terminal-red font-bold">화재경보</span>}
                            {item.type === 'offline' && <span className="text-amber-500 font-bold">오프라인</span>}
                            {item.type === 'normal' && <span className="text-terminal-green">정상</span>}
                            {item.type === 'system' && <span className="text-blue-500">시스템</span>}
                          </div>
                          <p className="text-ink font-medium leading-relaxed">{item.message}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-caption-sm text-mute text-center py-4">기록된 이벤트 이력이 없습니다.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* 빈 화면 (Empty State) */
            <div className="flex flex-col items-center justify-center h-full p-8 text-center text-body">
              <MapPin className="w-12 h-12 mb-4 text-mute" />
              <h3 className="text-heading-sm text-ink mb-2">CCTV를 선택해주세요</h3>
              <p className="text-body-sm mb-8">지도에서 마커를 클릭하여 상세 정보와<br />실시간 영상을 확인하세요.</p>

              <div className="w-full bg-canvas border border-hairline rounded-lg p-4 text-left">
                <h4 className="text-caption-sm text-mute uppercase tracking-wider mb-3">시스템 요약</h4>
                <ul className="space-y-2 text-body-sm text-ink">
                  <li className="flex justify-between"><span>전체 CCTV</span> <span>{cctvList.length}대</span></li>
                  <li className="flex justify-between"><span>위험 상태</span> <span className="text-terminal-red font-medium">{cctvList.filter(c => c.status === 'fire').length}대</span></li>
                  <li className="flex justify-between"><span>오프라인</span> <span className="text-mute">{cctvList.filter(c => c.status === 'offline').length}대</span></li>
                </ul>
              </div>
            </div>
          )}

          {/* 하단: 실시간 이벤트 로그 (항상 표시) */}
          <div className="border-t border-hairline mt-auto">
            <div className="px-6 py-4 bg-canvas">
              <h3 className="text-caption-sm text-mute uppercase tracking-wider mb-4">실시간 이벤트 로그</h3>
              <div className="space-y-3 max-h-48 overflow-y-auto">
                {MOCK_LOGS.map(log => (
                  <div key={log.id} className="flex gap-3 text-body-sm">
                    <span className="text-mute shrink-0 font-mono text-code-sm mt-0.5">{log.time}</span>
                    <p className={`${log.type === 'fire' ? 'text-terminal-red font-medium' : 'text-body'}`}>
                      {log.message}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

        </section>
      </main>
    </div>
  );
}

export default Dashboard;
