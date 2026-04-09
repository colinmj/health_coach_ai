import { useEffect, useRef } from 'react'
import { Outlet } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { TopNav } from '@/components/nav/TopNav'
import { getProfile, getSyncStatus, triggerSync } from '@/lib/api'

export function AppLayout() {
  // Prime the profile cache for all authenticated routes (e.g. StarterPrompts greeting)
  useQuery({ queryKey: ['profile'], queryFn: getProfile })

  const queryClient = useQueryClient()
  const { data: integrations } = useQuery({ queryKey: ['sync-status'], queryFn: getSyncStatus })
  const hasSynced = useRef(false)

  useEffect(() => {
    if (hasSynced.current || !integrations) return

    const syncSources = integrations.filter(
      (i) => i.auth_type !== 'upload' && i.authorized && i.is_active
    )
    if (syncSources.length === 0) return

    const syncedAt = localStorage.getItem('syncedAt')
    const stale = !syncedAt || Date.now() - Number(syncedAt) > 24 * 60 * 60 * 1000
    if (!stale) return

    hasSynced.current = true
    triggerSync()
      .then(() => {
        localStorage.setItem('syncedAt', Date.now().toString())
        queryClient.invalidateQueries({ queryKey: ['sync-status'] })
      })
      .catch(() => {
        hasSynced.current = false
      })
  }, [integrations, queryClient])

  return (
    <div className="flex flex-col h-screen">
      <TopNav />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
