import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getSyncStatus, triggerSync } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { RefreshCw, Upload } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { cn } from '@/lib/utils'
import type { SyncIntegration } from '@/types'

const SOURCE_LABELS: Record<string, string> = {
  hevy: 'Hevy',
  whoop: 'Whoop',
  withings: 'Withings',
  cronometer: 'Cronometer',
}

function IntegrationRow({ integration }: { integration: SyncIntegration }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            integration.is_active ? 'bg-green-500' : 'bg-muted-foreground/40',
          )}
        />
        <span className="text-xs text-sidebar-foreground">
          {SOURCE_LABELS[integration.source] ?? integration.source}
        </span>
      </div>
      <span className="text-xs text-muted-foreground">
        {integration.last_synced_at
          ? formatDistanceToNow(new Date(integration.last_synced_at), { addSuffix: true })
          : 'never'}
      </span>
    </div>
  )
}

export function SyncStatus() {
  const queryClient = useQueryClient()
  const [syncing, setSyncing] = useState(false)

  const { data: integrations, isLoading, isError } = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
    refetchInterval: 60_000,
    retry: 1,
  })

  async function handleSync() {
    setSyncing(true)
    try {
      await triggerSync()
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['sync-status'] })
        setSyncing(false)
      }, 4000)
    } catch {
      setSyncing(false)
    }
  }

  const syncSources = integrations?.filter((i) => i.load_type === 'sync') ?? []
  const uploadSources = integrations?.filter((i) => i.load_type === 'upload') ?? []

  return (
    <div className="border-t px-4 py-3 flex flex-col gap-3">

      {/* Auto-sync sources */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Synced
          </span>
          <Tooltip>
            <TooltipTrigger>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6"
                onClick={handleSync}
                disabled={syncing || isLoading || isError}
              >
                <RefreshCw className={cn('h-3 w-3', syncing && 'animate-spin')} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Sync now</TooltipContent>
          </Tooltip>
        </div>

        {isLoading && (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-4 w-full rounded" />
            ))}
          </div>
        )}
        {isError && <p className="text-xs text-muted-foreground">Backend offline</p>}
        {!isLoading && !isError && syncSources.length === 0 && (
          <p className="text-xs text-muted-foreground">No sync sources configured</p>
        )}
        {syncSources.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {syncSources.map((i) => <IntegrationRow key={i.source} integration={i} />)}
          </div>
        )}
      </div>

      {/* Manual upload sources */}
      {(isLoading || uploadSources.length > 0) && (
        <div>
          <div className="mb-2 flex items-center gap-1.5">
            <Upload className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Uploaded
            </span>
          </div>
          {isLoading && <Skeleton className="h-4 w-full rounded" />}
          {!isLoading && uploadSources.length > 0 && (
            <div className="flex flex-col gap-1.5">
              {uploadSources.map((i) => <IntegrationRow key={i.source} integration={i} />)}
            </div>
          )}
        </div>
      )}

    </div>
  )
}
