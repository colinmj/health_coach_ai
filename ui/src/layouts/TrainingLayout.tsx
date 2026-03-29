import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'

const TRAINING_SUB_NAV = [
  { to: '/training/overview', label: 'Overview' },
  { to: '/training/form-analyzer', label: 'Form Analyzer' },
  { to: '/training/workout-builder', label: 'Workout Builder' },
  { to: '/training/goal-physique', label: 'Goal Physique' },
  { to: '/training/progress-photos', label: 'Progress Photos' },
]

export function TrainingLayout() {
  return (
    <div className="flex flex-col h-full">
      <nav className="flex items-center gap-1 border-b px-4 py-2 shrink-0 overflow-x-auto">
        {TRAINING_SUB_NAV.map(({ to, label }) => (
          <NavLink
            key={to}
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
        ))}
      </nav>
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
