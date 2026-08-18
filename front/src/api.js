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
    if (res?.access_token) {
      setAccessToken(res.access_token);
      setCurrentUserToStorage({
        id: res.user.user_id,
        user_no: res.user.user_no,
        name: res.user.user_name,
        role: res.user.user_role === 'ADMIN' ? 'admin' : 'user',
        rawRole: res.user.user_role,
      });
    }
    return res;
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

// ▼ [추가] 이메일 인증번호 발송 요청 API
  requestEmailVerify: async (email) => {
    return await request('/auth/email/verify-request', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  },

  // ▼ [추가] 이메일 인증번호 확인 API
  confirmEmailVerify: async (email, code) => {
    return await request('/auth/email/verify-confirm', {
      method: 'POST',
      body: JSON.stringify({ email, code }),
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


// 1. 인증 API
// export const authApi = {
//   login: async (user_id, user_pw) => {
//     const res = await request('/auth/login', {
//       method: 'POST',
//       body: JSON.stringify({ user_id, user_pw }),
//     });
//     if (res?.access_token) {
//       setAccessToken(res.access_token);
//       setCurrentUserToStorage({
//         id: res.user.user_id,
//         user_no: res.user.user_no,
//         name: res.user.user_name,
//         role: res.user.user_role === 'ADMIN' ? 'admin' : 'user',
//         rawRole: res.user.user_role,
//       });
//     }
//     return res;
//   },

//   me: async () => {
//     return await request('/auth/me');
//   },

//   findId: async (user_name, user_email) => {
//     return await request('/auth/find-id', {
//       method: 'POST',
//       body: JSON.stringify({ user_name, user_email }),
//     });
//   },

//   requestPasswordReset: async (user_id, user_name, user_email) => {
//     return await request('/auth/password-reset/request', {
//       method: 'POST',
//       body: JSON.stringify({ user_id, user_name, user_email }),
//     });
//   },

//   confirmPasswordReset: async (user_id, code, user_pw) => {
//     return await request('/auth/password-reset/confirm', {
//       method: 'POST',
//       body: JSON.stringify({ user_id, code, user_pw }),
//     });
//   },

//   // ▼ [추가] 이메일 인증번호 발송 요청 API
//   requestEmailVerify: async (email) => {
//     return await request('/auth/email/verify-request', {
//       method: 'POST',
//       body: JSON.stringify({ email }),
//     });
//   },

//   // ▼ [추가] 이메일 인증번호 확인 API
//   confirmEmailVerify: async (email, code) => {
//     return await request('/auth/email/verify-confirm', {
//       method: 'POST',
//       body: JSON.stringify({ email, code }),
//     });
//   },

//   logout: () => {
//     setAccessToken(null);
//     setCurrentUserToStorage(null);
//   },
// };