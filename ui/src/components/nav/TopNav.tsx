import { useState } from 'react'
import { NavLink, Link } from 'react-router-dom'
import { Button, buttonVariants } from '@/components/ui/button'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { Settings, Menu } from 'lucide-react'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'

const NAV_LINKS = [
  { to: '/', label: 'Chat', end: true },
  { to: '/goals', label: 'Goals & Insights', end: false },
]

function NavLinks({ onClick }: { onClick?: () => void }) {
  return (
    <>
      {NAV_LINKS.map(({ to, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onClick}
          className={({ isActive }) =>
            cn(
              'rounded-md px-3 py-1.5 text-sm transition-colors',
              isActive
                ? 'bg-muted text-foreground font-medium'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            )
          }
        >
          {label}
        </NavLink>
      ))}
    </>
  )
}

export function TopNav() {
  const isMobile = useIsMobile()
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <header className="flex h-12 shrink-0 items-center border-b bg-background px-4 gap-4">
      <span className="text-sm font-semibold">Health Coach AI</span>

      {!isMobile && (
        <nav className="flex items-center gap-1">
          <NavLinks />
        </nav>
      )}

      <div className="ml-auto flex items-center gap-1">
        <Link
          to="/settings"
          className={cn(buttonVariants({ variant: 'ghost', size: 'icon' }), 'h-8 w-8')}
        >
          <Settings className="h-4 w-4" />
        </Link>

        {isMobile && (
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={() => setSheetOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
        )}
      </div>

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="left" className="w-64 pt-10">
          <nav className="flex flex-col gap-1">
            <NavLinks onClick={() => setSheetOpen(false)} />
          </nav>
        </SheetContent>
      </Sheet>
    </header>
  )
}
