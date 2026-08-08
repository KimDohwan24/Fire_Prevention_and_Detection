import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import FindAccount from './pages/FindAccount';
import Dashboard from './pages/Dashboard';
import AdminPage from './pages/AdminPage';
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
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/admin" element={<AdminPage />} />
        {/* Placeholder for other routes */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <DarkModeToggle />
    </BrowserRouter>
  );
}

export default App;
