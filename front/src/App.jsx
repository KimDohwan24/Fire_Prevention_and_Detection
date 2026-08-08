import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import DarkModeToggle from './components/DarkModeToggle';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/signup" element={<Signup />} />
        {/* Placeholder for other routes */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <DarkModeToggle />
    </BrowserRouter>
  );
}

export default App;
