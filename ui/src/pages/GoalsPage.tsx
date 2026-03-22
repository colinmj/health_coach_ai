import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getGoals, getInsights } from '@/lib/api'
import { Collapsible } from '@base-ui/react/collapsible'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { ChevronRight, ChevronDown, Pin } from 'lucide-react'
import { formatDistanceToNow, format } from 'date-fns'
import { cn } from '@/lib/utils'
import type { Goal, Insight } from '@/types'

function InsightCard({ insight }: { insight: Insight }) {
  const [open, setOpen] = useState(false)
  const preview = insight.insight.split(/[.!?]/)[0].trim()

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="rounded-lg border bg-card text-sm overflow-hidden">
      <Collapsible.Trigger className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-muted/50 cursor-pointer">
        {insight.pinned && <Pin className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
        <span className="flex-1 font-medium text-foreground truncate">{preview}</span>
        <span className="text-xs text-muted-foreground shrink-0">
          {insight.date_derived ? formatDistanceToNow(new Date(insight.date_derived), { addSuffix: true }) : ''}
        </span>
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200', open && 'rotate-180')} />
      </Collapsible.Trigger>

      <Collapsible.Panel className="overflow-hidden data-[starting-style]:h-0 data-[ending-style]:h-0 transition-all duration-200 ease-in-out">
        <div className="px-4 pb-4">
          <Separator className="mb-3" />
          <p className="text-foreground leading-relaxed mb-4">{insight.insight}</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs sm:grid-cols-4">
            <div>
              <p className="text-muted-foreground font-medium uppercase tracking-wide mb-1">Status</p>
              <Badge variant="outline" className="text-xs capitalize">{insight.status}</Badge>
            </div>
            <div>
              <p className="text-muted-foreground font-medium uppercase tracking-wide mb-1">Effect</p>
              {insight.effect
                ? <Badge variant="secondary" className="text-xs capitalize">{insight.effect}</Badge>
                : <span className="text-muted-foreground">—</span>}
            </div>
            <div>
              <p className="text-muted-foreground font-medium uppercase tracking-wide mb-1">Confidence</p>
              {insight.confidence
                ? <Badge variant="outline" className="text-xs capitalize">{insight.confidence}</Badge>
                : <span className="text-muted-foreground">—</span>}
            </div>
            <div>
              <p className="text-muted-foreground font-medium uppercase tracking-wide mb-1">Tool Used</p>
              {insight.correlative_tool
                ? <span className="text-foreground capitalize">{insight.correlative_tool.replace(/_/g, ' ')}</span>
                : <span className="text-muted-foreground">—</span>}
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            {insight.date_derived ? format(new Date(insight.date_derived), 'MMM d, yyyy') : ''}
          </p>
        </div>
      </Collapsible.Panel>
    </Collapsible.Root>
  )
}

function GoalCard({ goal }: { goal: Goal }) {
  const protocolCount = goal.protocols.length
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card p-4 transition-colors hover:bg-muted/50">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{goal.goal_text}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {goal.domains?.map((d) => (
            <Badge key={d} variant="secondary" className="text-xs">{d}</Badge>
          ))}
          {goal.target_date && (
            <Badge variant="outline" className="text-xs">
              Due {format(new Date(goal.target_date), 'MMM d, yyyy')}
            </Badge>
          )}
          {protocolCount > 0 && (
            <span className="text-xs text-muted-foreground">
              {protocolCount} protocol{protocolCount !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </div>
  )
}

function SkeletonList({ count = 3 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-20 w-full rounded-lg" />
      ))}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return <p className="text-sm text-muted-foreground py-4">{message}</p>
}

export function GoalsPage() {
  const { data: insights, isLoading: insightsLoading } = useQuery({
    queryKey: ['insights'],
    queryFn: getInsights,
  })

  const { data: goals, isLoading: goalsLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: getGoals,
  })

  return (
    <ScrollArea className="h-full">
      <div className="p-6 flex flex-col gap-8 max-w-2xl">

        <section>
          <h2 className="text-lg font-semibold mb-3">Insights</h2>
          {insightsLoading && <SkeletonList count={2} />}
          {!insightsLoading && insights?.length === 0 && (
            <EmptyState message="No insights yet. Chat with the agent to discover correlations in your data." />
          )}
          {insights && insights.length > 0 && (
            <div className="flex flex-col gap-3">
              {insights.map((insight) => <InsightCard key={insight.id} insight={insight} />)}
            </div>
          )}
        </section>

        <section>
          <h2 className="text-lg font-semibold mb-3">Goals</h2>
          {goalsLoading && <SkeletonList count={3} />}
          {!goalsLoading && goals?.length === 0 && (
            <EmptyState message="No goals set yet. Start a chat to create one." />
          )}
          {goals && goals.length > 0 && (
            <div className="flex flex-col gap-3">
              {goals.map((goal) => (
                <Link key={goal.id} to={`/goals/${goal.id}`}>
                  <GoalCard goal={goal} />
                </Link>
              ))}
            </div>
          )}
        </section>

      </div>
    </ScrollArea>
  )
}
