import { Outlet } from 'react-router-dom'
import { TopNav } from '@/components/nav/TopNav'

export function AppLayout() {
  return (
    <div className="flex flex-col h-screen">
      <TopNav />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
