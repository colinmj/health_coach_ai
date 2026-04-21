import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { ConfirmRequiredEvent, ManualWorkout, Message, ParsedWorkout, Session, StreamEvent, SyncIntegration, Goal, Insight, TrainingProgram, TrainingBlock } from '@/types'

const BASE = '/api'

// Clerk token getter — wired up by ClerkTokenBridge in main.tsx
let _getToken: () => Promise<string | null> = async () => null

export function setClerkTokenGetter(fn: () => Promise<string | null>) {
  _getToken = fn
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await _getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = await authHeaders()
  return fetch(url, {
    ...init,
    headers: { ...headers, ...(init.headers as Record<string, string> | undefined) },
  })
}

// Auth
export async function startOAuth(provider: string): Promise<void> {
  const res = await apiFetch(`${BASE}/oauth/${provider}/start`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `OAuth start failed for ${provider}`)
  }
  const { url } = await res.json()
  if (!url) throw new Error(`No redirect URL returned for ${provider}`)
  window.location.href = url
}

export async function deleteAccount(): Promise<void> {
  const res = await apiFetch(`${BASE}/auth/account`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Failed to delete account')
  }
}

// Profile
export async function getProfile(): Promise<Record<string, unknown>> {
  const res = await apiFetch(`${BASE}/profile/`)
  if (!res.ok) throw new Error('Failed to fetch profile')
  return res.json()
}

export async function updateProfile(data: Record<string, unknown>): Promise<void> {
  const res = await apiFetch(`${BASE}/profile/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update profile')
}

// Integrations
export async function getAvailableIntegrations(): Promise<object[]> {
  const res = await apiFetch(`${BASE}/integrations/available`)
  if (!res.ok) throw new Error('Failed to fetch integrations')
  return res.json()
}

export async function createIntegrations(sources: string[], credentials: Record<string, string> = {}): Promise<{ created: number }> {
  const res = await apiFetch(`${BASE}/integrations/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sources, credentials }),
  })
  if (!res.ok) throw new Error('Failed to save integrations')
  return res.json()
}

export async function saveDataImports(assignments: Record<string, string>): Promise<{ saved: number }> {
  const res = await apiFetch(`${BASE}/integrations/data-imports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assignments }),
  })
  if (!res.ok) throw new Error('Failed to save data imports')
  return res.json()
}

export async function deleteIntegration(source: string): Promise<void> {
  const res = await apiFetch(`${BASE}/integrations/${source}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error('Failed to disconnect integration')
}

export async function getDataImports(): Promise<Record<string, string>> {
  const res = await apiFetch(`${BASE}/integrations/data-imports`)
  if (!res.ok) throw new Error('Failed to fetch data imports')
  return res.json()
}

// Sessions
export async function getSessions(): Promise<Session[]> {
  const res = await apiFetch(`${BASE}/sessions/`)
  if (!res.ok) throw new Error('Failed to fetch sessions')
  return res.json()
}

export async function deleteSession(sessionId: number): Promise<void> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error('Failed to delete session')
}

export async function updateSession(
  sessionId: number,
  body: { title?: string | null; pinned?: boolean },
): Promise<Session> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed to update session')
  return res.json()
}

export async function getMessages(sessionId: number): Promise<Message[]> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}/messages`)
  if (!res.ok) throw new Error('Failed to fetch messages')
  return res.json()
}

// Sync
export async function getSyncStatus(): Promise<SyncIntegration[]> {
  const res = await apiFetch(`${BASE}/sync/status`)
  if (!res.ok) throw new Error('Failed to fetch sync status')
  return res.json()
}

export async function triggerSync(): Promise<void> {
  const res = await apiFetch(`${BASE}/sync/trigger`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to trigger sync')
}

type UploadCsvResult =
  | { rows_imported: number }
  | { inserted: number; days: number }

export async function uploadCsvFile(file: File): Promise<UploadCsvResult> {
  const form = new FormData()
  form.append('file', file)
  const res = await apiFetch(`${BASE}/sync/upload-csv`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Upload failed')
  }
  return res.json()
}

export async function uploadAppleHealthFile(file: File): Promise<{ rows_imported: number }> {
  const form = new FormData()
  form.append('file', file)
  const res = await apiFetch(`${BASE}/sync/upload-apple-health`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Upload failed')
  }
  return res.json()
}

export interface FormFinding {
  aspect: string
  severity: 'ok' | 'warning' | 'error'
  note: string
}

export interface FormAnalysisResult {
  overall_rating: 'good' | 'needs_work' | 'safety_concern'
  findings: FormFinding[]
  cues: string[]
  frame_count: number
}

export interface FormAnalysis extends FormAnalysisResult {
  id: number
  exercise_name: string
  video_date: string
  recovery_score_day_of: number | null
  created_at: string
}

export async function uploadLiftingVideo(exerciseName: string, file: File): Promise<FormAnalysisResult> {
  const form = new FormData()
  form.append('exercise_name', exerciseName)
  form.append('file', file)
  const res = await apiFetch(`${BASE}/sync/upload-video`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Analysis failed')
  }
  return res.json()
}

export async function getFormAnalyses(): Promise<FormAnalysis[]> {
  const res = await apiFetch(`${BASE}/sync/form-analyses`)
  if (!res.ok) throw new Error('Failed to fetch form analyses')
  return res.json()
}

// Goals
export async function getGoals(): Promise<Goal[]> {
  const res = await apiFetch(`${BASE}/goals/`)
  if (!res.ok) throw new Error('Failed to fetch goals')
  return res.json()
}

export async function getGoal(id: number): Promise<Goal> {
  const res = await apiFetch(`${BASE}/goals/${id}`)
  if (!res.ok) throw new Error('Failed to fetch goal')
  return res.json()
}

export async function deleteGoal(id: number): Promise<void> {
  const res = await apiFetch(`${BASE}/goals/${id}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error('Failed to delete goal')
}

// Insights
export async function getInsights(): Promise<Insight[]> {
  const res = await apiFetch(`${BASE}/insights/`)
  if (!res.ok) throw new Error('Failed to fetch insights')
  return res.json()
}

// Chat
export async function streamChat(
  query: string,
  sessionId: number | null,
  handlers: {
    onToken: (token: string) => void
    onToolStart: (name: string) => void
    onDone: (sessionId: number) => void
    onError: (err: Error) => void
    onSuggestedQuestions: (questions: string[]) => void
    onConfirmRequired?: (event: ConfirmRequiredEvent) => void
    onStreamReset?: () => void
  },
  signal: AbortSignal,
  confirmed = false,
) {
  let doneReceived = false
  let errorReceived = false
  const headers = await authHeaders()

  fetchEventSource(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify({ query, session_id: sessionId, confirmed }),
    signal,
    onmessage(ev) {
      const event: StreamEvent = JSON.parse(ev.data)
      if (event.type === 'token' && event.text) handlers.onToken(event.text)
      else if (event.type === 'tool_start' && event.name) handlers.onToolStart(event.name)
      else if (event.type === 'suggested_questions' && event.questions) handlers.onSuggestedQuestions(event.questions)
      else if (event.type === 'done' && event.session_id != null) { doneReceived = true; handlers.onDone(event.session_id) }
      else if (event.type === 'error') { errorReceived = true; handlers.onError(new Error(event.error ?? 'Stream error')) }
      else if (event.type === 'confirm_required' && handlers.onConfirmRequired) {
        handlers.onConfirmRequired(event as ConfirmRequiredEvent)
      }
      else if (event.type === 'stream_reset') handlers.onStreamReset?.()
    },
    onclose() {
      if (!doneReceived && !errorReceived) handlers.onError(new Error('Stream closed unexpectedly'))
    },
    onerror(err) {
      if (err instanceof Error && err.name === 'AbortError') throw err // intentional stop
      handlers.onError(err instanceof Error ? err : new Error('Stream failed'))
      throw err
    },
  })
}

// Workout Builder
export async function streamWorkoutBuilder(
  query: string,
  sessionId: number | null,
  handlers: {
    onToken: (token: string) => void
    onToolStart: (name: string) => void
    onDone: (sessionId: number) => void
    onError: (err: Error) => void
  },
  signal: AbortSignal,
) {
  let doneReceived = false
  let errorReceived = false
  const headers = await authHeaders()

  fetchEventSource(`${BASE}/workout-builder/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify({ query, session_id: sessionId }),
    signal,
    onmessage(ev) {
      const event: StreamEvent = JSON.parse(ev.data)
      if (event.type === 'token' && event.text) handlers.onToken(event.text)
      else if (event.type === 'tool_start' && event.name) handlers.onToolStart(event.name)
      else if (event.type === 'done' && event.session_id != null) { doneReceived = true; handlers.onDone(event.session_id) }
      else if (event.type === 'error') { errorReceived = true; handlers.onError(new Error(event.error ?? 'Stream error')) }
    },
    onclose() {
      if (!doneReceived && !errorReceived) handlers.onError(new Error('Stream closed unexpectedly'))
    },
    onerror(err) {
      if (err instanceof Error && err.name === 'AbortError') throw err
      handlers.onError(err instanceof Error ? err : new Error('Stream failed'))
      throw err
    },
  })
}

export async function getWorkoutPrograms(): Promise<TrainingProgram[]> {
  const res = await apiFetch(`${BASE}/workout-builder/programs`)
  if (!res.ok) throw new Error('Failed to fetch programs')
  return res.json()
}

export async function getWorkoutProgram(id: string): Promise<TrainingProgram> {
  const res = await apiFetch(`${BASE}/workout-builder/programs/${id}`)
  if (!res.ok) throw new Error('Failed to fetch program')
  return res.json()
}

export async function syncSessionToHevy(
  programId: string,
  blockIndex: number,
  sessionIndex: number,
): Promise<{ routine_title: string; created: boolean; skipped: boolean }> {
  const res = await apiFetch(`${BASE}/workout-builder/programs/${programId}/sync-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ block_index: blockIndex, session_index: sessionIndex }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Hevy session sync failed')
  }
  return res.json()
}

export async function syncProgramToHevy(programId: string): Promise<{ message: string }> {
  const res = await apiFetch(`${BASE}/workout-builder/programs/${programId}/sync-to-hevy`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Hevy sync failed')
  }
  return res.json()
}

export async function deleteWorkoutProgram(programId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/workout-builder/programs/${programId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete program')
}

export async function getTrainingBlocks(): Promise<TrainingBlock[]> {
  const res = await apiFetch(`${BASE}/workout-builder/blocks`)
  if (!res.ok) throw new Error('Failed to fetch blocks')
  return res.json()
}

// Manual Workout
export async function parseManualWorkout(
  text: string | null,
  file: File | null,
): Promise<{ parsed: ParsedWorkout; warnings: string[] }> {
  const form = new FormData()
  if (text !== null) form.append('text', text)
  if (file !== null) form.append('file', file)
  // Do NOT set Content-Type manually — let the browser set the multipart boundary
  const res = await apiFetch(`${BASE}/manual-workout/parse`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Parse failed')
  }
  return res.json()
}

export async function saveManualWorkout(
  parsed: ParsedWorkout,
): Promise<{ workout_id: number }> {
  const res = await apiFetch(`${BASE}/manual-workout/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parsed }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Save failed')
  }
  return res.json()
}

export async function getManualWorkouts(): Promise<ManualWorkout[]> {
  const res = await apiFetch(`${BASE}/manual-workout/`)
  if (!res.ok) throw new Error('Failed to fetch manual workouts')
  return res.json()
}

export async function deleteManualWorkout(id: number): Promise<void> {
  const res = await apiFetch(`${BASE}/manual-workout/${id}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error('Failed to delete workout')
}

// Progress Photos
export interface ProgressPhoto {
  id: number
  url: string
  taken_at: string
  notes: string | null
  created_at: string
}

export async function uploadProgressPhoto(
  file: File,
  takenAt?: string,
  notes?: string,
): Promise<{ photo_id: number; taken_at: string }> {
  const form = new FormData()
  form.append('file', file)
  if (takenAt) form.append('taken_at', takenAt)
  if (notes) form.append('notes', notes)
  const res = await apiFetch(`${BASE}/progress-photos/`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Upload failed')
  }
  return res.json()
}

export interface ProgressPhotosPage {
  total: number
  page: number
  page_size: number
  photos: ProgressPhoto[]
}

export async function deleteProgressPhoto(id: number): Promise<void> {
  const res = await apiFetch(`${BASE}/progress-photos/${id}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error('Failed to delete photo')
}

export async function getProgressPhotos(page = 1): Promise<ProgressPhotosPage> {
  const res = await apiFetch(`${BASE}/progress-photos/?page=${page}`)
  if (!res.ok) throw new Error('Failed to fetch progress photos')
  return res.json()
}
