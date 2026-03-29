import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  uploadLiftingVideo,
  getFormAnalyses,
  type FormAnalysisResult,
  type FormAnalysis,
  type FormFinding,
} from '@/lib/api'

const EXERCISES: { key: string; label: string }[] = [
  { key: 'barbell_squat', label: 'Barbell Squat' },
  { key: 'deadlift', label: 'Deadlift' },
  { key: 'bench_press', label: 'Bench Press' },
  { key: 'overhead_press', label: 'Overhead Press' },
]

const RATING_META = {
  good: { label: 'Good', className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  needs_work: { label: 'Needs Work', className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
  safety_concern: { label: 'Safety Concern', className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
}

const SEVERITY_ICON = {
  ok: '✅',
  warning: '⚠️',
  error: '❌',
}

function RatingBadge({ rating }: { rating: FormAnalysisResult['overall_rating'] }) {
  const meta = RATING_META[rating]
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

function FindingRow({ finding }: { finding: FormFinding }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="mt-0.5 shrink-0">{SEVERITY_ICON[finding.severity]}</span>
      <div>
        <span className="font-medium">{finding.aspect}:</span>{' '}
        <span className="text-muted-foreground">{finding.note}</span>
      </div>
    </div>
  )
}

function AnalysisCard({ result }: { result: FormAnalysisResult }) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <div className="flex items-center gap-2">
        <span className="font-semibold text-sm">Overall</span>
        <RatingBadge rating={result.overall_rating} />
        <span className="ml-auto text-xs text-muted-foreground">{result.frame_count} frames analysed</span>
      </div>

      {result.findings.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Findings</p>
          {result.findings.map((f, i) => (
            <FindingRow key={i} finding={f} />
          ))}
        </div>
      )}

      {result.cues.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Coaching cues</p>
          {result.cues.map((cue, i) => (
            <div key={i} className="flex gap-2 text-sm">
              <span className="text-muted-foreground shrink-0">→</span>
              <span>{cue}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function HistoryItem({ analysis }: { analysis: FormAnalysis }) {
  const [expanded, setExpanded] = useState(false)
  const label = EXERCISES.find((e) => e.key === analysis.exercise_name)?.label ?? analysis.exercise_name
  const date = new Date(analysis.video_date).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })

  return (
    <div className="rounded-md border">
      <button
        className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">{date}</span>
        <RatingBadge rating={analysis.overall_rating} />
        {analysis.recovery_score_day_of != null && (
          <span className="ml-auto text-xs text-muted-foreground">
            Recovery {Math.round(analysis.recovery_score_day_of)}%
          </span>
        )}
      </button>
      {expanded && (
        <div className="px-3 pb-3">
          <AnalysisCard result={analysis} />
        </div>
      )}
    </div>
  )
}

export function FormCheckPage() {
  const [exerciseKey, setExerciseKey] = useState(EXERCISES[0].key)
  const [dragging, setDragging] = useState(false)
  const [durationWarning, setDurationWarning] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<FormAnalysisResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: history } = useQuery({
    queryKey: ['form-analyses'],
    queryFn: getFormAnalyses,
  })

  async function handleFile(file: File) {
    setError(null)
    setResult(null)
    setDurationWarning(false)

    // Client-side duration check
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.preload = 'metadata'
    await new Promise<void>((resolve) => {
      video.onloadedmetadata = () => resolve()
      video.onerror = () => resolve()
      video.src = url
    })
    URL.revokeObjectURL(url)
    if (video.duration > 30) {
      setDurationWarning(true)
    }

    setUploading(true)
    try {
      const analysis = await uploadLiftingVideo(exerciseKey, file)
      setResult(analysis)
      queryClient.invalidateQueries({ queryKey: ['form-analyses'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setUploading(false)
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Form Check</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload a short lifting video for AI-powered form analysis.
        </p>
      </div>

      {/* Exercise selector */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium" htmlFor="exercise-select">Exercise</label>
        <select
          id="exercise-select"
          value={exerciseKey}
          onChange={(e) => setExerciseKey(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {EXERCISES.map((ex) => (
            <option key={ex.key} value={ex.key}>{ex.label}</option>
          ))}
        </select>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors cursor-pointer select-none
          ${dragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/30 hover:border-muted-foreground/60 hover:bg-muted/30'}
          ${uploading ? 'pointer-events-none opacity-60' : ''}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/mp4,video/quicktime"
          className="hidden"
          onChange={onFileChange}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-2">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-sm text-muted-foreground">Analysing your form…</span>
          </div>
        ) : (
          <>
            <svg className="mb-3 h-8 w-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 10l4.553-2.276A1 1 0 0121 8.677v6.646a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
            </svg>
            <p className="text-sm font-medium">Drop video here or click to upload</p>
            <p className="mt-1 text-xs text-muted-foreground">MP4 or MOV · Max 30 seconds</p>
          </>
        )}
      </div>

      {durationWarning && (
        <p className="text-sm text-yellow-600 dark:text-yellow-400">
          ⚠️ Video is longer than 30 seconds — analysis may be slower and less accurate. Consider trimming to the working set.
        </p>
      )}

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
      )}

      {result && (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            {EXERCISES.find((e) => e.key === exerciseKey)?.label} Analysis
          </p>
          <AnalysisCard result={result} />
        </div>
      )}

      {/* History */}
      {history && history.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Recent Analyses</p>
          {history.map((a) => (
            <HistoryItem key={a.id} analysis={a} />
          ))}
        </div>
      )}
    </div>
  )
}
