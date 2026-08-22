const ACTIVITY_STORAGE_KEY = 'userActivityLogs';
const MAX_ACTIVITY_LOGS = 100;

const getStorage = () => {
  if (typeof window === 'undefined') return null;
  return window.localStorage;
};

const readStoredLogs = () => {
  const storage = getStorage();
  if (!storage) return [];

  try {
    const parsed = JSON.parse(storage.getItem(ACTIVITY_STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const createLocalActivityId = () => (
  `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
);

/**
 * 브라우저에 저장된 활동 이력을 현재 사용자 기준으로 읽는다.
 * user_no가 없는 기존 레코드는 scoped 레코드가 하나도 없을 때만 호환한다.
 */
export function getLocalActivityLogs(userNo) {
  const logs = readStoredLogs();
  const hasScopedLogs = logs.some((log) => log?.user_no != null);

  return logs.filter((log) => {
    if (userNo == null) return true;
    if (log?.user_no == null) return !hasScopedLogs;
    return String(log.user_no) === String(userNo);
  });
}

export function appendLocalActivityLog(activity = {}) {
  const storage = getStorage();
  if (!storage) return null;

  const entry = {
    ...activity,
    id: activity.id ?? activity.activity_no ?? createLocalActivityId(),
    activity_at: activity.activity_at ?? activity.time ?? new Date().toISOString(),
  };

  const sameEntry = (stored) => (
    String(stored?.id ?? '') === String(entry.id)
    && String(stored?.user_no ?? '') === String(entry.user_no ?? '')
  );

  const nextLogs = [entry, ...readStoredLogs().filter((stored) => !sameEntry(stored))]
    .slice(0, MAX_ACTIVITY_LOGS);

  try {
    storage.setItem(ACTIVITY_STORAGE_KEY, JSON.stringify(nextLogs));
    return entry;
  } catch {
    return null;
  }
}

export function formatActivityDate(value) {
  if (!value) return '-';

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value).replace('T', ' ').slice(0, 16);
  }

  const pad = (part) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + ` ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function normalizeActivityType(activity = {}) {
  const rawType = String(
    activity.activity_type ?? activity.action_type ?? activity.type ?? ''
  ).toUpperCase();

  if (rawType.includes('LOGOUT') || rawType.includes('SIGN_OUT')) {
    return 'logout';
  }
  if (rawType.includes('LOGIN') || rawType.includes('SIGN_IN') || rawType.includes('ACCESS')) {
    return 'login';
  }
  if (rawType.includes('FALSE') || rawType.includes('CANCEL')) {
    return 'false_alarm';
  }
  if (rawType.includes('FIRE') || rawType.includes('CONFIRM') || rawType.includes('119')) {
    return 'fire';
  }
  if (rawType.includes('ADMIN') || rawType.includes('ROLE')) {
    return 'admin';
  }
  if (rawType.includes('SETTING') || rawType.includes('PREFERENCE') || rawType.includes('PASSWORD')) {
    return 'setting';
  }
  return 'system';
}

const DEFAULT_ACTIVITY_COPY = {
  login: {
    title: '로그인',
    detail: 'FireGuard에 로그인했습니다.',
  },
  logout: {
    title: '로그아웃',
    detail: 'FireGuard에서 로그아웃했습니다.',
  },
  fire: {
    title: '화재 확인 및 119 신고 절차 시작',
    detail: '화재 대응 조치를 시작했습니다.',
  },
  false_alarm: {
    title: '화재 알림 오탐지 취소 처리',
    detail: '화재 알림을 오탐지로 처리했습니다.',
  },
  admin: {
    title: '관리자 권한 변경',
    detail: '관리자 권한 관련 작업을 수행했습니다.',
  },
  setting: {
    title: '알림 설정 변경',
    detail: '개인 알림 설정을 변경했습니다.',
  },
  system: {
    title: '시스템 활동',
    detail: 'FireGuard에서 활동을 수행했습니다.',
  },
};

export function normalizeActivityRecord(activity = {}) {
  const type = normalizeActivityType(activity);
  const defaults = DEFAULT_ACTIVITY_COPY[type];
  const occurredAt = activity.activity_at ?? activity.created_at ?? activity.time;

  return {
    ...activity,
    id: activity.activity_no ?? activity.id ?? `${type}-${occurredAt ?? 'unknown'}`,
    type,
    time: formatActivityDate(occurredAt),
    title: activity.title ?? activity.activity_title ?? defaults.title,
    detail: activity.detail
      ?? activity.activity_detail
      ?? activity.description
      ?? defaults.detail,
  };
}
