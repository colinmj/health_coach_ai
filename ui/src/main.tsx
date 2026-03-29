import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Outlet, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppLayout } from './layouts/AppLayout'
import { ChatPage } from './pages/ChatPage'
import { GoalsPage } from './pages/GoalsPage'
import { GoalDetailPage } from './pages/GoalDetailPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { SettingsPage } from './pages/SettingsPage'
import { FormCheckPage } from './pages/FormCheckPage'
import { TrainingOverviewPage } from './pages/TrainingOverviewPage'
import { WorkoutBuilderPage } from './pages/WorkoutBuilderPage'
import { GoalPhysiquePage } from './pages/GoalPhysiquePage'
import { ProgressPhotosPage } from './pages/ProgressPhotosPage'
import { TrainingLayout } from './layouts/TrainingLayout'
import { useAuthStore } from './stores/authStore'
import './index.css'

const queryClient = new QueryClient()

function RequireAuth() {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}

function RequireOnboarding() {
  const onboardingComplete = useAuthStore((s) => s.onboardingComplete)
  if (!onboardingComplete) return <Navigate to="/onboarding" replace />
  return <Outlet />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            {/* Auth-required routes */}
            <Route element={<RequireAuth />}>
              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route element={<RequireOnboarding />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<ChatPage />} />
                <Route path="/goals" element={<GoalsPage />} />
                <Route path="/goals/:id" element={<GoalDetailPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/form-check" element={<FormCheckPage />} />
                {/* Training section — sub-pages share the TrainingLayout sub-nav */}
                <Route path="/training" element={<TrainingLayout />}>
                  <Route index element={<Navigate to="/training/overview" replace />} />
                  <Route path="overview" element={<TrainingOverviewPage />} />
                  <Route path="form-analyzer" element={<FormCheckPage />} />
                  <Route path="workout-builder" element={<WorkoutBuilderPage />} />
                  <Route path="goal-physique" element={<GoalPhysiquePage />} />
                  <Route path="progress-photos" element={<ProgressPhotosPage />} />
                </Route>
              </Route>
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
)
