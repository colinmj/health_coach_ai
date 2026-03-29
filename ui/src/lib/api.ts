import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { ConfirmRequiredEvent, Message, Session, StreamEvent, SyncIntegration, Goal, Insight } from '@/types'
import { useAuthStore } from '@/stores/authStore'

const BASE = '/api'

function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers as Record<string, string> | undefined) },
  })
}

// Auth
export async function registerUser(email: string, password: string): Promise<{ token: string; user_id: number }> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Registration failed')
  }
  return res.json()
}

export async function loginUser(email: string, password: string): Promise<{ token: string; user_id: number; has_integrations: boolean }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Login failed')
  }
  return res.json()
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

// Insights
export async function getInsights(): Promise<Insight[]> {
  const res = await apiFetch(`${BASE}/insights/`)
  if (!res.ok) throw new Error('Failed to fetch insights')
  return res.json()
}

// Chat
export function streamChat(
  query: string,
  sessionId: number | null,
  handlers: {
    onToken: (token: string) => void
    onToolStart: (name: string) => void
    onDone: (sessionId: number) => void
    onError: (err: Error) => void
    onSuggestedQuestions: (questions: string[]) => void
    onConfirmRequired?: (event: ConfirmRequiredEvent) => void
  },
  signal: AbortSignal,
  confirmed = false,
) {
  let doneReceived = false

  fetchEventSource(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ query, session_id: sessionId, confirmed }),
    signal,
    onmessage(ev) {
      const event: StreamEvent = JSON.parse(ev.data)
      if (event.type === 'token' && event.text) handlers.onToken(event.text)
      else if (event.type === 'tool_start' && event.name) handlers.onToolStart(event.name)
      else if (event.type === 'suggested_questions' && event.questions) handlers.onSuggestedQuestions(event.questions)
      else if (event.type === 'done' && event.session_id != null) { doneReceived = true; handlers.onDone(event.session_id) }
      else if (event.type === 'error') handlers.onError(new Error(event.error ?? 'Stream error'))
      else if (event.type === 'confirm_required' && handlers.onConfirmRequired) {
        handlers.onConfirmRequired(event as ConfirmRequiredEvent)
      }
    },
    onclose() {
      if (!doneReceived) handlers.onError(new Error('Stream closed unexpectedly'))
    },
    onerror(err) {
      if (err instanceof Error && err.name === 'AbortError') throw err // intentional stop
      handlers.onError(err instanceof Error ? err : new Error('Stream failed'))
      throw err
    },
  })
}
