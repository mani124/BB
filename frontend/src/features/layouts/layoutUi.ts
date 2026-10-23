import { useEffect } from 'react';

export type LayoutAction = 'saveAs' | 'reset';
const EVENT = 'bb:layout-action';

/** Asks the workspace switcher to open one of its dialogs (used by the command palette). */
export function requestLayoutAction(action: LayoutAction): void {
  window.dispatchEvent(new CustomEvent<LayoutAction>(EVENT, { detail: action }));
}

export function useLayoutActionRequests(handler: (a: LayoutAction) => void): void {
  useEffect(() => {
    const on = (e: Event) => handler((e as CustomEvent<LayoutAction>).detail);
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, [handler]);
}
