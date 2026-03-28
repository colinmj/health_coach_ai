export type PromptCategory = 'Training' | 'Nutrition' | 'Body Composition' | 'Sleep & Recovery' | 'Correlations'

export const STARTER_PROMPTS: Record<PromptCategory, string[]> = {
  Training: [
    'What exercises have I PRed on in the last month?',
    'How has my training volume changed over the past 8 weeks?',
    'Which muscle groups am I training most frequently?',
  ],
  Nutrition: [
    'What has my average daily protein intake been this week?',
    'How do my calories today compare to my weekly average?',
  ],
  'Body Composition': [
    'How has my weight trended over the last 30 days?',
    'What is my current estimated body fat percentage trend?',
  ],
  'Sleep & Recovery': [
    'How has my HRV trended over the past two weeks?',
    'What does my average sleep duration look like this month?',
    'On which days did I have the best recovery scores?',
  ],
  Correlations: [
    'Did my sleep quality affect my workout performance last week?',
    'Is there a relationship between my protein intake and strength PRs?',
    'How does my recovery score correlate with training volume?',
  ],
}

export const PROMPT_CATEGORIES = Object.keys(STARTER_PROMPTS) as PromptCategory[]
