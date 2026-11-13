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
import { PageHeader } from '@/components/layout/PageHeader'
import { Button, IconButton } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Field, Input, Select, Textarea } from '@/components/ui/Field'
import { PALETTE } from '@/lib/colors'
import { dayOfMonth, hm, weekdayShort } from '@/lib/time'
import { toast } from '@/stores/toastStore'
import { ColorPicker, MergeDialog } from './shared'

export function TagsPage() {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') === 'categories' ? 'categories' : 'tags'
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }
  return (
    <>
      <PageHeader title="Tags & categories" subtitle="Categories split your 24 hours once. Tags overlap and can carry weekly limits." />
      <Tabs.Root value={tab} onValueChange={(v) => { const n = new URLSearchParams(); n.set('tab', v); setSp(n) }} className="p-4 md:px-7 md:py-5">
        <Tabs.List aria-label="Taxonomy" className="mb-4 inline-flex rounded-[10px] border border-line bg-line2 p-[3px]">
          {[['tags', 'Tags'], ['categories', 'Categories']].map(([v, l]) => <Tabs.Trigger key={v} value={v} className="min-h-[30px] rounded-[7px] px-4 text-[12.5px] font-medium text-muted data-[state=active]:bg-card data-[state=active]:font-semibold data-[state=active]:text-ink data-[state=active]:shadow-sm">{l}</Tabs.Trigger>)}
        </Tabs.List>
        <Tabs.Content value="tags"><TagsTab selected={sp.get('tag')} onSelect={(id) => set('tag', id)} /></Tabs.Content>
        <Tabs.Content value="categories"><CategoriesTab selected={sp.get('cat')} onSelect={(id) => set('cat', id)} /></Tabs.Content>
      </Tabs.Root>
    </>
  )
}

// ====================================================================================================================== tags
function GoalBar({ tag }: { tag: Tag }) {
  if (tag.goal_kind === 'tracked' || !tag.goal_weekly_minutes) return <span className="num text-xs text-muted">{hm(tag.minutes_in_range)}</span>
  const pct = Math.min(100, (tag.minutes_in_range / tag.goal_weekly_minutes) * 100)
  const color = tag.goal_status === 'over' ? 'var(--bad)' : tag.goal_status === 'met' ? 'var(--good)' : 'var(--accent)'
  return (
    <div className="flex min-w-28 items-center gap-2" title={`${hm(tag.minutes_in_range)} of ${tag.goal_kind === 'max' ? 'max ' : 'min '}${hm(tag.goal_weekly_minutes)} this week`}>
      <div className="h-1.5 flex-1 overflow-hidden rounded bg-line2"><i className="block h-full rounded" style={{ width: `${pct}%`, background: color }} /></div>
      <span className="num text-xs text-muted">{hm(tag.minutes_in_range)}/{hm(tag.goal_weekly_minutes)}</span>
    </div>
  )
}

function TagsTab({ selected, onSelect }: { selected: string | null; onSelect: (id: string | null) => void }) {
  const [archived, setArchived] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const { data: tags, isLoading, error, refetch } = useTags({ archived })
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
      <section className={clsx('min-w-0', selected && 'max-lg:hidden')}>
        <div className="mb-3 flex items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-[12.5px] font-medium text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Show archived</label>
          <Button variant="primary" icon="plus" onClick={() => setNewOpen(true)}>New tag</Button>
        </div>
        <div className="card overflow-hidden">
          {isLoading && <div className="flex flex-col gap-2 p-4"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
          {error && <ErrorState error={error} onRetry={() => refetch()} />}
          {tags && tags.length === 0 && <EmptyState icon="tag" title={archived ? 'No archived tags' : 'No tags yet'} action={!archived ? <Button variant="primary" icon="plus" onClick={() => setNewOpen(true)}>Create a tag</Button> : undefined}>Tags describe what an activity was about (#product-b, #p0, #social-media). One activity can have many.</EmptyState>}
          {tags && tags.length > 0 && <>
            <p className="m-0 border-b border-line px-4 py-2 text-[11.5px] text-faint">Hours this week. Tags overlap, so tag totals can exceed your logged time.</p>
            <ul className="m-0 list-none p-0">{tags.map((t) => (
              <li key={t.id} className="border-b border-line2 last:border-0">
                <button type="button" aria-current={t.id === selected ? 'true' : undefined} onClick={() => onSelect(t.id)} className={clsx('flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-line2/60', t.id === selected && 'bg-tint')}>
                  <TagChip name={t.name} color={t.color} over={t.goal_status === 'over'} />
                  <span className="flex items-center gap-3">{t.goal_status === 'over' && <span className="rounded-full bg-bad/15 px-2 py-0.5 text-[10.5px] font-semibold text-bad">Over cap</span>}<GoalBar tag={t} /></span>
                </button>
              </li>
            ))}</ul>
          </>}
        </div>
      </section>
      {selected && <TagPanel id={selected} onClose={() => onSelect(null)} />}
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

function TagPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const nav = useNavigate()
  const { data: tag, isLoading, error, refetch } = useTag(id)
  const { data: allTags } = useTags()
  const { data: rules } = useRules({ target_type: 'tag', target_id: id })
  const update = useUpdateTag(), del = useDeleteTag(), merge = useMergeTag(), aliases = usePutAliases(), addRule = useCreateRule(), delRule = useDeleteRule()
  const [name, setName] = useState('')
  const [keepAlias, setKeepAlias] = useState(true)
  const [desc, setDesc] = useState('')
  const [goal, setGoal] = useState<'tracked' | 'min' | 'max'>('tracked')
  const [hours, setHours] = useState('')
  const [alias, setAlias] = useState('')
  const [phrase, setPhrase] = useState('')
  const [mergeOpen, setMergeOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => {
    if (!tag) return
    setName(tag.name); setDesc(tag.description ?? ''); setGoal(tag.goal_kind); setHours(tag.goal_weekly_minutes ? String(tag.goal_weekly_minutes / 60) : '5')
  }, [tag?.id, tag?.name, tag?.description, tag?.goal_kind, tag?.goal_weekly_minutes]) // eslint-disable-line react-hooks/exhaustive-deps
  const fail = (e: unknown) => toast.error(errorMessage(e))
  if (isLoading) return <div className="card flex flex-col gap-3 p-5"><Skeleton className="h-8" /><Skeleton className="h-40" /></div>
  if (error || !tag) return <div className="card"><ErrorState error={error} onRetry={() => refetch()} compact /></div>
  const tagAliases = tag.aliases ?? []
  const max = Math.max(...tag.by_day.map((d) => d.minutes), 1)
  const targets = (allTags ?? []).filter((t) => t.id !== id).map((t) => ({ id: t.id, label: `#${t.name}` }))

  return (
    <aside aria-label="Tag details" className="card flex min-w-0 flex-col gap-5 p-4 md:p-5">
      <div className="flex items-center justify-between"><TagChip name={tag.name} color={tag.color} over={tag.goal_status === 'over'} /><IconButton icon="x" label="Close tag" onClick={onClose} /></div>
      {tag.archived && <p role="status" className="m-0 rounded-lg bg-line2 px-3 py-2 text-[13px] text-muted">Archived. It is hidden from pickers but stays on past activities.</p>}

      <div className="flex flex-col gap-3">
        <Field label="Name">{(fid) => <Input id={fid} dense value={name} maxLength={48} onChange={(e) => setName(e.target.value)} />}</Field>
        {name.toLowerCase().replace(/^#/, '') !== tag.name && <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={keepAlias} onChange={(e) => setKeepAlias(e.target.checked)} />Keep “{tag.name}” as an alias</label>}
        <Field label="Colour">{() => <ColorPicker value={tag.color} onChange={(c) => update.mutate({ id, color: c }, { onError: fail })} />}</Field>
        <Field label="Description">{(fid) => <Textarea id={fid} value={desc} maxLength={300} onChange={(e) => setDesc(e.target.value)} className="min-h-16" />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Weekly goal">{(fid) => <Select id={fid} dense value={goal} onChange={(e) => setGoal(e.target.value as any)}><option value="tracked">Just track it</option><option value="max">At most</option><option value="min">At least</option></Select>}</Field>
          {goal !== 'tracked' && <Field label="Hours per week">{(fid) => <Input id={fid} dense type="number" min={0.5} step={0.5} value={hours} onChange={(e) => setHours(e.target.value)} />}</Field>}
        </div>
        <div className="flex justify-end"><Button variant="primary" size="sm" loading={update.isPending} onClick={() => update.mutate({ id, name: name.replace(/^#/, ''), keep_old_name_as_alias: keepAlias, description: desc || null, goal_kind: goal, goal_weekly_minutes: goal === 'tracked' ? null : Math.round(Number(hours) * 60) }, { onSuccess: () => toast.success('Tag saved'), onError: fail })}>Save changes</Button></div>
      </div>

      <section><h3 className="m-0 mb-2 text-[13px] font-semibold">This week</h3>
        <div className="flex items-end gap-1.5" role="img" aria-label={`Per day: ${tag.by_day.map((d) => `${d.date} ${hm(d.minutes)}`).join(', ')}`}>
          {tag.by_day.map((d) => <div key={d.date} className="flex flex-1 flex-col items-center gap-1" title={`${d.date}: ${hm(d.minutes)}`}><i className="block w-full max-w-[28px] rounded" style={{ height: Math.max(3, (d.minutes / max) * 56), background: tag.color, opacity: d.minutes ? 1 : 0.25 }} /><span className="text-[10px] text-faint">{weekdayShort(d.date)[0]}</span></div>)}
        </div>
        <p className="mb-0 mt-2 text-xs text-muted">{hm(tag.total_minutes)} total{tag.goal_weekly_minutes ? ` · ${tag.goal_kind === 'max' ? 'cap' : 'goal'} ${hm(tag.goal_weekly_minutes)}` : ''}</p>
      </section>

      <section><h3 className="m-0 mb-2 text-[13px] font-semibold">Also known as</h3>
        <div className="mb-2 flex flex-wrap gap-1.5">{tagAliases.length === 0 && <span className="text-xs text-faint">No aliases</span>}{tagAliases.map((a) => <span key={a} className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold">{a}<button aria-label={`Remove alias ${a}`} className="text-faint hover:text-ink" onClick={() => aliases.mutate({ id, aliases: tagAliases.filter((x) => x !== a) }, { onError: fail })}>×</button></span>)}</div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (alias.trim()) aliases.mutate({ id, aliases: [...tagAliases, alias.trim()] }, { onSuccess: () => setAlias(''), onError: fail }) }}><Input dense aria-label="Add alias" placeholder="Add an alias" maxLength={48} value={alias} onChange={(e) => setAlias(e.target.value)} /><Button type="submit" size="md">Add</Button></form>
      </section>

      <section><h3 className="m-0 mb-1 text-[13px] font-semibold">Auto-tag when I say…</h3><p className="m-0 mb-2 text-xs text-muted">Whole words, case-insensitive. Used when the AI journal arrives.</p>
        <div className="mb-2 flex flex-wrap gap-1.5">{(rules ?? []).length === 0 && <span className="text-xs text-faint">No phrases</span>}{(rules ?? []).map((r) => <span key={r.id} className="inline-flex items-center gap-1 rounded-full bg-line2 px-2.5 py-0.5 text-[11px] font-semibold">“{r.phrase}”<button aria-label={`Remove phrase ${r.phrase}`} className="text-faint hover:text-ink" onClick={() => delRule.mutate(r.id, { onError: fail })}>×</button></span>)}</div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (phrase.trim()) addRule.mutate({ phrase: phrase.trim(), target_type: 'tag', target_id: id }, { onSuccess: () => setPhrase(''), onError: fail }) }}><Input dense aria-label="Add phrase" placeholder="e.g. scrolled instagram" maxLength={60} value={phrase} onChange={(e) => setPhrase(e.target.value)} /><Button type="submit">Add</Button></form>
      </section>

      <section><h3 className="m-0 mb-1.5 text-[13px] font-semibold">Recent activities</h3>
        {tag.recent_activities.length === 0 ? <p className="m-0 text-[13px] text-muted">Nothing tagged yet.</p> : <ul className="m-0 list-none p-0">{tag.recent_activities.slice(0, 6).map((a) => (
          <li key={a.id}><button type="button" onClick={() => nav(`/activities/${a.id}`)} className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-2 text-left hover:bg-line2"><i className="h-6 w-[3px] rounded" style={{ background: a.category.color }} /><span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium">{a.title}</span><span className="text-[11px] text-faint">{weekdayShort(a.local_date)} {dayOfMonth(a.local_date)}</span></span><span className="num text-xs text-muted">{hm(a.duration_minutes ?? 0)}</span></button></li>
        ))}</ul>}
      </section>

      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
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
function CategoriesTab({ selected, onSelect }: { selected: string | null; onSelect: (id: string | null) => void }) {
  const [archived, setArchived] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const { data: tree, isLoading, error, refetch } = useCategories(archived)
  const flat = flattenCategories(tree, archived)
  const current = flat.find((c) => c.id === selected)
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
      <section className={clsx('min-w-0', selected && 'max-lg:hidden')}>
        <div className="mb-3 flex items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-[12.5px] font-medium text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Show archived</label>
          <Button variant="primary" icon="plus" onClick={() => setNewOpen(true)}>New category</Button>
        </div>
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
