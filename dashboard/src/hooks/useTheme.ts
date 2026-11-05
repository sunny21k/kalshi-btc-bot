import React from 'react';

export function useTheme() {
  const [theme, setTheme] = React.useState(() => localStorage.getItem('dashboard-theme') ?? 'dark');

  React.useEffect(() => {
    localStorage.setItem('dashboard-theme', theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggleTheme = React.useCallback(() => {
    setTheme((current) => current === 'dark' ? 'light' : 'dark');
  }, []);

  return { theme, toggleTheme };
}
