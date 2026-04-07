import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

import { getProfiles } from '@/api/settings';
import { hostedMode } from '@/lib/supabase';

const STORAGE_KEY = 'launchboard-profile';
const HOSTED_PROFILE = 'workspace';

interface ProfileContextValue {
  profile: string;
  setProfile: (p: string) => void;
}

const ProfileContext = createContext<ProfileContextValue>({
  profile: 'default',
  setProfile: () => {},
});

function getStoredProfile(): string {
  if (hostedMode) return HOSTED_PROFILE;
  try {
    return localStorage.getItem(STORAGE_KEY) || 'default';
  } catch {
    return 'default';
  }
}

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfileState] = useState(getStoredProfile);
  const effectiveProfile = hostedMode ? HOSTED_PROFILE : profile;

  const setProfile = useCallback((p: string) => {
    if (hostedMode) {
      return;
    }
    setProfileState(p);
    try {
      localStorage.setItem(STORAGE_KEY, p);
    } catch {
      // localStorage unavailable — state still works
    }
  }, []);

  useEffect(() => {
    if (hostedMode) return;
    let active = true;

    async function validateStoredProfile() {
      try {
        const profiles = await getProfiles();
        if (!active) return;
        if (profile === 'default') return;

        const exists = profiles.some((item) => item.name === profile);
        if (exists) return;

        setProfileState('default');
        try {
          localStorage.setItem(STORAGE_KEY, 'default');
        } catch {
          // localStorage unavailable — in-memory state still resets
        }
      } catch {
        // Keep the existing profile if the backend is unavailable.
      }
    }

    void validateStoredProfile();
    return () => {
      active = false;
    };
  }, [profile]);

  return (
    <ProfileContext.Provider value={{ profile: effectiveProfile, setProfile }}>
      {children}
    </ProfileContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProfile() {
  return useContext(ProfileContext);
}
