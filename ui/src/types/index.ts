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

export type StreamEventType = 'tool_start' | 'token' | 'done' | 'error' | 'suggested_questions' | 'confirm_required' | 'stream_reset'

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

export interface Goal {
  id: number
  title: string | null
  goal_text: string
  domains: string[] | null
  target_date: string | null
  status: string
  created_at: string
  actions: Action[]
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

export interface ProgramExercise {
  exercise_template_id?: string
  exercise_title?: string
  sets?: number | string
  reps?: number | string
  rest_seconds?: number
  notes?: string
}

export interface ProgramSession {
  day_label?: string
  exercises?: ProgramExercise[]
}

export interface ProgramBlock {
  name: string
  duration_weeks?: number
  days_per_week?: number
  sessions?: ProgramSession[]
}

export interface TrainingProgram {
  id: string
  name: string
  type: 'hevy' | 'manual'
  goal_type: string | null
  training_iq_at_generation: string | null
  version: number
  is_active: boolean
  hevy_synced_at: string | null
  created_at: string
  block_count: number
  blocks?: ProgramBlock[]
}

export interface TrainingBlock {
  id: number
  name: string
  goal: string
  start_date: string
  end_date: string | null
  is_active: boolean
  notes: string | null
  created_at: string
}

export interface ManualWorkoutSet {
  set_index: number
  set_type: string
  weight_kg: number | null
  reps: number | null
  rpe: number | null
}

export interface ManualWorkoutExercise {
  name: string
  sets: ManualWorkoutSet[]
}

export interface ParsedWorkout {
  title: string | null
  date: string | null
  exercises: ManualWorkoutExercise[]
  warnings: string[]
}

export interface ManualWorkout {
  id: number
  title: string | null
  start_time: string | null
  logged_at: string
}
