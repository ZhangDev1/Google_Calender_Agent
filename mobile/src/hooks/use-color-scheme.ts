import { useThemePreference } from '@/context/theme-preference';

/**
 * The app-wide color scheme, honoring the user's toggle (from
 * ThemePreferenceProvider) instead of the raw OS setting. Anything that
 * needs to know "light or dark" should call this, not react-native's
 * own useColorScheme, so it stays in sync with the toggle.
 */
export function useColorScheme() {
  return useThemePreference().scheme;
}
