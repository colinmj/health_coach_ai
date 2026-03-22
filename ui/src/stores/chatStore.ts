import { create } from 'zustand'
import type { Message, Session } from '@/types'

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

  // Streaming
  isStreaming: boolean
  streamingTool: string | null
  setIsStreaming: (streaming: boolean) => void
  setStreamingTool: (tool: string | null) => void

  // Start a new chat (clear active session)
  startNewChat: () => void
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
        messages[messages.length - 1] = { ...last, text: last.text + token }
      } else {
        messages.push({ role: 'ai', text: token })
      }
      return { messages }
    }),
  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  isStreaming: false,
  streamingTool: null,
  setIsStreaming: (isStreaming) => set({ isStreaming }),
  setStreamingTool: (streamingTool) => set({ streamingTool }),

  startNewChat: () =>
    set({ activeSessionId: null, messages: [], streamingTool: null, isStreaming: false }),
}))
