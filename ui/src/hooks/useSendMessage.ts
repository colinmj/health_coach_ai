import { useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useChatStore } from '@/stores/chatStore'
import { streamChat } from '@/lib/api'
import type { ConfirmRequiredEvent } from '@/types'

interface UseSendMessageReturn {
  sendMessage: (query: string, confirmed?: boolean) => void
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
    setConfirmState,
    clearConfirmState,
  } = useChatStore()

  function sendMessage(query: string, confirmed = false) {
    const trimmed = query.trim()
    if (!trimmed || isStreaming) return

    clearSuggestedQuestions()
    clearConfirmState()
    if (!confirmed) {
      // Only add the human message on the first send, not on confirmed re-run
      addMessage({ role: 'human', text: trimmed })
    }
    setIsStreaming(true)
    setStreamingTool(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    const sessionId = useChatStore.getState().activeSessionId

    streamChat(
      trimmed,
      sessionId,
      {
        onToken: appendToken,
        onToolStart: (name) => setStreamingTool(name),
        onSuggestedQuestions: setSuggestedQuestions,
        onDone: (sid) => {
          setActiveSessionId(sid)
          setIsStreaming(false)
          setStreamingTool(null)
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
        },
        onError: (err) => {
          console.error('[chat stream error]', err)
          addMessage({ role: 'ai', text: 'Sorry, something went wrong. Please try again.' })
          setIsStreaming(false)
          setStreamingTool(null)
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
        },
        onConfirmRequired: (event: ConfirmRequiredEvent) => {
          setIsStreaming(false)
          setStreamingTool(null)
          setConfirmState({
            open: true,
            event,
            pendingQuery: trimmed,
            pendingSessionId: sessionId,
          })
        },
      },
      ctrl.signal,
      confirmed,
    )
  }

  function stop() {
    abortRef.current?.abort()
    setIsStreaming(false)
    setStreamingTool(null)
  }

  return { sendMessage, stop, isStreaming }
}
