import { useRef, useState } from 'react'
import { useChatStore } from '@/stores/chatStore'
import { streamChat } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { ArrowUp, Square } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

export function ChatInput() {
  const [input, setInput] = useState('')
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
  } = useChatStore()

  function handleStop() {
    abortRef.current?.abort()
    setIsStreaming(false)
    setStreamingTool(null)
  }

  function handleSubmit() {
    const query = input.trim()
    if (!query || isStreaming) return

    setInput('')
    addMessage({ role: 'human', text: query })
    setIsStreaming(true)
    setStreamingTool(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    streamChat(
      query,
      activeSessionId,
      {
        onToken: appendToken,
        onToolStart: (name) => setStreamingTool(name),
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

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t bg-background px-4 py-4">
      <div className="relative flex items-end gap-2 rounded-2xl border bg-muted/30 px-4 py-3">
        <textarea
          className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          placeholder="Ask about your workouts, sleep, nutrition..."
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          style={{ maxHeight: '160px', overflowY: 'auto' }}
          onInput={(e) => {
            const el = e.currentTarget
            el.style.height = 'auto'
            el.style.height = `${Math.min(el.scrollHeight, 160)}px`
          }}
        />
        {isStreaming ? (
          <Button size="icon" variant="destructive" className="shrink-0" onClick={handleStop}>
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            className="shrink-0"
            onClick={handleSubmit}
            disabled={!input.trim()}
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Shift+Enter for new line · Enter to send
      </p>
    </div>
  )
}
