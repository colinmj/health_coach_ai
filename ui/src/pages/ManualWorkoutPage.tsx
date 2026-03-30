import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import {
  parseManualWorkout,
  saveManualWorkout,
  getManualWorkouts,
  deleteManualWorkout,
} from '@/lib/api'
import type { ManualWorkout, ManualWorkoutSet, ParsedWorkout } from '@/types'

// ─── Sub-components ──────────────────────────────────────────────────────────

function SetTable({ sets }: { sets: ManualWorkoutSet[] }) {
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b">
          <th className="pb-1 pr-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">Set</th>
          <th className="pb-1 pr-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">Weight</th>
          <th className="pb-1 pr-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">Reps</th>
          <th className="pb-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">RPE</th>
        </tr>
      </thead>
      <tbody className="divide-y">
        {sets.map((s) => (
          <tr key={s.set_index}>
            <td className="py-1.5 pr-4 text-sm">{s.set_index + 1}</td>
            <td className="py-1.5 pr-4 text-sm">
              {s.weight_kg !== null ? `${s.weight_kg} kg` : '—'}
            </td>
            <td className="py-1.5 pr-4 text-sm">{s.reps !== null ? s.reps : '—'}</td>
            <td className="py-1.5 text-sm">{s.rpe !== null ? s.rpe : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ParsedPreviewCard({
  parsed,
  saving,
  saved,
  onSave,
  onClear,
}: {
  parsed: ParsedWorkout
  saving: boolean
  saved: boolean
  onSave: () => void
  onClear: () => void
}) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-sm">{parsed.title ?? 'Untitled workout'}</p>
          {parsed.date && (
            <p className="text-xs text-muted-foreground mt-0.5">{parsed.date}</p>
          )}
        </div>
        <button
          onClick={onClear}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0"
        >
          Clear
        </button>
      </div>

      {parsed.warnings.length > 0 && (
        <div className="space-y-1">
          {parsed.warnings.map((w, i) => (
            <p key={i} className="text-sm text-amber-600 dark:text-amber-400">
              ⚠️ {w}
            </p>
          ))}
        </div>
      )}

      {parsed.exercises.length === 0 ? (
        <p className="text-sm text-muted-foreground">No exercises detected.</p>
      ) : (
        <div className="space-y-4">
          {parsed.exercises.map((ex, i) => (
            <div key={i}>
              <p className="text-sm font-medium mb-2">{ex.name}</p>
              <SetTable sets={ex.sets} />
            </div>
          ))}
        </div>
      )}

      <button
        onClick={onSave}
        disabled={saving || saved}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-60 hover:opacity-90"
      >
        {saved ? 'Saved!' : saving ? (
          <span className="flex items-center gap-2">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
            Saving…
          </span>
        ) : 'Save workout'}
      </button>
    </div>
  )
}

function WorkoutRow({
  workout,
  onDelete,
}: {
  workout: ManualWorkout
  onDelete: (id: number) => void
}) {
  const [deleting, setDeleting] = useState(false)

  const date = workout.start_time
    ? new Date(workout.start_time).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : new Date(workout.logged_at).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })

  async function handleDelete() {
    setDeleting(true)
    try {
      await onDelete(workout.id)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex items-center justify-between rounded-md border px-3 py-2">
      <div>
        <p className="text-sm font-medium">{workout.title ?? 'Untitled workout'}</p>
        <p className="text-xs text-muted-foreground">{date}</p>
      </div>
      <button
        onClick={handleDelete}
        disabled={deleting}
        aria-label={`Delete ${workout.title ?? 'workout'}`}
        className="text-muted-foreground hover:text-destructive transition-colors disabled:opacity-40"
      >
        {deleting ? (
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent inline-block" />
        ) : (
          <Trash2 size={16} />
        )}
      </button>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type Mode = 'text' | 'photo'

export function ManualWorkoutPage() {
  const [mode, setMode] = useState<Mode>('text')
  const [input, setInput] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [parsed, setParsed] = useState<ParsedWorkout | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: recentWorkouts } = useQuery({
    queryKey: ['manual-workouts'],
    queryFn: getManualWorkouts,
  })

  function resetParseState() {
    setParsed(null)
    setSaved(false)
    setError(null)
  }

  function handleModeSwitch(next: Mode) {
    setMode(next)
    setInput('')
    setFile(null)
    resetParseState()
  }

  async function handleParse(text: string | null, photoFile: File | null) {
    setError(null)
    setParsed(null)
    setSaved(false)
    setParsing(true)
    try {
      const result = await parseManualWorkout(text, photoFile)
      setParsed(result.parsed)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Parse failed')
    } finally {
      setParsing(false)
    }
  }

  async function handlePhotoFile(selected: File) {
    setFile(selected)
    await handleParse(null, selected)
  }

  function onFileInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0]
    if (selected) handlePhotoFile(selected)
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) handlePhotoFile(dropped)
  }

  async function handleSave() {
    if (!parsed) return
    setSaving(true)
    setError(null)
    try {
      await saveManualWorkout(parsed)
      setSaved(true)
      queryClient.invalidateQueries({ queryKey: ['manual-workouts'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: number) {
    await deleteManualWorkout(id)
    queryClient.invalidateQueries({ queryKey: ['manual-workouts'] })
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 space-y-6">
      {/* Header + mode toggle */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Log Workout</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Describe your workout as text or upload a photo of your log.
          </p>
        </div>
        <div className="flex items-center rounded-md border p-0.5 shrink-0">
          <button
            onClick={() => handleModeSwitch('text')}
            className={`rounded px-3 py-1 text-sm transition-colors ${
              mode === 'text'
                ? 'bg-muted text-foreground font-medium'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Text
          </button>
          <button
            onClick={() => handleModeSwitch('photo')}
            className={`rounded px-3 py-1 text-sm transition-colors ${
              mode === 'photo'
                ? 'bg-muted text-foreground font-medium'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Photo
          </button>
        </div>
      </div>

      {/* Input area */}
      {mode === 'text' ? (
        <div className="space-y-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. Bench press 4x8 at 100kg, Squat 3x5 at 140kg, RDL 3x10 at 80kg"
            rows={5}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            onClick={() => handleParse(input, null)}
            disabled={parsing || !input.trim()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-60 hover:opacity-90"
          >
            {parsing ? (
              <span className="flex items-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                Parsing…
              </span>
            ) : 'Parse workout'}
          </button>
        </div>
      ) : (
        /* Photo drop zone — mirrors FormCheckPage.tsx pattern */
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !parsing && fileInputRef.current?.click()}
          className={[
            'relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors cursor-pointer select-none',
            dragging
              ? 'border-primary bg-primary/5'
              : 'border-muted-foreground/30 hover:border-muted-foreground/60 hover:bg-muted/30',
            parsing ? 'pointer-events-none opacity-60' : '',
          ].join(' ')}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/heic,image/webp"
            className="hidden"
            onChange={onFileInputChange}
          />
          {parsing ? (
            <div className="flex flex-col items-center gap-2">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <span className="text-sm text-muted-foreground">Parsing your workout log…</span>
            </div>
          ) : (
            <>
              <svg
                className="mb-3 h-8 w-8 text-muted-foreground"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
              {file ? (
                <p className="text-sm font-medium">{file.name}</p>
              ) : (
                <>
                  <p className="text-sm font-medium">Drop photo here or click to upload</p>
                  <p className="mt-1 text-xs text-muted-foreground">JPEG, PNG, HEIC, WebP</p>
                </>
              )}
            </>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
      )}

      {/* Parse result preview */}
      {parsed && (
        <ParsedPreviewCard
          parsed={parsed}
          saving={saving}
          saved={saved}
          onSave={handleSave}
          onClear={resetParseState}
        />
      )}

      {/* Recent workouts */}
      {recentWorkouts && recentWorkouts.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Recent Workouts</p>
          {recentWorkouts.map((w) => (
            <WorkoutRow key={w.id} workout={w} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}
