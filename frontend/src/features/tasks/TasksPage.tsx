import clsx from 'clsx'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { errorMessage } from '@/api/errors'
import { useCreateProject, useCreateTask, useDeleteTask, useProjects, useTask, useTasks, useUpdateProject, useUpdateTask } from '@/api/hooks/useTasks'
import type { Task } from '@/api/types'
import { ProjectSelect } from '@/components/domain/Pickers'
import { PageHeader, Segmented } from '@/components/layout/PageHeader'
import { Button, IconButton } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Field, Input, Select, Textarea } from '@/components/ui/Field'
import { Icon } from '@/components/ui/Icon'
import { dayAndMonth, dayOfMonth, hm, weekdayShort } from '@/lib/time'
import { toast } from '@/stores/toastStore'

const PRIORITIES = ['P0', 'P1', 'P2', 'P3']

function DueBadge({ t }: { t: Task }) {
  if (!t.due_date || t.status !== 'open') return null
  const label = t.overdue ? `${Math.abs(t.days_left!)}d overdue` : t.days_left === 0 ? 'Due today' : t.days_left === 1 ? 'Tomorrow' : `${dayAndMonth(t.due_date)}`
  return <span className={clsx('rounded-full px-2 py-0.5 text-[10.5px] font-semibold', t.overdue ? 'bg-bad/15 text-bad' : (t.days_left ?? 99) <= 3 ? 'bg-warn/15 text-warn' : 'bg-line2 text-muted')}>{label}</span>
}

export function TasksPage() {
  const { taskId } = useParams()
  const nav = useNavigate()
  const [status, setStatus] = useState('open')
  const [project, setProject] = useState('')
  const [q, setQ] = useState('')
  const [newOpen, setNewOpen] = useState(false)
  const [projectsOpen, setProjectsOpen] = useState(false)
  const { data: tasks, isLoading, error, refetch } = useTasks({ status: status || undefined, project_id: project || undefined, q: q || undefined })
  const { data: projects } = useProjects()
  const pname = new Map((projects ?? []).map((p) => [p.id, p]))
  const updateTask = useUpdateTask()
  const toggle = (t: Task) => updateTask.mutate({ id: t.id, version: t.version, status: t.status === 'done' ? 'open' : 'done', clear: [] } as any, { onError: (e) => toast.error(errorMessage(e)) })
  const stats = {
    open: (tasks ?? []).filter((t) => t.status === 'open').length,
    overdue: (tasks ?? []).filter((t) => t.status === 'open' && t.overdue).length,
    soon: (tasks ?? []).filter((t) => t.status === 'open' && !t.overdue && t.days_left != null && t.days_left <= 7).length,
    logged: (tasks ?? []).filter((t) => t.status === 'open').reduce((a, t) => a + t.logged_minutes, 0),
  }

  return (
    <>
      <PageHeader title="Tasks" subtitle="Work items that collect time across days">
        <Button icon="folder" onClick={() => setProjectsOpen(true)}>Projects</Button>
        <Button variant="primary" icon="plus" onClick={() => setNewOpen(true)}>New task</Button>
      </PageHeader>
      <div className={clsx('grid items-start gap-4 p-4 md:px-7 md:py-[22px] md:pb-10', taskId && 'lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]')}>
        <section className={clsx('flex min-w-0 flex-col gap-4', taskId && 'max-lg:hidden')}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ['Open', `${stats.open}`, 'tasks still to finish', undefined],
              ['Overdue', `${stats.overdue}`, stats.overdue ? 'need attention' : 'nothing late', stats.overdue ? 'text-bad' : undefined],
              ['Due this week', `${stats.soon}`, 'in the next 7 days', undefined],
              ['Logged on open tasks', hm(stats.logged), 'across all days', undefined],
            ].map(([l, v, h, c]) => (
              <div key={l} className="card flex flex-col gap-1.5 p-4"><div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{l}</div><div className={clsx('num text-[26px] font-semibold leading-none', c)}>{v}</div><div className="text-xs text-muted">{h}</div></div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="relative min-w-52 flex-1"><Icon name="search" size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint" /><Input aria-label="Search tasks" placeholder="Search tasks" className="h-10 pl-10" value={q} onChange={(e) => setQ(e.target.value)} /></div>
            <Segmented label="Status" value={status} onChange={setStatus} options={[{ value: 'open', label: 'Open' }, { value: 'done', label: 'Done' }, { value: 'dropped', label: 'Dropped' }, { value: '', label: 'All' }]} />
            <Select aria-label="Project" className="h-10 !w-52" value={project} onChange={(e) => setProject(e.target.value)}><option value="">All projects</option>{(projects ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
          </div>
          <div className="card overflow-hidden">
            {isLoading && <div className="flex flex-col gap-2 p-4"><Skeleton className="h-16" /><Skeleton className="h-16" /><Skeleton className="h-16" /></div>}
            {error && <ErrorState error={error} onRetry={() => refetch()} />}
            {tasks && tasks.length === 0 && <EmptyState icon="tasks" title={q || project || status !== 'open' ? 'No tasks match' : 'No tasks yet'} action={<Button variant="primary" icon="plus" onClick={() => setNewOpen(true)}>New task</Button>}>Tasks appear as you log work, or add one now. A task can exist with zero time.</EmptyState>}
            {tasks && tasks.length > 0 && (
              <ul className="m-0 list-none p-0">
                {tasks.map((t) => {
                  const proj = t.project_id ? pname.get(t.project_id) : undefined
                  const pct = t.estimate_minutes ? Math.min(100, (t.logged_minutes / t.estimate_minutes) * 100) : null
                  return (
                    <li key={t.id} className={clsx('group flex items-center gap-3.5 border-b border-line2 px-5 py-3.5 last:border-0 hover:bg-line2/60', t.id === taskId && 'bg-tint')}>
                      <button type="button" aria-label={t.status === 'done' ? `Reopen ${t.title}` : `Mark ${t.title} done`} onClick={() => toggle(t)}
                        className={clsx('flex size-[22px] flex-none items-center justify-center rounded-full border-2 transition', t.status === 'done' ? 'border-good bg-good text-white' : t.status === 'dropped' ? 'border-ghostline text-faint' : 'border-ghostline text-transparent hover:border-good hover:text-good')}>
                        {t.status === 'dropped' ? <Icon name="x" size={12} strokeWidth={2.4} /> : <Icon name="check" size={13} strokeWidth={3} />}
                      </button>
                      <button type="button" onClick={() => nav(`/tasks/${t.id}`)} aria-current={t.id === taskId ? 'true' : undefined} className="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 text-left">
                        <span className="min-w-0">
                          <span className={clsx('block truncate text-sm font-semibold', t.status !== 'open' && 'text-muted line-through')}>{t.title}</span>
                          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                            <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-[3px]" style={{ background: proj?.color ?? 'var(--ghostline)' }} />{proj?.name ?? 'No project'}</span>
                            <span className="num font-medium">{hm(t.logged_minutes)}{t.estimate_minutes ? ` of ${hm(t.estimate_minutes)}` : ''} logged</span>
                          </span>
                        </span>
                        <span className="flex items-center gap-2">
                          {t.priority !== null && <span className={clsx('rounded-md px-2 py-0.5 text-[11px] font-bold', t.priority === 0 ? 'bg-bad/15 text-bad' : 'bg-line2 text-muted')}>{PRIORITIES[t.priority]}</span>}
                          <DueBadge t={t} />
                        </span>
                        {pct !== null && <span className="col-span-2 h-1.5 overflow-hidden rounded-full bg-line2" role="img" aria-label={`${Math.round(pct)}% of the estimate`}><i className="block h-full rounded-full" style={{ width: `${pct}%`, background: t.logged_minutes > (t.estimate_minutes ?? 0) ? 'var(--warn)' : 'var(--accent)' }} /></span>}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </section>
        {taskId && <TaskDetail id={taskId} onClose={() => nav('/tasks')} />}
      </div>
      <NewTaskDialog open={newOpen} onOpenChange={setNewOpen} onCreated={(id) => nav(`/tasks/${id}`)} />
      <ProjectsDialog open={projectsOpen} onOpenChange={setProjectsOpen} />
    </>
  )
}

function NewTaskDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated: (id: string) => void }) {
  const create = useCreateTask()
  const [title, setTitle] = useState('')
  const [project, setProject] = useState('')
  const [priority, setPriority] = useState('')
  const [due, setDue] = useState('')
  const [error, setError] = useState<string>()
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return setError('Give the task a title.')
    create.mutate({ title: title.trim(), project_id: project || null, priority: priority === '' ? null : Number(priority), due_date: due || null }, {
      onSuccess: (t) => { setTitle(''); setProject(''); setPriority(''); setDue(''); setError(undefined); onOpenChange(false); onCreated(t.id) },
      onError: (e) => setError(errorMessage(e)),
    })
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New task" footer={<><Button variant="subtle" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" type="submit" form="new-task" loading={create.isPending}>Create task</Button></>}>
      <form id="new-task" onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Field label="Title" error={error}>{(id, d) => <Input id={id} aria-describedby={d} dense autoFocus maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Fix sync bug" />}</Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Project">{(id) => <ProjectSelect id={id} dense value={project} onChange={setProject} />}</Field>
          <Field label="Priority">{(id) => <Select id={id} dense value={priority} onChange={(e) => setPriority(e.target.value)}><option value="">None</option>{PRIORITIES.map((p, i) => <option key={p} value={i}>{p}</option>)}</Select>}</Field>
          <Field label="Due">{(id) => <Input id={id} dense type="date" value={due} onChange={(e) => setDue(e.target.value)} />}</Field>
        </div>
      </form>
    </Dialog>
  )
}

function TaskDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const nav = useNavigate()
  const { data: t, isLoading, error, refetch } = useTask(id)
  const update = useUpdateTask()
  const del = useDeleteTask()
  const [draft, setDraft] = useState<Record<string, any>>({})
  const [confirmDelete, setConfirmDelete] = useState(false)
  const val = <K extends keyof Task>(k: K) => (k in draft ? draft[k as string] : (t as Task | undefined)?.[k])
  const dirty = Object.keys(draft).length > 0

  const save = () => {
    if (!t) return
    const clear: string[] = []
    const body: Record<string, any> = { id: t.id, version: t.version }
    for (const [k, v] of Object.entries(draft)) { if (v === null || v === '') clear.push(k); else body[k] = v }
    update.mutate({ ...body, clear } as any, { onSuccess: () => { setDraft({}); toast.success('Task saved') }, onError: (e) => toast.error(errorMessage(e)) })
  }

  return (
    <aside aria-label="Task details" className="min-w-0">
      <div className="card p-4 md:p-5">
        <div className="mb-3 flex items-center justify-between"><h2 className="m-0 text-sm font-semibold">Task</h2><IconButton icon="x" label="Close task" onClick={onClose} /></div>
        {isLoading && <div className="flex flex-col gap-3"><Skeleton className="h-9" /><Skeleton className="h-28" /></div>}
        {error && <ErrorState error={error} onRetry={() => refetch()} compact />}
        {t && (
          <div className="flex flex-col gap-4">
            <Field label="Title">{(fid) => <Input id={fid} dense value={val('title') as string} maxLength={160} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />}</Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Status">{(fid) => <Select id={fid} dense value={val('status') as string} onChange={(e) => setDraft({ ...draft, status: e.target.value })}><option value="open">Open</option><option value="done">Done</option><option value="dropped">Dropped</option></Select>}</Field>
              <Field label="Priority">{(fid) => <Select id={fid} dense value={String(val('priority') ?? '')} onChange={(e) => setDraft({ ...draft, priority: e.target.value === '' ? null : Number(e.target.value) })}><option value="">None</option>{PRIORITIES.map((p, i) => <option key={p} value={i}>{p}</option>)}</Select>}</Field>
              <Field label="Due">{(fid) => <Input id={fid} dense type="date" value={(val('due_date') as string) ?? ''} onChange={(e) => setDraft({ ...draft, due_date: e.target.value || null })} />}</Field>
              <Field label="Project">{(fid) => <ProjectSelect id={fid} dense value={(val('project_id') as string) ?? ''} onChange={(v) => setDraft({ ...draft, project_id: v || null })} />}</Field>
              <Field label="Estimate (min)">{(fid) => <Input id={fid} dense type="number" min={1} value={(val('estimate_minutes') as number | null) ?? ''} onChange={(e) => setDraft({ ...draft, estimate_minutes: e.target.value ? Number(e.target.value) : null })} />}</Field>
            </div>
            <Field label="Notes">{(fid) => <Textarea id={fid} value={(val('description') as string) ?? ''} maxLength={4000} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />}</Field>
            <div className="flex items-center justify-between">
              <Button variant="ghost" size="sm" icon="trash" className="text-bad" onClick={() => setConfirmDelete(true)}>Delete</Button>
              <div className="flex gap-2"><Button size="sm" variant="subtle" disabled={!dirty} onClick={() => setDraft({})}>Reset</Button><Button size="sm" variant="primary" disabled={!dirty} loading={update.isPending} onClick={save}>Save</Button></div>
            </div>

            <hr className="m-0 border-line" />
            <div>
              <div className="mb-2 flex items-baseline justify-between"><h3 className="m-0 text-[13px] font-semibold">Time logged</h3><span className="num text-lg font-semibold">{hm(t.rollup.total_minutes)}</span></div>
              {t.rollup.by_day.length === 0 ? <p className="m-0 text-[13px] text-muted">No time logged yet. Link activities to this task from the Calendar.</p> : <DayBars points={t.rollup.by_day} />}
            </div>
            {t.activities.length > 0 && (
              <div><h3 className="m-0 mb-1.5 text-[13px] font-semibold">Linked activities</h3>
                <ul className="m-0 list-none p-0">{t.activities.map((a) => (
                  <li key={a.id}><button type="button" onClick={() => nav(`/activities/${a.id}`)} className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-2 text-left hover:bg-line2">
                    <i className="h-6 w-[3px] flex-none rounded" style={{ background: a.category.color }} />
                    <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-medium">{a.title}</span><span className="block text-[11px] text-faint">{weekdayShort(a.local_date)} {dayAndMonth(a.local_date)}</span></span>
                    <span className="num text-xs font-semibold text-muted">{hm(a.duration_minutes ?? 0)}</span></button></li>
                ))}</ul>
              </div>
            )}
          </div>
        )}
      </div>
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete} title="Delete this task?" description="Its logged activities are kept and simply unlinked."
        footer={<><Button variant="subtle" onClick={() => setConfirmDelete(false)}>Keep it</Button><Button variant="danger" loading={del.isPending} onClick={() => del.mutate(id, { onSuccess: () => { toast.success('Task deleted'); onClose() }, onError: (e) => toast.error(errorMessage(e)) })}>Delete task</Button></>}>
        <p className="m-0 text-sm text-muted">Time already logged against it stays in your totals.</p>
      </Dialog>
    </aside>
  )
}

function DayBars({ points }: { points: { key: string; minutes: number }[] }) {
  const max = Math.max(...points.map((p) => p.minutes), 1)
  return (
    <div className="flex items-end gap-1.5" role="img" aria-label={`Time logged by day: ${points.map((p) => `${p.key} ${hm(p.minutes)}`).join(', ')}`}>
      {points.slice(-14).map((p) => (
        <div key={p.key} className="flex flex-1 flex-col items-center gap-1" title={`${p.key}: ${hm(p.minutes)}`}>
          <i className="block w-full max-w-[26px] rounded bg-accent" style={{ height: Math.max(4, (p.minutes / max) * 64) }} />
          <span className="num text-[10px] text-faint">{dayOfMonth(p.key)}</span>
        </div>
      ))}
    </div>
  )
}

function ProjectsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { data: projects } = useProjects()
  const create = useCreateProject()
  const update = useUpdateProject()
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null)
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Projects" description="Group tasks, for example by product or client.">
      <div className="flex flex-col gap-4">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate({ name: name.trim() }, { onSuccess: () => setName(''), onError: (er) => toast.error(errorMessage(er)) }) }}>
          <Input dense aria-label="New project name" placeholder="New project" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          <Button type="submit" variant="primary" icon="plus" loading={create.isPending}>Add</Button>
        </form>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {(projects ?? []).length === 0 && <li className="text-[13px] text-muted">No projects yet.</li>}
          {(projects ?? []).map((p) => (
            <li key={p.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2">
              {editing?.id === p.id ? (
                <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); update.mutate({ id: p.id, name: editing.name }, { onSuccess: () => setEditing(null), onError: (er) => toast.error(errorMessage(er)) }) }}>
                  <Input dense autoFocus aria-label="Project name" value={editing.name} onChange={(e) => setEditing({ id: p.id, name: e.target.value })} /><Button type="submit" size="sm" variant="primary">Save</Button>
                </form>
              ) : (
                <>
                  <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold">{p.name}</span><span className="text-[11px] text-faint">{p.task_count} tasks · {hm(p.logged_minutes)}</span></span>
                  <IconButton icon="edit" label={`Rename ${p.name}`} onClick={() => setEditing({ id: p.id, name: p.name })} />
                  <Button size="sm" variant="subtle" onClick={() => update.mutate({ id: p.id, archived: true }, { onSuccess: () => toast.success(`${p.name} archived`) })}>Archive</Button>
                </>
              )}
            </li>
          ))}
        </ul>
      </div>
    </Dialog>
  )
}
