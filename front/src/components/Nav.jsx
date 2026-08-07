import React from 'react';
import { Button } from './Button';

/**
 * PrimaryNav component based on the Ollama Design System.
 */
export const PrimaryNav = ({ links = [] }) => {
  return (
    <nav className="w-full bg-canvas text-ink h-[56px] px-4 md:px-8 flex items-center justify-between text-body-sm-strong font-body-sm-strong border-b border-hairline sticky top-0 z-50">
      <div className="flex items-center gap-6">
        <a href="/" className="flex items-center gap-2">
          {/* Llama Mascot Placeholder */}
          <span className="text-[24px]">🦙</span>
        </a>
        <div className="hidden md:flex items-center gap-4">
          {links.map((link, idx) => (
            <a key={idx} href={link.href} className="hover:text-charcoal transition-colors">
              {link.label}
            </a>
          ))}
        </div>
      </div>
      
      {/* Centered Search Pill */}
      <div className="hidden md:flex flex-1 max-w-[360px] mx-4">
        <div className="w-full bg-surface-soft text-ink font-ui text-body-sm h-[36px] rounded-full px-4 flex items-center cursor-text border border-transparent focus-within:bg-canvas focus-within:border-hairline transition-colors">
          <svg className="w-4 h-4 mr-2 text-mute" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
          <input type="text" placeholder="Search models" className="bg-transparent outline-none w-full placeholder-mute" />
        </div>
      </div>

      <div className="hidden md:flex items-center gap-4">
        <a href="#" className="hover:text-charcoal transition-colors">Sign in</a>
        <Button variant="primary">Download</Button>
      </div>

      <div className="flex md:hidden items-center">
        <button className="p-2 text-ink">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
        </button>
      </div>
    </nav>
  );
};

export const FooterSection = () => {
  return (
    <footer className="w-full bg-canvas text-body font-ui text-caption-sm font-caption-sm px-6 py-[32px] border-t border-hairline text-center">
      <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 mb-4">
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">Download</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">Blog</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">Docs</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">GitHub</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">Discord</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">X</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">Contact</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">Privacy</a>
        <a href="#" className="hover:text-ink transition-colors underline decoration-transparent hover:decoration-ink">Terms</a>
      </div>
      <p>&copy; {new Date().getFullYear()} Ollama</p>
    </footer>
  );
};
