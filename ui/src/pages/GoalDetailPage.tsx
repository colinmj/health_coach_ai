import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getGoal } from '@/lib/api'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { ChevronLeft } from 'lucide-react'
import { format } from 'date-fns'
import type { Action } from '@/types'

function ActionRow({ action }: { action: Action }) {
  const descriptor = action.metric && action.condition && action.target_value != null
    ? `${action.metric.replace(/_/g, ' ')} ${action.condition.replace(/_/g, ' ')} ${action.target_value}`
    : null

  return (
    <div className="flex items-start gap-3 py-2">
      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-muted-foreground shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-foreground">{action.action_text}</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {descriptor && (
            <Badge variant="outline" className="text-xs font-mono">{descriptor}</Badge>
          )}
          {action.frequency && (
            <Badge variant="secondary" className="text-xs">{action.frequency}</Badge>
          )}
        </div>
      </div>
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-7 w-2/3" />
      <div className="flex gap-2">
        <Skeleton className="h-5 w-20 rounded-full" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-16 w-full" />
    </div>
  )
}

export function GoalDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: goal, isLoading } = useQuery({
    queryKey: ['goals', id],
    queryFn: () => getGoal(Number(id)),
    enabled: !!id,
  })

  return (
    <ScrollArea className="h-full">
      <div className="p-6 max-w-2xl">
        <Link
          to="/goals"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
        >
          <ChevronLeft className="h-4 w-4" />
          Goals
        </Link>

        {isLoading && <DetailSkeleton />}

        {goal && (
          <>
            <h1 className="text-xl font-semibold mb-3">{goal.title ?? goal.goal_text}</h1>
            <div className="flex flex-wrap gap-2 mb-6">
              {goal.domains?.map((d) => (
                <Badge key={d} variant="secondary">{d}</Badge>
              ))}
              {goal.target_date && (
                <Badge variant="outline">Due {format(new Date(goal.target_date), 'MMM d, yyyy')}</Badge>
              )}
            </div>

            {goal.protocols.length === 0 && goal.direct_actions.length === 0 && (
              <p className="text-sm text-muted-foreground">No protocol or actions defined yet.</p>
            )}

            {goal.protocols.map((protocol, i) => (
              <div key={protocol.id} className="mb-8">
                {goal.protocols.length > 1 && (
                  <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Protocol {i + 1}</p>
                )}
                <p className="text-sm text-foreground leading-relaxed mb-4">{protocol.protocol_text}</p>

                {protocol.actions.length > 0 && (
                  <>
                    <Separator className="mb-3" />
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Actions</p>
                    <div className="divide-y">
                      {protocol.actions.map((action) => (
                        <ActionRow key={action.id} action={action} />
                      ))}
                    </div>
                  </>
                )}
              </div>
            ))}

            {goal.direct_actions.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Direct Actions</p>
                <div className="divide-y">
                  {goal.direct_actions.map((action) => (
                    <ActionRow key={action.id} action={action} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </ScrollArea>
  )
}
