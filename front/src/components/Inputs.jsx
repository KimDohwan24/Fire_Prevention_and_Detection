import React from 'react';

export const InstallSnippet = ({ command }) => {
  return (
    <div className="bg-surface-soft rounded-full px-[20px] py-[12px] h-[48px] flex items-center justify-between w-full max-w-xl mx-auto border border-transparent hover:border-hairline transition-colors">
      <code className="font-mono text-code-md font-code-md text-ink truncate mr-4">
        {command}
      </code>
      <button className="text-mute hover:text-ink transition-colors p-1 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring">
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
      </button>
    </div>
  );
};

export const CommandTag = ({ children }) => {
  return (
    <span className="bg-surface-soft text-ink font-mono text-code-sm font-code-sm rounded-full px-[12px] py-[6px] inline-flex items-center">
      {children}
    </span>
  );
};
