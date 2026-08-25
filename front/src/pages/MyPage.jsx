import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminUpgradeApi } from '../api';
import {
  User, ShieldCheck, Mail, Phone, Calendar,
  Lock, Bell, Key, CheckCircle, Clock,
  ArrowLeft, Edit3, Save, X, AlertTriangle,
  FileText, Activity, Smartphone, Monitor, ShieldAlert, Video, MapPin, ExternalLink, Loader2,
  LogOut, RotateCcw, ChevronLeft, ChevronRight
} from 'lucide-react';

import CctvPlayer from '../components/CctvPlayer';
import AppHeader from '../components/AppHeader';
import MyPagePasswordGate from '../components/MyPagePasswordGate';
import PasswordInput from '../components/PasswordInput';
import { cctvApi, userApi } from '../api';
import { useAuth } from '../context/authState';
import {
  appendLocalActivityLog,
  getLocalActivityLogs,
  normalizeActivityRecord,
} from '../utils/activityLog';

const normalizePhoneNumber = (value = '') => (
  String(value).replace(/\D/g, '').slice(0, 11)
);

const formatPhoneNumber = (value = '') => {
  const digits = normalizePhoneNumber(value);

  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  if (digits.length <= 10) {
    return `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
};

/**
 * 1, 2, ..., 10, 11 형태의 생략 기호가 포함된 페이지네이션 배열 생성
 */
const getPaginationRange = (currentPage, totalPages) => {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, '...', totalPages];
  }

  if (currentPage >= totalPages - 3) {
    return [1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }

  return [1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages];
};

export default function MyPage() {
  const navigate = useNavigate();
  const { logout, refreshSession, user: currentUser } = useAuth();

  // 마이페이지 진입 전 개인정보 보호를 위한 비밀번호 확인 상태
  const [isPasswordVerified, setIsPasswordVerified] = useState(false);
  const [myPagePassword, setMyPagePassword] = useState('');
  const [passwordVerificationError, setPasswordVerificationError] = useState('');
  const [isPasswordVerifying, setIsPasswordVerifying] = useState(false);

  // 내 활동 및 접속 이력 페이지네이션 및 로딩 상태
  const [activityPage, setActivityPage] = useState(1);
  const [isActivitiesLoading, setIsActivitiesLoading] = useState(true);
  const [activityTotal, setActivityTotal] = useState(0);
  const [activityTotalPages, setActivityTotalPages] = useState(0);
  const [activityError, setActivityError] = useState('');
  const [activityRefreshKey, setActivityRefreshKey] = useState(0);
  const ITEMS_PER_PAGE = 5;

  // 내 관리 CCTV 모달 및 로딩 상태
  const [myCctvs, setMyCctvs] = useState([]);
  const [isCctvsLoading, setIsCctvsLoading] = useState(true);
  const [selectedMyCctv, setSelectedMyCctv] = useState(null);
  
  // 알림 및 시스템 설정
  const [settings, setSettings] = useState({
    smsNotify: true,
    emailNotify: true,
    pushNotify: true,
    nightMode: true
  });

  // 활동 내역 목록
  const [activities, setActivities] = useState([]);

  // 모달 상태
  const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);
  const [isPasswordChangeNoticeOpen, setIsPasswordChangeNoticeOpen] = useState(false);

  // 폼 상태: 프로필 수정
  const [editForm, setEditForm] = useState({
    name: '',
    email: '',
    phone: '',
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
    if (!isPasswordVerified || !currentUser?.user_no) return undefined;

    let cancelled = false;
    setIsCctvsLoading(true);

    const loadCurrentUserCctvs = async () => {
      try {
        const isSessionAdmin = currentUser.role === 'admin';
        const cctvResponse = await cctvApi.list(
          isSessionAdmin ? {} : { user_no: currentUser.user_no }
        );
        const items = cctvResponse?.items || cctvResponse || [];
        const accessibleItems = Array.isArray(items)
          ? isSessionAdmin
            ? items
            : items.filter((item) => String(item.user_no) === String(currentUser.user_no))
          : [];

        const mapped = accessibleItems.map(item => ({
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
        if (!cancelled) setMyCctvs(mapped);
      } catch (error) {
        if (!cancelled) setMyCctvs([]);
        console.warn('MyPage CCTV 권한 확인 오류:', error.message);
      } finally {
        if (!cancelled) setIsCctvsLoading(false);
      }
    };

    loadCurrentUserCctvs();
    return () => {
      cancelled = true;
    };
  }, [currentUser, isPasswordVerified]);

  useEffect(() => {
    if (!isPasswordVerified || !currentUser?.user_no) return;

    setActivityError('');

    const localActivities = getLocalActivityLogs(currentUser.user_no)
      .map(normalizeActivityRecord);
    const localTotalPages = Math.ceil(localActivities.length / ITEMS_PER_PAGE);
    const localStart = (activityPage - 1) * ITEMS_PER_PAGE;

    setActivities(localActivities.slice(localStart, localStart + ITEMS_PER_PAGE));
    setActivityTotal(localActivities.length);
    setActivityTotalPages(localTotalPages);
    setIsActivitiesLoading(false);
  }, [isPasswordVerified, currentUser?.user_no, activityPage, activityRefreshKey]);

  const handleVerifyMyPagePassword = async (event) => {
    event.preventDefault();

    if (!myPagePassword) {
      setPasswordVerificationError('현재 비밀번호를 입력해주세요.');
      return;
    }

    setIsPasswordVerifying(true);
    setPasswordVerificationError('');

    try {
      const response = await userApi.verifyMyPagePassword(myPagePassword);

      if (!response?.verified) {
        setPasswordVerificationError(response?.message || '비밀번호가 일치하지 않습니다.');
        return;
      }

      setMyPagePassword('');
      setIsPasswordVerified(true);
    } catch (error) {
      if (error.status === 401) {
        return;
      }

      setPasswordVerificationError(
        error.message || '비밀번호 확인 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
      );
    } finally {
      setIsPasswordVerifying(false);
    }
  };

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3000);
  };

  const isAdmin = currentUser?.role === 'admin';
  const isSocialAccount = Boolean(currentUser?.authProvider);

  if (!isPasswordVerified) {
    return (
      <MyPagePasswordGate
        password={myPagePassword}
        onPasswordChange={(value) => {
          setMyPagePassword(value);
          if (passwordVerificationError) setPasswordVerificationError('');
        }}
        onSubmit={handleVerifyMyPagePassword}
        onCancel={() => navigate('/dashboard')}
        errorMessage={passwordVerificationError}
        isSubmitting={isPasswordVerifying}
      />
    );
  }

  const handleResetActivities = () => {
    setActivityPage(1);
    setActivityRefreshKey((current) => current + 1);
    showToast('활동 이력을 최신 상태로 초기화했습니다.');
  };

  // 프로필 수정 모달 열기
  const openEditModal = () => {
    setEditForm({
      name: currentUser.name || '',
      email: currentUser.email || '',
      phone: formatPhoneNumber(currentUser.phone || ''),
      assignedZone: currentUser.assignedZone || ''
    });
    setIsEditProfileOpen(true);
  };

  // 관리자 승격 승인 요청 보내기
  const handleRequestUpgrade = async () => {
    try {
      await adminUpgradeApi.requestUpgrade();
      await refreshSession().catch((sessionError) => {
        console.warn('관리자 승격 요청 상태 갱신 오류:', sessionError);
      });
      showToast('관리자 승격 요청을 전송했습니다.');
    } catch (err) {
      console.error('승급 요청 실패:', err);
      showToast(err.message || '관리자 승격 요청에 실패했습니다.');
    }
  };

  // 프로필 수정 저장
  const handleSaveProfile = async (e) => {
    e.preventDefault();
    if (!currentUser?.user_no) {
      showToast('사용자 정보를 확인할 수 없어 저장하지 못했습니다. 다시 로그인해 주세요.');
      return;
    }

    const name = editForm.name.trim();
    const phone = normalizePhoneNumber(editForm.phone);
    const email = editForm.email.trim();
    const profilePayload = {
      user_name: name,
      user_phone: phone || null,
    };

    if (!isSocialAccount) {
      profilePayload.user_email = email;
    }

    try {
      await userApi.update(currentUser.user_no, profilePayload);
      const updatedUser = {
        ...currentUser,
        name,
        phone,
        ...(isSocialAccount ? {} : { email }),
      };
      await refreshSession().catch((sessionError) => {
        console.warn('수정된 프로필 세션 갱신 오류:', sessionError);
      });
      appendLocalActivityLog({
        user_no: updatedUser.user_no,
        activity_type: 'PROFILE_UPDATE',
        type: 'system',
        title: '프로필 정보 수정',
        detail: isSocialAccount
          ? '이름 또는 연락처 정보를 변경했습니다.'
          : '이름, 이메일 또는 연락처 정보를 변경했습니다.',
      });
      setIsEditProfileOpen(false);
      setActivityPage(1);
      setActivityRefreshKey((current) => current + 1);
      showToast('프로필 정보가 저장되었습니다.');
    } catch (error) {
      showToast(error.message || '프로필 저장에 실패했습니다.');
    }
  };

  // 비밀번호 변경 저장
  const handleSavePassword = async (e) => {
    e.preventDefault();
    if (currentUser?.authProvider) {
      showToast('소셜 로그인 계정은 해당 소셜 서비스에서 비밀번호를 관리합니다.');
      return;
    }
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

    const token = localStorage.getItem('access_token');

    try {
      const response = await fetch('/api/users/password', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          current_password: pwForm.currentPassword,
          new_password: pwForm.newPassword
        })
      });

      const data = await response.json();

      if (!response.ok) {
        alert(data.message || '비밀번호 변경에 실패했습니다.');
        return;
      }

      setIsChangePasswordOpen(false);
      setPwForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
      appendLocalActivityLog({
        user_no: currentUser.user_no,
        activity_type: 'PASSWORD_CHANGE',
        type: 'setting',
        title: '비밀번호 변경',
        detail: '계정 비밀번호를 변경했습니다.',
      });
      setActivityPage(1);
      setActivityRefreshKey((current) => current + 1);
      setIsPasswordChangeNoticeOpen(true);

    } catch (error) {
      console.error('Password change error:', error);
      alert('서버 통신 중 오류가 발생했습니다.');
    }
  };

  // 알림 설정 변경 핸들러
  const toggleSetting = (key) => {
    const nextValue = !settings[key];
    const settingLabels = {
      smsNotify: '긴급 SMS 알림',
      emailNotify: '이메일 화재 리포트',
      pushNotify: '브라우저 웹 푸시',
      nightMode: '야간 모드',
    };

    setSettings(prev => ({ ...prev, [key]: nextValue }));
    appendLocalActivityLog({
      user_no: currentUser?.user_no,
      activity_type: 'SETTING_UPDATE',
      type: 'setting',
      title: '알림 설정 변경',
      detail: `${settingLabels[key] || '개인 설정'}을 ${nextValue ? '켜짐' : '꺼짐'}으로 변경했습니다.`,
    });
    setActivityPage(1);
    setActivityRefreshKey((current) => current + 1);
    showToast('설정이 업데이트되었습니다.');
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-ui transition-colors duration-300">
      
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-primary text-on-primary px-5 py-3 rounded-full text-body-sm font-semibold shadow-lg flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      <AppHeader
        currentPage="mypage"
        currentUser={currentUser}
        onLogout={logout}
      />

      {/* 메인 컨텐츠 영역 */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 space-y-8">
        
        {/* 뒤로가기 링크 & 타이틀 헤더 */}
        <div className="flex items-center justify-between border-b border-hairline pb-4">
          <div>
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-1.5 text-caption-sm font-semibold text-body hover:text-ink transition-colors mb-2 cursor-pointer focus:outline-none"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>대시보드로 돌아가기</span>
            </button>
            <h1 className="text-heading-xl font-display tracking-tight text-ink">내 계정 프로필</h1>
            <p className="text-body-sm font-medium text-body mt-1">계정 상세 정보 관리 및 화재 알림 시스템 개인 설정을 진행합니다.</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={openEditModal}
              className="flex items-center gap-2 bg-surface-soft hover:bg-hairline text-ink px-4 h-10 rounded-full text-caption-sm font-bold border border-hairline-strong transition-colors focus:outline-none cursor-pointer"
            >
              <Edit3 className="w-4 h-4 text-charcoal" />
              <span>프로필 수정</span>
            </button>
            {isSocialAccount ? (
              <span className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-hairline bg-surface-soft text-caption-sm font-bold text-body">
                <Key className="w-4 h-4" />
                <span>소셜 계정</span>
              </span>
            ) : (
              <button
                onClick={() => setIsChangePasswordOpen(true)}
                className="flex items-center gap-2 bg-primary text-on-primary hover:bg-ink-deep px-4 h-10 rounded-full text-caption-sm font-bold transition-colors focus:outline-none cursor-pointer shadow-xs"
              >
                <Key className="w-4 h-4" />
                <span>비밀번호 변경</span>
              </button>
            )}
          </div>
        </div>

        {/* 1. 프로필 요약 카드 (Profile Overview Card) */}
        <section className="bg-canvas border border-hairline rounded-2xl p-6 sm:p-8 shadow-xs">
          <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
            
            {/* 프로필 이미지/아바타 */}
            <div>
              <div className="w-24 h-24 sm:w-28 sm:h-28 rounded-full bg-surface-soft border-2 border-hairline-strong flex items-center justify-center text-3xl font-bold text-ink shrink-0 overflow-hidden shadow-inner">
                {currentUser?.avatar ? (
                  <img src={currentUser.avatar} alt="Profile" className="w-full h-full object-cover" />
                ) : (
                  <User className="w-12 h-12 text-mute" />
                )}
              </div>
            </div>

            {/* 유저 이름 및 권한 정보 */}
            <div className="flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-heading-lg font-bold text-ink">{currentUser?.name || '사용자'}</h2>
                {isAdmin ? (
                  <span className="bg-amber-500/10 text-amber-700 dark:text-amber-400 font-bold text-xs px-3 py-1 rounded-full border border-amber-500/30 flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" /> 총괄 관리자
                  </span>
                ) : (
                  <span className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-bold text-xs px-3 py-1 rounded-full border border-emerald-500/30 flex items-center gap-1">
                    <User className="w-3.5 h-3.5" /> 관제 요원
                  </span>
                )}
              </div>

              {/* 관리자 승인 요청 상태 배지 및 버튼 */}
              <div className="pt-2 flex items-center gap-3">
                {!isAdmin ? (
                currentUser?.status === 'PENDING' || currentUser?.user_status === 'PENDING' ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-700 bg-amber-500/10 border border-amber-500/30 px-3.5 py-1.5 rounded-full">
                      <span>⏳</span>
                      <span>관리자 승격 승인 요청 대기 중</span>
                    </span>
                  ) : (
                    <button
                      onClick={handleRequestUpgrade}
                      className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-700 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 px-3.5 py-1.5 rounded-full transition-all cursor-pointer shadow-xs"
                    >
                      <span>👑</span>
                      <span>관리자 승인 요청 보내기</span>
                    </button>
                  )
                ) : null}
              </div>

              <div className="pt-2 flex flex-wrap gap-y-2 gap-x-6 text-caption-sm font-medium text-body">
                <div className="flex items-center gap-1.5">
                  <Mail className="w-4 h-4 text-charcoal" />
                  <span>{currentUser?.email || '이메일 없음'}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Phone className="w-4 h-4 text-charcoal" />
                  <span>{formatPhoneNumber(currentUser?.phone) || '연락처 미등록'}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-charcoal" />
                  <span>가입일: {currentUser?.joinedAt || '2026-01-01'}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 3. 내가 등록 및 관리하는 CCTV 목록 카드 */}
        <section className="bg-canvas border border-hairline rounded-2xl p-6 sm:p-8 space-y-6 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-hairline pb-4 gap-2">
            <div>
              <h3 className="text-heading-md font-bold text-ink flex items-center gap-2">
                <Video className="w-5 h-5 text-ink" />
                <span>최근 등록 CCTV ({isCctvsLoading ? '조회중...' : `${Math.min(myCctvs.length, 3)} / ${myCctvs.length}대`})</span>
              </h3>
              <p className="text-body-sm font-medium text-body mt-0.5">최근 등록한 CCTV 3대의 상태를 확인합니다. 전체 영상과 지도는 실시간 관제에서 확인하세요.</p>
            </div>
            <button
              onClick={() => navigate('/monitoring')}
              className="flex items-center gap-1.5 text-xs text-primary hover:text-ink font-bold px-3 py-1.5 rounded-full border border-hairline hover:bg-surface-soft transition-colors shrink-0 self-start sm:self-auto cursor-pointer"
            >
              <span>실시간 관제에서 전체 확인</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>

          {isCctvsLoading ? (
            <div className="flex flex-col items-center justify-center py-12 text-body space-y-3 bg-surface-soft/40 border border-hairline rounded-xl">
              <Loader2 className="w-8 h-8 animate-spin text-ink" />
              <span className="text-caption-sm font-bold text-body">백엔드 DB에서 담당 CCTV 자산 목록을 불러오는 중입니다...</span>
            </div>
          ) : myCctvs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-body space-y-2 bg-surface-soft/30 border border-hairline rounded-xl text-center">
              <Video className="w-8 h-8 text-mute" />
              <span className="text-caption-sm font-semibold">등록되거나 담당 중인 CCTV 카메라가 없습니다.</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {myCctvs.slice(0, 3).map((cctv) => (
                <div
                  key={cctv.id}
                  onClick={() => setSelectedMyCctv(cctv)}
                  className="p-4 rounded-xl border border-hairline bg-canvas hover:bg-surface-soft/60 hover:border-ink transition-all cursor-pointer space-y-3 shadow-xs group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-caption-sm font-mono font-bold text-charcoal bg-surface-soft px-2 py-0.5 rounded border border-hairline">
                      {cctv.id}
                    </span>
                    {cctv.status === 'fire' ? (
                      <span className="px-2.5 py-0.5 bg-terminal-red/10 text-terminal-red rounded-full text-caption-sm font-bold border border-terminal-red/20 animate-pulse">
                        위험 (화재)
                      </span>
                    ) : cctv.status === 'offline' ? (
                      <span className="px-2.5 py-0.5 bg-surface-soft text-body rounded-full text-caption-sm font-semibold border border-hairline">
                        오프라인
                      </span>
                    ) : (
                      <span className="px-2.5 py-0.5 bg-emerald-500/10 text-emerald-700 rounded-full text-caption-sm font-bold border border-emerald-500/20">
                        정상 작동중
                      </span>
                    )}
                  </div>

                  <div>
                    <h4 className="text-body-sm-strong text-ink group-hover:text-primary transition-colors font-bold">{cctv.name}</h4>
                    <p className="text-caption-sm font-medium text-body flex items-center gap-1 mt-1">
                      <MapPin className="w-3.5 h-3.5 text-mute" />
                      <span>{cctv.location}</span>
                    </p>
                  </div>

                  <div className="pt-2 border-t border-hairline/60 flex items-center justify-between text-caption-sm text-body">
                    <span>상태 요약</span>
                    <span className="text-ink font-bold group-hover:underline flex items-center gap-1">
                      모니터링 &rarr;
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 2컬럼 레이아웃: 좌측(알림 설정) / 우측(최근 활동 로그 및 표준 번호 페이지네이션) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* 시스템 & 화재 알림 수신 설정 */}
          <section className="bg-canvas border border-hairline rounded-2xl p-6 space-y-6 shadow-xs">
            <div className="flex items-center justify-between border-b border-hairline pb-4">
              <div className="flex items-center gap-2">
                <Bell className="w-5 h-5 text-ink" />
                <h3 className="text-heading-md font-bold text-ink">화재 경보 & 알림 설정</h3>
              </div>
            </div>

            <div className="space-y-4">
              {/* 토글 1: 긴급 SMS 알림 */}
              <div className="flex items-center justify-between p-3.5 hover:bg-surface-soft rounded-xl transition-colors">
                <div className="flex items-start gap-3">
                  <Smartphone className="w-5 h-5 text-mute mt-0.5" />
                  <div>
                    <p className="text-body-sm font-bold text-ink">긴급 SMS 비상 문자 수신</p>
                    <p className="text-caption-sm font-medium text-body">화재 감지 시 등록된 연락처로 긴급 SMS 전송</p>
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
                    <p className="text-body-sm font-bold text-ink">이메일 화재 리포트 수신</p>
                    <p className="text-caption-sm font-medium text-body">일간/주간 화재 예방 및 미션 리포트 수신</p>
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
                    <p className="text-body-sm font-bold text-ink">웹 브라우저 데스크톱 푸시</p>
                    <p className="text-caption-sm font-medium text-body">대시보드 미접속 상태에서도 브라우저 데스크톱 알림</p>
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
            </div>
          </section>

          {/* 최근 활동 로그 및 관제 내역 (1, 2, ..., 10, 11 페이지네이션 적용) */}
          <section className="bg-canvas border border-hairline rounded-2xl p-6 space-y-6 shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-hairline pb-4 gap-2">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-ink" />
                <h3 className="text-heading-md font-bold text-ink">내 활동 및 접속 이력</h3>
                <span className="text-caption-sm font-bold text-charcoal font-mono bg-surface-soft px-2.5 py-0.5 rounded-full border border-hairline">
                  총 {activityTotal}건
                </span>
              </div>
              <button
                type="button"
                onClick={handleResetActivities}
                disabled={isActivitiesLoading}
                className="flex items-center gap-1.5 text-xs text-charcoal hover:text-ink hover:bg-surface-soft border border-hairline px-3 py-1.5 rounded-full transition-colors font-bold cursor-pointer disabled:opacity-40 shrink-0 self-start sm:self-auto"
                title="활동 이력 목록을 최신 상태로 다시 불러오기"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>새로고침</span>
              </button>
            </div>

            {/* 본문: 로딩 버퍼링 / 비어있음 / 5건씩 슬라이스된 목록 */}
            {isActivitiesLoading ? (
              <div className="flex flex-col items-center justify-center py-10 text-body space-y-2 bg-surface-soft/30 border border-hairline rounded-xl">
                <Loader2 className="w-6 h-6 animate-spin text-ink" />
                <span className="text-caption-sm font-bold text-body">활동 이력을 불러오는 중입니다.</span>
              </div>
            ) : activityError ? (
              <div className="flex flex-col items-center justify-center py-10 text-body space-y-2 bg-surface-soft/30 border border-hairline rounded-xl text-center">
                <AlertTriangle className="w-8 h-8 text-terminal-red" />
                <span className="text-caption-sm font-bold text-red-700">{activityError}</span>
              </div>
            ) : activities.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-body space-y-2 bg-surface-soft/30 border border-hairline rounded-xl text-center">
                <Activity className="w-8 h-8 text-mute" />
                <span className="text-caption-sm font-medium">기록된 활동 및 접속 이력이 없습니다.</span>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-3">
                  {activities.map((act) => (
                    <div key={act.id} className="flex items-start justify-between gap-3.5 p-3.5 rounded-xl border border-hairline hover:bg-surface-soft transition-colors group">
                      <div className="flex items-start gap-3.5 min-w-0 flex-1">
                        <div className="p-2 rounded-lg bg-surface-soft border border-hairline text-ink shrink-0 mt-0.5">
                          {act.type === 'login' && <Monitor className="w-4 h-4 text-blue-500" />}
                          {act.type === 'logout' && <LogOut className="w-4 h-4 text-mute" />}
                          {act.type === 'fire' && <AlertTriangle className="w-4 h-4 text-red-500" />}
                          {act.type === 'false_alarm' && <ShieldAlert className="w-4 h-4 text-amber-500" />}
                          {act.type === 'admin' && <ShieldCheck className="w-4 h-4 text-amber-500" />}
                          {act.type === 'system' && <FileText className="w-4 h-4 text-emerald-500" />}
                          {act.type === 'setting' && <Bell className="w-4 h-4 text-purple-500" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <p className={`text-body-sm font-bold truncate ${act.type === 'false_alarm' ? 'text-amber-700 dark:text-amber-400' : 'text-ink'}`}>
                              {act.title}
                            </p>
                            <span className="text-[11px] font-bold text-body shrink-0 font-mono">{act.time}</span>
                          </div>
                          <p className="text-caption-sm font-medium text-body mt-0.5 truncate">{act.detail}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* 1, 2, ..., 10, 11 표준 생략 기호 페이지네이션 컨트롤러 바 (상단 버튼 / 하단 페이지 정보 1줄 정렬) */}
                {activityTotalPages > 1 && (
                  <div className="pt-4 border-t border-hairline flex flex-col items-center gap-2">
                    {/* 상단: 한 줄로 시원하게 중앙 정렬된 페이지 번호 컨트롤러 */}
                    <div className="flex items-center justify-center gap-1 flex-wrap">
                      {/* 이전 버튼 */}
                      <button
                        type="button"
                        onClick={() => setActivityPage(prev => Math.max(1, prev - 1))}
                        disabled={activityPage === 1}
                        className="h-8 px-2.5 rounded-lg border border-hairline bg-canvas hover:border-ink hover:bg-surface-soft disabled:opacity-40 disabled:hover:border-hairline disabled:hover:bg-canvas transition-colors flex items-center gap-1 cursor-pointer font-bold text-caption-sm text-charcoal focus:outline-none focus-visible:outline-none"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                        <span>이전</span>
                      </button>

                      {/* 페이지 번호 및 '...' 생략 기호 */}
                      {getPaginationRange(activityPage, activityTotalPages).map((item, idx) => {
                        if (item === '...') {
                          return (
                            <span
                              key={`ellipsis-${idx}`}
                              className="px-1.5 text-mute font-bold text-caption-sm select-none"
                            >
                              ...
                            </span>
                          );
                        }

                        const pageNum = Number(item);
                        const isActive = activityPage === pageNum;

                        return (
                          <button
                            key={pageNum}
                            type="button"
                            onClick={() => setActivityPage(pageNum)}
                            className={`min-w-8 h-8 px-2 rounded-lg text-caption-sm font-bold transition-all cursor-pointer focus:outline-none focus-visible:outline-none ${
                              isActive
                                ? 'bg-primary text-on-primary shadow-xs'
                                : 'bg-canvas border border-hairline hover:border-ink hover:bg-surface-soft text-charcoal'
                            }`}
                          >
                            {pageNum}
                          </button>
                        );
                      })}

                      {/* 다음 버튼 */}
                      <button
                        type="button"
                        onClick={() => setActivityPage(prev => Math.min(activityTotalPages, prev + 1))}
                        disabled={activityPage === activityTotalPages}
                        className="h-8 px-2.5 rounded-lg border border-hairline bg-canvas hover:border-ink hover:bg-surface-soft disabled:opacity-40 disabled:hover:border-hairline disabled:hover:bg-canvas transition-colors flex items-center gap-1 cursor-pointer font-bold text-charcoal focus:outline-none focus-visible:outline-none"
                      >
                        <span>다음</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {/* 하단: 페이지 고르는 것 밑에 깔끔하게 한 줄로 표시되는 페이지 정보 */}
                    <span className="text-caption-sm font-semibold text-body font-mono text-center">
                      {activityPage} / {activityTotalPages} 페이지 (총 {activityTotal}건)
                    </span>
                  </div>
                )}
              </div>
            )}
          </section>

        </div>

      </main>

      {/* 팝업 모달 0: CCTV 상세 상태 및 변동 이력 다이얼로그 모달 */}
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
                <span className="text-caption-sm font-mono font-bold text-charcoal bg-surface-soft px-2 py-0.5 rounded border border-hairline">
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
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-ink flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                    <span>실시간 HLS 비디오 스트림</span>
                  </span>
                  <span className="text-caption-sm font-semibold text-charcoal font-mono">24 FPS · Live</span>
                </div>
                <CctvPlayer
                  key={selectedMyCctv.id}
                  streamUrl={selectedMyCctv.stream_url || selectedMyCctv.cctv_stream_url || 'https://media.w3.org/2010/05/sintel/trailer_hd.mp4'}
                  cctvName={selectedMyCctv.name}
                />
              </div>

              <div className="bg-surface-soft p-4 rounded-xl space-y-2 border border-hairline text-body-sm">
                <div className="flex justify-between">
                  <span className="font-medium text-body">현재 카메라 상태:</span>
                  {selectedMyCctv.status === 'fire' ? (
                    <span className="text-terminal-red font-bold">🔥 위험 (화재 감지)</span>
                  ) : selectedMyCctv.status === 'offline' ? (
                    <span className="text-body font-bold">오프라인</span>
                  ) : (
                    <span className="text-emerald-700 font-bold">🟢 정상 작동중</span>
                  )}
                </div>
                <div className="flex justify-between">
                  <span className="font-medium text-body">설치 위치:</span>
                  <span className="text-ink font-bold">{selectedMyCctv.location}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-medium text-body">GPS 위치 좌표:</span>
                  <span className="text-ink font-mono text-xs font-semibold">Lat {selectedMyCctv.lat}, Lng {selectedMyCctv.lng}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-medium text-body">최초 설치/등록일:</span>
                  <span className="text-ink font-bold">{selectedMyCctv.installedAt}</span>
                </div>
              </div>

              <div>
                <h4 className="text-body-sm-strong font-bold text-ink mb-3 flex items-center justify-between">
                  <span>📋 카메라 상태 변동 & 탐지 이력</span>
                  <span className="text-caption-sm font-normal text-body">총 {selectedMyCctv.history?.length || 0}건</span>
                </h4>
                <div className="space-y-2.5">
                  {selectedMyCctv.history && selectedMyCctv.history.length > 0 ? (
                    selectedMyCctv.history.map(item => (
                      <div key={item.id} className="p-3 rounded-xl border border-hairline bg-canvas text-xs space-y-1">
                        <div className="flex items-center justify-between text-body font-medium">
                          <span className="font-mono text-[11px]">{item.time}</span>
                          {item.type === 'fire' && <span className="text-terminal-red font-bold bg-terminal-red/10 px-2 py-0.5 rounded-full">화재 경보</span>}
                          {item.type === 'offline' && <span className="text-amber-600 font-bold bg-amber-500/10 px-2 py-0.5 rounded-full">연결 장애</span>}
                          {item.type === 'normal' && <span className="text-emerald-700 font-bold bg-emerald-500/10 px-2 py-0.5 rounded-full">정상점검</span>}
                          {item.type === 'system' && <span className="text-blue-600 font-bold bg-blue-500/10 px-2 py-0.5 rounded-full">시스템</span>}
                        </div>
                        <p className="text-ink font-semibold text-body-sm leading-relaxed">{item.message}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-body-sm text-body font-medium text-center py-6">기록된 카메라 감지 이력이 없습니다.</p>
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
                  navigate('/monitoring');
                }}
                className="flex items-center gap-1.5 text-xs text-primary font-bold hover:underline cursor-pointer"
              >
                <span>실시간 관제 화면으로 보기</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setSelectedMyCctv(null)}
                className="px-5 h-10 rounded-full bg-primary text-on-primary text-caption-sm font-bold hover:bg-ink-deep transition-colors focus:outline-none cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 팝업 모달 1: 프로필 수정 다이얼로그 (ui_modal_rules 준수) */}
      {isEditProfileOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <div
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden"
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          >
            <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
              <h3 className="text-heading-md font-bold text-ink flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-charcoal" />
                <span>프로필 정보 수정</span>
              </h3>
              <button
                onClick={() => setIsEditProfileOpen(false)}
                className="p-1 text-mute hover:text-ink rounded-full transition-colors focus:outline-none cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveProfile} className="flex flex-col shrink-0">
              <div className="p-6 max-h-[70vh] overflow-y-auto space-y-4">
                <div>
                  <label className="block text-caption-sm font-bold text-ink mb-1">
                    {isSocialAccount ? '닉네임' : '이름'}
                  </label>
                  <input
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline-strong rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    required
                  />
                </div>

                {!isSocialAccount && (
                  <div>
                    <label className="block text-caption-sm font-bold text-ink mb-1">이메일 주소</label>
                    <input
                      type="email"
                      value={editForm.email}
                      onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                      className="block box-border w-full h-11 px-4 bg-canvas border border-hairline-strong rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                      required
                    />
                  </div>
                )}

                <div>
                  <label className="block text-caption-sm font-bold text-ink mb-1">연락처 (전화번호)</label>
                  <input
                    type="text"
                    value={formatPhoneNumber(editForm.phone)}
                    onChange={(e) => setEditForm({ ...editForm, phone: formatPhoneNumber(e.target.value) })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline-strong rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="010-0000-0000"
                    inputMode="tel"
                  />
                </div>

                <div className="p-3.5 bg-surface-soft border border-hairline rounded-xl space-y-1">
                  <span className="block text-caption-sm font-bold text-charcoal">📹 내가 설치 / 등록한 CCTV 카메라 ({myCctvs.length}대 - 클릭시 실시간 재생)</span>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {myCctvs.map(c => (
                      <button
                        type="button"
                        key={c.id}
                        onClick={() => {
                          setIsEditProfileOpen(false);
                          setSelectedMyCctv(c);
                        }}
                        className="text-xs font-bold text-ink bg-canvas hover:bg-surface-soft hover:border-ink px-2.5 py-1 rounded-lg border border-hairline flex items-center gap-1 transition-colors cursor-pointer"
                        title={`${c.name} 실시간 비디오 모니터링`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                        <span>{c.name} ({c.id})</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-end gap-3 shrink-0">
                <button
                  type="button"
                  onClick={() => setIsEditProfileOpen(false)}
                  className="px-5 h-11 rounded-full text-caption-sm font-bold text-body hover:text-ink transition-colors focus:outline-none cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-2 px-6 h-11 bg-primary text-on-primary rounded-full text-caption-sm font-bold hover:bg-ink-deep transition-colors focus:outline-none cursor-pointer shadow-xs"
                >
                  <Save className="w-4 h-4" />
                  <span>저장하기</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 팝업 모달 2: 비밀번호 변경 다이얼로그 (ui_modal_rules 준수) */}
      {isChangePasswordOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <div
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col overflow-hidden"
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          >
            <div className="px-6 py-4 border-b border-hairline flex items-center justify-between shrink-0 bg-canvas">
              <h3 className="text-heading-md font-bold text-ink flex items-center gap-2">
                <Lock className="w-5 h-5 text-charcoal" />
                <span>비밀번호 변경</span>
              </h3>
              <button
                onClick={() => setIsChangePasswordOpen(false)}
                className="p-1 text-mute hover:text-ink rounded-full transition-colors focus:outline-none cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSavePassword} className="flex flex-col shrink-0">
              <div className="p-6 max-h-[70vh] overflow-y-auto space-y-4">
                <div>
                  <label className="block text-caption-sm font-bold text-ink mb-1">현재 비밀번호</label>
                  <PasswordInput
                    value={pwForm.currentPassword}
                    onChange={(e) => setPwForm({ ...pwForm, currentPassword: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline-strong rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="현재 사용 중인 비밀번호"
                    required
                  />
                </div>

                <div>
                  <label className="block text-caption-sm font-bold text-ink mb-1">새 비밀번호</label>
                  <PasswordInput
                    value={pwForm.newPassword}
                    onChange={(e) => setPwForm({ ...pwForm, newPassword: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline-strong rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="새 비밀번호 (최소 4자리)"
                    required
                  />
                </div>

                <div>
                  <label className="block text-caption-sm font-bold text-ink mb-1">새 비밀번호 확인</label>
                  <PasswordInput
                    value={pwForm.confirmPassword}
                    onChange={(e) => setPwForm({ ...pwForm, confirmPassword: e.target.value })}
                    className="block box-border w-full h-11 px-4 bg-canvas border border-hairline-strong rounded-full text-body-sm text-ink focus:outline-none focus-visible:outline-none focus:border-ink transition-colors"
                    placeholder="새 비밀번호 재입력"
                    required
                  />
                </div>
              </div>

              <div className="px-6 py-4 border-t border-hairline bg-surface-soft flex items-center justify-end gap-3 shrink-0">
                <button
                  type="button"
                  onClick={() => setIsChangePasswordOpen(false)}
                  className="px-5 h-11 rounded-full text-caption-sm font-bold text-body hover:text-ink transition-colors focus:outline-none cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-2 px-6 h-11 bg-primary text-on-primary rounded-full text-caption-sm font-bold hover:bg-ink-deep transition-colors focus:outline-none cursor-pointer shadow-xs"
                >
                  <Key className="w-4 h-4" />
                  <span>비밀번호 변경</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isPasswordChangeNoticeOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
          aria-labelledby="password-change-notice-title"
        >
          <div
            style={{ width: '420px', minWidth: '320px', maxWidth: '95vw' }}
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl p-6 text-center shrink-0 box-border"
          >
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10 text-amber-600">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <h3 id="password-change-notice-title" className="text-heading-md font-bold text-ink">
              비밀번호가 정상적으로 변경되었습니다.
            </h3>
            <p className="mt-3 text-body-sm leading-6 text-body">
              보안을 위해 다음 로그인 시 새 비밀번호를 사용해 주세요.
            </p>
            <button
              type="button"
              onClick={() => setIsPasswordChangeNoticeOpen(false)}
              className="mt-6 h-11 w-full rounded-full bg-primary text-caption-sm font-bold text-on-primary transition-colors hover:bg-ink-deep focus:outline-none focus-visible:outline-none cursor-pointer shadow-xs"
            >
              확인
            </button>
          </div>
        </div>
      )}

      {/* 푸터 */}
      <footer className="w-full bg-canvas text-body font-ui text-caption-sm border-t border-hairline py-6 px-6 text-center text-body mt-auto">
        <p>&copy; {new Date().getFullYear()} FireGuard Fire Prevention & Detection System</p>
      </footer>
    </div>
  );
}
