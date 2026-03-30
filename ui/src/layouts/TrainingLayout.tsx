import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { getProfile } from '@/lib/api'

const TRAINING_SUB_NAV = [
  { to: '/training/overview', label: 'Overview' },
  { to: '/training/form-analyzer', label: 'Form Analyzer' },
  { to: '/training/workout-builder', label: 'Workout Builder' },
  { to: '/training/goal-physique', label: 'Goal Physique' },
  { to: '/training/progress-photos', label: 'Progress Photos' },
]

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'rounded-md px-3 py-1.5 text-sm transition-colors whitespace-nowrap',
          isActive
            ? 'bg-muted text-foreground font-medium'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )
      }
    >
      {label}
    </NavLink>
  )
}

export function TrainingLayout() {
  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
  })

  const isManualWorkoutSource =
    (profile as Record<string, unknown> | undefined)?.workout_source === 'manual'

  return (
    <div className="flex flex-col h-full">
      <nav className="flex items-center gap-1 border-b px-4 py-2 shrink-0 overflow-x-auto">
        {TRAINING_SUB_NAV.map(({ to, label }) => (
          <NavItem key={to} to={to} label={label} />
        ))}
        {isManualWorkoutSource && (
          <NavItem to="/training/manual-log" label="Log Workout" />
        )}
      </nav>
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
