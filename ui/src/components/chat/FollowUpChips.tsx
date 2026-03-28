import { cn } from '@/lib/utils'
import { useChatStore } from '@/stores/chatStore'
import { useSendMessage } from '@/hooks/useSendMessage'

export function FollowUpChips() {
  const { suggestedQuestions, isStreaming } = useChatStore()
  const { sendMessage } = useSendMessage()

  if (isStreaming || suggestedQuestions.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2 pb-3">
      {suggestedQuestions.map((q) => (
        <button
          key={q}
          type="button"
          onClick={() => sendMessage(q)}
          className={cn(
            'rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground',
            'transition-colors hover:border-foreground/30 hover:text-foreground hover:bg-muted/50',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          )}
        >
          {q}
        </button>
      ))}
    </div>
  )
}
