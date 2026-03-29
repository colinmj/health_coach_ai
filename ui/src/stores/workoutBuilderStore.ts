import { create } from 'zustand'
import type { Message } from '@/types'

interface WBState {
  messages: Message[]
  activeSessionId: number | null
  isStreaming: boolean
  streamingTool: string | null
  addMessage: (m: Message) => void
  appendToken: (t: string) => void
  setIsStreaming: (v: boolean) => void
  setStreamingTool: (name: string | null) => void
  setActiveSessionId: (id: number) => void
  reset: () => void
}

export const useWorkoutBuilderStore = create<WBState>((set) => ({
  messages: [],
  activeSessionId: null,
  isStreaming: false,
  streamingTool: null,

  addMessage: (m) => set((state) => ({ messages: [...state.messages, m] })),

  appendToken: (t) =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last?.role === 'ai') {
        messages[messages.length - 1] = { ...last, text: last.text + t }
      } else {
        messages.push({ role: 'ai', text: t })
      }
      return { messages, streamingTool: null }
    }),

  setIsStreaming: (isStreaming) => set({ isStreaming }),
  setStreamingTool: (streamingTool) => set({ streamingTool }),
  setActiveSessionId: (id) => set({ activeSessionId: id }),

  reset: () => set({ messages: [], activeSessionId: null, isStreaming: false, streamingTool: null }),
}))
