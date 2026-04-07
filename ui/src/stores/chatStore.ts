import { create } from 'zustand'
import type { ConfirmRequiredEvent, Message, Session } from '@/types'

interface ConfirmState {
  open: boolean
  event: ConfirmRequiredEvent | null
  pendingQuery: string
  pendingSessionId: number | null
}

interface ChatState {
  // Sessions
  sessions: Session[]
  activeSessionId: number | null
  setSessions: (sessions: Session[]) => void
  setActiveSessionId: (id: number | null) => void

  // Messages for the active session
  messages: Message[]
  setMessages: (messages: Message[]) => void
  appendToken: (token: string) => void
  addMessage: (message: Message) => void
  clearLastAiMessage: () => void

  // Streaming
  isStreaming: boolean
  streamingTool: string | null
  setIsStreaming: (streaming: boolean) => void
  setStreamingTool: (tool: string | null) => void

  // Follow-up question chips
  suggestedQuestions: string[]
  setSuggestedQuestions: (questions: string[]) => void
  clearSuggestedQuestions: () => void

  // Confirmation modal state
  confirmState: ConfirmState
  setConfirmState: (state: ConfirmState) => void
  clearConfirmState: () => void

  // Start a new chat (clear active session)
  startNewChat: () => void

  // Reset all state (used on logout)
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  sessions: [],
  activeSessionId: null,
  setSessions: (sessions) => set({ sessions }),
  setActiveSessionId: (id) => set({ activeSessionId: id }),

  messages: [],
  setMessages: (messages) => set({ messages }),
  appendToken: (token) =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last?.role === 'ai') {
        const newText = (last.text + token).replace(/([.!?])([A-Z])/g, '$1 $2')
        messages[messages.length - 1] = { ...last, text: newText }
      } else {
        messages.push({ role: 'ai', text: token })
      }
      return { messages, streamingTool: null }
    }),
  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  clearLastAiMessage: () =>
    set((state) => {
      const messages = [...state.messages]
      if (messages[messages.length - 1]?.role === 'ai') {
        messages.pop()
      }
      return { messages }
    }),

  isStreaming: false,
  streamingTool: null,
  setIsStreaming: (isStreaming) => set({ isStreaming }),
  setStreamingTool: (streamingTool) => set({ streamingTool }),

  suggestedQuestions: [],
  setSuggestedQuestions: (suggestedQuestions) => set({ suggestedQuestions }),
  clearSuggestedQuestions: () => set({ suggestedQuestions: [] }),

  confirmState: { open: false, event: null, pendingQuery: '', pendingSessionId: null },
  setConfirmState: (confirmState) => set({ confirmState }),
  clearConfirmState: () => set({ confirmState: { open: false, event: null, pendingQuery: '', pendingSessionId: null } }),

  startNewChat: () =>
    set({ activeSessionId: null, messages: [], streamingTool: null, isStreaming: false, suggestedQuestions: [] }),

  reset: () =>
    set({ sessions: [], activeSessionId: null, messages: [], isStreaming: false, streamingTool: null, suggestedQuestions: [], confirmState: { open: false, event: null, pendingQuery: '', pendingSessionId: null } }),
}))
