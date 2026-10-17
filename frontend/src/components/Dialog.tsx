import React from 'react';
import { useDialog } from './useDialog';

/** Overlay + modal with dialog semantics, focus trap, Escape to close and focus return. */
export const Dialog: React.FC<{
  label: string;
  onClose: () => void;
  className?: string;
  style?: React.CSSProperties;
  /** Click on the dim backdrop closes the dialog (off for forms where typed text could be lost). */
  closeOnBackdrop?: boolean;
  children: React.ReactNode;
}> = ({ label, onClose, className = '', style, closeOnBackdrop = true, children }) => {
  const ref = useDialog<HTMLDivElement>(onClose);
  return (
    <div className="desk-overlay" onClick={closeOnBackdrop ? onClose : undefined}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className={`desk-modal ${className}`}
        style={style}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
};
