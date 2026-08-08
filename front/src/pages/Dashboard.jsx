import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LogOut, Search, Bell, AlertTriangle, CheckCircle,
  Video, MapPin, Search as SearchIcon, VideoOff, X, ArrowLeft,
  ShieldCheck, Users, PlusCircle, Settings, ShieldAlert, UserCheck
} from 'lucide-react';

// 가상의 CCTV 데이터
const INITIAL_CCTVS = [
  { id: 'CCTV-01', name: '정문 주차장', status: 'normal', lat: 37.5665, lng: 126.9780 },
  { id: 'CCTV-02', name: '후문 분리수거장', status: 'normal', lat: 37.5668, lng: 126.9785 },
  { id: 'CCTV-03', name: 'A동 1층 로비', status: 'fire', lat: 37.5662, lng: 126.9790 },
  { id: 'CCTV-04', name: 'B동 뒷골목', status: 'normal', lat: 37.5670, lng: 126.9770 },
  { id: 'CCTV-05', name: '옥상', status: 'offline', lat: 37.5655, lng: 126.9775 },
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
        setCurrentUser(JSON.parse(storedUser));
      } catch (e) {
        console.error(e);
      }
    } else {
      // 기본값 설정 (비로그인 접근 시)
      setCurrentUser({ id: 'guest', name: '손님', role: 'user' });
    }
  }, []);

  const isAdmin = currentUser?.role === 'admin';

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

  const filteredCCTVs = cctvList.filter(cctv =>
    cctv.name.includes(searchQuery) || cctv.id.includes(searchQuery)
  );

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
            <button className="hover:text-ink transition-colors">마이페이지</button>
            
            {/* 👑 관리자가 접속하면 마이페이지 옆에 보이는 '관리자 페이지' */}
            {isAdmin && (
              <button
                onClick={() => navigate('/admin')}
                className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400 font-bold bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 px-3 py-1 rounded-full transition-all text-xs cursor-pointer shadow-sm"
              >
                <span>👑 관리자 페이지</span>
              </button>
            )}

            <button className="text-ink transition-colors font-bold">CCTV 모니터링</button>
          </nav>

          <div className="flex items-center gap-3">
            <span className="text-xs text-mute font-medium hidden sm:inline">
              {currentUser?.name || '사용자'}님
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
                    <MapPin className="w-4 h-4" /> 119 연동 정보
                  </h3>
                  <div className="bg-canvas border border-hairline rounded-lg p-4 font-mono text-code-sm text-ink">
                    <div className="mb-2">
                      <span className="text-mute">Lat:</span> {selectedCCTV.lat}
                    </div>
                    <div>
                      <span className="text-mute">Lng:</span> {selectedCCTV.lng}
                    </div>
                  </div>

                  {selectedCCTV.status === 'fire' && (
                    <button className="w-full mt-4 bg-primary text-on-primary h-[36px] rounded-full text-button-md hover:bg-ink-deep transition-colors focus:outline-none flex justify-center items-center gap-2">
                      <Bell className="w-4 h-4" />
                      119 상황 전파하기
                    </button>
                  )}
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
