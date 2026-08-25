import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import FindAccount from './pages/FindAccount';
import Dashboard from './pages/Dashboard';
import Monitoring from './pages/Monitoring';
import AdminPage from './pages/AdminPage';
import MyPage from './pages/MyPage';
import DarkModeToggle from './components/DarkModeToggle';
import ProtectedAppLayout from './components/auth/ProtectedAppLayout';
import ProtectedRoute from './components/auth/ProtectedRoute';
import AuthProvider from './context/AuthContext';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/forgot-password" element={<FindAccount />} />
          <Route path="/find-account" element={<FindAccount />} />
          <Route path="/find-id-pw" element={<FindAccount />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<ProtectedAppLayout />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/monitoring" element={<Monitoring />} />
              <Route path="/mypage" element={<MyPage />} />
              <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
                <Route path="/admin" element={<AdminPage />} />
              </Route>
            </Route>
          </Route>

          {/* Placeholder for other routes */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <DarkModeToggle />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
