export interface Session {
  id: number
  title: string
  summary: string | null
  created_at: string
}

export interface Message {
  role: 'human' | 'ai' | 'tool'
  text: string
}

export type StreamEventType = 'tool_start' | 'token' | 'done' | 'error'

export interface StreamEvent {
  type: StreamEventType
  text?: string
  name?: string
  session_id?: number
  error?: string
}

export interface SyncStatus {
  [source: string]: string | null
}
