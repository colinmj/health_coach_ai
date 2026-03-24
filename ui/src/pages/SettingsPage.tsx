import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  getProfile, updateProfile,
  getAvailableIntegrations, getSyncStatus,
  getDataImports, saveDataImports,
  createIntegrations, deleteIntegration,
} from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { ExternalLink, Loader2, Trash2, Check, Upload } from 'lucide-react'
import type { SyncIntegration } from '@/types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DATA_TYPE_LABELS: Record<string, string> = {
  sleep:             'Sleep',
  hrv_recovery:      'HRV & Recovery',
  strength_workouts: 'Strength Training',
  activities:        'Activities',
  body_composition:  'Body Composition',
  nutrition:         'Nutrition',
}

async function startOAuth(provider: string) {
  const token = useAuthStore.getState().token
  const res = await fetch(`/api/oauth/${provider}/start`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const { url } = await res.json()
  window.location.href = url
}

// ---------------------------------------------------------------------------
// Tab primitives
// ---------------------------------------------------------------------------

type Tab = 'profile' | 'integrations'

function Tabs({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  const tabs: { id: Tab; label: string }[] = [
    { id: 'profile', label: 'Profile' },
    { id: 'integrations', label: 'Integrations' },
  ]
  return (
    <div className="flex gap-1 border-b mb-6">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cn(
            'px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors',
            active === t.id
              ? 'border-foreground text-foreground'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Profile tab
// ---------------------------------------------------------------------------

function ProfileTab() {
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: profile, isLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
  })

  const [form, setForm] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  const mutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  function field(key: string) {
    return key in form ? form[key] : (String(profile?.[key] ?? ''))
  }

  function set(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSave() {
    const payload: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(form)) {
      if (v !== '') payload[k] = v
    }
    mutation.mutate(payload)
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading…</div>
  }

  return (
    <div className="space-y-6 max-w-md">
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            value={field('name')}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Your name"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="dob">Date of birth</Label>
          <Input
            id="dob"
            type="date"
            value={field('date_of_birth')}
            onChange={(e) => set('date_of_birth', e.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="sex">Sex</Label>
          <select
            id="sex"
            value={field('sex')}
            onChange={(e) => set('sex', e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="">Not specified</option>
            <option value="male">Male</option>
            <option value="female">Female</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="height">Height (cm)</Label>
          <Input
            id="height"
            type="number"
            value={field('height_cm')}
            onChange={(e) => set('height_cm', e.target.value)}
            placeholder="e.g. 178"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="units">Units</Label>
          <select
            id="units"
            value={field('units') || 'metric'}
            onChange={(e) => set('units', e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="metric">Metric (kg, cm)</option>
            <option value="imperial">Imperial (lbs, ft)</option>
          </select>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={mutation.isPending}>
          {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : saved ? <><Check className="h-4 w-4 mr-1.5" />Saved</> : 'Save changes'}
        </Button>
        {mutation.isError && (
          <p className="text-sm text-destructive">Failed to save.</p>
        )}
      </div>

      <div className="pt-4 border-t">
        <Button variant="ghost" className="text-muted-foreground hover:text-destructive" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Integration card
// ---------------------------------------------------------------------------

interface AvailableIntegration {
  source: string
  label: string
  description: string
  auth_type: 'oauth' | 'api_key' | 'upload'
  data_types: string[]
}

function IntegrationCard({
  available,
  connected,
  onDisconnect,
  onConnect,
  onConnectOAuth,
}: {
  available: AvailableIntegration
  connected: SyncIntegration | undefined
  onDisconnect: () => void
  onConnect: (apiKey?: string) => void
  onConnectOAuth: () => void
}) {
  const [showKeyInput, setShowKeyInput] = useState(false)
  const [keyValue, setKeyValue] = useState('')
  const [working, setWorking] = useState(false)

  const isConnected = !!connected

  async function handleConnect() {
    setWorking(true)
    try {
      await onConnect(keyValue || undefined)
    } finally {
      setWorking(false)
      setShowKeyInput(false)
      setKeyValue('')
    }
  }

  async function handleDisconnect() {
    setWorking(true)
    try {
      await onDisconnect()
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="rounded-lg border border-border p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-medium text-sm">{available.label}</p>
            {isConnected && (
              <span className="shrink-0 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 px-2 py-0.5 text-xs font-medium">
                {connected!.authorized ? 'Connected' : 'Pending auth'}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{available.description}</p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            {available.data_types.map((dt) => DATA_TYPE_LABELS[dt] ?? dt).join(' · ')}
          </p>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {/* Upload — always shows as available; connect = add row */}
          {available.auth_type === 'upload' && !isConnected && (
            <Button size="sm" variant="outline" disabled={working} onClick={() => onConnect()}>
              {working ? <Loader2 className="h-3 w-3 animate-spin" /> : <><Upload className="h-3 w-3 mr-1.5" />Add</>}
            </Button>
          )}

          {/* OAuth — connect button */}
          {available.auth_type === 'oauth' && (!isConnected || !connected!.authorized) && (
            <Button size="sm" variant="outline" onClick={onConnectOAuth}>
              Connect <ExternalLink className="h-3 w-3 ml-1.5" />
            </Button>
          )}

          {/* API key — show input or connect button */}
          {available.auth_type === 'api_key' && !isConnected && !showKeyInput && (
            <Button size="sm" variant="outline" onClick={() => setShowKeyInput(true)}>
              Connect
            </Button>
          )}
          {available.auth_type === 'api_key' && isConnected && (
            <Button size="sm" variant="ghost" className="text-xs text-muted-foreground" onClick={() => setShowKeyInput((v) => !v)}>
              Update key
            </Button>
          )}

          {/* Disconnect */}
          {isConnected && (
            <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground hover:text-destructive" disabled={working} onClick={handleDisconnect}>
              {working ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
            </Button>
          )}
        </div>
      </div>

      {/* API key input */}
      {showKeyInput && (
        <div className="flex gap-2 mt-1">
          <Input
            type="password"
            placeholder="Paste API key…"
            value={keyValue}
            onChange={(e) => setKeyValue(e.target.value)}
            className="h-8 text-sm"
          />
          <Button size="sm" disabled={!keyValue || working} onClick={handleConnect}>
            {working ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Save'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => { setShowKeyInput(false); setKeyValue('') }}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Data routing section
// ---------------------------------------------------------------------------

function DataRouting({
  connected,
  assignments,
  onChange,
}: {
  connected: SyncIntegration[]
  assignments: Record<string, string>
  onChange: (dt: string, source: string) => void
}) {
  const typeToSources: Record<string, string[]> = {}
  for (const i of connected) {
    for (const dt of i.data_types) {
      if (!typeToSources[dt]) typeToSources[dt] = []
      typeToSources[dt].push(i.source)
    }
  }

  const entries = Object.entries(typeToSources)
  if (entries.length === 0) return null

  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">Data routing</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Choose which source to use for each data type.
        </p>
      </div>
      <div className="rounded-lg border border-border p-4 space-y-3">
        {entries.map(([dt, sources]) => (
          <div key={dt} className="flex items-center justify-between gap-4">
            <Label className="text-sm">{DATA_TYPE_LABELS[dt] ?? dt}</Label>
            {sources.length === 1 ? (
              <span className="text-sm text-muted-foreground">{sources[0]}</span>
            ) : (
              <select
                className="text-sm rounded border border-input bg-background px-2 py-1"
                value={assignments[dt] ?? sources[0]}
                onChange={(e) => onChange(dt, e.target.value)}
              >
                {sources.map((s) => (
                  <option key={s} value={s}>
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </option>
                ))}
              </select>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Integrations tab
// ---------------------------------------------------------------------------

function IntegrationsTab() {
  const queryClient = useQueryClient()
  const [routingSaved, setRoutingSaved] = useState(false)

  const { data: available = [] } = useQuery({
    queryKey: ['integrations-available'],
    queryFn: getAvailableIntegrations,
  })

  const { data: syncStatus = [] } = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
  })

  const { data: dataImports = {} } = useQuery({
    queryKey: ['data-imports'],
    queryFn: getDataImports,
  })

  const [pendingAssignments, setPendingAssignments] = useState<Record<string, string>>({})

  const connectedMap = new Map((syncStatus as SyncIntegration[]).map((i) => [i.source, i]))
  const connected = syncStatus as SyncIntegration[]

  const assignments = { ...dataImports, ...pendingAssignments }

  async function handleConnect(source: string, apiKey?: string) {
    await createIntegrations([source], apiKey ? { [source]: apiKey } : {})
    queryClient.invalidateQueries({ queryKey: ['sync-status'] })
  }

  async function handleDisconnect(source: string) {
    await deleteIntegration(source)
    queryClient.invalidateQueries({ queryKey: ['sync-status'] })
    queryClient.invalidateQueries({ queryKey: ['data-imports'] })
  }

  async function handleSaveRouting() {
    await saveDataImports(pendingAssignments)
    queryClient.invalidateQueries({ queryKey: ['data-imports'] })
    setPendingAssignments({})
    setRoutingSaved(true)
    setTimeout(() => setRoutingSaved(false), 2000)
  }

  return (
    <div className="space-y-6 max-w-lg">
      <div className="space-y-3">
        {(available as AvailableIntegration[]).map((avail) => (
          <IntegrationCard
            key={avail.source}
            available={avail}
            connected={connectedMap.get(avail.source)}
            onConnect={(apiKey) => handleConnect(avail.source, apiKey)}
            onDisconnect={() => handleDisconnect(avail.source)}
            onConnectOAuth={() => startOAuth(avail.source)}
          />
        ))}
      </div>

      <DataRouting
        connected={connected}
        assignments={assignments}
        onChange={(dt, source) => setPendingAssignments((prev) => ({ ...prev, [dt]: source }))}
      />

      {Object.keys(pendingAssignments).length > 0 && (
        <Button onClick={handleSaveRouting}>
          {routingSaved ? <><Check className="h-4 w-4 mr-1.5" />Saved</> : 'Save routing'}
        </Button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('profile')

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-xl font-semibold mb-6">Settings</h1>
      <Tabs active={tab} onChange={setTab} />
      {tab === 'profile' && <ProfileTab />}
      {tab === 'integrations' && <IntegrationsTab />}
    </div>
  )
}
