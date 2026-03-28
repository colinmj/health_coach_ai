import { useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useChatStore } from '@/stores/chatStore'
import { streamChat } from '@/lib/api'

interface UseSendMessageReturn {
  sendMessage: (query: string) => void
  stop: () => void
  isStreaming: boolean
}

export function useSendMessage(): UseSendMessageReturn {
  const abortRef = useRef<AbortController | null>(null)
  const queryClient = useQueryClient()

  const {
    activeSessionId,
    isStreaming,
    addMessage,
    appendToken,
    setIsStreaming,
    setStreamingTool,
    setActiveSessionId,
    setSuggestedQuestions,
    clearSuggestedQuestions,
  } = useChatStore()

  function sendMessage(query: string) {
    const trimmed = query.trim()
    if (!trimmed || isStreaming) return

    clearSuggestedQuestions()
    addMessage({ role: 'human', text: trimmed })
    setIsStreaming(true)
    setStreamingTool(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    streamChat(
      trimmed,
      activeSessionId,
      {
        onToken: appendToken,
        onToolStart: (name) => setStreamingTool(name),
        onSuggestedQuestions: setSuggestedQuestions,
        onDone: (sessionId) => {
          setActiveSessionId(sessionId)
          setIsStreaming(false)
          setStreamingTool(null)
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
        },
        onError: () => {
          setIsStreaming(false)
          setStreamingTool(null)
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
        },
      },
      ctrl.signal,
    )
  }

  function stop() {
    abortRef.current?.abort()
    setIsStreaming(false)
    setStreamingTool(null)
  }

  return { sendMessage, stop, isStreaming }
}
