import React from 'react';
import { LoaderCircle, RefreshCw, ShieldAlert } from 'lucide-react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { AUTH_STATUS, useAuth } from '../../context/authState';
import {
  createAuthReturnPath,
  hasAllowedRole,
} from '../../utils/authRouting';

function SessionGateScreen({ error, onRetry }) {
  const isError = Boolean(error);

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-4 font-ui text-ink">
      <section className="w-full max-w-sm rounded-xl border border-hairline bg-canvas p-6 text-center">
        <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-surface-soft text-ink">
          {isError ? <ShieldAlert className="h-5 w-5" /> : <LoaderCircle className="h-5 w-5 animate-spin" />}
        </span>
        <h1 className="mt-4 text-heading-sm font-semibold">
          {isError ? '로그인 상태를 확인하지 못했습니다.' : '로그인 상태를 확인하고 있습니다.'}
        </h1>
        <p className="mt-2 text-body-sm text-body">
          {isError
            ? error.message || '서버 연결을 확인한 뒤 다시 시도해주세요.'
            : '잠시만 기다려주세요.'}
        </p>
        {isError && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-5 inline-flex h-9 items-center gap-2 rounded-full bg-primary px-4 text-caption-sm font-semibold text-on-primary hover:bg-ink-deep focus:outline-none focus-visible:outline-none"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            다시 확인
          </button>
        )}
      </section>
    </main>
  );
}

export default function ProtectedRoute({ allowedRoles = [] }) {
  const location = useLocation();
  const {
    error,
    retrySession,
    status,
    user,
  } = useAuth();

  if (status === AUTH_STATUS.CHECKING) {
    return <SessionGateScreen />;
  }

  if (status === AUTH_STATUS.ERROR) {
    return <SessionGateScreen error={error} onRetry={retrySession} />;
  }

  if (status !== AUTH_STATUS.AUTHENTICATED || !user) {
    return (
      <Navigate
        to="/"
        replace
        state={{ from: createAuthReturnPath(location) }}
      />
    );
  }

  if (!hasAllowedRole(user, allowedRoles)) {
    return <Navigate to="/dashboard" replace state={{ accessDenied: true }} />;
  }

  return <Outlet />;
}
