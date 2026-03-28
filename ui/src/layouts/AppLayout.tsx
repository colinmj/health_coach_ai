import { Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { TopNav } from '@/components/nav/TopNav'
import { getProfile } from '@/lib/api'

export function AppLayout() {
  // Prime the profile cache for all authenticated routes (e.g. StarterPrompts greeting)
  useQuery({ queryKey: ['profile'], queryFn: getProfile })

  return (
    <div className="flex flex-col h-screen">
      <TopNav />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
