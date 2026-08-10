import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ShieldCheck, Users, PlusCircle, LogOut,
  AlertTriangle, ArrowLeft, Video, CheckCircle, Trash2,
  Activity, UserCheck, Search, ShieldAlert, X, Clock,
  Film, AlertCircle, Info, FileText, CheckCircle2, Play,
  Mail, Phone, Building, Calendar, Shield, User, ExternalLink,
  BadgeCheck, ChevronRight, Edit3, MapPin
} from 'lucide-react';
import { cctvApi } from '../api';
import CctvPlayer from '../components/CctvPlayer';

// 가상의 초기 CCTV 데이터
const INITIAL_CCTVS = [];

// 가상의 회원 목록 데이터 (상세 정보 확장)
const INITIAL_USERS = [
  {
    id: 'admin',
    name: '최고 관리자',
    email: 'admin@fireguard.or.kr',
    role: 'admin',
    status: '승인',
    dept: '관제총괄팀',
    phone: '010-1234-5678',
    position: '총괄 관제 책임자',
    joinedAt: '2026-01-02',
    lastLogin: '2026-08-10 10:25:12',
    assignedZone: '전체 관제 구역 (A동, B동, 외곽 및 옥상)',
    activities: [
      { time: '2026-08-10 10:25:12', action: '관리자 센터 로그인 성공' },
      { time: '2026-08-08 12:00:00', action: '신규 관제회원(이영희) 승인 및 접근 권한 부여' },
      { time: '2026-08-08 09:30:00', action: '전체 시스템 통합 정기 자가 점검 지시' },
      { time: '2026-08-05 14:20:00', action: '신규 카메라(CCTV-05) 모니터링 시스템 등록' }
    ]
  },
  {
    id: 'user01',
    name: '홍길동',
    email: 'gildong@fireguard.or.kr',
    role: 'user',
    status: '승인',
    dept: '관제1팀',
    phone: '010-9876-5432',
    position: '주간 관제 전담 요원',
    joinedAt: '2026-03-15',
    lastLogin: '2026-08-10 09:12:00',
    assignedZone: 'A동 1층 ~ 5층 실내 관제 구역',
    activities: [
      { time: '2026-08-10 09:12:00', action: '관제1팀 시스템 로그인' },
      { time: '2026-08-08 14:45:05', action: 'A동 1층 로비 화재 경보 알림 수신 및 119 자동신고 확인' },
      { time: '2026-08-08 14:46:00', action: 'A동 현장 요원에게 긴급 출동 지시 전달' }
    ]
  },
  {
    id: 'user02',
    name: '김철수',
    email: 'chulsoo@fireguard.or.kr',
    role: 'user',
    status: '승인',
    dept: '시설관리팀',
    phone: '010-5555-1111',
    position: '시설 및 장비 유지보수 기사',
    joinedAt: '2026-04-10',
    lastLogin: '2026-08-09 17:30:45',
    assignedZone: 'B동 전 구역 및 옥상 패널 구역',
    activities: [
      { time: '2026-08-09 17:30:45', action: '시설관리 로그아웃' },
      { time: '2026-08-08 14:11:30', action: 'CCTV-05 옥상 카메라 네트워크 끊김 장애 점검 티켓 수신' },
      { time: '2026-08-07 18:22:10', action: '후문 분리수거장 연기 오탐지 현장 수증기 확인 완료 보고' }
    ]
  },
  {
    id: 'user03',
    name: '이영희',
    email: 'younghee@fireguard.or.kr',
    role: 'user',
    status: '승인대기',
    dept: '보안팀',
    phone: '010-3333-7777',
    position: '야간 보안 관제 담당 (신규)',
    joinedAt: '2026-08-08',
    lastLogin: '미접속 (가입 승인 대기중)',
    assignedZone: '배정 대기중',
    activities: [
      { time: '2026-08-08 11:58:10', action: 'FireGuard 관제 시스템 회원 가입 신청 제출' }
    ]
  },
];

// 감사 및 시스템 감지 상세 로그 (백엔드 연동용 확장 데이터 구조)
const SYSTEM_LOGS = [
  {
    id: 1,
    time: '2026-08-08 14:45:00',
    message: 'A동 1층 로비 화재 의심 감지 (화재 확률 98%)',
    level: 'error',
    cctvId: 'CCTV-03',
    location: 'A동 1F 로비 (중앙 서측)',
    confidence: 98,
    eventType: '화재/연기 감지',
    status: '조치중 (119 신고 완료)',
    videoUrl: 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4',
    thumbnail: 'https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=800&auto=format&fit=crop&q=80',
    history: [
      { timestamp: '2026-08-08 14:45:00', event: 'AI 모듈 - 연기 및 불꽃 패턴 감지 (신뢰도 98%)' },
      { timestamp: '2026-08-08 14:45:03', event: '관제센터 실시간 대시보드 경보 팝업 출력' },
      { timestamp: '2026-08-08 14:45:10', event: '119 긴급 자동 비상 신고 연동 발송 (사건번호 #2026-0808-1445)' },
      { timestamp: '2026-08-08 14:46:00', event: 'A동 관제 담당자 현장 확인 조치 요청 접수' }
    ]
  },
  {
    id: 2,
    time: '2026-08-08 14:10:00',
    message: 'CCTV-05 옥상 카메라 연결 끊김',
    level: 'warning',
    cctvId: 'CCTV-05',
    location: 'A동 R층 옥상 파노라마',
    confidence: 0,
    eventType: '장비 네트워크 장애',
    status: '점검 진행중',
    videoUrl: null,
    thumbnail: null,
    history: [
      { timestamp: '2026-08-08 14:10:00', event: 'RTSP 비디오 스트림 응답 시간 초과 (Ping Timeout)' },
      { timestamp: '2026-08-08 14:11:30', event: '시설관리팀 네트워크 점검 자동 티켓 발행' }
    ]
  },
  {
    id: 3,
    time: '2026-08-08 12:00:00',
    message: '관리자(admin)가 보안팀 이영희 회원 가입 승인 처리',
    level: 'info',
    cctvId: '-',
    location: '관제센터 관리자 콘솔',
    confidence: 0,
    eventType: '계정 권한 관리',
    status: '처리 완료',
    videoUrl: null,
    thumbnail: null,
    history: [
      { timestamp: '2026-08-08 11:58:10', event: '이영희(younghee) 회원가입 요청' },
      { timestamp: '2026-08-08 12:00:00', event: '최고 관리자(admin) 승인 및 접근 권한 부여' }
    ]
  },
  {
    id: 4,
    time: '2026-08-08 09:30:00',
    message: '전체 5개 CCTV 카메라 및 AI 가속 엔진 정기 자가 점검 완료 (정상)',
    level: 'info',
    cctvId: 'ALL',
    location: '전체 모니터링 구역',
    confidence: 0,
    eventType: '시스템 정기 점검',
    status: '정상 완료',
    videoUrl: null,
    thumbnail: null,
    history: [
      { timestamp: '2026-08-08 09:30:00', event: 'CCTV 5개 채널 비디오 입력 헬스체크 완료' },
      { timestamp: '2026-08-08 09:30:02', event: 'GPU AI 추론 엔진 프레임 드랍 0%, 온도 정상' }
    ]
  },
  {
    id: 5,
    time: '2026-08-07 18:20:00',
    message: '후문 분리수거장 소형 연기 오탐지 해제 처리',
    level: 'warning',
    cctvId: 'CCTV-02',
    location: '1F 외부 후문 분리수거장',
    confidence: 72,
    eventType: '화재 의심 감지',
    status: '오탐지 해제',
    videoUrl: 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4',
    thumbnail: 'https://images.unsplash.com/photo-1508873696983-2df515122519?w=800&auto=format&fit=crop&q=80',
    history: [
      { timestamp: '2026-08-07 18:20:00', event: 'AI 모듈 - 연기 패턴 감지 (신뢰도 72%)' },
      { timestamp: '2026-08-07 18:22:10', event: '관제요원 현장 카메라 줌 확인 완료 (수증기 확인)' },
      { timestamp: '2026-08-07 18:23:00', event: '관리자 오탐지(False Alarm) 해제 처리' }
    ]
  }
];

const AdminPage = () => {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState(null);
  const [activeTab, setActiveTab] = useState('cctv'); // 'cctv' | 'users' | 'logs'

  // 데이터 상태
  const [cctvList, setCctvList] = useState(INITIAL_CCTVS);
  const [userList, setUserList] = useState(INITIAL_USERS);

  // 폼 및 검색 상태
  const [newCctvName, setNewCctvName] = useState('');
  const [newCctvLoc, setNewCctvLoc] = useState('');
  const [newCctvStatus, setNewCctvStatus] = useState('normal');
  const [newCctvLat, setNewCctvLat] = useState('37.5665');
  const [newCctvLng, setNewCctvLng] = useState('126.9780');
  const [userSearch, setUserSearch] = useState('');

  // 팝업 모달 상태
  const [selectedLog, setSelectedLog] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [editingCctv, setEditingCctv] = useState(null);
  const [isAddingCctv, setIsAddingCctv] = useState(false);
  const [previewCctv, setPreviewCctv] = useState(null);

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

    // 백엔드 CCTV 목록 로드
    cctvApi.list().then(res => {
      const items = res?.items || res || [];
      if (Array.isArray(items) && items.length > 0) {
        const mapped = items.map(item => ({
          id: `CCTV-${String(item.cctv_no).padStart(2, '0')}`,
          cctv_no: item.cctv_no,
          name: item.cctv_name,
          location: item.cctv_location,
          status: item.cctv_status === 'ACTIVE' ? 'normal' : item.cctv_status === 'INACTIVE' ? 'offline' : 'fire',
          lat: parseFloat(item.cctv_lat) || 37.5665,
          lng: parseFloat(item.cctv_lng) || 126.9780,
          stream_url: item.cctv_stream_url
        }));
        setCctvList(mapped);
      }
    }).catch(err => console.warn('CCTV 백엔드 로드 오류:', err));
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('currentUser');
    navigate('/login');
  };

  // 현재 브라우저 GPS 위치 좌표 받아오기
  const handleGetCurrentLocation = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setNewCctvLat(position.coords.latitude.toFixed(6));
          setNewCctvLng(position.coords.longitude.toFixed(6));
          alert('현재 위치 GPS 좌표를 성공적으로 가져왔습니다.');
        },
        () => {
          alert('GPS 위치 정보를 가져올 수 없습니다. 직접 입력을 이용해주세요.');
        }
      );
    } else {
      alert('이 브라우저는 위치 정보 서비스를 지원하지 않습니다.');
    }
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
      status: newCctvStatus || 'normal',
      lat: parseFloat(newCctvLat) || 37.5665,
      lng: parseFloat(newCctvLng) || 126.9780,
    };
    setCctvList([...cctvList, newCamera]);
    setNewCctvName('');
    setNewCctvLoc('');
    setNewCctvStatus('normal');
    setNewCctvLat('37.5665');
    setNewCctvLng('126.9780');
    setIsAddingCctv(false);
    alert(`[${newCamera.name}] 카메라 (위도: ${newCamera.lat}, 경도: ${newCamera.lng})가 성공적으로 등록되었습니다.`);
  };

  // CCTV 정보 수정
  const handleUpdateCCTV = (e) => {
    e.preventDefault();
    if (!editingCctv || !editingCctv.name.trim()) return;
    setCctvList(prev => prev.map(c => c.id === editingCctv.id ? editingCctv : c));
    alert(`[${editingCctv.name}] CCTV 정보가 성공적으로 수정되었습니다.`);
    setEditingCctv(null);
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
        const updated = { ...u, role: nextRole };
        if (selectedUser && selectedUser.id === userId) {
          setSelectedUser(updated);
        }
        return updated;
      }
      return u;
    }));
  };

  // 회원 승인
  const approveUser = (userId) => {
    setUserList(prev => prev.map(u => {
      if (u.id === userId) {
        const updated = { ...u, status: '승인' };
        if (selectedUser && selectedUser.id === userId) {
          setSelectedUser(updated);
        }
        return updated;
      }
      return u;
    }));
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
          <span className="text-xs text-white font-bold bg-neutral-900 dark:bg-neutral-800 px-3 py-1 rounded-full border border-neutral-700 hidden sm:inline-flex items-center shadow-xs">
            {currentUser?.name ? `${currentUser.name.replace(/\s*님$/, '')}님` : '관리자님'}
          </span>
          <Link
            to="/mypage"
            className="flex items-center gap-1.5 text-body-sm text-mute hover:text-ink transition-colors px-3 py-1.5 rounded-full border border-hairline hover:bg-surface-soft"
          >
            <User className="w-4 h-4" />
            <span>마이페이지</span>
          </Link>
          <Link
            to="/dashboard"
            className="flex items-center gap-1.5 text-body-sm text-mute hover:text-ink transition-colors px-3 py-1.5 rounded-full border border-hairline hover:bg-surface-soft"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>CCTV 모니터링으로 돌아가기</span>
          </Link>

          <button
            onClick={handleLogout}
            className="flex items-center gap-2 bg-primary text-on-primary px-4 py-1.5 rounded-full text-xs font-semibold hover:bg-ink-deep transition-colors cursor-pointer"
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
              CCTV 자산 등록, 관제 회원 권한 설정 및 시스템 감지 감사 로그를 모니터링합니다.
            </p>
          </div>

          {/* 탭 컨트롤 */}
          <div className="flex items-center bg-canvas border border-hairline p-1 rounded-xl gap-1 shrink-0">
            <button
              onClick={() => setActiveTab('cctv')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${activeTab === 'cctv'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
                }`}
            >
              <Video className="w-4 h-4" />
              <span>CCTV 자산 관리 ({cctvList.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('users')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${activeTab === 'users'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
                }`}
            >
              <Users className="w-4 h-4" />
              <span>회원 권한 ({userList.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('logs')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${activeTab === 'logs'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
                }`}
            >
              <Activity className="w-4 h-4" />
              <span>감사 로그 ({SYSTEM_LOGS.length})</span>
            </button>
          </div>
        </div>
      </div>

      {/* 3. 메인 콘텐츠 영역 */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-8">

        {/* TAB 1: CCTV 카메라 관리 */}
        {activeTab === 'cctv' && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {/* 상단 서브 액션 바 */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-canvas border border-hairline rounded-2xl p-5 shadow-sm">
              <div>
                <h2 className="font-bold text-body-md text-ink flex items-center gap-2">
                  <Video className="w-5 h-5 text-amber-500" />
                  CCTV 자산 모니터링 목록 ({cctvList.length}대)
                </h2>
                <p className="text-xs text-mute mt-1">
                  등록된 CCTV 정보는 GIS 지도 및 관제 대시보드 화면에 실시간으로 반영됩니다.
                </p>
              </div>

              <button
                onClick={() => {
                  setIsAddingCctv(true);
                  setEditingCctv(null);
                }}
                className="bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs px-4 py-2.5 rounded-xl shadow-sm transition-all flex items-center gap-2 cursor-pointer shrink-0 self-start sm:self-auto"
              >
                <PlusCircle className="w-4 h-4" />
                <span>+ 신규 CCTV 자산 등록</span>
              </button>
            </div>

            {/* 목록 테이블 카드 */}
            <div className="bg-canvas border border-hairline rounded-2xl overflow-hidden shadow-sm">
              <div className="p-5 border-b border-hairline flex items-center justify-between">
                <h3 className="font-bold text-body-md text-ink">등록된 CCTV 자산 상세 목록</h3>
                <span className="text-xs text-mute">원하시는 카메라의 '수정하기' 버튼을 클릭하면 정보를 팝업 창에서 변경할 수 있습니다.</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-soft border-b border-hairline text-mute uppercase font-semibold">
                    <tr>
                      <th className="p-4">카메라 ID</th>
                      <th className="p-4">CCTV 명칭</th>
                      <th className="p-4">설치 위치 및 좌표</th>
                      <th className="p-4">현재 상태</th>
                      <th className="p-4 text-center">작동 관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {cctvList.map(cctv => (
                      <tr key={cctv.id} className="hover:bg-surface-soft/50 transition-colors">
                        <td className="p-4 font-mono font-bold text-ink">{cctv.id}</td>
                        <td className="p-4 font-semibold text-ink">{cctv.name}</td>
                        <td className="p-4">
                          <span className="font-semibold text-ink block">{cctv.location}</span>
                          <span className="text-[10px] text-mute font-mono block mt-0.5">
                            좌표: ({cctv.lat}, {cctv.lng})
                          </span>
                        </td>
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
                        <td className="p-4 text-center space-x-2 whitespace-nowrap">
                          <button
                            onClick={() => setPreviewCctv(cctv)}
                            className="px-2.5 py-1 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors cursor-pointer inline-flex items-center gap-1 shadow-xs"
                            title="실시간 비디오 스트림 팝업 보기"
                          >
                            <Play className="w-3.5 h-3.5 fill-current" />
                            <span>실시간 스트림</span>
                          </button>
                          <button
                            onClick={() => {
                              setEditingCctv({ ...cctv });
                              setIsAddingCctv(false);
                            }}
                            className="px-2.5 py-1 text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 border border-amber-500/30 rounded-lg transition-colors cursor-pointer inline-flex items-center gap-1"
                            title="CCTV 정보 수정"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                            <span>수정하기</span>
                          </button>
                          <button
                            onClick={() => handleDeleteCCTV(cctv.id)}
                            className="px-2.5 py-1 text-xs font-semibold text-terminal-red bg-terminal-red/10 hover:bg-terminal-red/20 border border-terminal-red/20 rounded-lg transition-colors cursor-pointer inline-flex items-center gap-1"
                            title="CCTV 삭제"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>삭제</span>
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
                  <p className="text-xs text-mute mt-0.5">
                    회원 이름을 클릭하거나 <strong className="text-amber-500">이메일 주소</strong>를 클릭하시면 상세 회원 프로필 및 관제 활동 이력을 볼 수 있습니다.
                  </p>
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
                      <th className="p-3.5">이메일 / 소속 (클릭 시 상세조회)</th>
                      <th className="p-3.5">현재 권한</th>
                      <th className="p-3.5">가입 승인 상태</th>
                      <th className="p-3.5 text-right">상세조회 및 관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {filteredUsers.map(user => (
                      <tr key={user.id} className="hover:bg-surface-soft/60 transition-colors">
                        <td
                          onClick={() => setSelectedUser(user)}
                          className="p-3.5 font-bold text-ink cursor-pointer hover:text-amber-500 transition-colors"
                        >
                          {user.name} <span className="font-normal text-mute">({user.id})</span>
                        </td>
                        <td className="p-3.5">
                          <button
                            onClick={() => setSelectedUser(user)}
                            className="text-amber-600 dark:text-amber-400 font-medium hover:underline flex items-center gap-1.5 cursor-pointer text-left"
                            title="회원 정보 상세 보기"
                          >
                            <Mail className="w-3.5 h-3.5 shrink-0 text-amber-500" />
                            <span>{user.email}</span>
                            <span className="text-[11px] text-mute font-mono bg-surface-soft px-1.5 py-0.5 rounded border border-hairline ml-1">
                              [{user.dept}]
                            </span>
                          </button>
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
                              onClick={(e) => {
                                e.stopPropagation();
                                approveUser(user.id);
                              }}
                              className="px-2.5 py-1 bg-amber-500 text-white font-bold rounded-md hover:bg-amber-600 transition-colors cursor-pointer"
                            >
                              가입 승인하기
                            </button>
                          )}
                        </td>
                        <td className="p-3.5 text-right space-x-2">
                          <button
                            onClick={() => setSelectedUser(user)}
                            className="px-2.5 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30 hover:bg-amber-500/20 rounded-lg font-bold transition-colors cursor-pointer inline-flex items-center gap-1"
                          >
                            <span>상세보기</span>
                            <ChevronRight className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleRole(user.id);
                            }}
                            className="px-2.5 py-1 bg-canvas border border-hairline hover:border-ink rounded-lg font-semibold transition-colors cursor-pointer"
                          >
                            {user.role === 'admin' ? '일반변경' : '관리자승격'}
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

        {/* TAB 3: 감사 로그 */}
        {activeTab === 'logs' && (
          <div className="bg-canvas border border-hairline rounded-2xl p-6 shadow-sm animate-in fade-in duration-200">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 mb-5">
              <div>
                <h2 className="text-heading-sm font-bold text-ink flex items-center gap-2">
                  <Activity className="w-5 h-5 text-amber-500" />
                  시스템 통합 감사 로그 & 감지 이력
                </h2>
                <p className="text-xs text-mute mt-1">
                  감사 로그 항목을 클릭하면 해당 이벤트의 <strong className="text-amber-500">녹화 영상 및 감지 타임라인 이력</strong>을 확인할 수 있습니다.
                </p>
              </div>
              <span className="text-[11px] px-3 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-mono rounded-full border border-amber-500/20 shrink-0 self-start md:self-auto">
                ⚡ 백엔드 REST/RTSP 연동 대기중
              </span>
            </div>

            <div className="space-y-3 font-mono text-xs">
              {SYSTEM_LOGS.map(log => (
                <div
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className="p-4 border border-hairline rounded-xl flex flex-col md:flex-row md:items-center justify-between bg-surface-soft/30 hover:bg-amber-500/5 hover:border-amber-500/40 cursor-pointer transition-all group shadow-2xs"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-mute shrink-0 text-[11px] bg-canvas px-2 py-1 rounded border border-hairline">
                      {log.time}
                    </span>
                    <span className={`font-semibold transition-colors group-hover:text-amber-600 dark:group-hover:text-amber-400 ${log.level === 'error' ? 'text-terminal-red' : log.level === 'warning' ? 'text-amber-500' : 'text-ink'
                      }`}>
                      {log.message}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 mt-2 md:mt-0 shrink-0">
                    {log.videoUrl && (
                      <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 bg-terminal-red/10 text-terminal-red rounded border border-terminal-red/20 font-sans font-bold">
                        <Film className="w-3 h-3" /> 영상보기
                      </span>
                    )}
                    <span className="text-[10px] px-2 py-0.5 bg-surface-soft border border-hairline rounded uppercase text-mute group-hover:border-amber-500/30">
                      {log.level}
                    </span>
                    <span className="text-xs text-amber-500 group-hover:translate-x-0.5 transition-transform">
                      ➔
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* 4. 회원 상세 정보 보기 모달 */}
      {selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-canvas border border-hairline rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl flex flex-col">
            {/* 모달 헤더 */}
            <div className="p-6 border-b border-hairline flex items-center justify-between bg-surface-soft/60">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-amber-500/20 text-amber-500 flex items-center justify-center font-bold text-lg border border-amber-500/40">
                  {selectedUser.name ? selectedUser.name.charAt(0) : 'U'}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-heading-sm font-bold text-ink">{selectedUser.name}</h2>
                    <span className="text-xs text-mute font-mono">({selectedUser.id})</span>
                    {selectedUser.role === 'admin' ? (
                      <span className="px-2 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold rounded-full text-[11px] border border-amber-500/30">
                        👑 관리자
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 bg-surface-soft text-mute rounded-full text-[11px] border border-hairline">
                        👤 일반 관제원
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-mute mt-0.5 flex items-center gap-2">
                    <span>{selectedUser.dept}</span>
                    <span>•</span>
                    <span>{selectedUser.position}</span>
                  </p>
                </div>
              </div>

              <button
                onClick={() => setSelectedUser(null)}
                className="p-1.5 rounded-lg text-mute hover:text-ink hover:bg-surface-soft transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 모달 본문 */}
            <div className="p-6 space-y-6">
              {/* 기본 정보 카격 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 bg-surface-soft/40 border border-hairline rounded-xl space-y-3">
                  <h3 className="text-xs font-bold text-ink uppercase tracking-wider text-mute flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5 text-amber-500" />
                    계정 및 연락처 정보
                  </h3>
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-mute flex items-center gap-1">
                        <Mail className="w-3.5 h-3.5" /> 이메일
                      </span>
                      <span className="font-mono text-ink font-semibold">{selectedUser.email}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-mute flex items-center gap-1">
                        <Phone className="w-3.5 h-3.5" /> 연락처
                      </span>
                      <span className="font-mono text-ink font-semibold">{selectedUser.phone}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-mute flex items-center gap-1">
                        <Building className="w-3.5 h-3.5" /> 소속 부서
                      </span>
                      <span className="text-ink font-semibold">{selectedUser.dept} ({selectedUser.position})</span>
                    </div>
                  </div>
                </div>

                <div className="p-4 bg-surface-soft/40 border border-hairline rounded-xl space-y-3">
                  <h3 className="text-xs font-bold text-ink uppercase tracking-wider text-mute flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5 text-amber-500" />
                    관제 시스템 권한 상태
                  </h3>
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-mute flex items-center gap-1">
                        <BadgeCheck className="w-3.5 h-3.5" /> 가입 승인 상태
                      </span>
                      {selectedUser.status === '승인' ? (
                        <span className="text-emerald-500 font-bold flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> 승인완료
                        </span>
                      ) : (
                        <span className="text-amber-500 font-bold">승인 대기중</span>
                      )}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-mute flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" /> 가입 신청일
                      </span>
                      <span className="font-mono text-ink">{selectedUser.joinedAt}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-mute flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" /> 최근 로그인
                      </span>
                      <span className="font-mono text-ink text-[11px]">{selectedUser.lastLogin}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* 담당 관제 구역 */}
              <div className="p-4 bg-surface-soft/40 border border-hairline rounded-xl space-y-1.5">
                <span className="text-xs font-bold text-mute uppercase tracking-wider flex items-center gap-1.5">
                  <Video className="w-3.5 h-3.5 text-amber-500" />
                  담당 관제 구역
                </span>
                <p className="text-xs font-semibold text-ink">
                  {selectedUser.assignedZone}
                </p>
              </div>

              {/* 최근 활동 이력 목록 */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-ink uppercase tracking-wider text-mute flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-amber-500" />
                  최근 시스템 관제 및 활동 이력
                </h3>
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {selectedUser.activities && selectedUser.activities.map((act, idx) => (
                    <div key={idx} className="p-3 bg-canvas border border-hairline rounded-lg text-xs flex items-center justify-between">
                      <span className="text-ink font-medium">{act.action}</span>
                      <span className="text-[11px] font-mono text-mute shrink-0 ml-2">{act.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 모달 푸터 액션 */}
            <div className="p-4 border-t border-hairline bg-surface-soft/40 flex items-center justify-between">
              <div className="flex items-center gap-2">
                {selectedUser.status !== '승인' && (
                  <button
                    onClick={() => approveUser(selectedUser.id)}
                    className="bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs py-2 px-4 rounded-lg transition-colors cursor-pointer flex items-center gap-1"
                  >
                    <UserCheck className="w-3.5 h-3.5" />
                    가입 승인하기
                  </button>
                )}
                <button
                  onClick={() => toggleRole(selectedUser.id)}
                  className="bg-canvas border border-hairline hover:border-ink text-ink font-semibold text-xs py-2 px-4 rounded-lg transition-colors cursor-pointer"
                >
                  {selectedUser.role === 'admin' ? '일반 관제원으로 권한 변경' : '관리자 권한으로 승격'}
                </button>
              </div>

              <button
                onClick={() => setSelectedUser(null)}
                className="bg-primary text-on-primary hover:bg-ink-deep font-bold text-xs py-2 px-5 rounded-lg transition-colors cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. 감사 로그 상세 영상 및 이력 팝업 모달 */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-canvas border border-hairline rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl flex flex-col">
            {/* 모달 헤더 */}
            <div className="p-6 border-b border-hairline flex items-start justify-between bg-surface-soft/60">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-0.5 rounded text-[11px] font-bold uppercase ${selectedLog.level === 'error' ? 'bg-terminal-red/20 text-terminal-red border border-terminal-red/30' :
                      selectedLog.level === 'warning' ? 'bg-amber-500/20 text-amber-500 border border-amber-500/30' :
                        'bg-blue-500/20 text-blue-500 border border-blue-500/30'
                    }`}>
                    {selectedLog.eventType} [{selectedLog.level}]
                  </span>
                  <span className="text-xs text-mute font-mono flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-mute" />
                    {selectedLog.time}
                  </span>
                </div>
                <h2 className="text-heading-sm font-bold text-ink mt-1">
                  {selectedLog.message}
                </h2>
              </div>

              <button
                onClick={() => setSelectedLog(null)}
                className="p-1.5 rounded-lg text-mute hover:text-ink hover:bg-surface-soft transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 모달 본문 */}
            <div className="p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* 왼쪽: 영상 / 캡처 미디어 뷰어 */}
              <div className="lg:col-span-7 space-y-4">
                <div className="relative aspect-video bg-black rounded-xl overflow-hidden border border-hairline shadow-md group">
                  {selectedLog.videoUrl ? (
                    <video
                      controls
                      autoPlay
                      muted
                      loop
                      className="w-full h-full object-cover"
                      poster={selectedLog.thumbnail}
                    >
                      <source src={selectedLog.videoUrl} type="video/mp4" />
                      브라우저가 비디오 재생을 지원하지 않습니다.
                    </video>
                  ) : selectedLog.thumbnail ? (
                    <img
                      src={selectedLog.thumbnail}
                      alt="감지 스냅샷"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-mute space-y-2 p-6 text-center">
                      <Film className="w-10 h-10 stroke-1 opacity-40 text-mute" />
                      <p className="text-xs">이 감사 로그는 녹화 영상 미디어가 포함되어 있지 않습니다.</p>
                      <span className="text-[11px] text-mute/60 font-mono">(시스템 행위 / 권한 관리 로그)</span>
                    </div>
                  )}

                  {/* Overlay status tag */}
                  {selectedLog.cctvId !== '-' && (
                    <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-md px-3 py-1 rounded-md text-[11px] font-mono text-white flex items-center gap-2 border border-white/10">
                      <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                      <span>{selectedLog.cctvId} ({selectedLog.location})</span>
                    </div>
                  )}
                </div>

                {/* 위치 & 감지 데이터 정보 메타 카드 */}
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="p-3 bg-surface-soft border border-hairline rounded-xl">
                    <span className="text-mute block text-[11px]">발생 구역 / 장비</span>
                    <span className="font-bold text-ink mt-0.5 block">{selectedLog.location}</span>
                    <span className="text-mute font-mono text-[10px]">ID: {selectedLog.cctvId}</span>
                  </div>

                  <div className="p-3 bg-surface-soft border border-hairline rounded-xl">
                    <span className="text-mute block text-[11px]">AI 확신도 / 상태</span>
                    <div className="flex items-center gap-2 mt-0.5">
                      {selectedLog.confidence > 0 ? (
                        <span className="font-extrabold text-terminal-red text-sm font-mono">
                          {selectedLog.confidence}%
                        </span>
                      ) : (
                        <span className="font-bold text-ink text-xs">N/A</span>
                      )}
                      <span className="text-[11px] px-2 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold rounded border border-amber-500/20">
                        {selectedLog.status}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* 오른쪽: 상세 감지 이력 타임라인 (History Timeline) */}
              <div className="lg:col-span-5 flex flex-col space-y-4">
                <h3 className="font-bold text-body-md text-ink flex items-center gap-2 border-b border-hairline pb-2">
                  <FileText className="w-4 h-4 text-amber-500" />
                  감지 이력 및 타임라인
                </h3>

                <div className="flex-1 space-y-4 relative before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-hairline">
                  {selectedLog.history && selectedLog.history.map((hist, idx) => (
                    <div key={idx} className="relative pl-7 text-xs space-y-0.5">
                      {/* 타임라인 노드 아이콘 */}
                      <div className={`absolute left-1.5 top-0.5 -translate-x-1/2 w-3.5 h-3.5 rounded-full border-2 bg-canvas flex items-center justify-center ${idx === 0 ? 'border-amber-500 bg-amber-500' : 'border-hairline'
                        }`}>
                        {idx === 0 && <span className="w-1 h-1 rounded-full bg-white"></span>}
                      </div>

                      <span className="text-[11px] font-mono text-mute block">
                        {hist.timestamp}
                      </span>
                      <p className="font-medium text-ink leading-relaxed">
                        {hist.event}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="pt-4 border-t border-hairline text-[11px] text-mute flex items-center gap-1.5 bg-surface-soft/40 p-3 rounded-xl">
                  <Info className="w-4 h-4 text-amber-500 shrink-0" />
                  <span>
                    백엔드 연동 시 REST API 및 RTSP 녹화 서버의 상세 메타데이터와 자동 연동됩니다.
                  </span>
                </div>
              </div>
            </div>

            {/* 모달 푸터 */}
            <div className="p-4 border-t border-hairline bg-surface-soft/30 flex justify-end">
              <button
                onClick={() => setSelectedLog(null)}
                className="bg-primary text-on-primary hover:bg-ink-deep font-bold text-xs py-2 px-5 rounded-lg transition-colors cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. CCTV 정보 수정 팝업 모달 */}
      {editingCctv && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div
            className="relative bg-canvas border border-hairline rounded-2xl shadow-2xl overflow-hidden my-auto animate-in zoom-in-95 duration-150"
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          >
            {/* 모달 헤더 */}
            <div className="p-5 border-b border-hairline flex items-center justify-between bg-surface-soft/60">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-amber-500/10 text-amber-500 rounded-xl border border-amber-500/20 shrink-0">
                  <Edit3 className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-body-md font-bold text-ink">
                    CCTV 자산 정보 수정
                  </h2>
                  <p className="text-[11px] text-mute font-mono">장비 ID: {editingCctv.id}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditingCctv(null)}
                className="p-1.5 rounded-lg text-mute hover:text-ink hover:bg-surface-soft transition-colors cursor-pointer shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 모달 본문 (폼) */}
            <form onSubmit={handleUpdateCCTV} className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink">CCTV 카메라 명칭 *</label>
                <input
                  type="text"
                  value={editingCctv.name}
                  onChange={(e) => setEditingCctv({ ...editingCctv, name: e.target.value })}
                  className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-ui"
                  placeholder="예: 정문 주차장 카메라"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink">설치 구역 및 상세 위치 *</label>
                <input
                  type="text"
                  value={editingCctv.location}
                  onChange={(e) => setEditingCctv({ ...editingCctv, location: e.target.value })}
                  className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-ui"
                  placeholder="예: 1F 외부 서측 정문"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink">관제 센서 작동 상태</label>
                <select
                  value={editingCctv.status}
                  onChange={(e) => setEditingCctv({ ...editingCctv, status: e.target.value })}
                  className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all cursor-pointer font-medium font-ui"
                >
                  <option value="normal">🟢 정상 작동 (normal)</option>
                  <option value="fire">🔥 화재 감지 경보 (fire)</option>
                  <option value="offline">🔌 연결 끊김 (offline)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-1">
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-ink">위도 (Latitude) *</label>
                  <input
                    type="number"
                    step="any"
                    value={editingCctv.lat}
                    onChange={(e) => setEditingCctv({ ...editingCctv, lat: parseFloat(e.target.value) || 0 })}
                    className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-mono text-xs"
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-ink">경도 (Longitude) *</label>
                  <input
                    type="number"
                    step="any"
                    value={editingCctv.lng}
                    onChange={(e) => setEditingCctv({ ...editingCctv, lng: parseFloat(e.target.value) || 0 })}
                    className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-mono text-xs"
                    required
                  />
                </div>
              </div>

              {/* 모달 푸터 액션 */}
              <div className="pt-4 border-t border-hairline flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setEditingCctv(null)}
                  className="px-4 h-10 bg-surface-soft hover:bg-hairline text-ink font-semibold text-xs rounded-xl transition-colors cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="px-5 h-10 bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs rounded-xl shadow-sm transition-colors cursor-pointer inline-flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  수정사항 저장하기
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 7. 신규 CCTV 등록 팝업 모달 */}
      {isAddingCctv && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div
            className="relative bg-canvas border border-hairline rounded-2xl shadow-2xl overflow-hidden my-auto animate-in zoom-in-95 duration-150"
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          >
            {/* 모달 헤더 */}
            <div className="p-5 border-b border-hairline flex items-center justify-between bg-surface-soft/60">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-amber-500/10 text-amber-500 rounded-xl border border-amber-500/20 shrink-0">
                  <PlusCircle className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-body-md font-bold text-ink">
                    신규 CCTV 자산 등록
                  </h2>
                  <p className="text-[11px] text-mute">CCTV 정보 및 위치 GPS 좌표 등록</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsAddingCctv(false)}
                className="p-1.5 rounded-lg text-mute hover:text-ink hover:bg-surface-soft transition-colors cursor-pointer shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 모달 본문 (폼) */}
            <form onSubmit={handleAddCCTV} className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink">CCTV 카메라 명칭 *</label>
                <input
                  type="text"
                  value={newCctvName}
                  onChange={(e) => setNewCctvName(e.target.value)}
                  className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-ui"
                  placeholder="예: C동 지하 2층 주차장"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink">설치 구역 및 상세 위치</label>
                <input
                  type="text"
                  value={newCctvLoc}
                  onChange={(e) => setNewCctvLoc(e.target.value)}
                  className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-ui"
                  placeholder="예: C동 지하 주차장 04번 기둥 앞"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink">초기 관제 상태</label>
                <select
                  value={newCctvStatus}
                  onChange={(e) => setNewCctvStatus(e.target.value)}
                  className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all cursor-pointer font-medium font-ui"
                >
                  <option value="normal">🟢 정상 작동 (normal)</option>
                  <option value="fire">🔥 화재 감지 경보 (fire)</option>
                  <option value="offline">🔌 연결 끊김 (offline)</option>
                </select>
              </div>

              <div className="space-y-2 pt-2 border-t border-hairline">
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-bold text-ink">위치 GPS 좌표 설정 *</label>
                  <button
                    type="button"
                    onClick={handleGetCurrentLocation}
                    className="px-2.5 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 border border-amber-500/30 rounded-lg text-[11px] font-semibold transition-colors flex items-center gap-1 cursor-pointer"
                  >
                    <MapPin className="w-3 h-3" />
                    <span>현재 GPS 가져오기</span>
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="block text-[11px] text-mute mb-1">위도 (Latitude)</span>
                    <input
                      type="number"
                      step="any"
                      placeholder="37.5665"
                      value={newCctvLat}
                      onChange={(e) => setNewCctvLat(e.target.value)}
                      className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm font-mono outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all text-xs"
                      required
                    />
                  </div>
                  <div>
                    <span className="block text-[11px] text-mute mb-1">경도 (Longitude)</span>
                    <input
                      type="number"
                      step="any"
                      placeholder="126.9780"
                      value={newCctvLng}
                      onChange={(e) => setNewCctvLng(e.target.value)}
                      className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm font-mono outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all text-xs"
                      required
                    />
                  </div>
                </div>
              </div>

              {/* 모달 푸터 액션 */}
              <div className="pt-4 border-t border-hairline flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsAddingCctv(false)}
                  className="px-4 h-10 bg-surface-soft hover:bg-hairline text-ink font-semibold text-xs rounded-xl transition-colors cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="px-5 h-10 bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs rounded-xl shadow-sm transition-colors cursor-pointer inline-flex items-center gap-1.5"
                >
                  <PlusCircle className="w-4 h-4" />
                  신규 CCTV 등록 완료
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 팝업 모달 4: CCTV 실시간 스트리밍 영상 라이브 뷰어 모달 */}
      {/* ------------------------------------------------------------- */}
      {previewCctv && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-xs animate-in fade-in duration-200">
          <div
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden"
            style={{ width: '640px', minWidth: '320px', maxWidth: '95vw' }}
          >
            {/* Header */}
            <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500 animate-ping" />
                <div>
                  <h3 className="text-heading-md font-bold text-ink">{previewCctv.name} 실시간 모니터링</h3>
                  <p className="text-caption-sm text-mute font-mono">{previewCctv.id} · {previewCctv.location}</p>
                </div>
              </div>
              <button
                onClick={() => setPreviewCctv(null)}
                className="p-1.5 text-mute hover:text-ink rounded-full transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 max-h-[75vh] overflow-y-auto space-y-4">
              <CctvPlayer
                streamUrl={previewCctv.stream_url || previewCctv.cctv_stream_url}
                cctvName={previewCctv.name}
                isFire={previewCctv.status === 'fire'}
              />

              <div className="bg-surface-soft p-4 rounded-xl border border-hairline space-y-2 text-xs">
                <div className="flex justify-between items-center">
                  <span className="text-mute font-medium">카메라 명칭:</span>
                  <span className="text-ink font-bold">{previewCctv.name}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-mute font-medium">설치 위치:</span>
                  <span className="text-ink font-semibold">{previewCctv.location}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-mute font-medium">GPS 위도/경도:</span>
                  <span className="text-ink font-mono">{previewCctv.lat}, {previewCctv.lng}</span>
                </div>
                <div className="flex justify-between items-center pt-2 border-t border-hairline">
                  <span className="text-mute font-medium">실시간 스트림 URL:</span>
                  <span className="text-blue-500 font-mono text-[11px] truncate max-w-[320px]">
                    {previewCctv.stream_url || previewCctv.cctv_stream_url || '자동 갱신 HLS 주소'}
                  </span>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-between shrink-0">
              <span className="text-xs text-mute">ITS 실시간 스트림 자동 토큰 갱신 지원</span>
              <button
                onClick={() => setPreviewCctv(null)}
                className="px-5 h-10 rounded-full bg-primary text-on-primary text-body-sm font-medium hover:bg-ink-deep transition-colors cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPage;


