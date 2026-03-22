import { SessionSidebar } from '@/components/chat/SessionSidebar'
import { MessageList } from '@/components/chat/MessageList'
import { ChatInput } from '@/components/chat/ChatInput'

export function ChatPage() {
  return (
    <div className="flex h-screen">
      <SessionSidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <MessageList />
        <ChatInput />
      </main>
    </div>
  )
}
