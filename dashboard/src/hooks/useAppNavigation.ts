import React from 'react';
import { readAppLocation } from '../lib/navigation';

export function useAppNavigation() {
  const [location, setLocation] = React.useState(() => readAppLocation(typeof window === 'undefined' ? '/' : window.location.pathname));

  React.useEffect(() => {
    const onLocationChange = () => setLocation(readAppLocation(window.location.pathname));
    window.addEventListener('popstate', onLocationChange);
    return () => window.removeEventListener('popstate', onLocationChange);
  }, []);

  React.useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      if (location.page === 'bots' || location.section === 'overview') window.scrollTo({ top: 0 });
      else document.getElementById(`info/${location.section}`)?.scrollIntoView({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [location]);

  return location;
}
