import { StrictMode, useEffect, useLayoutEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Outlet, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ClerkProvider, RedirectToSignIn, SignedIn, SignedOut, useAuth } from '@clerk/clerk-react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppLayout } from './layouts/AppLayout'
import { ChatPage } from './pages/ChatPage'
import { GoalsPage } from './pages/GoalsPage'
import { GoalDetailPage } from './pages/GoalDetailPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { SettingsPage } from './pages/SettingsPage'
import { FormCheckPage } from './pages/FormCheckPage'
import { WorkoutBuilderPage } from './pages/WorkoutBuilderPage'
import { ManualWorkoutPage } from './pages/ManualWorkoutPage'
import { TrainingLayout } from './layouts/TrainingLayout'
import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'
import { setClerkTokenGetter } from './lib/api'
import './index.css'

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
})

/** Wires Clerk's getToken into the api.ts module so all fetches attach a valid JWT. */
function ClerkTokenBridge() {
  const { getToken } = useAuth()
  useLayoutEffect(() => {
    setClerkTokenGetter(() => getToken())
  }, [getToken])
  return null
}

function ThemeSync() {
  const isDark = useThemeStore((s) => s.isDark)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark)
  }, [isDark])
  return null
}

/** Resets onboardingComplete whenever a different Clerk user signs in. */
function ClerkUserSync() {
  const { userId } = useAuth()
  const setClerkUser = useAuthStore((s) => s.setClerkUser)
  useEffect(() => {
    if (userId) setClerkUser(userId)
  }, [userId, setClerkUser])
  return null
}

function RequireOnboarding() {
  const onboardingComplete = useAuthStore((s) => s.onboardingComplete)
  if (!onboardingComplete) return <Navigate to="/onboarding" replace />
  return <Outlet />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={clerkPublishableKey}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <BrowserRouter>
            <ClerkTokenBridge />
            <ClerkUserSync />
            <ThemeSync />
            <Routes>
              {/* Signed-out users are redirected to Clerk's hosted sign-in page */}
              <Route
                path="*"
                element={
                  <>
                    <SignedOut>
                      <RedirectToSignIn />
                    </SignedOut>
                    <SignedIn>
                      <Routes>
                        <Route path="/onboarding" element={<OnboardingPage />} />
                        <Route element={<RequireOnboarding />}>
                          <Route element={<AppLayout />}>
                            <Route path="/" element={<ChatPage />} />
                            <Route path="/goals" element={<GoalsPage />} />
                            <Route path="/goals/:id" element={<GoalDetailPage />} />
                            <Route path="/settings" element={<SettingsPage />} />
                            <Route path="/form-check" element={<FormCheckPage />} />
                            <Route path="/training" element={<TrainingLayout />}>
                              <Route index element={<Navigate to="/training/form-analyzer" replace />} />
                              <Route path="form-analyzer" element={<FormCheckPage />} />
                              <Route path="workout-builder" element={<WorkoutBuilderPage />} />
                              <Route path="manual-log" element={<ManualWorkoutPage />} />
                            </Route>
                          </Route>
                        </Route>
                      </Routes>
                    </SignedIn>
                  </>
                }
              />
            </Routes>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>,
)
