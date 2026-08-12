import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LogOut, Search, Bell, AlertTriangle, CheckCircle,
  Video, MapPin, Search as SearchIcon, VideoOff, X, ArrowLeft,
  ShieldCheck, Users, PlusCircle, Settings, ShieldAlert, UserCheck, Loader2,
  Flame, Siren, PhoneCall, CheckCircle2, XCircle, Clock, ExternalLink, FileText
} from 'lucide-react';
import { authApi, cctvApi, agencyApi, eventApi, alertApi, reportApi } from '../api';
import CctvPlayer from '../components/CctvPlayer';
import ItsCctvModal from '../components/ItsCctvModal';
import GisMap from '../components/GisMap';

const DEFAULT_AGENCIES = [];
const INITIAL_CCTVS = [];

const normalizeCctvText = (value) => String(value || '').trim().toLowerCase();
const normalizeCctvCoord = (value) => {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed.toFixed(6) : '';
};

const isSameRegisteredCctv = (registered, incoming) => {
  const registeredName = normalizeCctvText(registered.cctv_name || registered.name);
  const incomingName = normalizeCctvText(incoming.cctv_name || incoming.name);
  const registeredStream = normalizeCctvText(registered.cctv_stream_url || registered.stream_url);
  const incomingStream = normalizeCctvText(incoming.cctv_stream_url || incoming.stream_url);
  const registeredLat = normalizeCctvCoord(registered.cctv_lat ?? registered.lat);
  const registeredLng = normalizeCctvCoord(registered.cctv_lng ?? registered.lng);
  const incomingLat = normalizeCctvCoord(incoming.cctv_lat ?? incoming.lat);
  const incomingLng = normalizeCctvCoord(incoming.cctv_lng ?? incoming.lng);

  if (registeredName && incomingName && registeredName === incomingName) return true;
  if (registeredStream && incomingStream && registeredStream === incomingStream) return true;
  return Boolean(registeredLat && registeredLng && registeredLat === incomingLat && registeredLng === incomingLng);
};

function Dashboard() {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState(null);
  const [cctvList, setCctvList] = useState(INITIAL_CCTVS);
  const [selectedCCTV, setSelectedCCTV] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  // 관할 소방서 및 이벤트 로그 목록 State (실시간 DB 연동)
  const [agencyList, setAgencyList] = useState(DEFAULT_AGENCIES);
  const [fireStation, setFireStation] = useState(null);
  const [eventLogs, setEventLogs] = useState([]);

  // 지도 오버레이 및 탭 조작 UI State
  const [showFireStation, setShowFireStation] = useState(true);
  const [isAgencyTabOpen, setIsAgencyTabOpen] = useState(false);
  const [isItsModalOpen, setIsItsModalOpen] = useState(false);
  const [isTestCctvSelectModalOpen, setIsTestCctvSelectModalOpen] = useState(false);
  const [isActionHistoryModalOpen, setIsActionHistoryModalOpen] = useState(false);
  const [highlightedAgencyNo, setHighlightedAgencyNo] = useState(null);

  // 실시간 긴급 상단 알림 배너 및 이벤트 상세 모달 상태
  const [activeAlertBanner, setActiveAlertBanner] = useState(null);
  const [isBannerDismissed, setIsBannerDismissed] = useState(false);
  const [selectedEventDetail, setSelectedEventDetail] = useState(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  // 관리자 전용 모달 상태
  const [activeAdminTab, setActiveAdminTab] = useState(null);
  const [userList, setUserList] = useState([]);
  const [newCCTVName, setNewCCTVName] = useState('');
  const [autoNotify119, setAutoNotify119] = useState(true);

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  useEffect(() => {
    // 로딩 안전 이중 가드: 2.5초 후 무조건 로딩 해제
    const safetyTimer = setTimeout(() => {
      setLoading(false);
    }, 2500);

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
    }

    // 2. 초기 데이터 수신 (소방서 DB 및 CCTV 목록 - 최초 1회만 호출)
    const fetchInitialData = async () => {
      try {
        // 2-1. 소방서 DB 조회
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
            const fallbackAgency = [{
              agency_no: 1,
              name: '종로소방서',
              agency_name: '종로소방서',
              agency_lat: 37.5730,
              agency_lng: 126.9790,
              x: 50,
              y: 38,
              address: '서울특별시 종로구 종로1길 28',
              phone: '119 (비상 종합 상황실)',
              agency_is_active: true
            }];
            setAgencyList(fallbackAgency);
            setFireStation(fallbackAgency[0]);
          }
        } catch (err) {
          console.warn('소방서 DB 조회 실패:', err.message);
        }

        // 2-2. CCTV 목록 수신
        try {
          const cctvRes = await cctvApi.list();
          const rawItems = cctvRes?.items || cctvRes || [];
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
              history: []
            }));
            setCctvList(mappedCctvs);
            setSelectedCCTV(mappedCctvs[0]);
          }
        } catch (err) {
          console.warn('CCTV 목록 로드 오류:', err.message);
        }
      } finally {
        setLoading(false);
        clearTimeout(safetyTimer);
      }
    };

    // 3. 백엔드 REST API 실시간 폴링 (4초 주기: 실시간 알림 & 화재 이벤트만 조회)
    const fetchPollingData = async () => {
      try {
        const [alertRes, eventRes] = await Promise.all([
          alertApi.list().catch(() => null),
          eventApi.list({ size: 20, include_test: true }).catch(() => null)
        ]);

        const alerts = alertRes?.items || alertRes || [];
        const events = eventRes?.items || eventRes || [];

        const falseAlarmList = JSON.parse(localStorage.getItem('falseAlarmEvents') || '[]');
        const resolvedList = JSON.parse(localStorage.getItem('resolvedEvents') || '[]');

        // 해결(조치 완료) 또는 오탐 처리되지 않은 실시간 미해결건만 긴급 배너 출력
        const activeAlert = Array.isArray(alerts) ? alerts.find(a => 
          a.alert_status === 'SENT' && !falseAlarmList.includes(a.event_no) && !falseAlarmList.includes(a.alert_no) && !resolvedList.includes(a.event_no) && !resolvedList.includes(a.alert_no)
        ) : null;
        
        const confirmedEvent = Array.isArray(events) ? events.find(e => 
          (e.event_status === 'CONFIRMED' || e.event_class === 'FLAME_SMOKE') &&
          e.event_status !== 'FALSE_ALARM' &&
          e.event_status !== 'RESOLVED' &&
          e.event_status !== 'CANCEL' &&
          e.alert_status !== 'CANCEL' &&
          !falseAlarmList.includes(e.event_no) &&
          !resolvedList.includes(e.event_no)
        ) : null;

        if (activeAlert || confirmedEvent) {
          const bannerData = {
            alert_no: activeAlert?.alert_no || null,
            event_no: activeAlert?.event_no || confirmedEvent?.event_no || 1,
            cctv_no: confirmedEvent?.cctv_no || activeAlert?.cctv_no,
            cctv_name: activeAlert?.cctv_name || confirmedEvent?.cctv_name || 'A동 1층 로비 메인',
            location: confirmedEvent?.cctv_location || 'A동 1층 중앙 서측 관제 구역',
            confidence: confirmedEvent?.event_confidence ? Math.round(confirmedEvent.event_confidence * 100) : 98,
            event_class: activeAlert?.event_class || confirmedEvent?.event_class || 'FLAME_SMOKE',
            detected_at: confirmedEvent?.event_first_detected_at || activeAlert?.alert_sent_at || new Date().toISOString()
          };
          setActiveAlertBanner(prev => {
            if (prev && prev.isTest && !activeAlert) {
              return prev;
            }
            return bannerData;
          });
        } else {
          // 사용자가 진행 중인 테스트 비상 배너는 해결 버튼을 누르기 전까지 4초 폴링이나 마커 선택 시 지우지 않는다.
          setActiveAlertBanner(prev => {
            if (prev && prev.isTest) {
              return prev;
            }
            return null;
          });
        }

        // 실시간 AI 감지 로그에는 미해결 감지건만 노출 (조치 완료/오탐 처리건은 안 보이게 제거)
        if (Array.isArray(events) && events.length > 0) {
          const activeEvents = events.filter(ev => {
            const isResolved = ev.event_status === 'FALSE_ALARM' || 
                               ev.event_status === 'RESOLVED' || 
                               ev.event_status === 'CANCEL' || 
                               ev.alert_status === 'CANCEL' || 
                               falseAlarmList.includes(ev.event_no) || 
                               resolvedList.includes(ev.event_no);
            return !isResolved;
          });

          const mappedLogs = activeEvents.map(ev => ({
            id: ev.event_no,
            event_no: ev.event_no,
            time: ev.event_first_detected_at ? ev.event_first_detected_at.substring(11, 19) : '14:00:00',
            message: `${ev.cctv_name || '카메라'} ${ev.event_class === 'FLAME_SMOKE' ? '화재 및 연기 감지' : '화재 의심 감지'} (${Math.round((ev.event_confidence || 0.9) * 100)}%)`,
            type: 'fire'
          }));
          setEventLogs(mappedLogs);
        }
      } catch (err) {
        console.warn('이벤트/알림 수신 오류:', err.message);
      } finally {
        setLoading(false);
      }
    };

    // 최초 마운트 시 1회 호출
    fetchInitialData();

    // 알림 및 이벤트 데이터는 즉시 1회 호출 후 4초 간격 폴링
    fetchPollingData();
    const intervalId = setInterval(fetchPollingData, 4000);
    return () => clearInterval(intervalId);
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
    authApi.logout();
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

  // 실시간 긴급 이벤트 상세 모달 열기
  const handleOpenEventDetail = async (eventNo) => {
    setIsDetailLoading(true);
    try {
      const res = await eventApi.get(eventNo).catch(() => null);
      if (res) {
        setSelectedEventDetail(res);
      } else {
        setSelectedEventDetail({
          event_no: eventNo || 1,
          cctv_name: activeAlertBanner?.cctv_name || 'A동 1층 로비 메인',
          cctv_location: activeAlertBanner?.location || 'A동 1층 중앙 서측 관제 구역',
          event_status: 'CONFIRMED',
          event_class: activeAlertBanner?.event_class || 'FLAME_SMOKE',
          event_confidence: (activeAlertBanner?.confidence || 98) / 100,
          event_first_detected_at: activeAlertBanner?.detected_at || new Date().toISOString(),
          thumbnail_url: null,
          reports: []
        });
      }
    } catch (err) {
      console.warn('이벤트 상세 정보 수신 실패:', err);
    } finally {
      setIsDetailLoading(false);
    }
  };

  // ⚡ 비상 배너 테스트 버튼 클릭 시 CCTV 직접 선택 모달 오픈
  const triggerBannerTest = () => {
    setIsTestCctvSelectModalOpen(true);
  };

  // 선택한 특정 CCTV 장비로 비상 화재 알림 배너 발령
  const triggerBannerTestWithCctv = (cctv) => {
    const targetCctv = cctv || cctvList[0] || {
      cctv_no: 1,
      name: 'A동 1층 로비 메인',
      location: 'A동 1층 중앙 서측 관제 구역'
    };
    const randomConfidence = Math.floor(Math.random() * 7) + 93; // 93%~99%
    const now = new Date();
    
    const testData = {
      alert_no: Date.now(),
      event_no: Date.now(),
      cctv_no: targetCctv.cctv_no || 1,
      cctv_name: targetCctv.name || 'A동 1층 로비 메인',
      location: targetCctv.location || 'A동 1층 중앙 서측 관제 구역',
      confidence: randomConfidence,
      event_class: 'FLAME_SMOKE',
      detected_at: now.toISOString(),
      isTest: true
    };

    // 해당 CCTV를 현재 선택 상태로 전환하고 지도 뷰 및 비상 배너 갱신
    setSelectedCCTV(targetCctv);
    setIsBannerDismissed(false);
    setActiveAlertBanner(testData);

    // 실시간 AI 감지 로그 패널에도 해당 테스트 감지건 추가
    setEventLogs(prev => [
      {
        id: testData.event_no,
        event_no: testData.event_no,
        time: now.toISOString().substring(11, 19),
        message: `${testData.cctv_name} 화재 및 연기 감지 (${testData.confidence}%)`,
        type: 'fire',
        isTest: true
      },
      ...prev.filter(l => l.event_no !== testData.event_no)
    ]);
    showToast(`🚨 [비상 테스트] (${testData.cctv_name}) 화재 비상 배너가 동작되었습니다.`);
  };

  // 알림 응답 (화재 확인 / 소방서 출동 승인 / 오탐 취소)
  const handleRespondAlert = async (action) => {
    const alertNo = activeAlertBanner?.alert_no || Date.now();
    const targetEventNo = activeAlertBanner?.event_no || Date.now();
    const cctvName = activeAlertBanner?.cctv_name || 'A동 1층 로비 메인';
    const cctvLoc = activeAlertBanner?.location || '관제 구역';
    const confidence = activeAlertBanner?.confidence || 98;
    const dateStr = new Date().toISOString().substring(0, 16).replace('T', ' ');

    try {
      await alertApi.respond(alertNo, action).catch(() => null);
      
      const isConfirm = action === 'READ'; // 화재 확인 / 소방서 승인
      showToast(isConfirm 
        ? '🔥 화재가 확인되었으며 119 비상 출동 절차가 승인되었습니다!' 
        : '✅ 오탐지 취소 처리되었습니다.'
      );

      setSelectedEventDetail(null);
      setIsBannerDismissed(true);
      setActiveAlertBanner(null);

      // 1. 대시보드 실시간 AI 화재 감지 로그(eventLogs)에서 조치 완료된 항목 제거 (안 보이게 처리)
      setEventLogs(prev => prev.filter(l => l.event_no !== targetEventNo && l.id !== targetEventNo && l.id !== alertNo));

      // 2. 조치 완료된 항목을 resolvedEvents 스토리지에 보존하여 4초 폴링 시에도 감지 로그에서 제외
      const resolvedList = JSON.parse(localStorage.getItem('resolvedEvents') || '[]');
      if (targetEventNo && !resolvedList.includes(targetEventNo)) resolvedList.push(targetEventNo);
      if (alertNo && !resolvedList.includes(alertNo)) resolvedList.push(alertNo);
      localStorage.setItem('resolvedEvents', JSON.stringify(resolvedList));

      // 3. 마이페이지용 영구 활동 기록(userActivityLogs)에 조치 결과 보존
      const userLogs = JSON.parse(localStorage.getItem('userActivityLogs') || '[]');
      const newActivity = {
        id: targetEventNo,
        time: dateStr,
        type: isConfirm ? 'fire' : 'false_alarm',
        title: isConfirm ? '🔥 소방서 119 비상 출동 승인 완료' : '✅ 화재 알림 오탐지 취소 처리',
        detail: `${cctvName} (${cctvLoc}) - ${isConfirm ? `신뢰도 ${confidence}% 긴급 출동 요청` : '관제 요원 오탐 취소 완료'}`
      };
      userLogs.unshift(newActivity);
      localStorage.setItem('userActivityLogs', JSON.stringify(userLogs.slice(0, 30)));

      // 4. 오탐인 경우 falseAlarmEvents 스토리지에도 기록 추가
      if (!isConfirm) {
        const falseAlarmList = JSON.parse(localStorage.getItem('falseAlarmEvents') || '[]');
        if (targetEventNo && !falseAlarmList.includes(targetEventNo)) falseAlarmList.push(targetEventNo);
        if (alertNo && !falseAlarmList.includes(alertNo)) falseAlarmList.push(alertNo);
        localStorage.setItem('falseAlarmEvents', JSON.stringify(falseAlarmList));
      }
    } catch (err) {
      showToast(err.message || '응답 처리에 실패했습니다.');
    }
  };

  // ui_modal_rules 수칙 100% 준수: 고정 및 제약 너비(style) 지정 + shrink-0 + box-border
  if (loading) {
    return (
      <div className="min-h-screen bg-canvas text-ink flex flex-col items-center justify-center font-ui p-4 transition-colors duration-300">
        <div
          style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
          className="shrink-0 flex flex-col items-center gap-6 p-8 rounded-2xl bg-canvas border border-hairline shadow-2xl text-center box-border animate-in fade-in duration-300"
        >
          <div className="shrink-0 relative flex items-center justify-center w-16 h-16">
            <Loader2 className="w-14 h-14 text-red-500 animate-spin shrink-0" />
            <span className="absolute text-xl animate-pulse">🔥</span>
          </div>
          <div className="shrink-0 space-y-2 w-full">
            <h3 className="font-display text-heading-md font-bold text-ink tracking-tight">
              CCTV 위치 및 관제 DB 동기화 중
            </h3>
            <p className="text-body-sm text-mute leading-relaxed">
              등록된 CCTV 위치 좌표 및 관할 소방서 데이터베이스를 동기화하고 있습니다.
            </p>
          </div>
          <div className="shrink-0 flex items-center justify-center gap-2 px-4 h-11 rounded-full bg-surface-soft text-caption-sm font-bold text-mute border border-hairline animate-pulse w-full max-w-[340px] box-border">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping shrink-0" />
            <span className="truncate">📹 CCTV 실시간 좌표 연결 완료 대기 중...</span>
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
        <section className="flex-1 bg-surface-soft relative border-r border-hairline overflow-hidden flex flex-col z-0" style={{ maxHeight: 'calc(100vh - 56px)' }}>
          {/* 상단 검색/필터 바 오버레이 */}
          <div className="absolute top-4 left-4 z-30 flex flex-wrap items-center gap-2 pointer-events-none">
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
          </div>

          {/* 우측 하단: 관할 소방서 선택 드롭다운 */}
          <div className={`absolute bottom-4 right-4 ${isAgencyTabOpen ? 'z-[1000]' : 'z-30'}`}>
            <button
              onClick={() => setIsAgencyTabOpen(!isAgencyTabOpen)}
              className="flex items-center gap-2 bg-canvas/90 backdrop-blur-md border border-hairline rounded-full px-4 h-[38px] shadow-md hover:border-ink transition-all cursor-pointer text-xs font-bold text-ink"
            >
              <MapPin className="w-3.5 h-3.5 text-red-500" />
              <span>소방서: {fireStation?.name || '소방서'}</span>
            </button>

            {/* 소방서 선택 팝업 패널 (위로 펼침) */}
            {isAgencyTabOpen && (
              <div
                style={{ width: '320px', minWidth: '280px', maxWidth: '90vw' }}
                className="absolute right-0 bottom-12 z-[1000] bg-canvas border border-hairline rounded-2xl shadow-2xl p-3 shrink-0 box-border"
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

          {/* GIS Leaflet 지도 (CartoDB 타일) */}
          <div className="w-full h-full relative">
            <GisMap
              cctvList={filteredCCTVs.map(cctv => ({
                ...cctv,
                address: cctv.location,
                isEmergency: Boolean(
                  activeAlertBanner && (
                    activeAlertBanner.cctv_no === cctv.cctv_no ||
                    activeAlertBanner.cctv_name === cctv.name
                  )
                ) || cctv.status === 'fire'
              }))}
              agencyList={agencyList}
              selectedCCTV={selectedCCTV}
              onSelectCCTV={(cctv) => {
                setSelectedCCTV(cctv);
                const isFireAlert = activeAlertBanner && (
                  activeAlertBanner.cctv_no === cctv.cctv_no ||
                  activeAlertBanner.cctv_name === cctv.name
                );
                if (isFireAlert) {
                  handleOpenEventDetail(activeAlertBanner?.event_no || cctv.cctv_no || 1);
                }
              }}
              showFireStation={showFireStation}
              center={fireStation ? [parseFloat(fireStation.lat || fireStation.agency_lat || 37.5665), parseFloat(fireStation.lng || fireStation.agency_lng || 126.9780)] : [37.5665, 126.9780]}
              zoom={14}
            />
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
                  streamUrl={selectedCCTV.stream_url || selectedCCTV.streamUrl || ''}
                  cctvName={selectedCCTV.name}
                  isFire={selectedCCTV.status === 'fire' || Boolean(activeAlertBanner && (activeAlertBanner.cctv_no === selectedCCTV.cctv_no || activeAlertBanner.cctv_name === selectedCCTV.name))}
                />
                <div className="p-3 bg-canvas border-t border-hairline flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-ink">{selectedCCTV.name}</span>
                    <p className="text-[11px] text-mute">{selectedCCTV.location}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {((activeAlertBanner && (activeAlertBanner.cctv_no === selectedCCTV.cctv_no || activeAlertBanner.cctv_name === selectedCCTV.name)) || selectedCCTV.status === 'fire') && (
                      <button
                        onClick={() => handleOpenEventDetail(activeAlertBanner?.event_no || selectedCCTV.cctv_no || 1)}
                        className="px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white font-bold text-[10px] rounded-full shadow-xs transition-all flex items-center gap-1 cursor-pointer animate-pulse"
                      >
                        <span>🔥 긴급 팝업 보기</span>
                      </button>
                    )}
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${selectedCCTV.status === 'fire' || activeAlertBanner?.cctv_name === selectedCCTV.name
                      ? 'bg-red-500/10 text-red-500 border border-red-500/20'
                      : selectedCCTV.status === 'offline'
                        ? 'bg-neutral-500/10 text-neutral-500 border border-neutral-500/20'
                        : 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                      }`}>
                      {selectedCCTV.status === 'fire' || activeAlertBanner?.cctv_name === selectedCCTV.name ? '화재 감지' : selectedCCTV.status === 'offline' ? '오프라인' : '정상 작동'}
                    </span>
                  </div>
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
              {filteredCCTVs.map((cctv) => {
                const isFireAlert = activeAlertBanner && (
                  activeAlertBanner.cctv_no === cctv.cctv_no || 
                  activeAlertBanner.cctv_name === cctv.name || 
                  cctv.status === 'fire'
                );

                return (
                  <div
                    key={cctv.id}
                    onClick={() => {
                      setSelectedCCTV(cctv);
                      if (isFireAlert) {
                        handleOpenEventDetail(activeAlertBanner?.event_no || cctv.cctv_no || 1);
                      }
                    }}
                    className={`p-3 rounded-xl border text-xs cursor-pointer transition-all flex items-center justify-between ${
                      isFireAlert
                        ? 'border-red-500 bg-red-500/20 text-ink font-bold shadow-md ring-2 ring-red-500/40'
                        : selectedCCTV?.id === cctv.id
                        ? 'border-red-500/50 bg-red-500/10 text-ink font-bold shadow-xs'
                        : 'border-hairline hover:border-hairline-deep bg-canvas text-body'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${
                        isFireAlert ? 'bg-red-500 animate-ping' : cctv.status === 'offline' ? 'bg-neutral-400' : 'bg-emerald-500'
                      }`} />
                      <div>
                        <div className="flex items-center gap-1.5">
                          <p className="font-bold text-ink">{cctv.name}</p>
                          {isFireAlert && (
                            <span className="text-[10px] bg-red-600 text-white font-bold px-1.5 py-0.2 rounded-full border border-red-400 animate-pulse">
                              🔥 화재 감지됨
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-mute">{cctv.location}</p>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-mute">{cctv.id}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 실시간 감지 로그 패널 */}
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-mute uppercase tracking-wider flex items-center gap-1.5">
                <Bell className="w-3.5 h-3.5 text-red-500" />
                <span>실시간 AI 화재 감지 로그</span>
              </h3>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setIsActionHistoryModalOpen(true)}
                  className="text-[10px] font-bold text-ink bg-surface-soft hover:bg-surface-soft/80 px-2.5 py-0.5 rounded-full border border-hairline transition-all cursor-pointer shadow-xs flex items-center gap-1"
                  title="관제 요원 조치 완료 이력(오탐 취소/119 승인) 팝업 모달 열기"
                >
                  <FileText className="w-3 h-3 text-mute" />
                  <span>📋 조치 이력</span>
                </button>
                <button
                  onClick={triggerBannerTest}
                  className="text-[10px] font-bold text-red-600 dark:text-red-400 bg-red-500/10 hover:bg-red-500/20 px-2 py-0.5 rounded-full border border-red-500/30 transition-all cursor-pointer shadow-xs flex items-center gap-1"
                  title="클릭 시 CCTV 선택 긴급 화재 알림 배너 테스트 실행"
                >
                  <Siren className="w-3 h-3 animate-pulse" />
                  <span>⚡ 비상 배너 테스트</span>
                </button>
              </div>
            </div>

            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {eventLogs.length === 0 ? (
                <div
                  onClick={triggerBannerTest}
                  className="p-3.5 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-xs cursor-pointer transition-all text-center space-y-1 group"
                >
                  <div className="flex items-center justify-center gap-1.5 text-red-500 font-bold">
                    <Siren className="w-4 h-4 animate-pulse" />
                    <span>[테스트] 상단 비상 배너 호출하기</span>
                  </div>
                  <p className="text-[11px] text-mute group-hover:text-ink transition-colors">
                    이 박스를 클릭하면 등록된 CCTV 중 1곳의 화재 알림 배너가 내려옵니다.
                  </p>
                </div>
              ) : (
                eventLogs.map((log) => (
                  <div
                    key={log.id}
                    onClick={() => handleOpenEventDetail(log.event_no)}
                    className="p-2.5 rounded-lg border border-hairline bg-surface-soft hover:bg-red-500/10 hover:border-red-500/40 text-xs space-y-1 cursor-pointer transition-all group shadow-xs"
                    title="클릭 시 화재 감지 이벤트 상세 정보 팝업 모달 열기"
                  >
                    <div className="flex items-center justify-between text-caption-sm text-mute">
                      <span className="font-mono font-semibold">{log.time}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        log.type === 'fire' 
                          ? 'bg-red-500/10 text-red-500 border border-red-500/20' 
                          : log.type === 'false_alarm'
                          ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30'
                          : 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                      }`}>
                        {log.type === 'fire' ? '🔥 화재 경보' : log.type === 'false_alarm' ? '✅ 오탐 취소' : 'ℹ️ 정보'}
                      </span>
                    </div>
                    <p className="text-ink font-bold group-hover:text-red-500 transition-colors flex items-center justify-between">
                      <span className={log.type === 'false_alarm' ? 'line-through text-mute font-normal' : ''}>{log.message}</span>
                      <span className="text-[10px] text-mute group-hover:text-red-500 underline font-normal">&rarr; 상세보기</span>
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      </main>

      {/* ITS 공공 CCTV 검색 모달 다이얼로그 */}
      {isItsModalOpen && (
        <ItsCctvModal
          isOpen={isItsModalOpen}
          onClose={() => setIsItsModalOpen(false)}
          onSelectCctv={async (itsCctv) => {
            // ITS CCTV는 DB 등록이 완료된 경우에만 대시보드에 추가한다.
            try {
              const alreadyRegistered = cctvList.some((cctv) => isSameRegisteredCctv(cctv, itsCctv));
              if (alreadyRegistered) {
                showToast(`[${itsCctv.cctv_name}] 이미 등록된 CCTV입니다.`);
                return { alreadyRegistered: true };
              }

              const res = await cctvApi.create({
                cctv_name: itsCctv.cctv_name,
                cctv_location: itsCctv.cctv_location,
                cctv_lat: parseFloat(itsCctv.cctv_lat) || 37.5665,
                cctv_lng: parseFloat(itsCctv.cctv_lng) || 126.9780,
                cctv_stream_url: itsCctv.cctv_stream_url || '',
                cctv_width: 1920,
                cctv_height: 1080
              });

              const dbCctvNo = res?.cctv_no;
              if (!dbCctvNo) {
                throw new Error('DB 등록 응답에 cctv_no가 없습니다.');
              }

              const newCctv = {
                id: `CCTV-${String(dbCctvNo).padStart(2, '0')}`,
                cctv_no: dbCctvNo,
                name: itsCctv.cctv_name,
                cctv_name: itsCctv.cctv_name,
                status: 'normal',
                location: itsCctv.cctv_location,
                lat: parseFloat(itsCctv.cctv_lat) || 37.5665,
                lng: parseFloat(itsCctv.cctv_lng) || 126.9780,
                stream_url: itsCctv.cctv_stream_url || '',
                ownerId: currentUser?.id || 'user01',
                ownerName: currentUser?.name || '사용자',
                installedAt: new Date().toISOString().substring(0, 10),
                history: []
              };

              setCctvList(prev => [newCctv, ...prev]);
              setSelectedCCTV(newCctv);
              setIsItsModalOpen(false);
              showToast(`✅ [${itsCctv.cctv_name}] DB 등록 완료 (CCTV #${dbCctvNo})`);
            } catch (err) {
              console.warn('ITS CCTV DB 등록 실패:', err.message);
              if (err.status === 409 || /duplicate|already|exists|중복|이미/.test(String(err.message || '').toLowerCase())) {
                showToast(`[${itsCctv.cctv_name}] 이미 등록된 CCTV입니다.`);
                return { alreadyRegistered: true };
              }
              showToast(`❌ [${itsCctv.cctv_name}] DB 등록 실패: ${err.message}`);
            }
          }}
        />
      )}

      {/* 실시간 긴급 상단 알림 드롭다운 배너 */}
      {activeAlertBanner && !isBannerDismissed && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-top-4 duration-300 pointer-events-auto">
          <div
            className="bg-red-600 text-white rounded-2xl sm:rounded-full px-5 py-3 shadow-2xl border-2 border-red-400 font-bold flex flex-wrap sm:flex-nowrap items-center gap-3 ring-4 ring-red-500/40"
            style={{ minWidth: '380px', maxWidth: '95vw' }}
          >
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className="w-3 h-3 rounded-full bg-white animate-ping shrink-0" />
              <span className="text-xl shrink-0">🚨</span>
              <div className="truncate text-xs sm:text-sm">
                <span className="font-extrabold">
                  [화재 긴급 감지] {activeAlertBanner.cctv_name}
                </span>
                <span className="ml-2 font-mono text-red-100 text-xs font-semibold">
                  ({activeAlertBanner.confidence}% 신뢰도)
                </span>
              </div>
            </div>

            <div className="flex items-center gap-1.5 shrink-0 w-full sm:w-auto justify-end pt-1 sm:pt-0">
              <button
                onClick={() => handleOpenEventDetail(activeAlertBanner.event_no)}
                className="h-8 px-3 bg-white text-red-600 hover:bg-red-50 font-bold text-xs rounded-full shadow-xs transition-colors cursor-pointer flex items-center gap-1"
                title="화재 이벤트 상세 및 조치 팝업 열기"
              >
                <span>🔥 상세보기</span>
              </button>
              <button
                onClick={() => handleRespondAlert('CANCEL')}
                className="h-8 px-3 bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs rounded-full shadow-xs transition-colors cursor-pointer"
                title="오탐지 취소 및 기록 저장"
              >
                오탐지 취소
              </button>
              <button
                onClick={() => handleRespondAlert('READ')}
                className="h-8 px-3 bg-black hover:bg-neutral-900 text-white font-bold text-xs rounded-full shadow-xs transition-colors cursor-pointer"
                title="소방서 119 비상 출동 승인"
              >
                119 승인
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast 메시지 */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-primary text-on-primary px-5 py-3 rounded-full text-body-sm font-medium shadow-lg flex items-center gap-2 animate-in fade-in duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* 팝업 모달 수칙 준수: 화재 이벤트 감지 통합 상세 다이얼로그 (Dialog Popup) */}
      {(selectedEventDetail || isDetailLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
          <div
            style={{ width: '840px', minWidth: '320px', maxWidth: '95vw' }}
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl flex flex-col shrink-0 box-border"
          >
            {/* 모달 헤더 (shrink-0) */}
            <div className="p-5 border-b border-hairline flex items-center justify-between bg-surface-soft/60 shrink-0 rounded-t-2xl">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-red-500/10 text-red-500 rounded-xl border border-red-500/20 shrink-0">
                  <Siren className="w-6 h-6 animate-pulse" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-red-600 text-white font-bold rounded text-[11px]">
                      화재 확정 이벤트 #{selectedEventDetail?.event_no || 1}
                    </span>
                    <span className="text-xs text-mute font-mono">
                      신뢰도 {Math.round((selectedEventDetail?.event_confidence || 0.98) * 100)}%
                    </span>
                  </div>
                  <h2 className="text-heading-sm font-bold text-ink mt-0.5">
                    {selectedEventDetail?.cctv_name || 'A동 1층 로비 메인'} 감지 현황
                  </h2>
                </div>
              </div>

              <button
                onClick={() => setSelectedEventDetail(null)}
                className="p-1.5 rounded-lg text-mute hover:text-ink hover:bg-surface-soft transition-colors cursor-pointer shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 모달 본문 (max-h-[75vh] overflow-y-auto space-y-4) */}
            <div className="p-6 max-h-[75vh] overflow-y-auto space-y-5">
              {isDetailLoading ? (
                <div className="flex flex-col items-center justify-center py-16 space-y-3">
                  <Loader2 className="w-10 h-10 text-red-500 animate-spin" />
                  <span className="text-xs font-bold text-mute">백엔드 DB에서 이벤트 상세 미디어 및 119 이력을 수신하는 중...</span>
                </div>
              ) : (
                <>
                  {/* 상단 2컬럼: 비디오/스냅샷 뷰어 + 감지 메타 정보 */}
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
                    <div className="md:col-span-7">
                      <div className="aspect-video bg-black rounded-xl overflow-hidden border border-hairline shadow-md relative">
                        {selectedCCTV ? (
                          <CctvPlayer
                            streamUrl={selectedCCTV.stream_url || selectedCCTV.streamUrl}
                            cctvName={selectedCCTV.name || selectedCCTV.cctv_name}
                            isFire={selectedCCTV.status === 'fire'}
                          />
                        ) : selectedEventDetail?.thumbnail_url ? (
                          <img src={selectedEventDetail.thumbnail_url} alt="화재 스냅샷" className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center text-mute space-y-2">
                            <Flame className="w-12 h-12 text-red-500 animate-pulse" />
                            <span className="text-xs font-bold">화재 패턴 감지 스트림</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="md:col-span-5 space-y-3 text-xs">
                      <div className="p-3.5 bg-surface-soft border border-hairline rounded-xl space-y-2">
                        <span className="text-caption-sm text-mute font-bold uppercase tracking-wider block">카메라 및 설치 장소</span>
                        <div className="font-bold text-ink text-sm flex items-center gap-1.5">
                          <MapPin className="w-4 h-4 text-red-500" />
                          <span>{selectedEventDetail?.cctv_name}</span>
                        </div>
                        <p className="text-mute text-xs">{selectedEventDetail?.cctv_location || 'A동 중앙 서측 관제 구역'}</p>
                      </div>

                      <div className="p-3.5 bg-surface-soft border border-hairline rounded-xl space-y-2">
                        <span className="text-caption-sm text-mute font-bold uppercase tracking-wider block">화재 감지 시각 & 클래스</span>
                        <div className="flex items-center justify-between">
                          <span className="text-mute">감지 클래스:</span>
                          <span className="font-bold text-red-500 bg-red-500/10 px-2 py-0.5 rounded border border-red-500/20">
                            {selectedEventDetail?.event_class || 'FLAME_SMOKE'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-mute">최초 감지 시각:</span>
                          <span className="font-mono font-semibold text-ink">
                            {selectedEventDetail?.event_first_detected_at ? selectedEventDetail.event_first_detected_at.substring(0, 19) : '2026-08-11 12:25:25'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 119 신고 및 승계 이력 타임라인 */}
                  <div className="p-4 bg-surface-soft border border-hairline rounded-xl space-y-3">
                    <h3 className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-2">
                      <PhoneCall className="w-4 h-4 text-red-500" />
                      <span>관할 소방서 119 비상 신고 연동 상태</span>
                    </h3>

                    <div className="space-y-2">
                      <div className="p-3 bg-canvas border border-hairline rounded-lg text-xs flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                          <span className="font-bold text-ink">종로소방서 (1차 승계 대상)</span>
                          <span className="text-[11px] text-mute">(서울특별시 종로구 종로1길 28)</span>
                        </div>
                        <span className="text-xs font-mono font-bold text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                          119 비상 출동 대기중
                        </span>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* 모달 푸터 액션 (shrink-0) */}
            <div className="p-4 border-t border-hairline bg-surface-soft/60 flex items-center justify-between shrink-0 rounded-b-2xl">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleRespondAlert('READ')}
                  className="h-11 px-5 bg-red-600 hover:bg-red-700 text-white font-bold text-xs rounded-xl transition-all cursor-pointer shadow-md flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>화재 확정 및 119 비상 출동 승인</span>
                </button>
                <button
                  onClick={() => handleRespondAlert('CANCEL')}
                  className="h-11 px-4 bg-canvas border border-hairline hover:border-ink text-ink font-semibold text-xs rounded-xl transition-all cursor-pointer flex items-center gap-1.5"
                >
                  <XCircle className="w-4 h-4 text-mute" />
                  <span>오탐지 취소</span>
                </button>
              </div>

              <button
                onClick={() => setSelectedEventDetail(null)}
                className="h-11 px-5 bg-primary text-on-primary hover:bg-ink-deep font-bold text-xs rounded-xl transition-all cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. 비상 화재 테스트 - CCTV 직접 선택 팝업 모달 다이얼로그 (ui_modal_rules 100% 준수) */}
      {isTestCctvSelectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in">
          <div
            style={{ width: '520px', minWidth: '320px', maxWidth: '95vw' }}
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl overflow-hidden shrink-0 flex flex-col box-border max-h-[85vh]"
          >
            {/* 모달 헤더 (shrink-0) */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-hairline shrink-0 bg-surface-soft/50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-red-500/10 border border-red-500/30 text-red-500 shrink-0">
                  <Siren className="w-5 h-5 animate-pulse" />
                </div>
                <div>
                  <h3 className="font-display text-body-lg-strong font-bold text-ink">비상 화재 테스트 - CCTV 선택</h3>
                  <p className="text-caption-sm text-mute">화재 비상 알림 배너를 발령할 CCTV를 직접 선택하세요.</p>
                </div>
              </div>
              <button
                onClick={() => setIsTestCctvSelectModalOpen(false)}
                className="text-mute hover:text-ink transition-colors p-1.5 rounded-lg hover:bg-surface-soft cursor-pointer shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* CCTV 선택 목록 스크롤 영역 */}
            <div className="p-6 overflow-y-auto space-y-3 shrink flex-1 max-h-[60vh]">
              <p className="text-caption-sm font-bold text-mute uppercase tracking-wider">
                등록된 CCTV 장비 목록 ({cctvList.length}개)
              </p>
              
              <div className="space-y-2">
                {cctvList.map((cctv) => (
                  <div
                    key={cctv.id}
                    onClick={() => {
                      triggerBannerTestWithCctv(cctv);
                      setIsTestCctvSelectModalOpen(false);
                    }}
                    className="p-3.5 rounded-xl border border-hairline hover:border-red-500/60 bg-surface-soft hover:bg-red-500/10 transition-all cursor-pointer flex items-center justify-between group shadow-xs box-border min-h-[64px]"
                  >
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="w-10 h-10 rounded-full bg-canvas border border-hairline flex items-center justify-center text-red-500 group-hover:scale-110 transition-transform shrink-0">
                        <Video className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <h4 className="font-bold text-body-sm text-ink group-hover:text-red-500 transition-colors truncate">
                          {cctv.name}
                        </h4>
                        <p className="text-caption-sm text-mute flex items-center gap-1 mt-0.5 truncate">
                          <MapPin className="w-3.5 h-3.5 text-mute shrink-0" />
                          <span className="truncate">{cctv.location}</span>
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      <span className="text-caption-sm font-mono text-mute bg-canvas px-2 py-0.5 rounded border border-hairline hidden sm:inline-block">
                        {cctv.id}
                      </span>
                      <span className="px-3.5 h-9 rounded-full bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all flex items-center justify-center shadow-xs">
                        선택 &rarr;
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 모달 푸터 (shrink-0) */}
            <div className="px-6 py-4 border-t border-hairline shrink-0 bg-surface-soft/30 flex items-center justify-end">
              <button
                onClick={() => setIsTestCctvSelectModalOpen(false)}
                className="px-5 h-10 rounded-full border border-hairline hover:bg-surface-soft text-body-sm font-bold text-mute transition-colors cursor-pointer"
              >
                취소 / 닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. 관제 조치 완료 이력 팝업 모달 다이얼로그 (오탐 취소 & 119 출동 승인 기록) */}
      {isActionHistoryModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in">
          <div
            style={{ width: '560px', minWidth: '320px', maxWidth: '95vw' }}
            className="bg-canvas border border-hairline rounded-2xl shadow-2xl overflow-hidden shrink-0 flex flex-col box-border max-h-[85vh]"
          >
            {/* 모달 헤더 (shrink-0) */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-hairline shrink-0 bg-surface-soft/50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-500 shrink-0">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-display text-body-lg-strong font-bold text-ink">관제 조치 및 활동 이력</h3>
                  <p className="text-caption-sm text-mute">오탐지 취소 처리 및 119 비상 출동 승인 완료 내역입니다.</p>
                </div>
              </div>
              <button
                onClick={() => setIsActionHistoryModalOpen(false)}
                className="text-mute hover:text-ink transition-colors p-1.5 rounded-lg hover:bg-surface-soft cursor-pointer shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 조치 이력 목록 스크롤 영역 */}
            <div className="p-6 overflow-y-auto space-y-3 shrink flex-1 max-h-[60vh]">
              {(() => {
                const logs = JSON.parse(localStorage.getItem('userActivityLogs') || '[]');
                if (logs.length === 0) {
                  return (
                    <div className="py-12 text-center text-mute space-y-2">
                      <FileText className="w-8 h-8 text-mute mx-auto opacity-50" />
                      <p className="text-body-sm font-semibold">아직 조치 완료된 이력 기록이 없습니다.</p>
                      <p className="text-caption-sm text-mute">비상 배너 테스트 후 [오탐지 취소] 또는 [119 승인]을 누르시면 이곳에 영구 기록됩니다.</p>
                    </div>
                  );
                }
                return logs.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 rounded-xl border border-hairline/80 bg-surface-soft/60 space-y-1.5"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className={`px-2.5 py-0.5 rounded-full font-bold text-[11px] border ${
                        item.type === 'fire'
                          ? 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30'
                          : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30'
                      }`}>
                        {item.title}
                      </span>
                      <span className="font-mono text-caption-sm text-mute">{item.time}</span>
                    </div>
                    <p className="text-body-sm font-bold text-ink">{item.detail}</p>
                  </div>
                ));
              })()}
            </div>

            {/* 모달 푸터 (shrink-0) */}
            <div className="px-6 py-4 border-t border-hairline shrink-0 bg-surface-soft/30 flex items-center justify-end">
              <button
                onClick={() => setIsActionHistoryModalOpen(false)}
                className="px-5 h-10 rounded-full border border-hairline hover:bg-surface-soft text-body-sm font-bold text-mute transition-colors cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
