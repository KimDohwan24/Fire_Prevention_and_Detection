import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  authApi,
  clearStoredSession,
  getAccessToken,
  getCurrentUserFromStorage,
  normalizeAuthenticatedUser,
  setCurrentUserToStorage,
  subscribeToUnauthorized,
} from '../api';
import { clearAuthReturnPath } from '../utils/authRouting';
import { AUTH_STATUS, AuthContext } from './authState';

const isAuthenticationRejection = (error) => error?.status === 401 || error?.status === 403;

const hasOAuthCallback = () => {
  if (typeof window === 'undefined' || !window.location.hash) return false;
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  return params.has('access_token') || params.has('oauth_error');
};

function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState(AUTH_STATUS.CHECKING);
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const initializationStartedRef = useRef(false);
  const operationIdRef = useRef(0);
  const isLoggingOutRef = useRef(false);

  const setAuthenticatedSession = useCallback((nextUser) => {
    setCurrentUserToStorage(nextUser);
    setUser(nextUser);
    setError(null);
    setStatus(AUTH_STATUS.AUTHENTICATED);
    return nextUser;
  }, []);

  const verifySession = useCallback(async ({ blockUi = false } = {}) => {
    const operationId = ++operationIdRef.current;
    const accessToken = getAccessToken();

    if (!accessToken) {
      clearStoredSession();
      if (operationId === operationIdRef.current) {
        setUser(null);
        setError(null);
        setStatus(AUTH_STATUS.UNAUTHENTICATED);
      }
      return null;
    }

    if (blockUi) {
      setError(null);
      setStatus(AUTH_STATUS.CHECKING);
    }

    try {
      const response = await authApi.me();
      const storedUser = getCurrentUserFromStorage();
      const verifiedUser = normalizeAuthenticatedUser(
        response?.user || response,
        storedUser,
        storedUser?.authProvider,
      );

      if (operationId !== operationIdRef.current) return verifiedUser;
      return setAuthenticatedSession(verifiedUser);
    } catch (sessionError) {
      if (operationId !== operationIdRef.current) return null;

      if (isAuthenticationRejection(sessionError)) {
        clearStoredSession();
        setUser(null);
        setError(null);
        setStatus(AUTH_STATUS.UNAUTHENTICATED);
        return null;
      }

      if (blockUi) {
        setError(sessionError);
        setStatus(AUTH_STATUS.ERROR);
      }
      throw sessionError;
    }
  }, [setAuthenticatedSession]);

  const refreshSession = useCallback(() => verifySession({ blockUi: false }), [verifySession]);

  const retrySession = useCallback(() => (
    verifySession({ blockUi: true }).catch(() => null)
  ), [verifySession]);

  const login = useCallback(async (userId, password) => {
    const operationId = ++operationIdRef.current;
    const response = await authApi.login(userId, password);
    let signedInUser = response?.user || getCurrentUserFromStorage();

    if (!signedInUser) {
      throw new Error('로그인 사용자 정보를 확인하지 못했습니다.');
    }

    try {
      const sessionResponse = await authApi.me();
      signedInUser = normalizeAuthenticatedUser(
        sessionResponse?.user || sessionResponse,
        signedInUser,
        signedInUser.authProvider,
      );
    } catch (sessionError) {
      if (isAuthenticationRejection(sessionError)) throw sessionError;
      console.warn('로그인 사용자 상세 정보를 불러오지 못해 기본 정보로 시작합니다.', sessionError);
    }

    if (operationId !== operationIdRef.current) return signedInUser;
    return setAuthenticatedSession(signedInUser);
  }, [setAuthenticatedSession]);

  const completeOAuthLogin = useCallback(() => {
    const completion = authApi.completeOAuthLogin();
    if (!completion) return null;

    const operationId = ++operationIdRef.current;
    return completion
      .then((result) => {
        if (operationId !== operationIdRef.current) return result;
        setAuthenticatedSession(result.user);
        return result;
      })
      .catch((oauthError) => {
        if (operationId === operationIdRef.current) {
          clearStoredSession();
          setUser(null);
          setError(null);
          setStatus(AUTH_STATUS.UNAUTHENTICATED);
        }
        throw oauthError;
      });
  }, [setAuthenticatedSession]);

  const logout = useCallback(async () => {
    ++operationIdRef.current;
    isLoggingOutRef.current = true;

    try {
      await authApi.logout();
    } finally {
      clearStoredSession();
      clearAuthReturnPath();
      setUser(null);
      setError(null);
      setStatus(AUTH_STATUS.UNAUTHENTICATED);
      navigate('/', { replace: true });
      isLoggingOutRef.current = false;
    }
  }, [navigate]);

  useEffect(() => subscribeToUnauthorized(() => {
    if (isLoggingOutRef.current) return;
    ++operationIdRef.current;
    setUser(null);
    setError(null);
    setStatus(AUTH_STATUS.UNAUTHENTICATED);
  }), []);

  useEffect(() => {
    if (initializationStartedRef.current) return;
    initializationStartedRef.current = true;

    if (hasOAuthCallback()) {
      setUser(null);
      setError(null);
      setStatus(AUTH_STATUS.UNAUTHENTICATED);
      return;
    }

    verifySession({ blockUi: true }).catch(() => null);
  }, [verifySession]);

  const value = useMemo(() => ({
    completeOAuthLogin,
    error,
    login,
    logout,
    refreshSession,
    retrySession,
    status,
    user,
  }), [
    completeOAuthLogin,
    error,
    login,
    logout,
    refreshSession,
    retrySession,
    status,
    user,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default AuthProvider;
