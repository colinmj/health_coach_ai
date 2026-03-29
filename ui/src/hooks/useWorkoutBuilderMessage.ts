import { useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWorkoutBuilderStore } from '@/stores/workoutBuilderStore'
import { streamWorkoutBuilder } from '@/lib/api'

interface UseWorkoutBuilderMessageReturn {
  sendMessage: (query: string) => void
  stop: () => void
  isStreaming: boolean
}

export function useWorkoutBuilderMessage(): UseWorkoutBuilderMessageReturn {
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
  } = useWorkoutBuilderStore()

  function sendMessage(query: string) {
    const trimmed = query.trim()
    if (!trimmed || isStreaming) return

    addMessage({ role: 'human', text: trimmed })
    setIsStreaming(true)
    setStreamingTool(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    const sessionId = useWorkoutBuilderStore.getState().activeSessionId

    streamWorkoutBuilder(
      trimmed,
      sessionId,
      {
        onToken: appendToken,
        onToolStart: (name) => setStreamingTool(name),
        onDone: (sid) => {
          setActiveSessionId(sid)
          setIsStreaming(false)
          setStreamingTool(null)
          queryClient.invalidateQueries({ queryKey: ['workout-programs'] })
        },
        onError: (err) => {
          console.error('[workout builder stream error]', err)
          addMessage({ role: 'ai', text: 'Sorry, something went wrong. Please try again.' })
          setIsStreaming(false)
          setStreamingTool(null)
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
