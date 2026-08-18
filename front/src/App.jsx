import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import FindAccount from './pages/FindAccount';
import Dashboard from './pages/Dashboard';
import Monitoring from './pages/Monitoring';
import AdminPage from './pages/AdminPage';
import MyPage from './pages/MyPage';
import OAuthCallback from './pages/OAuthCallback';
import DarkModeToggle from './components/DarkModeToggle';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/forgot-password" element={<FindAccount />} />
        <Route path="/find-account" element={<FindAccount />} />
        <Route path="/find-id-pw" element={<FindAccount />} />
        {/* 백엔드가 프로바이더에 넘기는 redirect URI 가 이 경로다 — 바꾸면 OAUTH_REDIRECT_BASE 도 같이 바꿔야 한다. */}
        <Route path="/oauth/callback/:provider" element={<OAuthCallback />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/mypage" element={<MyPage />} />
        {/* Placeholder for other routes */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <DarkModeToggle />
    </BrowserRouter>
  );
}

export default App;
