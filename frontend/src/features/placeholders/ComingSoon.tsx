import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/Feedback'
import { PageHeader } from '@/components/layout/PageHeader'

/** Honest placeholders for modules that land in later PRD phases. The routes and nav exist so the shell is complete. */
export function JournalPage() {
  const nav = useNavigate()
  return (
    <>
      <PageHeader title="Journal" subtitle="Dictate or type your day" />
      <EmptyState icon="journal" title="The AI journal arrives in Phase 2" action={<Button variant="primary" icon="plus" onClick={() => nav('/calendar?log=1')}>Log time manually</Button>}>
        Speak or type a few sentences and Cadence will turn them into reviewed, tagged activities. Until then, log time by hand from the Calendar: every chart and total already works with manual entries.
      </EmptyState>
    </>
  )
}

export function IdealPage() {
  const nav = useNavigate()
  return (
    <>
      <PageHeader title="Ideal Day & Week" subtitle="Targets to compare your time against" />
      <EmptyState icon="ideal" title="Ideal Day & Week editors arrive in Phase 3" action={<Button onClick={() => nav('/overview')}>Back to Overview</Button>}>
        Your account was seeded with a balanced 24-hour Ideal Day (it adds up to exactly 24h) and shows on the Calendar as a ghost overlay. Editing, the 168h Ideal Week and version history come next.
      </EmptyState>
    </>
  )
}
