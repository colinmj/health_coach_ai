import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { Message, Session, StreamEvent, SyncStatus } from '@/types'

const BASE = '/api'

export async function getSessions(): Promise<Session[]> {
  const res = await fetch(`${BASE}/sessions/`)
  if (!res.ok) throw new Error('Failed to fetch sessions')
  return res.json()
}

export async function getMessages(sessionId: number): Promise<Message[]> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/messages`)
  if (!res.ok) throw new Error('Failed to fetch messages')
  return res.json()
}

export async function getSyncStatus(): Promise<SyncStatus> {
  const res = await fetch(`${BASE}/sync/status`)
  if (!res.ok) throw new Error('Failed to fetch sync status')
  return res.json()
}

export async function triggerSync(): Promise<void> {
  const res = await fetch(`${BASE}/sync/trigger`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to trigger sync')
}

export function streamChat(
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
  fetchEventSource(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id: sessionId }),
    signal,
    onmessage(ev) {
      const event: StreamEvent = JSON.parse(ev.data)
      if (event.type === 'token' && event.text) handlers.onToken(event.text)
      else if (event.type === 'tool_start' && event.name) handlers.onToolStart(event.name)
      else if (event.type === 'done' && event.session_id != null) handlers.onDone(event.session_id)
      else if (event.type === 'error') handlers.onError(new Error(event.error ?? 'Stream error'))
    },
    onerror(err) {
      handlers.onError(err instanceof Error ? err : new Error('Stream failed'))
      throw err
    },
  })
}
