import React from 'react';
import { Button } from './Button';

export const TerminalCard = ({ children, className = '' }) => {
  return (
    <div className={`bg-canvas border border-hairline rounded-lg p-[16px] shadow-sm w-full font-mono text-code-sm font-code-sm text-ink ${className}`}>
      <div className="flex items-center gap-[4px] mb-[12px]">
        <div className="w-[12px] h-[12px] rounded-full bg-terminal-red"></div>
        <div className="w-[12px] h-[12px] rounded-full bg-terminal-yellow"></div>
        <div className="w-[12px] h-[12px] rounded-full bg-terminal-green"></div>
      </div>
      <div className="overflow-x-auto">
        <pre className="whitespace-pre-wrap">{children}</pre>
      </div>
    </div>
  );
};

export const PricingCard = ({ 
  title, 
  price, 
  description, 
  features = [], 
  dark = false, 
  buttonLabel = "Get Started" 
}) => {
  const containerClass = dark 
    ? "bg-surface-dark text-on-dark border border-transparent rounded-lg p-[32px] w-full"
    : "bg-canvas text-ink border border-hairline rounded-lg p-[32px] w-full";

  const btnVariant = dark ? "pill-on-dark" : "primary";

  return (
    <div className={containerClass}>
      <div className="mb-[16px]">
        {/* Placeholder for mascot in card */}
        <span className="text-[32px]">🦙</span>
      </div>
      <h3 className="font-ui text-heading-md font-heading-md mb-[8px]">{title}</h3>
      <p className={`font-ui text-body-sm mb-[24px] ${dark ? 'text-on-dark-mute' : 'text-body'}`}>{description}</p>
      <div className="font-display text-display-lg font-display-lg mb-[24px]">{price}</div>
      <Button variant={btnVariant} className="w-full mb-[32px]">{buttonLabel}</Button>
      
      <div className="border-t border-hairline pt-[24px]">
        <h4 className="font-ui text-body-sm-strong font-body-sm-strong mb-[16px]">Everything in {title === 'Max' ? 'Pro' : 'Free'}, plus:</h4>
        <ul className="space-y-[8px]">
          {features.map((feature, idx) => (
            <li key={idx} className="flex items-start gap-[8px] font-ui text-body-sm font-body-sm text-charcoal">
              <span className={dark ? "text-on-dark" : "text-ink"}>✓</span>
              <span className={dark ? "text-on-dark-mute" : "text-charcoal"}>{feature}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
