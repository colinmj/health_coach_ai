import { useChatStore } from '@/stores/chatStore'
import { useSendMessage } from '@/hooks/useSendMessage'

export function ConfirmModal() {
  const { confirmState, clearConfirmState } = useChatStore()
  const { sendMessage } = useSendMessage()

  if (!confirmState.open || !confirmState.event) return null

  const { event, pendingQuery } = confirmState

  function handleConfirm() {
    clearConfirmState()
    sendMessage(pendingQuery, true)
  }

  function handleCancel() {
    clearConfirmState()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
          {event.title}
        </h2>

        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{event.body}</p>

        <div className="mt-3 flex gap-4 text-xs text-zinc-500 dark:text-zinc-400">
          <span>Last run: {event.stats.last_run}</span>
          {event.stats.daily_limit != null && (
            <span>
              Used today: {event.stats.daily_used} / {event.stats.daily_limit}
            </span>
          )}
        </div>

        {event.cached_result && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
              Cached result
            </p>
            <div className="max-h-40 overflow-y-auto rounded border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              <pre className="whitespace-pre-wrap break-words font-mono">
                {(() => {
                  try {
                    return JSON.stringify(JSON.parse(event.cached_result!), null, 2)
                  } catch {
                    return event.cached_result
                  }
                })()}
              </pre>
            </div>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-3">
          <button
            onClick={handleCancel}
            className="rounded-md px-4 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            Run anyway
          </button>
        </div>
      </div>
    </div>
  )
}
