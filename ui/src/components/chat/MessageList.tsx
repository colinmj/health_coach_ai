import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import Markdown from 'markdown-to-jsx'
import { Copy, Check, ThumbsUp, ThumbsDown } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { cn } from '@/lib/utils'
import { StarterPrompts } from './StarterPrompts'

/** Removes JSON code blocks (```json ... ``` or ``` { ... ```) and bare JSON objects/arrays from AI messages. */
function stripJsonCodeBlocks(text: string): string {
  return text
    .replace(/```json[\s\S]*?```/g, '')          // complete ```json blocks
    .replace(/```\s*[{[][\s\S]*?```/g, '')       // complete ``` { ... ``` blocks
    .replace(/```json[\s\S]*/g, '')              // incomplete ```json blocks (mid-stream)
    .replace(/```\s*[{[][\s\S]*/g, '')           // incomplete ``` { ... blocks (mid-stream)
    // Strip messages that are entirely bare JSON (no surrounding prose)
    .replace(/^\s*[{[][\s\S]*[}\]]\s*$/, '')
    .trim()
}

/** Strips all common markdown syntax, leaving plain text suitable for clipboard. */
function stripMarkdown(text: string): string {
  return text
    // Fenced code blocks — keep the content, drop the fences
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '$1')
    // Inline code
    .replace(/`([^`]*)`/g, '$1')
    // ATX headings (# ## ### etc.)
    .replace(/^#{1,6}\s+/gm, '')
    // Bold + italic (*** or ___)
    .replace(/\*{3}([^*]+)\*{3}/g, '$1')
    .replace(/_{3}([^_]+)_{3}/g, '$1')
    // Bold (** or __)
    .replace(/\*{2}([^*]+)\*{2}/g, '$1')
    .replace(/_{2}([^_]+)_{2}/g, '$1')
    // Italic (* or _)
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    // Strikethrough (~~)
    .replace(/~~([^~]+)~~/g, '$1')
    // Links — keep the label
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Images — drop entirely
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    // Blockquotes
    .replace(/^>\s+/gm, '')
    // Unordered list markers
    .replace(/^[\s]*[-*+]\s+/gm, '')
    // Ordered list markers
    .replace(/^[\s]*\d+\.\s+/gm, '')
    // Horizontal rules
    .replace(/^[-*_]{3,}\s*$/gm, '')
    // Collapse 3+ blank lines to a single blank line
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

type FeedbackState = 'thumbs-up' | 'thumbs-down' | null

interface MessageActionsProps {
  text: string
}

function MessageActions({ text }: MessageActionsProps) {
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState<FeedbackState>(null)

  const handleCopy = useCallback(() => {
    const plain = stripMarkdown(text)
    navigator.clipboard.writeText(plain).then(() => {
      setCopied(true)
      const timer = window.setTimeout(() => setCopied(false), 1500)
      return () => window.clearTimeout(timer)
    })
  }, [text])

  const handleFeedback = useCallback((value: FeedbackState) => {
    setFeedback((prev) => (prev === value ? null : value))
  }, [])

  const actionBtn = cn(
    'w-7 h-7 rounded-md flex items-center justify-center transition-all duration-150',
    'border border-[#E8E8F0] dark:border-[#2a2a3a]',
    'text-[#c0c0d0] dark:text-[#4a4a60]',
    'hover:border-[#3B6FFF33] hover:text-[#3B6FFF] hover:bg-[#F0F4FF]',
    'dark:hover:bg-[#1C1C27] dark:hover:border-[#3B6FFF44]',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
  )

  return (
    <div className="mt-2 flex items-center gap-1.5 pl-1">
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? 'Copied' : 'Copy message'}
        className={actionBtn}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-green-500" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>

      <button
        type="button"
        onClick={() => handleFeedback('thumbs-up')}
        aria-label="Helpful"
        aria-pressed={feedback === 'thumbs-up'}
        className={cn(actionBtn, feedback === 'thumbs-up' && 'text-[#3B6FFF] border-[#3B6FFF44]')}
      >
        <ThumbsUp
          className="h-3.5 w-3.5"
          fill={feedback === 'thumbs-up' ? 'currentColor' : 'none'}
        />
      </button>

      <button
        type="button"
        onClick={() => handleFeedback('thumbs-down')}
        aria-label="Not helpful"
        aria-pressed={feedback === 'thumbs-down'}
        className={cn(actionBtn, feedback === 'thumbs-down' && 'text-[#3B6FFF] border-[#3B6FFF44]')}
      >
        <ThumbsDown
          className="h-3.5 w-3.5"
          fill={feedback === 'thumbs-down' ? 'currentColor' : 'none'}
        />
      </button>
    </div>
  )
}

const TOOL_STEPS: Record<string, string[]> = {
  create_goal: ['Analysing goal', 'Creating actions', 'Saving goal'],
}

function TypingIndicator({ tool }: { tool: string | null }) {
  const steps = useMemo(() => (tool ? TOOL_STEPS[tool] ?? null : null), [tool])
  const [stepIndex, setStepIndex] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setStepIndex(0)
    if (!steps) return
    intervalRef.current = setInterval(() => {
      setStepIndex((i) => (i + 1) % steps.length)
    }, 800)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [steps])

  const label = steps ? steps[stepIndex] : tool ? tool.replace(/_/g, ' ') : null

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
        {label && (
          <span className="text-xs text-muted-foreground capitalize">
            {label}
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
    return <StarterPrompts />
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={cn(
            'flex flex-col',
            msg.role === 'human' ? 'items-end' : 'items-start',
          )}
        >
          <div
            className={cn(
              'rounded-[18px] px-4 py-2.5 text-sm leading-relaxed',
              msg.role === 'human'
                ? 'rounded-br-[4px] max-w-[420px] ml-auto text-white whitespace-pre-wrap'
                : 'w-full md:w-3/4 bg-muted dark:bg-obsidian text-[#404058] dark:text-[#c8c8d8] prose prose-sm prose-neutral dark:prose-invert max-w-none',
            )}
            style={msg.role === 'human' ? { backgroundColor: '#3B6FFF' } : undefined}
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
                {stripJsonCodeBlocks(msg.text)}
              </Markdown>
            )}
          </div>
          {msg.role === 'ai' && !isStreaming && <MessageActions text={msg.text} />}
        </div>
      ))}

      {isStreaming && (messages[messages.length - 1]?.role !== 'ai' || streamingTool !== null) && (
        <TypingIndicator tool={streamingTool} />
      )}

      <div ref={bottomRef} />
    </div>
  )
}
