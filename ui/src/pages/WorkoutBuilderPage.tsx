import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Markdown from 'markdown-to-jsx'
import { ArrowUp, Square, ChevronLeft, X, Dumbbell, LayoutList, RefreshCw, Download, Mail } from 'lucide-react'
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
import type { TrainingProgram } from '@/types'

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

function ProgramListItem({
  program,
  onClick,
}: {
  program: TrainingProgram
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
      className="w-full text-left px-3 py-3 rounded-lg hover:bg-muted/60 transition-colors border border-transparent hover:border-border group"
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
// Programs panel — detail view
// ---------------------------------------------------------------------------

interface BlockEntry {
  name: string
  duration_weeks?: number
  days_per_week?: number
  sessions?: { day_label?: string; exercises?: unknown[] }[]
}

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

  if (isLoading) {
    return (
      <div className="flex flex-col h-full p-4 gap-3">
        <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground w-fit">
          <ChevronLeft className="h-4 w-4" /> Back
        </button>
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (!program) return null

  const blocks = (program.blocks as BlockEntry[] | undefined) ?? []

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b shrink-0">
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
        {program.goal_type && (
          <p className="text-xs text-muted-foreground mt-1">
            Goal: {GOAL_LABELS[program.goal_type] ?? program.goal_type}
          </p>
        )}
      </div>

      {/* Blocks summary */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {blocks.length === 0 && (
          <p className="text-xs text-muted-foreground">No blocks data available.</p>
        )}
        {blocks.map((block, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-1">
            <p className="text-sm font-medium">{block.name}</p>
            <div className="flex gap-3 text-xs text-muted-foreground">
              {block.duration_weeks != null && (
                <span>{block.duration_weeks} {block.duration_weeks === 1 ? 'week' : 'weeks'}</span>
              )}
              {block.days_per_week != null && (
                <span>{block.days_per_week} days/week</span>
              )}
              {block.sessions != null && (
                <span>{block.sessions.length} sessions</span>
              )}
            </div>
            {block.sessions && block.sessions.length > 0 && (
              <div className="mt-2 space-y-0.5">
                {block.sessions.map((s, j) => (
                  <div key={j} className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{s.day_label ?? `Day ${j + 1}`}</span>
                    {s.exercises && (
                      <span className="text-muted-foreground/60">{s.exercises.length} exercises</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Action buttons */}
      <div className="p-4 border-t space-y-2 shrink-0">
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

        <Button variant="outline" size="sm" className="w-full" disabled title="Coming soon">
          <Download className="h-3.5 w-3.5 mr-1.5" />
          Download PDF
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
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
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
            <ProgramListItem key={p.id} program={p} onClick={() => setSelectedId(p.id)} />
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
