import { useQuery } from '@tanstack/react-query'
import { getSessions, getMessages } from '@/lib/api'
import { useChatStore } from '@/stores/chatStore'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { MessageCircle, Pin, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { SyncStatus } from './SyncStatus'
import { SessionActions } from './SessionActions'
import type { Session } from '@/types'

interface SessionSidebarProps {
  isMobile: boolean
  open: boolean
  onClose: () => void
}

export function SessionSidebar({ isMobile, open, onClose }: SessionSidebarProps) {
  const { activeSessionId, setActiveSessionId, setMessages, startNewChat, clearSuggestedQuestions } = useChatStore()

  const { data: sessions, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
    refetchInterval: 30_000,
  })

  async function handleSelectSession(id: number) {
    if (id === activeSessionId) return
    const messages = await getMessages(id)
    setMessages(messages)
    clearSuggestedQuestions()
    setActiveSessionId(id)
    if (isMobile) onClose()
  }

  function handleNewChat() {
    startNewChat()
    if (isMobile) onClose()
  }

  function handleSessionDeleted(session: Session) {
    // If the deleted session was active, navigate away to a new chat
    if (session.id === activeSessionId) {
      startNewChat()
    }
  }

  const pinnedSessions = sessions?.filter((s) => s.pinned) ?? []
  const unpinnedSessions = sessions?.filter((s) => !s.pinned) ?? []

  return (
    <aside
      className={cn(
        'flex flex-col border-r bg-sidebar transition-transform duration-200',
        isMobile
          ? 'fixed inset-y-0 left-0 z-30 w-full max-w-xs'
          : 'h-full w-64 shrink-0',
        isMobile && !open && '-translate-x-full',
      )}
    >
      <div className="flex items-center justify-between px-4 py-4">
        <span className="text-[11px] font-semibold text-[#b0b0c0] dark:text-[#4a4a60] tracking-[0.08em] uppercase">Sessions</span>
        <div className="flex items-center gap-1">
          <button
            className="w-6 h-6 rounded-md bg-transparent border border-[#E0E0E8] dark:border-[#2a2a3a] text-[#b0b0c0] dark:text-[#6b6b80]
              hover:border-[#3B6FFF] hover:text-[#3B6FFF] transition-all duration-150
              flex items-center justify-center text-sm"
            onClick={handleNewChat}
            title="New chat"
          >
            +
          </button>
          {isMobile && (
            <Button size="icon" variant="ghost" onClick={onClose} title="Close">
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <Separator />

      <ScrollArea className="min-h-0 flex-1 px-2 py-2">
        {isLoading && (
          <div className="flex flex-col gap-2 px-2 py-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-lg" />
            ))}
          </div>
        )}

        {pinnedSessions.length > 0 && (
          <>
            <p className="px-3 pb-1 pt-1 text-[11px] font-semibold text-[#b0b0c0] dark:text-[#4a4a60] tracking-[0.08em] uppercase">
              Pinned
            </p>
            {pinnedSessions.map((session) => (
              <SessionRow
                key={session.id}
                session={session}
                isActive={activeSessionId === session.id}
                onSelect={handleSelectSession}
                onDeleted={() => handleSessionDeleted(session)}
              />
            ))}
            {unpinnedSessions.length > 0 && <div className="my-1" />}
          </>
        )}

        {unpinnedSessions.map((session) => (
          <SessionRow
            key={session.id}
            session={session}
            isActive={activeSessionId === session.id}
            onSelect={handleSelectSession}
            onDeleted={() => handleSessionDeleted(session)}
          />
        ))}

        {sessions?.length === 0 && !isLoading && (
          <p className="px-3 py-4 text-xs text-muted-foreground">No conversations yet.</p>
        )}
      </ScrollArea>

      <SyncStatus />
    </aside>
  )
}

interface SessionRowProps {
  session: Session
  isActive: boolean
  onSelect: (id: number) => void
  onDeleted: () => void
}

function SessionRow({ session, isActive, onSelect, onDeleted }: SessionRowProps) {
  return (
    // Using a div with role="button" instead of <button> because we need to nest
    // interactive elements (SessionActions) inside the row. Nested <button> elements
    // are invalid HTML and cause browser quirks. The div carries keyboard navigation
    // via onKeyDown so it remains accessible.
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(session.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(session.id)
        }
      }}
      className={cn(
        'group flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-sm transition-all duration-150',
        'border-l-2 cursor-pointer',
        isActive
          ? 'bg-[#F0F0F8] dark:bg-[#1C1C27] border-l-[#3B6FFF]'
          : 'border-l-transparent hover:bg-[#F0F0F8] dark:hover:bg-[#1C1C27]',
      )}
    >
      <MessageCircle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />

      <div className="min-w-0 flex-1">
        <div className={cn('flex items-center gap-1 truncate font-medium', isActive ? 'text-foreground' : 'text-[#505068] dark:text-[#c8c8d8]')}>
          {session.pinned && (
            <Pin className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="Pinned" />
          )}
          <span className="truncate">
            {session.title ?? 'New conversation'}
          </span>
        </div>
        <div className="text-xs text-muted-foreground">
          {formatDistanceToNow(new Date(session.created_at), { addSuffix: true })}
        </div>
      </div>

      <SessionActions
        session={session}
        isActive={isActive}
        onDeleted={onDeleted}
      />
    </div>
  )
}
