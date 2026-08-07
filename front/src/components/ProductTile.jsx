import React from 'react';

/**
 * ProductTile component based on the Apple Design System.
 * 
 * Variants:
 * - light: White background.
 * - parchment: Off-white parchment background.
 * - dark: Dark tile 1 (#272729).
 * - dark-2: Dark tile 2 (micro-step lighter).
 * - dark-3: Dark tile 3 (micro-step darker).
 */
export const ProductTile = ({
  variant = 'light',
  headline,
  tagline,
  children,
  className = '',
}) => {
  let bgClass = '';
  let textClass = 'text-ink';
  
  switch (variant) {
    case 'light':
      bgClass = 'bg-canvas';
      break;
    case 'parchment':
      bgClass = 'bg-canvas-parchment';
      break;
    case 'dark':
      bgClass = 'bg-surface-tile-1';
      textClass = 'text-on-dark';
      break;
    case 'dark-2':
      bgClass = 'bg-surface-tile-2';
      textClass = 'text-on-dark';
      break;
    case 'dark-3':
      bgClass = 'bg-surface-tile-3';
      textClass = 'text-on-dark';
      break;
    default:
      bgClass = 'bg-canvas';
  }

  return (
    <section className={`w-full py-section rounded-none flex flex-col items-center text-center overflow-hidden relative ${bgClass} ${textClass} ${className}`}>
      {headline && (
        <h2 className="font-display text-display-lg font-display-lg whitespace-pre-line px-4 z-10">
          {headline}
        </h2>
      )}
      {tagline && (
        <p className="font-display text-lead font-lead mt-2 px-4 z-10 max-w-2xl">
          {tagline}
        </p>
      )}
      
      <div className="z-10 mt-4 flex items-center justify-center gap-sm">
        {children}
      </div>
    </section>
  );
};

/**
 * Product Image wrapper for applying the signature shadow and spacing.
 */
export const ProductImage = ({ src, alt, className = '' }) => {
  return (
    <div className={`mt-10 w-full max-w-5xl px-4 flex justify-center z-0 ${className}`}>
      <img 
        src={src} 
        alt={alt} 
        style={{ boxShadow: 'var(--shadow-product)' }}
        className="max-w-full h-auto object-contain"
      />
    </div>
  );
};
