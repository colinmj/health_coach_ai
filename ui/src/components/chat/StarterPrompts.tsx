import { useUser } from '@clerk/clerk-react'

export function StarterPrompts() {
  const { user } = useUser()
  const firstName = user?.firstName

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-8">
      <div
        className="text-center"
        style={{ animation: 'fadeIn 0.7s ease both' }}
      >
        <h1 className="font-display text-[28px] font-normal text-foreground leading-snug tracking-tight max-w-[540px]">
          How can I help you optimize<br />
          your training and performance
          <span className="text-[#b0b0c8] dark:text-[#5a5a78]">, </span>
          {firstName}?
        </h1>
      </div>
    </div>
  )
}
