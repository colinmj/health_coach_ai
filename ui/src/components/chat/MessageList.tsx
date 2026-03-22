import { useEffect, useRef } from 'react'
import Markdown from 'markdown-to-jsx'
import { useChatStore } from '@/stores/chatStore'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function MessageList() {
  const { messages, isStreaming, streamingTool } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground text-sm">
        Ask me anything about your health data.
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={cn(
            'flex',
            msg.role === 'human' ? 'justify-end' : 'justify-start',
          )}
        >
          <div
            className={cn(
              'max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
              msg.role === 'human'
                ? 'bg-primary text-primary-foreground whitespace-pre-wrap'
                : 'bg-muted text-foreground prose prose-sm prose-neutral dark:prose-invert max-w-none',
            )}
          >
            {msg.role === 'human' ? (
              msg.text
            ) : (
              <Markdown
                options={{
                  overrides: {
                    code: {
                      props: { className: 'bg-background rounded px-1 py-0.5 text-xs font-mono' },
                    },
                    pre: {
                      props: { className: 'bg-background rounded-lg p-3 overflow-x-auto text-xs font-mono my-2' },
                    },
                    a: {
                      props: { className: 'text-primary underline underline-offset-2', target: '_blank', rel: 'noreferrer' },
                    },
                  },
                }}
              >
                {msg.text}
              </Markdown>
            )}
          </div>
        </div>
      ))}

      {isStreaming && streamingTool && (
        <div className="flex justify-start">
          <Badge variant="secondary" className="animate-pulse text-xs">
            {streamingTool}...
          </Badge>
        </div>
      )}

      {isStreaming && !streamingTool && messages[messages.length - 1]?.role !== 'ai' && (
        <div className="flex justify-start gap-2">
          <Skeleton className="h-4 w-48 rounded-full" />
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
