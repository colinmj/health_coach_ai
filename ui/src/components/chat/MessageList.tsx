import { useEffect, useRef } from 'react'
import Markdown from 'markdown-to-jsx'
import { useChatStore } from '@/stores/chatStore'
import { cn } from '@/lib/utils'

function TypingIndicator({ tool }: { tool: string | null }) {
  return (
    <div className="flex justify-start">
      <div className="bg-muted rounded-2xl px-4 py-3 flex items-center gap-3">
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce"
              style={{ animationDelay: `${i * 150}ms`, animationDuration: '900ms' }}
            />
          ))}
        </div>
        {tool && (
          <span className="text-xs text-muted-foreground capitalize">
            {tool.replace(/_/g, ' ')}
          </span>
        )}
      </div>
    </div>
  )
}

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

      {isStreaming && messages[messages.length - 1]?.role !== 'ai' && (
        <TypingIndicator tool={streamingTool} />
      )}

      <div ref={bottomRef} />
    </div>
  )
}
