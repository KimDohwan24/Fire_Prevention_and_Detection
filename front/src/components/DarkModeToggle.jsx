import React, { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';

const DarkModeToggle = () => {
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('theme');
    if (saved !== null) {
      return saved === 'dark';
    }
    return false;
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }

    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  return (
    <button
      type="button"
      onClick={() => setIsDark(!isDark)}
      className="fixed bottom-8 right-8 p-3 rounded-full border border-hairline bg-canvas text-ink hover:bg-surface-soft transition-colors shadow-lg flex items-center justify-center cursor-pointer z-50 focus:outline-none focus-visible:outline-none"
      aria-label="테마 전환 (다크/라이트 모드)"
      title={isDark ? '라이트 모드로 전환' : '다크 모드로 전환'}
    >
      {isDark ? <Sun className="w-5 h-5 text-amber-400" /> : <Moon className="w-5 h-5 text-charcoal" />}
    </button>
  );
};

export default DarkModeToggle;
