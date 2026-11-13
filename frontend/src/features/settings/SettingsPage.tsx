import clsx from 'clsx'
import { useEffect, useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router-dom'
import { errorMessage } from '@/api/errors'
import { useChangePassword, useLogout, useResendVerification } from '@/api/hooks/useAuth'
import { useAuthEvents, useDeleteAccount, useExportJob, usePreferences, useRequestExport, useUpdatePreferences, useUpdateProfile } from '@/api/hooks/useSettings'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Field, Input, Select } from '@/components/ui/Field'
import { Icon, type IconName } from '@/components/ui/Icon'
import { allTimezones } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore, type ThemeMode } from '@/stores/themeStore'
import { toast } from '@/stores/toastStore'

const SECTIONS: { id: string; label: string; icon: IconName }[] = [
  { id: 'profile', label: 'Profile', icon: 'user' },
  { id: 'preferences', label: 'Preferences', icon: 'sliders' },
  { id: 'appearance', label: 'Appearance', icon: 'sun' },
  { id: 'security', label: 'Security', icon: 'shield' },
  { id: 'data', label: 'Your data', icon: 'download' },
]

export function SettingsPage() {
  const { section = 'profile' } = useParams()
  return (
    <>
      <PageHeader title="Settings" subtitle="Your account, preferences and data" />
      <div className="grid gap-5 p-4 md:grid-cols-[200px_minmax(0,1fr)] md:px-7 md:py-5">
        <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto md:flex-col">
          {SECTIONS.map((s) => (
            <NavLink key={s.id} to={`/settings/${s.id}`} className={({ isActive }) => clsx('flex min-h-10 flex-none items-center gap-2.5 rounded-[9px] px-3 text-[13.5px] font-medium', isActive ? 'bg-tint font-semibold text-accent-ink' : 'text-muted hover:bg-line2 hover:text-ink')}>
              <Icon name={s.icon} size={17} />{s.label}
            </NavLink>
          ))}
        </nav>
        <div className="min-w-0 max-w-2xl">
          {section === 'profile' && <Profile />}
          {section === 'preferences' && <Preferences />}
          {section === 'appearance' && <Appearance />}
          {section === 'security' && <Security />}
          {section === 'data' && <Data />}
        </div>
      </div>
    </>
  )
}

const Card = ({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) => (
  <section className="card mb-4 p-4 md:p-5"><h2 className="m-0 text-[15px] font-semibold">{title}</h2>{desc && <p className="m-0 mt-1 text-[13px] text-muted">{desc}</p>}<div className="mt-4 flex flex-col gap-4">{children}</div></section>
)

function Profile() {
  const user = useAuthStore((s) => s.user)!
  const update = useUpdateProfile()
  const resend = useResendVerification()
  const [name, setName] = useState(user.display_name)
  const [role, setRole] = useState(user.role_title ?? '')
  const [tz, setTz] = useState(user.timezone)
  const zones = allTimezones()
  const dirty = name.trim() !== user.display_name || role.trim() !== (user.role_title ?? '') || tz !== user.timezone
  return (
    <>
      <Card title="Profile">
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); update.mutate({ display_name: name.trim(), role_title: role.trim() || null as any, timezone: tz }, { onSuccess: () => toast.success('Profile saved'), onError: (er) => toast.error(errorMessage(er)) }) }}>
          <Field label="Name">{(id) => <Input id={id} dense value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />}</Field>
          <Field label="Role" hint="Shown under your name in the sidebar.">{(id) => <Input id={id} dense value={role} maxLength={80} placeholder="e.g. Founder" onChange={(e) => setRole(e.target.value)} />}</Field>
          <Field label="Timezone" hint="Changing it never rewrites past activities; each keeps the zone it was logged in.">{(id) => <Select id={id} dense value={tz} onChange={(e) => setTz(e.target.value)}>{(zones.includes(tz) ? zones : [tz, ...zones]).map((z) => <option key={z}>{z}</option>)}</Select>}</Field>
          <div className="flex justify-end"><Button type="submit" variant="primary" disabled={!dirty || !name.trim()} loading={update.isPending}>Save</Button></div>
        </form>
      </Card>
      <Card title="Email">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><div className="text-sm font-medium">{user.email}</div><div className={clsx('mt-0.5 text-xs font-semibold', user.email_verified ? 'text-good' : 'text-warn')}>{user.email_verified ? 'Verified' : 'Not verified yet'}</div></div>
          {!user.email_verified && <Button loading={resend.isPending} onClick={() => resend.mutate(undefined, { onSuccess: () => toast.success('Verification email sent'), onError: (e) => toast.error(errorMessage(e)) })}>Send verification link</Button>}
        </div>
        {!user.email_verified && <p className="m-0 text-xs text-muted">Export and account deletion need a verified email.</p>}
      </Card>
    </>
  )
}

function Preferences() {
  const { data: p, isLoading, error, refetch } = usePreferences()
  const update = useUpdatePreferences()
  if (isLoading) return <Skeleton className="h-72" />
  if (error || !p) return <ErrorState error={error} onRetry={() => refetch()} />
  const save = (b: Parameters<typeof update.mutate>[0]) => update.mutate(b, { onError: (e) => toast.error(errorMessage(e)) })
  const hhmm = (m: number) => `${Math.floor(m / 60).toString().padStart(2, '0')}:${(m % 60).toString().padStart(2, '0')}`
  const toMin = (v: string) => { const [h, m] = v.split(':').map(Number); return h * 60 + m }
  return (
    <>
      <Card title="Time" desc="How days and times appear.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Week starts on">{(id) => <Select id={id} dense value={p.week_start} onChange={(e) => save({ week_start: Number(e.target.value) })}><option value={1}>Monday</option><option value={7}>Sunday</option><option value={6}>Saturday</option></Select>}</Field>
          <Field label="Clock">{(id) => <Select id={id} dense value={p.time_format} onChange={(e) => save({ time_format: e.target.value as any })}><option value="12h">12-hour (9:30am)</option><option value="24h">24-hour (09:30)</option></Select>}</Field>
        </div>
      </Card>
      <Card title="Coverage" desc="What counts as a fully logged day.">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Tolerance (min)" hint="A day this close to 24h counts as complete.">{(id) => <Input id={id} dense type="number" min={0} max={60} defaultValue={p.coverage_tolerance_minutes} onBlur={(e) => Number(e.target.value) !== p.coverage_tolerance_minutes && save({ coverage_tolerance_minutes: Number(e.target.value) })} />}</Field>
          <Field label="Smallest gap (min)" hint="Shorter unlogged gaps are not shown.">{(id) => <Input id={id} dense type="number" min={1} max={60} defaultValue={p.gap_min_minutes} onBlur={(e) => Number(e.target.value) !== p.gap_min_minutes && save({ gap_min_minutes: Number(e.target.value) })} />}</Field>
          <Field label="Short night (min)" hint="Sleep below this is flagged.">{(id) => <Input id={id} dense type="number" min={240} max={600} step={15} defaultValue={p.short_night_minutes} onBlur={(e) => Number(e.target.value) !== p.short_night_minutes && save({ short_night_minutes: Number(e.target.value) })} />}</Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Office hours start">{(id) => <Input id={id} dense type="time" step={900} defaultValue={hhmm(p.office_start_minute)} onBlur={(e) => e.target.value && toMin(e.target.value) !== p.office_start_minute && save({ office_start_minute: toMin(e.target.value) })} />}</Field>
          <Field label="Office hours end">{(id) => <Input id={id} dense type="time" step={900} defaultValue={hhmm(p.office_end_minute)} onBlur={(e) => e.target.value && toMin(e.target.value) !== p.office_end_minute && save({ office_end_minute: toMin(e.target.value) })} />}</Field>
        </div>
      </Card>
      <Card title="AI & privacy" desc="Applies when the AI journal arrives.">
        <label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={p.ai_enabled} onChange={(e) => save({ ai_enabled: e.target.checked })} /><span><b className="font-semibold">Use AI to turn journal entries into activities</b><span className="mt-0.5 block text-[13px] text-muted">When off, journal text is never sent to an AI provider; you log activities by hand. Your name, email and other entries are never sent either way.</span></span></label>
        <Field label="Voice input">{(id) => <Select id={id} dense value={p.transcription_mode} onChange={(e) => save({ transcription_mode: e.target.value as any })}><option value="auto">Automatic (browser first, server fallback)</option><option value="browser_only">Browser only (audio never leaves your device)</option><option value="server_only">Server only</option></Select>}</Field>
      </Card>
    </>
  )
}

function Appearance() {
  const mode = useThemeStore((s) => s.mode)
  const setMode = useThemeStore((s) => s.setMode)
  const update = useUpdateProfile()
  const pick = (m: ThemeMode) => { setMode(m); update.mutate({ theme: m }) }
  const opts: { v: ThemeMode; label: string; icon: IconName }[] = [{ v: 'system', label: 'Match system', icon: 'settings' }, { v: 'light', label: 'Light', icon: 'sun' }, { v: 'dark', label: 'Dark', icon: 'moon' }]
  return (
    <Card title="Theme" desc="Applies on all your devices.">
      <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-2.5">
        {opts.map((o) => <button key={o.v} type="button" role="radio" aria-checked={mode === o.v} onClick={() => pick(o.v)} className={clsx('flex flex-col items-center gap-2 rounded-xl border p-4 text-[13px] font-medium', mode === o.v ? 'border-accent bg-tint text-accent-ink' : 'border-line bg-card hover:border-ghostline')}><Icon name={o.icon} size={20} />{o.label}</button>)}
      </div>
    </Card>
  )
}

function Security() {
  const user = useAuthStore((s) => s.user)!
  const change = useChangePassword()
  const logout = useLogout()
  const nav = useNavigate()
  const { data: events, isLoading } = useAuthEvents()
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [err, setErr] = useState<string>()
  const label: Record<string, string> = { login_ok: 'Signed in', login_fail: 'Failed sign-in', logout: 'Signed out', password_changed: 'Password changed', reset_requested: 'Password reset requested', reset_done: 'Password reset', google_linked: 'Google linked' }
  return (
    <>
      <Card title="Password">
        {user.has_password ? (
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); setErr(undefined); change.mutate({ current_password: cur, new_password: next }, { onSuccess: () => { setCur(''); setNext(''); toast.success('Password changed. Other devices were signed out.') }, onError: (er) => setErr(errorMessage(er)) }) }}>
            <Field label="Current password">{(id) => <Input id={id} dense type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />}</Field>
            <Field label="New password" hint="At least 10 characters." error={err}>{(id, d) => <Input id={id} aria-describedby={d} dense type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />}</Field>
            <div className="flex justify-end"><Button type="submit" variant="primary" disabled={!cur || next.length < 10} loading={change.isPending}>Change password</Button></div>
          </form>
        ) : <p className="m-0 text-[13px] text-muted">You sign in with Google and have no password. Use “Forgot password” on the sign-in page to set one.</p>}
      </Card>
      <Card title="Sessions">
        <div className="flex flex-wrap items-center justify-between gap-3"><p className="m-0 text-[13px] text-muted">Sign out of every device, including this one.</p><Button icon="logout" loading={logout.isPending} onClick={() => logout.mutate(true, { onSettled: () => nav('/login') })}>Sign out everywhere</Button></div>
      </Card>
      <Card title="Recent security activity" desc="Sign-ins and password changes on your account. Kept for 90 days.">
        {isLoading ? <Skeleton className="h-24" /> : (
          <ul className="m-0 list-none p-0">{(events ?? []).map((e) => (
            <li key={e.id} className="flex items-baseline justify-between gap-3 border-b border-line2 py-2 text-[13px] last:border-0"><span className={clsx('font-medium', e.event_type === 'login_fail' && 'text-bad')}>{label[e.event_type] ?? e.event_type}</span><span className="text-right text-xs text-faint">{new Date(e.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}{e.ip ? ` · ${e.ip}` : ''}</span></li>
          ))}{(events ?? []).length === 0 && <li className="text-[13px] text-muted">Nothing yet.</li>}</ul>
        )}
      </Card>
    </>
  )
}

function Data() {
  const user = useAuthStore((s) => s.user)!
  const request = useRequestExport()
  const [jobId, setJobId] = useState<string>()
  const { data: job } = useExportJob(jobId)
  const [delOpen, setDelOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  async function download() {
    if (!job?.download_url) return
    setBusy(true)
    try {
      const r = await fetch(job.download_url, { headers: { Authorization: `Bearer ${useAuthStore.getState().accessToken}` }, credentials: 'include' })
      if (!r.ok) throw new Error()
      const url = URL.createObjectURL(await r.blob())
      const a = Object.assign(document.createElement('a'), { href: url, download: 'cadence-export.zip' })
      a.click(); URL.revokeObjectURL(url)
    } catch { toast.error('Download failed. Request a new export.') } finally { setBusy(false) }
  }
  const working = job && ['queued', 'running'].includes(job.status)
  return (
    <>
      <Card title="Export your data" desc="Everything you have logged as a ZIP of JSON files. The link works for 24 hours.">
        <div className="flex flex-wrap items-center gap-3">
          <Button icon="download" loading={request.isPending || !!working} disabled={!user.email_verified} onClick={() => request.mutate(undefined, { onSuccess: (j) => setJobId(j.id), onError: (e) => toast.error(errorMessage(e)) })}>{working ? 'Preparing…' : 'Request export'}</Button>
          {job?.status === 'succeeded' && <Button variant="primary" loading={busy} onClick={download}>Download ZIP</Button>}
          {job?.status === 'failed' && <span role="alert" className="text-[13px] text-bad">The export failed. Try again.</span>}
          {job?.status === 'expired' && <span className="text-[13px] text-muted">That export expired. Request a new one.</span>}
        </div>
        {!user.email_verified && <p className="m-0 text-xs text-muted">Verify your email first (Profile).</p>}
      </Card>
      <Card title="Delete account" desc="Permanently deletes your account and every activity, task, tag and category. This cannot be undone.">
        <div><Button variant="danger" icon="trash" disabled={!user.email_verified} onClick={() => setDelOpen(true)}>Delete my account</Button></div>
        {!user.email_verified && <p className="m-0 text-xs text-muted">Verify your email first (Profile).</p>}
      </Card>
      {delOpen && <DeleteDialog onClose={() => setDelOpen(false)} />}
    </>
  )
}

function DeleteDialog({ onClose }: { onClose: () => void }) {
  const del = useDeleteAccount()
  const nav = useNavigate()
  const [pw, setPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const [err, setErr] = useState<string>()
  useEffect(() => setErr(undefined), [pw, confirm])
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()} title="Delete your account?" description="Re-enter your password and type DELETE to confirm."
      footer={<><Button variant="subtle" onClick={onClose}>Cancel</Button><Button variant="danger" disabled={confirm !== 'DELETE' || !pw} loading={del.isPending} onClick={() => del.mutate({ password: pw, confirm }, { onSuccess: () => { useAuthStore.getState().clear(); nav('/login', { replace: true }); toast.info('Your account was deleted.') }, onError: (e) => setErr(errorMessage(e)) })}>Delete everything</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Password">{(id) => <Input id={id} dense type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} />}</Field>
        <Field label="Type DELETE" error={err}>{(id, d) => <Input id={id} aria-describedby={d} dense value={confirm} onChange={(e) => setConfirm(e.target.value)} />}</Field>
      </div>
    </Dialog>
  )
}
