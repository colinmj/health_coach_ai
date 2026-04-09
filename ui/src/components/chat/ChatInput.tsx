import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ArrowUp, Square } from 'lucide-react'
import { useSendMessage } from '@/hooks/useSendMessage'
import { FollowUpChips } from './FollowUpChips'

export function ChatInput() {
  const [input, setInput] = useState('')
  const { sendMessage, stop, isStreaming } = useSendMessage()
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function handleSubmit() {
    const query = input.trim()
    if (!query || isStreaming) return
    setInput('')
    // Reset the inline height set by the onInput auto-grow handler so the
    // textarea returns to its single-row default after the value is cleared.
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    sendMessage(query)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t bg-background px-4 py-4">
      <FollowUpChips />
      <div className="flex items-end gap-2.5 bg-white dark:bg-[#13131A] border border-[#E0E0E8] dark:border-[#2a2a3a] rounded-xl px-4 py-2.5 focus-within:border-[#3B6FFF55] transition-colors duration-150">
        <textarea
          ref={textareaRef}
          className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          placeholder="Ask about your workouts, sleep, nutrition..."
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          style={{ maxHeight: '160px', overflowY: 'auto' }}
          onInput={(e) => {
            const el = e.currentTarget
            el.style.height = 'auto'
            el.style.height = `${Math.min(el.scrollHeight, 160)}px`
          }}
        />
        {isStreaming ? (
          <Button size="icon" variant="destructive" className="shrink-0" onClick={stop}>
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!input.trim()}
            className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: '#3B6FFF' }}
            onMouseEnter={(e) => { if (!e.currentTarget.disabled) e.currentTarget.style.backgroundColor = '#5A8AFF' }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#3B6FFF' }}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Shift+Enter for new line · Enter to send
      </p>
    </div>
  )
}
