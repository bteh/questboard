import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

const STORAGE_KEY = 'launchboard-profile';

interface ProfileContextValue {
  profile: string;
  setProfile: (p: string) => void;
}

const ProfileContext = createContext<ProfileContextValue>({
  profile: 'default',
  setProfile: () => {},
});

function getStoredProfile(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || 'default';
  } catch {
    return 'default';
  }
}

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfileState] = useState(getStoredProfile);

  const setProfile = useCallback((p: string) => {
    setProfileState(p);
    try {
      localStorage.setItem(STORAGE_KEY, p);
    } catch {
      // localStorage unavailable — state still works
    }
  }, []);

  return (
    <ProfileContext.Provider value={{ profile, setProfile }}>
      {children}
    </ProfileContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProfile() {
  return useContext(ProfileContext);
}
