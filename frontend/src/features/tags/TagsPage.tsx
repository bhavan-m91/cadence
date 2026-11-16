import * as Tabs from '@radix-ui/react-tabs'
import clsx from 'clsx'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import {
  flattenCategories, useCategories, useCreateCategory, useCreateRule, useCreateTag, useDeleteCategory, useDeleteRule, useDeleteTag, useMergeCategory,
  useMergeTag, usePutAliases, useRules, useTag, useTags, useUpdateCategory, useUpdateTag, type FlatCategory,
} from '@/api/hooks/useTaxonomy'
import type { Tag } from '@/api/types'
import { CategoryChip, TagChip } from '@/components/domain/Chips'
import { PageHeader, Segmented } from '@/components/layout/PageHeader'
import { Columns } from '@/components/charts/charts'
import { Button, IconButton } from '@/components/ui/Button'
import { Icon } from '@/components/ui/Icon'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Field, Input, Select, Textarea } from '@/components/ui/Field'
import { PALETTE } from '@/lib/colors'
import { addDays, dayOfMonth, hm, todayIn, weekdayShort, weekStartOf } from '@/lib/time'
import { usePreferences } from '@/api/hooks/useSettings'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'
import { ColorPicker, MergeDialog } from './shared'

export function TagsPage() {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') === 'categories' ? 'categories' : 'tags'
  const [search, setSearch] = useState('')
  const [newTag, setNewTag] = useState(false)
  const [newCat, setNewCat] = useState(false)
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }
  return (
    <>
      <PageHeader title="Tags & categories" subtitle="Categories split your 24 hours once. Tags overlap and can carry weekly limits.">
        {tab === 'tags' && <div className="relative max-md:w-full"><Icon name="search" size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" /><Input aria-label="Search tags" placeholder="Search tags" className="h-9 w-56 pl-9 max-md:w-full" value={search} onChange={(e) => setSearch(e.target.value)} /></div>}
        <Button variant="primary" icon="plus" onClick={() => (tab === 'tags' ? setNewTag(true) : setNewCat(true))}>{tab === 'tags' ? 'New tag' : 'New category'}</Button>
      </PageHeader>
      <Tabs.Root value={tab} onValueChange={(v) => { const n = new URLSearchParams(); n.set('tab', v); setSp(n) }} className="p-4 md:px-7 md:py-[22px] md:pb-10">
        <Tabs.List aria-label="Taxonomy" className="mb-4 inline-flex rounded-[10px] border border-line bg-line2 p-[3px]">
          {[['tags', 'Tags'], ['categories', 'Categories']].map(([v, l]) => <Tabs.Trigger key={v} value={v} className="min-h-[30px] rounded-[7px] px-4 text-[12.5px] font-medium text-muted data-[state=active]:bg-card data-[state=active]:font-semibold data-[state=active]:text-ink data-[state=active]:shadow-sm">{l}</Tabs.Trigger>)}
        </Tabs.List>
        <Tabs.Content value="tags"><TagsTab selected={sp.get('tag')} onSelect={(id) => set('tag', id)} search={search} newOpen={newTag} setNewOpen={setNewTag} /></Tabs.Content>
        <Tabs.Content value="categories"><CategoriesTab selected={sp.get('cat')} onSelect={(id) => set('cat', id)} newOpen={newCat} setNewOpen={setNewCat} /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}

// ====================================================================================================================== tags
const GUIDE = [
  { t: 'Category', d: 'Filled chip. Every activity has exactly one, so categories add up to your 24 hours.', ex: <CategoryChip name="Deep work" color="#3E86D4" /> },
  { t: 'Tag', d: 'Outlined chip with a colour dot. An activity can carry many.', ex: <TagChip name="p0" color="#4C63E6" /> },
  { t: 'Auto-tagged', d: 'Sparkle means Cadence added it. Hover to see the words that triggered it.', ex: <TagChip name="bug" color="#3E86D4" source="rule" /> },
  { t: 'Needs a check', d: "Dashed amber when Cadence isn't sure. Shown in review only.", ex: <TagChip name="client:acme" color="#8A6CE6" needsCheck /> },
  { t: 'Over its cap', d: 'Red ring once a capped tag passes its weekly limit.', ex: <TagChip name="social-media" color="#3E86D4" over /> },
  { t: 'Tag path', d: 'Used in tooltips and task details to show where a tag lives.', ex: <span className="inline-flex max-w-full flex-wrap items-center gap-1.5"><CategoryChip name="Work" color="#3E86D4" /><span className="text-faint">›</span><TagChip name="product-b" color="#4C63E6" /></span> },
]

function StyleGuide() {
  // Open on wide screens, tucked away on a phone where it would push the tags a full screen down.
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.matchMedia('(min-width: 768px)').matches)
  return (
    <section className="card p-4 md:p-[18px]" aria-labelledby="guide">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3"><h2 id="guide" className="m-0 text-[13.5px] font-semibold">Chip style guide</h2><span className="text-[11.5px] font-medium text-faint max-sm:hidden">How to read the chips anywhere in Cadence</span></div>
        <button type="button" aria-expanded={open} aria-controls="guide-body" onClick={() => setOpen((v) => !v)} className="flex items-center gap-1 text-xs font-semibold text-muted hover:text-ink">{open ? 'Hide' : 'Show'}<Icon name="chevronDown" size={13} className={clsx('transition-transform', open && 'rotate-180')} /></button>
      </div>
      {open && (
        <div id="guide-body" className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-6">
          {GUIDE.map((g) => (
            <div key={g.t} className="flex flex-col gap-2 rounded-xl bg-line2 p-3">
              <div className="flex min-h-[26px] flex-wrap items-center gap-1.5">{g.ex}</div>
              <b className="text-xs font-semibold">{g.t}</b>
              <span className="text-[11px] leading-snug text-muted">{g.d}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

const groupOf = (name: string) => (name.includes(':') ? name.split(':')[0] : 'General')

function TagRow({ tag, scale, selected, onSelect }: { tag: Tag; scale: number; selected: boolean; onSelect: () => void }) {
  const goal = tag.goal_kind !== 'tracked' ? tag.goal_weekly_minutes : null
  const over = tag.goal_status === 'over'
  const label = `${tag.name}: ${hm(tag.minutes_in_range)} this week${goal ? `, ${tag.goal_kind === 'max' ? 'limit' : 'goal'} ${hm(goal)}` : ''}${over ? ', over its cap' : ''}`
  return (
    <button type="button" onClick={onSelect} aria-pressed={selected} aria-label={label}
      className={clsx('grid w-full grid-cols-[minmax(0,150px)_minmax(0,1fr)_auto] items-center gap-3 rounded-[9px] px-2 py-2 text-left transition max-sm:grid-cols-[minmax(0,1fr)_auto]',
        selected ? 'bg-tint shadow-[inset_0_0_0_1px_var(--tintA2)]' : 'hover:bg-line2')}>
      <span className="flex min-w-0 items-center gap-2 text-[12.5px] font-semibold"><i className="size-[9px] flex-none rounded-[3px]" style={{ background: tag.color }} /><span className="truncate">#{tag.name}</span>{over && <span className="flex-none rounded-full bg-bad/15 px-1.5 py-px text-[10px] font-semibold text-bad">Over</span>}</span>
      <span className={clsx('relative h-2 rounded bg-line2 max-sm:order-3 max-sm:col-span-2', selected && 'bg-card')} aria-hidden>
        <i className="absolute inset-y-0 left-0 rounded" style={{ width: `${Math.min(100, (tag.minutes_in_range / scale) * 100)}%`, background: over ? 'var(--bad)' : tag.color }} />
        {goal ? <em className="absolute -inset-y-[3px] w-0.5 rounded-sm bg-ink" style={{ left: `calc(${Math.min(100, (goal / scale) * 100)}% - 1px)` }} /> : null}
      </span>
      <span className="num whitespace-nowrap text-right text-[11.5px] font-semibold">{hm(tag.minutes_in_range)}{goal ? <span className="font-medium text-faint"> of {hm(goal)}</span> : null}</span>
    </button>
  )
}

type TagRange = '7d' | 'week' | 'last' | '30d'
const RANGE_LABEL: Record<TagRange, string> = { '7d': 'Last 7 days', week: 'This week', last: 'Last week', '30d': 'Last 30 days' }

function useTagRange(range: TagRange) {
  const tz = useAuthStore((s) => s.user!.timezone)
  const weekStart = usePreferences().data?.week_start ?? 1
  const today = todayIn(tz)
  const ws = weekStartOf(today, weekStart)
  return range === 'week' ? { from: ws, to: addDays(ws, 6) } : range === 'last' ? { from: addDays(ws, -7), to: addDays(ws, -1) } : range === '30d' ? { from: addDays(today, -29), to: today } : { from: addDays(today, -6), to: today }
}

function TagsTab({ selected, onSelect, search, newOpen, setNewOpen }: { selected: string | null; onSelect: (id: string | null) => void; search: string; newOpen: boolean; setNewOpen: (v: boolean) => void }) {
  const [archived, setArchived] = useState(false)
  const [range, setRange] = useState<TagRange>('7d') // a rolling week, so a Monday morning never shows an empty page
  const span = useTagRange(range)
  const { data: tags, isLoading, error, refetch } = useTags({ archived, ...span })
  // Land on a tag on wide screens so the detail panel is never an empty box (the design always shows one).
  useEffect(() => {
    if (!selected && tags?.length && typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches) onSelect([...tags].sort((x, y) => y.minutes_in_range - x.minutes_in_range)[0].id) // open on the busiest tag
  }, [selected, tags]) // eslint-disable-line react-hooks/exhaustive-deps
  const shown = (tags ?? []).filter((t) => t.name.toLowerCase().includes(search.trim().toLowerCase().replace(/^#/, ''))).sort((x, y) => y.minutes_in_range - x.minutes_in_range || x.name.localeCompare(y.name))
  const scale = Math.max(60, ...shown.map((t) => Math.max(t.minutes_in_range, t.goal_kind !== 'tracked' ? t.goal_weekly_minutes ?? 0 : 0)))
  const groups = Array.from(shown.reduce((m, t) => m.set(groupOf(t.name), [...(m.get(groupOf(t.name)) ?? []), t]), new Map<string, Tag[]>()))
    .sort(([a], [b]) => (a === 'General' ? -1 : b === 'General' ? 1 : a.localeCompare(b)))
  return (
    <div className="flex flex-col gap-4">
      <StyleGuide />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section className={clsx('card min-w-0 p-4 md:p-[18px]', selected && 'max-lg:hidden')} aria-labelledby="all-tags">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2.5">
            <div><h2 id="all-tags" className="m-0 text-[13.5px] font-semibold">All tags</h2><span className="text-[11.5px] font-medium text-faint">Bar = hours in {RANGE_LABEL[range].toLowerCase()} · line = weekly limit</span></div>
            <Select dense aria-label="Range" className="!w-40" value={range} onChange={(e) => setRange(e.target.value as TagRange)}>{(Object.keys(RANGE_LABEL) as TagRange[]).map((r) => <option key={r} value={r}>{RANGE_LABEL[r]}</option>)}</Select>
          </div>
          {isLoading && <div className="flex flex-col gap-2"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
          {error && <ErrorState error={error} onRetry={() => refetch()} />}
          {tags && tags.length === 0 && <EmptyState icon="tag" title={archived ? 'No archived tags' : 'No tags yet'} action={!archived ? <Button variant="primary" icon="plus" onClick={() => setNewOpen(true)}>Create a tag</Button> : undefined}>Tags describe what an activity was about (#product-b, #p0, #social-media). One activity can have many.</EmptyState>}
          {tags && tags.length > 0 && shown.length === 0 && <p className="m-0 py-4 text-[13px] text-muted">No tag matches “{search}”.</p>}
          {groups.map(([name, list]) => (
            <div key={name} className="mb-2">
              <div className="flex items-center gap-2.5 border-b border-line2 px-2 pb-2 pt-2.5">
                <CategoryChip name={name} color="var(--sky)" />
                <span className="text-[11.5px] text-faint">{list.length} {list.length === 1 ? 'tag' : 'tags'}</span>
                <span className="num ml-auto text-[11.5px] text-muted"><b className="font-semibold text-ink">{hm(list.reduce((a, t) => a + t.minutes_in_range, 0))}</b> tagged</span>
              </div>
              {list.map((t) => <TagRow key={t.id} tag={t} scale={scale} selected={t.id === selected} onSelect={() => onSelect(t.id)} />)}
            </div>
          ))}
          <label className="mt-2 flex items-center gap-2 border-t border-line2 pt-3 text-[12.5px] font-medium text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Show archived</label>
        </section>
        {selected ? <TagPanel key={selected} id={selected} span={span} rangeLabel={RANGE_LABEL[range]} onClose={() => onSelect(null)} />
          : <section className="card hidden p-8 text-center text-[13px] text-muted lg:block">Pick a tag to see its limit, keywords and the days it was used.</section>}
      </div>
      <NewTagDialog open={newOpen} onOpenChange={setNewOpen} onCreated={(id) => onSelect(id)} />
    </div>
  )
}

function NewTagDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated: (id: string) => void }) {
  const create = useCreateTag()
  const [name, setName] = useState('')
  const [color, setColor] = useState(PALETTE[0])
  const [goal, setGoal] = useState<'tracked' | 'min' | 'max'>('tracked')
  const [hours, setHours] = useState('5')
  const [error, setError] = useState<string>()
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New tag" description="Lowercase letters, digits, - and _. Add a namespace like client:acme if you like."
      footer={<><Button variant="subtle" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" type="submit" form="new-tag" loading={create.isPending}>Create tag</Button></>}>
      <form id="new-tag" noValidate className="flex flex-col gap-4" onSubmit={(e) => {
        e.preventDefault(); setError(undefined)
        create.mutate({ name, color, goal_kind: goal, goal_weekly_minutes: goal === 'tracked' ? null : Math.round(Number(hours) * 60) }, {
          onSuccess: (t) => { setName(''); onOpenChange(false); onCreated(t.id) }, onError: (er) => setError(errorMessage(er)) })
      }}>
        <Field label="Name" error={error}>{(id, d) => <Input id={id} aria-describedby={d} dense autoFocus value={name} maxLength={48} placeholder="product-b" onChange={(e) => setName(e.target.value)} />}</Field>
        <Field label="Colour">{() => <ColorPicker value={color} onChange={setColor} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Weekly goal">{(id) => <Select id={id} dense value={goal} onChange={(e) => setGoal(e.target.value as any)}><option value="tracked">Just track it</option><option value="max">At most…</option><option value="min">At least…</option></Select>}</Field>
          {goal !== 'tracked' && <Field label="Hours per week">{(id) => <Input id={id} dense type="number" min={0.5} step={0.5} value={hours} onChange={(e) => setHours(e.target.value)} />}</Field>}
        </div>
      </form>
    </Dialog>
  )
}

const KINDS: { value: 'tracked' | 'max' | 'min'; label: string }[] = [{ value: 'tracked', label: 'Just track it' }, { value: 'max', label: 'At most' }, { value: 'min', label: 'At least' }]

function Sect({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="mt-3.5 border-t border-line2 pt-3.5"><div className="mb-2 text-[11.5px] font-semibold text-muted">{label}</div>{children}</div>
}

function TagPanel({ id, span, rangeLabel, onClose }: { id: string; span: { from: string; to: string }; rangeLabel: string; onClose: () => void }) {
  const nav = useNavigate()
  const { data: tag, isLoading, error, refetch } = useTag(id, span)
  const { data: allTags } = useTags()
  const { data: rules } = useRules({ target_type: 'tag', target_id: id })
  const update = useUpdateTag(), del = useDeleteTag(), merge = useMergeTag(), aliases = usePutAliases(), addRule = useCreateRule(), delRule = useDeleteRule()
  const [name, setName] = useState('')
  const [keepAlias, setKeepAlias] = useState(true)
  const [desc, setDesc] = useState('')
  const [hours, setHours] = useState('5')
  const [alias, setAlias] = useState('')
  const [phrase, setPhrase] = useState('')
  const [mergeOpen, setMergeOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => {
    if (!tag) return
    setName(tag.name); setDesc(tag.description ?? ''); setHours(tag.goal_weekly_minutes ? String(tag.goal_weekly_minutes / 60) : '5')
  }, [tag?.id, tag?.name, tag?.description, tag?.goal_weekly_minutes]) // eslint-disable-line react-hooks/exhaustive-deps
  const fail = (e: unknown) => toast.error(errorMessage(e))
  if (isLoading) return <div className="card flex flex-col gap-3 p-5"><Skeleton className="h-8" /><Skeleton className="h-40" /></div>
  if (error || !tag) return <div className="card"><ErrorState error={error} onRetry={() => refetch()} compact /></div>
  const tagAliases = tag.aliases ?? []
  const targets = (allTags ?? []).filter((t) => t.id !== id).map((t) => ({ id: t.id, label: `#${t.name}` }))
  const goalMin = tag.goal_kind !== 'tracked' ? tag.goal_weekly_minutes ?? 0 : 0
  const setGoal = (kind: 'tracked' | 'max' | 'min', h = hours) => update.mutate({ id, goal_kind: kind, goal_weekly_minutes: kind === 'tracked' ? null : Math.max(30, Math.round(Number(h) * 60)) }, { onError: fail })
  const over = tag.goal_status === 'over'
  const pct = goalMin ? Math.min(100, (tag.minutes_in_range / goalMin) * 100) : 0
  const status = !goalMin ? '' : tag.goal_kind === 'max' ? (over ? `${hm(tag.minutes_in_range - goalMin)} over the cap` : `${hm(goalMin - tag.minutes_in_range)} left under the cap`) : tag.goal_status === 'met' ? 'Goal reached' : `${hm(goalMin - tag.minutes_in_range)} to go`

  return (
    <aside aria-label="Tag details" className="card flex min-w-0 flex-col p-4 md:p-[18px] lg:sticky lg:top-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <span className={clsx('inline-flex max-w-full items-center gap-2 rounded-full border bg-card py-1.5 pl-3 pr-3.5 font-display text-lg font-bold', over ? 'border-bad ring-2 ring-bad/30' : 'border-line')}><i className="size-3 flex-none rounded" style={{ background: tag.color }} /><span className="truncate">#{tag.name}</span></span>
          {over && <span className="rounded-full bg-bad/15 px-2.5 py-0.5 text-[11px] font-semibold text-bad">Over its cap</span>}
        </div>
        <IconButton icon="x" label="Close tag" onClick={onClose} className="lg:hidden" />
      </div>
      {tag.archived && <p role="status" className="m-0 mt-3 rounded-lg bg-line2 px-3 py-2 text-[13px] text-muted">Archived. It is hidden from pickers but stays on past activities.</p>}

      <div className="mt-3.5 flex flex-col gap-3">
        <Field label="Name">{(fid) => <Input id={fid} dense value={name} maxLength={48} onChange={(e) => setName(e.target.value)} />}</Field>
        {name.toLowerCase().replace(/^#/, '') !== tag.name && <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={keepAlias} onChange={(e) => setKeepAlias(e.target.checked)} />Keep “{tag.name}” as an alias</label>}
        <Field label="Description">{(fid) => <Textarea id={fid} value={desc} maxLength={300} placeholder="What does this tag mean?" onChange={(e) => setDesc(e.target.value)} className="min-h-16" />}</Field>
        <div className="flex justify-end"><Button variant="primary" size="sm" loading={update.isPending} disabled={name === tag.name && desc === (tag.description ?? '')} onClick={() => update.mutate({ id, name: name.replace(/^#/, ''), keep_old_name_as_alias: keepAlias, description: desc || null }, { onSuccess: () => toast.success('Tag saved'), onError: fail })}>Save changes</Button></div>
      </div>

      <Sect label="Colour"><ColorPicker value={tag.color} onChange={(c) => update.mutate({ id, color: c }, { onError: fail })} /></Sect>

      <Sect label="How it compares to your limit">
        <Segmented label="Weekly limit" value={tag.goal_kind} onChange={(k) => setGoal(k)} options={KINDS} />
        {goalMin > 0 ? (
          <>
            <div className="mt-2.5 flex flex-wrap items-center gap-2.5 text-[12.5px] text-muted">
              <span>{tag.goal_kind === 'max' ? 'No more than' : 'At least'}</span>
              <Input dense type="number" min={0.5} step={0.5} aria-label="Hours per week" className="!w-[78px] font-semibold" value={hours} onChange={(e) => setHours(e.target.value)} onBlur={() => Number(hours) > 0 && Math.round(Number(hours) * 60) !== goalMin && setGoal(tag.goal_kind as 'max' | 'min', hours)} />
              <span>hours a week</span><span className="num text-faint">≈ {hm(Math.round(goalMin / 7))} a day</span>
            </div>
            <div className="mt-3">
              <div className="mb-1.5 flex justify-between text-xs text-muted"><span>{rangeLabel}</span><b className="num font-semibold text-ink">{hm(tag.minutes_in_range)} of {hm(goalMin)}</b></div>
              <div className="relative h-3 overflow-hidden rounded-md bg-line2" role="img" aria-label={`${hm(tag.minutes_in_range)} of ${hm(goalMin)}`}><i className="absolute inset-y-0 left-0 rounded-md" style={{ width: `${pct}%`, background: over ? 'var(--bad)' : tag.goal_status === 'met' ? 'var(--good)' : 'var(--accent)' }} /></div>
              <div className={clsx('mt-1.5 text-xs font-medium', over ? 'text-bad' : 'text-muted')}>{status}</div>
            </div>
          </>
        ) : <p className="m-0 mt-2.5 text-[12.5px] text-muted">Tracked only. It shows up in charts, with no target.</p>}
      </Sect>

      <Sect label="Auto-tag when I say…">
        <p className="m-0 mb-2 text-[11.5px] text-faint">Whole words, case-insensitive. Used when you dictate or type a journal entry.</p>
        <div className="flex flex-wrap items-center gap-1.5">
          {(rules ?? []).map((r) => <span key={r.id} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-line2 py-[3px] pl-2.5 pr-1.5 text-xs">{r.phrase}<button aria-label={`Remove phrase ${r.phrase}`} className="flex size-5 items-center justify-center rounded text-faint hover:bg-card hover:text-ink" onClick={() => delRule.mutate(r.id, { onError: fail })}><Icon name="x" size={11} strokeWidth={2.4} /></button></span>)}
          <form className="inline-flex" onSubmit={(e) => { e.preventDefault(); if (phrase.trim()) addRule.mutate({ phrase: phrase.trim(), target_type: 'tag', target_id: id }, { onSuccess: () => setPhrase(''), onError: fail }) }}>
            <input aria-label="Add keyword" placeholder="+ keyword" maxLength={60} value={phrase} onChange={(e) => setPhrase(e.target.value)} className="h-[26px] w-28 rounded-lg border border-dashed border-ghostline bg-transparent px-2.5 text-xs outline-none placeholder:text-faint focus:border-accent focus:bg-card" />
          </form>
        </div>
      </Sect>

      <Sect label="Also known as">
        <div className="flex flex-wrap items-center gap-1.5">
          {tagAliases.map((a) => <span key={a} className="inline-flex items-center gap-1.5 rounded-full border border-line py-0.5 pl-2.5 pr-1.5 text-[11.5px] font-semibold">{a}<button aria-label={`Remove alias ${a}`} className="flex size-4 items-center justify-center rounded-full text-faint hover:bg-line2 hover:text-ink" onClick={() => aliases.mutate({ id, aliases: tagAliases.filter((x) => x !== a) }, { onError: fail })}><Icon name="x" size={10} strokeWidth={2.4} /></button></span>)}
          <form className="inline-flex" onSubmit={(e) => { e.preventDefault(); if (alias.trim()) aliases.mutate({ id, aliases: [...tagAliases, alias.trim()] }, { onSuccess: () => setAlias(''), onError: fail }) }}>
            <input aria-label="Add alias" placeholder="+ alias" maxLength={48} value={alias} onChange={(e) => setAlias(e.target.value)} className="h-[26px] w-24 rounded-full border border-dashed border-ghostline bg-transparent px-2.5 text-xs outline-none placeholder:text-faint focus:border-accent focus:bg-card" />
          </form>
        </div>
      </Sect>

      <Sect label={`Per day · ${rangeLabel.toLowerCase()}`}>
        <Columns items={tag.by_day.map((d) => ({ key: d.date, label: weekdayShort(d.date), sub: String(dayOfMonth(d.date)), value: d.minutes, color: tag.color, muted: d.minutes === 0 }))} height={118} />
        <p className="mb-0 mt-2 text-xs text-muted">{hm(tag.total_minutes)} in {rangeLabel.toLowerCase()}</p>
      </Sect>

      <Sect label="Recent activities">
        {tag.recent_activities.length === 0 ? <p className="m-0 text-[13px] text-muted">Nothing tagged yet.</p> : <ul className="m-0 list-none p-0">{tag.recent_activities.slice(0, 6).map((a) => (
          <li key={a.id}><button type="button" onClick={() => nav(`/activities/${a.id}`)} className="flex w-full items-center gap-3 rounded-lg px-1.5 py-2 text-left hover:bg-line2"><i className="h-7 w-[3px] flex-none rounded" style={{ background: a.category.color }} /><span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold">{a.title}</span><span className="text-[11px] text-faint">{weekdayShort(a.local_date)} {dayOfMonth(a.local_date)} · {a.category.name}</span></span><span className="num text-xs font-semibold text-muted">{hm(a.duration_minutes ?? 0)}</span></button></li>
        ))}</ul>}
      </Sect>

      <div className="mt-3.5 flex flex-wrap gap-2 border-t border-line2 pt-3.5">
        <Button size="sm" onClick={() => update.mutate({ id, archived: !tag.archived }, { onSuccess: () => toast.success(tag.archived ? 'Tag restored' : 'Tag archived'), onError: fail })}>{tag.archived ? 'Unarchive' : 'Archive'}</Button>
        <Button size="sm" icon="merge" onClick={() => setMergeOpen(true)}>Merge into…</Button>
        <Button size="sm" variant="ghost" icon="trash" className="text-bad" onClick={() => setConfirmDelete(true)}>Delete</Button>
      </div>

      <MergeDialog open={mergeOpen} onOpenChange={setMergeOpen} title={`Merge #${tag.name}`} description="Moves every activity, alias, phrase and goal to the other tag. The old name keeps working as an alias."
        options={targets} confirmLabel="Merge tags"
        preview={async (t) => { const r = await api.post<{ moved_links: number; deduplicated: number }>(`/tags/${id}/merge`, { target_id: t, preview: true }); return `${r.moved_links} activities move${r.deduplicated ? ` and ${r.deduplicated} already have the target tag` : ''}.` }}
        confirm={async (t) => { await merge.mutateAsync({ id, target_id: t }); onClose() }} />
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete} title={`Delete #${tag.name}?`} description="Only tags that no activity uses can be deleted."
        footer={<><Button variant="subtle" onClick={() => setConfirmDelete(false)}>Keep it</Button><Button variant="danger" loading={del.isPending} onClick={() => del.mutate(id, { onSuccess: () => { toast.success('Tag deleted'); onClose() }, onError: (e) => { setConfirmDelete(false); fail(e) } })}>Delete tag</Button></>}>
        <p className="m-0 text-sm text-muted">If it is in use, archive or merge it instead.</p>
      </Dialog>
    </aside>
  )
}

// ====================================================================================================================== categories
function CategoriesTab({ selected, onSelect, newOpen, setNewOpen }: { selected: string | null; onSelect: (id: string | null) => void; newOpen: boolean; setNewOpen: (v: boolean) => void }) {
  const [archived, setArchived] = useState(false)
  const { data: tree, isLoading, error, refetch } = useCategories(archived)
  const flat = flattenCategories(tree, archived)
  const current = flat.find((c) => c.id === selected)
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <section className={clsx('min-w-0', selected && 'max-lg:hidden')}>
        <label className="mb-3 flex items-center gap-2 text-[12.5px] font-medium text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Show archived</label>
        <div className="card overflow-hidden">
          {isLoading && <div className="flex flex-col gap-2 p-4"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
          {error && <ErrorState error={error} onRetry={() => refetch()} />}
          {tree && <>
            <p className="m-0 border-b border-line px-4 py-2 text-[11.5px] text-faint">Every activity has exactly one category, so category totals add up to the time you logged.</p>
            <ul className="m-0 list-none p-0">{flat.map((c) => (
              <li key={c.id} className="border-b border-line2 last:border-0">
                <button type="button" aria-current={c.id === selected ? 'true' : undefined} onClick={() => onSelect(c.id)} className={clsx('flex w-full items-center gap-2.5 px-4 py-2.5 text-left hover:bg-line2/60', c.id === selected && 'bg-tint', c.archived && 'opacity-55')} style={{ paddingLeft: 16 + (c.depth - 1) * 22 }}>
                  <i className="size-3 flex-none rounded" style={{ background: c.color }} />
                  <span className={clsx('min-w-0 flex-1 truncate text-[13.5px]', c.depth === 1 ? 'font-bold' : 'font-medium')}>{c.name}</span>
                  {c.counts_as_focus && <span className="rounded-full bg-tint px-2 py-0.5 text-[10.5px] font-semibold text-accent-ink">Focus</span>}
                  {c.is_transition && <span className="rounded-full bg-line2 px-2 py-0.5 text-[10.5px] font-semibold text-muted">Transition</span>}
                  {c.archived && <span className="text-[10.5px] font-semibold text-faint">Archived</span>}
                </button>
              </li>
            ))}</ul>
          </>}
        </div>
      </section>
      {current && <CategoryPanel key={current.id} cat={current} flat={flat} onClose={() => onSelect(null)} />}
      <NewCategoryDialog open={newOpen} onOpenChange={setNewOpen} onCreated={(id) => onSelect(id)} />
    </div>
  )
}

function NewCategoryDialog({ open, onOpenChange, onCreated, parent }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated: (id: string) => void; parent?: string }) {
  const { data: tree } = useCategories()
  const create = useCreateCategory()
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState(parent ?? '')
  const [focus, setFocus] = useState(false)
  const [error, setError] = useState<string>()
  useEffect(() => { if (open) setParentId(parent ?? parentId ?? '') }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!parentId && tree?.[0]) setParentId(tree[0].id) }, [tree, parentId])
  const eligible = flattenCategories(tree).filter((c) => c.depth < 3)
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New category" description="Categories can be three levels deep, for example Work › Clients › Acme."
      footer={<><Button variant="subtle" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" type="submit" form="new-cat" loading={create.isPending}>Create category</Button></>}>
      <form id="new-cat" noValidate className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); setError(undefined); create.mutate({ parent_id: parentId, name: name.trim(), counts_as_focus: focus }, { onSuccess: (c) => { setName(''); onOpenChange(false); onCreated(c.id) }, onError: (er) => setError(errorMessage(er)) }) }}>
        <Field label="Name" error={error}>{(id, d) => <Input id={id} aria-describedby={d} dense autoFocus maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <Field label="Inside">{(id) => <Select id={id} dense value={parentId} onChange={(e) => setParentId(e.target.value)}>{eligible.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</Select>}</Field>
        <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={focus} onChange={(e) => setFocus(e.target.checked)} />Counts as focus time (deep work, client work, learning)</label>
      </form>
    </Dialog>
  )
}

function CategoryPanel({ cat, flat, onClose }: { cat: FlatCategory; flat: FlatCategory[]; onClose: () => void }) {
  const update = useUpdateCategory(), del = useDeleteCategory(), merge = useMergeCategory()
  const [name, setName] = useState(cat.name)
  const [desc, setDesc] = useState(cat.description ?? '')
  const [addOpen, setAddOpen] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [parent, setParent] = useState(cat.parent_id ?? '')
  const fail = (e: unknown) => toast.error(errorMessage(e))
  const descendants = new Set(flat.filter((c) => c.path_names.startsWith(cat.path_names + ' ›')).map((c) => c.id))
  const parents = flat.filter((c) => c.id !== cat.id && !descendants.has(c.id) && c.root_kind === cat.root_kind && c.depth < 3)
  const mergeTargets = flat.filter((c) => c.id !== cat.id && !descendants.has(c.id) && c.root_kind === cat.root_kind && c.depth > 1).map((c) => ({ id: c.id, label: c.label }))
  const root = cat.depth === 1

  return (
    <aside aria-label="Category details" className="card flex min-w-0 flex-col gap-5 p-4 md:p-5">
      <div className="flex items-center justify-between"><CategoryChip name={cat.path_names} color={cat.color} /><IconButton icon="x" label="Close category" onClick={onClose} /></div>
      {root && <p role="status" className="m-0 rounded-lg bg-line2 px-3 py-2 text-[13px] text-muted">Work, Personal and Sleep are built in. You can recolour them and add categories inside.</p>}
      {cat.archived && <p role="status" className="m-0 rounded-lg bg-line2 px-3 py-2 text-[13px] text-muted">Archived. Hidden from pickers; history is kept.</p>}
      <div className="flex flex-col gap-3">
        <Field label="Name">{(id) => <Input id={id} dense value={name} disabled={root} maxLength={60} onChange={(e) => setName(e.target.value)} />}</Field>
        <Field label="Colour">{() => <ColorPicker value={cat.color} onChange={(c) => update.mutate({ id: cat.id, color: c }, { onError: fail })} />}</Field>
        <Field label="Description" hint="Shown to the AI when it picks a category.">{(id) => <Textarea id={id} className="min-h-16" maxLength={300} value={desc} onChange={(e) => setDesc(e.target.value)} />}</Field>
        <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={cat.counts_as_focus} onChange={(e) => update.mutate({ id: cat.id, counts_as_focus: e.target.checked }, { onError: fail })} />Counts as focus time</label>
        {!root && <Field label="Move inside">{(id) => <Select id={id} dense value={parent} onChange={(e) => { setParent(e.target.value); update.mutate({ id: cat.id, parent_id: e.target.value }, { onSuccess: () => toast.success('Moved'), onError: (er) => { setParent(cat.parent_id ?? ''); fail(er) } }) }}>{parents.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</Select>}</Field>}
        <div className="flex justify-end"><Button variant="primary" size="sm" loading={update.isPending} onClick={() => update.mutate({ id: cat.id, ...(root ? {} : { name: name.trim() }), description: desc || null }, { onSuccess: () => toast.success('Category saved'), onError: fail })}>Save changes</Button></div>
      </div>
      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        {cat.depth < 3 && <Button size="sm" icon="plus" onClick={() => setAddOpen(true)}>Add inside</Button>}
        {!root && <>
          <Button size="sm" onClick={() => update.mutate({ id: cat.id, archived: !cat.archived }, { onSuccess: () => toast.success(cat.archived ? 'Restored' : 'Archived'), onError: fail })}>{cat.archived ? 'Unarchive' : 'Archive'}</Button>
          <Button size="sm" icon="merge" onClick={() => setMergeOpen(true)}>Merge into…</Button>
          <Button size="sm" variant="ghost" icon="trash" className="text-bad" onClick={() => setConfirmDelete(true)}>Delete</Button>
        </>}
      </div>
      <NewCategoryDialog open={addOpen} onOpenChange={setAddOpen} parent={cat.id} onCreated={() => undefined} />
      <MergeDialog open={mergeOpen} onOpenChange={setMergeOpen} title={`Merge ${cat.name}`} description="Moves its activities, Ideal allocation and phrases into the other category, then archives this one."
        options={mergeTargets} confirmLabel="Merge categories"
        preview={async (t) => { const r = await api.post<{ moved_activities: number; moved_allocations: number }>(`/categories/${cat.id}/merge`, { target_id: t, preview: true }); return `${r.moved_activities} activities${r.moved_allocations ? ` and ${r.moved_allocations} Ideal allocation` : ''} will move.` }}
        confirm={async (t) => { await merge.mutateAsync({ id: cat.id, target_id: t }); onClose() }} />
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete} title={`Delete ${cat.name}?`} description="Only a category with no activities can be deleted."
        footer={<><Button variant="subtle" onClick={() => setConfirmDelete(false)}>Keep it</Button><Button variant="danger" loading={del.isPending} onClick={() => del.mutate(cat.id, { onSuccess: () => { toast.success('Category deleted'); onClose() }, onError: (e) => { setConfirmDelete(false); fail(e) } })}>Delete category</Button></>}>
        <p className="m-0 text-sm text-muted">If it has activities, merge it into another category instead.</p>
      </Dialog>
    </aside>
  )
}
