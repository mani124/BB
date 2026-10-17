import React, { useRef } from 'react';

export interface TabItem<T extends string> {
  id: T;
  label: React.ReactNode;
  /** Plain-text name for screen readers when `label` has extra badges. */
  name?: string;
}

/** WAI-ARIA tablist: roving tabindex, arrow keys, Home/End. */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  className,
  tabClassName,
  idPrefix,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  className?: string;
  tabClassName: string;
  /** Tab ids become `${idPrefix}-tab-${id}`; panels should use aria-labelledby with that id. */
  idPrefix: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const move = (to: number) => {
    const next = items[(to + items.length) % items.length];
    onChange(next.id);
    refs.current[next.id]?.focus();
  };
  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); move(index + 1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); move(index - 1); }
    else if (e.key === 'Home') { e.preventDefault(); move(0); }
    else if (e.key === 'End') { e.preventDefault(); move(items.length - 1); }
  };
  return (
    <div role="tablist" aria-label={label} className={className}>
      {items.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => { refs.current[t.id] = el; }}
          id={`${idPrefix}-tab-${t.id}`}
          type="button"
          role="tab"
          aria-selected={value === t.id}
          aria-controls={`${idPrefix}-panel`}
          aria-label={t.name}
          tabIndex={value === t.id ? 0 : -1}
          className={tabClassName}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKeyDown(e, i)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
