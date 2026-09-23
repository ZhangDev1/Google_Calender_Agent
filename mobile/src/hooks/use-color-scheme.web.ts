import { useEffect, useState } from 'react';

import { useThemePreference } from '@/context/theme-preference';

/**
 * Web needs an extra guard: on first render (before the client hydrates),
 * we can't safely read any client-only state, so we return 'light' to
 * match static/server-rendered output and avoid a hydration mismatch.
 * After hydration, this defers to the same toggle-aware scheme as native.
 */
export function useColorScheme() {
  const [hasHydrated, setHasHydrated] = useState(false);

  useEffect(() => {
    setHasHydrated(true);
  }, []);

  const { scheme } = useThemePreference();

  if (hasHydrated) {
    return scheme;
  }

  return 'light';
}
