import { useEffect, useState } from 'react';

/** True at 1024 px and wider; follows window resizes. */
export function useDesktopMedia(): boolean {
  const query = '(min-width: 1024px)';
  const [matches, setMatches] = useState(() => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : true));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return matches;
}
