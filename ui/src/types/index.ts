export interface Session {
  id: number
  title: string | null
  summary: string | null
  pinned: boolean
  created_at: string
}

export interface Message {
  role: 'human' | 'ai' | 'tool'
  text: string
}

export type StreamEventType = 'tool_start' | 'token' | 'done' | 'error' | 'suggested_questions' | 'confirm_required'

export interface ConfirmStats {
  last_run: string
  daily_used: number
  daily_limit: number | null
}

export interface ConfirmRequiredEvent {
  type: 'confirm_required'
  tool: string
  title: string
  body: string
  stats: ConfirmStats
  cached_result: string | null
}

export interface StreamEvent {
  type: StreamEventType
  text?: string
  name?: string
  session_id?: number
  error?: string
  questions?: string[]
  // confirm_required fields
  tool?: string
  title?: string
  body?: string
  stats?: ConfirmStats
  cached_result?: string | null
}

export interface Action {
  id: number
  action_text: string
  metric: string | null
  condition: string | null
  target_value: number | null
  data_source: string | null
  frequency: string | null
  created_at: string
}

export interface Protocol {
  id: number
  goal_id: number
  protocol_text: string
  start_date: string | null
  review_date: string | null
  status: string
  outcome: string | null
  actions: Action[]
}

export interface Goal {
  id: number
  title: string | null
  goal_text: string
  domains: string[] | null
  target_date: string | null
  status: string
  created_at: string
  protocols: Protocol[]
  direct_actions: Action[]
}

export interface Insight {
  id: number
  title: string | null
  insight: string
  correlative_tool: string | null
  effect: string | null
  confidence: string | null
  date_derived: string
  status: string
  pinned: boolean
  created_at: string
}

export interface SyncIntegration {
  source: string
  auth_type: 'oauth' | 'api_key' | 'upload'
  last_synced_at: string | null
  is_active: boolean
  authorized: boolean
  data_types: string[]
  label: string
}
