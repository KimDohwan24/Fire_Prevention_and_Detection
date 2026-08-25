export const DEFAULT_AUTHENTICATED_PATH = '/dashboard';
export const AUTH_RETURN_PATH_KEY = 'fireguard_auth_return_to';

const PROTECTED_PATHS = new Set([
  '/dashboard',
  '/monitoring',
  '/mypage',
  '/admin',
]);

const AUTH_ROUTING_ORIGIN = 'https://fireguard.local';

export function sanitizeAuthReturnPath(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) {
    return null;
  }

  try {
    const url = new URL(value, AUTH_ROUTING_ORIGIN);
    if (url.origin !== AUTH_ROUTING_ORIGIN || !PROTECTED_PATHS.has(url.pathname)) {
      return null;
    }
    return `${url.pathname}${url.search}`;
  } catch {
    return null;
  }
}

export function createAuthReturnPath(location) {
  return sanitizeAuthReturnPath(`${location?.pathname || ''}${location?.search || ''}`);
}

export function hasAllowedRole(user, allowedRoles = []) {
  return allowedRoles.length === 0 || allowedRoles.includes(user?.role);
}

export function rememberAuthReturnPath(value) {
  const safePath = sanitizeAuthReturnPath(value);
  if (typeof sessionStorage === 'undefined') return safePath;

  if (safePath) {
    sessionStorage.setItem(AUTH_RETURN_PATH_KEY, safePath);
  } else {
    sessionStorage.removeItem(AUTH_RETURN_PATH_KEY);
  }
  return safePath;
}

export function clearAuthReturnPath() {
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem(AUTH_RETURN_PATH_KEY);
  }
}

export function consumeAuthReturnPath(preferredPath) {
  const preferred = sanitizeAuthReturnPath(preferredPath);
  const stored = typeof sessionStorage === 'undefined'
    ? null
    : sanitizeAuthReturnPath(sessionStorage.getItem(AUTH_RETURN_PATH_KEY));

  clearAuthReturnPath();
  return preferred || stored || DEFAULT_AUTHENTICATED_PATH;
}
