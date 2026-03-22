import { useQuery } from '@tanstack/react-query'
import { getSessions, getMessages } from '@/lib/api'
import { useChatStore } from '@/stores/chatStore'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { PenSquare, MessageCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'

export function SessionSidebar() {
  const { activeSessionId, setActiveSessionId, setMessages, startNewChat } = useChatStore()

  const { data: sessions, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
    refetchInterval: 30_000,
  })

  async function handleSelectSession(id: number) {
    if (id === activeSessionId) return
    const messages = await getMessages(id)
    setMessages(messages)
    setActiveSessionId(id)
  }

  return (
    <aside className="flex w-64 flex-col border-r bg-sidebar">
      <div className="flex items-center justify-between px-4 py-4">
        <span className="text-sm font-semibold text-sidebar-foreground">Health Coach</span>
        <Button size="icon" variant="ghost" onClick={startNewChat} title="New chat">
          <PenSquare className="h-4 w-4" />
        </Button>
      </div>

      <Separator />

      <ScrollArea className="flex-1 px-2 py-2">
        {isLoading && (
          <div className="flex flex-col gap-2 px-2 py-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-lg" />
            ))}
          </div>
        )}

        {sessions?.map((session) => (
          <button
            key={session.id}
            onClick={() => handleSelectSession(session.id)}
            className={cn(
              'flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-sidebar-accent',
              activeSessionId === session.id && 'bg-sidebar-accent',
            )}
          >
            <MessageCircle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium text-sidebar-foreground">
                {session.title || 'New conversation'}
              </div>
              <div className="text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(session.created_at), { addSuffix: true })}
              </div>
            </div>
          </button>
        ))}

        {sessions?.length === 0 && !isLoading && (
          <p className="px-3 py-4 text-xs text-muted-foreground">No conversations yet.</p>
        )}
      </ScrollArea>
    </aside>
  )
}
