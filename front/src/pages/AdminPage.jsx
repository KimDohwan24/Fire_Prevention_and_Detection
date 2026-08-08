import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ShieldCheck, Users, PlusCircle, Settings, LogOut,
  AlertTriangle, ArrowLeft, Video, CheckCircle, Trash2,
  Bell, Sliders, Activity, UserCheck, Search, ShieldAlert
} from 'lucide-react';

// 가상의 초기 CCTV 데이터
const INITIAL_CCTVS = [
  { id: 'CCTV-01', name: '정문 주차장', status: 'normal', location: '1F 외부', lat: 37.5665, lng: 126.9780 },
  { id: 'CCTV-02', name: '후문 분리수거장', status: 'normal', location: '1F 외부', lat: 37.5668, lng: 126.9785 },
  { id: 'CCTV-03', name: 'A동 1층 로비', status: 'fire', location: 'A동 1F', lat: 37.5662, lng: 126.9790 },
  { id: 'CCTV-04', name: 'B동 뒷골목', status: 'normal', location: 'B동 외곽', lat: 37.5670, lng: 126.9770 },
  { id: 'CCTV-05', name: '옥상', status: 'offline', location: 'A동 R층', lat: 37.5655, lng: 126.9775 },
];

// 가상의 회원 목록 데이터
const INITIAL_USERS = [
  { id: 'admin', name: '최고 관리자', email: 'admin@fireguard.or.kr', role: 'admin', status: '승인', dept: '관제총괄팀' },
  { id: 'user01', name: '홍길동', email: 'gildong@fireguard.or.kr', role: 'user', status: '승인', dept: '관제1팀' },
  { id: 'user02', name: '김철수', email: 'chulsoo@fireguard.or.kr', role: 'user', status: '승인', dept: '시설관리팀' },
  { id: 'user03', name: '이영희', email: 'younghee@fireguard.or.kr', role: 'user', status: '승인대기', dept: '보안팀' },
];

const SYSTEM_LOGS = [
  { id: 1, time: '2026-08-08 14:45:00', message: 'A동 1층 로비 화재 의심 감지 (화재 98%)', level: 'error' },
  { id: 2, time: '2026-08-08 14:10:00', message: 'CCTV-05 옥상 카메라 연결 끊김', level: 'warning' },
  { id: 3, time: '2026-08-08 12:00:00', message: '관리자(admin)가 AI 임계값을 90%로 수정함', level: 'info' },
  { id: 4, time: '2026-08-08 09:30:00', message: '시스템 정기 자가 점검 완료 (정상)', level: 'info' },
];

const AdminPage = () => {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState(null);
  const [activeTab, setActiveTab] = useState('cctv'); // 'cctv' | 'users' | 'settings' | 'logs'
  
  // 데이터 상태
  const [cctvList, setCctvList] = useState(INITIAL_CCTVS);
  const [userList, setUserList] = useState(INITIAL_USERS);
  
  // 폼 상태
  const [newCctvName, setNewCctvName] = useState('');
  const [newCctvLoc, setNewCctvLoc] = useState('');
  const [autoNotify119, setAutoNotify119] = useState(true);
  const [threshold, setThreshold] = useState(90);
  const [userSearch, setUserSearch] = useState('');

  useEffect(() => {
    const stored = localStorage.getItem('currentUser');
    if (stored) {
      try {
        const user = JSON.parse(stored);
        if (user.role !== 'admin') {
          alert('관리자만 접근 가능한 페이지입니다.');
          navigate('/dashboard');
          return;
        }
        setCurrentUser(user);
      } catch (e) {
        navigate('/login');
      }
    } else {
      navigate('/login');
    }
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('currentUser');
    navigate('/login');
  };

  // CCTV 등록
  const handleAddCCTV = (e) => {
    e.preventDefault();
    if (!newCctvName.trim()) return;
    const newId = `CCTV-0${cctvList.length + 1}`;
    const newCamera = {
      id: newId,
      name: newCctvName,
      location: newCctvLoc || '위치 미지정',
      status: 'normal',
      lat: 37.5660 + (Math.random() * 0.002 - 0.001),
      lng: 126.9780 + (Math.random() * 0.002 - 0.001),
    };
    setCctvList([...cctvList, newCamera]);
    setNewCctvName('');
    setNewCctvLoc('');
    alert(`[${newCamera.name}] 카메라가 성공적으로 등록되었습니다.`);
  };

  // CCTV 삭제
  const handleDeleteCCTV = (id) => {
    if (confirm('해당 CCTV를 모니터링 목록에서 삭제하시겠습니까?')) {
      setCctvList(cctvList.filter(c => c.id !== id));
    }
  };

  // 회원 권한 토글
  const toggleRole = (userId) => {
    setUserList(prev => prev.map(u => {
      if (u.id === userId) {
        const nextRole = u.role === 'admin' ? 'user' : 'admin';
        return { ...u, role: nextRole };
      }
      return u;
    }));
  };

  // 회원 승인
  const approveUser = (userId) => {
    setUserList(prev => prev.map(u => u.id === userId ? { ...u, status: '승인' } : u));
  };

  const filteredUsers = userList.filter(u =>
    u.name.includes(userSearch) || u.id.includes(userSearch) || u.email.includes(userSearch)
  );

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-ui transition-colors duration-300">
      {/* 1. 상단 Header */}
      <header className="h-16 px-6 border-b border-hairline bg-canvas flex items-center justify-between sticky top-0 z-30 shrink-0">
        <div className="flex items-center gap-4">
          <Link to="/dashboard" className="flex items-center gap-2 text-ink hover:opacity-80 transition-opacity">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            <span className="font-display text-heading-md tracking-tight">FireGuard</span>
          </Link>

          <span className="flex items-center gap-1 text-xs bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold px-3 py-1 rounded-full border border-amber-500/30">
            <ShieldCheck className="w-4 h-4" /> 관리자 전용 센터
          </span>
        </div>

        <div className="flex items-center gap-4">
          <Link
            to="/dashboard"
            className="flex items-center gap-1.5 text-body-sm text-mute hover:text-ink transition-colors px-3 py-1.5 rounded-full border border-hairline hover:bg-surface-soft"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>CCTV 모니터링으로 돌아가기</span>
          </Link>

          <button
            onClick={handleLogout}
            className="flex items-center gap-2 bg-primary text-on-primary px-4 py-1.5 rounded-full text-xs font-semibold hover:bg-ink-deep transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>로그아웃</span>
          </button>
        </div>
      </header>

      {/* 2. 관리자 메인 타이틀 & 탭 네비게이션 */}
      <div className="px-8 py-6 bg-surface-soft border-b border-hairline shrink-0">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-heading-lg font-bold tracking-tight text-ink flex items-center gap-2">
              <ShieldAlert className="w-6 h-6 text-amber-500" />
              시스템 통합 관리자 설정
            </h1>
            <p className="text-body-sm text-mute mt-1">
              CCTV 자산 등록, 관제 회원 권한 설정 및 화재 감지 임계값을 통합 제어합니다.
            </p>
          </div>

          {/* 탭 컨트롤 */}
          <div className="flex items-center bg-canvas border border-hairline p-1 rounded-xl gap-1 shrink-0">
            <button
              onClick={() => setActiveTab('cctv')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'cctv'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
              }`}
            >
              <Video className="w-4 h-4" />
              <span>CCTV 자산 관리 ({cctvList.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('users')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'users'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
              }`}
            >
              <Users className="w-4 h-4" />
              <span>회원 권한 ({userList.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('settings')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'settings'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
              }`}
            >
              <Settings className="w-4 h-4" />
              <span>AI 감지 설정</span>
            </button>

            <button
              onClick={() => setActiveTab('logs')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'logs'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span>감사 로그</span>
            </button>
          </div>
        </div>
      </div>

      {/* 3. 메인 콘텐츠 영역 */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-8">
        
        {/* TAB 1: CCTV 카메라 관리 */}
        {activeTab === 'cctv' && (
          <div className="space-y-8 animate-in fade-in duration-200">
            {/* 등록 폼 카드 */}
            <div className="bg-canvas border border-hairline rounded-2xl p-6 shadow-sm">
              <h2 className="text-heading-sm font-bold text-ink mb-4 flex items-center gap-2">
                <PlusCircle className="w-5 h-5 text-amber-500" />
                신규 CCTV 카메라 등록
              </h2>

              <form onSubmit={handleAddCCTV} className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-body mb-1">CCTV 명칭</label>
                  <input
                    type="text"
                    placeholder="예: C동 지하 2층 주차장"
                    value={newCctvName}
                    onChange={(e) => setNewCctvName(e.target.value)}
                    className="w-full px-4 py-2 bg-canvas border border-hairline rounded-lg text-body-sm outline-none focus:border-ink transition-colors"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-body mb-1">설치 위치 설명</label>
                  <input
                    type="text"
                    placeholder="예: C동 지하 주차장 04번 기둥 앞"
                    value={newCctvLoc}
                    onChange={(e) => setNewCctvLoc(e.target.value)}
                    className="w-full px-4 py-2 bg-canvas border border-hairline rounded-lg text-body-sm outline-none focus:border-ink transition-colors"
                  />
                </div>

                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs py-2.5 px-4 rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <PlusCircle className="w-4 h-4" />
                    CCTV 등록 추가하기
                  </button>
                </div>
              </form>
            </div>

            {/* 목록 테이블 카드 */}
            <div className="bg-canvas border border-hairline rounded-2xl overflow-hidden shadow-sm">
              <div className="p-5 border-b border-hairline flex items-center justify-between">
                <h3 className="font-bold text-body-md text-ink">등록된 CCTV 리스트 ({cctvList.length}대)</h3>
                <span className="text-xs text-mute">GIS 지도 및 관제 대시보드에 실시간 노출됩니다.</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-soft border-b border-hairline text-mute uppercase font-semibold">
                    <tr>
                      <th className="p-4">카메라 ID</th>
                      <th className="p-4">CCTV 명칭</th>
                      <th className="p-4">설치 위치</th>
                      <th className="p-4">현재 상태</th>
                      <th className="p-4 text-center">작동 관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {cctvList.map(cctv => (
                      <tr key={cctv.id} className="hover:bg-surface-soft/50 transition-colors">
                        <td className="p-4 font-mono font-bold text-ink">{cctv.id}</td>
                        <td className="p-4 font-semibold text-ink">{cctv.name}</td>
                        <td className="p-4 text-mute">{cctv.location}</td>
                        <td className="p-4">
                          {cctv.status === 'fire' ? (
                            <span className="px-2.5 py-1 bg-terminal-red/10 text-terminal-red font-bold rounded-full border border-terminal-red/20">
                              🔥 화재 감지
                            </span>
                          ) : cctv.status === 'offline' ? (
                            <span className="px-2.5 py-1 bg-surface-soft text-mute font-medium rounded-full border border-hairline">
                              🔌 연결 끊김
                            </span>
                          ) : (
                            <span className="px-2.5 py-1 bg-terminal-green/10 text-terminal-green font-medium rounded-full border border-terminal-green/20">
                              🟢 정상 작동
                            </span>
                          )}
                        </td>
                        <td className="p-4 text-center">
                          <button
                            onClick={() => handleDeleteCCTV(cctv.id)}
                            className="p-1.5 text-mute hover:text-terminal-red hover:bg-terminal-red/10 rounded-lg transition-colors"
                            title="삭제"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: 회원 권한 관리 */}
        {activeTab === 'users' && (
          <div className="space-y-6 animate-in fade-in duration-200">
            <div className="bg-canvas border border-hairline rounded-2xl p-6 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                  <h2 className="text-heading-sm font-bold text-ink flex items-center gap-2">
                    <Users className="w-5 h-5 text-amber-500" />
                    관제회원 권한 및 승인 관리
                  </h2>
                  <p className="text-xs text-mute mt-0.5">시스템 접근 및 관리자 권한을 부여하거나 변경합니다.</p>
                </div>

                <div className="flex items-center bg-surface-soft border border-hairline rounded-lg px-3 py-1.5 w-full md:w-64">
                  <Search className="w-4 h-4 text-mute mr-2" />
                  <input
                    type="text"
                    placeholder="이름 또는 이메일 검색"
                    value={userSearch}
                    onChange={(e) => setUserSearch(e.target.value)}
                    className="bg-transparent border-none outline-none text-xs w-full text-ink"
                  />
                </div>
              </div>

              <div className="overflow-x-auto border border-hairline rounded-xl">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-soft border-b border-hairline text-mute uppercase font-semibold">
                    <tr>
                      <th className="p-3.5">이름 (아이디)</th>
                      <th className="p-3.5">이메일 / 소속</th>
                      <th className="p-3.5">현재 권한</th>
                      <th className="p-3.5">가입 승인 상태</th>
                      <th className="p-3.5 text-right">권한 승격 / 변경</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {filteredUsers.map(user => (
                      <tr key={user.id} className="hover:bg-surface-soft/50 transition-colors">
                        <td className="p-3.5 font-bold text-ink">
                          {user.name} <span className="font-normal text-mute">({user.id})</span>
                        </td>
                        <td className="p-3.5 text-mute">
                          {user.email} <span className="text-[11px] text-mute font-mono">[{user.dept}]</span>
                        </td>
                        <td className="p-3.5">
                          {user.role === 'admin' ? (
                            <span className="px-2.5 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold rounded-full border border-amber-500/30">
                              👑 관리자
                            </span>
                          ) : (
                            <span className="px-2.5 py-0.5 bg-surface-soft text-mute rounded-full border border-hairline">
                              👤 일반 사용자
                            </span>
                          )}
                        </td>
                        <td className="p-3.5">
                          {user.status === '승인' ? (
                            <span className="text-emerald-500 font-bold flex items-center gap-1">
                              <UserCheck className="w-3.5 h-3.5" /> 승인완료
                            </span>
                          ) : (
                            <button
                              onClick={() => approveUser(user.id)}
                              className="px-2.5 py-1 bg-amber-500 text-white font-bold rounded-md hover:bg-amber-600 transition-colors"
                            >
                              가입 승인하기
                            </button>
                          )}
                        </td>
                        <td className="p-3.5 text-right">
                          <button
                            onClick={() => toggleRole(user.id)}
                            className="px-3 py-1.5 bg-canvas border border-hairline hover:border-ink rounded-lg font-semibold transition-colors"
                          >
                            {user.role === 'admin' ? '일반 권한으로 변경' : '관리자 승격'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: AI 탐지 & 119 설정 */}
        {activeTab === 'settings' && (
          <div className="space-y-6 max-w-2xl animate-in fade-in duration-200">
            <div className="bg-canvas border border-hairline rounded-2xl p-6 shadow-sm space-y-6">
              <h2 className="text-heading-sm font-bold text-ink flex items-center gap-2">
                <Sliders className="w-5 h-5 text-amber-500" />
                AI 화재 탐지 & 119 비상 연락망 설정
              </h2>

              <div className="space-y-5">
                <div className="flex items-center justify-between p-4 border border-hairline rounded-xl bg-surface-soft/50">
                  <div>
                    <h3 className="font-bold text-ink text-sm">119 긴급 자동 연동 시스템</h3>
                    <p className="text-xs text-mute mt-0.5">화재 확률 95% 감지 시 소방서 서보로 즉시 구조 요청 전달</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={autoNotify119}
                    onChange={(e) => setAutoNotify119(e.target.checked)}
                    className="w-5 h-5 accent-amber-500 rounded cursor-pointer"
                  />
                </div>

                <div className="p-4 border border-hairline rounded-xl space-y-3">
                  <div className="flex justify-between items-center">
                    <h3 className="font-bold text-ink text-sm">AI 객체 탐지 임계값 (Sensitivity)</h3>
                    <span className="text-amber-500 font-mono font-bold text-base">{threshold}%</span>
                  </div>
                  <input
                    type="range"
                    min="70"
                    max="98"
                    value={threshold}
                    onChange={(e) => setThreshold(e.target.value)}
                    className="w-full accent-amber-500 cursor-pointer"
                  />
                  <p className="text-xs text-mute">임계값이 높을수록 오탐률은 줄어들고 화재 확신도 판정이 엄격해집니다.</p>
                </div>
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  onClick={() => alert('시스템 설정이 저장되었습니다.')}
                  className="bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs py-2.5 px-6 rounded-lg transition-colors cursor-pointer"
                >
                  설정 내용 저장
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: 감사 로그 */}
        {activeTab === 'logs' && (
          <div className="bg-canvas border border-hairline rounded-2xl p-6 shadow-sm animate-in fade-in duration-200">
            <h2 className="text-heading-sm font-bold text-ink mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-amber-500" />
              시스템 감지 및 작업 로그
            </h2>

            <div className="space-y-3 font-mono text-xs">
              {SYSTEM_LOGS.map(log => (
                <div key={log.id} className="p-3 border border-hairline rounded-xl flex items-center justify-between bg-surface-soft/30">
                  <div className="flex items-center gap-3">
                    <span className="text-mute">{log.time}</span>
                    <span className={`font-semibold ${log.level === 'error' ? 'text-terminal-red' : log.level === 'warning' ? 'text-amber-500' : 'text-ink'}`}>
                      {log.message}
                    </span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 bg-surface-soft border border-hairline rounded uppercase text-mute">
                    {log.level}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default AdminPage;
