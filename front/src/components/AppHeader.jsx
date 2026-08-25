import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  LayoutDashboard,
  LogOut,
  MapPin,
  Settings,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import { isSuperAdminUser } from '../api';

const NAV_ITEMS = [
  { key: 'dashboard', label: '대시보드', path: '/dashboard', icon: LayoutDashboard },
  { key: 'monitoring', label: '실시간 관제', path: '/monitoring', icon: MapPin },
  { key: 'mypage', label: '마이페이지', path: '/mypage', icon: UserRound },
  { key: 'admin', label: '관리자', path: '/admin', icon: Settings, adminOnly: true },
];

export default function AppHeader({ currentPage, currentUser, onLogout }) {
  const navigate = useNavigate();
  const isSuperAdmin = isSuperAdminUser(currentUser);
  const isAdmin = isSuperAdmin || currentUser?.role === 'admin' || currentUser?.rawRole === 'ADMIN';
  const visibleItems = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  return (
    <header className="sticky top-0 z-40 h-14 shrink-0 border-b border-hairline bg-canvas">
      <div className="w-full h-full px-3 sm:px-6 flex items-center justify-between gap-2 sm:gap-4">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0 shrink-0">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="h-9 flex cursor-pointer items-center gap-2 text-ink focus:outline-none focus-visible:outline-none"
            aria-label="FireGuard 대시보드로 이동"
          >
            <AlertTriangle className="w-5 h-5 shrink-0" />
            <span className="hidden sm:inline font-display text-heading-md tracking-tight">FireGuard</span>
          </button>

          <span className="hidden md:inline-flex items-center h-7 px-2.5 rounded-full border border-hairline bg-surface-soft text-[11px] font-semibold text-body whitespace-nowrap">
            {isSuperAdmin
              ? <><ShieldCheck className="w-3.5 h-3.5 mr-1" />최고 관리자</>
              : isAdmin
                ? <><ShieldCheck className="w-3.5 h-3.5 mr-1" />관리자 권한</>
                : '일반 관제회원'}
          </span>
        </div>

        <nav className="flex items-center justify-center gap-1 sm:gap-1.5 min-w-0" aria-label="주요 메뉴">
          {visibleItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPage === item.key;

            return (
              <button
                key={item.key}
                type="button"
                onClick={() => navigate(item.path)}
                aria-current={isActive ? 'page' : undefined}
                aria-label={item.label}
                title={item.label}
                className={`h-9 cursor-pointer px-2.5 lg:px-3.5 rounded-full flex items-center justify-center gap-1.5 border text-caption-sm font-semibold whitespace-nowrap focus:outline-none focus-visible:outline-none ${
                  isActive
                    ? 'border-hairline-strong bg-surface-soft text-ink'
                    : 'border-transparent bg-canvas text-body hover:text-ink hover:border-hairline'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="hidden lg:inline">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <span className="hidden 2xl:inline-flex text-caption-sm font-semibold text-body whitespace-nowrap">
            {currentUser?.name ? `${currentUser.name.replace(/\s*님$/, '')}님` : '사용자'}
          </span>
          <button
            type="button"
            onClick={onLogout}
            className="h-9 cursor-pointer px-2.5 sm:px-4 rounded-full bg-primary text-on-primary text-caption-sm font-semibold flex items-center gap-1.5 focus:outline-none focus-visible:outline-none"
            aria-label="로그아웃"
            title="로그아웃"
          >
            <LogOut className="w-3.5 h-3.5 shrink-0" />
            <span className="hidden sm:inline">로그아웃</span>
          </button>
        </div>
      </div>
    </header>
  );
}
