import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  clerkUserId: string | null
  onboardingComplete: boolean
  setClerkUser: (id: string) => void
  completeOnboarding: () => void
  resetOnboarding: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      clerkUserId: null,
      onboardingComplete: false,
      setClerkUser: (id) => set((s) => ({
        clerkUserId: id,
        onboardingComplete: s.clerkUserId === id ? s.onboardingComplete : false,
      })),
      completeOnboarding: () => set({ onboardingComplete: true }),
      resetOnboarding: () => set({ onboardingComplete: false }),
    }),
    { name: 'auth' },
  ),
)
