import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { getProfile } from '@/lib/api'
import { STARTER_PROMPTS, PROMPT_CATEGORIES } from '@/config/starterPrompts'
import type { PromptCategory } from '@/config/starterPrompts'
import { useSendMessage } from '@/hooks/useSendMessage'

type FilterValue = 'All' | PromptCategory

export function StarterPrompts() {
  const [activeFilter, setActiveFilter] = useState<FilterValue>('All')
  const { sendMessage, isStreaming } = useSendMessage()
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: getProfile })
  const name = profile?.name as string | undefined

  const visiblePrompts =
    activeFilter === 'All'
      ? PROMPT_CATEGORIES.flatMap((cat) => STARTER_PROMPTS[cat])
      : STARTER_PROMPTS[activeFilter]

  const filters: FilterValue[] = ['All', ...PROMPT_CATEGORIES]

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-8">
      <p className="mb-4 text-xl font-semibold text-foreground">{name ? `Hi ${name}` : 'Get started'}</p>

      {/* Filter chips */}
      <div className="mb-6 flex flex-wrap justify-center gap-2">
        {filters.map((filter) => (
          <button
            key={filter}
            type="button"
            onClick={() => setActiveFilter(filter)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              activeFilter === filter
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-transparent text-muted-foreground hover:border-foreground/30 hover:text-foreground',
            )}
          >
            {filter}
          </button>
        ))}
      </div>

      {/* Prompt cards grid */}
      <div className="grid w-full max-w-2xl grid-cols-2 gap-2 sm:grid-cols-3">
        {visiblePrompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            disabled={isStreaming}
            onClick={() => sendMessage(prompt)}
            className={cn(
              'rounded-lg border bg-card px-3 py-3 text-left text-xs leading-snug text-card-foreground',
              'transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              isStreaming
                ? 'cursor-not-allowed opacity-50'
                : 'hover:border-foreground/30 hover:bg-muted/50',
            )}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}
