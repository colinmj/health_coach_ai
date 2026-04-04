import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getSyncStatus, triggerSync, uploadCsvFile, uploadAppleHealthFile, startOAuth } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Check, ExternalLink, Loader2, RefreshCw, Upload } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { cn } from '@/lib/utils'
import type { SyncIntegration } from '@/types'

function IntegrationRow({
  integration,
  onUpload,
  uploading,
  uploadError,
  uploadSuccess,
}: {
  integration: SyncIntegration
  onUpload?: () => void
  uploading?: boolean
  uploadError?: string | null
  uploadSuccess?: string | false
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              integration.is_active ? 'bg-green-500' : 'bg-muted-foreground/40',
            )}
          />
          <span className="text-xs text-sidebar-foreground">
            {integration.label}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {!integration.authorized && integration.auth_type === 'oauth' ? (
            <button
              onClick={() => startOAuth(integration.source)}
              className="flex items-center gap-0.5 text-xs text-primary hover:underline"
            >
              Connect <ExternalLink className="h-2.5 w-2.5" />
            </button>
          ) : (
            <span className="text-xs text-muted-foreground">
              {integration.last_synced_at
                ? formatDistanceToNow(new Date(integration.last_synced_at), { addSuffix: true })
                : 'never'}
            </span>
          )}
          {onUpload && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-5 w-5"
                    onClick={onUpload}
                    disabled={uploading}
                  >
                    {uploading
                      ? <Loader2 className="h-3 w-3 animate-spin" />
                      : <Upload className="h-3 w-3" />
                    }
                  </Button>
                }
              />
              <TooltipContent side="left">{integration.source === 'apple_health' ? 'Upload ZIP' : 'Upload CSV'}</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>
      {uploadError && (
        <p className="text-xs text-destructive pl-3">{uploadError}</p>
      )}
      {uploadSuccess && !uploadError && (
        <p className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400 pl-3">
          <Check className="h-3 w-3" aria-hidden="true" />
          {uploadSuccess}
        </p>
      )}
    </div>
  )
}

export function SyncStatus() {
  const queryClient = useQueryClient()
  const [syncing, setSyncing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<string | false>(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const activeUploadSourceRef = useRef<string>('cronometer')

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

  function handleUploadClick(source: string) {
    activeUploadSourceRef.current = source
    if (fileInputRef.current) {
      fileInputRef.current.accept = source === 'apple_health' ? '.zip' : '.csv'
    }
    setUploadError(null)
    setUploadSuccess(false)
    fileInputRef.current?.click()
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    // Reset so the same file can be re-selected
    e.target.value = ''
    setUploading(true)
    setUploadError(null)
    try {
      const source = activeUploadSourceRef.current
      const result = source === 'apple_health'
        ? await uploadAppleHealthFile(file)
        : await uploadCsvFile(file)
      queryClient.invalidateQueries({ queryKey: ['sync-status'] })
      let msg: string
      if (source === 'apple_health') {
        const r = result as unknown as { rows_imported: Record<string, number> }
        msg = Object.entries(r.rows_imported)
          .filter(([, n]) => n > 0)
          .map(([k, n]) => `${n} ${k.replace('_', ' ')}`)
          .join(', ') || 'No new records'
      } else if ('inserted' in result) {
        msg = `${result.inserted} food item${result.inserted === 1 ? '' : 's'} imported across ${result.days} day${result.days === 1 ? '' : 's'}`
      } else {
        msg = `${result.rows_imported} day${result.rows_imported === 1 ? '' : 's'} imported`
      }
      setUploadSuccess(msg)
      setTimeout(() => setUploadSuccess(false), 3000)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const syncSources = integrations?.filter((i) => i.auth_type !== 'upload') ?? []
  const uploadSources = integrations?.filter((i) => i.auth_type === 'upload') ?? []

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
              Data Upload
            </span>
          </div>
          {isLoading && <Skeleton className="h-4 w-full rounded" />}
          {!isLoading && uploadSources.length > 0 && (
            <div className="flex flex-col gap-1.5">
              {uploadSources.map((i) => (
                <IntegrationRow
                  key={i.source}
                  integration={i}
                  onUpload={() => handleUploadClick(i.source)}
                  uploading={uploading}
                  uploadError={uploadError}
                  uploadSuccess={uploadSuccess}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={handleFileChange}
      />

    </div>
  )
}
