import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  User, ShieldCheck, Mail, Phone, Building, Calendar,
  Lock, Bell, Shield, Key, CheckCircle, Clock,
  LogOut, ArrowLeft, Edit3, Camera, Save, X, AlertTriangle,
  FileText, Activity, Smartphone, Monitor, ShieldAlert, Video, MapPin, ExternalLink, Loader2
} from 'lucide-react';

import CctvPlayer from '../components/CctvPlayer';
import { authApi, cctvApi, eventApi, getCurrentUserFromStorage } from '../api';

export default function MyPage() {
  const navigate = useNavigate();

  // 사용자 프로필 정보 (실시간 DB / 세션 복원 및 안전한 초기값)
  const [currentUser, setCurrentUser] = useState(() => {
    return getCurrentUserFromStorage() || {
      id: 'admin',
      name: '최고 관리자',
      email: 'admin@fireguard.or.kr',
      role: 'admin',
      dept: '관제총괄팀',
      phone: '010-1234-5678',
      position: '총괄 관제 책임자',
      joinedAt: '2026-01-01',
      lastLogin: '접속 중',
      assignedZone: '전체 관제 구역'
    };
  });
  
  // 내 관리 CCTV 모달 및 로딩 상태
  const [myCctvs, setMyCctvs] = useState([]);
  const [isCctvsLoading, setIsCctvsLoading] = useState(true);
  const [selectedMyCctv, setSelectedMyCctv] = useState(null);
  
  // 알림 및 시스템 설정
  const [settings, setSettings] = useState({
    smsNotify: true,
    emailNotify: true,
    pushNotify: true,
    autoNotify119: true,
    nightMode: true
  });

  // 활동 내역 목록
  const [activities, setActivities] = useState([]);

  // 모달 상태
  const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);

  // 폼 상태: 프로필 수정
  const [editForm, setEditForm] = useState({
    name: '',
    email: '',
    phone: '',
    dept: '',
    position: '',
    assignedZone: ''
  });

  // 폼 상태: 비밀번호 변경
  const [pwForm, setPwForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  });

  // 성공/에러 메시지 Toast
  const [toastMessage, setToastMessage] = useState(null);

  useEffect(() => {
    // 1. 세션 복원 또는 localStorage 정보 활용
    authApi.me().then(res => {
      if (res) {
        const user = {
          id: res.user_id,
          user_no: res.user_no,
          name: res.user_name || res.user_id,
          email: res.user_email || `${res.user_id}@fireguard.or.kr`,
          phone: res.user_phone || '',
          role: res.user_role === 'ADMIN' ? 'admin' : 'user',
          dept: res.user_role === 'ADMIN' ? '관제총괄팀' : '관제팀',
          position: res.user_role === 'ADMIN' ? '총괄 관제 책임자' : '관제 전담 요원',
          joinedAt: '2026-01-01',
          lastLogin: '최근 접속 중',
          assignedZone: 'A동 및 외곽 관제 구역'
        };
        setCurrentUser(user);
        localStorage.setItem('currentUser', JSON.stringify(user));
      }
    }).catch(() => {
      const storedUser = localStorage.getItem('currentUser');
      if (storedUser) {
        try {
          const parsed = JSON.parse(storedUser);
          if (parsed.name) parsed.name = parsed.name.replace(/\s*님$/, '');
          setCurrentUser(prev => ({ ...prev, ...parsed }));
        } catch (e) {
          console.error('사용자 정보 로드 실패:', e);
        }
      }
    });

    // 2. CCTV 목록 수신
    cctvApi.list().then(res => {
      const items = res?.items || res || [];
      if (Array.isArray(items)) {
        const mapped = items.map(item => ({
          id: `CCTV-${String(item.cctv_no).padStart(2, '0')}`,
          name: item.cctv_name,
          status: item.cctv_status === 'ACTIVE' ? 'normal' : 'offline',
          location: item.cctv_location,
          installedAt: item.cctv_created_at ? item.cctv_created_at.substring(0, 10) : '2026-01-01',
          lat: parseFloat(item.cctv_lat) || 37.5665,
          lng: parseFloat(item.cctv_lng) || 126.9780,
          stream_url: item.cctv_stream_url,
          history: []
        }));
        setMyCctvs(mapped);
      }
    }).catch(err => console.warn('MyPage CCTV 로드 오류:', err))
      .finally(() => setIsCctvsLoading(false));

    // 3. 최근 활동 이력 수신
    eventApi.list({ size: 10 }).then(res => {
      const items = res?.items || [];
      if (Array.isArray(items)) {
        const mappedActs = items.map(ev => ({
          id: ev.event_no,
          time: ev.event_first_detected_at || '2026-08-10 14:00:00',
          type: ev.event_status === 'CONFIRMED' ? 'fire' : 'system',
          title: ev.event_class === 'FLAME_SMOKE' ? '화재 및 연기 감지' : '화재 의심 상태 감지',
          detail: `${ev.cctv_name || '카메라'} 위치 (${ev.cctv_location || '관제 구역'})`
        }));
        setActivities(mappedActs);
      }
    }).catch(err => console.warn('MyPage 활동이력 로드 오류:', err));
  }, []);

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3000);
  };

  const isAdmin = currentUser?.role === 'admin';

  const handleLogout = () => {
    localStorage.removeItem('currentUser');
    navigate('/login');
  };

  // 프로필 수정 모달 열기
  const openEditModal = () => {
    setEditForm({
      name: currentUser.name || '',
      email: currentUser.email || '',
      phone: currentUser.phone || '',
      dept: currentUser.dept || '',
      position: currentUser.position || '',
      assignedZone: currentUser.assignedZone || ''
    });
    setIsEditProfileOpen(true);
  };

  // 관리자 승격 승인 요청 보내기
  const handleRequestAdmin = () => {
    const updated = {
      ...currentUser,
      adminRequested: true,
      adminRequestStatus: 'PENDING'
    };
    setCurrentUser(updated);
    localStorage.setItem('currentUser', JSON.stringify(updated));
    showToast('관리자 승격 요청이 제출되었습니다! 관리자의 승인 후 관리자로 승격됩니다.');
  };

  // 프로필 수정 저장
  const handleSaveProfile = (e) => {
    e.preventDefault();
    const updated = {
      ...currentUser,
      ...editForm
    };
    setCurrentUser(updated);
    localStorage.setItem('currentUser', JSON.stringify(updated));
    setIsEditProfileOpen(false);
    showToast('프로필 정보(직책 포함)가 성공적으로 수정되었습니다.');
  };

  // 비밀번호 변경 저장
  const handleSavePassword = (e) => {
    e.preventDefault();
    if (!pwForm.currentPassword) {
      alert('현재 비밀번호를 입력해주세요.');
      return;
    }
    if (pwForm.newPassword.length < 4) {
      alert('새 비밀번호는 최소 4자리 이상이어야 합니다.');
      return;
    }
    if (pwForm.newPassword !== pwForm.confirmPassword) {
      alert('새 비밀번호와 비밀번호 확인이 일치하지 않습니다.');
      return;
    }

    setPwForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
    setIsChangePasswordOpen(false);
    showToast('비밀번호가 안전하게 변경되었습니다.');
  };

  // 설정을 변경할 때의 핸들러
  const toggleSetting = (key) => {
    setSettings(prev => {
      const next = { ...prev, [key]: !prev[key] };
      showToast('설정이 업데이트되었습니다.');
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-ui transition-colors duration-300">
      
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-primary text-on-primary px-5 py-3 rounded-full text-body-sm font-medium shadow-lg flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* 1. 상단 네비게이션 바 (GNB) */}
      <header className="flex items-center justify-between px-6 h-14 border-b border-hairline shrink-0 bg-canvas z-20 sticky top-0">
        <div className="flex items-center gap-3">
          <Link to="/dashboard" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <AlertTriangle className="w-5 h-5 text-ink" />
            <span className="font-display text-heading-md tracking-tight">FireGuard</span>
          </Link>

          {/* 권한 표시 배지 */}
          {isAdmin ? (
            <span className="flex items-center gap-1.5 text-xs bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold px-3 py-1 rounded-full border border-amber-500/30">
              <ShieldCheck className="w-4 h-4" /> 관리자 권한
            </span>
          ) : (
            <span className="text-xs bg-surface-soft text-mute px-2.5 py-1 rounded-full border border-hairline">
              일반 관제회원
            </span>
          )}
        </div>

        <div className="flex items-center gap-6">
          <nav className="flex items-center gap-6 text-body-sm-strong text-body">
            <span className="text-ink font-bold underline decoration-ink underline-offset-4 cursor-default">마이페이지</span>

            <button onClick={() => navigate('/dashboard')} className="hover:text-ink transition-colors cursor-pointer">
              CCTV 모니터링
            </button>

            {isAdmin && (
              <button
                onClick={() => navigate('/admin')}
                className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400 font-bold bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 px-3 py-1 rounded-full transition-all text-xs cursor-pointer"
              >
                <span>관리자 페이지</span>
              </button>
            )}
          </nav>

          <div className="flex items-center gap-3">
            <span className="text-xs text-white font-bold bg-neutral-900 dark:bg-neutral-800 px-3 py-1 rounded-full border border-neutral-700 hidden sm:inline-flex items-center shadow-xs">
              {currentUser?.name ? `${currentUser.name.replace(/\s*님$/, '')}님` : '사용자님'}
            </span>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 bg-primary text-on-primary px-4 h-[34px] rounded-full text-button-md hover:bg-ink-deep transition-colors focus:outline-none focus-visible:outline-none text-xs cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>로그아웃</span>
            </button>
          </div>
        </div>
      </header>

      {/* 메인 컨텐츠 영역 */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 space-y-8">
        
        {/* 뒤로가기 링크 & 타이틀 헤더 */}
        <div className="flex items-center justify-between border-b border-hairline pb-4">
          <div>
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-1.5 text-body-sm text-mute hover:text-ink transition-colors mb-2 cursor-pointer focus:outline-none"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>대시보드로 돌아가기</span>
            </button>
            <h1 className="text-heading-xl font-display tracking-tight text-ink">내 계정 프로필</h1>
            <p className="text-body-sm text-mute mt-1">계정 상세 정보 관리 및 화재 알림 시스템 개인 설정을 진행합니다.</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={openEditModal}
              className="flex items-center gap-2 bg-surface-soft hover:bg-hairline text-ink px-4 h-10 rounded-full text-body-sm font-medium border border-hairline transition-colors focus:outline-none cursor-pointer"
            >
              <Edit3 className="w-4 h-4 text-mute" />
              <span>프로필 수정</span>
            </button>
            <button
              onClick={() => setIsChangePasswordOpen(true)}
              className="flex items-center gap-2 bg-primary text-on-primary hover:bg-ink-deep px-4 h-10 rounded-full text-body-sm font-medium transition-colors focus:outline-none cursor-pointer"
            >
              <Key className="w-4 h-4" />
              <span>비밀번호 변경</span>
            </button>
          </div>
        </div>

        {/* 1. 프로필 요약 카드 (Profile Overview Card) */}
        <section className="bg-canvas border border-hairline rounded-2xl p-6 sm:p-8 shadow-sm">
          <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
            
            {/* 프로필 이미지/아바타 */}
            <div className="relative group">
              <div className="w-24 h-24 sm:w-28 sm:h-28 rounded-full bg-surface-soft border-2 border-hairline flex items-center justify-center text-3xl font-bold text-ink shrink-0 overflow-hidden shadow-inner">
                {currentUser?.avatar ? (
                  <img src={currentUser.avatar} alt="Profile" className="w-full h-full object-cover" />
                ) : (
                  <User className="w-12 h-12 text-mute" />
                )}
              </div>
              <button 
                onClick={openEditModal}
                className="absolute bottom-0 right-0 bg-primary text-on-primary p-2 rounded-full border border-canvas shadow hover:scale-105 transition-transform cursor-pointer"
                title="프로필 사진 수정"
              >
                <Camera className="w-4 h-4" />
              </button>
            </div>

            {/* 유저 이름 & 직책 정보 */}
            <div className="flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-heading-lg font-bold text-ink">{currentUser?.name || '사용자'}</h2>
                {isAdmin ? (
                  <span className="bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold text-xs px-3 py-1 rounded-full border border-amber-500/30 flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" /> 총괄 관리자
                  </span>
                ) : (
                  <span className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold text-xs px-3 py-1 rounded-full border border-emerald-500/30 flex items-center gap-1">
                    <User className="w-3.5 h-3.5" /> {currentUser?.dept || '관제 요원'}
                  </span>
                )}
                <span className="text-caption-sm text-mute border border-hairline px-2.5 py-0.5 rounded-full bg-surface-soft">
                  ID: {currentUser?.id || '-'}
                </span>
              </div>

              <p className="text-body-md text-mute flex items-center gap-2 flex-wrap">
                <Building className="w-4 h-4 text-mute shrink-0" />
                <span>{currentUser?.dept || '부서 미지정'}</span>
                <span className="text-hairline">|</span>
                <span className="font-semibold text-ink">직책: {currentUser?.position || '직책 미입력'}</span>
              </p>

              {/* 관리자 승인 요청 상태 배지 및 버튼 */}
              <div className="pt-2 flex items-center gap-3">
                {!isAdmin && (
                  currentUser?.adminRequested || currentUser?.adminRequestStatus === 'PENDING' ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-600 bg-amber-500/10 border border-amber-500/30 px-3.5 py-1.5 rounded-full">
                      <span>⏳</span>
                      <span>관리자 승격 승인 요청 대기 중</span>
                    </span>
                  ) : (
                    <button
                      onClick={handleRequestAdmin}
                      className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-600 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 px-3.5 py-1.5 rounded-full transition-all cursor-pointer shadow-xs"
                    >
                      <span>👑</span>
                      <span>관리자 승인 요청 보내기</span>
                    </button>
                  )
                )}
              </div>

              <div className="pt-2 flex flex-wrap gap-y-2 gap-x-6 text-body-sm text-mute">
                <div className="flex items-center gap-1.5">
                  <Mail className="w-4 h-4 text-mute" />
                  <span>{currentUser?.email || '이메일 없음'}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Phone className="w-4 h-4 text-mute" />
                  <span>{currentUser?.phone || '연락처 미등록'}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-mute" />
                  <span>가입일: {currentUser?.joinedAt || '2026-01-01'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* 내가 설치/등록한 카메라 자산 현황 박스 */}
          <div className="mt-6 pt-6 border-t border-hairline flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-surface-soft p-4 rounded-xl">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-canvas rounded-lg border border-hairline text-ink">
                <Video className="w-5 h-5 text-amber-500" />
              </div>
              <div>
                <p className="text-caption-sm text-mute uppercase tracking-wider font-semibold">내가 직접 설치 / 등록한 CCTV 카메라</p>
                <div className="text-body-sm font-semibold text-ink mt-0.5 flex items-center gap-2 flex-wrap">
                  <span className="text-amber-600 dark:text-amber-400 font-bold bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                    총 {myCctvs.length}대 등록됨 (클릭 시 실시간 비디오)
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {myCctvs.map(c => (
                      <button
                        key={c.id}
                        onClick={() => setSelectedMyCctv(c)}
                        className="text-xs font-semibold text-ink bg-canvas hover:bg-surface-soft hover:border-amber-500 px-2 py-0.5 rounded border border-hairline transition-colors cursor-pointer inline-flex items-center gap-1"
                        title={`${c.name} 실시간 비디오 재생`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                        <span>{c.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div className="text-xs text-mute flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              <span>최근 접속: {currentUser?.lastLogin || '2026-08-10 10:25:12'}</span>
            </div>
          </div>
        </section>

        {/* 3. 내가 등록 및 관리하는 CCTV 목록 & 이력 카드 */}
        <section className="bg-canvas border border-hairline rounded-2xl p-6 sm:p-8 space-y-6 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-hairline pb-4 gap-2">
            <div>
              <h3 className="text-heading-md font-bold text-ink flex items-center gap-2">
                <Video className="w-5 h-5 text-ink" />
                <span>내 등록/담당 CCTV 목록 ({isCctvsLoading ? '조회중...' : `${myCctvs.length}대`})</span>
              </h3>
              <p className="text-body-sm text-mute mt-0.5">내가 직접 등록했거나 전담 관제 중인 CCTV 카메라 및 상태 변동 이력입니다.</p>
            </div>
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-1.5 text-xs text-primary hover:text-ink font-semibold px-3 py-1.5 rounded-full border border-hairline hover:bg-surface-soft transition-colors shrink-0 self-start sm:self-auto cursor-pointer"
            >
              <span>대시보드 지도에서 전체 확인</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>

          {isCctvsLoading ? (
            <div className="flex flex-col items-center justify-center py-12 text-mute space-y-3 bg-surface-soft/40 border border-hairline rounded-xl">
              <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
              <span className="text-xs font-semibold text-body">백엔드 DB에서 담당 CCTV 자산 목록을 불러오는 중입니다...</span>
            </div>
          ) : myCctvs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-mute space-y-2 bg-surface-soft/30 border border-hairline rounded-xl text-center">
              <Video className="w-8 h-8 text-mute/50" />
              <span className="text-xs font-medium">등록되거나 담당 중인 CCTV 카메라가 없습니다.</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {myCctvs.map((cctv) => (
                <div
                  key={cctv.id}
                  onClick={() => setSelectedMyCctv(cctv)}
                  className="p-4 rounded-xl border border-hairline bg-canvas hover:bg-surface-soft/60 hover:border-ink transition-all cursor-pointer space-y-3 shadow-xs group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-caption-sm font-mono text-mute bg-surface-soft px-2 py-0.5 rounded border border-hairline">
                      {cctv.id}
                    </span>
                    {cctv.status === 'fire' ? (
                      <span className="px-2.5 py-0.5 bg-terminal-red/10 text-terminal-red rounded-full text-caption-sm font-bold border border-terminal-red/20 animate-pulse">
                        위험 (화재)
                      </span>
                    ) : cctv.status === 'offline' ? (
                      <span className="px-2.5 py-0.5 bg-surface-soft text-mute rounded-full text-caption-sm font-medium border border-hairline">
                        오프라인
                      </span>
                    ) : (
                      <span className="px-2.5 py-0.5 bg-emerald-500/10 text-emerald-600 rounded-full text-caption-sm font-semibold border border-emerald-500/20">
                        정상 작동중
                      </span>
                    )}
                  </div>

                  <div>
                    <h4 className="text-body-sm-strong text-ink group-hover:text-primary transition-colors font-bold">{cctv.name}</h4>
                    <p className="text-caption-sm text-mute flex items-center gap-1 mt-1">
                      <MapPin className="w-3.5 h-3.5 text-mute" />
                      <span>{cctv.location}</span>
                    </p>
                  </div>

                  <div className="pt-2 border-t border-hairline/60 flex items-center justify-between text-caption-sm text-mute">
                    <span>감지 이력 {cctv.history?.length || 0}건</span>
                    <span className="text-ink font-semibold group-hover:underline flex items-center gap-1">
                      이력 보기 &rarr;
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 2컬럼 레이아웃: 좌측(알림 설정) / 우측(최근 활동 로그) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* 시스템 & 화재 알림 수신 설정 */}
          <section className="bg-canvas border border-hairline rounded-2xl p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-hairline pb-4">
              <div className="flex items-center gap-2">
                <Bell className="w-5 h-5 text-ink" />
                <h3 className="text-heading-md font-bold text-ink">화재 경보 & 알림 설정</h3>
              </div>
              <span className="text-caption-sm text-mute bg-surface-soft px-2.5 py-1 rounded-full border border-hairline">
                실시간 119 자동 연동
              </span>
            </div>

            <div className="space-y-4">
              {/* 토글 1: 긴급 SMS 알림 */}
              <div className="flex items-center justify-between p-3.5 hover:bg-surface-soft rounded-xl transition-colors">
                <div className="flex items-start gap-3">
                  <Smartphone className="w-5 h-5 text-mute mt-0.5" />
                  <div>
                    <p className="text-body-sm font-semibold text-ink">긴급 SMS 비상 문자 수신</p>
                    <p className="text-caption-sm text-mute">화재 감지 시 등록된 연락처로 긴급 SMS 전송</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => toggleSetting('smsNotify')}
                  className={`w-12 h-6 rounded-full transition-colors relative cursor-pointer focus:outline-none ${settings.smsNotify ? 'bg-primary' : 'bg-surface-soft border border-hairline'}`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-canvas transition-transform ${settings.smsNotify ? 'right-1' : 'left-1'}`} />
                </button>
              </div>

              {/* 토글 2: 이메일 경보 */}
              <div className="flex items-center justify-between p-3.5 hover:bg-surface-soft rounded-xl transition-colors">
                <div className="flex items-start gap-3">
                  <Mail className="w-5 h-5 text-mute mt-0.5" />
                  <div>
                    <p className="text-body-sm font-semibold text-ink">이메일 화재 리포트 수신</p>
                    <p className="text-caption-sm text-mute">일간/주간 화재 예방 및 미션 리포트 수신</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => toggleSetting('emailNotify')}
                  className={`w-12 h-6 rounded-full transition-colors relative cursor-pointer focus:outline-none ${settings.emailNotify ? 'bg-primary' : 'bg-surface-soft border border-hairline'}`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-canvas transition-transform ${settings.emailNotify ? 'right-1' : 'left-1'}`} />
                </button>
              </div>

              {/* 토글 3: 브라우저 웹 푸시 */}
              <div className="flex items-center justify-between p-3.5 hover:bg-surface-soft rounded-xl transition-colors">
                <div className="flex items-start gap-3">
                  <Monitor className="w-5 h-5 text-mute mt-0.5" />
                  <div>
                    <p className="text-body-sm font-semibold text-ink">웹 브라우저 데스크톱 푸시</p>
                    <p className="text-caption-sm text-mute">대시보드 미접속 상태에서도 브라우저 데스크톱 알림</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => toggleSetting('pushNotify')}
                  className={`w-12 h-6 rounded-full transition-colors relative cursor-pointer focus:outline-none ${settings.pushNotify ? 'bg-primary' : 'bg-surface-soft border border-hairline'}`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-canvas transition-transform ${settings.pushNotify ? 'right-1' : 'left-1'}`} />
                </button>
              </div>

              {/* 토글 4: 119 소방서 자동 신고 동의 */}
              <div className="flex items-center justify-between p-3.5 bg-amber-500/5 border border-amber-500/20 rounded-xl">
                <div className="flex items-start gap-3">
                  <ShieldAlert className="w-5 h-5 text-amber-500 mt-0.5" />
                  <div>
                    <p className="text-body-sm font-semibold text-ink">119 소방서 자동 긴급 신고 연동</p>
                    <p className="text-caption-sm text-mute">AI 화재 신뢰도 90% 이상 시 즉시 소방서 지능형 자동 신고</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => toggleSetting('autoNotify119')}
                  className={`w-12 h-6 rounded-full transition-colors relative cursor-pointer focus:outline-none ${settings.autoNotify119 ? 'bg-amber-600' : 'bg-surface-soft border border-hairline'}`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-canvas transition-transform ${settings.autoNotify119 ? 'right-1' : 'left-1'}`} />
                </button>
              </div>

            </div>
          </section>

          {/* 최근 활동 로그 및 관제 내역 */}
          <section className="bg-canvas border border-hairline rounded-2xl p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-hairline pb-4">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-ink" />
                <h3 className="text-heading-md font-bold text-ink">내 활동 및 접속 이력</h3>
              </div>
              <span className="text-caption-sm text-mute">최근 5건</span>
            </div>

            <div className="space-y-4">
              {activities.map((act) => (
                <div key={act.id} className="flex items-start gap-3.5 p-3 rounded-xl border border-hairline/60 hover:bg-surface-soft transition-colors">
                  <div className="p-2 rounded-lg bg-surface-soft border border-hairline text-ink shrink-0 mt-0.5">
                    {act.type === 'login' && <Monitor className="w-4 h-4 text-blue-500" />}
                    {act.type === 'fire' && <AlertTriangle className="w-4 h-4 text-red-500" />}
                    {act.type === 'admin' && <ShieldCheck className="w-4 h-4 text-amber-500" />}
                    {act.type === 'system' && <FileText className="w-4 h-4 text-emerald-500" />}
                    {act.type === 'setting' && <Bell className="w-4 h-4 text-purple-500" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="text-body-sm font-semibold text-ink truncate">{act.title}</p>
                      <span className="text-[11px] text-mute shrink-0">{act.time}</span>
                    </div>
                    <p className="text-caption-sm text-mute mt-0.5 truncate">{act.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

        </div>

      </main>

      {/* ------------------------------------------------------------- */}
      {/* 팝업 모달 0: CCTV 상세 상태 및 변동 이력 다이얼로그 모달 */}
      {/* ------------------------------------------------------------- */}
      {selectedMyCctv && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <div
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden"
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
              <div className="flex items-center gap-2">
                <Video className="w-5 h-5 text-ink" />
                <h3 className="text-heading-md font-bold text-ink">{selectedMyCctv.name}</h3>
                <span className="text-caption-sm font-mono text-mute bg-surface-soft px-2 py-0.5 rounded border border-hairline">
                  {selectedMyCctv.id}
                </span>
              </div>
              <button
                onClick={() => setSelectedMyCctv(null)}
                className="p-1 text-mute hover:text-ink rounded-full transition-colors focus:outline-none cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 max-h-[75vh] overflow-y-auto space-y-4">
              {/* 실시간 HLS 비디오 스트리밍 플레이어 */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-ink flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                    <span>실시간 HLS 비디오 스트림</span>
                  </span>
                  <span className="text-caption-sm text-mute font-mono">24 FPS · Live</span>
                </div>
                <CctvPlayer
                  key={selectedMyCctv.id}
                  streamUrl={selectedMyCctv.stream_url || selectedMyCctv.cctv_stream_url || 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4'}
                  cctvName={selectedMyCctv.name}
                  isFire={selectedMyCctv.status === 'fire'}
                />
              </div>

              <div className="bg-surface-soft p-4 rounded-xl space-y-2 border border-hairline text-body-sm">
                <div className="flex justify-between">
                  <span className="text-mute">현재 카메라 상태:</span>
                  {selectedMyCctv.status === 'fire' ? (
                    <span className="text-terminal-red font-bold">🔥 위험 (화재 감지)</span>
                  ) : selectedMyCctv.status === 'offline' ? (
                    <span className="text-mute font-bold">오프라인</span>
                  ) : (
                    <span className="text-emerald-600 font-bold">🟢 정상 작동중</span>
                  )}
                </div>
                <div className="flex justify-between">
                  <span className="text-mute">설치 위치:</span>
                  <span className="text-ink font-medium">{selectedMyCctv.location}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-mute">GPS 위치 좌표:</span>
                  <span className="text-ink font-mono text-xs">Lat {selectedMyCctv.lat}, Lng {selectedMyCctv.lng}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-mute">최초 설치/등록일:</span>
                  <span className="text-ink font-medium">{selectedMyCctv.installedAt}</span>
                </div>
              </div>

              <div>
                <h4 className="text-body-sm-strong font-bold text-ink mb-3 flex items-center justify-between">
                  <span>📋 카메라 상태 변동 & 탐지 이력</span>
                  <span className="text-caption-sm font-normal text-mute">총 {selectedMyCctv.history?.length || 0}건</span>
                </h4>
                <div className="space-y-2.5">
                  {selectedMyCctv.history && selectedMyCctv.history.length > 0 ? (
                    selectedMyCctv.history.map(item => (
                      <div key={item.id} className="p-3 rounded-xl border border-hairline bg-canvas text-xs space-y-1">
                        <div className="flex items-center justify-between text-mute">
                          <span className="font-mono text-[11px]">{item.time}</span>
                          {item.type === 'fire' && <span className="text-terminal-red font-bold bg-terminal-red/10 px-2 py-0.5 rounded-full">화재 경보</span>}
                          {item.type === 'offline' && <span className="text-amber-500 font-bold bg-amber-500/10 px-2 py-0.5 rounded-full">연결 장애</span>}
                          {item.type === 'normal' && <span className="text-emerald-600 font-medium bg-emerald-500/10 px-2 py-0.5 rounded-full">정상점검</span>}
                          {item.type === 'system' && <span className="text-blue-500 font-medium bg-blue-500/10 px-2 py-0.5 rounded-full">시스템</span>}
                        </div>
                        <p className="text-ink font-medium text-body-sm leading-relaxed">{item.message}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-body-sm text-mute text-center py-6">기록된 카메라 감지 이력이 없습니다.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-between shrink-0">
              <button
                type="button"
                onClick={() => {
                  setSelectedMyCctv(null);
                  navigate('/dashboard');
                }}
                className="flex items-center gap-1.5 text-xs text-primary font-semibold hover:underline cursor-pointer"
              >
                <span>CCTV 모니터링 화면으로 보기</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setSelectedMyCctv(null)}
                className="px-5 h-10 rounded-full bg-primary text-on-primary text-body-sm font-medium hover:bg-ink-deep transition-colors focus:outline-none cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 팝업 모달 1: 프로필 수정 다이얼로그 (ui_modal_rules 수칙 준수) */}
      {/* ------------------------------------------------------------- */}
      {isEditProfileOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          {/* Outer Card with Explicit Width constraints */}
          <div
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden"
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          >
            {/* Modal Header (shrink-0) */}
            <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
              <h3 className="text-heading-md font-bold text-ink flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-mute" />
                <span>프로필 정보 수정</span>
              </h3>
              <button
                onClick={() => setIsEditProfileOpen(false)}
                className="p-1 text-mute hover:text-ink rounded-full transition-colors focus:outline-none cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Form Content (Scrollable & Spacing) */}
            <form onSubmit={handleSaveProfile} className="flex flex-col shrink-0">
              <div className="p-6 max-h-[70vh] overflow-y-auto space-y-4">
                <div>
                  <label className="block text-body-sm font-semibold text-ink mb-1">이름</label>
                  <input
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    required
                  />
                </div>

                <div>
                  <label className="block text-body-sm font-semibold text-ink mb-1">이메일 주소</label>
                  <input
                    type="email"
                    value={editForm.email}
                    onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    required
                  />
                </div>

                <div>
                  <label className="block text-body-sm font-semibold text-ink mb-1">연락처 (전화번호)</label>
                  <input
                    type="text"
                    value={editForm.phone}
                    onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="010-0000-0000"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-body-sm font-semibold text-ink mb-1">소속 부서</label>
                    <input
                      type="text"
                      value={editForm.dept}
                      onChange={(e) => setEditForm({ ...editForm, dept: e.target.value })}
                      className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                      placeholder="예: 관제1팀, 시설팀"
                    />
                  </div>
                  <div>
                    <label className="block text-body-sm font-semibold text-ink mb-1">직책 (사용자 입력)</label>
                    <input
                      type="text"
                      value={editForm.position}
                      onChange={(e) => setEditForm({ ...editForm, position: e.target.value })}
                      className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                      placeholder="예: 관제팀장, 보안담당관"
                    />
                  </div>
                </div>

                <div className="p-3.5 bg-surface-soft border border-hairline rounded-xl space-y-1">
                  <span className="block text-caption-sm text-mute font-semibold">📹 내가 설치 / 등록한 CCTV 카메라 ({myCctvs.length}대 - 클릭시 실시간 재생)</span>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {myCctvs.map(c => (
                      <button
                        type="button"
                        key={c.id}
                        onClick={() => {
                          setIsEditProfileOpen(false);
                          setSelectedMyCctv(c);
                        }}
                        className="text-xs font-semibold text-ink bg-canvas hover:bg-surface-soft hover:border-amber-500 px-2.5 py-1 rounded-lg border border-hairline flex items-center gap-1 transition-colors cursor-pointer"
                        title={`${c.name} 실시간 비디오 모니터링`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                        <span>{c.name} ({c.id})</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* 👑 관리자 승인 요청 섹션 (일반 사용자일 경우에만 노출) */}
                {!isAdmin && (
                  <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl space-y-2 mt-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-bold text-xs">
                        <span>👑</span>
                        <span>관리자 권한 승격 신청</span>
                      </div>
                      {currentUser.adminRequested || currentUser.adminRequestStatus === 'PENDING' ? (
                        <span className="text-[11px] font-bold text-amber-500 bg-amber-500/20 px-2.5 py-0.5 rounded-full border border-amber-500/30 animate-pulse">
                          ⏳ 승인 대기 중
                        </span>
                      ) : null}
                    </div>
                    <p className="text-caption-sm text-ink/80 leading-relaxed">
                      최고 관리자에게 승인 요청을 전송합니다. 관리자가 승인하면 관리자 전용 대시보드 및 시스템 설정 권한으로 승격됩니다.
                    </p>

                    <button
                      type="button"
                      onClick={handleRequestAdmin}
                      disabled={currentUser.adminRequested || currentUser.adminRequestStatus === 'PENDING'}
                      className="w-full h-10 mt-1 bg-amber-500 hover:bg-amber-600 active:scale-[0.99] text-white font-bold text-xs rounded-xl transition-all shadow-xs flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span>👑</span>
                      <span>
                        {currentUser.adminRequested || currentUser.adminRequestStatus === 'PENDING'
                          ? '관리자 승인 요청됨 (대기 중)'
                          : '관리자 승인 요청 보내기'}
                      </span>
                    </button>
                  </div>
                )}
              </div>

              {/* Modal Footer (shrink-0) */}
              <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-end gap-3 shrink-0">
                <button
                  type="button"
                  onClick={() => setIsEditProfileOpen(false)}
                  className="px-5 h-11 rounded-full text-body-sm font-medium text-body hover:text-ink transition-colors focus:outline-none cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-2 px-6 h-11 bg-primary text-on-primary rounded-full text-body-sm font-medium hover:bg-ink-deep transition-colors focus:outline-none cursor-pointer"
                >
                  <Save className="w-4 h-4" />
                  <span>저장하기</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 팝업 모달 2: 비밀번호 변경 다이얼로그 (ui_modal_rules 수칙 준수) */}
      {/* ------------------------------------------------------------- */}
      {isChangePasswordOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          {/* Outer Card with Explicit Width constraints */}
          <div
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden"
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          >
            {/* Modal Header (shrink-0) */}
            <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
              <h3 className="text-heading-md font-bold text-ink flex items-center gap-2">
                <Lock className="w-5 h-5 text-mute" />
                <span>비밀번호 변경</span>
              </h3>
              <button
                onClick={() => setIsChangePasswordOpen(false)}
                className="p-1 text-mute hover:text-ink rounded-full transition-colors focus:outline-none cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Form Content */}
            <form onSubmit={handleSavePassword} className="flex flex-col shrink-0">
              <div className="p-6 max-h-[70vh] overflow-y-auto space-y-4">
                <div>
                  <label className="block text-body-sm font-semibold text-ink mb-1">현재 비밀번호</label>
                  <input
                    type="password"
                    value={pwForm.currentPassword}
                    onChange={(e) => setPwForm({ ...pwForm, currentPassword: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="현재 사용 중인 비밀번호"
                    required
                  />
                </div>

                <div>
                  <label className="block text-body-sm font-semibold text-ink mb-1">새 비밀번호</label>
                  <input
                    type="password"
                    value={pwForm.newPassword}
                    onChange={(e) => setPwForm({ ...pwForm, newPassword: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="새 비밀번호 (최소 4자리)"
                    required
                  />
                </div>

                <div>
                  <label className="block text-body-sm font-semibold text-ink mb-1">새 비밀번호 확인</label>
                  <input
                    type="password"
                    value={pwForm.confirmPassword}
                    onChange={(e) => setPwForm({ ...pwForm, confirmPassword: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="새 비밀번호 재입력"
                    required
                  />
                </div>
              </div>

              {/* Modal Footer (shrink-0) */}
              <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-end gap-3 shrink-0">
                <button
                  type="button"
                  onClick={() => setIsChangePasswordOpen(false)}
                  className="px-5 h-11 rounded-full text-body-sm font-medium text-body hover:text-ink transition-colors focus:outline-none cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-2 px-6 h-11 bg-primary text-on-primary rounded-full text-body-sm font-medium hover:bg-ink-deep transition-colors focus:outline-none cursor-pointer"
                >
                  <Key className="w-4 h-4" />
                  <span>비밀번호 변경</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 푸터 */}
      <footer className="w-full bg-canvas text-body font-ui text-caption-sm border-t border-hairline py-6 px-6 text-center text-mute mt-auto">
        <p>&copy; {new Date().getFullYear()} FireGuard Fire Prevention & Detection System</p>
      </footer>
    </div>
  );
}
