import clsx from 'clsx'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/errors'
import { useEntryList, type EntryFilter } from '@/api/hooks/useJournal'
import { TagChip } from '@/components/domain/Chips'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Input, Select } from '@/components/ui/Field'
import { Icon } from '@/components/ui/Icon'
import { dayAndMonth, hm, weekdayShort } from '@/lib/time'

export const STATUS_LABEL: Record<string, string> = { draft: 'Draft', processing: 'Reading…', review: 'Needs review', confirmed: 'Saved', failed: 'Failed', manual: 'Manual' }
export const statusTone = (s: string) => (s === 'failed' ? 'bg-bad/15 text-bad' : s === 'review' ? 'bg-warn/15 text-warn' : s === 'confirmed' ? 'bg-good/15 text-good' : 'bg-line2 text-muted')

export function HistoryPage() {
  const nav = useNavigate()
  const [q, setQ] = useState(''), [status, setStatus] = useState(''), [from, setFrom] = useState(''), [to, setTo] = useState('')
  const filter: EntryFilter = { q: q.trim() || undefined, status: status || undefined, from: from || undefined, to: to || undefined }
  const list = useEntryList(filter)
  const entries = list.data?.pages.flatMap((p) => p.data) ?? []
  const clear = () => { setQ(''); setStatus(''); setFrom(''); setTo('') }
  const filtered = !!(filter.q || filter.status || filter.from || filter.to)

  return (
    <>
      <PageHeader title="Journal history" subtitle="Everything you have written or dictated" back={() => nav('/journal')}>
        <Button variant="primary" icon="plus" onClick={() => nav('/journal')}>New entry</Button>
      </PageHeader>
      <div className="flex flex-col gap-4 p-4 md:px-7 md:py-[22px] md:pb-10">
        <div className="card flex flex-wrap items-end gap-3 p-3.5">
          <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-xs font-semibold text-muted">Search
            <span className="relative"><Icon name="search" size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" /><Input dense className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your entries" /></span></label>
          <label className="flex flex-col gap-1 text-xs font-semibold text-muted">Status
            <Select dense value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></label>
          <div className="grid w-full grid-cols-2 gap-3 sm:contents">
            <label className="flex flex-col gap-1 text-xs font-semibold text-muted">From<Input dense type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} /></label>
            <label className="flex flex-col gap-1 text-xs font-semibold text-muted">To<Input dense type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} /></label>
          </div>
          {filtered && <Button variant="subtle" onClick={clear}>Clear</Button>}
        </div>

        {list.isLoading && <div className="flex flex-col gap-2"><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></div>}
        {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {!list.isLoading && !list.error && entries.length === 0 && (
          <div className="card"><EmptyState icon="journal" title={filtered ? 'No entries match' : 'No entries yet'} action={filtered ? <Button onClick={clear}>Clear filters</Button> : <Button variant="primary" onClick={() => nav('/journal')}>Write the first one</Button>}>
            {filtered ? 'Try a different search or a wider date range.' : 'Dictate or type a few sentences about your day and they will be listed here.'}</EmptyState></div>
        )}
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {entries.map((e) => (
            <li key={e.id}>
              <button type="button" onClick={() => nav(e.status === 'review' || e.status === 'processing' ? `/journal/${e.id}/review` : `/journal/${e.id}`)}
                className="card flex w-full items-center gap-3.5 p-3.5 text-left transition hover:border-ghostline">
                <span className="flex size-10 flex-none items-center justify-center rounded-xl bg-tint text-accent-ink"><Icon name={e.input_method === 'dictated' ? 'journal' : 'keyboard'} size={18} /></span>
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-[13.5px] font-semibold">{e.title}</b>
                  <span className="block text-xs text-faint">{weekdayShort(e.entry_date)} {dayAndMonth(e.entry_date)} · {e.word_count} words · {e.input_method === 'dictated' ? 'dictated' : 'typed'}{e.activity_count ? ` · ${e.activity_count} activities` : ''}</span>
                  {e.tags.length > 0 && <span className="mt-1.5 flex flex-wrap gap-1">{e.tags.slice(0, 5).map((t) => <TagChip key={t.name} name={t.name} color={t.color} />)}</span>}
                </span>
                <span className="flex flex-none flex-col items-end gap-1">
                  <span className={clsx('rounded-full px-2 py-0.5 text-[11px] font-semibold', statusTone(e.status))}>{STATUS_LABEL[e.status] ?? e.status}</span>
                  {e.status === 'confirmed' && <span className="num text-xs font-semibold text-muted">{hm(e.covered_minutes)} <span className="font-medium text-faint">of {hm(e.window_minutes)}</span></span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {list.hasNextPage && <div className="flex justify-center"><Button loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage().catch((e) => alert(errorMessage(e)))}>Load more</Button></div>}
      </div>
    </>
  )
}
