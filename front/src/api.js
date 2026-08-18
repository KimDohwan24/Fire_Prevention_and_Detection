/**
 * FireGuard 백엔드 API 클라이언트
 * Base URL: /api (vite proxy -> http://localhost:5000/api)
 */

export const API_BASE_URL = '/api';

// 토큰 저장/조회/삭제 헬퍼
export function getAccessToken() {
  return localStorage.getItem('access_token');
}

export function setAccessToken(token) {
  if (token) {
    localStorage.setItem('access_token', token);
  } else {
    localStorage.removeItem('access_token');
  }
}

export function getCurrentUserFromStorage() {
  try {
    const raw = localStorage.getItem('currentUser');
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

export function setCurrentUserToStorage(user) {
  if (user) {
    localStorage.setItem('currentUser', JSON.stringify(user));
  } else {
    localStorage.removeItem('currentUser');
  }
}

// 로그인 응답(access_token + user)을 스토리지에 반영한다.
// 일반 로그인과 소셜 로그인의 응답 형식이 같으므로, 저장 경로가 갈라지면
// 로그인 이후 화면들이 서로 다른 모양의 currentUser 를 읽게 된다 — 한 곳으로 모은다.
function persistLoginResult(res) {
  if (!res?.access_token) return res;
  setAccessToken(res.access_token);
  setCurrentUserToStorage({
    id: res.user.user_id,
    user_no: res.user.user_no,
    name: res.user.user_name,
    role: res.user.user_role === 'ADMIN' ? 'admin' : 'user',
    rawRole: res.user.user_role,
  });
  return res;
}

async function request(endpoint, options = {}) {
  const token = getAccessToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const config = {
    ...options,
    headers,
  };

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, config);
    if (response.status === 404) {
      // 404 발생 시 백엔드 포트(http://localhost:5000/api)로 직접 2차 시도
      response = await fetch(`http://localhost:5000/api${endpoint}`, config);
    }
  } catch (e) {
    response = await fetch(`http://localhost:5000/api${endpoint}`, config).catch(() => null);
  }

  if (!response) {
    throw new Error('백엔드 API 서버(http://localhost:5000)가 연결 준비 중입니다.');
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    if (response.status === 401 && endpoint !== '/auth/login') {
      localStorage.removeItem('access_token');
    }
    const errorMsg = data?.message || data?.error || `요청 실패 (${response.status})`;
    const error = new Error(errorMsg);
    error.status = response.status;
    error.code = data?.code;
    throw error;
  }

  return data;
}

// 1. 인증 API
export const authApi = {
  login: async (user_id, user_pw) => {
    const res = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ user_id, user_pw }),
    });
    return persistLoginResult(res);
  },

  me: async () => {
    return await request('/auth/me');
  },

  findId: async (user_name, user_email) => {
    return await request('/auth/find-id', {
      method: 'POST',
      body: JSON.stringify({ user_name, user_email }),
    });
  },

  requestPasswordReset: async (user_id, user_name, user_email) => {
    return await request('/auth/password-reset/request', {
      method: 'POST',
      body: JSON.stringify({ user_id, user_name, user_email }),
    });
  },

  confirmPasswordReset: async (user_id, code, user_pw) => {
    return await request('/auth/password-reset/confirm', {
      method: 'POST',
      body: JSON.stringify({ user_id, code, user_pw }),
    });
  },

  logout: async () => {
    try {
      if (getAccessToken()) {
        await request('/auth/logout', { method: 'POST' });
      }
    } catch (error) {
      console.warn('로그아웃 활동 이력을 서버에 저장하지 못했습니다.', error);
    } finally {
      setAccessToken(null);
      setCurrentUserToStorage(null);
    }
  },
};

// 1-1. 소셜 로그인(OAuth) API
// 백엔드가 받는 provider 값(소문자)과 사람에게 보여줄 이름.
export const SOCIAL_PROVIDERS = [
  { id: 'google', name: 'Google' },
  { id: 'kakao', name: '카카오' },
  { id: 'naver', name: '네이버' },
];

// state 는 CSRF 방어용이라 브라우저 탭 안에서만 살아있으면 된다 —
// 탭을 닫으면 사라지도록 localStorage 가 아니라 sessionStorage 를 쓴다.
const oauthStateKey = (provider) => `oauth_state_${provider}`;

export const oauthApi = {
  // 프로바이더 동의 화면 URL 과 state 를 받아온다. (비로그인 공개 엔드포인트)
  getAuthorizeUrl: async (provider) => {
    return await request(`/auth/oauth/${provider}/authorize`);
  },

  saveState: (provider, state) => {
    sessionStorage.setItem(oauthStateKey(provider), state ?? '');
  },

  // 콜백에서 한 번만 쓰고 버린다 — 남겨두면 다음 로그인 시도에 재사용될 수 있다.
  takeState: (provider) => {
    const key = oauthStateKey(provider);
    const saved = sessionStorage.getItem(key);
    sessionStorage.removeItem(key);
    return saved;
  },

  // 인가 코드를 토큰으로 교환한다. 응답 형식이 /auth/login 과 같으므로 저장 경로도 같다.
  login: async (provider, code, state) => {
    const res = await request(`/auth/oauth/${provider}`, {
      method: 'POST',
      body: JSON.stringify({ code, state }),
    });
    return persistLoginResult(res);
  },
};

// 2. 사용자/관리자 API
export const userApi = {
  list: async (status = '') => {
    const query = status ? `?user_status=${encodeURIComponent(status)}` : '';
    return await request(`/users${query}`);
  },

  create: async (userData) => {
    return await request('/users', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  },

  update: async (user_no, userData) => {
    return await request(`/users/${user_no}`, {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
  },

  activities: async (user_no, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return await request(`/users/${user_no}/activities${query ? `?${query}` : ''}`);
  },
};

// 3. CCTV API
export const cctvApi = {
  list: async (filters = {}) => {
    // 기존 list('ACTIVE') 호출도 유지하면서 user_no 등 신규 필터를 함께 지원한다.
    const params = typeof filters === 'string'
      ? { cctv_status: filters }
      : filters;
    const queryString = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== '' && value != null)
    ).toString();
    const query = queryString ? `?${queryString}` : '';
    return await request(`/cctvs${query}`);
  },

  get: async (cctv_no) => {
    return await request(`/cctvs/${cctv_no}`);
  },

  create: async (cctvData) => {
    return await request('/cctvs', {
      method: 'POST',
      body: JSON.stringify(cctvData),
    });
  },

  update: async (cctv_no, cctvData) => {
    return await request(`/cctvs/${cctv_no}`, {
      method: 'PUT',
      body: JSON.stringify(cctvData),
    });
  },

  delete: async (cctv_no) => {
    return await request(`/cctvs/${cctv_no}`, {
      method: 'DELETE',
    });
  },
};

// ITS 실시간 공공 CCTV API — 키는 백엔드에서만 사용한다.
export const itsCctvApi = {
  list: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return await request(`/its/cctvs${query ? `?${query}` : ''}`);
  },
};

// 4. 화재 이벤트 API
export const eventApi = {
  list: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return await request(`/events${query ? `?${query}` : ''}`);
  },

  get: async (event_no) => {
    return await request(`/events/${event_no}`);
  },
};

// 5. 알림 API
export const alertApi = {
  list: async (filters = '') => {
    // 기존 list('SENT') 호출과 페이지/크기 옵션을 모두 지원한다.
    const params = typeof filters === 'string'
      ? (filters ? { alert_status: filters } : {})
      : filters;
    const queryString = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== '' && value != null)
    ).toString();
    const query = queryString ? `?${queryString}` : '';
    return await request(`/alerts${query}`);
  },

  respond: async (alert_no, action) => {
    return await request(`/alerts/${alert_no}/respond`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  },
};

// 6. 관할 소방서 API
export const agencyApi = {
  list: async () => {
    return await request('/agencies');
  },

  create: async (agencyData) => {
    return await request('/agencies', {
      method: 'POST',
      body: JSON.stringify(agencyData),
    });
  },

  update: async (agency_no, agencyData) => {
    return await request(`/agencies/${agency_no}`, {
      method: 'PUT',
      body: JSON.stringify(agencyData),
    });
  },
};

// 7. 119 신고 이력 API
export const reportApi = {
  list: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return await request(`/reports${query ? `?${query}` : ''}`);
  },
};


// 8. 관리자 승급 및 권한 관리 API (추가)
export const adminUpgradeApi = {
  // 일반 회원이 관리자 승인 요청
  requestUpgrade: async () => {
    return await request('/admin/request-upgrade', {
      method: 'POST',
    });
  },

  // 관리자가 유저의 승인 요청을 승인(approve) 또는 거절(reject)
  handleRequest: async (targetUserNo, action) => {
    return await request(`/admin/handle-request/${targetUserNo}`, {
      method: 'PATCH',
      body: JSON.stringify({ action }), // "approve" 또는 "reject"
    });
  },
};
