import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { deleteSession, updateSession } from '@/lib/api'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MoreHorizontal, Pencil, Pin, PinOff, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Session } from '@/types'

interface SessionActionsProps {
  session: Session
  isActive: boolean
  onDeleted: () => void
}

type Mode = 'view' | 'rename' | 'confirm-delete'

export function SessionActions({ session, onDeleted }: SessionActionsProps) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<Mode>('view')
  const [renameValue, setRenameValue] = useState('')

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen)
    // Always reset to view mode when popover closes
    if (!nextOpen) {
      setMode('view')
    }
  }

  async function handlePinToggle() {
    await updateSession(session.id, { pinned: !session.pinned })
    queryClient.invalidateQueries({ queryKey: ['sessions'] })
    setOpen(false)
  }

  function handleRenameClick() {
    setRenameValue(session.title ?? '')
    setMode('rename')
  }

  async function handleRenameSave() {
    const trimmed = renameValue.trim()
    await updateSession(session.id, { title: trimmed || null })
    queryClient.invalidateQueries({ queryKey: ['sessions'] })
    setOpen(false)
    setMode('view')
  }

  function handleRenameKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleRenameSave()
    }
    if (e.key === 'Escape') {
      setMode('view')
    }
  }

  async function handleDeleteConfirm() {
    await deleteSession(session.id)
    queryClient.invalidateQueries({ queryKey: ['sessions'] })
    setOpen(false)
    onDeleted()
  }

  return (
    // stopPropagation on the wrapper so clicks here don't bubble to the session row select handler
    <span
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      className="contents"
    >
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger
          aria-label="Session actions"
          className={cn(
            'flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground',
            'opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity',
            open && 'opacity-100',
          )}
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </PopoverTrigger>

        <PopoverContent
          side="bottom"
          align="end"
          sideOffset={4}
          onClick={(e) => e.stopPropagation()}
        >
          {mode === 'view' && (
            <div className="flex flex-col gap-px">
              <button
                onClick={handlePinToggle}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-foreground hover:bg-muted transition-colors"
              >
                {session.pinned ? (
                  <>
                    <PinOff className="h-3.5 w-3.5 text-muted-foreground" />
                    Unpin
                  </>
                ) : (
                  <>
                    <Pin className="h-3.5 w-3.5 text-muted-foreground" />
                    Pin
                  </>
                )}
              </button>

              <button
                onClick={handleRenameClick}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-foreground hover:bg-muted transition-colors"
              >
                <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                Rename
              </button>

              <button
                onClick={() => setMode('confirm-delete')}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-destructive hover:bg-destructive/10 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </button>
            </div>
          )}

          {mode === 'rename' && (
            <div className="flex flex-col gap-2 p-1">
              <Input
                autoFocus
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={handleRenameKeyDown}
                placeholder="Untitled session"
                className="h-7 text-sm"
              />
              <div className="flex items-center gap-1.5">
                <Button size="sm" onClick={handleRenameSave} className="h-6 flex-1 text-xs">
                  Save
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setMode('view')}
                  className="h-6 flex-1 text-xs"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {mode === 'confirm-delete' && (
            <div className="flex flex-col gap-2 p-1">
              <p className="text-xs text-muted-foreground px-1">Delete this session?</p>
              <div className="flex items-center gap-1.5">
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleDeleteConfirm}
                  className="h-6 flex-1 text-xs"
                >
                  Delete
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setMode('view')}
                  className="h-6 flex-1 text-xs"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </span>
  )
}
