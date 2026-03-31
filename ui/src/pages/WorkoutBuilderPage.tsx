import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Markdown from 'markdown-to-jsx'
import { ArrowUp, Square, ChevronLeft, ChevronDown, ChevronRight, X, Dumbbell, LayoutList, RefreshCw, Download, Mail, Timer, Repeat } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useWorkoutBuilderStore } from '@/stores/workoutBuilderStore'
import { useWorkoutBuilderMessage } from '@/hooks/useWorkoutBuilderMessage'
import {
  getWorkoutPrograms,
  getWorkoutProgram,
  syncProgramToHevy,
} from '@/lib/api'
import type { TrainingProgram, ProgramBlock, ProgramSession, ProgramExercise } from '@/types'

const STARTER_PROMPTS = [
  'Build me a 4-day push/pull/legs program',
  'Design a 12-week strength peaking block',
  'I want to add 10 kg to my squat — build a program',
]

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------

const MARKDOWN_OVERRIDES = {
  code: { props: { className: 'bg-background rounded px-1 py-0.5 text-xs font-mono' } },
  pre: { props: { className: 'bg-background rounded-lg p-3 overflow-x-auto text-xs font-mono my-2' } },
  a: { props: { className: 'text-primary underline underline-offset-2', target: '_blank', rel: 'noreferrer' } },
}

function TypingIndicator({ tool }: { tool: string | null }) {
  return (
    <div className="flex justify-start">
      <div className="bg-muted rounded-2xl px-4 py-3 flex items-center gap-3">
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce"
              style={{ animationDelay: `${i * 150}ms`, animationDuration: '900ms' }}
            />
          ))}
        </div>
        {tool && (
          <span className="text-xs text-muted-foreground capitalize">
            {tool.replace(/_/g, ' ')}
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Programs panel — list view
// ---------------------------------------------------------------------------

const GOAL_LABELS: Record<string, string> = {
  cut: 'Cut',
  bulk: 'Bulk',
  recomp: 'Recomp',
  strength: 'Strength',
  athletic: 'Athletic',
}

// ---------------------------------------------------------------------------
// PDF export — new-window approach
// ---------------------------------------------------------------------------
//
// Why a new window instead of window.print() + @media print CSS tricks:
//   The app shell uses overflow:hidden flex containers that confine #program-print-root
//   inside a clipped subtree. Browsers (especially Safari and Chrome headless) render
//   the clipped region as blank when printing because the layout engine resolves
//   `overflow:hidden` before applying @media print overrides. A new window contains
//   only the content we want, so there is nothing to isolate or override.

function formatRestForPrint(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`
}

function buildProgramHtml(program: TrainingProgram): string {
  const blocks: ProgramBlock[] = program.blocks ?? []
  const goalLabel = program.goal_type
    ? (GOAL_LABELS[program.goal_type] ?? program.goal_type)
    : null
  const subtitle = [goalLabel, program.type === 'hevy' ? 'Hevy' : 'Manual']
    .filter(Boolean)
    .join(' · ')

  function renderExercise(ex: ProgramExercise, i: number): string {
    const title = ex.exercise_title ?? `Exercise ${i + 1}`
    const sets = ex.sets != null ? String(ex.sets) : null
    const reps = ex.reps != null ? String(ex.reps) : null
    const rest = ex.rest_seconds != null ? formatRestForPrint(ex.rest_seconds) : null

    const setsReps = sets && reps
      ? `${sets} &times; ${reps}`
      : sets
        ? `${sets} sets`
        : null

    const meta = [setsReps, rest ? `${rest} rest` : null].filter(Boolean).join(' &nbsp;&middot;&nbsp; ')

    return `
      <tr>
        <td style="padding:4px 8px 4px 0;vertical-align:top;font-weight:500;">${title}</td>
        <td style="padding:4px 0;vertical-align:top;color:#555;white-space:nowrap;">${meta}</td>
      </tr>
      ${ex.notes ? `
      <tr>
        <td colspan="2" style="padding:0 8px 6px 0;color:#888;font-style:italic;font-size:9pt;">${ex.notes}</td>
      </tr>` : ''}
    `
  }

  function renderSession(session: ProgramSession, i: number): string {
    const label = session.day_label ?? `Day ${i + 1}`
    const exercises = session.exercises ?? []
    const rows = exercises.length > 0
      ? exercises.map((ex, j) => renderExercise(ex, j)).join('')
      : `<tr><td colspan="2" style="color:#aaa;padding:4px 0;">No exercises listed.</td></tr>`

    return `
      <div style="page-break-inside:avoid;margin-bottom:12px;">
        <div style="font-size:10.5pt;font-weight:600;padding:5px 0;border-bottom:1px solid #e0e0e0;margin-bottom:6px;">
          ${label}
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:9.5pt;">
          <tbody>${rows}</tbody>
        </table>
      </div>
    `
  }

  function renderBlock(block: ProgramBlock, i: number): string {
    const sessions = block.sessions ?? []
    const meta = [
      block.duration_weeks != null
        ? `${block.duration_weeks} ${block.duration_weeks === 1 ? 'week' : 'weeks'}`
        : null,
      block.days_per_week != null ? `${block.days_per_week} days/week` : null,
    ].filter(Boolean).join(' &nbsp;&middot;&nbsp; ')

    const sessionHtml = sessions.length > 0
      ? sessions.map((s, j) => renderSession(s, j)).join('')
      : `<p style="color:#aaa;font-size:9.5pt;">No sessions defined.</p>`

    return `
      <section style="margin-bottom:24px;">
        <h2 style="font-size:13pt;font-weight:700;margin:0 0 2px 0;padding-bottom:4px;border-bottom:2px solid #222;">
          ${block.name}
        </h2>
        ${meta ? `<p style="font-size:9pt;color:#666;margin:0 0 10px 0;">${meta}</p>` : ''}
        ${sessionHtml}
      </section>
    `
  }

  const blocksHtml = blocks.length > 0
    ? blocks.map((b, i) => renderBlock(b, i)).join('')
    : `<p style="color:#aaa;">No program data available.</p>`

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${program.name}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif;
      font-size: 10.5pt;
      color: #111;
      background: #fff;
      padding: 18mm 20mm;
      line-height: 1.4;
    }
    h1 {
      font-size: 20pt;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .subtitle {
      font-size: 10pt;
      color: #666;
      margin-bottom: 24px;
      padding-bottom: 12px;
      border-bottom: 1px solid #ddd;
    }
    @page {
      margin: 18mm 20mm;
      size: A4 portrait;
    }
    @media print {
      body { padding: 0; }
    }
  </style>
</head>
<body>
  <h1>${program.name}</h1>
  <p class="subtitle">${subtitle}</p>
  ${blocksHtml}
</body>
</html>`
}

function handlePrintPdf(program: TrainingProgram): void {
  const printWindow = window.open('', '_blank')
  if (!printWindow) return
  printWindow.document.write(buildProgramHtml(program))
  printWindow.document.close()
  printWindow.focus()
  printWindow.print()
  printWindow.close()
}

function ProgramListItem({
  program,
  isViewing,
  onClick,
}: {
  program: TrainingProgram
  /** True when this program is currently open in the detail panel. */
  isViewing: boolean
  onClick: () => void
}) {
  const date = new Date(program.created_at).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })

  return (
    <button
      onClick={onClick}
      aria-pressed={isViewing}
      className={cn(
        'w-full text-left px-3 py-3 rounded-lg transition-colors border group',
        isViewing
          ? 'bg-muted/60 border-border ring-2 ring-ring/30'
          : 'border-transparent hover:bg-muted/60 hover:border-border',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{program.name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{date}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {program.is_active && (
            <Badge variant="default" className="text-[10px] px-1.5 py-0 h-4">Active</Badge>
          )}
          {isViewing && !program.is_active && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">Viewing</Badge>
          )}
          {program.goal_type && (
            <span className="text-[10px] text-muted-foreground">
              {GOAL_LABELS[program.goal_type] ?? program.goal_type}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-1.5">
        <span className="text-[11px] text-muted-foreground">
          {program.block_count} {program.block_count === 1 ? 'block' : 'blocks'}
        </span>
        <span className="text-[11px] text-muted-foreground/50">·</span>
        <span className="text-[11px] text-muted-foreground capitalize">{program.type}</span>
        {program.hevy_synced_at && (
          <>
            <span className="text-[11px] text-muted-foreground/50">·</span>
            <span className="text-[11px] text-green-600 dark:text-green-400">Synced to Hevy</span>
          </>
        )}
      </div>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Programs panel — detail view sub-components
// ---------------------------------------------------------------------------

function formatRest(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`
}

function ExerciseRow({ exercise, index }: { exercise: ProgramExercise; index: number }) {
  const title = exercise.exercise_title ?? `Exercise ${index + 1}`
  const sets = exercise.sets != null ? String(exercise.sets) : null
  const reps = exercise.reps != null ? String(exercise.reps) : null
  const rest = exercise.rest_seconds != null ? formatRest(exercise.rest_seconds) : null

  return (
    <div className="flex flex-col gap-1 py-2 border-b last:border-0" data-exercise-row>
      <p className="text-xs font-medium leading-snug">{title}</p>
      <div className="flex items-center flex-wrap gap-x-3 gap-y-1">
        {sets && reps && (
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Repeat className="h-3 w-3 shrink-0" aria-hidden="true" />
            {sets} x {reps}
          </span>
        )}
        {sets && !reps && (
          <span className="text-[11px] text-muted-foreground">{sets} sets</span>
        )}
        {rest && (
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Timer className="h-3 w-3 shrink-0" aria-hidden="true" />
            {rest} rest
          </span>
        )}
      </div>
      {exercise.notes && (
        <p className="text-[11px] text-muted-foreground/70 italic leading-snug">{exercise.notes}</p>
      )}
    </div>
  )
}

function SessionCard({ session, index }: { session: ProgramSession; index: number }) {
  const [open, setOpen] = useState(false)
  const label = session.day_label ?? `Day ${index + 1}`
  const exerciseCount = session.exercises?.length ?? 0

  return (
    <div className="rounded-md border overflow-hidden" data-session-card>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-muted/40 transition-colors"
        aria-expanded={open}
        data-print-hide
      >
        <span className="text-xs font-medium">{label}</span>
        <span className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] text-muted-foreground">{exerciseCount} exercise{exerciseCount !== 1 ? 's' : ''}</span>
          {open
            ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          }
        </span>
      </button>
      <div className={cn('px-3 pb-1 bg-muted/20', !open && 'hidden')} data-session-body>
        {exerciseCount === 0 ? (
          <p className="text-[11px] text-muted-foreground py-2">No exercises listed.</p>
        ) : (
          session.exercises!.map((ex, i) => (
            <ExerciseRow key={i} exercise={ex} index={i} />
          ))
        )}
      </div>
    </div>
  )
}

function BlockCard({ block, blockIndex }: { block: ProgramBlock; blockIndex: number }) {
  const sessionCount = block.sessions?.length ?? 0

  return (
    <section aria-label={block.name}>
      {/* Block header */}
      <div className="mb-2">
        <h4 className="text-sm font-semibold">{block.name}</h4>
        <div className="flex gap-3 mt-0.5 flex-wrap">
          {block.duration_weeks != null && (
            <span className="text-[11px] text-muted-foreground">
              {block.duration_weeks} {block.duration_weeks === 1 ? 'week' : 'weeks'}
            </span>
          )}
          {block.days_per_week != null && (
            <span className="text-[11px] text-muted-foreground">{block.days_per_week} days/week</span>
          )}
          {sessionCount > 0 && (
            <span className="text-[11px] text-muted-foreground">{sessionCount} sessions</span>
          )}
        </div>
      </div>

      {/* Sessions */}
      {sessionCount === 0 ? (
        <p className="text-xs text-muted-foreground">No sessions defined.</p>
      ) : (
        <div className="space-y-1.5">
          {block.sessions!.map((session, j) => (
            <SessionCard key={j} session={session} index={j} />
          ))}
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Programs panel — detail view
// ---------------------------------------------------------------------------

function ProgramDetail({
  programId,
  onBack,
}: {
  programId: string
  onBack: () => void
}) {
  const queryClient = useQueryClient()
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<{ ok: boolean; message: string } | null>(null)

  const { data: program, isLoading } = useQuery({
    queryKey: ['workout-program', programId],
    queryFn: () => getWorkoutProgram(programId),
  })

  async function handleSyncToHevy() {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await syncProgramToHevy(programId)
      setSyncResult({ ok: true, message: res.message ?? 'Synced successfully' })
      queryClient.invalidateQueries({ queryKey: ['workout-programs'] })
      queryClient.invalidateQueries({ queryKey: ['workout-program', programId] })
    } catch (err) {
      setSyncResult({ ok: false, message: err instanceof Error ? err.message : 'Sync failed' })
    } finally {
      setSyncing(false)
    }
  }

  function handleExportPdf() {
    if (program) handlePrintPdf(program)
  }

  if (isLoading) {
    return (
      <div className="flex flex-col h-full p-4 gap-3">
        <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground w-fit">
          <ChevronLeft className="h-4 w-4" /> Back
        </button>
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (!program) return null

  const blocks: ProgramBlock[] = program.blocks ?? []

  return (
    <div id="program-print-root" className="flex flex-col h-full overflow-hidden">
      {/* Header — hidden during print via data-print-hide */}
      <div className="p-4 border-b shrink-0" data-print-hide>
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-3"
        >
          <ChevronLeft className="h-3.5 w-3.5" /> All programs
        </button>
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-semibold leading-tight">{program.name}</h3>
          <div className="flex gap-1 shrink-0">
            {program.is_active && <Badge variant="default" className="text-[10px] px-1.5 py-0 h-4">Active</Badge>}
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 capitalize">{program.type}</Badge>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-3 mt-1">
          {program.goal_type && (
            <p className="text-xs text-muted-foreground">
              Goal: {GOAL_LABELS[program.goal_type] ?? program.goal_type}
            </p>
          )}
          {blocks.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {blocks.length} {blocks.length === 1 ? 'block' : 'blocks'}
            </p>
          )}
        </div>
      </div>

      <div id="program-print-target" className="flex-1 overflow-y-auto p-4 space-y-6">
        {blocks.length === 0 && (
          <p className="text-xs text-muted-foreground">No program data available.</p>
        )}
        {blocks.map((block, i) => (
          <BlockCard key={i} block={block} blockIndex={i} />
        ))}
      </div>

      {/* Action buttons — hidden during print via data-print-hide */}
      <div className="p-4 border-t space-y-2 shrink-0" data-print-hide>
        {syncResult && (
          <p className={cn(
            'text-xs px-2 py-1.5 rounded',
            syncResult.ok
              ? 'text-green-700 bg-green-50 dark:text-green-300 dark:bg-green-950'
              : 'text-destructive bg-destructive/10',
          )}>
            {syncResult.message}
          </p>
        )}

        {program.type === 'hevy' && (
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={handleSyncToHevy}
            disabled={syncing}
          >
            <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', syncing && 'animate-spin')} />
            {syncing ? 'Syncing…' : program.hevy_synced_at ? 'Re-sync to Hevy' : 'Sync to Hevy'}
          </Button>
        )}

        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={handleExportPdf}
        >
          <Download className="h-3.5 w-3.5 mr-1.5" />
          Export to PDF
        </Button>

        <Button variant="outline" size="sm" className="w-full" disabled title="Coming soon">
          <Mail className="h-3.5 w-3.5 mr-1.5" />
          Email to me
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Programs panel (container)
// ---------------------------------------------------------------------------

function ProgramsPanel({ onClose }: { onClose: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: programs, isLoading } = useQuery({
    queryKey: ['workout-programs'],
    queryFn: getWorkoutPrograms,
  })

  return (
    <div className="flex flex-col h-full border-l bg-background">
      {/* Panel header — hidden in print; the program name is repeated in the print-only header */}
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0" data-print-hide>
        <div className="flex items-center gap-2">
          <LayoutList className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Programs</span>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      {selectedId ? (
        <ProgramDetail programId={selectedId} onBack={() => setSelectedId(null)} />
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {isLoading && (
            <>
              <Skeleton className="h-16 w-full rounded-lg" />
              <Skeleton className="h-16 w-full rounded-lg" />
            </>
          )}
          {!isLoading && programs?.length === 0 && (
            <p className="text-xs text-muted-foreground px-2 py-4 text-center">
              No programs yet. Chat with the builder to generate your first program.
            </p>
          )}
          {programs?.map((p) => (
            <ProgramListItem
              key={p.id}
              program={p}
              isViewing={selectedId === p.id}
              onClick={() => setSelectedId(p.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function WorkoutBuilderPage() {
  const { messages, isStreaming, streamingTool } = useWorkoutBuilderStore()
  const { sendMessage, stop } = useWorkoutBuilderMessage()
  const [input, setInput] = useState('')
  const [panelOpen, setPanelOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [input])

  const handleSend = useCallback(() => {
    if (!input.trim() || isStreaming) return
    sendMessage(input)
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }, [input, isStreaming, sendMessage])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const showTypingIndicator =
    isStreaming && (messages[messages.length - 1]?.role !== 'ai' || streamingTool !== null)

  return (
    <div className="flex h-full overflow-hidden">
      {/* Chat panel */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
          <div className="flex items-center gap-2">
            <Dumbbell className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold">Workout Builder</span>
          </div>
          <Button
            variant={panelOpen ? 'secondary' : 'outline'}
            size="sm"
            className="gap-1.5 text-xs h-7"
            onClick={() => setPanelOpen((v) => !v)}
          >
            <LayoutList className="h-3.5 w-3.5" />
            Programs
          </Button>
        </div>

        {/* Messages */}
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center h-full gap-6">
              <div className="text-center space-y-1">
                <Dumbbell className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm font-medium">Your personal S&amp;C coach</p>
                <p className="text-xs text-muted-foreground">
                  Describe your training goal and I'll build a personalised program.
                </p>
              </div>
              <div className="flex flex-col gap-2 w-full max-w-sm">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => sendMessage(prompt)}
                    className="text-left text-sm px-4 py-2.5 rounded-xl border hover:bg-muted/60 transition-colors text-muted-foreground hover:text-foreground"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn('flex flex-col', msg.role === 'human' ? 'items-end' : 'items-start')}
            >
              <div
                className={cn(
                  'rounded-2xl px-4 py-3 text-sm leading-relaxed',
                  msg.role === 'human'
                    ? 'max-w-[80%] bg-primary text-primary-foreground whitespace-pre-wrap'
                    : 'w-full md:w-3/4 bg-muted text-foreground prose prose-sm prose-neutral dark:prose-invert max-w-none',
                )}
              >
                {msg.role === 'human' ? (
                  msg.text
                ) : (
                  <Markdown options={{ overrides: MARKDOWN_OVERRIDES }}>{msg.text}</Markdown>
                )}
              </div>
            </div>
          ))}

          {showTypingIndicator && <TypingIndicator tool={streamingTool} />}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="shrink-0 border-t px-4 py-3">
          <div className="flex items-end gap-2 rounded-xl border bg-background px-3 py-2 focus-within:ring-2 focus-within:ring-ring">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe your training goal…"
              rows={1}
              disabled={isStreaming}
              className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50 leading-relaxed py-0.5"
              style={{ minHeight: '24px', maxHeight: '160px' }}
            />
            {isStreaming ? (
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 shrink-0 rounded-lg"
                onClick={stop}
                aria-label="Stop"
              >
                <Square className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button
                size="icon"
                className="h-7 w-7 shrink-0 rounded-lg"
                onClick={handleSend}
                disabled={!input.trim()}
                aria-label="Send"
              >
                <ArrowUp className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Programs panel (desktop) */}
      {panelOpen && (
        <div className="hidden md:flex w-80 shrink-0 flex-col overflow-hidden">
          <ProgramsPanel onClose={() => setPanelOpen(false)} />
        </div>
      )}

      {/* Programs panel overlay (mobile) */}
      {panelOpen && (
        <div className="md:hidden fixed inset-0 z-30 flex">
          <div
            className="flex-1 bg-black/40"
            onClick={() => setPanelOpen(false)}
          />
          <div className="w-80 flex flex-col overflow-hidden bg-background shadow-xl">
            <ProgramsPanel onClose={() => setPanelOpen(false)} />
          </div>
        </div>
      )}
    </div>
  )
}
