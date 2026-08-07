import React from 'react';

/**
 * Button component based on the Ollama Design System.
 * 
 * Variants:
 * - primary: Black pill.
 * - secondary: Outline alternative on light canvas.
 * - pill-on-dark: White pill on dark surface (e.g. for 'Max' plan).
 * - disabled: Flat soft gray.
 */
export const Button = ({ 
  children, 
  variant = 'primary', 
  className = '', 
  href,
  disabled,
  ...props 
}) => {
  let baseClass = 'inline-flex items-center justify-center cursor-pointer focus:outline-none';
  let variantClass = '';

  if (disabled) {
    variant = 'disabled';
  }

  switch (variant) {
    case 'primary':
      variantClass = 'bg-primary text-on-primary font-ui text-button-md font-button-md rounded-full px-[20px] py-[8px] h-[36px] hover:bg-ink-deep active:bg-ink-deep';
      break;
    case 'secondary':
      variantClass = 'bg-canvas text-ink font-ui text-button-md font-button-md border border-hairline-strong rounded-full px-[20px] py-[8px] h-[36px] hover:bg-surface-soft';
      break;
    case 'pill-on-dark':
      variantClass = 'bg-canvas text-ink font-ui text-button-md font-button-md rounded-full px-[20px] py-[8px] hover:bg-surface-soft';
      break;
    case 'disabled':
      baseClass = 'inline-flex items-center justify-center cursor-not-allowed';
      variantClass = 'bg-surface-soft text-mute font-ui text-button-md font-button-md rounded-full px-[20px] py-[8px] h-[36px]';
      break;
    default:
      variantClass = 'bg-primary text-on-primary font-ui text-button-md font-button-md rounded-full px-[20px] py-[8px] h-[36px]';
  }

  const combinedClasses = `${baseClass} ${variantClass} ${className}`.trim();

  if (href && !disabled) {
    return (
      <a href={href} className={combinedClasses} {...props}>
        {children}
      </a>
    );
  }

  return (
    <button className={combinedClasses} disabled={disabled} {...props}>
      {children}
    </button>
  );
};
