import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAvailableIntegrations, createIntegrations } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { RefreshCw, Upload } from 'lucide-react'

interface Integration {
  source: string
  domain: string
  load_type: 'sync' | 'upload'
  label: string
  description: string
  env_key: string | null
}

const SETUP_NOTES: Record<string, { text: string; inputLabel?: string; inputPlaceholder?: string; oauthProvider?: string }> = {
  hevy: {
    text: 'Get your API key from hevy.com → Settings → Developer tab.',
    inputLabel: 'Hevy API Key',
    inputPlaceholder: 'Paste your Hevy API key…',
  },
  whoop: {
    text: 'Once setup is complete, connect your Whoop account from the sidebar.',
  },
  withings: {
    text: 'Once setup is complete, connect your Withings account from the sidebar.',
  },
  cronometer: {
    text: 'Export a Daily Summary CSV from Cronometer and upload it from your dashboard.',
  },
}

const DOMAIN_LABELS: Record<string, string> = {
  strength: 'Strength',
  recovery: 'Recovery',
  body_composition: 'Body Composition',
  nutrition: 'Nutrition',
}

export function OnboardingPage() {
  const navigate = useNavigate()
  const completeOnboarding = useAuthStore((s) => s.completeOnboarding)
  const onboardingComplete = useAuthStore((s) => s.onboardingComplete)

  const [step, setStep] = useState<1 | 2>(1)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (onboardingComplete) {
      navigate('/', { replace: true })
      return
    }
    getAvailableIntegrations()
      .then((data) => setIntegrations(data as Integration[]))
      .catch(() => setError('Failed to load integrations'))
      .finally(() => setLoading(false))
  }, [onboardingComplete, navigate])

  function toggleSource(source: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(source)) next.delete(source)
      else next.add(source)
      return next
    })
  }

  async function handleFinish() {
    setSubmitting(true)
    setError(null)
    try {
      await createIntegrations(Array.from(selected), credentials)
      completeOnboarding()
      navigate('/')
    } catch {
      setError('Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-lg space-y-8">

        {/* Step indicator */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className={cn('font-medium', step === 1 && 'text-foreground')}>1. Choose integrations</span>
          <span>→</span>
          <span className={cn('font-medium', step === 2 && 'text-foreground')}>2. Setup notes</span>
        </div>

        {step === 1 && (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Connect your data</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Choose which integrations to enable. You can change these later in Settings.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {integrations.map((i) => {
                const isSelected = selected.has(i.source)
                return (
                  <button
                    key={i.source}
                    onClick={() => toggleSource(i.source)}
                    className={cn(
                      'rounded-lg border p-4 text-left transition-colors',
                      isSelected
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:border-muted-foreground/50',
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-medium text-sm">{i.label}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">{DOMAIN_LABELS[i.domain] ?? i.domain}</p>
                      </div>
                      <span className={cn(
                        'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium',
                        i.load_type === 'upload'
                          ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                          : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
                      )}>
                        {i.load_type === 'upload' ? <Upload className="inline h-3 w-3 mr-0.5" /> : <RefreshCw className="inline h-3 w-3 mr-0.5" />}
                        {i.load_type === 'upload' ? 'Upload' : 'Sync'}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">{i.description}</p>
                  </button>
                )
              })}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between">
              <button
                onClick={handleFinish}
                className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
                disabled={submitting}
              >
                Skip for now
              </button>
              <Button onClick={() => selected.size > 0 ? setStep(2) : handleFinish()} disabled={submitting}>
                {selected.size > 0 ? 'Next' : 'Continue without integrations'}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Setup notes</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Here's how to connect each integration you selected.
              </p>
            </div>

            <div className="space-y-3">
              {integrations
                .filter((i) => selected.has(i.source))
                .map((i) => {
                  const note = SETUP_NOTES[i.source]
                  return (
                    <div key={i.source} className="rounded-lg border border-border p-4 space-y-3">
                      <div>
                        <p className="font-medium text-sm">{i.label}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">{note?.text ?? 'Follow the setup guide.'}</p>
                      </div>
                      {note?.inputLabel && (
                        <div className="space-y-1.5">
                          <Label htmlFor={`cred-${i.source}`} className="text-xs">{note.inputLabel}</Label>
                          <Input
                            id={`cred-${i.source}`}
                            type="password"
                            placeholder={note.inputPlaceholder}
                            value={credentials[i.source] ?? ''}
                            onChange={(e) => setCredentials((prev) => ({ ...prev, [i.source]: e.target.value }))}
                          />
                        </div>
                      )}
                    </div>
                  )
                })}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between">
              <Button variant="ghost" onClick={() => setStep(1)}>Back</Button>
              <Button onClick={handleFinish} disabled={submitting}>
                {submitting ? 'Saving…' : 'Go to Chat'}
              </Button>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
