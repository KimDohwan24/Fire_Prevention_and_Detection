import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi, cctvApi, userApi, eventApi, reportApi, adminUpgradeApi, agencyApi, isSuperAdminUser } from '../api';
import {
  Users, PlusCircle,
  Video, CheckCircle, Trash2,
  Activity, UserCheck, Search, ShieldAlert, X, Clock,
  Film, AlertCircle, Info, FileText, CheckCircle2, Play,
  Mail, Phone, Building, Calendar, Shield, User, ExternalLink,
  BadgeCheck, ChevronRight, Edit3, MapPin, Loader2
} from 'lucide-react';
import CctvPlayer from '../components/CctvPlayer';
import AppHeader from '../components/AppHeader';

// 초기 CCTV 데이터
const INITIAL_CCTVS = [];

const AdminPage = () => {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState(null);
  const [activeTab, setActiveTab] = useState('cctv'); // 'cctv' | 'users' | 'logs'

  // 로딩/버퍼링 상태 관리
  const [isCctvLoading, setIsCctvLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAgencyLoading, setIsAgencyLoading] = useState(false);
  const [isAgencySubmitting, setIsAgencySubmitting] = useState(false);
  const [updatingUserNo, setUpdatingUserNo] = useState(null);

  // 데이터 상태 (실시간 백엔드 DB 연동)
  const [cctvList, setCctvList] = useState(INITIAL_CCTVS);
  const [userList, setUserList] = useState([]);
  const [systemLogs, setSystemLogs] = useState([]);
  const [agencyList, setAgencyList] = useState([]);

  // 폼 및 검색 상태
  const [newCctvName, setNewCctvName] = useState('');
  const [newCctvLoc, setNewCctvLoc] = useState('');
  const [newCctvStreamUrl, setNewCctvStreamUrl] = useState('');
  const [newCctvStatus, setNewCctvStatus] = useState('normal');
  const [newCctvLat, setNewCctvLat] = useState('37.5665');
  const [newCctvLng, setNewCctvLng] = useState('126.9780');
  const [userSearch, setUserSearch] = useState('');
  const [agencyForm, setAgencyForm] = useState({
    agency_no: null,
    agency_name: '',
    agency_lat: '37.5665',
    agency_lng: '126.9780',
    agency_endpoint: '',
    agency_is_active: true,
  });

  // 팝업 모달 상태
  const [selectedLog, setSelectedLog] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [assignedCctvs, setAssignedCctvs] = useState([]);
  const [isAssignedCctvsLoading, setIsAssignedCctvsLoading] = useState(false);
  const [assignedCctvsError, setAssignedCctvsError] = useState('');
  const [editingCctv, setEditingCctv] = useState(null);
  const [isAddingCctv, setIsAddingCctv] = useState(false);
  const [previewCctv, setPreviewCctv] = useState(null);
  const isCurrentUserSuperAdmin = isSuperAdminUser(currentUser);

  const canManageUserRole = (user) => {
    if (!user || isSuperAdminUser(user)) return false;
    if (user.role === 'admin') return isCurrentUserSuperAdmin;
    return user.isAdminRequestPending;
  };

  useEffect(() => {
    const stored = localStorage.getItem('currentUser');
    if (stored) {
      try {
        const user = JSON.parse(stored);
        if (user.role !== 'admin' && !isSuperAdminUser(user)) {
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

    // 1. 백엔드 CCTV 목록 로드 함수
    fetchCctvList();

    // 2. 백엔드 사용자 목록 로드
    userApi.list().then(res => {
      const items = res?.items || res || [];
      if (Array.isArray(items)) {
        const mappedUsers = items.map(u => {
          const userStatus = String(u.user_status || '').trim().toUpperCase();
          const isSuperAdmin = isSuperAdminUser(u);
          const role = isSuperAdmin || u.user_role === 'ADMIN' ? 'admin' : 'user';

          return {
            id: u.user_id,
            user_no: u.user_no,
            name: u.user_name || u.user_id,
            email: u.user_email || `${u.user_id}@fireguard.or.kr`,
            role,
            isSuperAdmin,
            userStatus,
            isAdminRequestPending: userStatus === 'PENDING',
            status: userStatus === 'ACTIVE'
              ? '승인'
              : userStatus === 'WITHDRAWN'
                ? '탈퇴'
                : userStatus === 'PENDING'
                  ? '관리자 요청 대기'
                  : '승인대기',
            dept: role === 'admin' ? '관제총괄팀' : '관제팀',
            phone: u.user_phone || '010-0000-0000',
            position: role === 'admin' ? '총괄 관제 책임자' : '관제 전담 요원',
            joinedAt: u.user_created_at ? u.user_created_at.substring(0, 10) : '2026-01-01',
            lastLogin: '접속 이력 확인가능',
            assignedZone: '지정 관제 구역',
            activities: []
          };
        });
        setUserList(mappedUsers);
      }
    }).catch(err => console.warn('사용자 목록 로드 오류:', err));

    // 3. 백엔드 이벤트 및 119 신고 감사 로그 로드
    eventApi.list({ size: 50 }).then(res => {
      const items = res?.items || [];
      if (Array.isArray(items)) {
        const mappedLogs = items.map(ev => ({
          id: ev.event_no,
          time: ev.event_first_detected_at || '2026-08-10 14:00:00',
          message: `${ev.cctv_name || '카메라'} ${ev.event_class === 'FLAME_SMOKE' ? '화재 및 연기 감지' : '화재 의심 감지'}`,
          level: ev.event_status === 'CONFIRMED' ? 'error' : ev.event_status === 'PENDING' ? 'warning' : 'info',
          cctvId: `CCTV-${String(ev.cctv_no || 1).padStart(2, '0')}`,
          location: ev.cctv_location || '관제 구역',
          confidence: Math.round((ev.event_confidence || 0.9) * 100),
          eventType: '화재/연기 감지',
          status: ev.event_status === 'CONFIRMED' ? '조치중 (119 신고)' : '관측중',
          videoUrl: null,
          thumbnail: ev.thumbnail_url || null,
          history: [
            { timestamp: ev.event_first_detected_at || '2026-08-10 14:00:00', event: 'AI 모듈 - 패턴 감지' }
          ]
        }));
        setSystemLogs(mappedLogs);
      }
    }).catch(err => console.warn('감사 로그 로드 오류:', err));
  }, [navigate]);

  const fetchCctvList = async () => {
    setIsCctvLoading(true);
    try {
      const res = await cctvApi.list();
      const items = res?.items || res || [];
      if (Array.isArray(items)) {
        const mapped = items.map(item => ({
          id: `CCTV-${String(item.cctv_no).padStart(2, '0')}`,
          cctv_no: item.cctv_no,
          owner_user_no: item.user_no,
          name: item.cctv_name,
          location: item.cctv_location,
          status: item.cctv_status === 'ACTIVE' ? 'normal' : item.cctv_status === 'INACTIVE' ? 'offline' : 'fire',
          lat: parseFloat(item.cctv_lat) || 37.5665,
          lng: parseFloat(item.cctv_lng) || 126.9780,
          stream_url: item.cctv_stream_url
        }));
        setCctvList(mapped);
      }
    } catch (err) {
      console.warn('CCTV 백엔드 로드 오류:', err);
    } finally {
      setIsCctvLoading(false);
    }
  };

  const openUserDetail = async (user) => {
    setSelectedUser(user);
    setAssignedCctvs([]);
    setAssignedCctvsError('');
    setIsAssignedCctvsLoading(true);

    try {
      const response = await cctvApi.list({ user_no: user.user_no });
      const items = response?.items || response || [];
      setAssignedCctvs(Array.isArray(items) ? items : []);
    } catch (error) {
      setAssignedCctvsError(error.message || '담당 CCTV 목록을 불러오지 못했습니다.');
    } finally {
      setIsAssignedCctvsLoading(false);
    }
  };

  const handleLogout = async () => {
    await authApi.logout();
    navigate('/login');
  };

  const resetAgencyForm = () => {
    setAgencyForm({
      agency_no: null,
      agency_name: '',
      agency_lat: '37.5665',
      agency_lng: '126.9780',
      agency_endpoint: '',
      agency_is_active: true,
    });
  };

  const fetchAgencyList = async () => {
    setIsAgencyLoading(true);
    try {
      const res = await agencyApi.list();
      const items = res?.items || res || [];
      setAgencyList(Array.isArray(items) ? items : []);
    } catch (err) {
      console.warn('소방서 목록 로드 오류:', err);
      alert(`소방서 목록을 불러오지 못했습니다: ${err.message || '오류가 발생했습니다.'}`);
    } finally {
      setIsAgencyLoading(false);
    }
  };

  const handleSaveAgency = async (e) => {
    e.preventDefault();
    if (!agencyForm.agency_name.trim() || isAgencySubmitting) return;

    const payload = {
      agency_name: agencyForm.agency_name.trim(),
      agency_lat: Number.parseFloat(agencyForm.agency_lat),
      agency_lng: Number.parseFloat(agencyForm.agency_lng),
      agency_endpoint: agencyForm.agency_endpoint.trim(),
      agency_is_active: agencyForm.agency_is_active,
    };

    if (!Number.isFinite(payload.agency_lat) || !Number.isFinite(payload.agency_lng)) {
      alert('위도와 경도는 숫자로 입력해주세요.');
      return;
    }

    setIsAgencySubmitting(true);
    try {
      if (agencyForm.agency_no) {
        await agencyApi.update(agencyForm.agency_no, payload);
        alert(`[${payload.agency_name}] 소방서 정보를 수정했습니다.`);
      } else {
        await agencyApi.create(payload);
        alert(`[${payload.agency_name}] 소방서를 등록했습니다.`);
      }
      resetAgencyForm();
      await fetchAgencyList();
    } catch (err) {
      console.error('소방서 저장 실패:', err);
      alert(`소방서 정보를 저장하지 못했습니다: ${err.message || '오류가 발생했습니다.'}`);
    } finally {
      setIsAgencySubmitting(false);
    }
  };

  const handleEditAgency = (agency) => {
    setAgencyForm({
      agency_no: agency.agency_no,
      agency_name: agency.agency_name || '',
      agency_lat: String(agency.agency_lat ?? ''),
      agency_lng: String(agency.agency_lng ?? ''),
      agency_endpoint: agency.agency_endpoint || '',
      agency_is_active: agency.agency_is_active !== false,
    });
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
  const handleAddCCTV = async (e) => {
    e.preventDefault();
    if (!newCctvName.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const statusMapToApi = {
        normal: 'ACTIVE',
        offline: 'INACTIVE',
        fire: 'FIRE',
      };

      const payload = {
        cctv_name: newCctvName.trim(),
        cctv_stream_url: newCctvStreamUrl.trim(),
        cctv_location: newCctvLoc || '위치 미지정',
        cctv_status: statusMapToApi[newCctvStatus] || 'ACTIVE',
        cctv_lat: parseFloat(newCctvLat) || 37.5665,
        cctv_lng: parseFloat(newCctvLng) || 126.9780,
      };

      await cctvApi.create(payload);
      await fetchCctvList();

      setNewCctvName('');
      setNewCctvLoc('');
      setNewCctvStreamUrl('');
      setNewCctvStatus('normal');
      setNewCctvLat('37.5665');
      setNewCctvLng('126.9780');
      setIsAddingCctv(false);
      alert(`[${payload.cctv_name}] 카메라가 성공적으로 등록되었습니다.`);
    } catch (err) {
      console.error('CCTV 등록 실패:', err);
      alert(`CCTV 등록 실패: ${err.message || '오류가 발생했습니다.'}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // CCTV 정보 수정
  const handleUpdateCCTV = async (e) => {
    e.preventDefault();
    if (!editingCctv || !editingCctv.name.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const statusMapToApi = {
        normal: 'ACTIVE',
        offline: 'INACTIVE',
        fire: 'FIRE',
      };

      const payload = {
        cctv_name: editingCctv.name,
        cctv_location: editingCctv.location || '위치 미지정',
        cctv_status: statusMapToApi[editingCctv.status] || 'ACTIVE',
        cctv_lat: parseFloat(editingCctv.lat) || 37.5665,
        cctv_lng: parseFloat(editingCctv.lng) || 126.9780,
      };

      if (editingCctv.cctv_no) {
        await cctvApi.update(editingCctv.cctv_no, payload);
      }

      await fetchCctvList();
      alert(`[${editingCctv.name}] CCTV 정보가 성공적으로 수정되었습니다.`);
      setEditingCctv(null);
    } catch (err) {
      console.error('CCTV 수정 실패:', err);
      alert(`CCTV 정보 수정 실패: ${err.message || '오류가 발생했습니다.'}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // CCTV 삭제
  const handleDeleteCCTV = async (cctv) => {
    if (isSubmitting) return;
    if (confirm(`[${cctv.name}] CCTV를 모니터링 목록에서 삭제하시겠습니까?`)) {
      setIsSubmitting(true);
      try {
        if (cctv.cctv_no) {
          await cctvApi.delete(cctv.cctv_no);
        }
        await fetchCctvList();
        alert(`[${cctv.name}] CCTV가 성공적으로 삭제되었습니다.`);
      } catch (err) {
        console.error('CCTV 삭제 실패:', err);
        alert(`CCTV 삭제 실패: ${err.message || '오류가 발생했습니다.'}`);
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  // 회원 권한 토글
  const toggleRole = async (user) => {
    if (user?.user_no == null || updatingUserNo !== null) return;
    if (!canManageUserRole(user)) {
      if (isSuperAdminUser(user)) {
        alert('최고 관리자의 권한은 변경할 수 없습니다.');
      } else if (user.role === 'admin' && !isCurrentUserSuperAdmin) {
        alert('다른 관리자의 권한은 최고 관리자만 변경할 수 있습니다.');
      }
      return;
    }

    const nextRole = user.role === 'admin' ? 'VIEWER' : 'ADMIN';
    const nextRoleLabel = nextRole === 'ADMIN' ? '관리자' : '일반 관제원';
    const nextUserStatus = user.userStatus === 'PENDING' ? 'ACTIVE' : user.userStatus || 'ACTIVE';
    const nextUserStatusLabel = nextUserStatus === 'ACTIVE'
      ? '승인'
      : nextUserStatus === 'WITHDRAWN'
        ? '탈퇴'
        : nextUserStatus === 'PENDING'
          ? '관리자 요청 대기'
          : '승인대기';
    setUpdatingUserNo(user.user_no);

    try {
      await userApi.updateRole(user.user_no, nextRole, nextUserStatus);

      const updatedUser = {
        ...user,
        role: nextRole === 'ADMIN' ? 'admin' : 'user',
        userStatus: nextUserStatus,
        isAdminRequestPending: false,
        status: nextUserStatusLabel,
        adminRequested: false,
        adminRequestStatus: nextRole === 'ADMIN' ? 'APPROVED' : undefined,
        dept: nextRole === 'ADMIN' ? '관제총괄팀' : '관제팀',
        position: nextRole === 'ADMIN' ? '총괄 관제 책임자' : '관제 전담 요원',
      };

      setUserList(prev => prev.map(item => (
        item.user_no === user.user_no ? updatedUser : item
      )));
      setSelectedUser(prev => (
        prev?.user_no === user.user_no ? updatedUser : prev
      ));

      if (currentUser?.user_no === user.user_no) {
        const updatedSessionUser = {
          ...currentUser,
          role: updatedUser.role,
          rawRole: nextRole,
        };
        setCurrentUser(updatedSessionUser);
        localStorage.setItem('currentUser', JSON.stringify(updatedSessionUser));
      }

      alert(`[${user.name}] 권한이 ${nextRoleLabel}(으)로 변경되었습니다.`);
    } catch (err) {
      console.error('회원 권한 변경 실패:', err);
      alert(`회원 권한 변경에 실패했습니다. ${err.message || '오류가 발생했습니다.'}`);
    } finally {
      setUpdatingUserNo(null);
    }
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

  const getCctvRegistrant = (cctv) => {
    const owner = userList.find((user) => String(user.user_no) === String(cctv.owner_user_no));
    if (owner) return `${owner.name} (${owner.id})`;
    return cctv.owner_user_no != null ? `사용자 #${cctv.owner_user_no}` : '등록자 정보 없음';
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-ui transition-colors duration-300">
      <AppHeader
        currentPage="admin"
        currentUser={currentUser}
        onLogout={handleLogout}
      />

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
              onClick={() => {
                setActiveTab('agencies');
                fetchAgencyList();
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${activeTab === 'agencies'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
                }`}
            >
              <MapPin className="w-4 h-4" />
              <span>소방서 위치</span>
            </button>

            <button
              onClick={() => setActiveTab('logs')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${activeTab === 'logs'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-body hover:text-ink hover:bg-surface-soft'
                }`}
            >
              <Activity className="w-4 h-4" />
              <span>감사 로그 ({systemLogs.length})</span>
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
                  등록된 CCTV 정보는 GIS 지도 및 실시간 관제 화면에 반영됩니다.
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
                <table className="w-full min-w-[1120px] table-fixed text-left text-xs">
                  <thead className="bg-surface-soft border-b border-hairline text-mute uppercase font-semibold">
                    <tr>
                      <th className="w-[110px] p-4">카메라 ID</th>
                      <th className="w-[170px] p-4">CCTV 명칭</th>
                      <th className="w-[170px] p-4">등록자</th>
                      <th className="w-[250px] p-4">설치 위치 및 좌표</th>
                      <th className="w-[120px] p-4 whitespace-nowrap">현재 상태</th>
                      <th className="w-[300px] p-4 text-center whitespace-nowrap">작동 관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {isCctvLoading ? (
                      <tr>
                        <td colSpan="6" className="p-8 text-center text-mute">
                          <div className="flex items-center justify-center gap-2 font-medium">
                            <Loader2 className="w-5 h-5 animate-spin text-amber-500" />
                            <span>CCTV 데이터 수신 대기 중... (버퍼링)</span>
                          </div>
                        </td>
                      </tr>
                    ) : cctvList.length === 0 ? (
                      <tr>
                        <td colSpan="6" className="p-8 text-center text-mute font-medium">
                          등록된 CCTV 자산이 없습니다. 상단의 신규 자산 등록 버튼을 클릭해주세요.
                        </td>
                      </tr>
                    ) : (
                      cctvList.map(cctv => (
                      <tr key={cctv.id} className="hover:bg-surface-soft/50 transition-colors">
                        <td className="p-4 font-mono font-bold text-ink">{cctv.id}</td>
                        <td className="p-4 font-semibold text-ink">{cctv.name}</td>
                        <td className="p-4">
                          <span className="font-semibold text-ink block">{getCctvRegistrant(cctv)}</span>
                          {cctv.owner_user_no != null && (
                            <span className="text-[10px] text-mute font-mono block mt-0.5">USER #{cctv.owner_user_no}</span>
                          )}
                        </td>
                        <td className="p-4">
                          <span className="font-semibold text-ink block">{cctv.location}</span>
                          <span className="text-[10px] text-mute font-mono block mt-0.5">
                            좌표: ({cctv.lat}, {cctv.lng})
                          </span>
                        </td>
                        <td className="p-4 whitespace-nowrap align-middle">
                          {cctv.status === 'fire' ? (
                            <span className="inline-flex whitespace-nowrap px-2.5 py-1 bg-terminal-red/10 text-terminal-red font-bold rounded-full border border-terminal-red/20">
                              🔥 화재 감지
                            </span>
                          ) : cctv.status === 'offline' ? (
                            <span className="inline-flex whitespace-nowrap px-2.5 py-1 bg-surface-soft text-mute font-medium rounded-full border border-hairline">
                              🔌 연결 끊김
                            </span>
                          ) : (
                            <span className="inline-flex whitespace-nowrap px-2.5 py-1 bg-terminal-green/10 text-terminal-green font-medium rounded-full border border-terminal-green/20">
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
                            onClick={() => handleDeleteCCTV(cctv)}
                            className="px-2.5 py-1 text-xs font-semibold text-terminal-red bg-terminal-red/10 hover:bg-terminal-red/20 border border-terminal-red/20 rounded-lg transition-colors cursor-pointer inline-flex items-center gap-1"
                            title="CCTV 삭제"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>삭제</span>
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: 회원 권한 관리 */}
        {activeTab === 'agencies' && (
          <div className="space-y-6 animate-in fade-in duration-200">
            <div className="bg-canvas border border-hairline rounded-2xl p-6 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                  <h2 className="text-heading-sm font-bold text-ink flex items-center gap-2">
                    <MapPin className="w-5 h-5 text-amber-500" />
                    소방서 위치 관리
                  </h2>
                  <p className="text-xs text-mute mt-1">관할 소방서의 이름과 위치 좌표를 직접 등록하거나 수정할 수 있습니다.</p>
                </div>
                <button
                  type="button"
                  onClick={fetchAgencyList}
                  disabled={isAgencyLoading}
                  className="h-10 px-4 rounded-full border border-hairline bg-surface-soft hover:border-amber-500 text-xs font-bold text-body hover:text-amber-700 disabled:opacity-60 inline-flex items-center gap-2 cursor-pointer"
                >
                  <Loader2 className={`w-4 h-4 ${isAgencyLoading ? 'animate-spin' : ''}`} />
                  목록 새로고침
                </button>
              </div>

              <div className="overflow-x-auto border border-hairline rounded-xl">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-soft border-b border-hairline text-mute uppercase font-semibold">
                    <tr>
                      <th className="p-3.5">소방서명</th>
                      <th className="p-3.5">위도 / 경도</th>
                      <th className="p-3.5">상태</th>
                      <th className="p-3.5 text-right">관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {isAgencyLoading ? (
                      <tr><td colSpan="4" className="p-8 text-center text-mute">소방서 목록을 불러오는 중입니다.</td></tr>
                    ) : agencyList.length === 0 ? (
                      <tr><td colSpan="4" className="p-8 text-center text-mute">등록된 소방서가 없습니다.</td></tr>
                    ) : agencyList.map((agency) => (
                      <tr key={agency.agency_no} className="hover:bg-surface-soft/60 transition-colors">
                        <td className="p-3.5 font-bold text-ink">{agency.agency_name}</td>
                        <td className="p-3.5 text-mute font-mono">{agency.agency_lat}, {agency.agency_lng}</td>
                        <td className="p-3.5">
                          <span className={`px-2 py-1 rounded-full font-bold ${agency.agency_is_active !== false ? 'bg-emerald-500/10 text-emerald-600' : 'bg-surface-soft text-mute'}`}>
                            {agency.agency_is_active !== false ? '운영 중' : '비활성'}
                          </span>
                        </td>
                        <td className="p-3.5 text-right">
                          <button type="button" onClick={() => handleEditAgency(agency)} className="px-3 py-1.5 rounded-lg border border-hairline hover:border-amber-500 text-xs font-bold text-body hover:text-amber-700 inline-flex items-center gap-1 cursor-pointer">
                            <Edit3 className="w-3.5 h-3.5" /> 수정
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <form onSubmit={handleSaveAgency} className="bg-canvas border border-hairline rounded-2xl p-6 shadow-sm">
              <div className="flex items-center justify-between gap-3 mb-5">
                <div>
                  <h3 className="text-body-md font-bold text-ink">{agencyForm.agency_no ? '소방서 정보 수정' : '소방서 직접 등록'}</h3>
                  <p className="mt-1 text-xs text-mute">저장된 정보는 실시간 관제 화면의 소방서 목록과 지도 마커에 반영됩니다.</p>
                </div>
                {agencyForm.agency_no && <button type="button" onClick={resetAgencyForm} className="text-xs font-bold text-mute hover:text-ink cursor-pointer">새로 등록</button>}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="text-xs font-bold text-body">소방서명
                  <input required value={agencyForm.agency_name} onChange={(e) => setAgencyForm({ ...agencyForm, agency_name: e.target.value })} className="mt-1.5 block box-border w-full h-10 rounded-lg border border-hairline bg-canvas px-3 text-sm text-ink focus:outline-none focus-visible:outline-none" placeholder="예: 종로소방서" />
                </label>
                <label className="text-xs font-bold text-body">119 연동 주소
                  <input required value={agencyForm.agency_endpoint} onChange={(e) => setAgencyForm({ ...agencyForm, agency_endpoint: e.target.value })} className="mt-1.5 block box-border w-full h-10 rounded-lg border border-hairline bg-canvas px-3 text-sm text-ink focus:outline-none focus-visible:outline-none" placeholder="http://..." />
                </label>
                <label className="text-xs font-bold text-body">위도
                  <input required type="number" step="any" value={agencyForm.agency_lat} onChange={(e) => setAgencyForm({ ...agencyForm, agency_lat: e.target.value })} className="mt-1.5 block box-border w-full h-10 rounded-lg border border-hairline bg-canvas px-3 text-sm text-ink focus:outline-none focus-visible:outline-none" />
                </label>
                <label className="text-xs font-bold text-body">경도
                  <input required type="number" step="any" value={agencyForm.agency_lng} onChange={(e) => setAgencyForm({ ...agencyForm, agency_lng: e.target.value })} className="mt-1.5 block box-border w-full h-10 rounded-lg border border-hairline bg-canvas px-3 text-sm text-ink focus:outline-none focus-visible:outline-none" />
                </label>
              </div>
              <label className="mt-4 inline-flex items-center gap-2 text-xs text-body cursor-pointer">
                <input type="checkbox" checked={agencyForm.agency_is_active} onChange={(e) => setAgencyForm({ ...agencyForm, agency_is_active: e.target.checked })} /> 운영 상태로 등록
              </label>
              <div className="mt-5 flex justify-end">
                <button disabled={isAgencySubmitting} className="h-10 px-4 rounded-full bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold disabled:opacity-60 inline-flex items-center gap-2 cursor-pointer">
                  {isAgencySubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                  {agencyForm.agency_no ? '소방서 정보 저장' : '소방서 등록'}
                </button>
              </div>
            </form>
          </div>
        )}

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
                      <th className="p-3.5">사용자 상태</th>
                      <th className="p-3.5 text-right">상세조회 및 관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {filteredUsers.map(user => (
                      <tr key={user.id} className="hover:bg-surface-soft/60 transition-colors">
                        <td
                          onClick={() => openUserDetail(user)}
                          className="p-3.5 font-bold text-ink cursor-pointer hover:text-amber-500 transition-colors"
                        >
                          {user.name} <span className="font-normal text-mute">({user.id})</span>
                        </td>
                        <td className="p-3.5">
                          <button
                            onClick={() => openUserDetail(user)}
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
                          {user.isSuperAdmin ? (
                            <span className="px-2.5 py-0.5 bg-ink text-canvas font-bold rounded-full border border-ink">
                              👑 최고 관리자
                            </span>
                          ) : user.role === 'admin' ? (
                            <span className="px-2.5 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold rounded-full border border-amber-500/30">
                              👑 관리자
                            </span>
                          ) : user.isAdminRequestPending ? (
                            <span className="px-2.5 py-0.5 bg-amber-500/20 text-amber-600 dark:text-amber-400 font-bold rounded-full border border-amber-500/40">
                              ⏳ 관리자 승격 요청됨
                            </span>
                          ) : (
                            <span className="px-2.5 py-0.5 bg-surface-soft text-mute rounded-full border border-hairline">
                              👤 일반 사용자
                            </span>
                          )}
                        </td>
                        <td className="p-3.5">
                          {user.isAdminRequestPending ? (
                            <span className="text-amber-500 font-bold flex items-center gap-1">
                              <Clock className="w-3.5 h-3.5" /> 관리자 요청 대기
                            </span>
                          ) : user.status === '승인' ? (
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
                            onClick={() => openUserDetail(user)}
                            className="px-2.5 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30 hover:bg-amber-500/20 rounded-lg font-bold transition-colors cursor-pointer inline-flex items-center gap-1"
                          >
                            <span>상세보기</span>
                            <ChevronRight className="w-3.5 h-3.5" />
                          </button>
                          {user.isSuperAdmin ? null : canManageUserRole(user) ? (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleRole(user);
                              }}
                              disabled={updatingUserNo !== null}
                              className={`px-3 py-1 font-bold rounded-lg transition-colors cursor-pointer shadow-xs ${
                                user.isAdminRequestPending
                                  ? 'bg-amber-500 text-white hover:bg-amber-600 border border-amber-600'
                                  : 'bg-canvas border border-hairline hover:border-ink'
                              }`}
                            >
                              {updatingUserNo === user.user_no ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : user.role === 'admin'
                                ? '일반 변경'
                                : '👑 관리자 승인 (승격)'}
                            </button>
                          ) : (
                            <span className="text-[11px] text-mute">
                              {user.role === 'admin' ? '최고 관리자 전용' : '관리자 요청 없음'}
                            </span>
                          )}
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
              {systemLogs.map(log => (
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
          <div
            style={{ width: '720px', minWidth: '320px', maxWidth: '95vw' }}
            className="bg-canvas border border-hairline rounded-2xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col shrink-0"
          >
            {/* 모달 헤더 */}
            <div className="p-6 border-b border-hairline flex items-center justify-between bg-surface-soft/60 shrink-0">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-amber-500/20 text-amber-500 flex items-center justify-center font-bold text-lg border border-amber-500/40">
                  {selectedUser.name ? selectedUser.name.charAt(0) : 'U'}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-heading-sm font-bold text-ink">{selectedUser.name}</h2>
                    <span className="text-xs text-mute font-mono">({selectedUser.id})</span>
                    {selectedUser.isSuperAdmin ? (
                      <span className="px-2 py-0.5 bg-ink text-canvas font-bold rounded-full text-[11px] border border-ink">
                        👑 최고 관리자
                      </span>
                    ) : selectedUser.role === 'admin' ? (
                      <span className="px-2 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold rounded-full text-[11px] border border-amber-500/30">
                        👑 관리자
                      </span>
                    ) : selectedUser.isAdminRequestPending ? (
                      <span className="px-2 py-0.5 bg-amber-500/20 text-amber-600 dark:text-amber-400 font-bold rounded-full text-[11px] border border-amber-500/40">
                        ⏳ 관리자 요청 대기
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
            <div className="p-6 max-h-[70vh] overflow-y-auto space-y-6">
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
                        <BadgeCheck className="w-3.5 h-3.5" /> 사용자 상태
                      </span>
                      {selectedUser.isAdminRequestPending ? (
                        <span className="text-amber-500 font-bold flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" /> 관리자 요청 대기
                        </span>
                      ) : selectedUser.status === '승인' ? (
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

              {/* 해당 인원이 설치/등록한 CCTV 카메라 목록 (클릭 시 실시간 비디오 모니터링) */}
              <div className="p-4 bg-surface-soft/40 border border-hairline rounded-xl space-y-2">
                <span className="text-xs font-bold text-mute uppercase tracking-wider flex items-center gap-1.5">
                  <Video className="w-3.5 h-3.5 text-amber-500" />
                  해당 인원이 직접 설치 / 등록한 CCTV 카메라 (클릭 시 실시간 재생)
                </span>
                <div className="flex flex-wrap gap-2 pt-0.5">
                  {isAssignedCctvsLoading ? (
                    <span className="inline-flex items-center gap-2 py-1 text-xs text-mute">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" /> 담당 CCTV를 조회 중입니다.
                    </span>
                  ) : assignedCctvsError ? (
                    <span className="text-xs text-red-600">{assignedCctvsError}</span>
                  ) : assignedCctvs.length === 0 ? (
                    <span className="text-xs text-mute">등록하거나 담당 중인 CCTV가 없습니다.</span>
                  ) : assignedCctvs.map((cctv) => (
                    <button
                      key={cctv.cctv_no}
                      onClick={() => {
                        setSelectedUser(null);
                        setPreviewCctv({
                          ...cctv,
                          id: `CCTV-${String(cctv.cctv_no).padStart(2, '0')}`,
                          name: cctv.cctv_name,
                          location: cctv.cctv_location,
                          stream_url: cctv.cctv_stream_url,
                          lat: cctv.cctv_lat,
                          lng: cctv.cctv_lng,
                          status: cctv.cctv_status === 'ACTIVE' ? 'normal' : 'offline',
                        });
                      }}
                      className="text-xs font-semibold text-ink bg-canvas hover:bg-surface-soft hover:border-amber-500 px-2.5 py-1 rounded-lg border border-hairline transition-colors cursor-pointer inline-flex items-center gap-1"
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${cctv.cctv_status === 'ACTIVE' ? 'bg-emerald-500' : 'bg-mute'}`} />
                      <span>{cctv.cctv_name} (CCTV-{String(cctv.cctv_no).padStart(2, '0')})</span>
                    </button>
                  ))}
                </div>
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
            <div className="p-4 border-t border-hairline bg-surface-soft/40 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                {selectedUser.status !== '승인' && !selectedUser.isAdminRequestPending && (
                  <button
                    onClick={() => approveUser(selectedUser.id)}
                    className="bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs py-2 px-4 rounded-lg transition-colors cursor-pointer flex items-center gap-1"
                  >
                    <UserCheck className="w-3.5 h-3.5" />
                    가입 승인하기
                  </button>
                )}
                {selectedUser.isSuperAdmin ? (
                  <span className="text-xs text-ink font-bold">최고 관리자 권한 고정</span>
                ) : canManageUserRole(selectedUser) ? (
                  <button
                    onClick={() => toggleRole(selectedUser)}
                    disabled={updatingUserNo !== null}
                    className="bg-canvas border border-hairline hover:border-ink text-ink font-semibold text-xs py-2 px-4 rounded-lg transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
                  >
                    {updatingUserNo === selectedUser.user_no && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    {selectedUser.role === 'admin' ? '일반 관제원으로 권한 변경' : '관리자 권한으로 승격'}
                  </button>
                ) : (
                  <span className="text-xs text-mute">
                    {selectedUser.role === 'admin' ? '최고 관리자만 권한을 변경할 수 있습니다.' : '관리자 권한 요청 없음'}
                  </span>
                )}
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
                  disabled={isSubmitting}
                  className="px-5 h-10 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold text-xs rounded-xl shadow-sm transition-colors cursor-pointer inline-flex items-center gap-1.5"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>수정사항 저장 중...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      <span>수정사항 저장하기</span>
                    </>
                  )}
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

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-ink">스트림 URL *</label>
                <input
                  type="url"
                  value={newCctvStreamUrl}
                  onChange={(e) => setNewCctvStreamUrl(e.target.value)}
                  className="w-full block h-11 px-3.5 bg-canvas border border-hairline rounded-xl text-body-sm text-ink outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-ui"
                  placeholder="rtsp://... or https://...m3u8"
                  required
                />
                <p className="text-[11px] text-mute">실시간 영상 재생에 사용하는 스트림 주소를 입력하세요.</p>
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
                  disabled={isSubmitting}
                  className="px-5 h-10 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold text-xs rounded-xl shadow-sm transition-colors cursor-pointer inline-flex items-center gap-1.5"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>신규 CCTV 등록 중...</span>
                    </>
                  ) : (
                    <>
                      <PlusCircle className="w-4 h-4" />
                      <span>신규 CCTV 등록 완료</span>
                    </>
                  )}
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


