import { createContext, useContext, useState, type ReactNode } from 'react';
import { useColorScheme as useSystemColorScheme } from 'react-native';

export type Scheme = 'light' | 'dark';
export type Preference = Scheme | 'system';

type ThemePreferenceContextValue = {
  scheme: Scheme;            // the RESOLVED scheme to actually render with
  preference: Preference;    // what the user picked ('system' means "follow OS")
  toggle: () => void;        // flips light <-> dark
};

const ThemePreferenceContext = createContext<ThemePreferenceContextValue | null>(null);

export function ThemePreferenceProvider({ children }: { children: ReactNode }) {
  const systemScheme: Scheme = useSystemColorScheme() === 'dark' ? 'dark' : 'light';
  const [preference, setPreference] = useState<Preference>('system');

  const scheme: Scheme = preference === 'system' ? systemScheme : preference;

  const toggle = () => setPreference(scheme === 'dark' ? 'light' : 'dark');

  return (
    <ThemePreferenceContext.Provider value={{ scheme, preference, toggle }}>
      {children}
    </ThemePreferenceContext.Provider>
  );
}

export function useThemePreference() {
  const ctx = useContext(ThemePreferenceContext);
  if (!ctx) {
    throw new Error('useThemePreference must be used within a ThemePreferenceProvider');
  }
  return ctx;
}
