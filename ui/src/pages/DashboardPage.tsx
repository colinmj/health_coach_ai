import { Tabs as TabsPrimitive } from '@base-ui/react/tabs'
import { BarChart2 } from 'lucide-react'
import { cn } from '@/lib/utils'

function ComingSoon({ description }: { description: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-muted-foreground">
      <BarChart2 className="h-10 w-10 opacity-30" />
      <p className="text-sm font-medium">Coming soon</p>
      <p className="text-xs">{description}</p>
    </div>
  )
}

const TABS = [
  { value: 'overview', label: 'Overview', description: 'Cross-domain trends and weekly summary' },
  { value: 'training', label: 'Training', description: 'Strength, 1RM trends, and performance scores' },
  { value: 'nutrition', label: 'Nutrition', description: 'Macros, calories, and key micronutrients' },
  { value: 'recovery', label: 'Recovery', description: 'HRV, sleep quality, and recovery scores' },
]

export function DashboardPage() {
  return (
    <div className="flex flex-col h-full p-6">
      <h1 className="text-xl font-semibold mb-4">Dashboard</h1>
      <TabsPrimitive.Root defaultValue="overview" className="flex flex-col flex-1">
        <TabsPrimitive.List className="flex gap-1 border-b mb-6">
          {TABS.map(({ value, label }) => (
            <TabsPrimitive.Tab
              key={value}
              value={value}
              className={cn(
                'px-4 py-2 text-sm -mb-px cursor-pointer transition-colors border-b-2 border-transparent',
                'text-muted-foreground hover:text-foreground',
                'data-[selected]:border-foreground data-[selected]:text-foreground data-[selected]:font-medium',
              )}
            >
              {label}
            </TabsPrimitive.Tab>
          ))}
        </TabsPrimitive.List>
        {TABS.map(({ value, description }) => (
          <TabsPrimitive.Panel key={value} value={value}>
            <ComingSoon description={description} />
          </TabsPrimitive.Panel>
        ))}
      </TabsPrimitive.Root>
    </div>
  )
}
