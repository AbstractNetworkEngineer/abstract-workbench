import React, { createContext, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext({ dark: true, mode: 'dark', setMode: () => {}, toggle: () => {} });

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => {
    return localStorage.getItem('netdeck_theme') === 'light' ? 'light' : 'dark';
  });
  const dark = mode === 'dark';

  useEffect(() => {
    localStorage.setItem('netdeck_theme', mode);
    document.documentElement.style.colorScheme = mode;
  }, [mode]);

  const toggle = () => setMode((m) => (m === 'dark' ? 'light' : 'dark'));

  return (
    <ThemeContext.Provider value={{ dark, mode, setMode, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
