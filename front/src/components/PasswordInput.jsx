import React, { forwardRef, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

const PasswordInput = forwardRef(function PasswordInput(
  {
    className = '',
    disabled = false,
    showLabel = '비밀번호 보기',
    hideLabel = '비밀번호 숨기기',
    ...inputProps
  },
  ref,
) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div className="relative w-full">
      <input
        {...inputProps}
        ref={ref}
        type={isVisible ? 'text' : 'password'}
        disabled={disabled}
        className={`${className} pr-12`}
      />
      <button
        type="button"
        onClick={() => setIsVisible((visible) => !visible)}
        className="absolute right-1 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full text-mute transition-colors hover:bg-surface-soft hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/30 disabled:pointer-events-none disabled:opacity-50"
        aria-label={isVisible ? hideLabel : showLabel}
        aria-pressed={isVisible}
        title={isVisible ? hideLabel : showLabel}
        disabled={disabled}
      >
        {isVisible ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
      </button>
    </div>
  );
});

export default PasswordInput;
