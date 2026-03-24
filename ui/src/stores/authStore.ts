import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  userId: number | null
  onboardingComplete: boolean
  setAuth: (token: string, userId: number) => void
  completeOnboarding: () => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      userId: null,
      onboardingComplete: false,
      setAuth: (token, userId) => set({ token, userId }),
      completeOnboarding: () => set({ onboardingComplete: true }),
      logout: () => set({ token: null, userId: null, onboardingComplete: false }),
    }),
    { name: 'auth' },
  ),
)
